#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize fixed-K credit SOC sweep results.")
    parser.add_argument("--result-dirs", nargs="+", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--xmin", type=int, default=2)
    return parser.parse_args()


def extract_k(path: Path) -> int:
    match = re.search(r"fixedK(\d+)", path.name)
    if match:
        return int(match.group(1))
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    return int(metadata["command_args"]["fixed_period_length_steps"])


def estimate_tail_alpha(values: np.ndarray, xmin: int) -> tuple[int, float | None]:
    tail = values[values >= xmin]
    if tail.size < 5:
        return int(tail.size), None
    alpha = 1.0 + tail.size / float(np.sum(np.log(tail / max(xmin - 0.5, 1e-9))))
    return int(tail.size), float(alpha)


def load_sweep(result_dirs: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    run_frames = []
    event_frames = []
    for result_dir in result_dirs:
        k_value = extract_k(result_dir)
        run_df = pd.read_csv(result_dir / "run_summary.csv")
        run_df["fixed_k"] = k_value
        run_df["result_dir"] = str(result_dir)
        run_frames.append(run_df)

        event_path = result_dir / "avalanche_events.csv"
        event_df = pd.read_csv(event_path) if event_path.exists() else pd.DataFrame()
        if not event_df.empty:
            event_df["fixed_k"] = k_value
            event_df["result_dir"] = str(result_dir)
            event_frames.append(event_df)

    runs = pd.concat(run_frames, ignore_index=True)
    events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    return runs, events


def summarize(runs: pd.DataFrame, events: pd.DataFrame, xmin: int) -> pd.DataFrame:
    rows = []
    group_cols = ["fixed_k", "money_distribution", "income_distribution_rule", "growth_rule", "scenario_id"]
    for keys, run_sub in runs.groupby(group_cols):
        key_dict = dict(zip(group_cols, keys))
        event_sub = events
        for col, value in key_dict.items():
            if col in event_sub.columns:
                event_sub = event_sub[event_sub[col] == value]
        event_sizes = event_sub["collapse_size"].to_numpy(dtype=float) if not event_sub.empty else np.array([])
        tail_n, alpha = estimate_tail_alpha(event_sizes, xmin)
        rows.append(
            {
                **key_dict,
                "runs": int(len(run_sub)),
                "run_critical_rate": float(run_sub["critical_event"].mean()),
                "mean_avalanche_count_per_run": float(run_sub["avalanche_count"].mean()),
                "events": int(len(event_sub)),
                "event_critical_rate": float(event_sub["critical_event"].mean()) if len(event_sub) else 0.0,
                "mean_event_size": float(event_sub["collapse_size"].mean()) if len(event_sub) else 0.0,
                "median_event_size": float(event_sub["collapse_size"].median()) if len(event_sub) else 0.0,
                "p90_event_size": float(event_sub["collapse_size"].quantile(0.90)) if len(event_sub) else 0.0,
                "p99_event_size": float(event_sub["collapse_size"].quantile(0.99)) if len(event_sub) else 0.0,
                "max_event_size": int(event_sub["collapse_size"].max()) if len(event_sub) else 0,
                "tail_xmin": xmin,
                "tail_n": tail_n,
                "tail_alpha_continuous": alpha,
                "mean_final_net_worth_gini": float(run_sub["final_net_worth_gini"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(group_cols)


def plot_metric(summary: pd.DataFrame, metric: str, ylabel: str, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.8))
    for scenario_id, sub in summary.groupby("scenario_id"):
        sub = sub.sort_values("fixed_k")
        ax.plot(sub["fixed_k"], sub[metric], marker="o", linewidth=1.6, label=scenario_id)
    ax.set_xlabel("Period length K (time steps per period)")
    ax.set_ylabel(ylabel)
    ax.set_title(ylabel + " by fixed K")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_ccdf_by_k(events: pd.DataFrame, growth_rule: str, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    sub_events = events[events["growth_rule"] == growth_rule]
    for fixed_k, sub in sub_events.groupby("fixed_k"):
        sizes = np.sort(sub["collapse_size"].to_numpy(dtype=float))
        sizes = sizes[sizes > 0]
        if sizes.size == 0:
            continue
        unique = np.unique(sizes)
        ccdf = np.array([(sizes >= x).mean() for x in unique])
        ax.loglog(unique, ccdf, marker="o", linewidth=1.3, markersize=3, label=f"K={fixed_k}")
    ax.set_xlabel("Avalanche size")
    ax.set_ylabel("CCDF P(S >= s)")
    ax.set_title(f"Avalanche CCDF by K: {growth_rule}")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def markdown_table(df: pd.DataFrame) -> str:
    def fmt(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.3f}"
        if value is None:
            return ""
        return str(value)

    columns = list(df.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(fmt(row[col]) for col in columns) + " |")
    return "\n".join(lines)


def write_report(summary: pd.DataFrame, events: pd.DataFrame, output_dir: Path) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z")
    compact = summary[
        [
            "fixed_k",
            "scenario_id",
            "runs",
            "events",
            "event_critical_rate",
            "mean_event_size",
            "p90_event_size",
            "max_event_size",
            "tail_n",
            "tail_alpha_continuous",
        ]
    ]
    lines = [
        "# 固定K慢驱动 avalanche 扫描汇总",
        "",
        f"生成时间：{now}",
        "",
        "## 实验协议",
        "",
        "- 协议：`time_step + period`；每个 `time_step` 新增 1 个单位信贷。",
        "- 结算：`period_end`；每个 period 末执行投资支出、消费支出、收入分配、违约检查和级联。",
        "- Avalanche协议：`continue_after_avalanche`；期末级联清算后继续下一period。",
        "- 固定窗口：`K` 个 time_step 组成一个 period，本报告扫描多个 K。",
        "- 大崩塌阈值：`collapse_fraction >= 0.10`，在 `N=200` 下即 avalanche size >= 20。",
        "",
        "## 汇总表",
        "",
        markdown_table(compact),
        "",
        "## 图表",
        "",
        f"- 大崩塌事件率随K变化：`{output_dir / 'event_critical_rate_by_k.png'}`",
        f"- 平均avalanche规模随K变化：`{output_dir / 'mean_event_size_by_k.png'}`",
        f"- 每run平均avalanche次数随K变化：`{output_dir / 'mean_avalanche_count_by_k.png'}`",
        f"- 随机增长CCDF：`{output_dir / 'ccdf_by_k_random.png'}`",
        f"- 债务偏好增长CCDF：`{output_dir / 'ccdf_by_k_preferential_debt.png'}`",
        "",
        "## 初步判断",
        "",
        "- 随机增长在较大K下进入高频大avalanche状态，表现为持续脆弱而不是稀有临界。",
        "- `preferential_debt` 债务集中增长在同样K下以小avalanche为主，说明网络形成机制显著影响级联规模。",
        "- 固定K扫描展示了从低强度驱动到过载驱动的转变，下一步需要在转变区附近增加重复数，并和收入内生K协议对照。",
        "",
        f"总avalanche事件数：{len(events)}。",
    ]
    (output_dir / "fixed_k_sweep_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runs, events = load_sweep(args.result_dirs)
    runs.to_csv(args.output_dir / "combined_run_summary.csv", index=False)
    events.to_csv(args.output_dir / "combined_avalanche_events.csv", index=False)
    summary = summarize(runs, events, args.xmin)
    summary.to_csv(args.output_dir / "fixed_k_sweep_summary.csv", index=False)

    plot_metric(summary, "event_critical_rate", "Critical avalanche event rate", args.output_dir / "event_critical_rate_by_k.png")
    plot_metric(summary, "mean_event_size", "Mean avalanche size", args.output_dir / "mean_event_size_by_k.png")
    plot_metric(summary, "mean_avalanche_count_per_run", "Mean avalanche count per run", args.output_dir / "mean_avalanche_count_by_k.png")
    if not events.empty:
        plot_ccdf_by_k(events, "random", args.output_dir / "ccdf_by_k_random.png")
        plot_ccdf_by_k(events, "preferential_debt", args.output_dir / "ccdf_by_k_preferential_debt.png")
    write_report(summary, events, args.output_dir)

    metadata = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "result_dirs": [str(path) for path in args.result_dirs],
        "output_dir": str(args.output_dir),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
