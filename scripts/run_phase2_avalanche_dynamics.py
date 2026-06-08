#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet.phase2_dynamics import (
    simulate_one_dynamics_run,
    validate_dynamics_against_baseline,
)
from creditnet.simulation import CreditNetworkParams


@dataclass(frozen=True)
class Scenario:
    family: str
    n_nodes: int
    period_length_rule: str
    fixed_k: int = 20
    c: float = 0.18

    def drive_value(self) -> float:
        return float(self.fixed_k if self.period_length_rule == "fixed" else self.c)

    def scenario_id(self) -> str:
        if self.period_length_rule == "fixed":
            return f"{self.family}__N-{self.n_nodes}__fixed-K-{self.fixed_k}"
        return f"{self.family}__N-{self.n_nodes}__income-c-{self.c:.2f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-2 avalanche dynamics experiments.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runs-per-scenario", type=int, default=20)
    parser.add_argument("--max-periods", type=int, default=240)
    parser.add_argument("--long-runs-per-scenario", type=int, default=5)
    parser.add_argument("--long-max-periods", type=int, default=1000)
    parser.add_argument("--seed-base", type=int, default=2026061400)
    parser.add_argument("--validation-seeds", type=int, default=3)
    parser.add_argument("--progress-every", type=int, default=10)
    return parser.parse_args()


def build_scenarios() -> list[Scenario]:
    scenarios = [
        Scenario("fixed_k_transition", 200, "fixed", fixed_k=k)
        for k in [18, 20, 22, 24, 26, 28]
    ]
    scenarios.extend(
        Scenario("income_c_transition", 200, "income", c=c)
        for c in [0.14, 0.16, 0.18, 0.20]
    )
    scenarios.extend(
        Scenario("size_scaling_income_c018", n, "income", c=0.18)
        for n in [100, 200, 500]
    )
    scenarios.extend(
        [
            Scenario("long_run_attractor", 200, "fixed", fixed_k=20),
            Scenario("long_run_attractor", 200, "fixed", fixed_k=30),
            Scenario("long_run_attractor", 200, "income", c=0.18),
            Scenario("long_run_attractor", 200, "income", c=0.20),
        ]
    )
    return scenarios


def base_params(scenario: Scenario, max_periods: int) -> CreditNetworkParams:
    return CreditNetworkParams(
        n_nodes=scenario.n_nodes,
        mean_initial_money=20.0,
        money_distribution="lognormal",
        income_distribution_rule="biased",
        growth_rule="random",
        consumption_wealth_propensity=0.02,
        consumption_income_propensity=0.20,
        investment_income_propensity=scenario.c,
        initial_income_per_capita=5.0,
        collapse_threshold_fraction=0.10,
        max_periods=max_periods,
        validate_accounting=True,
        period_length_rule=scenario.period_length_rule,
        fixed_period_length_steps=scenario.fixed_k,
        avalanche_protocol="continue_after_avalanche",
        default_check_mode="period_end",
    )


def lag1_size_correlation(events: list[dict[str, object]]) -> float:
    if len(events) < 3:
        return float("nan")
    sizes = np.asarray([event["collapse_size"] for event in events], dtype=float)
    if np.std(sizes[:-1]) == 0 or np.std(sizes[1:]) == 0:
        return float("nan")
    return float(np.corrcoef(sizes[:-1], sizes[1:])[0, 1])


def pooled_lag1_correlation(events: pd.DataFrame) -> float:
    left: list[float] = []
    right: list[float] = []
    for _, group in events.groupby(["scenario_id", "run_index"], sort=False):
        sizes = group.sort_values("avalanche_index")["collapse_size"].to_numpy(dtype=float)
        if len(sizes) > 1:
            left.extend(sizes[:-1])
            right.extend(sizes[1:])
    if len(left) < 3 or np.std(left) == 0 or np.std(right) == 0:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def aggregate_scenarios(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario_id, sub in runs.groupby("scenario_id", sort=False):
        event_sub = events[events["scenario_id"] == scenario_id].copy()
        waits = event_sub["period_waiting_time"].dropna() if len(event_sub) else pd.Series(dtype=float)
        rows.append(
            {
                "scenario_id": scenario_id,
                "family": sub["family"].iloc[0],
                "n_nodes": int(sub["n_nodes"].iloc[0]),
                "period_length_rule": sub["period_length_rule"].iloc[0],
                "drive_value": float(sub["drive_value"].iloc[0]),
                "runs": len(sub),
                "seeds": ";".join(map(str, sub["seed"].tolist())),
                "periods_observed": int(sub["periods_completed"].sum()),
                "event_count": len(event_sub),
                "events_per_100_periods": (
                    100.0 * len(event_sub) / sub["periods_completed"].sum()
                    if sub["periods_completed"].sum() > 0
                    else 0.0
                ),
                "avalanche_period_occupancy": (
                    len(event_sub) / sub["periods_completed"].sum()
                    if sub["periods_completed"].sum() > 0
                    else 0.0
                ),
                "one_period_wait_fraction": (
                    float((waits == 1).mean()) if len(waits) else float("nan")
                ),
                "mean_period_wait": float(waits.mean()) if len(waits) else float("nan"),
                "pooled_size_lag1_correlation": pooled_lag1_correlation(event_sub),
                "critical_run_rate": float(sub["critical_event"].mean()),
                "critical_event_rate": (
                    float(event_sub["critical_event"].mean()) if len(event_sub) else 0.0
                ),
                "mean_event_size": (
                    float(event_sub["collapse_size"].mean()) if len(event_sub) else 0.0
                ),
                "p95_event_size": (
                    float(event_sub["collapse_size"].quantile(0.95)) if len(event_sub) else 0.0
                ),
                "max_event_size": (
                    int(event_sub["collapse_size"].max()) if len(event_sub) else 0
                ),
                "mean_duration_generations": (
                    float(event_sub["duration_generations"].mean()) if len(event_sub) else 0.0
                ),
                "p95_duration_generations": (
                    float(event_sub["duration_generations"].quantile(0.95))
                    if len(event_sub)
                    else 0.0
                ),
                "max_duration_generations": (
                    int(event_sub["duration_generations"].max()) if len(event_sub) else 0
                ),
                "mean_weighted_branching_ratio": (
                    float(event_sub["weighted_branching_ratio"].mean())
                    if len(event_sub)
                    else 0.0
                ),
                "p95_weighted_branching_ratio": (
                    float(event_sub["weighted_branching_ratio"].quantile(0.95))
                    if len(event_sub)
                    else 0.0
                ),
                "mean_initial_default_count": (
                    float(event_sub["initial_default_count"].mean()) if len(event_sub) else 0.0
                ),
                "mean_propagated_default_count": (
                    float(event_sub["propagated_default_count"].mean()) if len(event_sub) else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    scenarios = build_scenarios()

    validation_rows: list[dict[str, object]] = []
    validation_specs = [
        Scenario("validation_fixed", 100, "fixed", fixed_k=28),
        Scenario("validation_income", 100, "income", c=0.20),
    ]
    for spec_index, spec in enumerate(validation_specs):
        params = base_params(spec, min(args.max_periods, 200))
        seeds = [
            args.seed_base + 9_000_000 + spec_index * 10_000 + index
            for index in range(args.validation_seeds)
        ]
        for row in validate_dynamics_against_baseline(params, seeds):
            validation_rows.append(
                row
                | {
                    "validation_scenario": spec.scenario_id(),
                    "n_nodes": spec.n_nodes,
                    "period_length_rule": spec.period_length_rule,
                    "drive_value": spec.drive_value(),
                }
            )
    pd.DataFrame(validation_rows).to_csv(args.output_dir / "baseline_equivalence.csv", index=False)

    run_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    wave_rows: list[dict[str, object]] = []
    first_run_histories: dict[str, object] = {}
    total_runs = sum(
        args.long_runs_per_scenario
        if scenario.family == "long_run_attractor"
        else args.runs_per_scenario
        for scenario in scenarios
    )
    completed = 0

    for scenario_index, scenario in enumerate(scenarios):
        scenario_id = scenario.scenario_id()
        scenario_max_periods = (
            args.long_max_periods if scenario.family == "long_run_attractor" else args.max_periods
        )
        scenario_runs = (
            args.long_runs_per_scenario
            if scenario.family == "long_run_attractor"
            else args.runs_per_scenario
        )
        params = base_params(scenario, scenario_max_periods)
        for run_index in range(scenario_runs):
            seed = args.seed_base + scenario_index * 10_000 + run_index
            result = simulate_one_dynamics_run(
                params,
                seed,
                keep_period_history=(run_index == 0),
            )
            waits = [
                event["period_waiting_time"]
                for event in result.avalanche_history
                if event["period_waiting_time"] is not None
            ]
            run_row = result.summary_row() | {
                "scenario_id": scenario_id,
                "family": scenario.family,
                "run_index": run_index,
                "drive_value": scenario.drive_value(),
                "events_per_100_periods": (
                    100.0 * len(result.avalanche_history) / result.periods_completed
                    if result.periods_completed > 0
                    else 0.0
                ),
                "avalanche_period_occupancy": (
                    len(result.avalanche_history) / result.periods_completed
                    if result.periods_completed > 0
                    else 0.0
                ),
                "one_period_wait_fraction": (
                    float(np.mean(np.asarray(waits) == 1)) if waits else float("nan")
                ),
                "size_lag1_correlation": lag1_size_correlation(result.avalanche_history),
                "mean_duration_generations": (
                    float(
                        np.mean(
                            [
                                event["duration_generations"]
                                for event in result.avalanche_history
                            ]
                        )
                    )
                    if result.avalanche_history
                    else 0.0
                ),
                "mean_weighted_branching_ratio": (
                    float(
                        np.mean(
                            [
                                event["weighted_branching_ratio"]
                                for event in result.avalanche_history
                            ]
                        )
                    )
                    if result.avalanche_history
                    else 0.0
                ),
            }
            run_rows.append(run_row)

            for avalanche_index, event in enumerate(result.avalanche_history, start=1):
                wave_sizes = list(event["wave_sizes"])
                branching_ratios = list(event["wave_branching_ratios"])
                event_row = {
                    key: value
                    for key, value in event.items()
                    if key not in {"wave_sizes", "wave_branching_ratios"}
                }
                event_row |= {
                    "scenario_id": scenario_id,
                    "family": scenario.family,
                    "run_index": run_index,
                    "seed": seed,
                    "avalanche_index": avalanche_index,
                    "n_nodes": scenario.n_nodes,
                    "period_length_rule": scenario.period_length_rule,
                    "drive_value": scenario.drive_value(),
                    "run_periods_completed": result.periods_completed,
                    "normalized_period_position": (
                        event["period"] / result.periods_completed
                        if result.periods_completed > 0
                        else 0.0
                    ),
                    "time_quartile": min(
                        4,
                        1
                        + int(
                            4 * (int(event["period"]) - 1) / max(result.periods_completed, 1)
                        ),
                    ),
                    "post_burn_in": bool(
                        int(event["period"]) > int(np.ceil(0.25 * result.periods_completed))
                    ),
                    "wave_sizes_json": json.dumps(wave_sizes),
                    "wave_branching_ratios_json": json.dumps(branching_ratios),
                }
                event_rows.append(event_row)
                for generation, wave_size in enumerate(wave_sizes):
                    wave_rows.append(
                        {
                            "scenario_id": scenario_id,
                            "family": scenario.family,
                            "run_index": run_index,
                            "seed": seed,
                            "avalanche_index": avalanche_index,
                            "period": event["period"],
                            "n_nodes": scenario.n_nodes,
                            "period_length_rule": scenario.period_length_rule,
                            "drive_value": scenario.drive_value(),
                            "run_periods_completed": result.periods_completed,
                            "time_quartile": min(
                                4,
                                1
                                + int(
                                    4
                                    * (int(event["period"]) - 1)
                                    / max(result.periods_completed, 1)
                                ),
                            ),
                            "generation": generation,
                            "wave_role": "initial" if generation == 0 else "propagated",
                            "new_default_count": wave_size,
                            "previous_wave_size": (
                                wave_sizes[generation - 1] if generation > 0 else None
                            ),
                            "branching_ratio_from_previous_wave": (
                                branching_ratios[generation - 1]
                                if generation > 0
                                else None
                            ),
                        }
                    )
            if run_index == 0:
                first_run_histories[scenario_id] = result.period_history

            completed += 1
            if args.progress_every > 0 and completed % args.progress_every == 0:
                print(f"completed_runs={completed}/{total_runs}", flush=True)

    runs = pd.DataFrame(run_rows)
    events = pd.DataFrame(event_rows)
    waves = pd.DataFrame(wave_rows)
    scenario_summary = aggregate_scenarios(runs, events)
    runs.to_csv(args.output_dir / "run_summary.csv", index=False)
    events.to_csv(args.output_dir / "avalanche_events.csv", index=False)
    waves.to_csv(args.output_dir / "avalanche_waves.csv", index=False)
    scenario_summary.to_csv(args.output_dir / "scenario_summary.csv", index=False)
    (args.output_dir / "first_run_period_histories.json").write_text(
        json.dumps(first_run_histories, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    created_at = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z")
    metadata = {
        "created_at": created_at,
        "command_args": vars(args) | {"output_dir": str(args.output_dir)},
        "protocol": {
            "money_distribution": "lognormal",
            "income_distribution_rule": "biased",
            "growth_rule": "random",
            "avalanche_protocol": "continue_after_avalanche",
            "default_check_mode": "period_end",
            "validate_accounting": True,
            "common_parameters": {
                "mean_initial_money": 20.0,
                "consumption_wealth_propensity": 0.02,
                "consumption_income_propensity": 0.20,
                "initial_income_per_capita": 5.0,
                "income_bias_floor": 1.0,
                "collapse_threshold_fraction": 0.10,
                "default_threshold": 0.0,
                "wipe_defaulted_assets": True,
                "max_time_steps": 0,
            },
            "family_execution": {
                "transition_and_size_scaling": {
                    "runs_per_scenario": args.runs_per_scenario,
                    "max_periods": args.max_periods,
                },
                "long_run_attractor": {
                    "runs_per_scenario": args.long_runs_per_scenario,
                    "max_periods": args.long_max_periods,
                },
            },
            "generation_definition": (
                "earliest FIFO queue-discovery generation under exact baseline sequential clearing; "
                "generation 0 is the initial negative-net-worth set"
            ),
            "duration_definition": (
                "number of discovery generations including generation 0; baseline cascade_steps "
                "is not used as duration because it counts processed defaulted nodes"
            ),
        },
        "scenario_count": len(scenarios),
        "run_count": len(runs),
        "event_count": len(events),
        "wave_count": len(waves),
        "validation_row_count": len(validation_rows),
        "validation_all_matched": bool(
            validation_rows and all(row["matched"] for row in validation_rows)
        ),
        "scenarios": [asdict(scenario) | {"scenario_id": scenario.scenario_id()} for scenario in scenarios],
        "seeds": runs[["scenario_id", "run_index", "seed"]].to_dict(orient="records"),
        "outputs": {
            name: str(args.output_dir / name)
            for name in [
                "baseline_equivalence.csv",
                "run_summary.csv",
                "avalanche_events.csv",
                "avalanche_waves.csv",
                "scenario_summary.csv",
                "first_run_period_histories.json",
            ]
        },
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "created_at": created_at,
                "run_count": len(runs),
                "event_count": len(events),
                "wave_count": len(waves),
                "validation_all_matched": metadata["validation_all_matched"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
