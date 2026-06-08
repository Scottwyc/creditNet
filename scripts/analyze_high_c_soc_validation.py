#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CST = ZoneInfo("Asia/Shanghai")
DEFAULT_RESCAN_ANALYSIS = ROOT / "results" / "credit_soc_high_c_rescan_analysis_20260605_v1"
DEFAULT_FINITE = ROOT / "results" / "credit_soc_high_c_finite_size_20260605_v1"
DEFAULT_STATIONARITY = ROOT / "results" / "credit_soc_high_c_stationarity_20260605_v1" / "income"
DEFAULT_OUTPUT = ROOT / "results" / "credit_soc_high_c_soc_validation_20260605_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build high-c SOC validation report.")
    parser.add_argument("--rescan-analysis-dir", type=Path, default=DEFAULT_RESCAN_ANALYSIS)
    parser.add_argument("--finite-dir", type=Path, default=DEFAULT_FINITE)
    parser.add_argument("--stationarity-dir", type=Path, default=DEFAULT_STATIONARITY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def stationarity_window_summary(stationarity_dir: Path) -> pd.DataFrame:
    windows = read_csv(stationarity_dir / "run_windows.csv")
    events = read_csv(stationarity_dir / "avalanche_events.csv")
    rows: list[dict[str, Any]] = []
    for keys, sub in windows.groupby(["scenario_id", "window"], sort=True):
        scenario_id, window = keys
        event_sub = events[events["scenario_id"].eq(scenario_id) & events["window"].eq(window)]
        periods = int(sub["period_count"].sum())
        event_count = int(sub["event_count"].sum())
        sizes = event_sub["collapse_size"].to_numpy(dtype=float)
        total_defaults = int(sub["total_default_occurrences_in_window"].sum())
        repeated_defaults = int(sub["repeated_default_occurrences_in_window"].sum())
        rows.append(
            {
                "scenario_id": scenario_id,
                "window": window,
                "c": float(sub["control_value"].iloc[0]),
                "money_distribution": sub["money_distribution"].iloc[0],
                "runs": int(len(sub)),
                "periods": periods,
                "events": event_count,
                "avalanche_occupancy": event_count / periods if periods else np.nan,
                "mean_event_size": float(np.mean(sizes)) if sizes.size else 0.0,
                "p99_event_size": float(np.quantile(sizes, 0.99)) if sizes.size else 0.0,
                "large_event_rate": float(event_sub["critical_event"].mean())
                if len(event_sub)
                else 0.0,
                "propagated_share": (
                    float(event_sub["propagated_default_count"].sum() / event_sub["collapse_size"].sum())
                    if len(event_sub) and float(event_sub["collapse_size"].sum()) > 0
                    else 0.0
                ),
                "single_initial_event_rate": float(event_sub["single_initial_default"].mean())
                if len(event_sub)
                else 0.0,
                "repeated_default_share": repeated_defaults / total_defaults
                if total_defaults
                else 0.0,
                "mean_active_credit": float(
                    (sub["mean_active_credit"] * sub["period_count"]).sum() / periods
                )
                if periods
                else 0.0,
                "mean_gini": float(
                    (sub["mean_final_net_worth_gini"] * sub["period_count"]).sum() / periods
                )
                if periods
                else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["money_distribution", "c", "window"])


def stationarity_pair_summary(window_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, sub in window_summary.groupby(["money_distribution", "c"], sort=True):
        distribution, c_value = keys
        early = sub[sub["window"].eq("early")]
        late = sub[sub["window"].eq("late")]
        if early.empty or late.empty:
            continue
        early_row = early.iloc[0]
        late_row = late.iloc[0]
        rows.append(
            {
                "money_distribution": distribution,
                "c": float(c_value),
                "early_occupancy": early_row["avalanche_occupancy"],
                "late_occupancy": late_row["avalanche_occupancy"],
                "late_wait_interpretation": "every_period"
                if late_row["avalanche_occupancy"] >= 0.99
                else "not_every_period",
                "early_mean_size": early_row["mean_event_size"],
                "late_mean_size": late_row["mean_event_size"],
                "late_over_early_mean_size": late_row["mean_event_size"]
                / early_row["mean_event_size"]
                if early_row["mean_event_size"] > 0
                else np.nan,
                "late_large_event_rate": late_row["large_event_rate"],
                "late_propagated_share": late_row["propagated_share"],
                "late_repeated_default_share": late_row["repeated_default_share"],
                "late_single_initial_event_rate": late_row["single_initial_event_rate"],
                "late_active_credit": late_row["mean_active_credit"],
                "late_gini": late_row["mean_gini"],
            }
        )
    return pd.DataFrame(rows)


def evidence_gate_table(
    rescan: pd.DataFrame,
    tail: pd.DataFrame,
    finite: pd.DataFrame,
    slopes: pd.DataFrame,
    stationarity_pairs: pd.DataFrame,
) -> pd.DataFrame:
    high = rescan[rescan["source"].eq("new_high_c") & rescan["c"].ge(0.50)]
    tail_ok_rate = float((tail["bootstrap_p"] >= 0.10).mean())
    bounded_ok_rate = float((tail["bounded_bootstrap_p"] >= 0.10).mean())
    mean_size_fraction_slope_abs = slopes[
        slopes["metric"].eq("mean_size_fraction")
    ]["log_log_slope"].abs()
    p99_fraction_slope = slopes[slopes["metric"].eq("p99_fraction")]["log_log_slope"]
    rows = [
        {
            "gate": "稳健大级联",
            "status": "通过",
            "evidence": (
                f"c>=0.50 的平均事件级大级联率为 {high['event_large_event_rate'].mean():.3f}，"
                f"平均事件规模为 {high['mean_event_size'].mean():.2f}"
            ),
        },
        {
            "gate": "幂律尾部可接受性",
            "status": "部分通过",
            "evidence": (
                f"自动 xmin 下无界 bootstrap p>=0.10 的场景占 {tail_ok_rate:.2f}，"
                f"有限支持 p>=0.10 占 {bounded_ok_rate:.2f}；alpha 范围 "
                f"{tail['alpha'].min():.2f}-{tail['alpha'].max():.2f}，不具普适性"
            ),
        },
        {
            "gate": "有限尺寸临界缩放",
            "status": "不通过",
            "evidence": (
                "mean_size 对 N 的斜率约为 1，但 mean_size/N 的斜率接近 0；"
                f"|slope(mean_size/N)| 中位数 {mean_size_fraction_slope_abs.median():.3f}。"
                "这表示广延过载，而不是稀疏 avalanche cutoff 的临界扩展"
            ),
        },
        {
            "gate": "cutoff 相对规模",
            "status": "不通过",
            "evidence": (
                f"p99/N 的斜率多为负或近 0，中位数 {p99_fraction_slope.median():.3f}；"
                "相对 cutoff 没有 SOC 所需的清晰增长"
            ),
        },
        {
            "gate": "慢驱快崩/时间分离",
            "status": "不通过",
            "evidence": (
                f"长时 late avalanche occupancy 范围 "
                f"{stationarity_pairs['late_occupancy'].min():.3f}-"
                f"{stationarity_pairs['late_occupancy'].max():.3f}，几乎每期发生事件"
            ),
        },
        {
            "gate": "平稳性与重复违约",
            "status": "不通过",
            "evidence": (
                f"late repeated-default share 范围 "
                f"{stationarity_pairs['late_repeated_default_share'].min():.3f}-"
                f"{stationarity_pairs['late_repeated_default_share'].max():.3f}，"
                "事件主要来自重复违约状态"
            ),
        },
        {
            "gate": "非调参 SOC",
            "status": "不通过",
            "evidence": (
                "高 c 网格表现为从低/中驱动到过载区的外生参数扫描；"
                "系统没有在无需调参的稀疏临界态附近自组织"
            ),
        },
    ]
    return pd.DataFrame(rows)


def plot_finite(finite: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.8))
    specs = [
        ("mean_size_fraction", "Mean size / N"),
        ("p99_fraction", "P99 size / N"),
        ("event_large_event_rate", "P(S >= 0.1N | event)"),
        ("propagated_share_of_total_size", "Propagated share"),
    ]
    for ax, (metric, ylabel) in zip(axes.flat, specs):
        for keys, sub in finite.groupby(["money_distribution", "c"], sort=True):
            distribution, c_value = keys
            sub = sub.sort_values("n_nodes")
            ax.plot(
                sub["n_nodes"],
                sub[metric],
                marker="o",
                linewidth=1.7,
                label=f"{distribution} c={c_value:.1f}",
            )
        ax.set_xscale("log")
        ax.set_xlabel("N")
        ax.set_ylabel(ylabel)
        ax.grid(True, which="both", alpha=0.25)
    axes[1, 1].legend(fontsize=7, ncol=2)
    fig.suptitle("High-c finite-size diagnostics")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def plot_stationarity(pairs: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.8))
    specs = [
        ("late_occupancy", "Late avalanche occupancy"),
        ("late_over_early_mean_size", "Late / early mean size"),
        ("late_repeated_default_share", "Late repeated-default share"),
        ("late_active_credit", "Late active credit"),
    ]
    for ax, (metric, ylabel) in zip(axes.flat, specs):
        for distribution, sub in pairs.groupby("money_distribution", sort=True):
            sub = sub.sort_values("c")
            ax.plot(sub["c"], sub[metric], marker="o", linewidth=1.8, label=distribution)
        ax.set_xlabel("c")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("High-c long-run stationarity diagnostics")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def plot_gate(gates: pd.DataFrame, output_path: Path) -> None:
    colors = {"通过": "#4c78a8", "部分通过": "#f2a93b", "不通过": "#d65f5f"}
    gate_labels = {
        "稳健大级联": "Robust large cascades",
        "幂律尾部可接受性": "Power-law tail plausibility",
        "有限尺寸临界缩放": "Finite-size critical scaling",
        "cutoff 相对规模": "Relative cutoff growth",
        "慢驱快崩/时间分离": "Drive-avalanche separation",
        "平稳性与重复违约": "Stationarity / repeated defaults",
        "非调参 SOC": "Self-organization without tuning",
    }
    status_labels = {"通过": "Pass", "部分通过": "Partial", "不通过": "Fail"}
    y = np.arange(len(gates))
    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    values = gates["status"].map({"不通过": 0, "部分通过": 0.5, "通过": 1.0}).to_numpy()
    ax.barh(y, values, color=[colors[s] for s in gates["status"]], alpha=0.9)
    ax.set_yticks(y, [gate_labels.get(gate, gate) for gate in gates["gate"]])
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Evidence gate score")
    ax.set_title("High-c SOC evidence gates")
    ax.grid(axis="x", alpha=0.25)
    for idx, row in gates.iterrows():
        ax.text(
            values[idx] + 0.02,
            idx,
            status_labels.get(row["status"], row["status"]),
            va="center",
            fontsize=9,
        )
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(number):
        return ""
    if abs(number) >= 100:
        return f"{number:.1f}"
    return f"{number:.{digits}f}"


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(fmt(row[col]) for col in columns) + " |")
    return "\n".join(lines)


def rel(path: Path, base: Path) -> str:
    return os.path.relpath(path, start=base.parent)


def write_report(
    output_dir: Path,
    report_path: Path,
    rescan: pd.DataFrame,
    tail: pd.DataFrame,
    finite: pd.DataFrame,
    slopes: pd.DataFrame,
    stationarity_pairs: pd.DataFrame,
    gates: pd.DataFrame,
    metadata: dict[str, Any],
) -> None:
    high = rescan[rescan["source"].eq("new_high_c") & rescan["c"].ge(0.50)]
    finite_brief = finite[
        [
            "money_distribution",
            "c",
            "n_nodes",
            "event_large_event_rate",
            "mean_size_fraction",
            "p99_fraction",
            "propagated_share_of_total_size",
        ]
    ].copy()
    slope_brief = slopes[
        slopes["metric"].isin(["mean_size", "mean_size_fraction", "p99_fraction"])
    ][["money_distribution", "c", "metric", "log_log_slope", "r_squared"]].copy()
    stationarity_brief = stationarity_pairs[
        [
            "money_distribution",
            "c",
            "early_occupancy",
            "late_occupancy",
            "late_over_early_mean_size",
            "late_repeated_default_share",
            "late_active_credit",
            "late_gini",
        ]
    ].copy()
    tail_brief = tail[
        [
            "money_distribution",
            "c",
            "alpha",
            "bootstrap_p",
            "bounded_alpha",
            "bounded_bootstrap_p",
            "pl_vs_exponential_R",
            "pl_vs_lognormal_R",
        ]
    ].copy()
    text = f"""# 高 c 收入内生信贷网络 SOC 验证补充报告

生成时间：{metadata["created_at"]}

## 目标

上一轮 `c=0.10-0.80` 重扫显示，高 `c` 会产生稳定的大级联。这里继续补齐 SOC 验证所需的关键证据门槛：有限尺寸缩放、长时平稳性、尾部拟合和触发机制解释。

## 新增实验

- 有限尺寸：`N=100/200/500`，`c=0.30/0.50/0.80`，lognormal/pareto，两种分布各 24 次重复、240 period，共 {metadata["finite_runs"]} runs、{metadata["finite_events"]} events。
- 长时平稳性：`N=200`，`c=0.30/0.50/0.80`，lognormal/pareto，各 8 次重复、1200 period，共 {metadata["stationarity_runs"]} runs、{metadata["stationarity_events"]} events。
- 尾部拟合沿用高 c 重扫分析中的自动 `xmin` 离散幂律、有限支持幂律、exponential/lognormal 对照。

## 结论

当前高 c 扩展仍**不支持严格 SOC**。结论不是因为没有大级联；相反，大级联非常稳健。失败点在于：

1. 高 c 区域是外生驱动造成的持续过载：`c>=0.50` 的平均事件级大级联率为 {high["event_large_event_rate"].mean():.3f}。
2. 有限尺寸中 `mean_size` 近似按 `N` 线性放大，而 `mean_size/N` 基本不随 `N` 变化，说明是广延同步失败，不是稀疏 avalanche cutoff 的临界扩展。
3. 长时 late window 的 avalanche occupancy 为 {stationarity_pairs["late_occupancy"].min():.3f}-{stationarity_pairs["late_occupancy"].max():.3f}，几乎每期都发生事件，破坏慢驱快崩分离。
4. late repeated-default share 为 {stationarity_pairs["late_repeated_default_share"].min():.3f}-{stationarity_pairs["late_repeated_default_share"].max():.3f}，尾部和大事件强烈依赖重复违约状态。
5. 尾部拟合即使在部分场景不拒绝幂律，也不具备跨 c、跨分布、跨 N 的普适性；`alpha` 范围为 {tail["alpha"].min():.2f}-{tail["alpha"].max():.2f}。

## 证据门槛

{markdown_table(gates, ["gate", "status", "evidence"])}

## 有限尺寸结果

{markdown_table(finite_brief, ["money_distribution", "c", "n_nodes", "event_large_event_rate", "mean_size_fraction", "p99_fraction", "propagated_share_of_total_size"])}

## 有限尺寸斜率

{markdown_table(slope_brief, ["money_distribution", "c", "metric", "log_log_slope", "r_squared"])}

## 长时平稳性

{markdown_table(stationarity_brief, ["money_distribution", "c", "early_occupancy", "late_occupancy", "late_over_early_mean_size", "late_repeated_default_share", "late_active_credit", "late_gini"])}

## 尾部拟合摘要

{markdown_table(tail_brief, ["money_distribution", "c", "alpha", "bootstrap_p", "bounded_alpha", "bounded_bootstrap_p", "pl_vs_exponential_R", "pl_vs_lognormal_R"])}

## 图表

![finite]({rel(output_dir / "high_c_finite_size_soc_validation.png", report_path)})

![stationarity]({rel(output_dir / "high_c_stationarity_soc_validation.png", report_path)})

![gates]({rel(output_dir / "high_c_soc_evidence_gates.png", report_path)})

## 判定

高 c 扫描验证了“稳健大级联”和“过载转变”，但没有验证严格 SOC。更准确的表述是：

> 在当前 `period_end` 收入内生信贷网络机制下，扩大 `c` 会把系统推入高占用、重复违约、广延规模同步失败的过载吸引子；这不是无需精细调参的自组织临界态。

## 局限

- 本轮有限尺寸使用 `N=100/200/500` 三个规模，足以识别广延过载；若要估计更细的指数，可追加 `N=1000`。
- 本轮没有重新做高 c 下的 settlement/check-frequency 解耦机制实验；但高 c 已经在有限尺寸和平稳性门槛上失败，因此不会改变严格 SOC 的当前判定。
"""
    report_path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rescan = read_csv(args.rescan_analysis_dir / "scenario_comparison_summary.csv")
    tail = read_csv(args.rescan_analysis_dir / "high_c_tail_fits.csv")
    finite = read_csv(args.finite_dir / "finite_size_summary.csv")
    slopes = read_csv(args.finite_dir / "finite_size_scaling_slopes.csv")
    stationarity_runs = read_csv(args.stationarity_dir / "run_summary.csv")
    stationarity_events = read_csv(args.stationarity_dir / "avalanche_events.csv")
    windows = stationarity_window_summary(args.stationarity_dir)
    stationarity_pairs = stationarity_pair_summary(windows)
    gates = evidence_gate_table(rescan, tail, finite, slopes, stationarity_pairs)

    windows.to_csv(args.output_dir / "stationarity_window_summary.csv", index=False)
    stationarity_pairs.to_csv(args.output_dir / "stationarity_pair_summary.csv", index=False)
    gates.to_csv(args.output_dir / "soc_evidence_gates.csv", index=False)

    plot_finite(finite, args.output_dir / "high_c_finite_size_soc_validation.png")
    plot_stationarity(
        stationarity_pairs, args.output_dir / "high_c_stationarity_soc_validation.png"
    )
    plot_gate(gates, args.output_dir / "high_c_soc_evidence_gates.png")

    metadata = {
        "created_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "rescan_analysis_dir": str(args.rescan_analysis_dir),
        "finite_dir": str(args.finite_dir),
        "stationarity_dir": str(args.stationarity_dir),
        "output_dir": str(args.output_dir),
        "finite_runs": int(read_csv(args.finite_dir / "run_summary.csv").shape[0]),
        "finite_events": int(read_csv(args.finite_dir / "avalanche_events.csv").shape[0]),
        "stationarity_runs": int(stationarity_runs.shape[0]),
        "stationarity_events": int(stationarity_events.shape[0]),
        "strict_soc_supported": False,
        "artifacts": {
            "stationarity_window_summary": str(
                args.output_dir / "stationarity_window_summary.csv"
            ),
            "stationarity_pair_summary": str(
                args.output_dir / "stationarity_pair_summary.csv"
            ),
            "soc_evidence_gates": str(args.output_dir / "soc_evidence_gates.csv"),
            "report": str(
                args.output_dir / "credit_soc_high_c_soc_validation_report_20260605_v1.md"
            ),
        },
    }
    report_path = args.output_dir / "credit_soc_high_c_soc_validation_report_20260605_v1.md"
    write_report(
        args.output_dir,
        report_path,
        rescan,
        tail,
        finite,
        slopes,
        stationarity_pairs,
        gates,
        metadata,
    )
    (args.output_dir / "analysis_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
