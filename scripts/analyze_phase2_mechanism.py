#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError


CST = ZoneInfo("Asia/Shanghai")
MECHANISM_ORDER = [
    "reference_period_end",
    "check_only_b10",
    "flow_split_b10_check_q10",
    "flow_split_b10_check_q5",
    "flow_split_b10_check_q2",
    "flow_split_b10_check_q1",
    "recovery_50pct",
    "recovery_90pct",
    "keep_defaulted_assets",
    "permanent_exit",
    "reset_to_initial_cash",
]
PROTOCOL_ORDER = ["high_risk_income_c020", "boundary_fixed_k20"]


def timestamp() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze phase-2 mechanism ablations.")
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--thresholds", nargs="+", type=float, default=[0.05, 0.10, 0.20])
    return parser.parse_args()


def markdown_table(df: pd.DataFrame, digits: int = 3) -> str:
    def fmt(value: object) -> str:
        if isinstance(value, (float, np.floating)):
            return f"{float(value):.{digits}f}"
        return str(value)

    columns = list(df.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(fmt(row[column]) for column in columns) + " |")
    return "\n".join(lines)


def estimate_tail(values: np.ndarray, xmin: int) -> dict[str, float | int | None]:
    tail = values[values >= xmin].astype(float)
    if tail.size < 5:
        return {"xmin": xmin, "tail_n": int(tail.size), "alpha_continuous": None}
    denominator = float(np.sum(np.log(tail / max(xmin - 0.5, 1e-9))))
    alpha = 1.0 + tail.size / denominator if denominator > 0 else None
    return {
        "xmin": xmin,
        "tail_n": int(tail.size),
        "alpha_continuous": float(alpha) if alpha is not None else None,
    }


def aggregate_results(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    run_summary = (
        runs.groupby(["protocol_id", "mechanism_id", "scenario_id"], sort=False)
        .agg(
            runs=("seed", "count"),
            default_run_rate=("ended_by_default", "mean"),
            run_critical_rate_10pct=("critical_event", "mean"),
            mean_avalanche_count=("avalanche_count", "mean"),
            mean_avalanche_active_macro_rate=("avalanche_active_macro_rate", "mean"),
            mean_max_collapse=("max_collapse_size", "mean"),
            mean_total_collapse=("total_collapse_size", "mean"),
            mean_unique_default_nodes=("unique_default_nodes", "mean"),
            mean_repeat_default_occurrences=("repeat_default_occurrences", "mean"),
            mean_repeat_default_share=("repeat_default_share", "mean"),
            mean_total_credit_issued=("total_credit_issued", "mean"),
            mean_final_active_credit=("final_active_credit", "mean"),
            mean_active_credit_after_settlement=("mean_active_credit_after_settlement", "mean"),
            mean_final_active_nodes=("final_active_nodes", "mean"),
            mean_creditor_loss=("total_creditor_loss", "mean"),
            mean_actual_recovery=("total_actual_recovery", "mean"),
            mean_external_reset_cash_flow=("external_reset_cash_flow", "mean"),
            mean_final_gini=("final_net_worth_gini", "mean"),
            capped_macro_periods=("capped_macro_periods", "sum"),
        )
        .reset_index()
    )
    if events.empty:
        for column in [
            "events",
            "event_critical_rate_10pct",
            "mean_event_size",
            "median_event_size",
            "p90_event_size",
            "max_event_size",
            "mean_credit_before_event",
            "mean_credit_after_event",
            "repeat_nodes_in_events",
        ]:
            run_summary[column] = 0.0
        return run_summary

    event_summary = (
        events.groupby(["protocol_id", "mechanism_id", "scenario_id"], sort=False)
        .agg(
            events=("collapse_size", "count"),
            event_critical_rate_10pct=("critical_event", "mean"),
            mean_event_size=("collapse_size", "mean"),
            median_event_size=("collapse_size", "median"),
            p90_event_size=("collapse_size", lambda values: values.quantile(0.90)),
            max_event_size=("collapse_size", "max"),
            mean_credit_before_event=("credit_scale_before_cascade", "mean"),
            mean_credit_after_event=("active_credit_after_cascade", "mean"),
            repeat_nodes_in_events=("repeat_default_nodes", "sum"),
        )
        .reset_index()
    )
    return run_summary.merge(
        event_summary,
        on=["protocol_id", "mechanism_id", "scenario_id"],
        how="left",
    ).fillna(0)


def threshold_sensitivity(
    runs: pd.DataFrame,
    events: pd.DataFrame,
    thresholds: list[float],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (protocol_id, mechanism_id, scenario_id), run_sub in runs.groupby(
        ["protocol_id", "mechanism_id", "scenario_id"], sort=False
    ):
        event_sub = events.loc[events["scenario_id"] == scenario_id] if not events.empty else events
        for threshold in thresholds:
            event_hits = (
                event_sub["collapse_fraction"] >= threshold
                if not event_sub.empty
                else pd.Series(dtype=bool)
            )
            hit_runs = set(event_sub.loc[event_hits, "run_index"].astype(int).tolist())
            rows.append(
                {
                    "protocol_id": protocol_id,
                    "mechanism_id": mechanism_id,
                    "scenario_id": scenario_id,
                    "threshold_fraction": threshold,
                    "threshold_nodes": int(np.ceil(threshold * float(run_sub["n_nodes"].iloc[0]))),
                    "runs": len(run_sub),
                    "run_critical_rate": len(hit_runs) / len(run_sub) if len(run_sub) else 0.0,
                    "events": len(event_sub),
                    "critical_events": int(event_hits.sum()) if not event_sub.empty else 0,
                    "event_critical_rate": float(event_hits.mean()) if not event_sub.empty else 0.0,
                }
            )
    return pd.DataFrame(rows)


def tail_summary(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if events.empty:
        return pd.DataFrame(rows)
    for (protocol_id, mechanism_id, scenario_id), sub in events.groupby(
        ["protocol_id", "mechanism_id", "scenario_id"], sort=False
    ):
        values = sub["collapse_size"].to_numpy(dtype=float)
        for xmin in [2, 5]:
            rows.append(
                {
                    "protocol_id": protocol_id,
                    "mechanism_id": mechanism_id,
                    "scenario_id": scenario_id,
                    **estimate_tail(values, xmin),
                }
            )
    return pd.DataFrame(rows)


def build_posthoc_audit(runs: pd.DataFrame) -> dict[str, object]:
    comparison_keys = [
        "total_credit_issued",
        "avalanche_count",
        "max_collapse_size",
        "total_collapse_size",
        "unique_default_nodes",
        "repeat_default_occurrences",
        "final_active_credit",
        "final_cash_total",
        "final_net_worth_gini",
    ]
    negative_control: dict[str, object] = {}
    for protocol_id, sub in runs.groupby("protocol_id", sort=False):
        reference = (
            sub[sub["mechanism_id"] == "reference_period_end"]
            .sort_values("run_index")
            .reset_index(drop=True)
        )
        check_only = (
            sub[sub["mechanism_id"] == "check_only_b10"]
            .sort_values("run_index")
            .reset_index(drop=True)
        )
        negative_control[protocol_id] = {
            "paired_runs": int(len(reference)),
            "mismatches": {
                key: int(
                    (
                        reference[key].round(10).to_numpy()
                        != check_only[key].round(10).to_numpy()
                    ).sum()
                )
                for key in comparison_keys
            },
        }

    nonreset = runs[runs["default_node_mode"] != "reset"]
    reset = runs[runs["default_node_mode"] == "reset"]
    cap_usage = (
        runs.groupby(["protocol_id", "mechanism_id"], sort=False)
        .agg(
            capped_macro_periods=("capped_macro_periods", "sum"),
            max_capped_macro_periods_per_run=("capped_macro_periods", "max"),
        )
        .reset_index()
    )
    cap_usage = cap_usage[cap_usage["capped_macro_periods"] > 0]
    return {
        "negative_control": negative_control,
        "accounting_residuals": {
            "max_abs_nonreset_cash_residual": float(
                (nonreset["final_cash_total"] - nonreset["initial_total_money"]).abs().max()
            ),
            "max_abs_reset_cash_identity_residual": float(
                (
                    reset["final_cash_total"]
                    - reset["initial_total_money"]
                    - reset["external_reset_cash_flow"]
                )
                .abs()
                .max()
            ),
        },
        "nonzero_drive_cap_usage": [
            {
                "protocol_id": str(row.protocol_id),
                "mechanism_id": str(row.mechanism_id),
                "capped_macro_periods": int(row.capped_macro_periods),
                "max_capped_macro_periods_per_run": int(
                    row.max_capped_macro_periods_per_run
                ),
            }
            for row in cap_usage.itertuples(index=False)
        ],
    }


def temporal_diagnostics(
    runs: pd.DataFrame,
    events: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, object]] = []
    quartile_rows: list[dict[str, object]] = []

    for (protocol_id, mechanism_id, scenario_id), run_sub in runs.groupby(
        ["protocol_id", "mechanism_id", "scenario_id"], sort=False
    ):
        event_sub = events.loc[events["scenario_id"] == scenario_id].copy()
        if event_sub.empty:
            macro_events = pd.DataFrame(
                columns=["run_index", "macro_period", "collapse_size", "critical_event"]
            )
        else:
            macro_events = (
                event_sub.groupby(["run_index", "macro_period"], as_index=False)
                .agg(
                    collapse_size=("collapse_size", "max"),
                    critical_event=("critical_event", "max"),
                )
            )

        periods_by_run = run_sub.set_index("run_index")["macro_periods_completed"].to_dict()
        active_macro_count = len(macro_events)
        total_macro_count = int(run_sub["macro_periods_completed"].sum())
        waits: list[int] = []
        lag_x: list[float] = []
        lag_y: list[float] = []
        quartile_active = {quartile: 0 for quartile in range(1, 5)}
        quartile_total = {quartile: 0 for quartile in range(1, 5)}
        quartile_sizes = {quartile: [] for quartile in range(1, 5)}
        quartile_critical = {quartile: [] for quartile in range(1, 5)}
        final_window_macro_periods = 0
        final_window_active_periods = 0
        final_window_critical_periods = 0
        final_window_sizes: list[float] = []

        for run_index, periods in periods_by_run.items():
            periods = int(periods)
            final_window_start = max(1, int(np.floor(0.8 * periods)) + 1)
            final_window_macro_periods += periods - final_window_start + 1
            for period in range(1, periods + 1):
                quartile = min(4, ((period - 1) * 4) // max(periods, 1) + 1)
                quartile_total[quartile] += 1
            sequence = macro_events.loc[
                macro_events["run_index"] == run_index
            ].sort_values("macro_period")
            event_periods = sequence["macro_period"].to_numpy(dtype=int)
            sizes = sequence["collapse_size"].to_numpy(dtype=float)
            final_sequence = sequence[sequence["macro_period"] >= final_window_start]
            final_window_active_periods += len(final_sequence)
            final_window_critical_periods += int(final_sequence["critical_event"].sum())
            final_window_sizes.extend(final_sequence["collapse_size"].astype(float).tolist())
            waits.extend(np.diff(event_periods).astype(int).tolist())
            if sizes.size >= 2:
                lag_x.extend(sizes[:-1].tolist())
                lag_y.extend(sizes[1:].tolist())
            for _, event in sequence.iterrows():
                quartile = min(
                    4,
                    ((int(event["macro_period"]) - 1) * 4) // max(periods, 1) + 1,
                )
                quartile_active[quartile] += 1
                quartile_sizes[quartile].append(float(event["collapse_size"]))
                quartile_critical[quartile].append(bool(event["critical_event"]))

        lag_corr = (
            float(np.corrcoef(lag_x, lag_y)[0, 1])
            if len(lag_x) >= 3 and np.std(lag_x) > 0 and np.std(lag_y) > 0
            else np.nan
        )
        q1_mean = float(np.mean(quartile_sizes[1])) if quartile_sizes[1] else 0.0
        q4_mean = float(np.mean(quartile_sizes[4])) if quartile_sizes[4] else 0.0
        summary_rows.append(
            {
                "protocol_id": protocol_id,
                "mechanism_id": mechanism_id,
                "scenario_id": scenario_id,
                "active_macro_periods": active_macro_count,
                "total_macro_periods": total_macro_count,
                "avalanche_active_macro_rate": (
                    active_macro_count / total_macro_count if total_macro_count else 0.0
                ),
                "wait_intervals": len(waits),
                "wait_one_share": (
                    float(np.mean(np.asarray(waits) == 1)) if waits else 0.0
                ),
                "macro_event_size_lag1_corr": lag_corr,
                "q1_mean_macro_event_size": q1_mean,
                "q4_mean_macro_event_size": q4_mean,
                "q4_to_q1_mean_size_ratio": q4_mean / q1_mean if q1_mean > 0 else np.nan,
                "q1_macro_critical_rate": (
                    float(np.mean(quartile_critical[1])) if quartile_critical[1] else 0.0
                ),
                "q4_macro_critical_rate": (
                    float(np.mean(quartile_critical[4])) if quartile_critical[4] else 0.0
                ),
                "final_20pct_avalanche_active_rate": (
                    final_window_active_periods / final_window_macro_periods
                    if final_window_macro_periods
                    else 0.0
                ),
                "final_20pct_large_event_rate_per_macro": (
                    final_window_critical_periods / final_window_macro_periods
                    if final_window_macro_periods
                    else 0.0
                ),
                "final_20pct_mean_macro_event_size": (
                    float(np.mean(final_window_sizes)) if final_window_sizes else 0.0
                ),
            }
        )
        for quartile in range(1, 5):
            quartile_rows.append(
                {
                    "protocol_id": protocol_id,
                    "mechanism_id": mechanism_id,
                    "scenario_id": scenario_id,
                    "time_quartile": quartile,
                    "macro_periods": quartile_total[quartile],
                    "active_avalanche_macro_periods": quartile_active[quartile],
                    "avalanche_active_macro_rate": (
                        quartile_active[quartile] / quartile_total[quartile]
                        if quartile_total[quartile]
                        else 0.0
                    ),
                    "mean_macro_event_size": (
                        float(np.mean(quartile_sizes[quartile]))
                        if quartile_sizes[quartile]
                        else 0.0
                    ),
                    "macro_critical_rate": (
                        float(np.mean(quartile_critical[quartile]))
                        if quartile_critical[quartile]
                        else 0.0
                    ),
                }
            )
    return pd.DataFrame(summary_rows), pd.DataFrame(quartile_rows)


def plot_grouped_metric(
    summary: pd.DataFrame,
    mechanisms: list[str],
    metric: str,
    ylabel: str,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(max(10, len(mechanisms) * 0.9), 5.8))
    x = np.arange(len(mechanisms), dtype=float)
    width = 0.36
    for index, protocol_id in enumerate(PROTOCOL_ORDER):
        values = []
        for mechanism_id in mechanisms:
            match = summary[
                (summary["protocol_id"] == protocol_id)
                & (summary["mechanism_id"] == mechanism_id)
            ]
            values.append(float(match[metric].iloc[0]) if len(match) else 0.0)
        ax.bar(
            x + (index - 0.5) * width,
            values,
            width=width,
            label=protocol_id,
        )
    ax.set_xticks(x, mechanisms, rotation=35, ha="right")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_batch_decoupling(summary: pd.DataFrame, output_path: Path) -> None:
    mechanisms = [
        "reference_period_end",
        "check_only_b10",
        "flow_split_b10_check_q10",
        "flow_split_b10_check_q5",
        "flow_split_b10_check_q2",
        "flow_split_b10_check_q1",
    ]
    metrics = [
        ("run_critical_rate_10pct", "Run critical rate (>=10%)"),
        ("mean_event_size", "Mean event size"),
        ("mean_final_active_credit", "Mean final active credit"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.5))
    x = np.arange(len(mechanisms), dtype=float)
    width = 0.36
    for ax, (metric, ylabel) in zip(axes, metrics):
        for index, protocol_id in enumerate(PROTOCOL_ORDER):
            values = []
            for mechanism_id in mechanisms:
                match = summary[
                    (summary["protocol_id"] == protocol_id)
                    & (summary["mechanism_id"] == mechanism_id)
                ]
                values.append(float(match[metric].iloc[0]) if len(match) else 0.0)
            ax.bar(x + (index - 0.5) * width, values, width=width, label=protocol_id)
            ax.set_xticks(
                x,
                ["ref", "credit-check10", "flow-q10", "flow-q5", "flow-q2", "flow-q1"],
                rotation=25,
            )
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.suptitle("Credit-drive total held at macro start; settlement/check frequency varied")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_thresholds(sensitivity: pd.DataFrame, output_path: Path) -> None:
    selected = sensitivity[
        sensitivity["mechanism_id"].isin(
            [
                "reference_period_end",
                "flow_split_b10_check_q1",
                "permanent_exit",
                "reset_to_initial_cash",
                "recovery_90pct",
            ]
        )
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.3), sharey=True)
    for ax, protocol_id in zip(axes, PROTOCOL_ORDER):
        sub = selected[selected["protocol_id"] == protocol_id]
        for mechanism_id, group in sub.groupby("mechanism_id", sort=False):
            group = group.sort_values("threshold_fraction")
            ax.plot(
                group["threshold_fraction"],
                group["run_critical_rate"],
                marker="o",
                label=mechanism_id,
            )
        ax.set_title(protocol_id)
        ax.set_xlabel("Collapse threshold fraction")
        ax.set_ylabel("Run critical-event rate")
        ax.grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_selected_ccdf(events: pd.DataFrame, output_path: Path) -> None:
    selected = events[
        events["mechanism_id"].isin(
            [
                "reference_period_end",
                "flow_split_b10_check_q1",
                "permanent_exit",
                "reset_to_initial_cash",
                "recovery_90pct",
            ]
        )
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.3), sharey=True)
    for ax, protocol_id in zip(axes, PROTOCOL_ORDER):
        sub = selected[selected["protocol_id"] == protocol_id]
        for mechanism_id, group in sub.groupby("mechanism_id", sort=False):
            sizes = np.sort(group["collapse_size"].to_numpy(dtype=float))
            sizes = sizes[sizes > 0]
            if sizes.size == 0:
                continue
            unique = np.unique(sizes)
            ccdf = np.array([(sizes >= value).mean() for value in unique])
            ax.loglog(unique, ccdf, marker="o", markersize=3, label=mechanism_id)
        ax.set_title(protocol_id)
        ax.set_xlabel("Avalanche size")
        ax.set_ylabel("CCDF P(S >= s)")
        ax.grid(which="both", alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_temporal_quartiles(quartiles: pd.DataFrame, output_path: Path) -> None:
    selected_mechanisms = [
        "reference_period_end",
        "flow_split_b10_check_q1",
        "recovery_90pct",
        "permanent_exit",
        "reset_to_initial_cash",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.3), sharey=False)
    for ax, protocol_id in zip(axes, PROTOCOL_ORDER):
        sub = quartiles[
            (quartiles["protocol_id"] == protocol_id)
            & (quartiles["mechanism_id"].isin(selected_mechanisms))
        ]
        for mechanism_id, group in sub.groupby("mechanism_id", sort=False):
            group = group.sort_values("time_quartile")
            ax.plot(
                group["time_quartile"],
                group["mean_macro_event_size"],
                marker="o",
                label=mechanism_id,
            )
        ax.set_title(protocol_id)
        ax.set_xlabel("Run-time quartile")
        ax.set_ylabel("Mean max avalanche size in active macro periods")
        ax.set_xticks([1, 2, 3, 4])
        ax.grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def write_analysis_summary(
    result_dir: Path,
    runs: pd.DataFrame,
    events: pd.DataFrame,
    summary: pd.DataFrame,
    sensitivity: pd.DataFrame,
    temporal: pd.DataFrame,
) -> None:
    compact = summary[
        [
            "protocol_id",
            "mechanism_id",
            "runs",
            "run_critical_rate_10pct",
            "events",
            "mean_event_size",
            "p90_event_size",
            "mean_final_active_credit",
            "mean_repeat_default_share",
            "mean_final_active_nodes",
        ]
    ].copy()
    threshold_compact = sensitivity[
        sensitivity["mechanism_id"].isin(
            [
                "reference_period_end",
                "flow_split_b10_check_q1",
                "permanent_exit",
                "reset_to_initial_cash",
                "recovery_90pct",
            ]
        )
    ][
        [
            "protocol_id",
            "mechanism_id",
            "threshold_fraction",
            "run_critical_rate",
            "event_critical_rate",
        ]
    ]
    temporal_compact = temporal[
        temporal["mechanism_id"].isin(
            [
                "reference_period_end",
                "flow_split_b10_check_q1",
                "recovery_90pct",
                "permanent_exit",
                "reset_to_initial_cash",
            ]
        )
    ][
        [
            "protocol_id",
            "mechanism_id",
            "avalanche_active_macro_rate",
            "wait_one_share",
            "macro_event_size_lag1_corr",
            "q1_mean_macro_event_size",
            "q4_mean_macro_event_size",
            "final_20pct_avalanche_active_rate",
            "final_20pct_large_event_rate_per_macro",
        ]
    ]
    lines = [
        "# Phase 2 机制稳健性消融分析摘要",
        "",
        f"生成时间：{timestamp()}",
        "",
        "## 口径",
        "",
        f"- Run 数：{len(runs)}；avalanche 事件数：{len(events)}。",
        "- `check_only_b10` 是可识别性负对照：拆分信贷驱动批次，但中间不结算流量。",
        "- `flow_split_b10_check_q10/q5/q2/q1` 固定为十次相同流量结算，只改变每隔多少次结算检查清算；这是纯检查频率对照。",
        "- `reference_period_end` 对比 `flow_split_b10_check_q10` 同时改变流量结算频率，必须视为收入/消费动态机制变化。",
        "- 回收率是从违约债务人现有现金支付的目标比例，受现金上限约束，不注入外部现金。",
        "- reset 会恢复节点的本轮初始现金，外部现金流单独记录，因此不能视为守恒机制。",
        "- 阈值敏感性只重分类同一批事件，不改变传播机制。",
        "",
        "## 场景汇总",
        "",
        markdown_table(compact),
        "",
        "## 大崩塌阈值敏感性",
        "",
        markdown_table(threshold_compact),
        "",
        "## 持续失效与非平稳性诊断",
        "",
        markdown_table(temporal_compact),
        "",
        "## 图表",
        "",
        "- `batch_decoupling.png`：信贷驱动总量与结算/检查频率解耦。",
        "- `clearing_mechanism_critical_rate.png`：各清算机制的 run 级大崩塌率。",
        "- `repeat_default_share.png`：重复违约占比。",
        "- `threshold_sensitivity.png`：大崩塌分类阈值敏感性。",
        "- `selected_mechanism_ccdf.png`：选定机制的事件规模 CCDF。",
        "- `temporal_quartile_event_size.png`：事件规模在运行时间四分位上的变化。",
        "",
        "连续 Pareto alpha 仅保留为重尾初筛，不构成严格 SOC 或幂律证明。",
        "",
    ]
    (result_dir / "analysis_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    runs = pd.read_csv(args.result_dir / "run_summary.csv")
    try:
        events = pd.read_csv(args.result_dir / "avalanche_events.csv")
    except EmptyDataError:
        events = pd.DataFrame()

    summary = aggregate_results(runs, events)
    summary.to_csv(args.result_dir / "scenario_summary.csv", index=False)
    sensitivity = threshold_sensitivity(runs, events, args.thresholds)
    sensitivity.to_csv(args.result_dir / "threshold_sensitivity.csv", index=False)
    tails = tail_summary(events)
    tails.to_csv(args.result_dir / "tail_screen.csv", index=False)
    temporal, temporal_quartiles = temporal_diagnostics(runs, events)
    temporal.to_csv(args.result_dir / "temporal_diagnostics.csv", index=False)
    temporal_quartiles.to_csv(args.result_dir / "temporal_quartiles.csv", index=False)
    posthoc_audit = build_posthoc_audit(runs)
    (args.result_dir / "posthoc_audit.json").write_text(
        json.dumps(
            {"created_at": timestamp(), **posthoc_audit},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    plot_batch_decoupling(summary, args.result_dir / "batch_decoupling.png")
    plot_grouped_metric(
        summary,
        MECHANISM_ORDER,
        "run_critical_rate_10pct",
        "Run critical-event rate (>=10%)",
        args.result_dir / "clearing_mechanism_critical_rate.png",
    )
    plot_grouped_metric(
        summary,
        MECHANISM_ORDER,
        "mean_repeat_default_share",
        "Mean repeated-default share",
        args.result_dir / "repeat_default_share.png",
    )
    plot_thresholds(sensitivity, args.result_dir / "threshold_sensitivity.png")
    if not events.empty:
        plot_selected_ccdf(events, args.result_dir / "selected_mechanism_ccdf.png")
        plot_temporal_quartiles(
            temporal_quartiles,
            args.result_dir / "temporal_quartile_event_size.png",
        )
    write_analysis_summary(args.result_dir, runs, events, summary, sensitivity, temporal)

    metadata = {
        "created_at": timestamp(),
        "result_dir": str(args.result_dir),
        "run_count": len(runs),
        "event_count": len(events),
        "thresholds": args.thresholds,
        "outputs": {
            "scenario_summary": str(args.result_dir / "scenario_summary.csv"),
            "threshold_sensitivity": str(args.result_dir / "threshold_sensitivity.csv"),
            "tail_screen": str(args.result_dir / "tail_screen.csv"),
            "temporal_diagnostics": str(args.result_dir / "temporal_diagnostics.csv"),
            "temporal_quartiles": str(args.result_dir / "temporal_quartiles.csv"),
            "posthoc_audit": str(args.result_dir / "posthoc_audit.json"),
            "analysis_summary": str(args.result_dir / "analysis_summary.md"),
        },
    }
    (args.result_dir / "analysis_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
