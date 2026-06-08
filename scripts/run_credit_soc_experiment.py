#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet import CreditNetworkParams, simulate_one_run


def parse_float_list(text: str) -> list[float]:
    return [float(value) for value in text.split(",") if value.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run credit-network SOC simulations.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--n-nodes", type=int, default=200)
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--max-periods", type=int, default=500)
    parser.add_argument("--max-time-steps", type=int, default=0)
    parser.add_argument("--seed-base", type=int, default=2026060200)
    parser.add_argument(
        "--money-distributions",
        nargs="+",
        default=["equal", "uniform", "normal", "lognormal", "pareto"],
    )
    parser.add_argument("--income-rules", nargs="+", default=["uniform", "biased"])
    parser.add_argument("--growth-rules", nargs="+", default=["random"])
    parser.add_argument("--mean-initial-money", type=float, default=20.0)
    parser.add_argument("--a", type=float, default=0.02, help="wealth consumption propensity")
    parser.add_argument("--b", type=float, default=0.20, help="income consumption propensity")
    parser.add_argument(
        "--c",
        type=float,
        default=0.20,
        help="income-to-planned-credit-attempt conversion coefficient",
    )
    parser.add_argument(
        "--c-values",
        default=None,
        help=(
            "Optional comma-separated sweep of c values. "
            "When provided, overrides --c, e.g. 0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80."
        ),
    )
    parser.add_argument("--initial-income-per-capita", type=float, default=5.0)
    parser.add_argument("--collapse-threshold-fraction", type=float, default=0.10)
    parser.add_argument(
        "--period-length-rule",
        choices=["income", "fixed"],
        default="income",
    )
    parser.add_argument("--fixed-period-length-steps", type=int, default=100)
    parser.add_argument(
        "--avalanche-protocol",
        choices=["stop_on_first_default", "continue_after_avalanche"],
        default="stop_on_first_default",
    )
    parser.add_argument("--keep-first-history", action="store_true")
    parser.add_argument("--no-validate-accounting", action="store_true")
    parser.add_argument("--progress-every", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    avalanche_rows = []
    histories = {}
    run_counter = 0
    c_values = parse_float_list(args.c_values) if args.c_values else [args.c]
    if not c_values:
        raise ValueError("--c-values did not contain any numeric values")
    multi_c = len(c_values) > 1

    for c_value in c_values:
        c_label = f"c{c_value:.2f}".replace(".", "p")
        for money_distribution in args.money_distributions:
            for income_rule in args.income_rules:
                for growth_rule in args.growth_rules:
                    scenario_id = f"{money_distribution}__{income_rule}__{growth_rule}"
                    if multi_c:
                        scenario_id = f"{c_label}__{scenario_id}"
                    for run_idx in range(args.runs):
                        seed = args.seed_base + run_counter
                        params = CreditNetworkParams(
                            n_nodes=args.n_nodes,
                            mean_initial_money=args.mean_initial_money,
                            money_distribution=money_distribution,
                            income_distribution_rule=income_rule,
                            growth_rule=growth_rule,
                            consumption_wealth_propensity=args.a,
                            consumption_income_propensity=args.b,
                            investment_income_propensity=c_value,
                            initial_income_per_capita=args.initial_income_per_capita,
                            collapse_threshold_fraction=args.collapse_threshold_fraction,
                            max_periods=args.max_periods,
                            max_time_steps=args.max_time_steps,
                            validate_accounting=not args.no_validate_accounting,
                            period_length_rule=args.period_length_rule,
                            fixed_period_length_steps=args.fixed_period_length_steps,
                            avalanche_protocol=args.avalanche_protocol,
                        )
                        keep_history = args.keep_first_history and run_idx == 0
                        result = simulate_one_run(
                            params, seed=seed, keep_period_history=keep_history
                        )
                        row = result.summary_row()
                        row["run_index"] = run_idx
                        row["scenario_id"] = scenario_id
                        rows.append(row)
                        for avalanche_index, event in enumerate(
                            result.avalanche_history, start=1
                        ):
                            event_row = dict(event)
                            event_row["seed"] = seed
                            event_row["run_index"] = run_idx
                            event_row["avalanche_index"] = avalanche_index
                            event_row["scenario_id"] = row["scenario_id"]
                            event_row["money_distribution"] = money_distribution
                            event_row["income_distribution_rule"] = income_rule
                            event_row["growth_rule"] = growth_rule
                            event_row["investment_income_propensity"] = c_value
                            avalanche_rows.append(event_row)
                        if keep_history:
                            histories[row["scenario_id"]] = result.period_history
                        run_counter += 1
                        if args.progress_every > 0 and run_counter % args.progress_every == 0:
                            print(f"completed_runs={run_counter}", file=sys.stderr, flush=True)

    df = pd.DataFrame(rows)
    summary_csv = args.output_dir / "run_summary.csv"
    df.to_csv(summary_csv, index=False)
    avalanche_csv = args.output_dir / "avalanche_events.csv"
    pd.DataFrame(avalanche_rows).to_csv(avalanche_csv, index=False)

    grouped = (
        df.groupby(
            [
                "investment_income_propensity",
                "money_distribution",
                "income_distribution_rule",
                "growth_rule",
            ]
        )
        .agg(
            runs=("seed", "count"),
            default_rate=("ended_by_default", "mean"),
            critical_event_rate=("critical_event", "mean"),
            mean_periods=("periods_completed", "mean"),
            mean_time_steps=("time_steps_completed", "mean"),
            mean_avalanche_count=("avalanche_count", "mean"),
            median_credit_scale=("credit_scale_before_cascade", "median"),
            mean_credit_scale=("credit_scale_before_cascade", "mean"),
            median_collapse_size=("collapse_size", "median"),
            mean_collapse_size=("collapse_size", "mean"),
            mean_total_collapse_size=("total_collapse_size", "mean"),
            p90_collapse_size=("collapse_size", lambda x: x.quantile(0.90)),
            max_collapse_size=("collapse_size", "max"),
            mean_initial_gini=("initial_money_gini", "mean"),
            mean_final_net_worth_gini=("final_net_worth_gini", "mean"),
        )
        .reset_index()
    )
    grouped.to_csv(args.output_dir / "scenario_summary.csv", index=False)

    metadata = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "command_args": vars(args) | {"output_dir": str(args.output_dir)},
        "summary_csv": str(summary_csv),
        "avalanche_csv": str(avalanche_csv),
        "scenario_summary_csv": str(args.output_dir / "scenario_summary.csv"),
        "history_json": str(args.output_dir / "first_run_histories.json"),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "first_run_histories.json").write_text(
        json.dumps(histories, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
