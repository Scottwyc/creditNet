#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from creditnet.phase2_topology import TopologySpec, simulate_one_topology_run
from creditnet.simulation import CreditNetworkParams, simulate_one_run
from run_comprehensive_scenario_scan import aggregate_scenarios

CST = ZoneInfo("Asia/Shanghai")

SPENDING = {
    "low": (0.01, 0.10),
    "baseline": (0.02, 0.20),
    "high_income": (0.02, 0.40),
    "high_wealth": (0.04, 0.20),
    "high_both": (0.04, 0.40),
}


@dataclass(frozen=True)
class CriticalScenario:
    scenario_index: int
    scenario_id: str
    scenario_base_id: str
    center_c: float
    c: float
    n_nodes: int
    mean_initial_money: float
    money_distribution: str
    income_distribution_rule: str
    growth_rule: str
    spending_label: str
    a: float
    b: float
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


@dataclass(frozen=True)
class RunSpec:
    scenario: CriticalScenario
    run_index: int
    seed: int
    topology_seed: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fine scan period_end critical-band candidates from the comprehensive phase map."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--source-summary",
        type=Path,
        default=ROOT / "results/credit_soc_comprehensive_scan_analysis_20260608_v1/scenario_summary_enriched.csv",
    )
    parser.add_argument(
        "--source-soc",
        type=Path,
        default=ROOT / "results/credit_soc_comprehensive_scan_analysis_20260608_v1/soc_screen_table.csv",
    )
    parser.add_argument("--candidate-count", type=int, default=12)
    parser.add_argument("--c-window", type=float, default=0.10)
    parser.add_argument("--c-step", type=float, default=0.025)
    parser.add_argument("--c-min", type=float, default=0.05)
    parser.add_argument("--c-max", type=float, default=0.85)
    parser.add_argument("--runs-per-scenario", type=int, default=24)
    parser.add_argument("--max-periods", type=int, default=240)
    parser.add_argument("--max-time-steps", type=int, default=0)
    parser.add_argument("--n-nodes", type=int, default=120)
    parser.add_argument("--mean-initial-money", type=float, default=20.0)
    parser.add_argument("--initial-income-per-capita", type=float, default=5.0)
    parser.add_argument("--collapse-threshold-fraction", type=float, default=0.10)
    parser.add_argument("--sw-rewire-probability", type=float, default=0.10)
    parser.add_argument("--seed-base", type=int, default=2026061100)
    parser.add_argument("--topology-seed-base", type=int, default=2026069100)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--no-validate-accounting", action="store_true")
    parser.add_argument("--write-candidate-table", action="store_true")
    return parser.parse_args()


def parse_base_id(base_id: str) -> dict[str, object]:
    parts = {}
    for token in base_id.split("__"):
        key, value = token.split("-", 1)
        parts[key] = value
    if "spend" not in parts or parts["spend"] not in SPENDING:
        raise ValueError(f"unknown spending label in {base_id}")
    topology_label = str(parts["topo"])
    if topology_label == "complete":
        topology = "complete"
        degree = 0
    else:
        family, degree_text = topology_label.split("_k", 1)
        topology = family
        degree = int(degree_text)
    a, b = SPENDING[str(parts["spend"])]
    return {
        "money_distribution": parts["money"],
        "income_distribution_rule": parts["income"],
        "growth_rule": parts["growth"],
        "spending_label": parts["spend"],
        "a": a,
        "b": b,
        "topology_label": topology_label,
        "topology": topology,
        "target_mean_degree": degree,
    }


def c_values(center: float, args: argparse.Namespace) -> list[float]:
    lo = max(args.c_min, center - args.c_window)
    hi = min(args.c_max, center + args.c_window)
    values = []
    v = lo
    while v <= hi + 1e-9:
        values.append(round(v, 3))
        v += args.c_step
    if round(center, 3) not in values:
        values.append(round(center, 3))
    return sorted(set(values))


def select_candidates(args: argparse.Namespace) -> pd.DataFrame:
    soc = pd.read_csv(args.source_soc)
    rows = soc[
        soc["event_large_event_rate"].between(0.02, 0.90)
        & (soc["event_occupancy"] < 0.90)
        & (soc["event_count"] >= 60)
    ].copy()
    rows["critical_band_rank"] = (
        rows["soc_screen_score"].fillna(0) * 10.0
        + rows["propagated_share_total"].fillna(0) * 5.0
        + rows["event_large_event_rate"].fillna(0)
        - rows["event_occupancy"].fillna(0) * 0.2
    )
    best = (
        rows.sort_values("critical_band_rank", ascending=False)
        .drop_duplicates("scenario_base_id")
        .head(args.candidate_count)
        .copy()
    )
    return best.reset_index(drop=True)


def make_scenarios(args: argparse.Namespace) -> tuple[list[CriticalScenario], pd.DataFrame]:
    candidates = select_candidates(args)
    scenarios: list[CriticalScenario] = []
    scenario_index = 0
    for row in candidates.itertuples(index=False):
        params = parse_base_id(row.scenario_base_id)
        center = float(row.c)
        for c in c_values(center, args):
            c_label = f"{c:.3f}".replace(".", "p")
            scenario_id = f"critical__base{len(scenarios):04d}__c-{c_label}__{row.scenario_base_id}"
            scenarios.append(
                CriticalScenario(
                    scenario_index=scenario_index,
                    scenario_id=scenario_id,
                    scenario_base_id=row.scenario_base_id,
                    center_c=center,
                    c=float(c),
                    n_nodes=args.n_nodes,
                    mean_initial_money=args.mean_initial_money,
                    max_periods=args.max_periods,
                    max_time_steps=args.max_time_steps,
                    collapse_threshold_fraction=args.collapse_threshold_fraction,
                    initial_income_per_capita=args.initial_income_per_capita,
                    sw_rewire_probability=args.sw_rewire_probability,
                    avalanche_protocol="continue_after_avalanche",
                    validate_accounting=not args.no_validate_accounting,
                    **params,
                )
            )
            scenario_index += 1
    if args.num_shards < 1:
        raise ValueError("--num-shards must be >= 1")
    if not 0 <= args.shard_index < args.num_shards:
        raise ValueError("--shard-index must be in [0, num_shards)")
    shard = [s for s in scenarios if s.scenario_index % args.num_shards == args.shard_index]
    return shard, candidates


def make_run_specs(args: argparse.Namespace) -> tuple[list[RunSpec], pd.DataFrame]:
    scenarios, candidates = make_scenarios(args)
    specs: list[RunSpec] = []
    for scenario in scenarios:
        for run_index in range(args.runs_per_scenario):
            global_index = scenario.scenario_index * args.runs_per_scenario + run_index
            specs.append(
                RunSpec(
                    scenario=scenario,
                    run_index=run_index,
                    seed=args.seed_base + global_index,
                    topology_seed=args.topology_seed_base + global_index,
                )
            )
    return specs, candidates


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
        default_check_mode="period_end",
    )
    if scenario.topology == "complete":
        result = simulate_one_run(params, seed=spec.seed, keep_period_history=False)
        n = scenario.n_nodes
        extra_params = {
            "topology": "complete",
            "target_mean_degree": n - 1,
            "topology_seed": spec.topology_seed,
            "topology_nodes": n,
            "topology_edges": n * (n - 1) // 2,
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
    else:
        topology_spec = TopologySpec(
            topology=scenario.topology,
            target_mean_degree=scenario.target_mean_degree,
            sw_rewire_probability=scenario.sw_rewire_probability,
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
            "scenario_id": scenario.scenario_id,
            "scenario_base_id": scenario.scenario_base_id,
            "scenario_index": scenario.scenario_index,
            "run_index": spec.run_index,
            "protocol": "period_end_critical_refined",
            "center_c": scenario.center_c,
            "spending_label": scenario.spending_label,
            "topology_label": scenario.topology_label,
            "topology_family": scenario.topology,
            "target_mean_degree_requested": scenario.target_mean_degree,
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
                "scenario_id": scenario.scenario_id,
                "scenario_base_id": scenario.scenario_base_id,
                "scenario_index": scenario.scenario_index,
                "protocol": "period_end_critical_refined",
                "center_c": scenario.center_c,
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
                "propagated_default_count": max(collapse_size - initial_defaults, 0),
            }
        )
        events.append(event_row)
    return row, events


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    specs, candidates = make_run_specs(args)
    if args.write_candidate_table or args.shard_index == 0:
        candidates.to_csv(args.output_dir / "selected_critical_band_bases.csv", index=False)
    if not specs:
        raise ValueError("empty run specs")

    rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=max(int(args.workers), 1)) as executor:
        futures = [executor.submit(run_one, spec) for spec in specs]
        for index, future in enumerate(as_completed(futures), start=1):
            row, events = future.result()
            rows.append(row)
            event_rows.extend(events)
            if args.progress_every and (index % args.progress_every == 0 or index == len(specs)):
                print(
                    f"shard={args.shard_index}/{args.num_shards} completed_runs={index}/{len(specs)}",
                    file=sys.stderr,
                    flush=True,
                )

    runs = pd.DataFrame(rows).sort_values(["scenario_index", "scenario_id", "run_index"])
    events = pd.DataFrame(event_rows)
    if not events.empty:
        events = events.sort_values(["scenario_index", "scenario_id", "run_index", "avalanche_index"])
    scenario_summary = aggregate_scenarios(runs, events)
    scenario_summary["protocol"] = "period_end_critical_refined"

    runs.to_csv(args.output_dir / "run_summary.csv", index=False)
    events.to_csv(args.output_dir / "avalanche_events.csv", index=False)
    scenario_summary.to_csv(args.output_dir / "scenario_summary.csv", index=False)
    metadata = {
        "created_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "protocol": "period_end_critical_refined",
        "command_args": {
            key: (str(value) if isinstance(value, Path) else value)
            for key, value in vars(args).items()
        },
        "candidate_base_count": int(candidates["scenario_base_id"].nunique()),
        "scenario_count": int(scenario_summary["scenario_id"].nunique()),
        "run_count": int(len(runs)),
        "event_count": int(len(events)),
        "note": (
            "Fine scan around period_end phase-map critical bands. Candidate bases "
            "come from non-saturated transition rows in the 20260608 comprehensive screen."
        ),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
