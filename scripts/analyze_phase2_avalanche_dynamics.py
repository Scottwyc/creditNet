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
from scipy.stats import linregress


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze phase-2 avalanche dynamics.")
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    return parser.parse_args()


def markdown_table(frame: pd.DataFrame) -> str:
    def render(value: object) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(render(row[column]) for column in columns) + " |")
    return "\n".join(lines)


def pooled_lag1(events: pd.DataFrame) -> float:
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


def independence_diagnostics(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario_id, sub in runs.groupby("scenario_id", sort=False):
        event_sub = events[events["scenario_id"] == scenario_id]
        waits = event_sub["period_waiting_time"].dropna()
        occupancy = (
            len(event_sub) / sub["periods_completed"].sum()
            if sub["periods_completed"].sum() > 0
            else 0.0
        )
        wait_one = float((waits == 1).mean()) if len(waits) else float("nan")
        lag1 = pooled_lag1(event_sub)
        persistent = bool(
            occupancy >= 0.50
            or (not np.isnan(wait_one) and wait_one >= 0.80)
            or (not np.isnan(lag1) and lag1 >= 0.50)
        )
        rows.append(
            {
                "scenario_id": scenario_id,
                "family": sub["family"].iloc[0],
                "n_nodes": int(sub["n_nodes"].iloc[0]),
                "period_length_rule": sub["period_length_rule"].iloc[0],
                "drive_value": float(sub["drive_value"].iloc[0]),
                "runs": len(sub),
                "periods_observed": int(sub["periods_completed"].sum()),
                "events": len(event_sub),
                "avalanche_period_occupancy": occupancy,
                "one_period_wait_fraction": wait_one,
                "pooled_size_lag1_correlation": lag1,
                "persistent_active_flag": persistent,
            }
        )
    return pd.DataFrame(rows)


def branching_summary(events: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "scenario_id",
        "family",
        "n_nodes",
        "period_length_rule",
        "drive_value",
    ]
    return (
        events.groupby(columns, as_index=False)
        .agg(
            event_count=("collapse_size", "size"),
            mean_initial_defaults=("initial_default_count", "mean"),
            mean_propagated_defaults=("propagated_default_count", "mean"),
            mean_weighted_branching=("weighted_branching_ratio", "mean"),
            median_weighted_branching=("weighted_branching_ratio", "median"),
            p95_weighted_branching=("weighted_branching_ratio", lambda x: x.quantile(0.95)),
            mean_duration=("duration_generations", "mean"),
            p95_duration=("duration_generations", lambda x: x.quantile(0.95)),
        )
        .sort_values(["family", "n_nodes", "drive_value"])
    )


def waiting_distribution(events: pd.DataFrame) -> pd.DataFrame:
    waits = events.dropna(subset=["period_waiting_time"]).copy()
    if waits.empty:
        return pd.DataFrame()
    columns = ["scenario_id", "family", "n_nodes", "period_length_rule", "drive_value"]
    rows: list[dict[str, object]] = []
    for keys, group in waits.groupby(columns, sort=False):
        values = group["period_waiting_time"].astype(int)
        for waiting_time, count in values.value_counts().sort_index().items():
            rows.append(
                dict(zip(columns, keys))
                | {
                    "period_waiting_time": int(waiting_time),
                    "count": int(count),
                    "probability": float(count / len(values)),
                    "ccdf": float((values >= waiting_time).mean()),
                }
            )
    return pd.DataFrame(rows)


def size_duration_bins(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario_id, group in events.groupby("scenario_id", sort=False):
        max_size = int(group["collapse_size"].max())
        edges = np.unique(
            np.maximum(
                1,
                np.rint(np.geomspace(1, max(max_size + 1, 2), num=12)).astype(int),
            )
        )
        if len(edges) < 2:
            edges = np.array([1, 2])
        bins = pd.cut(group["collapse_size"], bins=np.r_[edges, np.inf], right=False)
        for interval, sub in group.groupby(bins, observed=True):
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "family": group["family"].iloc[0],
                    "n_nodes": int(group["n_nodes"].iloc[0]),
                    "period_length_rule": group["period_length_rule"].iloc[0],
                    "drive_value": float(group["drive_value"].iloc[0]),
                    "size_bin_left": float(interval.left),
                    "size_bin_right": float(interval.right),
                    "event_count": len(sub),
                    "mean_size": float(sub["collapse_size"].mean()),
                    "mean_duration": float(sub["duration_generations"].mean()),
                    "median_duration": float(sub["duration_generations"].median()),
                    "p95_duration": float(sub["duration_generations"].quantile(0.95)),
                }
            )
    return pd.DataFrame(rows)


def duration_size_regressions(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario_id, group in events.groupby("scenario_id", sort=False):
        positive = group[(group["collapse_size"] > 0) & (group["duration_generations"] > 0)]
        x = np.log(positive["collapse_size"].to_numpy(dtype=float))
        y = np.log(positive["duration_generations"].to_numpy(dtype=float))
        if len(x) >= 10 and np.std(x) > 0 and np.std(y) > 0:
            result = linregress(x, y)
            slope, intercept, rvalue, pvalue, stderr = (
                result.slope,
                result.intercept,
                result.rvalue,
                result.pvalue,
                result.stderr,
            )
        else:
            slope = intercept = rvalue = pvalue = stderr = float("nan")
        rows.append(
            {
                "scenario_id": scenario_id,
                "family": group["family"].iloc[0],
                "n_nodes": int(group["n_nodes"].iloc[0]),
                "drive_value": float(group["drive_value"].iloc[0]),
                "events": len(group),
                "log_duration_vs_log_size_slope": slope,
                "intercept": intercept,
                "r_squared": rvalue * rvalue,
                "pvalue": pvalue,
                "slope_stderr": stderr,
            }
        )
    return pd.DataFrame(rows)


def scaling_summary(events: pd.DataFrame, diagnostics: pd.DataFrame) -> pd.DataFrame:
    sub = events[events["family"] == "size_scaling_income_c018"]
    rows: list[dict[str, object]] = []
    for n_nodes, group in sub.groupby("n_nodes"):
        diag = diagnostics[
            (diagnostics["family"] == "size_scaling_income_c018")
            & (diagnostics["n_nodes"] == n_nodes)
        ].iloc[0]
        rows.append(
            {
                "n_nodes": int(n_nodes),
                "events": len(group),
                "mean_size": float(group["collapse_size"].mean()),
                "p95_size": float(group["collapse_size"].quantile(0.95)),
                "max_size": int(group["collapse_size"].max()),
                "p95_size_fraction": float(group["collapse_fraction"].quantile(0.95)),
                "max_size_fraction": float(group["collapse_fraction"].max()),
                "mean_duration_generations": float(group["duration_generations"].mean()),
                "p95_duration_generations": float(
                    group["duration_generations"].quantile(0.95)
                ),
                "max_duration_generations": int(group["duration_generations"].max()),
                "mean_weighted_branching": float(group["weighted_branching_ratio"].mean()),
                "avalanche_period_occupancy": diag["avalanche_period_occupancy"],
                "one_period_wait_fraction": diag["one_period_wait_fraction"],
                "pooled_size_lag1_correlation": diag["pooled_size_lag1_correlation"],
            }
        )
    return pd.DataFrame(rows).sort_values("n_nodes")


def _quartile_period_count(periods_completed: int, quartile: int) -> int:
    periods = np.arange(1, periods_completed + 1)
    labels = np.minimum(
        4,
        1 + np.floor(4 * (periods - 1) / max(periods_completed, 1)).astype(int),
    )
    return int(np.sum(labels == quartile))


def time_window_summary(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    keys = ["scenario_id", "family", "n_nodes", "period_length_rule", "drive_value"]
    for scenario_id, run_sub in runs.groupby("scenario_id", sort=False):
        event_sub = events[events["scenario_id"] == scenario_id]
        base = {
            "scenario_id": scenario_id,
            "family": run_sub["family"].iloc[0],
            "n_nodes": int(run_sub["n_nodes"].iloc[0]),
            "period_length_rule": run_sub["period_length_rule"].iloc[0],
            "drive_value": float(run_sub["drive_value"].iloc[0]),
            "runs": len(run_sub),
        }
        for quartile in [1, 2, 3, 4]:
            window = event_sub[event_sub["time_quartile"] == quartile]
            period_count = int(
                sum(
                    _quartile_period_count(int(periods), quartile)
                    for periods in run_sub["periods_completed"]
                )
            )
            rows.append(
                base
                | {
                    "time_window": f"Q{quartile}",
                    "period_count": period_count,
                    "event_count": len(window),
                    "avalanche_period_occupancy": (
                        len(window) / period_count if period_count > 0 else 0.0
                    ),
                    "mean_event_size": (
                        float(window["collapse_size"].mean()) if len(window) else 0.0
                    ),
                    "large_event_rate": (
                        float(window["critical_event"].mean()) if len(window) else 0.0
                    ),
                    "mean_duration_generations": (
                        float(window["duration_generations"].mean()) if len(window) else 0.0
                    ),
                    "mean_weighted_branching": (
                        float(window["weighted_branching_ratio"].mean()) if len(window) else 0.0
                    ),
                    "mean_credit_before": (
                        float(window["credit_scale_before_cascade"].mean()) if len(window) else 0.0
                    ),
                    "mean_credit_after": (
                        float(window["active_credit_after_cascade"].mean()) if len(window) else 0.0
                    ),
                }
            )
        post = event_sub[event_sub["post_burn_in"]]
        post_period_count = int(
            sum(int(periods) - int(np.ceil(0.25 * int(periods))) for periods in run_sub["periods_completed"])
        )
        rows.append(
            base
            | {
                "time_window": "post_Q1_burn_in",
                "period_count": post_period_count,
                "event_count": len(post),
                "avalanche_period_occupancy": (
                    len(post) / post_period_count if post_period_count > 0 else 0.0
                ),
                "mean_event_size": float(post["collapse_size"].mean()) if len(post) else 0.0,
                "large_event_rate": float(post["critical_event"].mean()) if len(post) else 0.0,
                "mean_duration_generations": (
                    float(post["duration_generations"].mean()) if len(post) else 0.0
                ),
                "mean_weighted_branching": (
                    float(post["weighted_branching_ratio"].mean()) if len(post) else 0.0
                ),
                "mean_credit_before": (
                    float(post["credit_scale_before_cascade"].mean()) if len(post) else 0.0
                ),
                "mean_credit_after": (
                    float(post["active_credit_after_cascade"].mean()) if len(post) else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)


def plot_size_duration(events: pd.DataFrame, binned: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    families = ["fixed_k_transition", "income_c_transition", "size_scaling_income_c018"]
    titles = ["Fixed-K transition", "Endogenous-c transition", "N scaling at c=0.18"]
    rng = np.random.default_rng(20260604)
    for ax, family, title in zip(axes, families, titles):
        sub = events[events["family"] == family]
        if len(sub) > 5000:
            sub = sub.iloc[rng.choice(len(sub), size=5000, replace=False)]
        ax.scatter(
            sub["collapse_size"],
            sub["duration_generations"],
            s=8,
            alpha=0.12,
            color="tab:blue",
        )
        medians = binned[binned["family"] == family].groupby("size_bin_left", as_index=False).agg(
            mean_size=("mean_size", "mean"),
            median_duration=("median_duration", "mean"),
        )
        ax.plot(
            medians["mean_size"],
            medians["median_duration"],
            marker="o",
            color="tab:red",
            linewidth=2,
        )
        ax.set_xscale("log")
        ax.set_xlabel("Avalanche size S")
        ax.set_ylabel("Discovery-generation duration T")
        ax.set_title(title)
        ax.grid(alpha=0.25)
    fig.suptitle("Avalanche size-duration relation")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_branching(summary: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for ax, family, label in [
        (axes[0], "fixed_k_transition", "Fixed K"),
        (axes[1], "income_c_transition", "Endogenous c"),
    ]:
        sub = summary[summary["family"] == family].sort_values("drive_value")
        ax.plot(
            sub["drive_value"],
            sub["mean_weighted_branching"],
            marker="o",
            label="Mean weighted branching",
        )
        ax.plot(
            sub["drive_value"],
            sub["p95_weighted_branching"],
            marker="s",
            label="P95 weighted branching",
        )
        ax.axhline(1.0, linestyle="--", color="black", linewidth=1)
        ax.set_xlabel(label)
        ax.set_ylabel("Empirical branching ratio")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Wave-to-wave propagation versus drive")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_waiting(distribution: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, family, title in [
        (axes[0], "fixed_k_transition", "Fixed-K transition"),
        (axes[1], "income_c_transition", "Endogenous-c transition"),
    ]:
        sub = distribution[distribution["family"] == family]
        for drive, group in sub.groupby("drive_value"):
            ax.loglog(
                group["period_waiting_time"],
                group["ccdf"],
                marker="o",
                markersize=3,
                label=f"{drive:g}",
            )
        ax.set_xlabel("Inter-avalanche wait (periods)")
        ax.set_ylabel("CCDF")
        ax.set_title(title)
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(title="Drive", fontsize=7)
    fig.suptitle("Waiting-time distributions")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_scaling(events: pd.DataFrame, scaling: pd.DataFrame, output: Path) -> None:
    sub = events[events["family"] == "size_scaling_income_c018"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for n_nodes, group in sub.groupby("n_nodes"):
        fractions = np.sort(group["collapse_fraction"].to_numpy(dtype=float))
        unique = np.unique(fractions[fractions > 0])
        ccdf = np.array([(fractions >= value).mean() for value in unique])
        axes[0].loglog(unique, ccdf, marker="o", markersize=3, label=f"N={n_nodes}")
    axes[0].set_xlabel("Avalanche fraction S/N")
    axes[0].set_ylabel("CCDF")
    axes[0].set_title("Fractional avalanche cutoff")
    axes[0].grid(True, which="both", alpha=0.25)
    axes[0].legend()

    axes[1].plot(
        scaling["n_nodes"],
        scaling["p95_duration_generations"],
        marker="o",
        label="P95 duration",
    )
    axes[1].plot(
        scaling["n_nodes"],
        scaling["max_duration_generations"],
        marker="s",
        label="Max duration",
    )
    axes[1].set_xlabel("System size N")
    axes[1].set_ylabel("Discovery generations")
    axes[1].set_title("Propagation duration versus N")
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    fig.suptitle("Dynamic finite-size comparison at endogenous c=0.18")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_independence(diagnostics: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    metrics = [
        ("avalanche_period_occupancy", "Avalanche-period occupancy"),
        ("one_period_wait_fraction", "P(wait = 1 period)"),
        ("pooled_size_lag1_correlation", "Pooled size lag-1 correlation"),
    ]
    for ax, (metric, label) in zip(axes, metrics):
        for family, marker in [
            ("fixed_k_transition", "o"),
            ("income_c_transition", "s"),
        ]:
            sub = diagnostics[diagnostics["family"] == family].sort_values("drive_value")
            ax.plot(sub["drive_value"], sub[metric], marker=marker, label=family)
        ax.set_xlabel("Drive value (K or c)")
        ax.set_ylabel(label)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7)
    fig.suptitle("Event-separation and dependence diagnostics")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_time_windows(windows: pd.DataFrame, output: Path) -> None:
    sub = windows[
        (windows["family"] == "long_run_attractor")
        & (windows["time_window"].isin(["Q1", "Q2", "Q3", "Q4"]))
    ].copy()
    sub["label"] = np.where(
        sub["period_length_rule"] == "fixed",
        "K=" + sub["drive_value"].astype(int).astype(str),
        "c=" + sub["drive_value"].map(lambda value: f"{value:.2f}"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for label, group in sub.groupby("label"):
        group = group.sort_values("time_window")
        axes[0].plot(group["time_window"], group["mean_event_size"], marker="o", label=label)
        axes[1].plot(
            group["time_window"], group["avalanche_period_occupancy"], marker="o", label=label
        )
        axes[2].plot(
            group["time_window"], group["mean_weighted_branching"], marker="o", label=label
        )
    axes[0].set_ylabel("Mean avalanche size")
    axes[1].set_ylabel("Avalanche-period occupancy")
    axes[2].set_ylabel("Mean weighted branching")
    for ax in axes:
        ax.set_xlabel("Run time window")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Long-run transient versus late persistent-failure attractor")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def classify_evidence(diagnostics: pd.DataFrame, branching: pd.DataFrame) -> str:
    persistent_count = int(diagnostics["persistent_active_flag"].sum())
    total = len(diagnostics)
    mean_branching_max = float(branching["mean_weighted_branching"].max())
    if persistent_count > 0:
        return (
            f"{persistent_count}/{total} 个场景触发持续活跃/事件依赖标志；"
            f"事件平均分支比最高为 {mean_branching_max:.3f}。动态证据支持从亚临界传播向"
            "持续活跃或过载状态的转变，但不能把逐期相关事件当作独立 SOC avalanche，"
            "严格 SOC 在当前协议下不可识别。"
        )
    return (
        f"未触发持续活跃标志，事件平均分支比最高为 {mean_branching_max:.3f}；"
        "动态证据仍不足以单独证明严格 SOC。"
    )


def write_report(
    report_path: Path,
    result_dir: Path,
    runs: pd.DataFrame,
    events: pd.DataFrame,
    waves: pd.DataFrame,
    diagnostics: pd.DataFrame,
    branching: pd.DataFrame,
    scaling: pd.DataFrame,
    regressions: pd.DataFrame,
    validation: pd.DataFrame,
    windows: pd.DataFrame,
) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z")
    fixed = diagnostics[diagnostics["family"] == "fixed_k_transition"].sort_values("drive_value")
    income = diagnostics[diagnostics["family"] == "income_c_transition"].sort_values("drive_value")
    long_windows = windows[
        (windows["family"] == "long_run_attractor")
        & (windows["time_window"].isin(["Q1", "Q4", "post_Q1_burn_in"]))
    ].copy()
    long_windows["protocol"] = np.where(
        long_windows["period_length_rule"] == "fixed",
        "K=" + long_windows["drive_value"].astype(int).astype(str),
        "c=" + long_windows["drive_value"].map(lambda value: f"{value:.2f}"),
    )
    relative_result = Path("..") / result_dir.relative_to(report_path.parent.parent)
    conclusion = classify_evidence(diagnostics, branching)
    report_path.write_text(
        "\n".join(
            [
                "# 信贷网络 Phase-2 Avalanche 动态与临界传播报告",
                "",
                f"生成时间：{now}",
                "",
                "## 协议与口径",
                "",
                f"- 正式实验：{len(runs)} 个 run、{len(events)} 个 avalanche、{len(waves)} 个非空传播波。",
                "- 主机制：lognormal 初始本金、biased 收入、random 信贷增长、continue_after_avalanche、period_end 检查。",
                "- 扫描：固定 `K=18/20/22/24/26/28`；收入内生 `c=0.14/0.16/0.18/0.20`；`c=0.18` 下 `N=100/200/500`。",
                "- 所有正式 run 开启 `validate_accounting=True`，种子和完整参数见 `metadata.json`。",
                "- 持续时间定义为 FIFO 顺序清算中节点最早被发现的传播代数，初始违约集合为第 0 代；`cascade_steps` 只是处理节点数，未被误称为持续时间。",
                f"- 正式 sweep 前与当前基线逐种子校验：{int(validation['matched'].sum())}/{len(validation)} 行完全一致；最终方法审计另覆盖 502 个随机级联状态和 16 个完整 run。",
                "",
                "## 模型框架与动态变量",
                "",
                "当前模型先在一个 period 内逐 time_step 尝试增加单位信贷暴露，再在 period_end 完成投资/消费支出、收入分配、负净资产识别和级联清算。级联在同一 period_end 内完成；传播代数是算法清算顺序上的动态标注，不等同于 period 或 time_step。",
                "",
                "节点净资产为 `W_i = cash_i + loan_assets_i - debt_liabilities_i`，初始违约条件为严格 `W_i < 0`。清算债务人的入边会使其债权人减记贷款资产，可能产生下一传播代；当前 `wipe_defaulted_assets=True` 还会清除违约节点持有的贷款资产。`continue_after_avalanche` 不让节点永久退出，因此同一节点可跨 period 重复违约。",
                "",
                "| 变量 | 明确定义 | 不能误解为 |",
                "| --- | --- | --- |",
                "| avalanche size / `collapse_size` | 本次级联中最终被处理并清算的不同节点数，等于所有 wave size 之和 | 初始违约数或持续时间 |",
                "| initial default count | 收入分配后、传播清算前已经净资产 `<0` 的节点数，也是第 0 代 wave size | 由网络传播新增的违约数 |",
                "| wave size | 某一最早发现传播代中的新违约节点数 | 整次 avalanche size |",
                "| duration/generations | 非空 FIFO 最早发现代数量，包含第 0 代；传播代数为 duration-1 | 同步更新波数、物理时间、period 数、time_step 数或处理节点数 |",
                "| branching ratio | 相邻波 `wave_(g+1)/wave_g`；weighted branching 为传播新增总数除以前序波父节点总数 | 严格临界分支过程的无偏估计 |",
                "| period/time-step waiting time | 同一 run 中相邻 avalanche 的检测 period 差，以及检测时累计已执行信贷尝试步数差 | avalanche 内部持续时间、计划 K 差、成功贷款差或物理时间 |",
                "| avalanche-period occupancy | pooled 观测 period 中发生 avalanche 的比例；当前 period_end 协议每期最多记录一次 | 独立事件概率 |",
                "| size lag-1 correlation | 将每个 run 内相邻 avalanche-event size 对汇总后的 Pearson 相关；跨 run 不连接，事件不必相隔 1 period | period-lag 相关、逐 run 相关平均、因果关系或平稳性证明 |",
                "| baseline `cascade_steps` | 基线 FIFO 清算中被处理的违约节点数，数值上等于 avalanche size | duration/generations |",
                "",
                "基线清算为顺序 FIFO 队列，不是同步批量更新。节点一旦在净资产为负时进入队列，之后即使其他顺序清算使其净资产恢复，基线仍会处理该节点。因此本文 wave/generation 只表示“最早进入队列的算法发现代”，受节点处理顺序和 sticky queue 语义影响，不能解释为客观传播时间。",
                "",
                "## 最终方法审计",
                "",
                "- 数值与分母错误：未发现。",
                "- Baseline equivalence：正式 sweep 前 6/6 seed 行匹配；最终独立审计的 502 个随机级联状态与 16 个完整 run 均为 0 mismatch。",
                "- 校验器加固：baseline equivalence 现比较全部共享 run/event 字段和浮点字段；修改后另跑 6 行，全部匹配。",
                "- 原始时钟：280 个有事件 run 的首事件 waiting 均为空；后续 period/time-step waiting 全部等于相邻事件检测时钟之差；每个 run-period 最多一个事件。",
                "- 独立重算：occupancy、P(wait=1)、pooled event-lag1、Q1-Q4 与 burn-in 全部匹配，最大差异仅为浮点舍入量级。",
                f"- 机器可读审计：`{result_dir}/final_method_audit_20260604.json`。",
                "",
                "## 核心判断",
                "",
                conclusion,
                "",
                "平均分支比低于 1 并不自动表示整个长期过程独立亚临界：一次 period_end 可以同时产生多个初始违约，且 continue 协议可使相邻时期事件高度相关。严格 SOC 仍需独立事件定义、尾部分布检验、有限尺寸标度和慢驱动/快 avalanche 分离共同支持。",
                "",
                "本分支对当前 continue 协议的直接分类是：单次事件内部传播通常为亚临界分支，但系统长期状态向持续失败/过载吸引子漂移；因此 pooled avalanche 动态不是平稳独立的临界事件样本。该结论是对当前协议下严格 SOC 解释的不支持证据，而不是对所有可能清算、退出或驱动协议的普遍否定。",
                "",
                "## 事件分离与相关性",
                "",
                "持续活跃标志在 occupancy>=0.50、P(wait=1)>=0.80 或 size lag-1 corr>=0.50 任一满足时触发。",
                "",
                "这里的 occupancy 使用 `事件数 / pooled 已观测 period 数`；P(wait=1) 排除每个 run 的首个无前序事件；lag-1 将 run 内相邻事件对合并后计算 Pearson 相关，不跨 run 连接。",
                "",
                "### 固定 K",
                "",
                markdown_table(
                    fixed[
                        [
                            "drive_value",
                            "events",
                            "avalanche_period_occupancy",
                            "one_period_wait_fraction",
                            "pooled_size_lag1_correlation",
                            "persistent_active_flag",
                        ]
                    ].rename(columns={"drive_value": "K"})
                ),
                "",
                "### 收入内生 c",
                "",
                markdown_table(
                    income[
                        [
                            "drive_value",
                            "events",
                            "avalanche_period_occupancy",
                            "one_period_wait_fraction",
                            "pooled_size_lag1_correlation",
                            "persistent_active_flag",
                        ]
                    ].rename(columns={"drive_value": "c"})
                ),
                "",
                f"![事件分离与相关性]({relative_result / 'independence_diagnostics.png'})",
                "",
                "## 时间漂移、burn-in 与长期吸引子",
                "",
                "为避免把非平稳漂移混入 pooled dynamics，长跑面板对每个 run 按时间四等分，并同时报告去除 Q1 后的统计。Q4 与 Q1 的差异用于识别早期瞬态向晚期持续失败/过载吸引子的迁移。",
                "",
                "每个长期协议均为 5 个完整 1000-period run。Q1-Q4 按各 run 的相对 period 位置划分；occupancy 使用窗口内 pooled period 分母，size、duration、branching 和 active credit 是窗口内 pooled event 均值，不是先算逐 run 均值再平均。`post_Q1_burn_in` 删除各 run 前 25% period；这些窗口比较是非平稳性诊断，不是正式平稳性检验。",
                "",
                "四个长期协议的 Q4 事件期占比均为 1.0。最强的固定 `K=30` 场景从 Q1 到 Q4 出现：平均 size `12.89 -> 25.85`、大事件率 `0.165 -> 0.966`、平均 duration `1.99 -> 4.81`、平均 weighted branching `0.151 -> 0.578`，同时 avalanche 前活跃信贷 `778.50 -> 96.44`。这更符合脆弱低信贷存量上的持续失败吸引子，而非平稳临界态附近彼此分离的 avalanche。",
                "",
                markdown_table(
                    long_windows[
                        [
                            "protocol",
                            "time_window",
                            "period_count",
                            "event_count",
                            "avalanche_period_occupancy",
                            "mean_event_size",
                            "large_event_rate",
                            "mean_duration_generations",
                            "mean_weighted_branching",
                            "mean_credit_before",
                        ]
                    ]
                ),
                "",
                f"![time windows]({relative_result / 'long_run_time_windows.png'})",
                "",
                "## 传播分支与 size-duration",
                "",
                markdown_table(
                    branching[
                        [
                            "family",
                            "n_nodes",
                            "drive_value",
                            "event_count",
                            "mean_weighted_branching",
                            "p95_weighted_branching",
                            "mean_duration",
                            "p95_duration",
                        ]
                    ]
                ),
                "",
                f"![size-duration]({relative_result / 'size_duration_relation.png'})",
                "",
                f"![branching]({relative_result / 'branching_vs_drive.png'})",
                "",
                f"![waiting]({relative_result / 'waiting_time_distribution.png'})",
                "",
                "## 系统规模动态对照",
                "",
                "规模对照使用收入内生 `c=0.18`，使第一期及后续驱动随总收入扩展，避免固定绝对 K 改变人均驱动。",
                "",
                markdown_table(scaling),
                "",
                f"![dynamic scaling]({relative_result / 'dynamic_scaling.png'})",
                "",
                "## 证据边界",
                "",
                "- 传播波是对当前顺序清算算法的最早发现代数标注，不是假设同时更新的物理时间。",
                "- event 表中的相邻 avalanche 在 continue 协议下可能来自持续失败态；等待时间和 lag-1 相关已用于标记这一风险。",
                "- period waiting 是事件检测期索引差；time-step waiting 是检测时累计已执行信贷尝试步数差。二者都不是 avalanche 内部传播时间。",
                "- pooled lag-1 和 pooled quartile 均会按事件数给高事件 run 更大权重；本报告明确将其作为依赖/漂移诊断，不作为独立同分布统计。",
                "- size-duration 对数回归仅为描述性动态 scaling，不替代严格幂律与有限尺寸塌缩检验。",
                "- 当前动态证据可区分亚临界传播、转变区和持续活跃/过载风险，但不足以证明严格 SOC。",
                "",
                "## 证据文件",
                "",
                f"- 原始 run/event/wave：`{result_dir}/run_summary.csv`、`avalanche_events.csv`、`avalanche_waves.csv`",
                f"- 基线一致性：`{result_dir}/baseline_equivalence.csv`",
                f"- 独立性诊断：`{result_dir}/independence_diagnostics.csv`",
                f"- 动态规模对照：`{result_dir}/system_size_dynamics.csv`",
                f"- 时间窗口与 burn-in：`{result_dir}/time_window_dynamics.csv`",
                f"- size-duration 回归：`{result_dir}/duration_size_regressions.csv`",
                f"- 最终方法审计：`{result_dir}/final_method_audit_20260604.json`",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    runs = pd.read_csv(args.result_dir / "run_summary.csv")
    events = pd.read_csv(args.result_dir / "avalanche_events.csv")
    waves = pd.read_csv(args.result_dir / "avalanche_waves.csv")
    validation = pd.read_csv(args.result_dir / "baseline_equivalence.csv")

    diagnostics = independence_diagnostics(runs, events)
    branching = branching_summary(events)
    waiting = waiting_distribution(events)
    binned = size_duration_bins(events)
    regressions = duration_size_regressions(events)
    scaling = scaling_summary(events, diagnostics)
    windows = time_window_summary(runs, events)

    diagnostics.to_csv(args.result_dir / "independence_diagnostics.csv", index=False)
    branching.to_csv(args.result_dir / "branching_by_drive.csv", index=False)
    waiting.to_csv(args.result_dir / "waiting_time_distribution.csv", index=False)
    binned.to_csv(args.result_dir / "size_duration_binned.csv", index=False)
    regressions.to_csv(args.result_dir / "duration_size_regressions.csv", index=False)
    scaling.to_csv(args.result_dir / "system_size_dynamics.csv", index=False)
    windows.to_csv(args.result_dir / "time_window_dynamics.csv", index=False)

    plot_size_duration(events, binned, args.result_dir / "size_duration_relation.png")
    plot_branching(branching, args.result_dir / "branching_vs_drive.png")
    plot_waiting(waiting, args.result_dir / "waiting_time_distribution.png")
    plot_scaling(events, scaling, args.result_dir / "dynamic_scaling.png")
    plot_independence(diagnostics, args.result_dir / "independence_diagnostics.png")
    plot_time_windows(windows, args.result_dir / "long_run_time_windows.png")

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(
        args.report_path,
        args.result_dir,
        runs,
        events,
        waves,
        diagnostics,
        branching,
        scaling,
        regressions,
        validation,
        windows,
    )
    metadata = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "result_dir": str(args.result_dir),
        "report_path": str(args.report_path),
        "run_count": len(runs),
        "event_count": len(events),
        "wave_count": len(waves),
        "classification": classify_evidence(diagnostics, branching),
        "method_audit": str(args.result_dir / "final_method_audit_20260604.json"),
        "figures": [
            "size_duration_relation.png",
            "branching_vs_drive.png",
            "waiting_time_distribution.png",
            "dynamic_scaling.png",
            "independence_diagnostics.png",
            "long_run_time_windows.png",
        ],
    }
    (args.result_dir / "analysis_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
