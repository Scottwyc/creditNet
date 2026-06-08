#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet import CreditNetworkParams, simulate_one_run


CST = ZoneInfo("Asia/Shanghai")
DEFAULT_OUTPUT = ROOT / "results" / "credit_soc_phase2_strict_soc_20260604_v1"


def parse_float_list(text: str) -> list[float]:
    return [float(value) for value in text.split(",") if value.strip()]


def parse_int_list(text: str) -> list[int]:
    return [int(value) for value in text.split(",") if value.strip()]


def parse_str_list(text: str) -> list[str]:
    return [value.strip() for value in text.split(",") if value.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-2 strict SOC evidence sweeps.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--families",
        default="income,fixed,finite_fixed,finite_income",
        help="Comma-separated subset of income,fixed,finite_fixed,finite_income.",
    )
    parser.add_argument(
        "--income-values",
        default="0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80",
    )
    parser.add_argument("--fixed-k-values", default="18,20,22,24,26")
    parser.add_argument("--finite-n-values", default="100,200,500,1000")
    parser.add_argument("--money-distributions", default="lognormal,pareto")
    parser.add_argument("--runs-fine", type=int, default=60)
    parser.add_argument("--runs-size", type=int, default=30)
    parser.add_argument("--max-periods-fine", type=int, default=300)
    parser.add_argument("--max-periods-size", type=int, default=250)
    parser.add_argument("--finite-k-per-node", type=float, default=0.14)
    parser.add_argument("--finite-income-c", type=float, default=0.18)
    parser.add_argument("--seed-base", type=int, default=2026120000)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--no-validate-accounting", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def scenario_id(family: str, params: CreditNetworkParams, control_value: float) -> str:
    if family == "income":
        control = f"c{control_value:.2f}".replace(".", "p")
    elif family == "fixed":
        control = f"K{int(control_value)}"
    elif family == "finite_fixed":
        control = f"N{params.n_nodes}_K{params.fixed_period_length_steps}"
    elif family == "finite_income":
        control = f"N{params.n_nodes}_c{control_value:.2f}".replace(".", "p")
    else:
        raise ValueError(f"unknown family: {family}")
    return f"{family}__{control}__{params.money_distribution}__biased__random"


def build_scenarios(args: argparse.Namespace) -> list[dict[str, Any]]:
    requested = set(parse_str_list(args.families))
    allowed = {"income", "fixed", "finite_fixed", "finite_income"}
    unknown = requested - allowed
    if unknown:
        raise ValueError(f"unknown families: {sorted(unknown)}")

    distributions = parse_str_list(args.money_distributions)
    scenarios: list[dict[str, Any]] = []

    def append(
        family: str,
        params: CreditNetworkParams,
        runs: int,
        control_name: str,
        control_value: float,
    ) -> None:
        scenarios.append(
            {
                "family": family,
                "scenario_id": scenario_id(family, params, control_value),
                "control_name": control_name,
                "control_value": float(control_value),
                "runs": int(runs),
                "params": asdict(params),
            }
        )

    if "income" in requested:
        for c_value in parse_float_list(args.income_values):
            for distribution in distributions:
                append(
                    "income",
                    CreditNetworkParams(
                        n_nodes=200,
                        money_distribution=distribution,
                        income_distribution_rule="biased",
                        growth_rule="random",
                        investment_income_propensity=c_value,
                        max_periods=args.max_periods_fine,
                        avalanche_protocol="continue_after_avalanche",
                        validate_accounting=not args.no_validate_accounting,
                        period_length_rule="income",
                    ),
                    args.runs_fine,
                    "c",
                    c_value,
                )

    if "fixed" in requested:
        for k_value in parse_int_list(args.fixed_k_values):
            for distribution in distributions:
                append(
                    "fixed",
                    CreditNetworkParams(
                        n_nodes=200,
                        money_distribution=distribution,
                        income_distribution_rule="biased",
                        growth_rule="random",
                        max_periods=args.max_periods_fine,
                        avalanche_protocol="continue_after_avalanche",
                        validate_accounting=not args.no_validate_accounting,
                        period_length_rule="fixed",
                        fixed_period_length_steps=k_value,
                    ),
                    args.runs_fine,
                    "fixed_k",
                    float(k_value),
                )

    if "finite_fixed" in requested:
        for n_nodes in parse_int_list(args.finite_n_values):
            k_value = max(1, int(round(args.finite_k_per_node * n_nodes)))
            params = CreditNetworkParams(
                n_nodes=n_nodes,
                money_distribution="lognormal",
                income_distribution_rule="biased",
                growth_rule="random",
                max_periods=args.max_periods_size,
                avalanche_protocol="continue_after_avalanche",
                validate_accounting=not args.no_validate_accounting,
                period_length_rule="fixed",
                fixed_period_length_steps=k_value,
            )
            append("finite_fixed", params, args.runs_size, "k_per_node", args.finite_k_per_node)

    if "finite_income" in requested:
        for n_nodes in parse_int_list(args.finite_n_values):
            params = CreditNetworkParams(
                n_nodes=n_nodes,
                money_distribution="lognormal",
                income_distribution_rule="biased",
                growth_rule="random",
                investment_income_propensity=args.finite_income_c,
                max_periods=args.max_periods_size,
                avalanche_protocol="continue_after_avalanche",
                validate_accounting=not args.no_validate_accounting,
                period_length_rule="income",
            )
            append("finite_income", params, args.runs_size, "c", args.finite_income_c)

    for scenario_index, scenario in enumerate(scenarios):
        scenario["scenario_index"] = scenario_index
        scenario["seed_start"] = args.seed_base + scenario_index * 100_000
        scenario["seed_end"] = scenario["seed_start"] + scenario["runs"] - 1
    return scenarios


def run_task(task: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    params = CreditNetworkParams(**task["params"])
    result = simulate_one_run(params, seed=task["seed"], keep_period_history=False)
    shared = {
        "family": task["family"],
        "scenario_id": task["scenario_id"],
        "scenario_index": task["scenario_index"],
        "run_index": task["run_index"],
        "control_name": task["control_name"],
        "control_value": task["control_value"],
        "seed": task["seed"],
        "n_nodes": params.n_nodes,
        "money_distribution": params.money_distribution,
        "income_distribution_rule": params.income_distribution_rule,
        "growth_rule": params.growth_rule,
        "period_length_rule": params.period_length_rule,
        "fixed_period_length_steps": params.fixed_period_length_steps,
        "investment_income_propensity": params.investment_income_propensity,
        "k_per_node": (
            params.fixed_period_length_steps / params.n_nodes
            if params.period_length_rule == "fixed"
            else np.nan
        ),
    }
    run_row = result.summary_row()
    run_row.update(shared)
    event_rows = []
    for avalanche_index, event in enumerate(result.avalanche_history, start=1):
        event_row = dict(event)
        event_row.update(shared)
        event_row["avalanche_index"] = avalanche_index
        event_rows.append(event_row)
    return run_row, event_rows


def summarize(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
        if total <= 0:
            return float("nan"), float("nan")
        rate = successes / total
        denominator = 1.0 + z * z / total
        center = (rate + z * z / (2.0 * total)) / denominator
        margin = z * math.sqrt(rate * (1.0 - rate) / total + z * z / (4.0 * total * total))
        margin /= denominator
        return center - margin, center + margin

    rows: list[dict[str, Any]] = []
    for scenario_id, run_sub in runs.groupby("scenario_id", sort=True):
        event_sub = events[events["scenario_id"] == scenario_id]
        sizes = event_sub["collapse_size"] if len(event_sub) else pd.Series(dtype=float)
        first = run_sub.iloc[0]
        run_critical_successes = int(run_sub["critical_event"].sum())
        run_ci_low, run_ci_high = wilson_interval(run_critical_successes, len(run_sub))
        rows.append(
            {
                "family": first["family"],
                "scenario_id": scenario_id,
                "control_name": first["control_name"],
                "control_value": first["control_value"],
                "n_nodes": int(first["n_nodes"]),
                "money_distribution": first["money_distribution"],
                "period_length_rule": first["period_length_rule"],
                "fixed_period_length_steps": int(first["fixed_period_length_steps"]),
                "investment_income_propensity": first["investment_income_propensity"],
                "k_per_node": first["k_per_node"],
                "runs": len(run_sub),
                "seed_min": int(run_sub["seed"].min()),
                "seed_max": int(run_sub["seed"].max()),
                "events": len(event_sub),
                "mean_events_per_run": float(run_sub["avalanche_count"].mean()),
                "run_critical_rate": float(run_sub["critical_event"].mean()),
                "run_critical_successes": run_critical_successes,
                "run_critical_ci95_low": run_ci_low,
                "run_critical_ci95_high": run_ci_high,
                "event_critical_rate": float(event_sub["critical_event"].mean())
                if len(event_sub)
                else 0.0,
                "mean_event_size": float(sizes.mean()) if len(sizes) else 0.0,
                "median_event_size": float(sizes.median()) if len(sizes) else 0.0,
                "p90_event_size": float(sizes.quantile(0.90)) if len(sizes) else 0.0,
                "p99_event_size": float(sizes.quantile(0.99)) if len(sizes) else 0.0,
                "max_event_size": int(sizes.max()) if len(sizes) else 0,
                "mean_final_net_worth_gini": float(run_sub["final_net_worth_gini"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["family", "scenario_id"])


def main() -> None:
    args = parse_args()
    if args.workers < 1 or args.workers > 3:
        raise ValueError("--workers must be between 1 and 3 under coordinator constraints")
    scenarios = build_scenarios(args)
    tasks = []
    for scenario in scenarios:
        for run_index in range(scenario["runs"]):
            tasks.append(
                {
                    **scenario,
                    "run_index": run_index,
                    "seed": scenario["seed_start"] + run_index,
                }
            )
    if args.dry_run:
        print(
            json.dumps(
                {
                    "scenarios": scenarios,
                    "total_runs": len(tasks),
                    "workers": args.workers,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(CST)
    print(
        f"started={started.isoformat()} scenarios={len(scenarios)} "
        f"runs={len(tasks)} workers={args.workers}",
        file=sys.stderr,
        flush=True,
    )
    run_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    completed = 0
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_task, task): task for task in tasks}
        for future in as_completed(futures):
            run_row, task_events = future.result()
            run_rows.append(run_row)
            event_rows.extend(task_events)
            completed += 1
            if args.progress_every > 0 and (
                completed % args.progress_every == 0 or completed == len(tasks)
            ):
                print(
                    f"completed_runs={completed}/{len(tasks)} events={len(event_rows)} "
                    f"time={datetime.now(CST).isoformat()}",
                    file=sys.stderr,
                    flush=True,
                )

    runs = pd.DataFrame(run_rows).sort_values(["scenario_index", "run_index"])
    events = pd.DataFrame(event_rows).sort_values(
        ["scenario_index", "run_index", "avalanche_index"]
    )
    runs.to_csv(args.output_dir / "run_summary.csv", index=False)
    events.to_csv(args.output_dir / "avalanche_events.csv", index=False)
    summary = summarize(runs, events)
    summary.to_csv(args.output_dir / "sweep_summary.csv", index=False)

    finished = datetime.now(CST)
    metadata = {
        "created_at": finished.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_seconds": (finished - started).total_seconds(),
        "python": sys.executable,
        "pid": os.getpid(),
        "command_args": {
            key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
        },
        "validate_accounting": not args.no_validate_accounting,
        "scenarios": scenarios,
        "total_runs": len(runs),
        "total_events": len(events),
        "artifacts": {
            "run_summary": str(args.output_dir / "run_summary.csv"),
            "avalanche_events": str(args.output_dir / "avalanche_events.csv"),
            "sweep_summary": str(args.output_dir / "sweep_summary.csv"),
        },
    }
    (args.output_dir / "sweep_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
