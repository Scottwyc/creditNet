#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet.simulation import (
    CreditNetworkParams,
    compute_period_length,
    gini,
    grow_credit_network,
    net_worth,
    resolve_cascade,
    sample_initial_money,
    simulate_one_run,
    spend_and_distribute_income,
    validate_state,
)


CST = ZoneInfo("Asia/Shanghai")
DEFAULT_INCOME_VALUES = "0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80"
DEFAULT_FIXED_VALUES = "1,2,5,10,15,18,20,22,24,26,30"
DEFAULT_DISTRIBUTIONS = "lognormal,pareto"
EVENT_FIELDS = [
    "family",
    "scenario_id",
    "scenario_index",
    "run_index",
    "seed",
    "n_nodes",
    "money_distribution",
    "control_name",
    "control_value",
    "period",
    "time_bin",
    "window",
    "avalanche_index",
    "period_length_steps",
    "time_steps_completed",
    "period_waiting_time",
    "credit_scale_before_cascade",
    "active_credit_after_cascade",
    "active_credit_cleared",
    "initial_default_count",
    "propagated_default_count",
    "propagated_default_share",
    "single_initial_default",
    "collapse_size",
    "collapse_fraction",
    "critical_event",
    "new_unique_default_count",
    "repeated_default_count",
    "cumulative_unique_default_nodes",
    "cumulative_repeated_default_occurrences",
    "post_cascade_gini",
]


def parse_float_list(text: str) -> list[float]:
    return [float(value) for value in text.split(",") if value.strip()]


def parse_int_list(text: str) -> list[int]:
    return [int(value) for value in text.split(",") if value.strip()]


def parse_str_list(text: str) -> list[str]:
    return [value.strip() for value in text.split(",") if value.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run long baseline stationarity searches.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--family", choices=["income", "fixed"], required=True)
    parser.add_argument("--income-values", default=DEFAULT_INCOME_VALUES)
    parser.add_argument("--fixed-k-values", default=DEFAULT_FIXED_VALUES)
    parser.add_argument("--money-distributions", default=DEFAULT_DISTRIBUTIONS)
    parser.add_argument("--runs-per-scenario", type=int, default=12)
    parser.add_argument("--max-periods", type=int, default=2000)
    parser.add_argument("--n-nodes", type=int, default=200)
    parser.add_argument("--seed-base", type=int, default=2026400000)
    parser.add_argument("--window-fraction", type=float, default=0.20)
    parser.add_argument("--time-bins", type=int, default=10)
    parser.add_argument("--progress-every", type=int, default=12)
    parser.add_argument("--baseline-validation-runs", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def scenario_id(family: str, control_value: float, distribution: str, n_nodes: int) -> str:
    control = (
        f"c{control_value:.2f}".replace(".", "p")
        if family == "income"
        else f"K{int(control_value)}"
    )
    return f"{family}__N{n_nodes}__{control}__{distribution}__biased__random"


def build_scenarios(args: argparse.Namespace) -> list[dict[str, Any]]:
    distributions = parse_str_list(args.money_distributions)
    controls = (
        parse_float_list(args.income_values)
        if args.family == "income"
        else [float(value) for value in parse_int_list(args.fixed_k_values)]
    )
    family_offset = 0 if args.family == "income" else 20
    scenarios: list[dict[str, Any]] = []
    for control_index, control_value in enumerate(controls):
        for distribution_index, distribution in enumerate(distributions):
            scenario_index = family_offset + control_index * len(distributions) + distribution_index
            params = CreditNetworkParams(
                n_nodes=args.n_nodes,
                mean_initial_money=20.0,
                money_distribution=distribution,
                income_distribution_rule="biased",
                growth_rule="random",
                consumption_wealth_propensity=0.02,
                consumption_income_propensity=0.20,
                investment_income_propensity=(
                    control_value if args.family == "income" else 0.20
                ),
                initial_income_per_capita=5.0,
                income_bias_floor=1.0,
                collapse_threshold_fraction=0.10,
                max_periods=args.max_periods,
                default_threshold=0.0,
                wipe_defaulted_assets=True,
                validate_accounting=True,
                period_length_rule=args.family,
                fixed_period_length_steps=(
                    int(control_value) if args.family == "fixed" else 100
                ),
                avalanche_protocol="continue_after_avalanche",
                default_check_mode="period_end",
            )
            seed_start = args.seed_base + scenario_index * 10_000
            scenarios.append(
                {
                    "family": args.family,
                    "scenario_id": scenario_id(
                        args.family, control_value, distribution, args.n_nodes
                    ),
                    "scenario_index": scenario_index,
                    "control_name": "c" if args.family == "income" else "fixed_k",
                    "control_value": float(control_value),
                    "runs": args.runs_per_scenario,
                    "seed_start": seed_start,
                    "seed_end": seed_start + args.runs_per_scenario - 1,
                    "params": asdict(params),
                }
            )
    return scenarios


def correlation(values: list[int]) -> float:
    if len(values) < 3:
        return float("nan")
    left = np.asarray(values[:-1], dtype=float)
    right = np.asarray(values[1:], dtype=float)
    if np.std(left) == 0 or np.std(right) == 0:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def new_period_accumulator() -> dict[str, Any]:
    return {
        "period_count": 0,
        "event_count": 0,
        "large_event_count": 0,
        "event_sizes": [],
        "event_periods": [],
        "initial_default_count_sum": 0,
        "propagated_default_count_sum": 0,
        "single_initial_default_count": 0,
        "default_nodes": set(),
        "total_default_occurrences": 0,
        "active_credit_sum": 0.0,
        "gini_sum": 0.0,
        "period_length_sum": 0.0,
        "issued_credit_sum": 0.0,
        "total_income_sum": 0.0,
        "first_active_credit": None,
        "last_active_credit": None,
        "first_gini": None,
        "last_gini": None,
    }


def update_period_accumulator(
    accumulator: dict[str, Any],
    period: int,
    period_length_steps: int,
    issued: int,
    total_income: int,
    active_credit: int,
    final_gini: float,
    defaulted_nodes: np.ndarray | None,
    initial_default_count: int,
    critical_event: bool,
) -> None:
    accumulator["period_count"] += 1
    accumulator["active_credit_sum"] += active_credit
    accumulator["gini_sum"] += final_gini
    accumulator["period_length_sum"] += period_length_steps
    accumulator["issued_credit_sum"] += issued
    accumulator["total_income_sum"] += total_income
    if accumulator["first_active_credit"] is None:
        accumulator["first_active_credit"] = active_credit
        accumulator["first_gini"] = final_gini
    accumulator["last_active_credit"] = active_credit
    accumulator["last_gini"] = final_gini
    if defaulted_nodes is None:
        return
    nodes = np.flatnonzero(defaulted_nodes)
    size = int(nodes.size)
    accumulator["event_count"] += 1
    accumulator["large_event_count"] += int(critical_event)
    accumulator["event_sizes"].append(size)
    accumulator["event_periods"].append(period)
    accumulator["initial_default_count_sum"] += initial_default_count
    accumulator["propagated_default_count_sum"] += size - initial_default_count
    accumulator["single_initial_default_count"] += int(initial_default_count == 1)
    accumulator["total_default_occurrences"] += size
    accumulator["default_nodes"].update(map(int, nodes))


def finalize_period_accumulator(
    accumulator: dict[str, Any],
    base: dict[str, Any],
    label_name: str,
    label_value: str | int,
) -> dict[str, Any]:
    period_count = int(accumulator["period_count"])
    event_sizes = np.asarray(accumulator["event_sizes"], dtype=float)
    waits = np.diff(np.asarray(accumulator["event_periods"], dtype=int))
    unique_defaults = len(accumulator["default_nodes"])
    total_defaults = int(accumulator["total_default_occurrences"])
    row = dict(base)
    row[label_name] = label_value
    row.update(
        {
            "period_count": period_count,
            "event_count": int(accumulator["event_count"]),
            "avalanche_occupancy": (
                accumulator["event_count"] / period_count if period_count else 0.0
            ),
            "one_period_wait_fraction": (
                float(np.mean(waits == 1)) if waits.size else float("nan")
            ),
            "size_lag1_correlation": correlation(accumulator["event_sizes"]),
            "mean_event_size": float(event_sizes.mean()) if event_sizes.size else 0.0,
            "median_event_size": float(np.median(event_sizes)) if event_sizes.size else 0.0,
            "p90_event_size": (
                float(np.quantile(event_sizes, 0.90)) if event_sizes.size else 0.0
            ),
            "p99_event_size": (
                float(np.quantile(event_sizes, 0.99)) if event_sizes.size else 0.0
            ),
            "max_event_size": int(event_sizes.max()) if event_sizes.size else 0,
            "large_event_count": int(accumulator["large_event_count"]),
            "large_event_rate": (
                accumulator["large_event_count"] / accumulator["event_count"]
                if accumulator["event_count"]
                else 0.0
            ),
            "mean_initial_default_count": (
                accumulator["initial_default_count_sum"] / accumulator["event_count"]
                if accumulator["event_count"]
                else 0.0
            ),
            "mean_propagated_default_count": (
                accumulator["propagated_default_count_sum"] / accumulator["event_count"]
                if accumulator["event_count"]
                else 0.0
            ),
            "propagated_default_share": (
                accumulator["propagated_default_count_sum"] / total_defaults
                if total_defaults
                else 0.0
            ),
            "single_initial_default_fraction": (
                accumulator["single_initial_default_count"] / accumulator["event_count"]
                if accumulator["event_count"]
                else 0.0
            ),
            "mean_active_credit": (
                accumulator["active_credit_sum"] / period_count if period_count else 0.0
            ),
            "mean_final_net_worth_gini": (
                accumulator["gini_sum"] / period_count if period_count else 0.0
            ),
            "mean_period_length_steps": (
                accumulator["period_length_sum"] / period_count if period_count else 0.0
            ),
            "mean_issued_credit": (
                accumulator["issued_credit_sum"] / period_count if period_count else 0.0
            ),
            "mean_total_income": (
                accumulator["total_income_sum"] / period_count if period_count else 0.0
            ),
            "first_active_credit": accumulator["first_active_credit"],
            "last_active_credit": accumulator["last_active_credit"],
            "first_gini": accumulator["first_gini"],
            "last_gini": accumulator["last_gini"],
            "unique_default_nodes_in_window": unique_defaults,
            "total_default_occurrences_in_window": total_defaults,
            "repeated_default_occurrences_in_window": total_defaults - unique_defaults,
            "repeated_default_share_in_window": (
                (total_defaults - unique_defaults) / total_defaults if total_defaults else 0.0
            ),
        }
    )
    return row


def simulate_stationarity_run(
    params: CreditNetworkParams,
    seed: int,
    shared: dict[str, Any],
    event_writer: csv.DictWriter,
    window_fraction: float,
    time_bins: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    if params.default_check_mode != "period_end":
        raise ValueError("stationarity search requires default_check_mode='period_end'")
    if params.avalanche_protocol != "continue_after_avalanche":
        raise ValueError("stationarity search requires continue_after_avalanche")
    rng = np.random.default_rng(seed)
    cash = sample_initial_money(params, rng)
    initial_money = cash.copy()
    initial_cash_total = int(initial_money.sum())
    exposure = np.zeros((params.n_nodes, params.n_nodes), dtype=np.int64)
    loan_assets = np.zeros(params.n_nodes, dtype=np.int64)
    debt_liabilities = np.zeros(params.n_nodes, dtype=np.int64)
    last_income = np.full(
        params.n_nodes, int(round(params.initial_income_per_capita)), dtype=np.int64
    )
    last_total_income = int(last_income.sum())

    edge_periods = max(1, int(round(params.max_periods * window_fraction)))
    late_start = params.max_periods - edge_periods + 1
    windows = {"early": new_period_accumulator(), "late": new_period_accumulator()}
    bins = [new_period_accumulator() for _ in range(time_bins)]
    ever_defaulted = np.zeros(params.n_nodes, dtype=bool)
    total_credit_issued = 0
    failed_credit_events = 0
    time_steps_completed = 0
    first_cascade_period = 0
    first_cascade_time_steps = 0
    max_collapse_size = 0
    total_default_occurrences = 0
    critical_event_count = 0
    avalanche_count = 0
    total_initial_default_count = 0
    total_propagated_default_count = 0
    single_initial_default_events = 0
    previous_avalanche_period: int | None = None
    event_sizes: list[int] = []
    event_periods: list[int] = []
    event_hash = hashlib.sha256()
    max_period_length_steps = 0
    last_period_length_steps = 0

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
        total_credit_issued += issued
        failed_credit_events += failed
        time_steps_completed += attempted
        last_income, total_income, _, _ = spend_and_distribute_income(
            cash, loan_assets, debt_liabilities, last_income, borrowed, params, rng
        )
        last_total_income = total_income
        validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)
        worth = net_worth(cash, loan_assets, debt_liabilities)
        initial_defaults = np.flatnonzero(worth < params.default_threshold)

        defaulted_nodes: np.ndarray | None = None
        critical_event = False
        if initial_defaults.size > 0:
            pre_cascade_credit = int(exposure.sum())
            defaulted_nodes, _ = resolve_cascade(
                exposure, cash, loan_assets, debt_liabilities, initial_defaults, params
            )
            validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)
            collapse_size = int(defaulted_nodes.sum())
            initial_default_count = int(initial_defaults.size)
            propagated_default_count = collapse_size - initial_default_count
            collapse_fraction = collapse_size / params.n_nodes
            critical_event = collapse_fraction >= params.collapse_threshold_fraction
            new_unique = int(np.sum(defaulted_nodes & (~ever_defaulted)))
            repeated = collapse_size - new_unique
            ever_defaulted |= defaulted_nodes
            avalanche_count += 1
            total_default_occurrences += collapse_size
            total_initial_default_count += initial_default_count
            total_propagated_default_count += propagated_default_count
            single_initial_default_events += int(initial_default_count == 1)
            critical_event_count += int(critical_event)
            max_collapse_size = max(max_collapse_size, collapse_size)
            if first_cascade_period == 0:
                first_cascade_period = period
                first_cascade_time_steps = time_steps_completed
            waiting = (
                period - previous_avalanche_period
                if previous_avalanche_period is not None
                else None
            )
            previous_avalanche_period = period
            event_periods.append(period)
            event_sizes.append(collapse_size)
            event_hash.update(f"{period}:{collapse_size};".encode("ascii"))
            active_after = int(exposure.sum())
            post_gini = gini(net_worth(cash, loan_assets, debt_liabilities))
            window = "early" if period <= edge_periods else ("late" if period >= late_start else "")
            time_bin = min(time_bins, 1 + ((period - 1) * time_bins // params.max_periods))
            event_writer.writerow(
                shared
                | {
                    "period": period,
                    "time_bin": time_bin,
                    "window": window,
                    "avalanche_index": avalanche_count,
                    "period_length_steps": period_length_steps,
                    "time_steps_completed": time_steps_completed,
                    "period_waiting_time": waiting,
                    "credit_scale_before_cascade": pre_cascade_credit,
                    "active_credit_after_cascade": active_after,
                    "active_credit_cleared": pre_cascade_credit - active_after,
                    "initial_default_count": initial_default_count,
                    "propagated_default_count": propagated_default_count,
                    "propagated_default_share": (
                        propagated_default_count / collapse_size if collapse_size else 0.0
                    ),
                    "single_initial_default": initial_default_count == 1,
                    "collapse_size": collapse_size,
                    "collapse_fraction": collapse_fraction,
                    "critical_event": critical_event,
                    "new_unique_default_count": new_unique,
                    "repeated_default_count": repeated,
                    "cumulative_unique_default_nodes": int(ever_defaulted.sum()),
                    "cumulative_repeated_default_occurrences": (
                        total_default_occurrences - int(ever_defaulted.sum())
                    ),
                    "post_cascade_gini": post_gini,
                }
            )

        final_active_credit = int(exposure.sum())
        final_gini = gini(net_worth(cash, loan_assets, debt_liabilities))
        bin_index = min(time_bins - 1, (period - 1) * time_bins // params.max_periods)
        update_period_accumulator(
            bins[bin_index],
            period,
            period_length_steps,
            issued,
            total_income,
            final_active_credit,
            final_gini,
            defaulted_nodes,
            int(initial_defaults.size),
            critical_event,
        )
        if period <= edge_periods:
            update_period_accumulator(
                windows["early"],
                period,
                period_length_steps,
                issued,
                total_income,
                final_active_credit,
                final_gini,
                defaulted_nodes,
                int(initial_defaults.size),
                critical_event,
            )
        if period >= late_start:
            update_period_accumulator(
                windows["late"],
                period,
                period_length_steps,
                issued,
                total_income,
                final_active_credit,
                final_gini,
                defaulted_nodes,
                int(initial_defaults.size),
                critical_event,
            )

    final_worth = net_worth(cash, loan_assets, debt_liabilities)
    unique_default_nodes = int(ever_defaulted.sum())
    run_row = shared | {
        "periods_completed": params.max_periods,
        "time_steps_completed": time_steps_completed,
        "first_cascade_period": first_cascade_period,
        "first_cascade_time_steps": first_cascade_time_steps,
        "last_period_length_steps": last_period_length_steps,
        "max_period_length_steps": max_period_length_steps,
        "total_credit_issued": total_credit_issued,
        "failed_credit_events": failed_credit_events,
        "avalanche_count": avalanche_count,
        "critical_event_count": critical_event_count,
        "critical_event": critical_event_count > 0,
        "max_collapse_size": max_collapse_size,
        "total_default_occurrences": total_default_occurrences,
        "total_initial_default_count": total_initial_default_count,
        "total_propagated_default_count": total_propagated_default_count,
        "propagated_default_share": (
            total_propagated_default_count / total_default_occurrences
            if total_default_occurrences
            else 0.0
        ),
        "single_initial_default_events": single_initial_default_events,
        "single_initial_default_fraction": (
            single_initial_default_events / avalanche_count if avalanche_count else 0.0
        ),
        "unique_default_nodes": unique_default_nodes,
        "repeated_default_occurrences": total_default_occurrences - unique_default_nodes,
        "repeated_default_share": (
            (total_default_occurrences - unique_default_nodes) / total_default_occurrences
            if total_default_occurrences
            else 0.0
        ),
        "avalanche_occupancy": avalanche_count / params.max_periods,
        "one_period_wait_fraction": (
            float(np.mean(np.diff(np.asarray(event_periods, dtype=int)) == 1))
            if len(event_periods) > 1
            else float("nan")
        ),
        "size_lag1_correlation": correlation(event_sizes),
        "initial_total_money": initial_cash_total,
        "final_cash_total": int(cash.sum()),
        "cash_residual": int(cash.sum()) - initial_cash_total,
        "final_active_credit": int(exposure.sum()),
        "initial_money_gini": gini(initial_money),
        "final_net_worth_gini": gini(final_worth),
        "total_income_last_period": int(last_total_income),
        "event_sequence_sha256": event_hash.hexdigest(),
    }
    window_base = shared | {"edge_window_periods": edge_periods}
    window_rows = [
        finalize_period_accumulator(windows[name], window_base, "window", name)
        for name in ["early", "late"]
    ]
    bin_rows = [
        finalize_period_accumulator(accumulator, shared, "time_bin", index + 1)
        for index, accumulator in enumerate(bins)
    ]
    return run_row, window_rows, bin_rows


def baseline_equivalence_row(
    params: CreditNetworkParams, run_row: dict[str, Any], seed: int
) -> dict[str, Any]:
    baseline = simulate_one_run(params, seed=seed, keep_period_history=False)
    baseline_hash = hashlib.sha256()
    for event in baseline.avalanche_history:
        baseline_hash.update(f"{event['period']}:{event['collapse_size']};".encode("ascii"))
    comparisons = {
        "periods_completed": baseline.periods_completed == run_row["periods_completed"],
        "time_steps_completed": baseline.time_steps_completed == run_row["time_steps_completed"],
        "total_credit_issued": baseline.total_credit_issued == run_row["total_credit_issued"],
        "failed_credit_events": baseline.failed_credit_events == run_row["failed_credit_events"],
        "avalanche_count": baseline.avalanche_count == run_row["avalanche_count"],
        "max_collapse_size": baseline.max_collapse_size == run_row["max_collapse_size"],
        "total_collapse_size": baseline.total_collapse_size
        == run_row["total_default_occurrences"],
        "final_active_credit": baseline.final_active_credit == run_row["final_active_credit"],
        "final_cash_total": baseline.final_cash_total == run_row["final_cash_total"],
        "final_net_worth_gini": bool(
            np.isclose(baseline.final_net_worth_gini, run_row["final_net_worth_gini"])
        ),
        "event_sequence_sha256": baseline_hash.hexdigest()
        == run_row["event_sequence_sha256"],
    }
    return {
        "scenario_id": run_row["scenario_id"],
        "seed": seed,
        **comparisons,
        "all_match": all(comparisons.values()),
    }


def main() -> None:
    args = parse_args()
    if args.runs_per_scenario < 1:
        raise ValueError("--runs-per-scenario must be positive")
    if args.max_periods < 2:
        raise ValueError("--max-periods must be at least 2")
    if not 0.0 < args.window_fraction <= 0.5:
        raise ValueError("--window-fraction must be in (0, 0.5]")
    if args.time_bins < 2:
        raise ValueError("--time-bins must be at least 2")
    scenarios = build_scenarios(args)
    if args.dry_run:
        print(json.dumps({"args": vars(args) | {"output_dir": str(args.output_dir)}, "scenarios": scenarios}, indent=2))
        return

    args.output_dir.mkdir(parents=True, exist_ok=False)
    started = datetime.now(CST)
    run_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    bin_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    event_count = 0
    total_runs = sum(int(scenario["runs"]) for scenario in scenarios)
    event_path = args.output_dir / "avalanche_events.csv"
    with event_path.open("w", newline="", encoding="utf-8") as event_file:
        event_writer = csv.DictWriter(event_file, fieldnames=EVENT_FIELDS)
        event_writer.writeheader()
        completed = 0
        for scenario in scenarios:
            params = CreditNetworkParams(**scenario["params"])
            for run_index in range(scenario["runs"]):
                seed = scenario["seed_start"] + run_index
                shared = {
                    "family": scenario["family"],
                    "scenario_id": scenario["scenario_id"],
                    "scenario_index": scenario["scenario_index"],
                    "run_index": run_index,
                    "seed": seed,
                    "n_nodes": params.n_nodes,
                    "money_distribution": params.money_distribution,
                    "control_name": scenario["control_name"],
                    "control_value": scenario["control_value"],
                }
                run_row, task_windows, task_bins = simulate_stationarity_run(
                    params,
                    seed,
                    shared,
                    event_writer,
                    args.window_fraction,
                    args.time_bins,
                )
                run_rows.append(run_row)
                window_rows.extend(task_windows)
                bin_rows.extend(task_bins)
                event_count += int(run_row["avalanche_count"])
                if completed < args.baseline_validation_runs:
                    validation = baseline_equivalence_row(params, run_row, seed)
                    validation_rows.append(validation)
                    if not validation["all_match"]:
                        raise RuntimeError(f"baseline equivalence failed: {validation}")
                completed += 1
                if args.progress_every > 0 and (
                    completed % args.progress_every == 0 or completed == total_runs
                ):
                    print(
                        f"completed_runs={completed}/{total_runs} events={event_count} "
                        f"time={datetime.now(CST).isoformat()}",
                        file=sys.stderr,
                        flush=True,
                    )

    pd.DataFrame(run_rows).sort_values(["scenario_index", "run_index"]).to_csv(
        args.output_dir / "run_summary.csv", index=False
    )
    pd.DataFrame(window_rows).sort_values(
        ["scenario_index", "run_index", "window"]
    ).to_csv(args.output_dir / "run_windows.csv", index=False)
    pd.DataFrame(bin_rows).sort_values(
        ["scenario_index", "run_index", "time_bin"]
    ).to_csv(args.output_dir / "run_time_bins.csv", index=False)
    pd.DataFrame(validation_rows).to_csv(
        args.output_dir / "baseline_equivalence.csv", index=False
    )
    finished = datetime.now(CST)
    metadata = {
        "created_at": finished.isoformat(),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_seconds": (finished - started).total_seconds(),
        "command": " ".join(sys.argv),
        "args": vars(args) | {"output_dir": str(args.output_dir)},
        "scenario_count": len(scenarios),
        "run_count": len(run_rows),
        "event_count": event_count,
        "period_count": int(sum(row["periods_completed"] for row in run_rows)),
        "all_accounting_residuals_zero": all(row["cash_residual"] == 0 for row in run_rows),
        "all_baseline_equivalence_match": all(
            row["all_match"] for row in validation_rows
        ),
        "scenarios": scenarios,
        "outputs": {
            "runs": str(args.output_dir / "run_summary.csv"),
            "events": str(event_path),
            "windows": str(args.output_dir / "run_windows.csv"),
            "time_bins": str(args.output_dir / "run_time_bins.csv"),
            "baseline_equivalence": str(args.output_dir / "baseline_equivalence.csv"),
        },
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
