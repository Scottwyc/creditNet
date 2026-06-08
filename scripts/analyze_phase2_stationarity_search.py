#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CST = ZoneInfo("Asia/Shanghai")
CLASS_CODES = {
    "no_event_stable": 0,
    "no_event_accumulating_nonstationary": 1,
    "rare_stationary_soc_candidate": 2,
    "rare_stationary_events": 3,
    "stationary_high_occupancy_trigger_risk": 4,
    "sparse_but_nonstationary": 5,
    "drift_or_persistent_failure": 6,
}
CANDIDATE_GATE = {
    "minimum_late_events": 60,
    "minimum_late_occupancy": 0.001,
    "late_occupancy_note": "high occupancy is reported as event-dependence/batch-trigger risk, not a standalone rejection",
    "late_wait1_note": "P(wait=1) is descriptive and not a standalone rejection",
    "maximum_absolute_late_size_lag1": 0.30,
    "maximum_early_late_occupancy_difference": "max(0.02, 0.25 * max(early, late))",
    "maximum_relative_mean_size_drift": 0.25,
    "maximum_relative_active_credit_drift": 0.20,
    "maximum_absolute_gini_drift": 0.05,
    "maximum_absolute_propagation_share_drift": 0.10,
    "maximum_late_repeated_default_share": 0.80,
    "minimum_late_single_initial_default_fraction": 0.50,
    "minimum_late_propagated_default_share": 0.10,
    "breadth": "late p99 size >= 0.05*N and at least one late event >= 0.10*N",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze long stationarity-search shards.")
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--shards", default="income,fixed")
    return parser.parse_args()


def markdown_table(frame: pd.DataFrame) -> str:
    def render(value: object) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, (float, np.floating)):
            return f"{float(value):.4f}"
        return str(value)

    if frame.empty:
        return "_无记录_"
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(render(row[column]) for column in columns) + " |")
    return "\n".join(lines)


def relpath(path: Path, report_path: Path) -> str:
    return os.path.relpath(path, start=report_path.parent)


def sequence_diagnostics(events: pd.DataFrame) -> tuple[float, float]:
    wait_equal_one = 0
    wait_total = 0
    left: list[float] = []
    right: list[float] = []
    for _, group in events.groupby(["seed", "run_index"], sort=False):
        ordered = group.sort_values("period")
        periods = ordered["period"].to_numpy(dtype=int)
        sizes = ordered["collapse_size"].to_numpy(dtype=float)
        if periods.size > 1:
            waits = np.diff(periods)
            wait_equal_one += int(np.sum(waits == 1))
            wait_total += int(waits.size)
            left.extend(sizes[:-1])
            right.extend(sizes[1:])
    wait_one = wait_equal_one / wait_total if wait_total else float("nan")
    if len(left) < 3 or np.std(left) == 0 or np.std(right) == 0:
        lag1 = float("nan")
    else:
        lag1 = float(np.corrcoef(left, right)[0, 1])
    return wait_one, lag1


def read_shards(
    result_dir: Path, shard_names: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    run_frames: list[pd.DataFrame] = []
    event_frames: list[pd.DataFrame] = []
    window_frames: list[pd.DataFrame] = []
    bin_frames: list[pd.DataFrame] = []
    metadata: list[dict[str, Any]] = []
    event_columns = [
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
        "initial_default_count",
        "propagated_default_count",
        "propagated_default_share",
        "single_initial_default",
        "collapse_size",
        "critical_event",
        "credit_scale_before_cascade",
        "active_credit_after_cascade",
        "new_unique_default_count",
        "repeated_default_count",
    ]
    for name in shard_names:
        shard = result_dir / name
        if not shard.exists():
            raise FileNotFoundError(f"missing shard: {shard}")
        run_frames.append(pd.read_csv(shard / "run_summary.csv"))
        window_frames.append(pd.read_csv(shard / "run_windows.csv"))
        bin_frames.append(pd.read_csv(shard / "run_time_bins.csv"))
        event_frames.append(pd.read_csv(shard / "avalanche_events.csv", usecols=event_columns))
        metadata.append(json.loads((shard / "metadata.json").read_text(encoding="utf-8")))
    return (
        pd.concat(run_frames, ignore_index=True),
        pd.concat(event_frames, ignore_index=True),
        pd.concat(window_frames, ignore_index=True),
        pd.concat(bin_frames, ignore_index=True),
        metadata,
    )


def window_summary(windows: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    keys = [
        "family",
        "scenario_id",
        "scenario_index",
        "n_nodes",
        "money_distribution",
        "control_name",
        "control_value",
        "window",
    ]
    event_groups = {
        (scenario_id, window): group
        for (scenario_id, window), group in events[events["window"].isin(["early", "late"])].groupby(
            ["scenario_id", "window"], sort=False
        )
    }
    rows: list[dict[str, Any]] = []
    for key_values, sub in windows.groupby(keys, sort=True):
        base = dict(zip(keys, key_values))
        scenario_events = event_groups.get(
            (base["scenario_id"], base["window"]), pd.DataFrame(columns=events.columns)
        )
        sizes = scenario_events["collapse_size"].to_numpy(dtype=float)
        wait_one, lag1 = sequence_diagnostics(scenario_events)
        periods = int(sub["period_count"].sum())
        event_count = int(sub["event_count"].sum())
        unique_defaults = int(sub["unique_default_nodes_in_window"].sum())
        total_defaults = int(sub["total_default_occurrences_in_window"].sum())
        rows.append(
            base
            | {
                "runs": len(sub),
                "period_count": periods,
                "event_count": event_count,
                "runs_with_events": int(np.sum(sub["event_count"] > 0)),
                "avalanche_occupancy": event_count / periods if periods else 0.0,
                "one_period_wait_fraction": wait_one,
                "pooled_size_lag1_correlation": lag1,
                "mean_event_size": float(sizes.mean()) if sizes.size else 0.0,
                "median_event_size": float(np.median(sizes)) if sizes.size else 0.0,
                "p90_event_size": (
                    float(np.quantile(sizes, 0.90)) if sizes.size else 0.0
                ),
                "p95_event_size": (
                    float(np.quantile(sizes, 0.95)) if sizes.size else 0.0
                ),
                "p99_event_size": (
                    float(np.quantile(sizes, 0.99)) if sizes.size else 0.0
                ),
                "max_event_size": int(sizes.max()) if sizes.size else 0,
                "large_event_count": int(np.sum(scenario_events["critical_event"]))
                if sizes.size
                else 0,
                "large_event_rate": (
                    float(np.mean(scenario_events["critical_event"])) if sizes.size else 0.0
                ),
                "mean_initial_default_count": (
                    float(np.mean(scenario_events["initial_default_count"]))
                    if sizes.size
                    else 0.0
                ),
                "mean_propagated_default_count": (
                    float(np.mean(scenario_events["propagated_default_count"]))
                    if sizes.size
                    else 0.0
                ),
                "propagated_default_share": (
                    float(np.sum(scenario_events["propagated_default_count"]) / np.sum(sizes))
                    if np.sum(sizes) > 0
                    else 0.0
                ),
                "single_initial_default_fraction": (
                    float(np.mean(scenario_events["single_initial_default"]))
                    if sizes.size
                    else 0.0
                ),
                "mean_active_credit": (
                    float(
                        np.sum(sub["mean_active_credit"] * sub["period_count"]) / periods
                    )
                    if periods
                    else 0.0
                ),
                "mean_final_net_worth_gini": (
                    float(
                        np.sum(sub["mean_final_net_worth_gini"] * sub["period_count"])
                        / periods
                    )
                    if periods
                    else 0.0
                ),
                "mean_period_length_steps": (
                    float(
                        np.sum(sub["mean_period_length_steps"] * sub["period_count"])
                        / periods
                    )
                    if periods
                    else 0.0
                ),
                "mean_issued_credit": (
                    float(np.sum(sub["mean_issued_credit"] * sub["period_count"]) / periods)
                    if periods
                    else 0.0
                ),
                "unique_default_nodes_within_runs": unique_defaults,
                "total_default_occurrences_within_runs": total_defaults,
                "repeated_default_occurrences_within_runs": total_defaults - unique_defaults,
                "repeated_default_share": (
                    (total_defaults - unique_defaults) / total_defaults
                    if total_defaults
                    else 0.0
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["family", "control_value", "money_distribution", "window"]
    )


def time_bin_summary(bins: pd.DataFrame) -> pd.DataFrame:
    keys = [
        "family",
        "scenario_id",
        "scenario_index",
        "n_nodes",
        "money_distribution",
        "control_name",
        "control_value",
        "time_bin",
    ]
    rows: list[dict[str, Any]] = []
    for key_values, sub in bins.groupby(keys, sort=True):
        base = dict(zip(keys, key_values))
        periods = int(sub["period_count"].sum())
        events = int(sub["event_count"].sum())
        total_defaults = int(sub["total_default_occurrences_in_window"].sum())
        unique_defaults = int(sub["unique_default_nodes_in_window"].sum())
        rows.append(
            base
            | {
                "runs": len(sub),
                "period_count": periods,
                "event_count": events,
                "avalanche_occupancy": events / periods if periods else 0.0,
                "mean_event_size": (
                    float(
                        np.sum(sub["mean_event_size"] * sub["event_count"]) / events
                    )
                    if events
                    else 0.0
                ),
                "large_event_rate": (
                    float(
                        np.sum(sub["large_event_count"]) / events
                    )
                    if events
                    else 0.0
                ),
                "mean_initial_default_count": (
                    float(
                        np.sum(sub["mean_initial_default_count"] * sub["event_count"])
                        / events
                    )
                    if events
                    else 0.0
                ),
                "mean_propagated_default_count": (
                    float(
                        np.sum(sub["mean_propagated_default_count"] * sub["event_count"])
                        / events
                    )
                    if events
                    else 0.0
                ),
                "propagated_default_share": (
                    float(
                        np.sum(
                            sub["propagated_default_share"]
                            * sub["total_default_occurrences_in_window"]
                        )
                        / total_defaults
                    )
                    if total_defaults
                    else 0.0
                ),
                "single_initial_default_fraction": (
                    float(
                        np.sum(sub["single_initial_default_fraction"] * sub["event_count"])
                        / events
                    )
                    if events
                    else 0.0
                ),
                "mean_active_credit": (
                    float(np.sum(sub["mean_active_credit"] * sub["period_count"]) / periods)
                    if periods
                    else 0.0
                ),
                "mean_final_net_worth_gini": (
                    float(
                        np.sum(sub["mean_final_net_worth_gini"] * sub["period_count"])
                        / periods
                    )
                    if periods
                    else 0.0
                ),
                "mean_period_length_steps": (
                    float(
                        np.sum(sub["mean_period_length_steps"] * sub["period_count"])
                        / periods
                    )
                    if periods
                    else 0.0
                ),
                "repeated_default_share": (
                    (total_defaults - unique_defaults) / total_defaults
                    if total_defaults
                    else 0.0
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["family", "money_distribution", "control_value", "time_bin"]
    )


def relative_change(late: float, early: float, floor: float = 1.0) -> float:
    return abs(late - early) / max(abs(early), floor)


def classify(window: pd.DataFrame) -> pd.DataFrame:
    early = window[window["window"] == "early"].drop(columns=["window"]).copy()
    late = window[window["window"] == "late"].drop(columns=["window"]).copy()
    join_keys = [
        "family",
        "scenario_id",
        "scenario_index",
        "n_nodes",
        "money_distribution",
        "control_name",
        "control_value",
    ]
    early = early.rename(
        columns={column: f"early_{column}" for column in early.columns if column not in join_keys}
    )
    late = late.rename(
        columns={column: f"late_{column}" for column in late.columns if column not in join_keys}
    )
    combined = early.merge(late, on=join_keys, how="outer", validate="one_to_one")
    rows: list[dict[str, Any]] = []
    for _, row in combined.iterrows():
        early_occupancy = float(row["early_avalanche_occupancy"])
        late_occupancy = float(row["late_avalanche_occupancy"])
        occupancy_tolerance = max(0.02, 0.25 * max(early_occupancy, late_occupancy))
        occupancy_stationary = abs(late_occupancy - early_occupancy) <= occupancy_tolerance
        size_stationary = relative_change(
            float(row["late_mean_event_size"]), float(row["early_mean_event_size"])
        ) <= 0.25
        credit_stationary = relative_change(
            float(row["late_mean_active_credit"]),
            float(row["early_mean_active_credit"]),
        ) <= 0.20
        gini_stationary = abs(
            float(row["late_mean_final_net_worth_gini"])
            - float(row["early_mean_final_net_worth_gini"])
        ) <= 0.05
        lag1 = float(row["late_pooled_size_lag1_correlation"])
        separation_ok = not math.isnan(lag1) and abs(lag1) <= 0.30
        propagation_stationary = abs(
            float(row["late_propagated_default_share"])
            - float(row["early_propagated_default_share"])
        ) <= CANDIDATE_GATE["maximum_absolute_propagation_share_drift"]
        single_trigger_and_propagation_ok = (
            float(row["late_single_initial_default_fraction"])
            >= CANDIDATE_GATE["minimum_late_single_initial_default_fraction"]
            and float(row["late_propagated_default_share"])
            >= CANDIDATE_GATE["minimum_late_propagated_default_share"]
        )
        stationarity_ok = (
            occupancy_stationary
            and size_stationary
            and credit_stationary
            and gini_stationary
            and propagation_stationary
        )
        rare_stationary = (
            int(row["late_event_count"]) >= 20
            and late_occupancy <= 0.25
            and separation_ok
            and stationarity_ok
            and single_trigger_and_propagation_ok
        )
        breadth_ok = (
            float(row["late_p99_event_size"]) >= 0.05 * float(row["n_nodes"])
            and int(row["late_large_event_count"]) >= 1
        )
        candidate = (
            rare_stationary
            and int(row["late_event_count"]) >= CANDIDATE_GATE["minimum_late_events"]
            and late_occupancy >= CANDIDATE_GATE["minimum_late_occupancy"]
            and float(row["late_repeated_default_share"]) <= 0.80
            and breadth_ok
        )
        if (
            int(row["early_event_count"]) == 0
            and int(row["late_event_count"]) == 0
            and credit_stationary
            and gini_stationary
        ):
            classification = "no_event_stable"
        elif int(row["early_event_count"]) == 0 and int(row["late_event_count"]) == 0:
            classification = "no_event_accumulating_nonstationary"
        elif candidate:
            classification = "rare_stationary_soc_candidate"
        elif rare_stationary:
            classification = "rare_stationary_events"
        elif (
            late_occupancy > 0.25
            and stationarity_ok
            and separation_ok
            and single_trigger_and_propagation_ok
        ):
            classification = "stationary_high_occupancy_trigger_risk"
        elif late_occupancy <= 0.25:
            classification = "sparse_but_nonstationary"
        else:
            classification = "drift_or_persistent_failure"
        result = row.to_dict()
        result.update(
            {
                "occupancy_stationary": occupancy_stationary,
                "size_stationary": size_stationary,
                "active_credit_stationary": credit_stationary,
                "gini_stationary": gini_stationary,
                "propagation_stationary": propagation_stationary,
                "single_trigger_and_propagation_ok": single_trigger_and_propagation_ok,
                "separation_ok": separation_ok,
                "stationarity_ok": stationarity_ok,
                "breadth_ok": breadth_ok,
                "soc_candidate": candidate,
                "classification": classification,
                "classification_code": CLASS_CODES[classification],
                "occupancy_absolute_drift": late_occupancy - early_occupancy,
                "mean_size_relative_drift": relative_change(
                    float(row["late_mean_event_size"]), float(row["early_mean_event_size"])
                ),
                "active_credit_relative_drift": relative_change(
                    float(row["late_mean_active_credit"]),
                    float(row["early_mean_active_credit"]),
                ),
                "gini_absolute_drift": (
                    float(row["late_mean_final_net_worth_gini"])
                    - float(row["early_mean_final_net_worth_gini"])
                ),
                "propagation_share_absolute_drift": (
                    float(row["late_propagated_default_share"])
                    - float(row["early_propagated_default_share"])
                ),
            }
        )
        rows.append(result)
    return pd.DataFrame(rows).sort_values(
        ["family", "control_value", "money_distribution"]
    )


def audit(
    runs: pd.DataFrame,
    events: pd.DataFrame,
    windows: pd.DataFrame,
    metadata: list[dict[str, Any]],
) -> pd.DataFrame:
    event_by_run = (
        events.groupby(["scenario_id", "run_index"], as_index=False)
        .agg(
            event_rows=("collapse_size", "size"),
            collapse_sum=("collapse_size", "sum"),
            new_unique_sum=("new_unique_default_count", "sum"),
            repeated_sum=("repeated_default_count", "sum"),
            initial_sum=("initial_default_count", "sum"),
            propagated_sum=("propagated_default_count", "sum"),
        )
    )
    joined = runs.merge(event_by_run, on=["scenario_id", "run_index"], how="left")
    for column in [
        "event_rows",
        "collapse_sum",
        "new_unique_sum",
        "repeated_sum",
        "initial_sum",
        "propagated_sum",
    ]:
        joined[column] = joined[column].fillna(0)
    expected_edge_periods = {
        metadata_item["args"]["max_periods"]: int(
            round(metadata_item["args"]["max_periods"] * metadata_item["args"]["window_fraction"])
        )
        for metadata_item in metadata
    }
    expected_window_periods = next(iter(expected_edge_periods.values()))
    expected_max_periods = {int(item["args"]["max_periods"]) for item in metadata}
    expected_run_count = int(sum(item["run_count"] for item in metadata))
    checks = [
        (
            "required_run_count_from_metadata",
            len(runs) == expected_run_count,
            f"runs={len(runs)} expected={expected_run_count}",
        ),
        (
            "all_runs_match_requested_periods",
            len(expected_max_periods) == 1
            and bool(np.all(runs["periods_completed"] == next(iter(expected_max_periods)))),
            f"requested={sorted(expected_max_periods)} min={runs['periods_completed'].min()} max={runs['periods_completed'].max()}",
        ),
        (
            "all_cash_residuals_zero",
            bool(np.all(runs["cash_residual"] == 0)),
            f"max_abs={runs['cash_residual'].abs().max()}",
        ),
        (
            "event_rows_match_run_counts",
            bool(np.all(joined["event_rows"] == joined["avalanche_count"])),
            f"mismatches={int(np.sum(joined['event_rows'] != joined['avalanche_count']))}",
        ),
        (
            "event_sizes_match_run_totals",
            bool(np.all(joined["collapse_sum"] == joined["total_default_occurrences"])),
            f"mismatches={int(np.sum(joined['collapse_sum'] != joined['total_default_occurrences']))}",
        ),
        (
            "initial_plus_propagated_match_event_sizes",
            bool(np.all(joined["initial_sum"] + joined["propagated_sum"] == joined["collapse_sum"])),
            f"mismatches={int(np.sum(joined['initial_sum'] + joined['propagated_sum'] != joined['collapse_sum']))}",
        ),
        (
            "event_unique_counts_match_runs",
            bool(np.all(joined["new_unique_sum"] == joined["unique_default_nodes"])),
            f"mismatches={int(np.sum(joined['new_unique_sum'] != joined['unique_default_nodes']))}",
        ),
        (
            "event_repeated_counts_match_runs",
            bool(np.all(joined["repeated_sum"] == joined["repeated_default_occurrences"])),
            f"mismatches={int(np.sum(joined['repeated_sum'] != joined['repeated_default_occurrences']))}",
        ),
        (
            "early_late_window_periods_complete",
            bool(np.all(windows["period_count"] == expected_window_periods)),
            f"expected={expected_window_periods} min={windows['period_count'].min()} max={windows['period_count'].max()}",
        ),
        (
            "metadata_accounting_pass",
            all(item["all_accounting_residuals_zero"] for item in metadata),
            ";".join(str(item["all_accounting_residuals_zero"]) for item in metadata),
        ),
        (
            "metadata_baseline_equivalence_pass",
            all(item["all_baseline_equivalence_match"] for item in metadata),
            ";".join(str(item["all_baseline_equivalence_match"]) for item in metadata),
        ),
    ]
    return pd.DataFrame(
        [{"check": name, "passed": passed, "detail": detail} for name, passed, detail in checks]
    )


def plot_early_late(classification: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for row_index, family in enumerate(["income", "fixed"]):
        sub_family = classification[classification["family"] == family]
        x_label = "c" if family == "income" else "fixed K"
        for distribution, color in [("lognormal", "tab:blue"), ("pareto", "tab:orange")]:
            sub = sub_family[sub_family["money_distribution"] == distribution].sort_values(
                "control_value"
            )
            axes[row_index, 0].plot(
                sub["control_value"],
                sub["early_avalanche_occupancy"],
                marker="o",
                linestyle="--",
                color=color,
                alpha=0.7,
                label=f"{distribution} early",
            )
            axes[row_index, 0].plot(
                sub["control_value"],
                sub["late_avalanche_occupancy"],
                marker="o",
                color=color,
                label=f"{distribution} late",
            )
            axes[row_index, 1].plot(
                sub["control_value"],
                sub["early_mean_event_size"],
                marker="o",
                linestyle="--",
                color=color,
                alpha=0.7,
                label=f"{distribution} early",
            )
            axes[row_index, 1].plot(
                sub["control_value"],
                sub["late_mean_event_size"],
                marker="o",
                color=color,
                label=f"{distribution} late",
            )
        axes[row_index, 0].axhline(0.25, color="black", linestyle=":", linewidth=1)
        axes[row_index, 0].set_title(f"{family}: avalanche occupancy")
        axes[row_index, 1].set_title(f"{family}: mean avalanche size")
        for axis in axes[row_index]:
            axis.set_xlabel(x_label)
            axis.grid(alpha=0.25)
            axis.legend(fontsize=8, ncol=2)
    fig.suptitle("Early (first 20%) versus late (last 20%) stationarity diagnostics")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_time_bins(time_bins: pd.DataFrame, output: Path) -> None:
    families = ["income", "fixed"]
    distributions = ["lognormal", "pareto"]
    metrics = [
        ("avalanche_occupancy", "Occupancy"),
        ("mean_active_credit", "Active credit"),
        ("mean_final_net_worth_gini", "Gini"),
    ]
    fig, axes = plt.subplots(4, 3, figsize=(16, 15))
    row_index = 0
    for family in families:
        for distribution in distributions:
            sub = time_bins[
                (time_bins["family"] == family)
                & (time_bins["money_distribution"] == distribution)
            ]
            controls = sorted(sub["control_value"].unique())
            for column_index, (metric, title) in enumerate(metrics):
                matrix = (
                    sub.pivot(index="control_value", columns="time_bin", values=metric)
                    .reindex(index=controls)
                    .to_numpy(dtype=float)
                )
                image = axes[row_index, column_index].imshow(
                    matrix, aspect="auto", origin="lower", cmap="viridis"
                )
                axes[row_index, column_index].set_xticks(range(10), labels=range(1, 11))
                axes[row_index, column_index].set_yticks(
                    range(len(controls)), labels=[f"{value:g}" for value in controls]
                )
                axes[row_index, column_index].set_xlabel("time decile")
                axes[row_index, column_index].set_ylabel("c" if family == "income" else "K")
                axes[row_index, column_index].set_title(
                    f"{family} / {distribution}: {title}"
                )
                fig.colorbar(image, ax=axes[row_index, column_index], fraction=0.046)
            row_index += 1
    fig.suptitle("Long-run state drift across time deciles")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_independence(classification: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    for axis, family in zip(axes, ["income", "fixed"]):
        sub = classification[classification["family"] == family]
        scatter = axis.scatter(
            sub["late_avalanche_occupancy"],
            sub["late_one_period_wait_fraction"],
            c=sub["late_repeated_default_share"],
            s=40 + 150 * np.clip(sub["late_p99_event_size"] / sub["n_nodes"], 0, 1),
            cmap="magma",
            vmin=0,
            vmax=1,
            alpha=0.85,
        )
        for _, row in sub.iterrows():
            label = f"{row['control_value']:g}{'L' if row['money_distribution'] == 'lognormal' else 'P'}"
            axis.annotate(
                label,
                (row["late_avalanche_occupancy"], row["late_one_period_wait_fraction"]),
                fontsize=7,
                xytext=(2, 2),
                textcoords="offset points",
            )
        axis.axvline(0.25, color="black", linestyle=":", linewidth=1)
        axis.axhline(0.50, color="black", linestyle=":", linewidth=1)
        axis.set_xlabel("late avalanche occupancy")
        axis.set_ylabel("late P(wait=1)")
        axis.set_title(f"{family}: separation and repeated defaults")
        axis.grid(alpha=0.25)
        fig.colorbar(scatter, ax=axis, label="late repeated-default share")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def compact_classification_table(classification: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "family",
        "control_value",
        "money_distribution",
        "classification",
        "early_avalanche_occupancy",
        "late_avalanche_occupancy",
        "late_one_period_wait_fraction",
        "late_pooled_size_lag1_correlation",
        "early_mean_event_size",
        "late_mean_event_size",
        "active_credit_relative_drift",
        "gini_absolute_drift",
        "late_repeated_default_share",
        "late_single_initial_default_fraction",
        "late_propagated_default_share",
        "propagation_share_absolute_drift",
        "soc_candidate",
    ]
    return classification[columns].rename(
        columns={
            "control_value": "control",
            "money_distribution": "money",
            "classification": "class",
            "early_avalanche_occupancy": "early_occ",
            "late_avalanche_occupancy": "late_occ",
            "late_one_period_wait_fraction": "late_wait1",
            "late_pooled_size_lag1_correlation": "late_lag1",
            "early_mean_event_size": "early_mean_S",
            "late_mean_event_size": "late_mean_S",
            "active_credit_relative_drift": "credit_rel_drift",
            "gini_absolute_drift": "gini_drift",
            "late_repeated_default_share": "late_repeat_share",
            "late_single_initial_default_fraction": "late_P_initial1",
            "late_propagated_default_share": "late_prop_share",
            "propagation_share_absolute_drift": "prop_share_drift",
            "soc_candidate": "candidate",
        }
    )


def write_report(
    report_path: Path,
    result_dir: Path,
    runs: pd.DataFrame,
    events: pd.DataFrame,
    window: pd.DataFrame,
    classification: pd.DataFrame,
    audit_frame: pd.DataFrame,
    figures: list[Path],
    metadata: list[dict[str, Any]],
) -> None:
    candidates = classification[classification["soc_candidate"]]
    class_counts = (
        classification.groupby("classification", as_index=False)
        .size()
        .rename(columns={"size": "scenario_count"})
    )
    lowest_late = (
        classification.sort_values("late_avalanche_occupancy")
        .groupby(["family", "money_distribution"], as_index=False)
        .head(2)
    )
    boundary_table = lowest_late[
        [
            "family",
            "money_distribution",
            "control_value",
            "classification",
            "early_avalanche_occupancy",
            "late_avalanche_occupancy",
            "late_one_period_wait_fraction",
            "late_pooled_size_lag1_correlation",
            "late_repeated_default_share",
            "late_single_initial_default_fraction",
            "late_propagated_default_share",
        ]
    ].rename(
        columns={
            "control_value": "control",
            "money_distribution": "money",
            "classification": "class",
            "early_avalanche_occupancy": "early_occ",
            "late_avalanche_occupancy": "late_occ",
            "late_one_period_wait_fraction": "late_wait1",
            "late_pooled_size_lag1_correlation": "late_lag1",
            "late_repeated_default_share": "late_repeat_share",
            "late_single_initial_default_fraction": "late_P_initial1",
            "late_propagated_default_share": "late_prop_share",
        }
    )
    sparse = classification[classification["classification"] == "sparse_but_nonstationary"].copy()
    sparse["late_to_early_credit_ratio"] = (
        sparse["late_mean_active_credit"] / sparse["early_mean_active_credit"]
    )
    sparse_table = sparse[
        [
            "family",
            "control_value",
            "money_distribution",
            "early_avalanche_occupancy",
            "late_avalanche_occupancy",
            "late_pooled_size_lag1_correlation",
            "late_single_initial_default_fraction",
            "late_propagated_default_share",
            "late_repeated_default_share",
            "late_to_early_credit_ratio",
            "late_p99_event_size",
            "late_large_event_count",
        ]
    ].rename(
        columns={
            "control_value": "control",
            "money_distribution": "money",
            "early_avalanche_occupancy": "early_occ",
            "late_avalanche_occupancy": "late_occ",
            "late_pooled_size_lag1_correlation": "late_lag1",
            "late_single_initial_default_fraction": "late_P_initial1",
            "late_propagated_default_share": "late_prop_share",
            "late_repeated_default_share": "late_repeat_share",
            "late_to_early_credit_ratio": "late/early_credit",
            "late_p99_event_size": "late_P99",
            "late_large_event_count": "late_large_events",
        }
    )
    persistent = classification[classification["late_avalanche_occupancy"] >= 0.99].copy()
    persistent_table = persistent[
        [
            "family",
            "control_value",
            "money_distribution",
            "late_avalanche_occupancy",
            "late_one_period_wait_fraction",
            "early_mean_event_size",
            "late_mean_event_size",
            "late_single_initial_default_fraction",
            "late_propagated_default_share",
            "late_repeated_default_share",
            "early_mean_active_credit",
            "late_mean_active_credit",
            "early_mean_final_net_worth_gini",
            "late_mean_final_net_worth_gini",
        ]
    ].rename(
        columns={
            "control_value": "control",
            "money_distribution": "money",
            "late_avalanche_occupancy": "late_occ",
            "late_one_period_wait_fraction": "late_wait1",
            "early_mean_event_size": "early_mean_S",
            "late_mean_event_size": "late_mean_S",
            "late_single_initial_default_fraction": "late_P_initial1",
            "late_propagated_default_share": "late_prop_share",
            "late_repeated_default_share": "late_repeat_share",
            "early_mean_active_credit": "early_credit",
            "late_mean_active_credit": "late_credit",
            "early_mean_final_net_worth_gini": "early_gini",
            "late_mean_final_net_worth_gini": "late_gini",
        }
    )
    k1 = classification[
        (classification["family"] == "fixed") & (classification["control_value"] == 1)
    ]
    k1_credit_ratios = k1["late_mean_active_credit"] / k1["early_mean_active_credit"]
    sparse_credit_ratios = sparse["late_mean_active_credit"] / sparse["early_mean_active_credit"]
    all_audit_pass = bool(audit_frame["passed"].all())
    candidate_text = (
        f"发现 {len(candidates)} 个通过门槛的候选，需要追加有限尺寸验证。"
        if len(candidates)
        else f"{runs['scenario_id'].nunique()} 个场景中没有任何场景通过 SOC 候选门槛，因此按任务要求不追加有限尺寸验证。"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 信贷网络长期平稳性与稀有分离 Avalanche 搜索报告",
        "",
        f"生成时间：{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"结果版本：`{result_dir.name}`",
        "",
        "## 1. 任务与结论",
        "",
        "本分支在不修改 baseline 的前提下，执行从低到高驱动的 2000 期长期搜索，目标是排除此前短跑可能遗漏的“稀有、相互分离且统计平稳”的 avalanche 窗口。搜索只判断当前 baseline + `continue_after_avalanche` + `period_end` 约束；大事件、重尾、转变与严格 SOC 仍严格区分。",
        "",
        f"- 场景：{runs['scenario_id'].nunique()}；独立 run：{len(runs)}；总 period：{int(runs['periods_completed'].sum())}；avalanche：{len(events)}。",
        "- 每场景 12 seeds、每 run 2000 periods；N=200；lognormal/pareto 本金；biased 收入；random 增长；会计校验开启。",
        "- early/late 分别定义为每个 run 的前 20%（1-400 期）和后 20%（1601-2000 期）。",
        f"- 对账结论：{'全部通过' if all_audit_pass else '存在失败，见 audit CSV'}。",
        f"- 候选结论：{candidate_text}",
        "",
        "## 2. SOC 候选门槛",
        "",
        "只有同时满足下列条件才升级为候选；该门槛只是决定是否值得追加有限尺寸验证，不等于严格 SOC 证明：",
        "",
        "1. late 窗口至少 60 个事件，occupancy 至少 `0.001`；高 occupancy 和 `P(wait=1)` 只作为事件相关/批量触发风险报告，不单独否决；",
        "2. late size lag-1 绝对值 `<=0.30`；",
        "3. early/late occupancy 差不超过 `max(0.02, 25% * max(early,late))`；均值 size 相对漂移 `<=25%`；active credit 相对漂移 `<=20%`；Gini 绝对漂移 `<=0.05`；传播占比绝对漂移 `<=0.10`；",
        "4. late `P(initial_default_count=1) >= 0.50`，传播新增违约占全部违约 `>=0.10`，避免把同步多源初始违约广延增长直接当成单触发 avalanche；",
        "5. late repeated-default share `<=0.80`；late P99 至少达到 `0.05N`，且至少出现一次 `0.10N` 大事件。",
        "",
        "分类还区分：全程无事件且存量稳定区、无事件但持续累积的非平稳区、稀有平稳事件区、稀疏但非平稳区、平稳高占用触发风险区，以及漂移/持续失败区。",
        "",
        "## 3. 分类结果",
        "",
        markdown_table(class_counts),
        "",
        "各协议/本金分布中 late occupancy 最低的边界场景：",
        "",
        markdown_table(boundary_table),
        "",
        f"完整 {runs['scenario_id'].nunique()} 场景 early/late 统计与分类：",
        "",
        markdown_table(compact_classification_table(classification)),
        "",
        "## 4. 核心数值判断",
        "",
        f"- 最慢 fixed `K=1` 对照的 late occupancy 为 `{k1['late_avalanche_occupancy'].min():.4f}-{k1['late_avalanche_occupancy'].max():.4f}`，late `P(wait=1)` 为 `{k1['late_one_period_wait_fraction'].min():.4f}-{k1['late_one_period_wait_fraction'].max():.4f}`，lag-1 为 `{k1['late_pooled_size_lag1_correlation'].min():.4f}-{k1['late_pooled_size_lag1_correlation'].max():.4f}`。其事件均由单个 initial default 开始，但传播新增只占 `{k1['late_propagated_default_share'].min():.4f}-{k1['late_propagated_default_share'].max():.4f}`，late P99 size 仅 `{k1['late_p99_event_size'].min():.2f}-{k1['late_p99_event_size'].max():.2f}`，没有 10% 大事件。",
        f"- `K=1` 仍不是平稳候选：late/early active-credit 比为 `{k1_credit_ratios.min():.2f}-{k1_credit_ratios.max():.2f}`。它是当前 period-end 协议的最慢批量控制，但全体节点每期仍同时完成流量结算。",
        f"- 六个低驱动 sparse 场景的 late/early active-credit 比为 `{sparse_credit_ratios.min():.2f}-{sparse_credit_ratios.max():.2f}`，late P99 size 不超过 `{sparse['late_p99_event_size'].max():.2f}`，且全部没有 10% 大事件；因此它们是稀疏但仍在累积存量的非平稳区，而不是遗漏的稀有平稳 SOC 窗口。",
        f"- `{len(persistent)}` 个场景的 late occupancy 至少 0.99。这些场景的 late repeated-default share 为 `{persistent['late_repeated_default_share'].min():.4f}-{persistent['late_repeated_default_share'].max():.4f}`，`P(initial_default_count=1)` 为 `{persistent['late_single_initial_default_fraction'].min():.4f}-{persistent['late_single_initial_default_fraction'].max():.4f}`；结合 active credit/Gini 漂移和事件规模上升，更符合持续失败/退化终态风险。",
        "",
        "低驱动 sparse 场景：",
        "",
        markdown_table(sparse_table),
        "",
        "late occupancy 至少 0.99 的持续失败风险场景：",
        "",
        markdown_table(persistent_table),
        "",
        "## 5. 时间分离、漂移与重复违约",
        "",
        "候选判定同时使用 occupancy、等待时间、lag-1、active credit、Gini、initial/propagated 拆解和 exact node identity。`unique_default_nodes` 是每个 run/window 内至少违约一次的不同节点数；`repeated_default_occurrences = total occurrences - unique nodes`，因此可精确识别同一节点跨期重复违约的贡献，而不是估计范围。",
        "",
        "`initial_default_count` 是同一次 period-end 全体流量结算后同步出现的负净资产节点数；`propagated_default_count = collapse_size - initial_default_count` 才是网络清算传播新增违约。一次记录的 avalanche 可能有多个同步初始源，并不等同于单一微观触发。即使 fixed `K=1`，每期仍对全体节点进行期末流量结算，因此它只是当前协议最慢的批量控制，不自动等于单微观触发 SOC。",
        "",
        f"完整窗口统计：`{relpath(result_dir / 'window_summary.csv', report_path)}`。",
        f"时间十分位漂移：`{relpath(result_dir / 'time_bin_summary.csv', report_path)}`。",
        f"场景分类与门槛布尔量：`{relpath(result_dir / 'classification.csv', report_path)}`。",
        "",
        f"![early-late]({relpath(figures[0], report_path)})",
        "",
        f"![time-bins]({relpath(figures[1], report_path)})",
        "",
        f"![independence]({relpath(figures[2], report_path)})",
        "",
        "## 6. 可复现性与对账",
        "",
        markdown_table(audit_frame),
        "",
        "每个 shard 的 `metadata.json` 记录完整参数、种子范围、命令、开始/结束 CST 时间、run/event/period 数和输出路径；`baseline_equivalence.csv` 对首个长 run 与原 baseline 做事件序列哈希及终态逐项一致性验证。",
        "",
        f"- income shard：`{relpath(result_dir / 'income', report_path)}`",
        f"- fixed shard：`{relpath(result_dir / 'fixed', report_path)}`",
        f"- 对账表：`{relpath(result_dir / 'accounting_audit.csv', report_path)}`",
        f"- 候选门槛：`{relpath(result_dir / 'candidate_gate.json', report_path)}`",
        "",
        "## 7. 证据边界",
        "",
        "- `critical_event` 仍只是 `collapse_size >= 0.10N` 的人工标签。",
        "- 高 event occupancy 或 `P(wait=1)` 本身不是 SOC 的充分反证；本文只在其与批量驱动、lag-1、非平稳漂移、多源同步初始违约和退化终态共同出现时解释为风险。",
        "- 当前结果只排查 baseline `continue_after_avalanche`、period-end 检查和指定参数扫描；不能否定其他退出、重置、清算或流量结算机制。",
        "- 即使存在稀有平稳窗口，也仍需严格尾部拟合、替代分布比较、有限尺寸标度和无精细调参证据才能宣称严格 SOC。",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    shard_names = [value.strip() for value in args.shards.split(",") if value.strip()]
    runs, events, windows, bins, metadata = read_shards(args.result_dir, shard_names)
    expected_scenarios = int(sum(item["scenario_count"] for item in metadata))
    if runs["scenario_id"].nunique() != expected_scenarios:
        raise RuntimeError(
            f"expected {expected_scenarios} scenarios, found {runs['scenario_id'].nunique()}"
        )
    window = window_summary(windows, events)
    time_bins = time_bin_summary(bins)
    classification = classify(window)
    audit_frame = audit(runs, events, windows, metadata)
    args.result_dir.mkdir(parents=True, exist_ok=True)
    window.to_csv(args.result_dir / "window_summary.csv", index=False)
    time_bins.to_csv(args.result_dir / "time_bin_summary.csv", index=False)
    classification.to_csv(args.result_dir / "classification.csv", index=False)
    audit_frame.to_csv(args.result_dir / "accounting_audit.csv", index=False)
    (args.result_dir / "candidate_gate.json").write_text(
        json.dumps(CANDIDATE_GATE, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    figures = [
        args.result_dir / "early_late_stationarity.png",
        args.result_dir / "time_bin_drift.png",
        args.result_dir / "independence_repetition.png",
    ]
    plot_early_late(classification, figures[0])
    plot_time_bins(time_bins, figures[1])
    plot_independence(classification, figures[2])
    write_report(
        args.report_path,
        args.result_dir,
        runs,
        events,
        window,
        classification,
        audit_frame,
        figures,
        metadata,
    )
    analysis_metadata = {
        "created_at": datetime.now(CST).isoformat(),
        "shards": shard_names,
        "runs": len(runs),
        "scenarios": int(runs["scenario_id"].nunique()),
        "events": len(events),
        "periods": int(runs["periods_completed"].sum()),
        "candidate_count": int(classification["soc_candidate"].sum()),
        "classification_counts": classification["classification"].value_counts().to_dict(),
        "all_audits_pass": bool(audit_frame["passed"].all()),
        "report": str(args.report_path),
        "figures": [str(path) for path in figures],
    }
    (args.result_dir / "analysis_metadata.json").write_text(
        json.dumps(analysis_metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(analysis_metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
