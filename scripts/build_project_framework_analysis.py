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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build project.md-aligned credit SOC analysis.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--fixed-k-sweep-dir",
        type=Path,
        default=Path("results/credit_soc_fixedK_sweep_20260604_v1"),
    )
    parser.add_argument(
        "--income-c-sweep-dir",
        type=Path,
        default=Path("results/credit_soc_income_c_sweep_20260604_v1"),
    )
    parser.add_argument(
        "--income-rule-dir",
        type=Path,
        default=Path("results/credit_soc_continue_income_c005_20260604_v1"),
    )
    parser.add_argument(
        "--focus-dir",
        type=Path,
        default=Path("results/credit_soc_continue_income_c020_random_focus_20260604_v1"),
    )
    return parser.parse_args()


def initial_distribution_effect(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for money, run_sub in runs.groupby("money_distribution"):
        event_sub = events[events["money_distribution"] == money]
        critical = event_sub[event_sub["critical_event"]]
        total_periods = int(run_sub["periods_completed"].sum())
        rows.append(
            {
                "money_distribution": money,
                "runs": len(run_sub),
                "mean_initial_gini": run_sub["initial_money_gini"].mean(),
                "mean_final_net_worth_gini": run_sub["final_net_worth_gini"].mean(),
                "run_critical_rate": run_sub["critical_event"].mean(),
                "avalanche_events": len(event_sub),
                "critical_events": len(critical),
                "event_critical_rate": event_sub["critical_event"].mean(),
                "critical_events_per_100_periods": 100.0 * len(critical) / total_periods,
                "mean_event_size": event_sub["collapse_size"].mean(),
                "p90_event_size": event_sub["collapse_size"].quantile(0.90),
                "p99_event_size": event_sub["collapse_size"].quantile(0.99),
                "max_event_size": event_sub["collapse_size"].max(),
                "median_first_cascade_period": run_sub["first_cascade_period"].median(),
                "median_first_cascade_time_steps": run_sub["first_cascade_time_steps"].median(),
                "median_first_cascade_credit_scale": run_sub["credit_scale_before_cascade"].median(),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_initial_gini")


def income_distribution_effect(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, run_sub in runs.groupby(["income_distribution_rule", "growth_rule"]):
        income_rule, growth_rule = keys
        event_sub = events[
            (events["income_distribution_rule"] == income_rule)
            & (events["growth_rule"] == growth_rule)
        ]
        total_periods = int(run_sub["periods_completed"].sum())
        rows.append(
            {
                "income_distribution_rule": income_rule,
                "growth_rule": growth_rule,
                "runs": len(run_sub),
                "default_run_rate": run_sub["ended_by_default"].mean(),
                "mean_avalanche_count_per_run": run_sub["avalanche_count"].mean(),
                "avalanche_events_per_100_periods": 100.0 * len(event_sub) / total_periods,
                "mean_event_size": event_sub["collapse_size"].mean() if len(event_sub) else 0.0,
                "p90_event_size": event_sub["collapse_size"].quantile(0.90) if len(event_sub) else 0.0,
                "max_event_size": event_sub["collapse_size"].max() if len(event_sub) else 0,
                "mean_final_net_worth_gini": run_sub["final_net_worth_gini"].mean(),
                "mean_first_cascade_credit_scale": run_sub["credit_scale_before_cascade"].mean(),
            }
        )
    return pd.DataFrame(rows).sort_values(["growth_rule", "income_distribution_rule"])


def growth_rule_effect(runs: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, run_sub in runs.groupby(["fixed_k", "growth_rule"]):
        fixed_k, growth_rule = keys
        event_sub = events[(events["fixed_k"] == fixed_k) & (events["growth_rule"] == growth_rule)]
        critical = event_sub[event_sub["critical_event"]]
        total_periods = int(run_sub["periods_completed"].sum())
        rows.append(
            {
                "fixed_k": fixed_k,
                "growth_rule": growth_rule,
                "runs": len(run_sub),
                "avalanche_events": len(event_sub),
                "event_critical_rate": event_sub["critical_event"].mean(),
                "critical_events_per_100_periods": 100.0 * len(critical) / total_periods,
                "mean_event_size": event_sub["collapse_size"].mean(),
                "p90_event_size": event_sub["collapse_size"].quantile(0.90),
                "max_event_size": event_sub["collapse_size"].max(),
                "mean_avalanche_count_per_run": run_sub["avalanche_count"].mean(),
                "mean_final_net_worth_gini": run_sub["final_net_worth_gini"].mean(),
            }
        )
    return pd.DataFrame(rows).sort_values(["fixed_k", "growth_rule"])


def critical_credit_scale(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, sub in events.groupby(["money_distribution", "critical_event"]):
        money, critical_event = keys
        rows.append(
            {
                "money_distribution": money,
                "critical_event": bool(critical_event),
                "events": len(sub),
                "mean_credit_scale_before_cascade": sub["credit_scale_before_cascade"].mean(),
                "median_credit_scale_before_cascade": sub["credit_scale_before_cascade"].median(),
                "p10_credit_scale_before_cascade": sub["credit_scale_before_cascade"].quantile(0.10),
                "p90_credit_scale_before_cascade": sub["credit_scale_before_cascade"].quantile(0.90),
                "mean_time_steps_completed": sub["time_steps_completed"].mean(),
                "median_period": sub["period"].median(),
                "mean_collapse_size": sub["collapse_size"].mean(),
            }
        )
    return pd.DataFrame(rows).sort_values(["money_distribution", "critical_event"])


def plot_initial_effect(df: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))
    x = np.arange(len(df))
    labels = df["money_distribution"]
    axes[0].bar(x, df["mean_initial_gini"], color="#4c78a8")
    axes[0].set_title("Initial money inequality")
    axes[0].set_ylabel("Mean initial Gini")
    axes[1].bar(x, df["run_critical_rate"], color="#e45756")
    axes[1].set_title("Runs with large avalanche")
    axes[1].set_ylabel("Run-level critical rate")
    axes[2].bar(x, df["max_event_size"], color="#72b7b2")
    axes[2].set_title("Maximum avalanche")
    axes[2].set_ylabel("Nodes")
    for ax in axes:
        ax.set_xticks(x, labels, rotation=25)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Initial-principal distribution effect: endogenous K, c=0.20")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_income_effect(df: pd.DataFrame, path: Path) -> None:
    metrics = [
        ("avalanche_events_per_100_periods", "Avalanche events / 100 periods"),
        ("mean_event_size", "Mean avalanche size"),
        ("mean_final_net_worth_gini", "Final net-worth Gini"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    labels = [f"{r.income_distribution_rule}\n{r.growth_rule}" for r in df.itertuples()]
    x = np.arange(len(df))
    colors = ["#54a24b" if value == "uniform" else "#e45756" for value in df["income_distribution_rule"]]
    for ax, (metric, title) in zip(axes, metrics):
        ax.bar(x, df[metric], color=colors)
        ax.set_title(title)
        ax.set_xticks(x, labels, rotation=25)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Income distribution effect: endogenous K, c=0.05")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_growth_effect(df: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for growth_rule, sub in df.groupby("growth_rule"):
        sub = sub.sort_values("fixed_k")
        axes[0].plot(
            sub["fixed_k"],
            sub["event_critical_rate"],
            marker="o",
            linewidth=1.8,
            label=growth_rule,
        )
        axes[1].plot(
            sub["fixed_k"],
            sub["mean_event_size"],
            marker="o",
            linewidth=1.8,
            label=growth_rule,
        )
    axes[0].set_title("Large-avalanche event rate")
    axes[0].set_ylabel("Event critical rate")
    axes[1].set_title("Mean avalanche size")
    axes[1].set_ylabel("Nodes")
    for ax in axes:
        ax.set_xlabel("Fixed K")
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("Network-growth mechanism effect")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_credit_scale(events: pd.DataFrame, path: Path) -> None:
    distributions = sorted(events["money_distribution"].unique())
    data = []
    labels = []
    colors = []
    for money in distributions:
        for critical in [False, True]:
            values = events[
                (events["money_distribution"] == money)
                & (events["critical_event"] == critical)
            ]["credit_scale_before_cascade"]
            if values.empty:
                continue
            data.append(values)
            labels.append(f"{money}\n{'large' if critical else 'small'}")
            colors.append("#e45756" if critical else "#4c78a8")
    fig, ax = plt.subplots(figsize=(10, 5.3))
    box = ax.boxplot(data, tick_labels=labels, showfliers=False, patch_artist=True)
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.set_ylabel("Credit scale before cascade")
    ax.set_title("Critical credit scale by initial-principal distribution")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    focus_runs = pd.read_csv(args.focus_dir / "run_summary.csv")
    focus_events = pd.read_csv(args.focus_dir / "avalanche_events.csv")
    income_runs = pd.read_csv(args.income_rule_dir / "run_summary.csv")
    income_events = pd.read_csv(args.income_rule_dir / "avalanche_events.csv")
    fixed_runs = pd.read_csv(args.fixed_k_sweep_dir / "combined_run_summary.csv")
    fixed_events = pd.read_csv(args.fixed_k_sweep_dir / "combined_avalanche_events.csv")

    initial_df = initial_distribution_effect(focus_runs, focus_events)
    income_df = income_distribution_effect(income_runs, income_events)
    growth_df = growth_rule_effect(fixed_runs, fixed_events)
    credit_df = critical_credit_scale(focus_events)

    initial_df.to_csv(args.output_dir / "initial_distribution_effect.csv", index=False)
    income_df.to_csv(args.output_dir / "income_distribution_effect_c005.csv", index=False)
    growth_df.to_csv(args.output_dir / "growth_rule_effect_fixed_k.csv", index=False)
    credit_df.to_csv(args.output_dir / "critical_credit_scale.csv", index=False)

    plot_initial_effect(initial_df, args.output_dir / "initial_distribution_effect.png")
    plot_income_effect(income_df, args.output_dir / "income_distribution_effect.png")
    plot_growth_effect(growth_df, args.output_dir / "growth_rule_effect.png")
    plot_credit_scale(focus_events, args.output_dir / "critical_credit_scale.png")

    metadata = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "fixed_k_sweep_dir": str(args.fixed_k_sweep_dir),
        "income_c_sweep_dir": str(args.income_c_sweep_dir),
        "income_rule_dir": str(args.income_rule_dir),
        "focus_dir": str(args.focus_dir),
        "output_dir": str(args.output_dir),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
