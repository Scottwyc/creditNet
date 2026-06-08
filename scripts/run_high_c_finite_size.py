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
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet import CreditNetworkParams, simulate_one_run


CST = ZoneInfo("Asia/Shanghai")
DEFAULT_OUTPUT = ROOT / "results" / "credit_soc_high_c_finite_size_20260605_v1"


def parse_float_list(text: str) -> list[float]:
    return [float(value) for value in text.split(",") if value.strip()]


def parse_int_list(text: str) -> list[int]:
    return [int(value) for value in text.split(",") if value.strip()]


def parse_str_list(text: str) -> list[str]:
    return [value.strip() for value in text.split(",") if value.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run high-c finite-size SOC checks.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--c-values", default="0.30,0.50,0.80")
    parser.add_argument("--n-values", default="100,200,500")
    parser.add_argument("--money-distributions", default="lognormal,pareto")
    parser.add_argument("--runs-per-scenario", type=int, default=24)
    parser.add_argument("--max-periods", type=int, default=240)
    parser.add_argument("--seed-base", type=int, default=2026650000)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--no-validate-accounting", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def scenario_id(c_value: float, n_nodes: int, distribution: str) -> str:
    c_label = f"c{c_value:.2f}".replace(".", "p")
    return f"high_c_finite__N{n_nodes}__{c_label}__{distribution}__biased__random"


def build_scenarios(args: argparse.Namespace) -> list[dict[str, Any]]:
    c_values = parse_float_list(args.c_values)
    n_values = parse_int_list(args.n_values)
    distributions = parse_str_list(args.money_distributions)
    scenarios: list[dict[str, Any]] = []
    for c_index, c_value in enumerate(c_values):
        for n_index, n_nodes in enumerate(n_values):
            for distribution_index, distribution in enumerate(distributions):
                scenario_index = (
                    c_index * len(n_values) * len(distributions)
                    + n_index * len(distributions)
                    + distribution_index
                )
                params = CreditNetworkParams(
                    n_nodes=n_nodes,
                    mean_initial_money=20.0,
                    money_distribution=distribution,
                    income_distribution_rule="biased",
                    growth_rule="random",
                    consumption_wealth_propensity=0.02,
                    consumption_income_propensity=0.20,
                    investment_income_propensity=c_value,
                    initial_income_per_capita=5.0,
                    income_bias_floor=1.0,
                    collapse_threshold_fraction=0.10,
                    max_periods=args.max_periods,
                    default_threshold=0.0,
                    wipe_defaulted_assets=True,
                    validate_accounting=not args.no_validate_accounting,
                    period_length_rule="income",
                    fixed_period_length_steps=100,
                    avalanche_protocol="continue_after_avalanche",
                    default_check_mode="period_end",
                )
                scenarios.append(
                    {
                        "family": "high_c_finite_income",
                        "scenario_id": scenario_id(c_value, n_nodes, distribution),
                        "scenario_index": scenario_index,
                        "control_name": "c",
                        "control_value": float(c_value),
                        "n_nodes": int(n_nodes),
                        "money_distribution": distribution,
                        "runs": int(args.runs_per_scenario),
                        "params": asdict(params),
                        "seed_start": args.seed_base + scenario_index * 100_000,
                        "seed_end": args.seed_base
                        + scenario_index * 100_000
                        + args.runs_per_scenario
                        - 1,
                    }
                )
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
        "investment_income_propensity": params.investment_income_propensity,
    }
    run_row = result.summary_row()
    run_row.update(shared)
    events = []
    for avalanche_index, event in enumerate(result.avalanche_history, start=1):
        events.append(dict(event) | shared | {"avalanche_index": avalanche_index})
    return run_row, events


def finite_summary(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, event_sub in events.groupby(
        ["control_value", "n_nodes", "money_distribution"], sort=True
    ):
        c_value, n_nodes, distribution = keys
        run_sub = runs[
            runs["control_value"].eq(c_value)
            & runs["n_nodes"].eq(n_nodes)
            & runs["money_distribution"].eq(distribution)
        ]
        sizes = event_sub["collapse_size"].to_numpy(dtype=float)
        initial = event_sub["initial_default_count"].to_numpy(dtype=float)
        propagated = sizes - initial
        total_size = float(sizes.sum())
        rows.append(
            {
                "c": float(c_value),
                "n_nodes": int(n_nodes),
                "money_distribution": distribution,
                "runs": int(len(run_sub)),
                "events": int(len(event_sub)),
                "events_per_run": float(len(event_sub) / max(len(run_sub), 1)),
                "event_period_fraction": float(len(event_sub) / run_sub["periods_completed"].sum()),
                "run_large_event_rate": float(run_sub["critical_event"].mean()),
                "event_large_event_rate": float(event_sub["critical_event"].mean()),
                "mean_size": float(np.mean(sizes)),
                "median_size": float(np.median(sizes)),
                "p90_size": float(np.quantile(sizes, 0.90)),
                "p99_size": float(np.quantile(sizes, 0.99)),
                "max_size": int(np.max(sizes)),
                "mean_size_fraction": float(np.mean(sizes) / n_nodes),
                "p99_fraction": float(np.quantile(sizes, 0.99) / n_nodes),
                "max_fraction": float(np.max(sizes) / n_nodes),
                "second_moment": float(np.mean(sizes**2)),
                "moment_ratio_m2_m1": float(np.mean(sizes**2) / np.mean(sizes)),
                "mean_initial_defaults": float(np.mean(initial)),
                "mean_propagated_defaults": float(np.mean(propagated)),
                "propagated_share_of_total_size": float(np.sum(propagated) / total_size)
                if total_size > 0
                else 0.0,
                "multi_initial_event_rate": float(np.mean(initial > 1)),
                "mean_time_steps_per_period": float(
                    (run_sub["time_steps_completed"] / run_sub["periods_completed"]).mean()
                ),
                "mean_final_active_credit": float(run_sub["final_active_credit"].mean()),
                "mean_final_net_worth_gini": float(run_sub["final_net_worth_gini"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["money_distribution", "c", "n_nodes"])


def scaling_slopes(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    metrics = [
        "mean_size",
        "p99_size",
        "max_size",
        "moment_ratio_m2_m1",
        "mean_size_fraction",
        "p99_fraction",
        "propagated_share_of_total_size",
        "event_large_event_rate",
    ]
    for keys, sub in summary.groupby(["money_distribution", "c"], sort=True):
        distribution, c_value = keys
        sub = sub.sort_values("n_nodes")
        for metric in metrics:
            y = sub[metric].to_numpy(dtype=float)
            x = sub["n_nodes"].to_numpy(dtype=float)
            valid = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
            if valid.sum() >= 2:
                regression = stats.linregress(np.log(x[valid]), np.log(y[valid]))
                slope = float(regression.slope)
                r_squared = float(regression.rvalue**2)
                p_value = float(regression.pvalue) if valid.sum() >= 3 else float("nan")
            else:
                slope = float("nan")
                r_squared = float("nan")
                p_value = float("nan")
            rows.append(
                {
                    "money_distribution": distribution,
                    "c": float(c_value),
                    "metric": metric,
                    "log_log_slope": slope,
                    "r_squared": r_squared,
                    "p_value": p_value,
                    "n_sizes": int(valid.sum()),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    if args.workers < 1 or args.workers > 3:
        raise ValueError("--workers must be in [1, 3]")
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
                {"scenarios": scenarios, "total_runs": len(tasks), "workers": args.workers},
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
            run_row, events = future.result()
            run_rows.append(run_row)
            event_rows.extend(events)
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
    summary = finite_summary(runs, events)
    summary.to_csv(args.output_dir / "finite_size_summary.csv", index=False)
    slopes = scaling_slopes(summary)
    slopes.to_csv(args.output_dir / "finite_size_scaling_slopes.csv", index=False)

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
        "total_runs": int(len(runs)),
        "total_events": int(len(events)),
        "artifacts": {
            "run_summary": str(args.output_dir / "run_summary.csv"),
            "avalanche_events": str(args.output_dir / "avalanche_events.csv"),
            "finite_size_summary": str(args.output_dir / "finite_size_summary.csv"),
            "finite_size_scaling_slopes": str(
                args.output_dir / "finite_size_scaling_slopes.csv"
            ),
        },
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
