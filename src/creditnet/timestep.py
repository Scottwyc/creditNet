from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .phase2_topology import (
    TopologySpec,
    build_opportunity_graph,
    grow_credit_network_on_topology,
    topology_metrics,
    validate_topology_exposure,
)
from .simulation import (
    CreditNetworkParams,
    compute_period_length,
    gini,
    grow_credit_network,
    net_worth,
    resolve_cascade,
    sample_initial_money,
    stochastic_round,
    validate_state,
)


@dataclass
class TimestepRunResult:
    params: dict[str, Any]
    seed: int
    ended_by_default: bool
    periods_completed: int
    time_steps_completed: int
    settlements_completed: int
    checks_completed: int
    first_cascade_period: int
    first_cascade_time_steps: int
    last_period_length_steps: int
    max_period_length_steps: int
    max_period_length_steps_cap: int
    max_uncapped_period_length_steps: int
    capped_periods: int
    total_credit_issued: int
    credit_scale_before_cascade: int
    active_credit_after_cascade: int
    collapse_size: int
    max_collapse_size: int
    total_collapse_size: int
    avalanche_count: int
    avalanche_period_count: int
    avalanche_timestep_rate: float
    avalanche_period_occupancy: float
    collapse_fraction: float
    critical_event: bool
    initial_total_money: int
    final_cash_total: int
    final_active_credit: int
    initial_money_gini: float
    final_net_worth_gini: float
    failed_credit_events: int
    total_income_last_period: int
    total_default_occurrences: int
    unique_default_nodes: int
    repeat_default_occurrences: int
    repeat_default_share: float
    period_history: list[dict[str, Any]]
    avalanche_history: list[dict[str, Any]]

    def summary_row(self) -> dict[str, Any]:
        row = {
            "seed": self.seed,
            "ended_by_default": self.ended_by_default,
            "periods_completed": self.periods_completed,
            "time_steps_completed": self.time_steps_completed,
            "settlements_completed": self.settlements_completed,
            "checks_completed": self.checks_completed,
            "first_cascade_period": self.first_cascade_period,
            "first_cascade_time_steps": self.first_cascade_time_steps,
            "last_period_length_steps": self.last_period_length_steps,
            "max_period_length_steps": self.max_period_length_steps,
            "max_period_length_steps_cap": self.max_period_length_steps_cap,
            "max_uncapped_period_length_steps": self.max_uncapped_period_length_steps,
            "capped_periods": self.capped_periods,
            "total_credit_issued": self.total_credit_issued,
            "credit_scale_before_cascade": self.credit_scale_before_cascade,
            "active_credit_after_cascade": self.active_credit_after_cascade,
            "collapse_size": self.collapse_size,
            "max_collapse_size": self.max_collapse_size,
            "total_collapse_size": self.total_collapse_size,
            "avalanche_count": self.avalanche_count,
            "avalanche_period_count": self.avalanche_period_count,
            "avalanche_timestep_rate": self.avalanche_timestep_rate,
            "avalanche_period_occupancy": self.avalanche_period_occupancy,
            "collapse_fraction": self.collapse_fraction,
            "critical_event": self.critical_event,
            "initial_total_money": self.initial_total_money,
            "final_cash_total": self.final_cash_total,
            "final_active_credit": self.final_active_credit,
            "initial_money_gini": self.initial_money_gini,
            "final_net_worth_gini": self.final_net_worth_gini,
            "failed_credit_events": self.failed_credit_events,
            "total_income_last_period": self.total_income_last_period,
            "total_default_occurrences": self.total_default_occurrences,
            "unique_default_nodes": self.unique_default_nodes,
            "repeat_default_occurrences": self.repeat_default_occurrences,
            "repeat_default_share": self.repeat_default_share,
        }
        row.update(self.params)
        return row


def spend_and_distribute_income_scaled(
    cash: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    macro_reference_income: np.ndarray,
    borrowed_since_settlement: np.ndarray,
    consumption_scale: float,
    params: CreditNetworkParams,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int, int, int]:
    worth_before_spending = net_worth(cash, loan_assets, debt_liabilities)
    consumption_plan = float(consumption_scale) * (
        params.consumption_wealth_propensity * np.maximum(worth_before_spending, 0)
        + params.consumption_income_propensity * np.maximum(macro_reference_income, 0)
    )
    planned_consumption = stochastic_round(consumption_plan, rng)

    investment_spending = np.minimum(cash, borrowed_since_settlement).astype(np.int64)
    cash -= investment_spending
    consumption_spending = np.minimum(cash, planned_consumption).astype(np.int64)
    cash -= consumption_spending
    total_spending = int(investment_spending.sum() + consumption_spending.sum())

    if total_spending <= 0:
        new_income = np.zeros_like(cash)
        return new_income, 0, int(investment_spending.sum()), int(consumption_spending.sum())

    if params.income_distribution_rule == "uniform":
        probs = np.full(params.n_nodes, 1.0 / params.n_nodes)
    elif params.income_distribution_rule == "biased":
        worth_after_spending = net_worth(cash, loan_assets, debt_liabilities)
        weights = np.maximum(worth_after_spending, 0).astype(float) + params.income_bias_floor
        probs = weights / weights.sum()
    else:
        raise ValueError(f"unknown income_distribution_rule: {params.income_distribution_rule}")

    new_income = rng.multinomial(total_spending, probs).astype(np.int64)
    cash += new_income
    return (
        new_income,
        int(new_income.sum()),
        int(investment_spending.sum()),
        int(consumption_spending.sum()),
    )


def _complete_topology_defaults(params: CreditNetworkParams, topology_seed: int) -> dict[str, int | float | str]:
    n = params.n_nodes
    edges = n * (n - 1) // 2
    return {
        "topology": "complete",
        "target_mean_degree": n - 1,
        "topology_seed": topology_seed,
        "topology_nodes": n,
        "topology_edges": edges,
        "topology_mean_degree": float(n - 1) if n else 0.0,
        "topology_density": 1.0 if n > 1 else 0.0,
        "topology_clustering": 1.0 if n > 2 else 0.0,
        "topology_degree_std": 0.0,
        "topology_degree_cv": 0.0,
        "topology_max_degree": n - 1 if n else 0,
        "topology_components": 1 if n else 0,
        "topology_lcc_nodes": n,
        "topology_lcc_fraction": 1.0 if n else 0.0,
        "topology_lcc_average_path_length": 1.0 if n > 1 else 0.0,
    }


def simulate_timestep_settle_check_run(
    params: CreditNetworkParams,
    seed: int,
    topology_spec: TopologySpec | None = None,
    topology_seed: int | None = None,
    max_period_length_steps_cap: int = 0,
    keep_period_history: bool = False,
) -> TimestepRunResult:
    """Run the timestep-level settlement/check protocol.

    A macro period still fixes ``K_t`` from the previous macro income. The macro
    period is then split into exactly ``K_t`` one-attempt batches. After each
    one-attempt credit time_step, the model settles investment spending plus
    ``1/K_t`` of the macro consumption plan, redistributes the resulting income,
    checks defaults, and clears a full avalanche before the next credit time_step.
    """

    if params.avalanche_protocol not in {"stop_on_first_default", "continue_after_avalanche"}:
        raise ValueError(f"unknown avalanche_protocol: {params.avalanche_protocol}")
    if params.default_check_mode not in {"period_end", "timestep_settle_check"}:
        raise ValueError(f"unknown default_check_mode: {params.default_check_mode}")

    graph = None
    adjacency: tuple[np.ndarray, ...] | None = None
    graph_stats: dict[str, Any]
    graph_seed = seed + 1_000_003 if topology_seed is None else int(topology_seed)
    if topology_spec is None:
        graph_stats = _complete_topology_defaults(params, graph_seed)
    else:
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
    settlements_completed = 0
    checks_completed = 0
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
    max_uncapped_period_length_steps = 0
    capped_periods = 0
    periods_completed = 0
    default_counts = np.zeros(params.n_nodes, dtype=np.int64)

    for period in range(1, params.max_periods + 1):
        periods_completed = period
        uncapped_period_length_steps = compute_period_length(last_total_income, params)
        period_length_steps = uncapped_period_length_steps
        if (
            max_period_length_steps_cap > 0
            and period_length_steps > max_period_length_steps_cap
        ):
            period_length_steps = int(max_period_length_steps_cap)
            capped_periods += 1
        last_period_length_steps = period_length_steps
        max_period_length_steps = max(max_period_length_steps, period_length_steps)
        max_uncapped_period_length_steps = max(
            max_uncapped_period_length_steps,
            uncapped_period_length_steps,
        )
        macro_reference_income = last_income.copy()
        macro_new_income = np.zeros(params.n_nodes, dtype=np.int64)
        macro_issued = 0
        macro_failed = 0
        macro_attempted = 0
        macro_investment_spending = 0
        macro_consumption_spending = 0
        macro_events_before = len(avalanche_history)
        steps_this_period = max(int(period_length_steps), 0)

        if steps_this_period == 0:
            last_income = macro_new_income
            last_total_income = 0
        for micro_step in range(1, steps_this_period + 1):
            if adjacency is None:
                borrowed, issued, failed, attempted = grow_credit_network(
                    cash,
                    exposure,
                    loan_assets,
                    debt_liabilities,
                    last_total_income,
                    params,
                    rng,
                    period_length_steps=1,
                )
            else:
                borrowed, issued, failed, attempted = grow_credit_network_on_topology(
                    cash,
                    exposure,
                    loan_assets,
                    debt_liabilities,
                    adjacency,
                    last_total_income,
                    params,
                    rng,
                    period_length_steps=1,
                )
            total_credit_issued += issued
            time_steps_completed += attempted
            failed_credit_events += failed
            macro_issued += issued
            macro_failed += failed
            macro_attempted += attempted

            income, _, investment_spend, consumption_spend = spend_and_distribute_income_scaled(
                cash,
                loan_assets,
                debt_liabilities,
                macro_reference_income,
                borrowed,
                1.0 / max(steps_this_period, 1),
                params,
                rng,
            )
            macro_new_income += income
            macro_investment_spending += investment_spend
            macro_consumption_spending += consumption_spend
            settlements_completed += 1

            if params.validate_accounting:
                validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)
                if graph is not None:
                    validate_topology_exposure(exposure, graph)

            checks_completed += 1
            worth = net_worth(cash, loan_assets, debt_liabilities)
            initial_defaults = np.flatnonzero(worth < params.default_threshold)
            if initial_defaults.size > 0:
                ended_by_default = True
                pre_cascade_credit = int(exposure.sum())
                pre_cascade_directed_pairs = int(np.count_nonzero(exposure))
                defaulted, _ = resolve_cascade(
                    exposure,
                    cash,
                    loan_assets,
                    debt_liabilities,
                    initial_defaults,
                    params,
                )
                if params.validate_accounting:
                    validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)
                    if graph is not None:
                        validate_topology_exposure(exposure, graph)
                repeat_default_nodes = int(np.sum(default_counts[defaulted] > 0))
                first_time_default_nodes = int(np.sum(default_counts[defaulted] == 0))
                default_counts[defaulted] += 1
                event_collapse_size = int(defaulted.sum())
                event_collapse_fraction = (
                    event_collapse_size / params.n_nodes if params.n_nodes else 0.0
                )
                if not avalanche_history:
                    credit_scale_before_cascade = pre_cascade_credit
                    first_cascade_period = period
                    first_cascade_time_steps = time_steps_completed
                max_collapse_size = max(max_collapse_size, event_collapse_size)
                total_collapse_size += event_collapse_size
                avalanche_history.append(
                    {
                        "event_index": len(avalanche_history) + 1,
                        "period": period,
                        "macro_period": period,
                        "micro_step_in_period": micro_step,
                        "uncapped_period_length_steps": uncapped_period_length_steps,
                        "period_length_steps": period_length_steps,
                        "time_steps_completed": time_steps_completed,
                        "settlements_completed": settlements_completed,
                        "checks_completed": checks_completed,
                        "check_kind": "timestep_settle_check",
                        "credit_scale_before_cascade": pre_cascade_credit,
                        "directed_pairs_before_cascade": pre_cascade_directed_pairs,
                        "active_credit_after_cascade": int(exposure.sum()),
                        "initial_default_count": int(initial_defaults.size),
                        "collapse_size": event_collapse_size,
                        "collapse_fraction": float(event_collapse_fraction),
                        "critical_event": bool(
                            event_collapse_fraction >= params.collapse_threshold_fraction
                        ),
                        "propagated_default_count": max(
                            event_collapse_size - int(initial_defaults.size), 0
                        ),
                        "first_time_default_nodes": first_time_default_nodes,
                        "repeat_default_nodes": repeat_default_nodes,
                        "investment_spending_since_check": investment_spend,
                        "consumption_spending_since_check": consumption_spend,
                    }
                )
                if params.avalanche_protocol == "stop_on_first_default":
                    break

            if params.max_time_steps > 0 and time_steps_completed >= params.max_time_steps:
                break

        last_income = macro_new_income
        last_total_income = int(macro_new_income.sum())
        if keep_period_history:
            period_history.append(
                {
                    "period": period,
                    "uncapped_period_length_steps": uncapped_period_length_steps,
                    "period_length_steps": period_length_steps,
                    "time_steps_completed": time_steps_completed,
                    "settlements_completed": settlements_completed,
                    "checks_completed": checks_completed,
                    "issued_credit": macro_issued,
                    "failed_credit_events": macro_failed,
                    "attempted": macro_attempted,
                    "active_credit": int(exposure.sum()),
                    "active_directed_pairs": int(np.count_nonzero(exposure)),
                    "investment_spending": macro_investment_spending,
                    "consumption_spending": macro_consumption_spending,
                    "total_income": last_total_income,
                    "avalanche_count": len(avalanche_history) - macro_events_before,
                    "cash_total": int(cash.sum()),
                }
            )

        if params.avalanche_protocol == "stop_on_first_default" and avalanche_history:
            break
        if params.max_time_steps > 0 and time_steps_completed >= params.max_time_steps:
            break

    if not avalanche_history:
        credit_scale_before_cascade = int(exposure.sum())

    final_worth = net_worth(cash, loan_assets, debt_liabilities)
    collapse_size = max_collapse_size
    collapse_fraction = collapse_size / params.n_nodes if params.n_nodes > 0 else 0.0
    critical_event = any(event["critical_event"] for event in avalanche_history)
    total_default_occurrences = int(default_counts.sum())
    unique_default_nodes = int(np.sum(default_counts > 0))
    repeat_default_occurrences = total_default_occurrences - unique_default_nodes
    avalanche_period_count = len({int(event["period"]) for event in avalanche_history})
    result_params = (
        asdict(params)
        | (asdict(topology_spec) if topology_spec is not None else {})
        | {"default_check_mode": "timestep_settle_check"}
        | {"max_period_length_steps_cap": int(max_period_length_steps_cap)}
        | graph_stats
    )

    return TimestepRunResult(
        params=result_params,
        seed=seed,
        ended_by_default=ended_by_default,
        periods_completed=periods_completed,
        time_steps_completed=time_steps_completed,
        settlements_completed=settlements_completed,
        checks_completed=checks_completed,
        first_cascade_period=first_cascade_period,
        first_cascade_time_steps=first_cascade_time_steps,
        last_period_length_steps=last_period_length_steps,
        max_period_length_steps=max_period_length_steps,
        max_period_length_steps_cap=int(max_period_length_steps_cap),
        max_uncapped_period_length_steps=max_uncapped_period_length_steps,
        capped_periods=capped_periods,
        total_credit_issued=total_credit_issued,
        credit_scale_before_cascade=credit_scale_before_cascade,
        active_credit_after_cascade=int(exposure.sum()),
        collapse_size=collapse_size,
        max_collapse_size=max_collapse_size,
        total_collapse_size=total_collapse_size,
        avalanche_count=len(avalanche_history),
        avalanche_period_count=avalanche_period_count,
        avalanche_timestep_rate=(
            len(avalanche_history) / time_steps_completed if time_steps_completed else 0.0
        ),
        avalanche_period_occupancy=(
            avalanche_period_count / periods_completed if periods_completed else 0.0
        ),
        collapse_fraction=float(collapse_fraction),
        critical_event=bool(critical_event),
        initial_total_money=int(initial_money.sum()),
        final_cash_total=int(cash.sum()),
        final_active_credit=int(exposure.sum()),
        initial_money_gini=gini(initial_money),
        final_net_worth_gini=gini(final_worth),
        failed_credit_events=failed_credit_events,
        total_income_last_period=int(last_total_income),
        total_default_occurrences=total_default_occurrences,
        unique_default_nodes=unique_default_nodes,
        repeat_default_occurrences=repeat_default_occurrences,
        repeat_default_share=(
            repeat_default_occurrences / total_default_occurrences
            if total_default_occurrences
            else 0.0
        ),
        period_history=period_history,
        avalanche_history=avalanche_history,
    )
