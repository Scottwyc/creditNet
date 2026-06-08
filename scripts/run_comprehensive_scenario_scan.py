#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet.phase2_topology import TopologySpec, simulate_one_topology_run
from creditnet.simulation import CreditNetworkParams, simulate_one_run

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
class RunSpec:
    scenario_id: str
    scenario_base_id: str
    run_index: int
    seed: int
    topology_seed: int
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
    collapse_threshold_fraction: float
    initial_income_per_capita: float
    avalanche_protocol: str
    validate_accounting: bool


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
            raise ValueError(
                "spending presets must use label:a:b, e.g. low:0.01:0.10"
            )
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
        topology = parts[0].lower()
        degree = int(parts[1])
        choices.append(TopologyChoice(f"{topology}_k{degree}", topology, degree))
    if not choices:
        raise ValueError("empty topology list")
    return choices


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a comprehensive factorial scan for credit-network cascades and SOC screens."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--n-nodes", type=int, default=120)
    parser.add_argument("--runs-per-scenario", type=int, default=3)
    parser.add_argument("--max-periods", type=int, default=120)
    parser.add_argument("--max-time-steps", type=int, default=0)
    parser.add_argument("--seed-base", type=int, default=2026060800)
    parser.add_argument("--topology-seed-base", type=int, default=2026068800)
    parser.add_argument("--workers", type=int, default=8)
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
    parser.add_argument("--progress-every", type=int, default=500)
    parser.add_argument(
        "--max-scenarios",
        type=int,
        default=0,
        help="Optional smoke-test cap on scenario count before multiplying by runs.",
    )
    return parser.parse_args()


def make_specs(args: argparse.Namespace) -> list[RunSpec]:
    c_values = parse_float_list(args.c_values)
    spending = parse_spending_presets(args.spending_presets)
    topologies = parse_topologies(args.topologies)
    scenario_specs = []
    for (
        c_value,
        money,
        income_rule,
        growth_rule,
        spending_preset,
        topology_choice,
    ) in product(
        c_values,
        args.money_distributions,
        args.income_rules,
        args.growth_rules,
        spending,
        topologies,
    ):
        base_id = (
            f"money-{money}__income-{income_rule}__growth-{growth_rule}"
            f"__spend-{spending_preset.label}__topo-{topology_choice.label}"
        )
        scenario_id = f"c-{c_value:.2f}__{base_id}".replace(".", "p")
        scenario_specs.append(
            (
                scenario_id,
                base_id,
                c_value,
                money,
                income_rule,
                growth_rule,
                spending_preset,
                topology_choice,
            )
        )
    if args.max_scenarios > 0:
        scenario_specs = scenario_specs[: args.max_scenarios]

    run_specs: list[RunSpec] = []
    counter = 0
    for (
        scenario_id,
        base_id,
        c_value,
        money,
        income_rule,
        growth_rule,
        spending_preset,
        topology_choice,
    ) in scenario_specs:
        for run_index in range(args.runs_per_scenario):
            run_specs.append(
                RunSpec(
                    scenario_id=scenario_id,
                    scenario_base_id=base_id,
                    run_index=run_index,
                    seed=args.seed_base + counter,
                    topology_seed=args.topology_seed_base + counter,
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
                    collapse_threshold_fraction=args.collapse_threshold_fraction,
                    initial_income_per_capita=args.initial_income_per_capita,
                    avalanche_protocol=args.avalanche_protocol,
                    validate_accounting=not args.no_validate_accounting,
                )
            )
            counter += 1
    return run_specs


def topology_defaults(spec: RunSpec) -> dict[str, int | float | str]:
    if spec.topology != "complete":
        return {}
    n = spec.n_nodes
    edges = n * (n - 1) // 2
    mean_degree = float(n - 1) if n else 0.0
    return {
        "topology": "complete",
        "target_mean_degree": n - 1,
        "topology_seed": spec.topology_seed,
        "topology_nodes": n,
        "topology_edges": edges,
        "topology_mean_degree": mean_degree,
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


def run_one(spec: RunSpec) -> tuple[dict[str, object], list[dict[str, object]]]:
    params = CreditNetworkParams(
        n_nodes=spec.n_nodes,
        mean_initial_money=spec.mean_initial_money,
        money_distribution=spec.money_distribution,
        income_distribution_rule=spec.income_distribution_rule,
        growth_rule=spec.growth_rule,
        consumption_wealth_propensity=spec.a,
        consumption_income_propensity=spec.b,
        investment_income_propensity=spec.c,
        initial_income_per_capita=spec.initial_income_per_capita,
        collapse_threshold_fraction=spec.collapse_threshold_fraction,
        max_periods=spec.max_periods,
        max_time_steps=spec.max_time_steps,
        validate_accounting=spec.validate_accounting,
        period_length_rule="income",
        avalanche_protocol=spec.avalanche_protocol,
    )
    if spec.topology == "complete":
        result = simulate_one_run(params, seed=spec.seed, keep_period_history=False)
        extra_params = topology_defaults(spec)
    else:
        topology_spec = TopologySpec(
            topology=spec.topology,
            target_mean_degree=spec.target_mean_degree,
            sw_rewire_probability=spec.sw_rewire_probability,
        )
        result = simulate_one_topology_run(
            params,
            topology_spec,
            seed=spec.seed,
            topology_seed=spec.topology_seed,
            keep_period_history=False,
        )
        extra_params = {}

    row = result.summary_row()
    row.update(extra_params)
    row.update(
        {
            "scenario_id": spec.scenario_id,
            "scenario_base_id": spec.scenario_base_id,
            "run_index": spec.run_index,
            "spending_label": spec.spending_label,
            "topology_label": spec.topology_label,
            "topology_family": spec.topology,
            "target_mean_degree_requested": spec.target_mean_degree,
        }
    )
    events: list[dict[str, object]] = []
    for event_index, event in enumerate(result.avalanche_history, start=1):
        collapse_size = int(event.get("collapse_size", 0) or 0)
        initial_defaults = int(event.get("initial_default_count", 0) or 0)
        event_row = dict(event)
        event_row.update(
            {
                "seed": spec.seed,
                "run_index": spec.run_index,
                "avalanche_index": event_index,
                "scenario_id": spec.scenario_id,
                "scenario_base_id": spec.scenario_base_id,
                "n_nodes": spec.n_nodes,
                "money_distribution": spec.money_distribution,
                "income_distribution_rule": spec.income_distribution_rule,
                "growth_rule": spec.growth_rule,
                "spending_label": spec.spending_label,
                "consumption_wealth_propensity": spec.a,
                "consumption_income_propensity": spec.b,
                "investment_income_propensity": spec.c,
                "topology_label": spec.topology_label,
                "topology_family": spec.topology,
                "target_mean_degree_requested": spec.target_mean_degree,
                "propagated_default_count": max(collapse_size - initial_defaults, 0),
            }
        )
        events.append(event_row)
    return row, events


def aggregate_scenarios(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario_id, sub in runs.groupby("scenario_id", sort=False):
        event_sub = events[events["scenario_id"].eq(scenario_id)] if not events.empty else events
        first = sub.iloc[0]
        defaulted = sub[sub["ended_by_default"].astype(bool)]
        event_count = int(len(event_sub))
        size_sum = float(event_sub["collapse_size"].sum()) if event_count else 0.0
        prop_sum = float(event_sub["propagated_default_count"].sum()) if event_count else 0.0
        initial_sum = (
            float(event_sub["initial_default_count"].sum()) if event_count else 0.0
        )
        rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_base_id": first["scenario_base_id"],
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
                "mean_avalanche_count": float(sub["avalanche_count"].mean()),
                "event_count": event_count,
                "events_per_run": event_count / max(float(len(sub)), 1.0),
                "event_occupancy": float(sub["avalanche_count"].sum())
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
                "max_event_size": (
                    int(event_sub["collapse_size"].max()) if event_count else 0
                ),
                "mean_initial_default_count": (
                    float(event_sub["initial_default_count"].mean()) if event_count else 0.0
                ),
                "mean_propagated_default_count": (
                    float(event_sub["propagated_default_count"].mean()) if event_count else 0.0
                ),
                "propagated_share_total": prop_sum / size_sum if size_sum > 0 else 0.0,
                "initial_share_total": initial_sum / size_sum if size_sum > 0 else 0.0,
                "mean_first_cascade_credit": (
                    float(defaulted["credit_scale_before_cascade"].mean())
                    if len(defaulted)
                    else 0.0
                ),
                "mean_final_active_credit": float(sub["final_active_credit"].mean()),
                "mean_initial_gini": float(sub["initial_money_gini"].mean()),
                "mean_final_net_worth_gini": float(sub["final_net_worth_gini"].mean()),
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
    specs = make_specs(args)
    total = len(specs)
    if total == 0:
        raise ValueError("empty run spec list")

    rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=max(int(args.workers), 1)) as executor:
        futures = [executor.submit(run_one, spec) for spec in specs]
        for index, future in enumerate(as_completed(futures), start=1):
            row, events = future.result()
            rows.append(row)
            event_rows.extend(events)
            if args.progress_every > 0 and (
                index % args.progress_every == 0 or index == total
            ):
                print(
                    f"completed_runs={index}/{total}",
                    file=sys.stderr,
                    flush=True,
                )

    runs = pd.DataFrame(rows).sort_values(["scenario_id", "run_index"])
    events = pd.DataFrame(event_rows)
    if not events.empty:
        events = events.sort_values(["scenario_id", "run_index", "avalanche_index"])
    scenario_summary = aggregate_scenarios(runs, events)

    run_summary_csv = args.output_dir / "run_summary.csv"
    avalanche_csv = args.output_dir / "avalanche_events.csv"
    scenario_summary_csv = args.output_dir / "scenario_summary.csv"
    runs.to_csv(run_summary_csv, index=False)
    events.to_csv(avalanche_csv, index=False)
    scenario_summary.to_csv(scenario_summary_csv, index=False)

    metadata = {
        "created_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
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
            "Comprehensive factorial screen. It is designed for phase diagrams "
            "and candidate selection; strict SOC promotion still requires "
            "stationarity and finite-size follow-up."
        ),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
