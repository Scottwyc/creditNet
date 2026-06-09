#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet.phase2_topology import TopologySpec
from creditnet.simulation import CreditNetworkParams
from creditnet.timestep import simulate_timestep_settle_check_run

CST = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class SpendingPreset:
    label: str
    a: float
    b: float


@dataclass(frozen=True)
class TopologyChoice:
    label: str
    topology: str
    target_mean_degree: int

    @property
    def is_complete(self) -> bool:
        return self.topology == "complete"


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    scenario_base_id: str
    scenario_index: int
    n_nodes: int
    mean_initial_money: float
    money_distribution: str
    income_distribution_rule: str
    growth_rule: str
    spending_label: str
    a: float
    b: float
    c: float
    topology_label: str
    topology: str
    target_mean_degree: int
    sw_rewire_probability: float
    max_periods: int
    max_time_steps: int
    max_period_length_steps: int
    collapse_threshold_fraction: float
    initial_income_per_capita: float
    avalanche_protocol: str
    validate_accounting: bool


@dataclass(frozen=True)
class RunSpec:
    scenario: ScenarioSpec
    run_index: int
    seed: int
    topology_seed: int


def parse_float_list(text: str) -> list[float]:
    return [float(value) for value in text.split(",") if value.strip()]


def parse_spending_presets(text: str) -> list[SpendingPreset]:
    presets: list[SpendingPreset] = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 3:
            raise ValueError("spending presets must use label:a:b")
        presets.append(SpendingPreset(parts[0], float(parts[1]), float(parts[2])))
    if not presets:
        raise ValueError("empty spending preset list")
    return presets


def parse_topologies(text: str) -> list[TopologyChoice]:
    choices: list[TopologyChoice] = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        if item == "complete":
            choices.append(TopologyChoice("complete", "complete", 0))
            continue
        parts = item.split(":")
        if len(parts) != 2:
            raise ValueError("topology choices must use complete or topology:degree")
        choices.append(TopologyChoice(f"{parts[0].lower()}_k{int(parts[1])}", parts[0].lower(), int(parts[1])))
    if not choices:
        raise ValueError("empty topology list")
    return choices


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the timestep-level SOC counterfactual over the comprehensive scenario grid."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--n-nodes", type=int, default=120)
    parser.add_argument("--runs-per-scenario", type=int, default=3)
    parser.add_argument("--max-periods", type=int, default=120)
    parser.add_argument("--max-time-steps", type=int, default=0)
    parser.add_argument(
        "--max-period-length-steps",
        type=int,
        default=0,
        help="Optional cap on K_t for timestep_settle_check; 0 means uncapped.",
    )
    parser.add_argument("--seed-base", type=int, default=2026060900)
    parser.add_argument("--topology-seed-base", type=int, default=2026069900)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--mean-initial-money", type=float, default=20.0)
    parser.add_argument("--initial-income-per-capita", type=float, default=5.0)
    parser.add_argument("--collapse-threshold-fraction", type=float, default=0.10)
    parser.add_argument(
        "--c-values",
        default="0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80",
    )
    parser.add_argument(
        "--money-distributions",
        nargs="+",
        default=["equal", "uniform", "normal", "lognormal", "pareto"],
    )
    parser.add_argument("--income-rules", nargs="+", default=["uniform", "biased"])
    parser.add_argument(
        "--growth-rules",
        nargs="+",
        default=["random", "preferential_debt"],
    )
    parser.add_argument(
        "--spending-presets",
        default=(
            "low:0.01:0.10,baseline:0.02:0.20,"
            "high_income:0.02:0.40,high_wealth:0.04:0.20,high_both:0.04:0.40"
        ),
    )
    parser.add_argument(
        "--topologies",
        default="complete,er:6,er:12,er:24,ba:6,ba:12,ba:24,sw:6,sw:12,sw:24",
    )
    parser.add_argument("--sw-rewire-probability", type=float, default=0.10)
    parser.add_argument(
        "--avalanche-protocol",
        choices=["stop_on_first_default", "continue_after_avalanche"],
        default="continue_after_avalanche",
    )
    parser.add_argument("--no-validate-accounting", action="store_true")
    parser.add_argument("--progress-every", type=int, default=250)
    parser.add_argument("--max-scenarios", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    return parser.parse_args()


def make_scenarios(args: argparse.Namespace) -> list[ScenarioSpec]:
    c_values = parse_float_list(args.c_values)
    spending = parse_spending_presets(args.spending_presets)
    topologies = parse_topologies(args.topologies)
    scenarios: list[ScenarioSpec] = []
    for scenario_index, (
        c_value,
        money,
        income_rule,
        growth_rule,
        spending_preset,
        topology_choice,
    ) in enumerate(
        product(
            c_values,
            args.money_distributions,
            args.income_rules,
            args.growth_rules,
            spending,
            topologies,
        )
    ):
        base_id = (
            f"money-{money}__income-{income_rule}__growth-{growth_rule}"
            f"__spend-{spending_preset.label}__topo-{topology_choice.label}"
        )
        scenario_id = f"c-{c_value:.2f}__{base_id}".replace(".", "p")
        scenarios.append(
            ScenarioSpec(
                scenario_id=scenario_id,
                scenario_base_id=base_id,
                scenario_index=scenario_index,
                n_nodes=args.n_nodes,
                mean_initial_money=args.mean_initial_money,
                money_distribution=money,
                income_distribution_rule=income_rule,
                growth_rule=growth_rule,
                spending_label=spending_preset.label,
                a=spending_preset.a,
                b=spending_preset.b,
                c=c_value,
                topology_label=topology_choice.label,
                topology=topology_choice.topology,
                target_mean_degree=topology_choice.target_mean_degree,
                sw_rewire_probability=args.sw_rewire_probability,
                max_periods=args.max_periods,
                max_time_steps=args.max_time_steps,
                max_period_length_steps=args.max_period_length_steps,
                collapse_threshold_fraction=args.collapse_threshold_fraction,
                initial_income_per_capita=args.initial_income_per_capita,
                avalanche_protocol=args.avalanche_protocol,
                validate_accounting=not args.no_validate_accounting,
            )
        )
    if args.max_scenarios > 0:
        scenarios = scenarios[: args.max_scenarios]
    if args.num_shards < 1:
        raise ValueError("--num-shards must be >= 1")
    if args.shard_index < 0 or args.shard_index >= args.num_shards:
        raise ValueError("--shard-index must be in [0, num_shards)")
    return [
        scenario
        for scenario in scenarios
        if scenario.scenario_index % args.num_shards == args.shard_index
    ]


def make_run_specs(args: argparse.Namespace) -> list[RunSpec]:
    run_specs: list[RunSpec] = []
    for scenario in make_scenarios(args):
        for run_index in range(args.runs_per_scenario):
            global_run_index = scenario.scenario_index * args.runs_per_scenario + run_index
            run_specs.append(
                RunSpec(
                    scenario=scenario,
                    run_index=run_index,
                    seed=args.seed_base + global_run_index,
                    topology_seed=args.topology_seed_base + global_run_index,
                )
            )
    return run_specs


def run_one(spec: RunSpec) -> tuple[dict[str, object], list[dict[str, object]]]:
    scenario = spec.scenario
    params = CreditNetworkParams(
        n_nodes=scenario.n_nodes,
        mean_initial_money=scenario.mean_initial_money,
        money_distribution=scenario.money_distribution,
        income_distribution_rule=scenario.income_distribution_rule,
        growth_rule=scenario.growth_rule,
        consumption_wealth_propensity=scenario.a,
        consumption_income_propensity=scenario.b,
        investment_income_propensity=scenario.c,
        initial_income_per_capita=scenario.initial_income_per_capita,
        collapse_threshold_fraction=scenario.collapse_threshold_fraction,
        max_periods=scenario.max_periods,
        max_time_steps=scenario.max_time_steps,
        validate_accounting=scenario.validate_accounting,
        period_length_rule="income",
        avalanche_protocol=scenario.avalanche_protocol,
        default_check_mode="timestep_settle_check",
    )
    topology_spec = None
    if scenario.topology != "complete":
        topology_spec = TopologySpec(
            topology=scenario.topology,
            target_mean_degree=scenario.target_mean_degree,
            sw_rewire_probability=scenario.sw_rewire_probability,
        )
    result = simulate_timestep_settle_check_run(
        params,
        seed=spec.seed,
        topology_spec=topology_spec,
        topology_seed=spec.topology_seed,
        max_period_length_steps_cap=scenario.max_period_length_steps,
        keep_period_history=False,
    )
    row = result.summary_row()
    row.update(
        {
            "scenario_id": scenario.scenario_id,
            "scenario_base_id": scenario.scenario_base_id,
            "scenario_index": scenario.scenario_index,
            "run_index": spec.run_index,
            "protocol": "timestep_settle_check",
            "spending_label": scenario.spending_label,
            "topology_label": scenario.topology_label,
            "topology_family": scenario.topology,
            "target_mean_degree_requested": scenario.target_mean_degree,
        }
    )
    events: list[dict[str, object]] = []
    for event_index, event in enumerate(result.avalanche_history, start=1):
        event_row = dict(event)
        event_row.update(
            {
                "seed": spec.seed,
                "run_index": spec.run_index,
                "avalanche_index": event_index,
                "scenario_id": scenario.scenario_id,
                "scenario_base_id": scenario.scenario_base_id,
                "scenario_index": scenario.scenario_index,
                "protocol": "timestep_settle_check",
                "n_nodes": scenario.n_nodes,
                "money_distribution": scenario.money_distribution,
                "income_distribution_rule": scenario.income_distribution_rule,
                "growth_rule": scenario.growth_rule,
                "spending_label": scenario.spending_label,
                "consumption_wealth_propensity": scenario.a,
                "consumption_income_propensity": scenario.b,
                "investment_income_propensity": scenario.c,
                "topology_label": scenario.topology_label,
                "topology_family": scenario.topology,
                "target_mean_degree_requested": scenario.target_mean_degree,
            }
        )
        events.append(event_row)
    return row, events


def aggregate_scenarios(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario_id, sub in runs.groupby("scenario_id", sort=False):
        event_sub = events[events["scenario_id"].eq(scenario_id)] if not events.empty else events
        first = sub.iloc[0]
        event_count = int(len(event_sub))
        size_sum = float(event_sub["collapse_size"].sum()) if event_count else 0.0
        prop_sum = float(event_sub["propagated_default_count"].sum()) if event_count else 0.0
        initial_sum = float(event_sub["initial_default_count"].sum()) if event_count else 0.0
        event_period_count = (
            int(event_sub[["run_index", "period"]].drop_duplicates().shape[0])
            if event_count and {"run_index", "period"}.issubset(event_sub.columns)
            else 0
        )
        rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_base_id": first["scenario_base_id"],
                "scenario_index": int(first["scenario_index"]),
                "protocol": "timestep_settle_check",
                "c": float(first["investment_income_propensity"]),
                "n_nodes": int(first["n_nodes"]),
                "money_distribution": first["money_distribution"],
                "income_distribution_rule": first["income_distribution_rule"],
                "growth_rule": first["growth_rule"],
                "spending_label": first["spending_label"],
                "a": float(first["consumption_wealth_propensity"]),
                "b": float(first["consumption_income_propensity"]),
                "topology_label": first["topology_label"],
                "topology_family": first["topology_family"],
                "target_mean_degree_requested": int(first["target_mean_degree_requested"]),
                "runs": int(len(sub)),
                "run_default_rate": float(sub["ended_by_default"].mean()),
                "run_large_event_rate": float(sub["critical_event"].mean()),
                "mean_periods_completed": float(sub["periods_completed"].mean()),
                "mean_time_steps_completed": float(sub["time_steps_completed"].mean()),
                "mean_settlements_completed": float(sub["settlements_completed"].mean()),
                "mean_checks_completed": float(sub["checks_completed"].mean()),
                "mean_capped_periods": float(sub["capped_periods"].mean()),
                "mean_max_uncapped_period_length_steps": float(
                    sub["max_uncapped_period_length_steps"].mean()
                ),
                "mean_max_period_length_steps": float(sub["max_period_length_steps"].mean()),
                "mean_avalanche_count": float(sub["avalanche_count"].mean()),
                "event_count": event_count,
                "events_per_run": event_count / max(float(len(sub)), 1.0),
                "events_per_period": event_count / max(float(sub["periods_completed"].sum()), 1.0),
                "event_timestep_rate": event_count / max(float(sub["time_steps_completed"].sum()), 1.0),
                "event_occupancy": event_count / max(float(sub["time_steps_completed"].sum()), 1.0),
                "event_period_occupancy": event_period_count
                / max(float(sub["periods_completed"].sum()), 1.0),
                "event_large_event_rate": (
                    float(event_sub["critical_event"].mean()) if event_count else 0.0
                ),
                "mean_event_size": (
                    float(event_sub["collapse_size"].mean()) if event_count else 0.0
                ),
                "mean_event_fraction": (
                    float(event_sub["collapse_fraction"].mean()) if event_count else 0.0
                ),
                "median_event_size": (
                    float(event_sub["collapse_size"].median()) if event_count else 0.0
                ),
                "p90_event_size": (
                    float(event_sub["collapse_size"].quantile(0.90)) if event_count else 0.0
                ),
                "p99_event_size": (
                    float(event_sub["collapse_size"].quantile(0.99)) if event_count else 0.0
                ),
                "max_event_size": int(event_sub["collapse_size"].max()) if event_count else 0,
                "mean_initial_default_count": (
                    float(event_sub["initial_default_count"].mean()) if event_count else 0.0
                ),
                "mean_propagated_default_count": (
                    float(event_sub["propagated_default_count"].mean()) if event_count else 0.0
                ),
                "propagated_share_total": prop_sum / size_sum if size_sum > 0 else 0.0,
                "initial_share_total": initial_sum / size_sum if size_sum > 0 else 0.0,
                "mean_first_cascade_credit": float(
                    sub.loc[sub["ended_by_default"].astype(bool), "credit_scale_before_cascade"].mean()
                )
                if bool(sub["ended_by_default"].any())
                else 0.0,
                "mean_final_active_credit": float(sub["final_active_credit"].mean()),
                "mean_initial_gini": float(sub["initial_money_gini"].mean()),
                "mean_final_net_worth_gini": float(sub["final_net_worth_gini"].mean()),
                "mean_repeat_default_share": float(sub["repeat_default_share"].mean()),
                "mean_unique_default_nodes": float(sub["unique_default_nodes"].mean()),
                "mean_topology_degree": float(sub.get("topology_mean_degree", pd.Series([0])).mean()),
                "mean_topology_clustering": float(
                    sub.get("topology_clustering", pd.Series([0])).mean()
                ),
                "mean_topology_degree_cv": float(
                    sub.get("topology_degree_cv", pd.Series([0])).mean()
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        [
            "money_distribution",
            "income_distribution_rule",
            "growth_rule",
            "spending_label",
            "topology_label",
            "c",
        ]
    )


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_specs = make_run_specs(args)
    total = len(run_specs)
    if total == 0:
        raise ValueError("empty run spec list")

    rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=max(int(args.workers), 1)) as executor:
        futures = [executor.submit(run_one, spec) for spec in run_specs]
        for index, future in enumerate(as_completed(futures), start=1):
            row, events = future.result()
            rows.append(row)
            event_rows.extend(events)
            if args.progress_every > 0 and (
                index % args.progress_every == 0 or index == total
            ):
                print(
                    f"shard={args.shard_index}/{args.num_shards} completed_runs={index}/{total}",
                    file=sys.stderr,
                    flush=True,
                )

    runs = pd.DataFrame(rows).sort_values(["scenario_index", "scenario_id", "run_index"])
    events = pd.DataFrame(event_rows)
    if not events.empty:
        events = events.sort_values(["scenario_index", "scenario_id", "run_index", "avalanche_index"])
    scenario_summary = aggregate_scenarios(runs, events)

    run_summary_csv = args.output_dir / "run_summary.csv"
    avalanche_csv = args.output_dir / "avalanche_events.csv"
    scenario_summary_csv = args.output_dir / "scenario_summary.csv"
    runs.to_csv(run_summary_csv, index=False)
    events.to_csv(avalanche_csv, index=False)
    scenario_summary.to_csv(scenario_summary_csv, index=False)

    metadata = {
        "created_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "protocol": "timestep_settle_check",
        "command_args": {
            key: (str(value) if isinstance(value, Path) else value)
            for key, value in vars(args).items()
        },
        "run_count": int(len(runs)),
        "event_count": int(len(events)),
        "scenario_count": int(scenario_summary["scenario_id"].nunique()),
        "scenario_base_count": int(scenario_summary["scenario_base_id"].nunique()),
        "run_summary_csv": str(run_summary_csv),
        "avalanche_csv": str(avalanche_csv),
        "scenario_summary_csv": str(scenario_summary_csv),
        "note": (
            "Timestep-level counterfactual: each unit credit attempt is followed "
            "by scaled flow settlement, default check, and full cascade clearing."
        ),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
