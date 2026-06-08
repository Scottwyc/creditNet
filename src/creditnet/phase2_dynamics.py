from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

import numpy as np

from creditnet.simulation import (
    CreditNetworkParams,
    RunResult,
    compute_period_length,
    gini,
    grow_credit_network,
    net_worth,
    sample_initial_money,
    simulate_one_run,
    spend_and_distribute_income,
    validate_state,
)


def resolve_cascade_waves(
    exposure: np.ndarray,
    cash: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    initial_defaults: np.ndarray,
    params: CreditNetworkParams,
) -> tuple[np.ndarray, list[int], list[float]]:
    """Resolve a cascade with baseline clearing order and label discovery generations.

    The baseline simulator processes a FIFO queue and appends currently negative,
    not-yet-processed nodes after every clearing. This function retains that exact
    behavior. A node's generation is the earliest queue-discovery generation:
    initial negative-net-worth nodes are generation 0, and nodes first discovered
    while processing generation g are generation g + 1.

    These are algorithmic labels, not synchronous clearing waves or physical time.
    Baseline queue membership is sticky: a queued node is processed without
    rechecking whether later sequential clearings restored its net worth.
    """
    defaulted = np.zeros(params.n_nodes, dtype=bool)
    scheduled_generation = np.full(params.n_nodes, -1, dtype=np.int64)
    queue: list[tuple[int, int]] = []
    for node in map(int, initial_defaults):
        queue.append((node, 0))
        scheduled_generation[node] = 0

    wave_sizes: list[int] = []
    queue_index = 0
    while queue_index < len(queue):
        node, queued_generation = queue[queue_index]
        queue_index += 1
        if defaulted[node]:
            continue

        generation = int(scheduled_generation[node])
        if generation < 0:
            generation = int(queued_generation)
            scheduled_generation[node] = generation
        while len(wave_sizes) <= generation:
            wave_sizes.append(0)
        wave_sizes[generation] += 1
        defaulted[node] = True

        incoming = exposure[:, node].copy()
        loan_assets -= incoming
        debt_liabilities[node] -= int(incoming.sum())
        exposure[:, node] = 0

        if params.wipe_defaulted_assets:
            outgoing = exposure[node, :].copy()
            debt_liabilities -= outgoing
            loan_assets[node] -= int(outgoing.sum())
            exposure[node, :] = 0

        worth = net_worth(cash, loan_assets, debt_liabilities)
        new_defaults = np.flatnonzero((worth < params.default_threshold) & (~defaulted))
        for new_node in map(int, new_defaults):
            next_generation = generation + 1
            queue.append((new_node, next_generation))
            if scheduled_generation[new_node] < 0:
                scheduled_generation[new_node] = next_generation
            else:
                scheduled_generation[new_node] = min(
                    int(scheduled_generation[new_node]), next_generation
                )

    branching_ratios = [
        float(wave_sizes[index + 1] / wave_sizes[index])
        for index in range(len(wave_sizes) - 1)
        if wave_sizes[index] > 0
    ]
    return defaulted, wave_sizes, branching_ratios


def _event_dynamics(wave_sizes: list[int], branching_ratios: list[float]) -> dict[str, Any]:
    parent_total = int(sum(wave_sizes[:-1])) if len(wave_sizes) > 1 else int(wave_sizes[0])
    propagated_total = int(sum(wave_sizes[1:]))
    weighted_branching = propagated_total / parent_total if parent_total > 0 else 0.0
    return {
        "wave_sizes": [int(value) for value in wave_sizes],
        "wave_branching_ratios": [float(value) for value in branching_ratios],
        "duration_generations": len(wave_sizes),
        "propagation_generations": max(len(wave_sizes) - 1, 0),
        "propagated_default_count": propagated_total,
        "max_wave_size": max(wave_sizes, default=0),
        "mean_wave_branching_ratio": (
            float(np.mean(branching_ratios)) if branching_ratios else 0.0
        ),
        "weighted_branching_ratio": float(weighted_branching),
    }


def simulate_one_dynamics_run(
    params: CreditNetworkParams,
    seed: int,
    keep_period_history: bool = False,
) -> RunResult:
    """Run the baseline model with avalanche wave and waiting-time instrumentation."""
    if params.default_check_mode != "period_end":
        raise ValueError("only default_check_mode='period_end' is implemented")
    if params.avalanche_protocol not in {"stop_on_first_default", "continue_after_avalanche"}:
        raise ValueError(f"unknown avalanche_protocol: {params.avalanche_protocol}")

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
    previous_avalanche_period: int | None = None
    previous_avalanche_time_steps: int | None = None

    for period in range(1, params.max_periods + 1):
        period_length_steps = compute_period_length(last_total_income, params)
        last_period_length_steps = period_length_steps
        max_period_length_steps = max(max_period_length_steps, period_length_steps)
        borrowed, issued, failed, attempted = grow_credit_network(
            cash,
            exposure,
            loan_assets,
            debt_liabilities,
            last_total_income,
            params,
            rng,
            period_length_steps=period_length_steps,
        )
        time_steps_completed += attempted
        total_credit_issued += issued
        failed_credit_events += failed

        last_income, total_income, investment_spend, consumption_spend = (
            spend_and_distribute_income(
                cash, loan_assets, debt_liabilities, last_income, borrowed, params, rng
            )
        )
        last_total_income = total_income

        if params.validate_accounting:
            validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)

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
            defaulted, wave_sizes, branching_ratios = resolve_cascade_waves(
                exposure, cash, loan_assets, debt_liabilities, initial_defaults, params
            )
            if params.validate_accounting:
                validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)
            event_collapse_size = int(defaulted.sum())
            if event_collapse_size != int(sum(wave_sizes)):
                raise RuntimeError("wave accounting violation: wave sizes do not sum to avalanche size")
            if wave_sizes and wave_sizes[0] != int(initial_defaults.size):
                raise RuntimeError("wave accounting violation: generation 0 differs from initial defaults")

            event_collapse_fraction = (
                event_collapse_size / params.n_nodes if params.n_nodes else 0.0
            )
            if not avalanche_history:
                credit_scale_before_cascade = pre_cascade_credit
                first_cascade_period = period
                first_cascade_time_steps = time_steps_completed
            max_collapse_size = max(max_collapse_size, event_collapse_size)
            total_collapse_size += event_collapse_size
            event = {
                "period": period,
                "period_length_steps": period_length_steps,
                "time_steps_completed": time_steps_completed,
                "credit_scale_before_cascade": pre_cascade_credit,
                "active_credit_after_cascade": int(exposure.sum()),
                "active_credit_cleared": pre_cascade_credit - int(exposure.sum()),
                "initial_default_count": int(initial_defaults.size),
                "collapse_size": event_collapse_size,
                "collapse_fraction": float(event_collapse_fraction),
                "critical_event": bool(
                    event_collapse_fraction >= params.collapse_threshold_fraction
                ),
                "period_waiting_time": (
                    period - previous_avalanche_period
                    if previous_avalanche_period is not None
                    else None
                ),
                "time_step_waiting_time": (
                    time_steps_completed - previous_avalanche_time_steps
                    if previous_avalanche_time_steps is not None
                    else None
                ),
            }
            event.update(_event_dynamics(wave_sizes, branching_ratios))
            avalanche_history.append(event)
            previous_avalanche_period = period
            previous_avalanche_time_steps = time_steps_completed
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

    return RunResult(
        params=asdict(params),
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


def validate_dynamics_against_baseline(
    params: CreditNetworkParams,
    seeds: Iterable[int],
) -> list[dict[str, Any]]:
    """Assert identical baseline events and common trajectory summaries."""
    run_fields = [
        "params",
        "seed",
        "ended_by_default",
        "periods_completed",
        "time_steps_completed",
        "first_cascade_period",
        "first_cascade_time_steps",
        "last_period_length_steps",
        "max_period_length_steps",
        "total_credit_issued",
        "credit_scale_before_cascade",
        "active_credit_after_cascade",
        "collapse_size",
        "max_collapse_size",
        "total_collapse_size",
        "avalanche_count",
        "collapse_fraction",
        "critical_event",
        "initial_total_money",
        "final_cash_total",
        "final_active_credit",
        "initial_money_gini",
        "final_net_worth_gini",
        "failed_credit_events",
        "total_income_last_period",
    ]
    event_fields = [
        "period",
        "period_length_steps",
        "time_steps_completed",
        "credit_scale_before_cascade",
        "active_credit_after_cascade",
        "initial_default_count",
        "collapse_size",
        "collapse_fraction",
        "critical_event",
    ]
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        baseline = simulate_one_run(params, int(seed))
        dynamics = simulate_one_dynamics_run(params, int(seed))
        mismatches = []
        for field in run_fields:
            baseline_value = getattr(baseline, field)
            dynamics_value = getattr(dynamics, field)
            if isinstance(baseline_value, float):
                if not np.isclose(baseline_value, dynamics_value, equal_nan=True):
                    mismatches.append(field)
            elif baseline_value != dynamics_value:
                mismatches.append(field)
        if len(baseline.avalanche_history) != len(dynamics.avalanche_history):
            mismatches.append("avalanche_history_length")
        for index, (base_event, dynamic_event) in enumerate(
            zip(baseline.avalanche_history, dynamics.avalanche_history), start=1
        ):
            for field in event_fields:
                if isinstance(base_event[field], float):
                    matched = np.isclose(
                        base_event[field], dynamic_event[field], equal_nan=True
                    )
                else:
                    matched = base_event[field] == dynamic_event[field]
                if not matched:
                    mismatches.append(f"event_{index}_{field}")
            if int(sum(dynamic_event["wave_sizes"])) != int(dynamic_event["collapse_size"]):
                mismatches.append(f"event_{index}_wave_sum")
        rows.append(
            {
                "seed": int(seed),
                "matched": not mismatches,
                "mismatches": ";".join(mismatches),
                "baseline_event_count": len(baseline.avalanche_history),
                "dynamics_event_count": len(dynamics.avalanche_history),
                "baseline_total_collapse_size": baseline.total_collapse_size,
                "dynamics_total_collapse_size": dynamics.total_collapse_size,
            }
        )
        if mismatches:
            raise AssertionError(f"dynamics mismatch for seed={seed}: {mismatches}")
    return rows
