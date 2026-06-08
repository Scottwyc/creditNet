#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet.phase2_mechanism import (  # noqa: E402
    MechanismParams,
    run_phase2_accounting_checks,
    simulate_mechanism_run,
)


CST = ZoneInfo("Asia/Shanghai")


def timestamp() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run phase-2 clearing mechanism ablations.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--suite", choices=["smoke", "full"], default="full")
    parser.add_argument("--runs", type=int, default=24)
    parser.add_argument("--seed-base", type=int, default=2026084000)
    parser.add_argument("--high-risk-periods", type=int, default=200)
    parser.add_argument("--boundary-periods", type=int, default=300)
    parser.add_argument("--validate-full-accounting", action="store_true")
    parser.add_argument("--keep-first-history", action="store_true")
    parser.add_argument("--progress-every", type=int, default=20)
    return parser.parse_args()


def build_protocols(args: argparse.Namespace) -> list[tuple[str, MechanismParams]]:
    if args.suite == "smoke":
        common = dict(
            n_nodes=60,
            mean_initial_money=15.0,
            money_distribution="lognormal",
            income_distribution_rule="biased",
            max_macro_periods=35,
            max_drive_steps_per_macro=120,
            validate_accounting=True,
        )
        return [
            (
                "high_risk_income_c020",
                MechanismParams(**common, drive_rule="income", investment_income_propensity=0.20),
            ),
            (
                "boundary_fixed_k20",
                MechanismParams(**common, drive_rule="fixed", fixed_drive_steps=20),
            ),
        ]

    common = dict(
        n_nodes=200,
        mean_initial_money=20.0,
        money_distribution="lognormal",
        income_distribution_rule="biased",
        growth_rule="random",
        consumption_wealth_propensity=0.02,
        consumption_income_propensity=0.20,
        initial_income_per_capita=5.0,
        max_drive_steps_per_macro=500,
        validate_accounting=args.validate_full_accounting,
    )
    return [
        (
            "high_risk_income_c020",
            MechanismParams(
                **common,
                drive_rule="income",
                investment_income_propensity=0.20,
                max_macro_periods=args.high_risk_periods,
            ),
        ),
        (
            "boundary_fixed_k20",
            MechanismParams(
                **common,
                drive_rule="fixed",
                fixed_drive_steps=20,
                max_macro_periods=args.boundary_periods,
            ),
        ),
    ]


def build_variants() -> list[tuple[str, dict[str, object]]]:
    return [
        (
            "reference_period_end",
            {
                "settlement_mode": "period_end",
                "settlement_batches": 1,
                "recovery_rate": 0.0,
                "wipe_defaulted_assets": True,
                "default_node_mode": "continue",
            },
        ),
        (
            "check_only_b10",
            {
                "settlement_mode": "check_only",
                "settlement_batches": 10,
                "recovery_rate": 0.0,
                "wipe_defaulted_assets": True,
                "default_node_mode": "continue",
            },
        ),
        (
            "flow_split_b10_check_q10",
            {
                "settlement_mode": "settle_and_check",
                "settlement_batches": 10,
                "default_check_every_settlements": 10,
                "recovery_rate": 0.0,
                "wipe_defaulted_assets": True,
                "default_node_mode": "continue",
            },
        ),
        (
            "flow_split_b10_check_q5",
            {
                "settlement_mode": "settle_and_check",
                "settlement_batches": 10,
                "default_check_every_settlements": 5,
                "recovery_rate": 0.0,
                "wipe_defaulted_assets": True,
                "default_node_mode": "continue",
            },
        ),
        (
            "flow_split_b10_check_q2",
            {
                "settlement_mode": "settle_and_check",
                "settlement_batches": 10,
                "default_check_every_settlements": 2,
                "recovery_rate": 0.0,
                "wipe_defaulted_assets": True,
                "default_node_mode": "continue",
            },
        ),
        (
            "flow_split_b10_check_q1",
            {
                "settlement_mode": "settle_and_check",
                "settlement_batches": 10,
                "default_check_every_settlements": 1,
                "recovery_rate": 0.0,
                "wipe_defaulted_assets": True,
                "default_node_mode": "continue",
            },
        ),
        (
            "recovery_50pct",
            {
                "settlement_mode": "period_end",
                "settlement_batches": 1,
                "recovery_rate": 0.50,
                "wipe_defaulted_assets": True,
                "default_node_mode": "continue",
            },
        ),
        (
            "recovery_90pct",
            {
                "settlement_mode": "period_end",
                "settlement_batches": 1,
                "recovery_rate": 0.90,
                "wipe_defaulted_assets": True,
                "default_node_mode": "continue",
            },
        ),
        (
            "keep_defaulted_assets",
            {
                "settlement_mode": "period_end",
                "settlement_batches": 1,
                "recovery_rate": 0.0,
                "wipe_defaulted_assets": False,
                "default_node_mode": "continue",
            },
        ),
        (
            "permanent_exit",
            {
                "settlement_mode": "period_end",
                "settlement_batches": 1,
                "recovery_rate": 0.0,
                "wipe_defaulted_assets": True,
                "default_node_mode": "exit",
            },
        ),
        (
            "reset_to_initial_cash",
            {
                "settlement_mode": "period_end",
                "settlement_batches": 1,
                "recovery_rate": 0.0,
                "wipe_defaulted_assets": True,
                "default_node_mode": "reset",
            },
        ),
    ]


def write_checkpoint(
    output_dir: Path,
    rows: list[dict[str, object]],
    event_rows: list[dict[str, object]],
    manifest_rows: list[dict[str, object]],
    histories: dict[str, object],
) -> None:
    pd.DataFrame(rows).to_csv(output_dir / "run_summary.csv", index=False)
    pd.DataFrame(event_rows).to_csv(output_dir / "avalanche_events.csv", index=False)
    pd.DataFrame(manifest_rows).drop_duplicates("scenario_id").to_csv(
        output_dir / "scenario_manifest.csv", index=False
    )
    (output_dir / "first_run_macro_histories.json").write_text(
        json.dumps(histories, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    start_time = timestamp()
    checks = run_phase2_accounting_checks()
    (args.output_dir / "accounting_checks.json").write_text(
        json.dumps(
            {"created_at": timestamp(), "checks": checks},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    protocols = build_protocols(args)
    variants = build_variants()
    runs = 2 if args.suite == "smoke" and args.runs == 24 else args.runs
    rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    manifest_rows: list[dict[str, object]] = []
    histories: dict[str, object] = {}
    completed_runs = 0

    for protocol_index, (protocol_id, base_params) in enumerate(protocols):
        for mechanism_id, overrides in variants:
            params = replace(base_params, **overrides)
            scenario_id = f"{protocol_id}__{mechanism_id}"
            manifest_rows.append(
                {
                    "scenario_id": scenario_id,
                    "protocol_id": protocol_id,
                    "mechanism_id": mechanism_id,
                    **asdict(params),
                }
            )
            for run_index in range(runs):
                # Reusing the same seed across mechanisms gives paired comparisons.
                seed = args.seed_base + protocol_index * 100_000 + run_index
                keep_history = args.keep_first_history and run_index == 0
                result = simulate_mechanism_run(
                    params,
                    seed=seed,
                    keep_macro_history=keep_history,
                )
                row = result.summary_row()
                row.update(
                    {
                        "scenario_id": scenario_id,
                        "protocol_id": protocol_id,
                        "mechanism_id": mechanism_id,
                        "run_index": run_index,
                    }
                )
                rows.append(row)
                for event in result.avalanche_history:
                    event_rows.append(
                        {
                            **event,
                            "seed": seed,
                            "run_index": run_index,
                            "scenario_id": scenario_id,
                            "protocol_id": protocol_id,
                            "mechanism_id": mechanism_id,
                            "n_nodes": params.n_nodes,
                        }
                    )
                if keep_history:
                    histories[scenario_id] = result.macro_history
                completed_runs += 1
                if args.progress_every > 0 and completed_runs % args.progress_every == 0:
                    print(
                        f"{timestamp()} completed_runs={completed_runs}",
                        file=sys.stderr,
                        flush=True,
                    )
            write_checkpoint(args.output_dir, rows, event_rows, manifest_rows, histories)

    end_time = timestamp()
    metadata = {
        "created_at": end_time,
        "started_at": start_time,
        "completed_at": end_time,
        "suite": args.suite,
        "command": " ".join(sys.argv),
        "command_args": vars(args) | {"output_dir": str(args.output_dir)},
        "runs_per_scenario": runs,
        "protocol_count": len(protocols),
        "mechanism_variant_count": len(variants),
        "scenario_count": len(protocols) * len(variants),
        "completed_runs": completed_runs,
        "event_count": len(event_rows),
        "seed_rule": (
            "seed_base + protocol_index*100000 + run_index; identical seeds are paired "
            "across mechanism variants within each protocol"
        ),
        "identifiability": {
            "negative_control": (
                "check_only splits the fixed macro credit target but adds no flow settlement; "
                "unit credit preserves node net worth, so intermediate checks should add no defaults"
            ),
            "genuine_frequency_intervention": (
                "flow_split_b10_check_q10/q5/q2/q1 hold ten settlement/flow cycles fixed "
                "and vary only whether clearing occurs every 10/5/2/1 settlements"
            ),
            "flow_frequency_intervention": (
                "reference_period_end versus flow_split_b10_check_q10 changes one macro "
                "settlement into ten prorated flow settlements while checking at the same macro end; "
                "this is a flow/income-dynamics intervention, not pure check-frequency isolation"
            ),
        },
        "temporal_decision_gate": (
            "Analysis must compare active-avalanche macro-period rate, wait-one share, lag-1 "
            "event-size correlation, time quartiles, final-20% large-event rate, final Gini, "
            "and final active credit to test persistent low-credit/high-inequality failure."
        ),
        "accounting": {
            "recovery": (
                "target recovery is paid from the defaulted debtor's existing cash, pro-rata "
                "to creditors and cash-capped; it conserves total cash"
            ),
            "asset_wipe": (
                "wipe_defaulted_assets cancels loans held by a defaulted node and releases "
                "the corresponding borrower liabilities"
            ),
            "reset": (
                "reset clears the node balance sheet and restores run-specific initial cash; "
                "the external reset cash flow is recorded explicitly"
            ),
        },
        "outputs": {
            "run_summary": str(args.output_dir / "run_summary.csv"),
            "avalanche_events": str(args.output_dir / "avalanche_events.csv"),
            "scenario_manifest": str(args.output_dir / "scenario_manifest.csv"),
            "accounting_checks": str(args.output_dir / "accounting_checks.json"),
            "first_run_histories": str(args.output_dir / "first_run_macro_histories.json"),
        },
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
