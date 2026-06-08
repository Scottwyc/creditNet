from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import networkx as nx
import numpy as np

from creditnet.simulation import (
    BORROWER_WEIGHTED_RULES,
    LENDER_CASH_WEIGHTED_RULES,
    CreditNetworkParams,
    RunResult,
    compute_period_length,
    gini,
    net_worth,
    resolve_cascade,
    sample_initial_money,
    spend_and_distribute_income,
    validate_state,
)


SUPPORTED_TOPOLOGIES = {"er", "ba", "sw"}


@dataclass(frozen=True)
class TopologySpec:
    topology: str = "er"
    target_mean_degree: int = 12
    sw_rewire_probability: float = 0.10


def _target_edge_count(n_nodes: int, target_mean_degree: int) -> int:
    degree = min(max(int(target_mean_degree), 0), max(n_nodes - 1, 0))
    return min(n_nodes * degree // 2, n_nodes * (n_nodes - 1) // 2)


def _normalize_edge_count(graph: nx.Graph, target_edges: int, seed: int) -> nx.Graph:
    """Match edge count while retaining connectivity whenever the generator produced it."""
    rng = np.random.default_rng(seed)
    graph = nx.Graph(graph)
    graph.remove_edges_from(nx.selfloop_edges(graph))
    target_edges = min(max(target_edges, 0), graph.number_of_nodes() * (graph.number_of_nodes() - 1) // 2)

    while graph.number_of_edges() < target_edges:
        missing = list(nx.non_edges(graph))
        if not missing:
            break
        graph.add_edge(*missing[int(rng.integers(0, len(missing)))])

    preserve_connected = graph.number_of_nodes() > 0 and nx.is_connected(graph)
    while graph.number_of_edges() > target_edges:
        edges = list(graph.edges())
        rng.shuffle(edges)
        removed = False
        bridges = set(nx.bridges(graph)) if preserve_connected else set()
        bridges |= {(v, u) for u, v in bridges}
        for edge in edges:
            if preserve_connected and edge in bridges:
                continue
            graph.remove_edge(*edge)
            removed = True
            break
        if not removed:
            break
    return graph


def build_opportunity_graph(
    n_nodes: int,
    spec: TopologySpec,
    seed: int,
) -> nx.Graph:
    """Build an undirected graph of eligible counterparties for directed loans."""
    if spec.topology not in SUPPORTED_TOPOLOGIES:
        raise ValueError(f"unknown topology: {spec.topology}")
    if n_nodes < 0:
        raise ValueError("n_nodes must be non-negative")

    target_edges = _target_edge_count(n_nodes, spec.target_mean_degree)
    if n_nodes <= 1 or target_edges == 0:
        return nx.empty_graph(n_nodes)

    if spec.topology == "er":
        graph = nx.gnm_random_graph(n_nodes, target_edges, seed=seed)
    elif spec.topology == "ba":
        m = min(max(int(round(spec.target_mean_degree / 2)), 1), n_nodes - 1)
        graph = nx.barabasi_albert_graph(n_nodes, m, seed=seed)
        graph = _normalize_edge_count(graph, target_edges, seed + 101)
    else:
        degree = min(max(int(round(spec.target_mean_degree)), 2), n_nodes - 1)
        if degree % 2:
            degree = degree - 1 if degree > 2 else degree + 1
        degree = min(degree, n_nodes - 1)
        if degree % 2:
            degree -= 1
        graph = nx.watts_strogatz_graph(
            n_nodes,
            degree,
            min(max(float(spec.sw_rewire_probability), 0.0), 1.0),
            seed=seed,
        )
        graph = _normalize_edge_count(graph, target_edges, seed + 101)

    graph.add_nodes_from(range(n_nodes))
    return graph


def topology_metrics(graph: nx.Graph) -> dict[str, float | int]:
    n_nodes = graph.number_of_nodes()
    degrees = np.array([degree for _, degree in graph.degree()], dtype=float)
    components = sorted(nx.connected_components(graph), key=len, reverse=True)
    largest = components[0] if components else set()
    largest_subgraph = graph.subgraph(largest)
    mean_degree = float(degrees.mean()) if degrees.size else 0.0
    degree_std = float(degrees.std()) if degrees.size else 0.0
    return {
        "topology_nodes": n_nodes,
        "topology_edges": graph.number_of_edges(),
        "topology_mean_degree": mean_degree,
        "topology_density": float(nx.density(graph)) if n_nodes > 1 else 0.0,
        "topology_clustering": float(nx.average_clustering(graph)) if n_nodes else 0.0,
        "topology_degree_std": degree_std,
        "topology_degree_cv": degree_std / mean_degree if mean_degree > 0 else 0.0,
        "topology_max_degree": int(degrees.max()) if degrees.size else 0,
        "topology_components": len(components),
        "topology_lcc_nodes": len(largest),
        "topology_lcc_fraction": len(largest) / n_nodes if n_nodes else 0.0,
        "topology_lcc_average_path_length": (
            float(nx.average_shortest_path_length(largest_subgraph)) if len(largest) > 1 else 0.0
        ),
    }


def _choose_from_candidates(
    candidates: np.ndarray,
    weights: np.ndarray | None,
    rng: np.random.Generator,
) -> int | None:
    if candidates.size == 0:
        return None
    if weights is None:
        return int(rng.choice(candidates))
    candidate_weights = np.asarray(weights[candidates], dtype=float)
    total = float(candidate_weights.sum())
    if total <= 0:
        return int(rng.choice(candidates))
    return int(rng.choice(candidates, p=candidate_weights / total))


def grow_credit_network_on_topology(
    cash: np.ndarray,
    exposure: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    adjacency: tuple[np.ndarray, ...],
    last_total_income: int,
    params: CreditNetworkParams,
    rng: np.random.Generator,
    period_length_steps: int | None = None,
) -> tuple[np.ndarray, int, int, int]:
    """Issue directed credit only between nodes joined in the undirected opportunity graph."""
    planned_credit_events = (
        compute_period_length(last_total_income, params)
        if period_length_steps is None
        else int(period_length_steps)
    )
    borrowed_this_period = np.zeros(params.n_nodes, dtype=np.int64)
    issued = 0
    failed = 0
    attempted = 0
    worth = net_worth(cash, loan_assets, debt_liabilities)
    connected = np.array([neighbors.size > 0 for neighbors in adjacency], dtype=bool)

    for _ in range(max(planned_credit_events, 0)):
        attempted += 1
        valid_lenders = np.flatnonzero((cash >= 1) & connected)
        if valid_lenders.size == 0:
            failed += 1
            break
        lender_weights = cash if params.growth_rule in LENDER_CASH_WEIGHTED_RULES else None
        lender = _choose_from_candidates(valid_lenders, lender_weights, rng)
        if lender is None:
            failed += 1
            continue

        borrower_weights = None
        if params.growth_rule in BORROWER_WEIGHTED_RULES:
            if params.growth_rule in {"borrower_debt_preferential", "preferential_debt"}:
                borrower_weights = debt_liabilities.astype(float) + params.income_bias_floor
            else:
                borrower_weights = np.maximum(worth, 0).astype(float) + params.income_bias_floor
        borrower = _choose_from_candidates(adjacency[lender], borrower_weights, rng)
        if borrower is None:
            failed += 1
            continue

        cash[lender] -= 1
        cash[borrower] += 1
        exposure[lender, borrower] += 1
        loan_assets[lender] += 1
        debt_liabilities[borrower] += 1
        borrowed_this_period[borrower] += 1
        issued += 1

    return borrowed_this_period, issued, failed, attempted


def validate_topology_exposure(exposure: np.ndarray, graph: nx.Graph) -> None:
    allowed = nx.to_numpy_array(graph, nodelist=range(exposure.shape[0]), dtype=bool)
    if np.any((exposure > 0) & (~allowed)):
        raise RuntimeError("topology violation: credit exposure exists outside the opportunity graph")


def simulate_one_topology_run(
    params: CreditNetworkParams,
    topology_spec: TopologySpec,
    seed: int,
    topology_seed: int | None = None,
    keep_period_history: bool = False,
) -> RunResult:
    if params.default_check_mode != "period_end":
        raise ValueError("only default_check_mode='period_end' is implemented")
    if params.avalanche_protocol not in {"stop_on_first_default", "continue_after_avalanche"}:
        raise ValueError(f"unknown avalanche_protocol: {params.avalanche_protocol}")

    graph_seed = seed + 1_000_003 if topology_seed is None else int(topology_seed)
    graph = build_opportunity_graph(params.n_nodes, topology_spec, graph_seed)
    graph_stats = topology_metrics(graph)
    adjacency = tuple(
        np.fromiter(graph.neighbors(node), dtype=np.int64, count=graph.degree(node))
        for node in range(params.n_nodes)
    )

    rng = np.random.default_rng(seed)
    cash = sample_initial_money(params, rng)
    initial_money = cash.copy()
    initial_cash_total = int(initial_money.sum())
    exposure = np.zeros((params.n_nodes, params.n_nodes), dtype=np.int64)
    loan_assets = np.zeros(params.n_nodes, dtype=np.int64)
    debt_liabilities = np.zeros(params.n_nodes, dtype=np.int64)
    last_income = np.full(
        params.n_nodes,
        int(round(params.initial_income_per_capita)),
        dtype=np.int64,
    )
    last_total_income = int(last_income.sum())

    total_credit_issued = 0
    time_steps_completed = 0
    failed_credit_events = 0
    period_history: list[dict[str, Any]] = []
    avalanche_history: list[dict[str, Any]] = []
    ended_by_default = False
    max_collapse_size = 0
    total_collapse_size = 0
    credit_scale_before_cascade = 0
    first_cascade_period = 0
    first_cascade_time_steps = 0
    last_period_length_steps = 0
    max_period_length_steps = 0
    periods_completed = 0

    for period in range(1, params.max_periods + 1):
        period_length_steps = compute_period_length(last_total_income, params)
        last_period_length_steps = period_length_steps
        max_period_length_steps = max(max_period_length_steps, period_length_steps)
        borrowed, issued, failed, attempted = grow_credit_network_on_topology(
            cash,
            exposure,
            loan_assets,
            debt_liabilities,
            adjacency,
            last_total_income,
            params,
            rng,
            period_length_steps=period_length_steps,
        )
        time_steps_completed += attempted
        total_credit_issued += issued
        failed_credit_events += failed

        last_income, total_income, investment_spend, consumption_spend = spend_and_distribute_income(
            cash, loan_assets, debt_liabilities, last_income, borrowed, params, rng
        )
        last_total_income = total_income

        if params.validate_accounting:
            validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)
            validate_topology_exposure(exposure, graph)

        worth = net_worth(cash, loan_assets, debt_liabilities)
        initial_defaults = np.flatnonzero(worth < params.default_threshold)
        periods_completed = period

        if keep_period_history:
            period_history.append(
                {
                    "period": period,
                    "period_length_steps": period_length_steps,
                    "time_steps_completed": time_steps_completed,
                    "issued_credit": issued,
                    "failed_credit_events": failed,
                    "active_credit": int(exposure.sum()),
                    "active_directed_pairs": int(np.count_nonzero(exposure)),
                    "investment_spending": investment_spend,
                    "consumption_spending": consumption_spend,
                    "total_income": total_income,
                    "min_net_worth": float(worth.min()) if worth.size else 0.0,
                    "negative_net_worth_nodes": int(initial_defaults.size),
                    "cash_total": int(cash.sum()),
                }
            )

        if initial_defaults.size > 0:
            ended_by_default = True
            pre_cascade_credit = int(exposure.sum())
            pre_cascade_directed_pairs = int(np.count_nonzero(exposure))
            defaulted, _ = resolve_cascade(
                exposure, cash, loan_assets, debt_liabilities, initial_defaults, params
            )
            if params.validate_accounting:
                validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)
                validate_topology_exposure(exposure, graph)
            event_collapse_size = int(defaulted.sum())
            event_collapse_fraction = event_collapse_size / params.n_nodes if params.n_nodes else 0.0
            if not avalanche_history:
                credit_scale_before_cascade = pre_cascade_credit
                first_cascade_period = period
                first_cascade_time_steps = time_steps_completed
            max_collapse_size = max(max_collapse_size, event_collapse_size)
            total_collapse_size += event_collapse_size
            avalanche_history.append(
                {
                    "period": period,
                    "period_length_steps": period_length_steps,
                    "time_steps_completed": time_steps_completed,
                    "credit_scale_before_cascade": pre_cascade_credit,
                    "directed_pairs_before_cascade": pre_cascade_directed_pairs,
                    "active_credit_after_cascade": int(exposure.sum()),
                    "initial_default_count": int(initial_defaults.size),
                    "collapse_size": event_collapse_size,
                    "collapse_fraction": float(event_collapse_fraction),
                    "critical_event": bool(
                        event_collapse_fraction >= params.collapse_threshold_fraction
                    ),
                }
            )
            if params.avalanche_protocol == "stop_on_first_default":
                break

        if params.max_time_steps > 0 and time_steps_completed >= params.max_time_steps:
            break
    else:
        periods_completed = params.max_periods

    if not avalanche_history:
        credit_scale_before_cascade = int(exposure.sum())

    final_worth = net_worth(cash, loan_assets, debt_liabilities)
    collapse_size = max_collapse_size
    collapse_fraction = collapse_size / params.n_nodes if params.n_nodes > 0 else 0.0
    critical_event = any(event["critical_event"] for event in avalanche_history)
    result_params = asdict(params) | asdict(topology_spec) | {"topology_seed": graph_seed} | graph_stats

    return RunResult(
        params=result_params,
        seed=seed,
        ended_by_default=ended_by_default,
        periods_completed=periods_completed,
        time_steps_completed=time_steps_completed,
        first_cascade_period=first_cascade_period,
        first_cascade_time_steps=first_cascade_time_steps,
        last_period_length_steps=last_period_length_steps,
        max_period_length_steps=max_period_length_steps,
        total_credit_issued=total_credit_issued,
        credit_scale_before_cascade=credit_scale_before_cascade,
        active_credit_after_cascade=int(exposure.sum()),
        collapse_size=collapse_size,
        max_collapse_size=max_collapse_size,
        total_collapse_size=total_collapse_size,
        avalanche_count=len(avalanche_history),
        collapse_fraction=float(collapse_fraction),
        critical_event=bool(critical_event),
        initial_total_money=int(initial_money.sum()),
        final_cash_total=int(cash.sum()),
        final_active_credit=int(exposure.sum()),
        initial_money_gini=gini(initial_money),
        final_net_worth_gini=gini(final_worth),
        failed_credit_events=failed_credit_events,
        total_income_last_period=int(last_total_income),
        period_history=period_history,
        avalanche_history=avalanche_history,
    )
