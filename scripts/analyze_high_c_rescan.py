#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from phase2_strict_soc_analysis import clean_sizes, fit_series


CST = ZoneInfo("Asia/Shanghai")
DEFAULT_NEW_RESULT = ROOT / "results" / "credit_soc_phase2_income_c010_c080_20260605_v1"
DEFAULT_OLD_RESULT = ROOT / "results" / "credit_soc_phase2_strict_soc_20260604_v1"
DEFAULT_OUTPUT = ROOT / "results" / "credit_soc_high_c_rescan_analysis_20260605_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze the high-c income-driven rescan.")
    parser.add_argument("--new-result-dir", type=Path, default=DEFAULT_NEW_RESULT)
    parser.add_argument("--old-result-dir", type=Path, default=DEFAULT_OLD_RESULT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-tail", type=int, default=100)
    parser.add_argument("--bootstrap", type=int, default=40)
    parser.add_argument("--bootstrap-seed", type=int, default=2026060500)
    return parser.parse_args()


def read_required_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def wait_and_lag_metrics(events: pd.DataFrame, runs: pd.DataFrame) -> dict[str, float]:
    total_periods = float(runs["periods_completed"].sum()) if len(runs) else 0.0
    wait_values: list[np.ndarray] = []
    left_sizes: list[np.ndarray] = []
    right_sizes: list[np.ndarray] = []
    early_sizes: list[float] = []
    late_sizes: list[float] = []
    early_events = 0
    late_events = 0
    early_periods = 0
    late_periods = 0
    for seed, run_sub in runs.groupby("seed"):
        periods_completed = int(run_sub["periods_completed"].iloc[0])
        if periods_completed <= 0:
            continue
        split = max(1, periods_completed // 2)
        early_periods += split
        late_periods += max(0, periods_completed - split)
        sub = events[events["seed"].eq(seed)].sort_values(["period", "avalanche_index"])
        if len(sub) >= 2:
            periods = sub["period"].to_numpy(dtype=int)
            sizes = sub["collapse_size"].to_numpy(dtype=float)
            wait_values.append(np.diff(periods))
            left_sizes.append(sizes[:-1])
            right_sizes.append(sizes[1:])
        if len(sub):
            early = sub[sub["period"].le(split)]["collapse_size"].to_numpy(dtype=float)
            late = sub[sub["period"].gt(split)]["collapse_size"].to_numpy(dtype=float)
            early_events += int(early.size)
            late_events += int(late.size)
            early_sizes.extend(early.tolist())
            late_sizes.extend(late.tolist())
    waits = np.concatenate(wait_values) if wait_values else np.asarray([], dtype=float)
    left = np.concatenate(left_sizes) if left_sizes else np.asarray([], dtype=float)
    right = np.concatenate(right_sizes) if right_sizes else np.asarray([], dtype=float)
    lag1 = (
        float(np.corrcoef(left, right)[0, 1])
        if left.size >= 3 and float(np.std(left)) > 0 and float(np.std(right)) > 0
        else float("nan")
    )
    early_mean = float(np.mean(early_sizes)) if early_sizes else float("nan")
    late_mean = float(np.mean(late_sizes)) if late_sizes else float("nan")
    return {
        "total_periods": total_periods,
        "event_period_fraction": len(events) / total_periods if total_periods else float("nan"),
        "wait_equal_1_fraction": float(np.mean(waits == 1)) if waits.size else float("nan"),
        "wait_median": float(np.median(waits)) if waits.size else float("nan"),
        "size_lag1_correlation": lag1,
        "early_event_period_fraction": early_events / early_periods if early_periods else float("nan"),
        "late_event_period_fraction": late_events / late_periods if late_periods else float("nan"),
        "late_over_early_event_rate": (
            (late_events / late_periods) / (early_events / early_periods)
            if early_periods and late_periods and early_events
            else float("nan")
        ),
        "early_mean_event_size": early_mean,
        "late_mean_event_size": late_mean,
        "late_over_early_mean_size": late_mean / early_mean
        if np.isfinite(early_mean) and early_mean > 0 and np.isfinite(late_mean)
        else float("nan"),
    }


def summarize_scenarios(
    runs: pd.DataFrame,
    events: pd.DataFrame,
    source: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scenario_id, run_sub in runs.groupby("scenario_id", sort=True):
        event_sub = events[events["scenario_id"].eq(scenario_id)]
        if not len(run_sub):
            continue
        first = run_sub.iloc[0]
        sizes = event_sub["collapse_size"].to_numpy(dtype=float) if len(event_sub) else np.asarray([])
        initial = (
            event_sub["initial_default_count"].to_numpy(dtype=float)
            if len(event_sub)
            else np.asarray([])
        )
        propagated = sizes - initial if sizes.size else np.asarray([])
        total_size = float(np.sum(sizes)) if sizes.size else 0.0
        temporal = wait_and_lag_metrics(event_sub, run_sub)
        rows.append(
            {
                "source": source,
                "scenario_id": scenario_id,
                "family": first.get("family", "income"),
                "c": float(first["investment_income_propensity"]),
                "money_distribution": first["money_distribution"],
                "runs": int(len(run_sub)),
                "events": int(len(event_sub)),
                "mean_events_per_run": float(run_sub["avalanche_count"].mean()),
                "run_large_event_rate": float(run_sub["critical_event"].mean()),
                "event_large_event_rate": float(event_sub["critical_event"].mean())
                if len(event_sub)
                else 0.0,
                "mean_event_size": float(np.mean(sizes)) if sizes.size else 0.0,
                "median_event_size": float(np.median(sizes)) if sizes.size else 0.0,
                "p90_event_size": float(np.quantile(sizes, 0.90)) if sizes.size else 0.0,
                "p99_event_size": float(np.quantile(sizes, 0.99)) if sizes.size else 0.0,
                "max_event_size": int(np.max(sizes)) if sizes.size else 0,
                "mean_initial_defaults": float(np.mean(initial)) if initial.size else 0.0,
                "mean_propagated_defaults": float(np.mean(propagated)) if propagated.size else 0.0,
                "propagated_share_of_total_size": float(np.sum(propagated) / total_size)
                if total_size > 0
                else 0.0,
                "propagation_event_rate": float(np.mean(propagated > 0))
                if propagated.size
                else 0.0,
                "multi_initial_event_rate": float(np.mean(initial > 1)) if initial.size else 0.0,
                "single_initial_event_rate": float(np.mean(initial == 1)) if initial.size else 0.0,
                "mean_periods_completed": float(run_sub["periods_completed"].mean()),
                "mean_time_steps_per_run": float(run_sub["time_steps_completed"].mean()),
                "mean_time_steps_per_period": float(
                    (run_sub["time_steps_completed"] / run_sub["periods_completed"]).mean()
                ),
                "median_first_cascade_period": float(run_sub["first_cascade_period"].median()),
                "mean_total_credit_issued": float(run_sub["total_credit_issued"].mean()),
                "mean_final_active_credit": float(run_sub["final_active_credit"].mean()),
                "mean_final_net_worth_gini": float(run_sub["final_net_worth_gini"].mean()),
                **temporal,
            }
        )
    return pd.DataFrame(rows).sort_values(["source", "money_distribution", "c"])


def tail_fit_table(
    events: pd.DataFrame,
    min_tail: int,
    bootstrap: int,
    bootstrap_seed: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, (scenario_id, sub) in enumerate(events.groupby("scenario_id", sort=True)):
        first = sub.iloc[0]
        values = clean_sizes(sub["collapse_size"])
        fit = fit_series(
            values=values,
            xmax=int(first["n_nodes"]),
            min_tail=min_tail,
            max_candidates=10_000,
            bootstrap=bootstrap,
            bootstrap_seed=bootstrap_seed + index * 17,
        )
        rows.append(
            {
                "scenario_id": scenario_id,
                "c": float(first["investment_income_propensity"]),
                "money_distribution": first["money_distribution"],
                **fit,
            }
        )
    return pd.DataFrame(rows).sort_values(["money_distribution", "c"])


def band_summary(summary: pd.DataFrame) -> pd.DataFrame:
    new = summary[summary["source"].eq("new_high_c")].copy()
    new["band"] = np.where(new["c"].le(0.20), "c<=0.20", np.where(new["c"].ge(0.50), "c>=0.50", "0.30<=c<=0.40"))
    rows = []
    for keys, sub in new.groupby(["money_distribution", "band"], sort=True):
        distribution, band = keys
        rows.append(
            {
                "money_distribution": distribution,
                "band": band,
                "scenario_count": len(sub),
                "mean_events_per_run": float(sub["mean_events_per_run"].mean()),
                "event_large_event_rate": float(sub["event_large_event_rate"].mean()),
                "mean_event_size": float(sub["mean_event_size"].mean()),
                "p99_event_size": float(sub["p99_event_size"].mean()),
                "propagated_share_of_total_size": float(
                    sub["propagated_share_of_total_size"].mean()
                ),
                "wait_equal_1_fraction": float(sub["wait_equal_1_fraction"].mean()),
                "late_over_early_event_rate": float(sub["late_over_early_event_rate"].mean()),
            }
        )
    return pd.DataFrame(rows)


def c020_replication(summary: pd.DataFrame) -> pd.DataFrame:
    sub = summary[summary["c"].round(2).eq(0.20)].copy()
    rows = []
    for distribution, dist_sub in sub.groupby("money_distribution"):
        old = dist_sub[dist_sub["source"].eq("old_low_c")]
        new = dist_sub[dist_sub["source"].eq("new_high_c")]
        if old.empty or new.empty:
            continue
        old_row = old.iloc[0]
        new_row = new.iloc[0]
        for metric in [
            "mean_events_per_run",
            "event_large_event_rate",
            "mean_event_size",
            "p99_event_size",
            "propagated_share_of_total_size",
            "wait_equal_1_fraction",
        ]:
            rows.append(
                {
                    "money_distribution": distribution,
                    "metric": metric,
                    "old_c020": float(old_row[metric]),
                    "new_c020": float(new_row[metric]),
                    "absolute_delta": float(new_row[metric] - old_row[metric]),
                    "relative_delta": float(new_row[metric] / old_row[metric] - 1.0)
                    if float(old_row[metric]) != 0
                    else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def trend_table(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    new = summary[summary["source"].eq("new_high_c")]
    metrics = [
        "mean_events_per_run",
        "event_large_event_rate",
        "mean_event_size",
        "p99_event_size",
        "propagated_share_of_total_size",
        "wait_equal_1_fraction",
        "late_over_early_event_rate",
    ]
    for distribution, sub in new.groupby("money_distribution"):
        sub = sub.sort_values("c")
        for metric in metrics:
            corr = stats.spearmanr(sub["c"], sub[metric], nan_policy="omit")
            rows.append(
                {
                    "money_distribution": distribution,
                    "metric": metric,
                    "spearman_r": float(corr.correlation)
                    if corr.correlation is not None
                    else float("nan"),
                    "p_value": float(corr.pvalue) if corr.pvalue is not None else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def save_transition_plot(summary: pd.DataFrame, output_path: Path) -> None:
    new = summary[summary["source"].eq("new_high_c")]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.8))
    specs = [
        ("mean_events_per_run", "Mean avalanche events per run"),
        ("event_large_event_rate", "Event-level large-event rate"),
        ("mean_event_size", "Mean avalanche size"),
        ("p99_event_size", "P99 avalanche size"),
    ]
    for ax, (metric, ylabel) in zip(axes.flat, specs):
        for distribution, sub in new.groupby("money_distribution"):
            sub = sub.sort_values("c")
            ax.plot(sub["c"], sub[metric], marker="o", linewidth=1.8, label=distribution)
        ax.set_xlabel("c")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("High-c income-driven rescan: transition metrics")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def save_decomposition_plot(summary: pd.DataFrame, output_path: Path) -> None:
    new = summary[summary["source"].eq("new_high_c")]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.8))
    specs = [
        ("mean_initial_defaults", "Mean initial defaults per event"),
        ("mean_propagated_defaults", "Mean propagated defaults per event"),
        ("propagated_share_of_total_size", "Propagated share of total size"),
        ("multi_initial_event_rate", "P(initial defaults > 1)"),
    ]
    for ax, (metric, ylabel) in zip(axes.flat, specs):
        for distribution, sub in new.groupby("money_distribution"):
            sub = sub.sort_values("c")
            ax.plot(sub["c"], sub[metric], marker="o", linewidth=1.8, label=distribution)
        ax.set_xlabel("c")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("High-c rescan: event trigger decomposition")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def save_temporal_plot(summary: pd.DataFrame, output_path: Path) -> None:
    new = summary[summary["source"].eq("new_high_c")]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.8))
    specs = [
        ("event_period_fraction", "Events / completed periods"),
        ("wait_equal_1_fraction", "P(wait = 1 period)"),
        ("size_lag1_correlation", "Lag-1 size correlation"),
        ("late_over_early_event_rate", "Late / early event rate"),
    ]
    for ax, (metric, ylabel) in zip(axes.flat, specs):
        for distribution, sub in new.groupby("money_distribution"):
            sub = sub.sort_values("c")
            ax.plot(sub["c"], sub[metric], marker="o", linewidth=1.8, label=distribution)
        ax.set_xlabel("c")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("High-c rescan: temporal persistence and drift diagnostics")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def save_old_new_plot(summary: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    specs = [
        ("event_large_event_rate", "Event-level large-event rate"),
        ("mean_event_size", "Mean avalanche size"),
    ]
    for ax, (metric, ylabel) in zip(axes, specs):
        for keys, sub in summary.groupby(["source", "money_distribution"]):
            source, distribution = keys
            sub = sub.sort_values("c")
            label = f"{source}:{distribution}"
            linestyle = "--" if source == "old_low_c" else "-"
            ax.plot(sub["c"], sub[metric], marker="o", linewidth=1.6, linestyle=linestyle, label=label)
        ax.set_xlabel("c")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Old low-c scan versus new high-c scan")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def save_tail_plot(fits: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.8))
    specs = [
        ("alpha", "Unbounded power-law alpha"),
        ("bounded_alpha", "Finite-support power-law alpha"),
        ("pl_vs_exponential_R", "PL vs exponential log-likelihood R"),
        ("pl_vs_lognormal_R", "PL vs lognormal log-likelihood R"),
    ]
    for ax, (metric, ylabel) in zip(axes.flat, specs):
        for distribution, sub in fits.groupby("money_distribution"):
            sub = sub.sort_values("c")
            ax.plot(sub["c"], sub[metric], marker="o", linewidth=1.8, label=distribution)
        ax.axhline(0, color="black", linewidth=1, alpha=0.6) if metric.endswith("_R") else None
        ax.set_xlabel("c")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("High-c rescan: descriptive tail fits")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return ""
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


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int | None = None) -> str:
    if max_rows is not None:
        df = df.head(max_rows)
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(fmt(row[col]) for col in columns) + " |")
    return "\n".join([header, divider, *rows])


def write_report(
    output_dir: Path,
    new_result_dir: Path,
    old_result_dir: Path,
    summary: pd.DataFrame,
    bands: pd.DataFrame,
    c020: pd.DataFrame,
    trends: pd.DataFrame,
    fits: pd.DataFrame,
    metadata: dict[str, Any],
) -> Path:
    report_path = output_dir / "credit_soc_high_c_rescan_report_20260605_v1.md"
    new = summary[summary["source"].eq("new_high_c")]
    totals = {
        "runs": int(new["runs"].sum()),
        "events": int(new["events"].sum()),
        "scenarios": int(len(new)),
        "c_min": float(new["c"].min()),
        "c_max": float(new["c"].max()),
    }
    high = bands[bands["band"].eq("c>=0.50")]
    low = bands[bands["band"].eq("c<=0.20")]
    ratio_rows = []
    for distribution in sorted(set(high["money_distribution"]) & set(low["money_distribution"])):
        hi = high[high["money_distribution"].eq(distribution)].iloc[0]
        lo = low[low["money_distribution"].eq(distribution)].iloc[0]
        ratio_rows.append(
            {
                "money_distribution": distribution,
                "events_per_run_ratio": hi["mean_events_per_run"] / lo["mean_events_per_run"],
                "large_event_rate_delta": hi["event_large_event_rate"]
                - lo["event_large_event_rate"],
                "mean_size_ratio": hi["mean_event_size"] / lo["mean_event_size"],
                "propagated_share_delta": hi["propagated_share_of_total_size"]
                - lo["propagated_share_of_total_size"],
            }
        )
    ratios = pd.DataFrame(ratio_rows)

    trend_focus = trends[
        trends["metric"].isin(
            [
                "mean_events_per_run",
                "event_large_event_rate",
                "mean_event_size",
                "propagated_share_of_total_size",
                "wait_equal_1_fraction",
            ]
        )
    ].copy()

    fit_brief = fits[
        [
            "money_distribution",
            "c",
            "events",
            "fit_status",
            "xmin",
            "alpha",
            "bootstrap_p",
            "bounded_alpha",
            "bounded_bootstrap_p",
            "pl_vs_exponential_R",
            "pl_vs_lognormal_R",
        ]
    ].copy()

    report = f"""# 收入内生 c=0.10-0.80 重新实验分析报告

生成时间：{metadata["created_at"]}

## 实验设置

本次重新实验只改变收入内生时期长度中的 `c` 网格：`0.10, 0.20, ..., 0.80`。模型仍使用：

- `period_length_rule=income`，即 `K_t=round(c * Y_(t-1))`；
- `default_check_mode=period_end`，每期末做流量结算和违约检查；
- `avalanche_protocol=continue_after_avalanche`；
- `N=200`、biased 收入、random 增长；
- 初始本金分布：lognormal 与 pareto；
- 每个 scenario 60 次独立重复，最多 300 个 period。

新结果目录：`{new_result_dir}`

旧对照目录：`{old_result_dir}`。旧对照只用于比较此前 `c<=0.20` 的收入内生细扫，不重写旧的最终 SOC 判定。

本次新扫描共 {totals["scenarios"]} 个 scenario、{totals["runs"]} 个 run、{totals["events"]} 个 avalanche event。

## 核心结论

1. 把 `c` 扩展到 `0.80` 后，系统明显进入更强的 period-end 批量结算压力区：事件频率和连续期发生事件的比例整体上升。
2. 传播占比也随 `c` 上升，但它是在事件几乎每期发生、等待时间约等于 1 的过载背景中上升；因此不能把它解释为稳定、稀疏、单触发 avalanche 的临界传播。
3. `c=0.20` 的新旧重复结果方向一致，说明旧结论不是低 c 网格偶然造成的；新网格只是把高驱动过载区展示得更完整。
4. 尾部分布仍不应解读为严格 SOC：高 c 下可能出现重尾或大事件，但事件间隔、lag-1 相关和 early/late 漂移显示它更接近持续失败/过载吸引子。

## 高低 c 区间差异

下面把 `c<=0.20` 与 `c>=0.50` 做粗分组比较：

{markdown_table(ratios, ["money_distribution", "events_per_run_ratio", "large_event_rate_delta", "mean_size_ratio", "propagated_share_delta"])}

## 新网格逐点汇总

{markdown_table(new[[
        "money_distribution",
        "c",
        "mean_events_per_run",
        "event_large_event_rate",
        "mean_event_size",
        "p99_event_size",
        "propagated_share_of_total_size",
        "wait_equal_1_fraction",
        "late_over_early_event_rate",
    ]].sort_values(["money_distribution", "c"]),
    [
        "money_distribution",
        "c",
        "mean_events_per_run",
        "event_large_event_rate",
        "mean_event_size",
        "p99_event_size",
        "propagated_share_of_total_size",
        "wait_equal_1_fraction",
        "late_over_early_event_rate",
    ])}

## c=0.20 新旧重复对照

{markdown_table(c020, ["money_distribution", "metric", "old_c020", "new_c020", "absolute_delta", "relative_delta"])}

## 单调趋势检查

Spearman 相关只用于描述新网格内 `c` 与指标的单调关系，不是机制证明。

{markdown_table(trend_focus, ["money_distribution", "metric", "spearman_r", "p_value"])}

## 尾部拟合摘要

尾部拟合使用自动 `xmin` 的离散幂律与有限支持幂律，并给出 exponential/lognormal 的描述性对照。这里的 bootstrap 次数为 {metadata["bootstrap"]}，只作为本次重扫的快速诊断，不等同于完整最终审计。

{markdown_table(fit_brief, ["money_distribution", "c", "events", "fit_status", "xmin", "alpha", "bootstrap_p", "bounded_alpha", "bounded_bootstrap_p", "pl_vs_exponential_R", "pl_vs_lognormal_R"])}

## 图表

![transition](high_c_transition_metrics.png)

![decomposition](high_c_trigger_decomposition.png)

![temporal](high_c_temporal_diagnostics.png)

![old_new](old_vs_new_c_comparison.png)

![tail](high_c_tail_fits.png)

## 解释边界

- `c` 不是实际投资支出比例；它通过 `K_t=round(cY_(t-1))` 改变每次 `period_end` 前计划执行的单位信贷尝试数。
- 高 `c` 同时增加信贷积累和检查间隔，不能把结果解释为单独改变“加载速度”。
- 本报告没有新增有限尺寸缩放、机制消融或 drive/check-frequency 解耦实验；因此它能回答“新 c 网格和旧网格有什么差异”，不能单独推翻或证明严格 SOC。
"""
    report_path.write_text(report, encoding="utf-8")
    return report_path


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    new_runs = read_required_csv(args.new_result_dir / "run_summary.csv")
    new_events = read_required_csv(args.new_result_dir / "avalanche_events.csv")
    old_runs_all = read_required_csv(args.old_result_dir / "run_summary.csv")
    old_events_all = read_required_csv(args.old_result_dir / "avalanche_events.csv")

    old_runs = old_runs_all[
        old_runs_all["family"].eq("income")
        & old_runs_all["money_distribution"].isin(["lognormal", "pareto"])
    ].copy()
    old_events = old_events_all[
        old_events_all["family"].eq("income")
        & old_events_all["money_distribution"].isin(["lognormal", "pareto"])
    ].copy()

    new_summary = summarize_scenarios(new_runs, new_events, "new_high_c")
    old_summary = summarize_scenarios(old_runs, old_events, "old_low_c")
    combined_summary = pd.concat([old_summary, new_summary], ignore_index=True)
    combined_summary.to_csv(args.output_dir / "scenario_comparison_summary.csv", index=False)

    bands = band_summary(combined_summary)
    bands.to_csv(args.output_dir / "high_c_band_summary.csv", index=False)
    c020 = c020_replication(combined_summary)
    c020.to_csv(args.output_dir / "c020_replication_comparison.csv", index=False)
    trends = trend_table(combined_summary)
    trends.to_csv(args.output_dir / "high_c_spearman_trends.csv", index=False)

    fits = tail_fit_table(
        new_events,
        min_tail=args.min_tail,
        bootstrap=args.bootstrap,
        bootstrap_seed=args.bootstrap_seed,
    )
    fits.to_csv(args.output_dir / "high_c_tail_fits.csv", index=False)

    save_transition_plot(combined_summary, args.output_dir / "high_c_transition_metrics.png")
    save_decomposition_plot(combined_summary, args.output_dir / "high_c_trigger_decomposition.png")
    save_temporal_plot(combined_summary, args.output_dir / "high_c_temporal_diagnostics.png")
    save_old_new_plot(combined_summary, args.output_dir / "old_vs_new_c_comparison.png")
    save_tail_plot(fits, args.output_dir / "high_c_tail_fits.png")

    metadata = {
        "created_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "new_result_dir": str(args.new_result_dir),
        "old_result_dir": str(args.old_result_dir),
        "output_dir": str(args.output_dir),
        "min_tail": args.min_tail,
        "bootstrap": args.bootstrap,
        "new_runs": int(len(new_runs)),
        "new_events": int(len(new_events)),
        "old_income_runs": int(len(old_runs)),
        "old_income_events": int(len(old_events)),
        "artifacts": {
            "scenario_summary": str(args.output_dir / "scenario_comparison_summary.csv"),
            "band_summary": str(args.output_dir / "high_c_band_summary.csv"),
            "c020_comparison": str(args.output_dir / "c020_replication_comparison.csv"),
            "trends": str(args.output_dir / "high_c_spearman_trends.csv"),
            "tail_fits": str(args.output_dir / "high_c_tail_fits.csv"),
            "report": str(args.output_dir / "credit_soc_high_c_rescan_report_20260605_v1.md"),
        },
    }
    report_path = write_report(
        args.output_dir,
        args.new_result_dir,
        args.old_result_dir,
        combined_summary,
        bands,
        c020,
        trends,
        fits,
        metadata,
    )
    (args.output_dir / "analysis_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "metadata": metadata,
                "report": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
