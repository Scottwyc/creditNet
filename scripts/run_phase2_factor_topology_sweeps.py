#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet.phase2_topology import TopologySpec, simulate_one_topology_run
from creditnet.simulation import CreditNetworkParams


@dataclass(frozen=True)
class Scenario:
    factor_family: str
    money_distribution: str = "lognormal"
    income_rule: str = "biased"
    growth_rule: str = "random"
    a: float = 0.02
    b: float = 0.20
    topology: str = "er"
    target_mean_degree: int = 12

    def scenario_id(self) -> str:
        return (
            f"{self.factor_family}__money-{self.money_distribution}__income-{self.income_rule}"
            f"__growth-{self.growth_rule}__a-{self.a:.3f}__b-{self.b:.3f}"
            f"__topo-{self.topology}__k-{self.target_mean_degree}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-2 factor and explicit-topology sweeps.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runs-per-scenario", type=int, default=8)
    parser.add_argument("--n-nodes", type=int, default=200)
    parser.add_argument("--mean-initial-money", type=float, default=20.0)
    parser.add_argument("--fixed-k", type=int, default=20)
    parser.add_argument("--max-periods", type=int, default=240)
    parser.add_argument("--seed-base", type=int, default=2026060400)
    parser.add_argument("--topology-seed-base", type=int, default=2026064400)
    parser.add_argument("--sw-rewire-probability", type=float, default=0.10)
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument("--families", nargs="+", default=["all"])
    parser.add_argument("--no-validate-accounting", action="store_true")
    return parser.parse_args()


def build_scenarios(families: set[str]) -> list[Scenario]:
    all_families = {
        "topology_degree",
        "money_distribution",
        "income_rule",
        "ab_grid",
        "topology_growth",
    }
    selected = all_families if "all" in families else families
    unknown = selected - all_families
    if unknown:
        raise ValueError(f"unknown sweep families: {sorted(unknown)}")

    scenarios: list[Scenario] = []
    if "topology_degree" in selected:
        scenarios.extend(
            Scenario("topology_degree", topology=topology, target_mean_degree=degree)
            for topology in ["er", "ba", "sw"]
            for degree in [6, 12, 24]
        )
    if "money_distribution" in selected:
        scenarios.extend(
            Scenario("money_distribution", money_distribution=distribution)
            for distribution in ["equal", "uniform", "normal", "lognormal", "pareto"]
        )
    if "income_rule" in selected:
        scenarios.extend(
            Scenario("income_rule", income_rule=income_rule)
            for income_rule in ["uniform", "biased"]
        )
    if "ab_grid" in selected:
        scenarios.extend(
            Scenario("ab_grid", a=a, b=b)
            for a in [0.01, 0.02, 0.04]
            for b in [0.10, 0.20, 0.30]
        )
    if "topology_growth" in selected:
        scenarios.extend(
            Scenario("topology_growth", topology=topology, growth_rule=growth_rule)
            for topology in ["er", "ba", "sw"]
            for growth_rule in ["random", "preferential_debt"]
        )
    return scenarios


def aggregate_scenarios(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario_id, sub in runs.groupby("scenario_id", sort=False):
        event_sub = events[events["scenario_id"] == scenario_id] if not events.empty else pd.DataFrame()
        first_defaults = sub[sub["ended_by_default"]]
        rows.append(
            {
                "scenario_id": scenario_id,
                "factor_family": sub["factor_family"].iloc[0],
                "money_distribution": sub["money_distribution"].iloc[0],
                "income_distribution_rule": sub["income_distribution_rule"].iloc[0],
                "growth_rule": sub["growth_rule"].iloc[0],
                "a": sub["consumption_wealth_propensity"].iloc[0],
                "b": sub["consumption_income_propensity"].iloc[0],
                "topology": sub["topology"].iloc[0],
                "target_mean_degree": sub["target_mean_degree"].iloc[0],
                "runs": len(sub),
                "seeds": ";".join(map(str, sub["seed"].tolist())),
                "default_run_rate": float(sub["ended_by_default"].mean()),
                "critical_run_rate": float(sub["critical_event"].mean()),
                "mean_first_cascade_credit": (
                    float(first_defaults["credit_scale_before_cascade"].mean())
                    if len(first_defaults)
                    else None
                ),
                "mean_max_collapse_size": float(sub["max_collapse_size"].mean()),
                "mean_avalanche_count": float(sub["avalanche_count"].mean()),
                "event_count": len(event_sub),
                "critical_event_rate": (
                    float(event_sub["critical_event"].mean()) if len(event_sub) else 0.0
                ),
                "mean_event_size": float(event_sub["collapse_size"].mean()) if len(event_sub) else 0.0,
                "p90_event_size": (
                    float(event_sub["collapse_size"].quantile(0.90)) if len(event_sub) else 0.0
                ),
                "max_event_size": int(event_sub["collapse_size"].max()) if len(event_sub) else 0,
                "mean_initial_gini": float(sub["initial_money_gini"].mean()),
                "mean_final_net_worth_gini": float(sub["final_net_worth_gini"].mean()),
                "mean_topology_degree": float(sub["topology_mean_degree"].mean()),
                "mean_topology_clustering": float(sub["topology_clustering"].mean()),
                "mean_topology_degree_cv": float(sub["topology_degree_cv"].mean()),
                "mean_topology_lcc_fraction": float(sub["topology_lcc_fraction"].mean()),
                "mean_topology_path_length": float(
                    sub["topology_lcc_average_path_length"].mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = build_scenarios(set(args.families))
    rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    topology_rows: list[dict[str, object]] = []
    histories: dict[str, object] = {}
    run_counter = 0

    for scenario in scenarios:
        scenario_id = scenario.scenario_id()
        for run_index in range(args.runs_per_scenario):
            seed = args.seed_base + run_counter
            topology_seed = args.topology_seed_base + run_counter
            params = CreditNetworkParams(
                n_nodes=args.n_nodes,
                mean_initial_money=args.mean_initial_money,
                money_distribution=scenario.money_distribution,
                income_distribution_rule=scenario.income_rule,
                growth_rule=scenario.growth_rule,
                consumption_wealth_propensity=scenario.a,
                consumption_income_propensity=scenario.b,
                collapse_threshold_fraction=0.10,
                max_periods=args.max_periods,
                validate_accounting=not args.no_validate_accounting,
                period_length_rule="fixed",
                fixed_period_length_steps=args.fixed_k,
                avalanche_protocol="continue_after_avalanche",
            )
            topology_spec = TopologySpec(
                topology=scenario.topology,
                target_mean_degree=scenario.target_mean_degree,
                sw_rewire_probability=args.sw_rewire_probability,
            )
            keep_history = run_index == 0
            result = simulate_one_topology_run(
                params,
                topology_spec,
                seed=seed,
                topology_seed=topology_seed,
                keep_period_history=keep_history,
            )
            row = result.summary_row()
            row |= {
                "scenario_id": scenario_id,
                "factor_family": scenario.factor_family,
                "run_index": run_index,
            }
            rows.append(row)
            topology_rows.append(
                {
                    key: row[key]
                    for key in [
                        "scenario_id",
                        "factor_family",
                        "run_index",
                        "seed",
                        "topology_seed",
                        "topology",
                        "target_mean_degree",
                        "topology_nodes",
                        "topology_edges",
                        "topology_mean_degree",
                        "topology_density",
                        "topology_clustering",
                        "topology_degree_std",
                        "topology_degree_cv",
                        "topology_max_degree",
                        "topology_components",
                        "topology_lcc_nodes",
                        "topology_lcc_fraction",
                        "topology_lcc_average_path_length",
                    ]
                }
            )
            for event_index, event in enumerate(result.avalanche_history, start=1):
                event_rows.append(
                    dict(event)
                    | {
                        "scenario_id": scenario_id,
                        "factor_family": scenario.factor_family,
                        "run_index": run_index,
                        "seed": seed,
                        "avalanche_index": event_index,
                        "money_distribution": scenario.money_distribution,
                        "income_distribution_rule": scenario.income_rule,
                        "growth_rule": scenario.growth_rule,
                        "a": scenario.a,
                        "b": scenario.b,
                        "topology": scenario.topology,
                        "target_mean_degree": scenario.target_mean_degree,
                    }
                )
            if keep_history:
                histories[scenario_id] = result.period_history

            run_counter += 1
            if args.progress_every > 0 and run_counter % args.progress_every == 0:
                print(f"completed_runs={run_counter}/{len(scenarios) * args.runs_per_scenario}", flush=True)

    runs = pd.DataFrame(rows)
    events = pd.DataFrame(event_rows)
    topology_instances = pd.DataFrame(topology_rows)
    scenario_summary = aggregate_scenarios(runs, events)
    runs.to_csv(args.output_dir / "run_summary.csv", index=False)
    events.to_csv(args.output_dir / "avalanche_events.csv", index=False)
    topology_instances.to_csv(args.output_dir / "topology_instances.csv", index=False)
    scenario_summary.to_csv(args.output_dir / "scenario_summary.csv", index=False)
    (args.output_dir / "first_run_histories.json").write_text(
        json.dumps(histories, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z")
    metadata = {
        "created_at": now,
        "command_args": vars(args) | {"output_dir": str(args.output_dir)},
        "protocol": {
            "period_length_rule": "fixed",
            "fixed_k": args.fixed_k,
            "avalanche_protocol": "continue_after_avalanche",
            "default_check_mode": "period_end",
            "collapse_threshold_fraction": 0.10,
            "directed_mapping": (
                "A fixed undirected opportunity edge permits credit in either direction; "
                "the cash-eligible lender and growth-rule-selected adjacent borrower set direction."
            ),
        },
        "scenario_count": len(scenarios),
        "run_count": len(runs),
        "event_count": len(events),
        "run_seeds": runs["seed"].tolist(),
        "topology_seeds": runs["topology_seed"].tolist(),
        "scenarios": [asdict(scenario) | {"scenario_id": scenario.scenario_id()} for scenario in scenarios],
        "outputs": {
            "run_summary": str(args.output_dir / "run_summary.csv"),
            "avalanche_events": str(args.output_dir / "avalanche_events.csv"),
            "topology_instances": str(args.output_dir / "topology_instances.csv"),
            "scenario_summary": str(args.output_dir / "scenario_summary.csv"),
        },
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: metadata[key] for key in ["created_at", "scenario_count", "run_count", "event_count"]}))


if __name__ == "__main__":
    main()
