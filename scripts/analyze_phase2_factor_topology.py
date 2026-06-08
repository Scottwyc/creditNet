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
from scipy.stats import spearmanr


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze phase-2 factor/topology sweep.")
    parser.add_argument("--result-dir", type=Path, required=True)
    return parser.parse_args()


def topology_degree_plot(summary: pd.DataFrame, output: Path) -> None:
    sub = summary[summary["factor_family"] == "topology_degree"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for topology, group in sub.groupby("topology"):
        group = group.sort_values("target_mean_degree")
        axes[0].plot(
            group["target_mean_degree"],
            group["critical_run_rate"],
            marker="o",
            label=topology.upper(),
        )
        axes[1].plot(
            group["target_mean_degree"],
            group["mean_max_collapse_size"],
            marker="o",
            label=topology.upper(),
        )
    axes[0].set_ylabel("Run-level large-cascade rate")
    axes[1].set_ylabel("Mean maximum avalanche size")
    for ax in axes:
        ax.set_xlabel("Target mean degree")
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("Fixed-horizon topology and density comparison at fixed K=20")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def structure_scatter(runs: pd.DataFrame, output: Path) -> None:
    sub = runs[runs["factor_family"] == "topology_degree"]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6))
    metrics = [
        ("topology_clustering", "Clustering"),
        ("topology_degree_cv", "Degree CV"),
        ("topology_lcc_average_path_length", "LCC average path length"),
    ]
    colors = {"er": "tab:blue", "ba": "tab:orange", "sw": "tab:green"}
    for ax, (metric, label) in zip(axes, metrics):
        for topology, group in sub.groupby("topology"):
            ax.scatter(
                group[metric],
                group["max_collapse_size"],
                alpha=0.65,
                s=24,
                color=colors[topology],
                label=topology.upper(),
            )
        ax.set_xlabel(label)
        ax.set_ylabel("Run maximum avalanche size")
        ax.grid(alpha=0.25)
    axes[0].legend()
    fig.suptitle("Topology structure versus cascade severity")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def factor_effect_plot(summary: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    specifications = [
        ("money_distribution", "money_distribution", "Initial money distribution"),
        ("income_rule", "income_distribution_rule", "Income allocation"),
        ("topology_growth", "growth_rule", "Growth rule"),
    ]
    for ax, (family, category, title) in zip(axes, specifications):
        sub = summary[summary["factor_family"] == family].copy()
        if family == "topology_growth":
            sub["label"] = sub["topology"].str.upper() + " / " + sub[category]
            category = "label"
        sub = sub.sort_values(category)
        x = np.arange(len(sub))
        ax.bar(x, sub["mean_max_collapse_size"], color="tab:red", alpha=0.75)
        ax.set_xticks(x, sub[category], rotation=35, ha="right", fontsize=8)
        ax.set_ylabel("Mean maximum avalanche size")
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def ab_heatmap(summary: pd.DataFrame, output: Path) -> None:
    sub = summary[summary["factor_family"] == "ab_grid"]
    pivot = sub.pivot(index="a", columns="b", values="mean_max_collapse_size").sort_index()
    fig, ax = plt.subplots(figsize=(6.5, 5.2))
    image = ax.imshow(pivot.to_numpy(), cmap="magma", aspect="auto", origin="lower")
    ax.set_xticks(np.arange(len(pivot.columns)), [f"{x:.2f}" for x in pivot.columns])
    ax.set_yticks(np.arange(len(pivot.index)), [f"{x:.2f}" for x in pivot.index])
    ax.set_xlabel("b: income consumption propensity")
    ax.set_ylabel("a: wealth consumption propensity")
    ax.set_title("Mean maximum avalanche size on a/b grid")
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            ax.text(j, i, f"{pivot.iloc[i, j]:.1f}", ha="center", va="center", color="white")
    fig.colorbar(image, ax=ax)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def topology_ccdf(events: pd.DataFrame, output: Path) -> None:
    sub = events[
        (events["factor_family"] == "topology_degree") & (events["target_mean_degree"] == 12)
    ]
    fig, ax = plt.subplots(figsize=(7.5, 5.3))
    for topology, group in sub.groupby("topology"):
        sizes = np.sort(group["collapse_size"].to_numpy(dtype=float))
        unique = np.unique(sizes[sizes > 0])
        ccdf = np.array([(sizes >= size).mean() for size in unique])
        ax.loglog(unique, ccdf, marker="o", markersize=3, label=topology.upper())
    ax.set_xlabel("Avalanche size")
    ax.set_ylabel("CCDF P(S >= s)")
    ax.set_title("Avalanche tails at matched mean degree 12")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def first_cascade_credit_plot(summary: pd.DataFrame, output: Path) -> None:
    sub = summary[summary["factor_family"] == "topology_degree"].copy()
    sub["label"] = sub["topology"].str.upper() + "-k" + sub["target_mean_degree"].astype(str)
    sub = sub.sort_values(["target_mean_degree", "topology"])
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.bar(np.arange(len(sub)), sub["mean_first_cascade_credit"], color="tab:blue", alpha=0.75)
    ax.set_xticks(np.arange(len(sub)), sub["label"], rotation=35, ha="right")
    ax.set_ylabel("Mean active credit before first cascade")
    ax.set_title("First-avalanche credit scale by explicit topology")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def correlations(runs: pd.DataFrame) -> pd.DataFrame:
    sub = runs[runs["factor_family"] == "topology_degree"]
    rows = []
    for structure_metric in [
        "topology_mean_degree",
        "topology_clustering",
        "topology_degree_cv",
        "topology_lcc_average_path_length",
    ]:
        for outcome in [
            "credit_scale_before_cascade",
            "max_collapse_size",
            "avalanche_count",
            "final_net_worth_gini",
        ]:
            rho, pvalue = spearmanr(sub[structure_metric], sub[outcome])
            rows.append(
                {
                    "scope": "topology_degree_runs",
                    "structure_metric": structure_metric,
                    "outcome": outcome,
                    "n": len(sub),
                    "spearman_rho": rho,
                    "pvalue": pvalue,
                }
            )
    return pd.DataFrame(rows)


def tail_screen(events: pd.DataFrame, xmin: int = 2) -> pd.DataFrame:
    rows = []
    for scenario_id, sub in events.groupby("scenario_id"):
        tail = sub.loc[sub["collapse_size"] >= xmin, "collapse_size"].to_numpy(dtype=float)
        alpha = None
        if tail.size >= 5:
            alpha = 1.0 + tail.size / float(
                np.sum(np.log(tail / max(float(xmin) - 0.5, 1e-9)))
            )
        rows.append(
            {
                "scenario_id": scenario_id,
                "factor_family": sub["factor_family"].iloc[0],
                "xmin": xmin,
                "tail_n": int(tail.size),
                "alpha_continuous_screen": alpha,
                "max_event_size": int(sub["collapse_size"].max()),
            }
        )
    return pd.DataFrame(rows)


def markdown_table(frame: pd.DataFrame) -> str:
    def format_value(value: object) -> str:
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
        lines.append("| " + " | ".join(format_value(row[column]) for column in columns) + " |")
    return "\n".join(lines)


def write_analysis_summary(
    result_dir: Path,
    runs: pd.DataFrame,
    events: pd.DataFrame,
    summary: pd.DataFrame,
    corr: pd.DataFrame,
    tails: pd.DataFrame,
) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z")
    topology = summary[summary["factor_family"] == "topology_degree"].sort_values(
        "mean_max_collapse_size", ascending=False
    )
    money = summary[summary["factor_family"] == "money_distribution"].sort_values(
        "mean_max_collapse_size", ascending=False
    )
    lines = [
        "# Phase-2 因素与显式拓扑扫描自动摘要",
        "",
        f"生成时间：{now}",
        "",
        f"- Run 数：{len(runs)}",
        f"- Avalanche 事件数：{len(events)}",
        "- 协议：`N=200`、`fixed K=20`、`max_periods=240`、`continue_after_avalanche`、`period_end` 检查。",
        "- 结论口径：本扫描是统一 240-period 固定时域的瞬态比较，不代表长期稳态或长期拓扑效应。",
        "- 注意：大 avalanche 与重尾迹象不等于严格 SOC 证明。",
        "",
        "## 拓扑与密度汇总",
        "",
        markdown_table(
            topology[
                [
                    "topology",
                    "target_mean_degree",
                    "runs",
                    "critical_run_rate",
                    "mean_first_cascade_credit",
                    "mean_max_collapse_size",
                    "mean_topology_clustering",
                    "mean_topology_degree_cv",
                ]
            ]
        ),
        "",
        "## 初始本金分布汇总",
        "",
        markdown_table(
            money[
                [
                    "money_distribution",
                    "runs",
                    "critical_run_rate",
                    "mean_first_cascade_credit",
                    "mean_max_collapse_size",
                    "mean_initial_gini",
                    "mean_final_net_worth_gini",
                ]
            ]
        ),
        "",
        "## 结构量 Spearman 相关",
        "",
        markdown_table(corr),
        "",
        "## Avalanche 尾部初筛",
        "",
        "以下 `alpha_continuous_screen` 固定使用 `xmin=2`，只用于同协议描述性比较，不是离散幂律检验或严格 SOC 证明。",
        "",
        markdown_table(
            tails.sort_values(["factor_family", "scenario_id"])[
                [
                    "factor_family",
                    "scenario_id",
                    "tail_n",
                    "alpha_continuous_screen",
                    "max_event_size",
                ]
            ]
        ),
        "",
        "## 证据边界",
        "",
        "- 每个场景重复数较小，结果用于因素方向和后续高重复筛选，不用于严格统计证明。",
        "- 所有显式拓扑是固定的无向可借贷机会图；实际信贷暴露保持带权有向。",
        "- 已知高风险协议在更长时域会向高频失效、高 Gini 和低活跃信贷漂移，因此不得把 240-period 差异外推为稳态排序。",
    ]
    (result_dir / "analysis_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    runs = pd.read_csv(args.result_dir / "run_summary.csv")
    events = pd.read_csv(args.result_dir / "avalanche_events.csv")
    summary = pd.read_csv(args.result_dir / "scenario_summary.csv")
    topology_summary = summary[summary["factor_family"] == "topology_degree"].copy()
    topology_summary[topology_summary["target_mean_degree"] == 12].to_csv(
        args.result_dir / "topology_matched_degree_summary.csv", index=False
    )
    topology_summary.to_csv(args.result_dir / "topology_degree_density_sweep_summary.csv", index=False)
    corr = correlations(runs)
    corr.to_csv(args.result_dir / "structure_outcome_correlations.csv", index=False)
    tails = tail_screen(events)
    tails.to_csv(args.result_dir / "tail_alpha_screen.csv", index=False)

    topology_degree_plot(summary, args.result_dir / "topology_degree_effects.png")
    structure_scatter(runs, args.result_dir / "structure_vs_cascade.png")
    factor_effect_plot(summary, args.result_dir / "factor_effects.png")
    ab_heatmap(summary, args.result_dir / "ab_grid_heatmap.png")
    topology_ccdf(events, args.result_dir / "topology_matched_degree_ccdf.png")
    first_cascade_credit_plot(summary, args.result_dir / "first_cascade_credit_by_topology.png")
    write_analysis_summary(args.result_dir, runs, events, summary, corr, tails)

    metadata = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "input": str(args.result_dir),
        "run_count": len(runs),
        "event_count": len(events),
        "figures": [
            "topology_degree_effects.png",
            "structure_vs_cascade.png",
            "factor_effects.png",
            "ab_grid_heatmap.png",
            "topology_matched_degree_ccdf.png",
            "first_cascade_credit_by_topology.png",
        ],
    }
    (args.result_dir / "analysis_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
