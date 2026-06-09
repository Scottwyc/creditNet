#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_comprehensive_scenario_scan as base

CST = ZoneInfo("Asia/Shanghai")
DEFAULT_PERIOD_DIR = ROOT / "results" / "credit_soc_comprehensive_scan_20260608_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze the timestep-level SOC counterfactual comprehensive scan."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--period-end-dir", type=Path, default=DEFAULT_PERIOD_DIR)
    parser.add_argument("--min-tail", type=int, default=30)
    parser.add_argument("--bootstrap", type=int, default=20)
    parser.add_argument("--bootstrap-seed", type=int, default=2026061000)
    parser.add_argument("--max-xmin-candidates", type=int, default=200)
    parser.add_argument("--top-scenarios", type=int, default=36)
    return parser.parse_args()


def ensure_timestep_columns(summary: pd.DataFrame) -> pd.DataFrame:
    summary = summary.copy()
    if "event_timestep_rate" not in summary:
        summary["event_timestep_rate"] = summary["event_occupancy"]
    if "event_period_occupancy" not in summary:
        summary["event_period_occupancy"] = np.nan
    summary["event_occupancy"] = summary["event_timestep_rate"]
    return summary


def phase_summary_by_c(summary: pd.DataFrame) -> pd.DataFrame:
    return (
        summary.groupby("c", as_index=False)
        .agg(
            scenarios=("scenario_id", "nunique"),
            mean_large_event_rate=("event_large_event_rate", "mean"),
            mean_event_fraction=("mean_event_fraction", "mean"),
            mean_event_timestep_rate=("event_timestep_rate", "mean"),
            mean_event_period_occupancy=("event_period_occupancy", "mean"),
            mean_events_per_period=("events_per_period", "mean"),
            mean_propagated_share=("propagated_share_total", "mean"),
            mean_repeat_default_share=("mean_repeat_default_share", "mean"),
            saturated_scenarios=("event_timestep_rate", lambda x: int((x >= 0.80).sum())),
        )
        .sort_values("c")
    )


def axis_effect_summary(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for axis in [
        "money_distribution",
        "income_distribution_rule",
        "growth_rule",
        "spending_label",
        "topology_label",
    ]:
        grouped = (
            summary.groupby(axis, as_index=False)
            .agg(
                scenarios=("scenario_id", "nunique"),
                mean_large_event_rate=("event_large_event_rate", "mean"),
                mean_event_fraction=("mean_event_fraction", "mean"),
                mean_event_timestep_rate=("event_timestep_rate", "mean"),
                mean_event_period_occupancy=("event_period_occupancy", "mean"),
                mean_propagated_share=("propagated_share_total", "mean"),
                mean_repeat_default_share=("mean_repeat_default_share", "mean"),
            )
            .rename(columns={axis: "level"})
        )
        grouped.insert(0, "axis", axis)
        rows.append(grouped)
    return pd.concat(rows, ignore_index=True)


def soc_gate_summary(soc: pd.DataFrame) -> pd.DataFrame:
    gate_cols = [col for col in soc.columns if col.startswith("gate_")]
    return pd.DataFrame(
        [
            {
                "gate": col,
                "passed": int(soc[col].sum()),
                "total": int(len(soc)),
                "pass_rate": float(soc[col].mean()) if len(soc) else 0.0,
            }
            for col in gate_cols
        ]
        + [
            {
                "gate": "quick_soc_candidate",
                "passed": int(soc["quick_soc_candidate"].sum())
                if "quick_soc_candidate" in soc
                else 0,
                "total": int(len(soc)),
                "pass_rate": float(soc["quick_soc_candidate"].mean())
                if "quick_soc_candidate" in soc and len(soc)
                else 0.0,
            }
        ]
    )


def timestep_tail_fit_table(
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
        & (summary["max_event_size"] >= 3)
    ].copy()
    if candidates.empty:
        return pd.DataFrame()
    candidates = candidates.sort_values(
        [
            "p99_event_size",
            "max_event_size",
            "propagated_share_total",
            "event_count",
        ],
        ascending=[False, False, False, False],
    ).head(160)
    for index, row in enumerate(candidates.itertuples(index=False), start=1):
        sub = events[events["scenario_id"].eq(row.scenario_id)]
        sizes = sub["collapse_size"].to_numpy(dtype=np.int64)
        fit = base.fit_series(
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
                "event_count": row.event_count,
                "max_event_size": row.max_event_size,
                "p99_event_size": row.p99_event_size,
                "event_timestep_rate": row.event_timestep_rate,
                "propagated_share_total": row.propagated_share_total,
                **fit,
            }
        )
    return pd.DataFrame(rows)


def plot_protocol_by_c(
    timestep: pd.DataFrame,
    period: pd.DataFrame,
    output: Path,
) -> pd.DataFrame:
    t = phase_summary_by_c(timestep)
    p = (
        period.groupby("c", as_index=False)
        .agg(
            period_mean_large_event_rate=("event_large_event_rate", "mean"),
            period_mean_event_fraction=("mean_event_fraction", "mean"),
            period_mean_event_occupancy=("event_occupancy", "mean"),
            period_mean_propagated_share=("propagated_share_total", "mean"),
        )
        .sort_values("c")
    )
    merged = t.merge(p, on="c", how="left")
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.2), sharex=True)
    specs = [
        ("mean_large_event_rate", "period_mean_large_event_rate", "large-event rate"),
        ("mean_event_fraction", "period_mean_event_fraction", "mean collapse fraction"),
        ("mean_event_timestep_rate", "period_mean_event_occupancy", "event occupancy/rate"),
        ("mean_propagated_share", "period_mean_propagated_share", "propagated share"),
    ]
    for ax, (t_col, p_col, title) in zip(axes.ravel(), specs):
        ax.plot(merged["c"], merged[t_col], marker="o", label="timestep")
        ax.plot(merged["c"], merged[p_col], marker="s", label="period_end")
        ax.set_title(title)
        ax.set_xlabel("c")
        ax.grid(True, alpha=0.25)
        ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return merged


def plot_protocol_scatter(
    timestep: pd.DataFrame,
    period: pd.DataFrame,
    output: Path,
) -> pd.DataFrame:
    cols = [
        "scenario_id",
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
    ]
    merged = timestep[cols].merge(
        period[cols],
        on="scenario_id",
        how="inner",
        suffixes=("_timestep", "_period"),
    )
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.8))
    scatter_specs = [
        ("event_large_event_rate_period", "event_large_event_rate_timestep", "large-event rate"),
        ("mean_event_fraction_period", "mean_event_fraction_timestep", "mean collapse fraction"),
    ]
    for ax, (x_col, y_col, title) in zip(axes, scatter_specs):
        ax.scatter(merged[x_col], merged[y_col], s=8, alpha=0.35)
        lim = max(float(merged[[x_col, y_col]].max().max()), 1e-9)
        ax.plot([0, lim], [0, lim], color="black", linewidth=1.0, alpha=0.6)
        ax.set_xlabel("period_end")
        ax.set_ylabel("timestep")
        ax.set_title(title)
        ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return merged


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> str:
    return base.markdown_table(df, columns, max_rows)


def write_report(
    report_path: Path,
    input_dir: Path,
    output_dir: Path,
    period_dir: Path,
    metadata: dict[str, object],
    summary: pd.DataFrame,
    phase_by_c: pd.DataFrame,
    axis_summary: pd.DataFrame,
    soc: pd.DataFrame,
    gate_summary: pd.DataFrame,
    tail: pd.DataFrame,
    protocol_by_c: pd.DataFrame | None,
    protocol_match: pd.DataFrame | None,
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
    small_tail_candidate_count = (
        int(soc["small_tail_candidate"].sum()) if "small_tail_candidate" in soc else 0
    )
    command_args = metadata.get("command_args")
    if not command_args and metadata.get("shard_metadata"):
        command_args = metadata["shard_metadata"][0].get("command_args", {})
    command_args = command_args or {}
    timestep_saturated = int((summary["event_timestep_rate"] >= 0.80).sum())
    period_mean_delta = None
    if protocol_match is not None and not protocol_match.empty:
        period_mean_delta = {
            "large_event_rate": float(
                (
                    protocol_match["event_large_event_rate_timestep"]
                    - protocol_match["event_large_event_rate_period"]
                ).mean()
            ),
            "mean_event_fraction": float(
                (
                    protocol_match["mean_event_fraction_timestep"]
                    - protocol_match["mean_event_fraction_period"]
                ).mean()
            ),
        }
    rows = [
        "# timestep尺度信贷网络SOC对照实验报告 v2",
        "",
        f"生成时间：{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## 1. 实验协议",
        "",
        f"- timestep扫描目录：`{input_dir}`",
        f"- 分析目录：`{output_dir}`",
        f"- period_end 对照目录：`{period_dir}`",
        f"- run 数：{metadata.get('run_count', 0)}",
        f"- avalanche 事件数：{metadata.get('event_count', 0)}",
        f"- scenario 数：{metadata.get('scenario_count', summary['scenario_id'].nunique())}",
        f"- 每宏观期微步上限：`max_period_length_steps={command_args.get('max_period_length_steps', '未设置')}`",
        "",
        "本轮保持上一轮完备扫描的场景轴：初始本金分布、收入分配、信贷增长规则、支出机制、网络拓扑和 `c=0.10..0.80`。区别只在事件观测尺度：原协议在 `period_end` 统一结算检查；本协议把一个宏观期的计划 `K_t` 个单位信贷尝试拆成 `K_t` 个微步，每个成功或失败的 credit `time_step` 后立即按 `1/K_t` 缩放结算支出/收入、检查违约，并在下一次信贷增长前完成整次 avalanche 清算。",
        "",
        "因此，本报告里的 `event_timestep_rate` 是 avalanche 次数除以实际信贷尝试 time_step 数；`event_period_occupancy` 只是有事件的宏观期占比。SOC 快筛里的非饱和门槛使用 `event_timestep_rate < 0.80`，不再使用 period_end 报告中的 period 占用率。",
        "",
        "## 2. 与 period_end 的总体差异",
        "",
    ]
    if protocol_mean := period_mean_delta:
        rows.extend(
            [
                f"- 同场景平均大级联事件率变化：{protocol_mean['large_event_rate']:.4g}",
                f"- 同场景平均事件规模比例变化：{protocol_mean['mean_event_fraction']:.4g}",
                "",
            ]
        )
    for figure in figures:
        if figure.startswith("protocol_"):
            rows.append(f"![{figure}](../results/{output_dir.name}/{figure})")
            rows.append("")
    rows.extend(
        [
            "按 `c` 聚合的 timestep 结果：",
            "",
            markdown_table(
                phase_by_c,
                [
                    "c",
                    "scenarios",
                    "mean_large_event_rate",
                    "mean_event_fraction",
                    "mean_event_timestep_rate",
                    "mean_event_period_occupancy",
                    "mean_propagated_share",
                    "mean_repeat_default_share",
                ],
                12,
            ),
            "",
            "## 3. 级联失效相图",
            "",
        ]
    )
    for figure in figures:
        if figure.startswith("cascade") or figure.startswith("large") or figure.startswith("global_cascade"):
            rows.append(f"![{figure}](../results/{output_dir.name}/{figure})")
            rows.append("")
    rows.extend(
        [
            "级联规模最高的场景：",
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
                    "event_timestep_rate",
                    "propagated_share_total",
                    "mean_repeat_default_share",
                ],
                20,
            ),
            "",
            "## 4. SOC 快筛相图",
            "",
            f"- 快速候选数：{candidate_count}",
            f"- 小尺度尾部候选数（未达到 10%N 尺度门槛）：{small_tail_candidate_count}",
            f"- timestep 近饱和场景数（event_timestep_rate >= 0.80）：{timestep_saturated}",
            "",
            markdown_table(gate_summary, ["gate", "passed", "total", "pass_rate"], 20),
            "",
        ]
    )
    for figure in figures:
        if figure.startswith("global_soc"):
            rows.append(f"![{figure}](../results/{output_dir.name}/{figure})")
            rows.append("")
    rows.extend(
        [
            "SOC 快筛分数最高的场景：",
            "",
            markdown_table(
                top_soc,
                [
                    "soc_screen_score",
                    "quick_soc_candidate",
                    "small_tail_candidate",
                    "c",
                    "money_distribution",
                    "income_distribution_rule",
                    "growth_rule",
                    "spending_label",
                    "topology_label",
                    "event_large_event_rate",
                    "event_timestep_rate",
                    "propagated_share_total",
                    "bootstrap_p",
                    "bounded_bootstrap_p",
                    "pl_vs_lognormal_R",
                ],
                25,
            ),
            "",
            "## 5. 级联规模-频率关系",
            "",
        ]
    )
    for figure in figures:
        if figure.startswith("ccdf") or figure.startswith("top_candidate"):
            rows.append(f"![{figure}](../results/{output_dir.name}/{figure})")
            rows.append("")
    rows.extend(
        [
            "## 6. 尾部拟合摘要",
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
            "## 7. 当前判定",
            "",
            "timestep 协议可以回答一个明确问题：上一轮 period_end 大崩塌是否主要来自较粗的批量结算尺度。如果 timestep 结算后大级联率、平均规模和同步 initial defaults 明显下降，就说明原大事件有相当部分由 period_end 批量聚合放大；如果仍在多个相邻 `c` 和多类场景中存在稳定跨尺度事件，并通过尾部、平稳性和有限尺寸门槛，才可升级为 timestep-SOC 候选。",
            "",
            "本报告的 SOC 结论仍遵循项目层级：大级联出现 < 稳健级联转变 < 重尾 < 可信幂律 < 严格 SOC。timestep 下即使每个微步都可能触发 avalanche，也不能把高频事件本身直接等同于 SOC；必须结合规模分布、传播分量、重复违约、长期平稳和有限尺寸标度。",
            "",
            "## 8. 轴效应摘要",
            "",
            markdown_table(
                axis_summary.sort_values(["axis", "mean_event_fraction"], ascending=[True, False]),
                [
                    "axis",
                    "level",
                    "scenarios",
                    "mean_large_event_rate",
                    "mean_event_fraction",
                    "mean_event_timestep_rate",
                    "mean_propagated_share",
                    "mean_repeat_default_share",
                ],
                40,
            ),
            "",
        ]
    )
    report_path.write_text("\n".join(rows), encoding="utf-8")


def main() -> None:
    args = parse_args()
    base.ensure_dir(args.output_dir)
    runs = base.read_csv(args.input_dir / "run_summary.csv")
    events = base.read_csv(args.input_dir / "avalanche_events.csv")
    summary = ensure_timestep_columns(base.read_csv(args.input_dir / "scenario_summary.csv"))
    metadata = json.loads((args.input_dir / "metadata.json").read_text(encoding="utf-8"))

    if "propagated_default_count" not in events and not events.empty:
        events["propagated_default_count"] = (
            events["collapse_size"] - events["initial_default_count"]
        ).clip(lower=0)

    figures: list[str] = []
    figures.extend(base.plot_axis_heatmaps(summary, args.output_dir))
    figures.extend(base.plot_frequency_figures(events, args.output_dir))
    tail = timestep_tail_fit_table(
        summary,
        events,
        min_tail=args.min_tail,
        bootstrap=args.bootstrap,
        bootstrap_seed=args.bootstrap_seed,
        max_xmin_candidates=args.max_xmin_candidates,
    )
    soc = base.soc_screen(summary, tail)
    soc["small_tail_candidate"] = soc["quick_soc_candidate"].astype(bool)
    soc["gate_scale_range"] = soc["max_event_size"] >= (0.10 * soc["n_nodes"])
    soc["quick_soc_candidate"] = (
        soc["small_tail_candidate"].astype(bool) & soc["gate_scale_range"].astype(bool)
    )
    figures.extend(base.plot_global_phase(summary, soc, args.output_dir, args.top_scenarios))
    top_ccdf = args.output_dir / "top_candidate_ccdf_grid.png"
    base.plot_top_candidate_ccdfs(soc, events, top_ccdf)
    figures.append(top_ccdf.name)

    phase_by_c = phase_summary_by_c(summary)
    axis_summary = axis_effect_summary(summary)
    gates = soc_gate_summary(soc)
    top_large = summary.sort_values(
        ["event_large_event_rate", "mean_event_fraction", "propagated_share_total"],
        ascending=False,
    ).head(80)
    protocol_by_c = None
    protocol_match = None
    if args.period_end_dir.exists():
        period_summary = base.read_csv(args.period_end_dir / "scenario_summary.csv")
        protocol_by_c = plot_protocol_by_c(
            summary,
            period_summary,
            args.output_dir / "protocol_compare_by_c.png",
        )
        protocol_match = plot_protocol_scatter(
            summary,
            period_summary,
            args.output_dir / "protocol_scenario_scatter.png",
        )
        figures.extend(["protocol_compare_by_c.png", "protocol_scenario_scatter.png"])
        protocol_by_c.to_csv(args.output_dir / "protocol_compare_by_c.csv", index=False)
        protocol_match.to_csv(args.output_dir / "protocol_scenario_match.csv", index=False)

    summary.to_csv(args.output_dir / "scenario_summary_enriched.csv", index=False)
    phase_by_c.to_csv(args.output_dir / "phase_summary_by_c.csv", index=False)
    axis_summary.to_csv(args.output_dir / "axis_effect_summary.csv", index=False)
    tail.to_csv(args.output_dir / "tail_fit_screen.csv", index=False)
    soc.to_csv(args.output_dir / "soc_screen_table.csv", index=False)
    gates.to_csv(args.output_dir / "soc_gate_summary.csv", index=False)
    top_large.to_csv(args.output_dir / "top_cascade_scenarios.csv", index=False)
    write_report(
        args.report,
        args.input_dir,
        args.output_dir,
        args.period_end_dir,
        metadata,
        summary,
        phase_by_c,
        axis_summary,
        soc,
        gates,
        tail,
        protocol_by_c,
        protocol_match,
        figures,
    )

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
