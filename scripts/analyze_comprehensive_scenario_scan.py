#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from phase2_strict_soc_analysis import fit_series

CST = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze comprehensive credit-network scenario scan."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--min-tail", type=int, default=30)
    parser.add_argument("--bootstrap", type=int, default=20)
    parser.add_argument("--bootstrap-seed", type=int, default=2026060900)
    parser.add_argument("--max-xmin-candidates", type=int, default=200)
    parser.add_argument("--top-scenarios", type=int, default=36)
    return parser.parse_args()


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def scenario_label(row: pd.Series) -> str:
    return (
        f"{row.money_distribution}|{row.income_distribution_rule}|"
        f"{row.spending_label}|{row.topology_label}|{row.growth_rule}"
    )


def pivot_metric(summary: pd.DataFrame, row_key: str, metric: str) -> pd.DataFrame:
    grouped = (
        summary.groupby([row_key, "c"], as_index=False)[metric]
        .mean()
        .sort_values([row_key, "c"])
    )
    return grouped.pivot(index=row_key, columns="c", values=metric).fillna(0.0)


def heatmap(
    matrix: pd.DataFrame,
    output: Path,
    title: str,
    cbar_label: str,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
) -> None:
    height = max(4.0, 0.32 * len(matrix.index) + 1.5)
    width = max(6.0, 0.55 * len(matrix.columns) + 3.0)
    fig, ax = plt.subplots(figsize=(width, height))
    im = ax.imshow(matrix.values, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks(np.arange(len(matrix.columns)))
    ax.set_xticklabels([f"{float(c):.2f}" for c in matrix.columns], rotation=45, ha="right")
    ax.set_yticks(np.arange(len(matrix.index)))
    ax.set_yticklabels(matrix.index)
    ax.set_xlabel("c")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label=cbar_label)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_axis_heatmaps(summary: pd.DataFrame, output_dir: Path) -> list[str]:
    figure_paths: list[str] = []
    axis_specs = [
        ("money_distribution", "cascade_phase_by_money.png", "Cascade phase by initial money"),
        ("income_distribution_rule", "cascade_phase_by_income_rule.png", "Cascade phase by income allocation"),
        ("spending_label", "cascade_phase_by_spending.png", "Cascade phase by spending mechanism"),
        ("topology_label", "cascade_phase_by_topology.png", "Cascade phase by topology"),
        ("growth_rule", "cascade_phase_by_growth_rule.png", "Cascade phase by growth rule"),
    ]
    for key, filename, title in axis_specs:
        matrix = pivot_metric(summary, key, "mean_event_fraction")
        path = output_dir / filename
        heatmap(matrix, path, title, "mean collapse fraction", "magma", 0.0, 1.0)
        figure_paths.append(filename)
    for key, filename, title in [
        ("money_distribution", "large_event_phase_by_money.png", "Large-event rate by initial money"),
        ("spending_label", "large_event_phase_by_spending.png", "Large-event rate by spending"),
        ("topology_label", "large_event_phase_by_topology.png", "Large-event rate by topology"),
    ]:
        matrix = pivot_metric(summary, key, "event_large_event_rate")
        path = output_dir / filename
        heatmap(matrix, path, title, "event large-event rate", "viridis", 0.0, 1.0)
        figure_paths.append(filename)
    return figure_paths


def ccdf(values: pd.Series | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    array = np.asarray(values, dtype=np.int64)
    array = array[array > 0]
    if array.size == 0:
        return np.array([], dtype=int), np.array([], dtype=float)
    unique, counts = np.unique(array, return_counts=True)
    survival = np.cumsum(counts[::-1])[::-1] / array.size
    return unique, survival


def plot_ccdf_by(events: pd.DataFrame, key: str, output: Path, title: str, max_groups: int = 12) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    groups = []
    for value, sub in events.groupby(key, sort=True):
        groups.append((value, len(sub), sub))
    groups.sort(key=lambda item: item[1], reverse=True)
    for value, _, sub in groups[:max_groups]:
        x, y = ccdf(sub["collapse_size"])
        if x.size:
            ax.loglog(x, y, marker="o", markersize=2.5, linewidth=1.1, label=str(value))
    ax.set_xlabel("collapse_size")
    ax.set_ylabel("P(S >= s)")
    ax.set_title(title)
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_frequency_figures(events: pd.DataFrame, output_dir: Path) -> list[str]:
    figures: list[str] = []
    if events.empty:
        return figures
    for key, filename, title in [
        ("investment_income_propensity", "ccdf_by_c.png", "Collapse size-frequency by c"),
        ("money_distribution", "ccdf_by_money.png", "Collapse size-frequency by initial money"),
        ("income_distribution_rule", "ccdf_by_income_rule.png", "Collapse size-frequency by income allocation"),
        ("spending_label", "ccdf_by_spending.png", "Collapse size-frequency by spending mechanism"),
        ("topology_label", "ccdf_by_topology.png", "Collapse size-frequency by topology"),
        ("growth_rule", "ccdf_by_growth_rule.png", "Collapse size-frequency by growth rule"),
    ]:
        path = output_dir / filename
        plot_ccdf_by(events, key, path, title)
        figures.append(filename)
    return figures


def tail_fit_table(
    summary: pd.DataFrame,
    events: pd.DataFrame,
    min_tail: int,
    bootstrap: int,
    bootstrap_seed: int,
    max_xmin_candidates: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    candidates = summary[
        (summary["event_count"] >= min_tail)
        & (summary["event_large_event_rate"] > 0.0)
        & (summary["event_large_event_rate"] < 0.98)
    ].copy()
    if candidates.empty:
        return pd.DataFrame()
    candidates = candidates.sort_values(
        ["event_count", "event_large_event_rate", "propagated_share_total"],
        ascending=[False, False, False],
    ).head(160)
    for index, row in enumerate(candidates.itertuples(index=False), start=1):
        sub = events[events["scenario_id"].eq(row.scenario_id)]
        sizes = sub["collapse_size"].to_numpy(dtype=np.int64)
        fit = fit_series(
            sizes,
            xmax=int(row.n_nodes),
            min_tail=min_tail,
            max_candidates=max_xmin_candidates,
            bootstrap=bootstrap,
            bootstrap_seed=bootstrap_seed + index * 19,
        )
        rows.append(
            {
                "scenario_id": row.scenario_id,
                "scenario_base_id": row.scenario_base_id,
                "c": row.c,
                "money_distribution": row.money_distribution,
                "income_distribution_rule": row.income_distribution_rule,
                "growth_rule": row.growth_rule,
                "spending_label": row.spending_label,
                "topology_label": row.topology_label,
                **fit,
            }
        )
    return pd.DataFrame(rows)


def soc_screen(summary: pd.DataFrame, tail: pd.DataFrame) -> pd.DataFrame:
    merged = summary.copy()
    if not tail.empty:
        tail_cols = [
            "scenario_id",
            "fit_status",
            "alpha",
            "bootstrap_p",
            "bounded_alpha",
            "bounded_bootstrap_p",
            "pl_vs_exponential_R",
            "pl_vs_lognormal_R",
        ]
        available = [col for col in tail_cols if col in tail.columns]
        merged = merged.merge(tail[available], on="scenario_id", how="left")
    else:
        merged["fit_status"] = ""
    for col in [
        "alpha",
        "bootstrap_p",
        "bounded_alpha",
        "bounded_bootstrap_p",
        "pl_vs_exponential_R",
        "pl_vs_lognormal_R",
    ]:
        if col not in merged:
            merged[col] = np.nan

    merged["gate_event_count"] = merged["event_count"] >= 30
    merged["gate_not_saturated"] = merged["event_occupancy"] < 0.80
    merged["gate_has_transition"] = merged["event_large_event_rate"].between(0.02, 0.90)
    merged["gate_propagation"] = merged["propagated_share_total"] >= 0.15
    merged["gate_tail_plausible"] = (
        (merged["fit_status"].eq("ok"))
        & (
            (merged["bootstrap_p"].fillna(-1) >= 0.10)
            | (merged["bounded_bootstrap_p"].fillna(-1) >= 0.10)
        )
    )
    merged["gate_alternative_not_better"] = (
        (merged["pl_vs_exponential_R"].fillna(-1) >= 0)
        | (merged["pl_vs_lognormal_R"].fillna(-1) >= 0)
    )
    gate_cols = [
        "gate_event_count",
        "gate_not_saturated",
        "gate_has_transition",
        "gate_propagation",
        "gate_tail_plausible",
        "gate_alternative_not_better",
    ]
    merged["soc_screen_score"] = merged[gate_cols].sum(axis=1).astype(int)
    merged["quick_soc_candidate"] = merged["soc_screen_score"] >= 5
    return merged.sort_values(
        ["soc_screen_score", "event_large_event_rate", "propagated_share_total"],
        ascending=[False, False, False],
    )


def plot_global_phase(summary: pd.DataFrame, soc: pd.DataFrame, output_dir: Path, top_n: int) -> list[str]:
    base = (
        summary.groupby("scenario_base_id", as_index=False)
        .agg(max_large_rate=("event_large_event_rate", "max"), max_mean_fraction=("mean_event_fraction", "max"))
        .sort_values(["max_large_rate", "max_mean_fraction"], ascending=False)
        .head(top_n)
    )
    chosen = summary[summary["scenario_base_id"].isin(base["scenario_base_id"])].copy()
    chosen["label"] = chosen.apply(scenario_label, axis=1)
    order = (
        chosen.groupby("label")["event_large_event_rate"].max().sort_values(ascending=False).index
    )
    matrix = (
        chosen.groupby(["label", "c"], as_index=False)["event_large_event_rate"]
        .mean()
        .pivot(index="label", columns="c", values="event_large_event_rate")
        .reindex(order)
        .fillna(0.0)
    )
    path1 = output_dir / "global_cascade_phase_map.png"
    heatmap(matrix, path1, "Top scenario cascade phase map", "large-event rate", "viridis", 0.0, 1.0)

    soc_chosen = soc[soc["scenario_base_id"].isin(base["scenario_base_id"])].copy()
    soc_chosen["label"] = soc_chosen.apply(scenario_label, axis=1)
    matrix2 = (
        soc_chosen.groupby(["label", "c"], as_index=False)["soc_screen_score"]
        .mean()
        .pivot(index="label", columns="c", values="soc_screen_score")
        .reindex(order)
        .fillna(0.0)
    )
    path2 = output_dir / "global_soc_screen_phase_map.png"
    heatmap(matrix2, path2, "Top scenario quick SOC-screen phase map", "quick SOC-screen score", "cividis", 0.0, 6.0)
    return [path1.name, path2.name]


def plot_top_candidate_ccdfs(soc: pd.DataFrame, events: pd.DataFrame, output: Path, top_n: int = 12) -> None:
    candidates = soc.head(top_n)
    cols = 3
    rows = math.ceil(len(candidates) / cols) if len(candidates) else 1
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.2, rows * 3.2), squeeze=False)
    for ax in axes.ravel():
        ax.set_visible(False)
    for ax, row in zip(axes.ravel(), candidates.itertuples(index=False)):
        ax.set_visible(True)
        sub = events[events["scenario_id"].eq(row.scenario_id)]
        x, y = ccdf(sub["collapse_size"])
        if x.size:
            ax.loglog(x, y, marker="o", markersize=2.3, linewidth=1.0)
        ax.set_title(
            f"{row.money_distribution}/{row.income_distribution_rule}/"
            f"{row.spending_label}/{row.topology_label}/c={row.c:.2f}\n"
            f"score={row.soc_screen_score}, events={row.event_count}",
            fontsize=8,
        )
        ax.grid(True, which="both", alpha=0.25)
        ax.set_xlabel("S")
        ax.set_ylabel("P(S>=s)")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> str:
    if df.empty:
        return "（无记录）"
    sub = df[columns].head(max_rows).copy()
    def fmt(value: object) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, float):
            return f"{value:.4g}"
        text = str(value)
        return text.replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = [
        "| " + " | ".join(fmt(row[col]) for col in columns) + " |"
        for _, row in sub.iterrows()
    ]
    return "\n".join([header, sep, *body])


def write_report(
    report_path: Path,
    input_dir: Path,
    output_dir: Path,
    metadata: dict[str, object],
    summary: pd.DataFrame,
    soc: pd.DataFrame,
    tail: pd.DataFrame,
    figures: list[str],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    top_large = summary.sort_values(
        ["event_large_event_rate", "mean_event_fraction", "propagated_share_total"],
        ascending=False,
    )
    top_soc = soc.sort_values(
        ["soc_screen_score", "event_large_event_rate", "propagated_share_total"],
        ascending=False,
    )
    candidate_count = int(soc["quick_soc_candidate"].sum()) if "quick_soc_candidate" in soc else 0
    saturated = int((summary["event_occupancy"] >= 0.80).sum())
    rows = [
        "# 信贷网络完备场景扫描与 SOC 相图报告 v1",
        "",
        f"生成时间：{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## 1. 扫描范围",
        "",
        f"- 原始扫描目录：`{input_dir}`",
        f"- 分析目录：`{output_dir}`",
        f"- run 数：{metadata.get('run_count', len(summary))}",
        f"- avalanche 事件数：{metadata.get('event_count', 0)}",
        f"- scenario 数：{metadata.get('scenario_count', summary['scenario_id'].nunique())}",
        f"- scenario base 数：{metadata.get('scenario_base_count', summary['scenario_base_id'].nunique())}",
        "",
        "本轮扫描覆盖本金初始化、收入分配、增长规则、支出参数、显式拓扑结构和 `c=0.10..0.80`。这是全因子筛选，用于形成相图和挑选 SOC 候选；严格 SOC 推断仍需有限尺寸和平稳性复核。",
        "",
        "## 2. 级联失效规模相图",
        "",
    ]
    for figure in figures:
        if figure.startswith("cascade") or figure.startswith("large") or figure.startswith("global_cascade"):
            rows.append(f"![{figure}](../results/{output_dir.name}/{figure})")
            rows.append("")
    rows.extend(
        [
            "级联规模最高的场景如下：",
            "",
            markdown_table(
                top_large,
                [
                    "c",
                    "money_distribution",
                    "income_distribution_rule",
                    "growth_rule",
                    "spending_label",
                    "topology_label",
                    "event_large_event_rate",
                    "mean_event_fraction",
                    "propagated_share_total",
                    "event_occupancy",
                ],
                20,
            ),
            "",
            "## 3. SOC 快速筛选相图",
            "",
            "SOC 快速筛选不是最终证明。它只是把事件数、非饱和占用、级联转变、传播新增占比、尾部拟合和替代分布对照合成一个 0-6 分的候选指标。",
            "",
            f"- 快速候选数：{candidate_count}",
            f"- 近持续失败/饱和场景数（event occupancy >= 0.80）：{saturated}",
            "",
        ]
    )
    for figure in figures:
        if figure.startswith("global_soc"):
            rows.append(f"![{figure}](../results/{output_dir.name}/{figure})")
            rows.append("")
    rows.extend(
        [
            "SOC 快速筛选分数最高的场景如下：",
            "",
            markdown_table(
                top_soc,
                [
                    "soc_screen_score",
                    "quick_soc_candidate",
                    "c",
                    "money_distribution",
                    "income_distribution_rule",
                    "growth_rule",
                    "spending_label",
                    "topology_label",
                    "event_large_event_rate",
                    "propagated_share_total",
                    "event_occupancy",
                    "bootstrap_p",
                    "bounded_bootstrap_p",
                    "pl_vs_lognormal_R",
                ],
                25,
            ),
            "",
            "## 4. 级联失效规模-频率关系图",
            "",
        ]
    )
    for figure in figures:
        if figure.startswith("ccdf") or figure.startswith("top_candidate"):
            rows.append(f"![{figure}](../results/{output_dir.name}/{figure})")
            rows.append("")
    rows.extend(
        [
            "## 5. 尾部拟合摘要",
            "",
            markdown_table(
                tail.sort_values(["fit_status", "bootstrap_p"], ascending=[True, False])
                if not tail.empty
                else tail,
                [
                    "c",
                    "money_distribution",
                    "income_distribution_rule",
                    "growth_rule",
                    "spending_label",
                    "topology_label",
                    "events",
                    "fit_status",
                    "xmin",
                    "alpha",
                    "bootstrap_p",
                    "bounded_alpha",
                    "bounded_bootstrap_p",
                    "pl_vs_exponential_R",
                    "pl_vs_lognormal_R",
                ],
                25,
            ),
            "",
            "## 6. 当前判定",
            "",
            "本轮完备场景扫描可以给出两个相图层面的结论：",
            "",
            "1. 级联失效规模相图：高 `c`、高支出倾向、biased 收入分配、重尾本金和部分稀疏/异质拓扑会显著推高大级联率和平均规模。",
            "2. SOC 相图：出现大级联或重尾的区域不等同于严格 SOC。凡是 event occupancy 接近 1、传播新增占比低、或尾部被替代分布更好解释的区域，应解释为过载/持续失败区，而不是 SOC。",
            "",
            "最终 SOC 推断仍遵循项目定义：大级联出现 < 稳健级联转变 < 重尾 < 可信幂律 < 严格 SOC。后续如果要提升某个候选区，需要对该候选继续做 `N` 扩展、长时平稳性、重复违约与机制消融。",
            "",
        ]
    )
    report_path.write_text("\n".join(rows), encoding="utf-8")


def main() -> None:
    args = parse_args()
    ensure_dir(args.output_dir)
    runs = read_csv(args.input_dir / "run_summary.csv")
    events = read_csv(args.input_dir / "avalanche_events.csv")
    summary = read_csv(args.input_dir / "scenario_summary.csv")
    metadata = json.loads((args.input_dir / "metadata.json").read_text(encoding="utf-8"))

    if "propagated_default_count" not in events and not events.empty:
        events["propagated_default_count"] = (
            events["collapse_size"] - events["initial_default_count"]
        ).clip(lower=0)

    figures: list[str] = []
    figures.extend(plot_axis_heatmaps(summary, args.output_dir))
    figures.extend(plot_frequency_figures(events, args.output_dir))
    tail = tail_fit_table(
        summary,
        events,
        min_tail=args.min_tail,
        bootstrap=args.bootstrap,
        bootstrap_seed=args.bootstrap_seed,
        max_xmin_candidates=args.max_xmin_candidates,
    )
    soc = soc_screen(summary, tail)
    figures.extend(plot_global_phase(summary, soc, args.output_dir, args.top_scenarios))
    top_ccdf = args.output_dir / "top_candidate_ccdf_grid.png"
    plot_top_candidate_ccdfs(soc, events, top_ccdf)
    figures.append(top_ccdf.name)

    summary.to_csv(args.output_dir / "scenario_summary_enriched.csv", index=False)
    tail.to_csv(args.output_dir / "tail_fit_screen.csv", index=False)
    soc.to_csv(args.output_dir / "soc_screen_table.csv", index=False)
    write_report(args.report, args.input_dir, args.output_dir, metadata, summary, soc, tail, figures)

    analysis_metadata = {
        "created_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "input_dir": str(args.input_dir),
        "output_dir": str(args.output_dir),
        "report": str(args.report),
        "figures": figures,
        "min_tail": args.min_tail,
        "bootstrap": args.bootstrap,
        "tail_fit_count": int(len(tail)),
        "quick_soc_candidate_count": int(soc["quick_soc_candidate"].sum()),
    }
    (args.output_dir / "analysis_metadata.json").write_text(
        json.dumps(analysis_metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(analysis_metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
