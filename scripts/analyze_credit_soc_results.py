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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze credit-network SOC simulation results.")
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--xmin", type=int, default=2)
    return parser.parse_args()


def estimate_tail_alpha(values: np.ndarray, xmin: int) -> dict[str, float | int | None]:
    tail = values[values >= xmin]
    if tail.size < 5:
        return {"xmin": xmin, "tail_n": int(tail.size), "alpha_continuous": None}
    alpha = 1.0 + tail.size / float(np.sum(np.log(tail / max(xmin - 0.5, 1e-9))))
    return {"xmin": xmin, "tail_n": int(tail.size), "alpha_continuous": float(alpha)}


def plot_collapse_ccdf(df: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for scenario_id, sub in df.groupby("scenario_id"):
        sizes = np.sort(sub["collapse_size"].to_numpy(dtype=float))
        sizes = sizes[sizes > 0]
        if sizes.size == 0:
            continue
        unique = np.unique(sizes)
        ccdf = np.array([(sizes >= x).mean() for x in unique])
        ax.loglog(unique, ccdf, marker="o", linewidth=1.0, markersize=3, label=scenario_id)
    ax.set_xlabel("Cascade size")
    ax.set_ylabel("CCDF P(S >= s)")
    ax.set_title("Cascade-size complementary distribution")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_avalanche_credit_scatter(events: pd.DataFrame, output_path: Path) -> None:
    if events.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for scenario_id, sub in events.groupby("scenario_id"):
        ax.scatter(
            sub["credit_scale_before_cascade"],
            sub["collapse_size"],
            s=14,
            alpha=0.55,
            label=scenario_id,
        )
    ax.set_xlabel("Credit scale before cascade")
    ax.set_ylabel("Avalanche size")
    ax.set_title("Avalanche size versus credit scale")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_avalanche_timeline(events: pd.DataFrame, output_path: Path) -> None:
    if events.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for scenario_id, sub in events.groupby("scenario_id"):
        ax.scatter(
            sub["time_steps_completed"],
            sub["collapse_size"],
            s=12,
            alpha=0.50,
            label=scenario_id,
        )
    ax.set_xlabel("Completed time steps")
    ax.set_ylabel("Avalanche size")
    ax.set_title("Avalanche timeline")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_credit_scale_box(df: pd.DataFrame, output_path: Path) -> None:
    scenario_order = sorted(df["scenario_id"].unique())
    data = [df.loc[df["scenario_id"] == sid, "credit_scale_before_cascade"] for sid in scenario_order]
    fig, ax = plt.subplots(figsize=(max(8, len(scenario_order) * 0.7), 5.5))
    ax.boxplot(data, tick_labels=scenario_order, showfliers=False)
    ax.set_ylabel("Credit scale before cascade")
    ax.set_title("Critical credit scale by scenario")
    ax.tick_params(axis="x", rotation=35, labelsize=8)
    ax.grid(axis="y", alpha=0.25)
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


def write_report(
    df: pd.DataFrame,
    avalanche_events: pd.DataFrame,
    scenario_summary: pd.DataFrame,
    tail_rows: list[dict[str, object]],
    output_dir: Path,
) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "# 信贷网络自组织临界第一批仿真结果",
        "",
        f"生成时间：{now}",
        "",
        "## 实验对象",
        "",
        "- 模型：离散单位信贷网络仿真器 `src/creditnet/simulation.py`。",
        "- 节点：个体资产负债表，状态包括现金、贷款资产、债务负债、净资产。",
        "- 信贷边：`lender -> borrower`，每次新增 1 单位信贷。",
        "- 流量：借入资金当期投资支出；消费支出由 `a * 正净资产 + b * 上期收入` 随机舍入得到。",
        "- 收入分配：`uniform` 为等概率分配，`biased` 为按正净资产加 floor 的偏好分配。",
        "- 级联：债务人违约后，债权人对应贷款资产减记；若债权人净资产转负则继续传播。",
        "",
        "## 参数范围",
        "",
        f"- 总运行数：{len(df)}",
        f"- Avalanche事件数：{len(avalanche_events)}",
        f"- 节点数：{sorted(df['n_nodes'].unique().tolist())}",
        f"- 每个场景重复数：{int(df.groupby('scenario_id').size().iloc[0]) if len(df) else 0}",
        f"- 最大时期：{sorted(df['max_periods'].unique().tolist())}",
        f"- 初始本金分布：{', '.join(sorted(df['money_distribution'].unique()))}",
        f"- 收入分配机制：{', '.join(sorted(df['income_distribution_rule'].unique()))}",
        f"- 网络增长机制：{', '.join(sorted(df['growth_rule'].unique()))}",
        f"- 大崩塌阈值：collapse_fraction >= {float(df['collapse_threshold_fraction'].iloc[0]):.3f}",
        "",
        "## 场景汇总",
        "",
        markdown_table(scenario_summary),
        "",
        "## 幂律尾部初筛",
        "",
        "这里优先使用 `avalanche_events.csv` 中的全部 avalanche size 做连续近似 Pareto tail alpha 第一眼筛查；它不等同于严格幂律检验，后续需要做 KS/似然比对照。",
        "",
        markdown_table(pd.DataFrame(tail_rows)),
        "",
        "## 图表",
        "",
        f"- Run级 collapse size CCDF：`{output_dir / 'collapse_size_ccdf.png'}`",
        f"- 临界信贷规模箱线图：`{output_dir / 'credit_scale_boxplot.png'}`",
        f"- Avalanche size vs credit scale：`{output_dir / 'avalanche_credit_scatter.png'}`",
        f"- Avalanche timeline：`{output_dir / 'avalanche_timeline.png'}`",
        "",
        "## 初步观察",
        "",
        "- 本批结果主要用于验证机制和建立基线，不作为最终 SOC 结论。",
        "- 如果 collapse size 的尾部样本数偏少，下一步应增加重复轮次并扫 `a/b/c` 参数。",
        "- 偏好收入分配和高不平等初始本金分布预计会改变临界信贷规模和崩塌规模尾部，需要后续做稳健性对照。",
        "",
    ]
    (output_dir / "analysis_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or args.result_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.result_dir / "run_summary.csv")
    scenario_summary = pd.read_csv(args.result_dir / "scenario_summary.csv")
    avalanche_path = args.result_dir / "avalanche_events.csv"
    try:
        avalanche_events = pd.read_csv(avalanche_path) if avalanche_path.exists() else pd.DataFrame()
    except EmptyDataError:
        avalanche_events = pd.DataFrame()

    plot_collapse_ccdf(df, output_dir / "collapse_size_ccdf.png")
    plot_credit_scale_box(df, output_dir / "credit_scale_boxplot.png")
    plot_avalanche_credit_scatter(avalanche_events, output_dir / "avalanche_credit_scatter.png")
    plot_avalanche_timeline(avalanche_events, output_dir / "avalanche_timeline.png")

    tail_rows = []
    tail_source = avalanche_events if not avalanche_events.empty else df
    for scenario_id, sub in tail_source.groupby("scenario_id"):
        stats = estimate_tail_alpha(sub["collapse_size"].to_numpy(dtype=float), args.xmin)
        stats["scenario_id"] = scenario_id
        stats["source"] = "avalanche_events" if not avalanche_events.empty else "run_summary"
        tail_rows.append(stats)
    pd.DataFrame(tail_rows).to_csv(output_dir / "tail_alpha_screen.csv", index=False)
    write_report(df, avalanche_events, scenario_summary, tail_rows, output_dir)

    metadata = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "input": str(args.result_dir),
        "output": str(output_dir),
    }
    (output_dir / "analysis_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
