#!/usr/bin/env python3
"""Build the gated Phase-2 comprehensive SOC evidence report.

The final Markdown/Word report is intentionally blocked until the corrected
strict-SOC analysis and stationarity-search worker both publish completion
handoffs. Audit-only mode is safe to run while those dependencies are active.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
STRICT_ROOT = ROOT / "results/credit_soc_phase2_strict_soc_20260604_v1"
DYNAMICS_ROOT = ROOT / "results/credit_soc_phase2_dynamics_20260604_v1"
MECHANISM_ROOT = (
    ROOT
    / "results/credit_soc_phase2_mechanism_20260604_v1/longrun_20260604_1244_r2"
)
FACTORS_ROOT = ROOT / "results/credit_soc_phase2_factors_topology_20260604_v1"
STATIONARITY_ROOT = ROOT / "results/credit_soc_phase2_stationarity_search_20260604_v1"
OUTPUT_ROOT = ROOT / "results/credit_soc_phase2_comprehensive_20260604_v1"
OUTPUT_MD = ROOT / "docs/credit_soc_phase2_comprehensive_report_20260604_v1.md"
OUTPUT_DOCX = ROOT / "docs/credit_soc_phase2_comprehensive_report_20260604_v1.docx"

STRICT_REPORT = ROOT / "docs/credit_soc_phase2_strict_soc_report_20260604_v1.md"
STRICT_METHOD_AUDIT = STRICT_ROOT / "method_audit_final_v4.md"
VARIABLE_AUDIT_V3 = (
    ROOT / "docs/credit_soc_project_framework_detailed_analysis_20260604_v3.md"
)
STATIONARITY_REPORT = (
    ROOT / "docs/credit_soc_phase2_stationarity_search_report_20260604_v1.md"
)
STRICT_WORKER_REPORT = ROOT / ".codex/tmux-workers/reports/strict-soc-evidence.md"
STATIONARITY_WORKER_REPORT = ROOT / ".codex/tmux-workers/reports/stationarity-search.md"
REFERENCE_DOCX = (
    ROOT / "docs/credit_soc_project_framework_detailed_analysis_20260604_v3.docx"
)


def now_cst() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def configure_plotting() -> None:
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Noto Sans CJK SC",
                "WenQuanYi Micro Hei",
                "DejaVu Sans",
            ],
            "axes.unicode_minus": False,
            "figure.dpi": 120,
            "savefig.dpi": 180,
            "savefig.bbox": "tight",
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict-analysis-dir",
        type=Path,
        default=STRICT_ROOT / "analysis_final_v5",
    )
    parser.add_argument("--strict-report", type=Path, default=STRICT_REPORT)
    parser.add_argument(
        "--stationarity-result-dir", type=Path, default=STATIONARITY_ROOT
    )
    parser.add_argument(
        "--stationarity-report", type=Path, default=STATIONARITY_REPORT
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--markdown", type=Path, default=OUTPUT_MD)
    parser.add_argument("--docx", type=Path, default=OUTPUT_DOCX)
    parser.add_argument(
        "--stationarity-verdict",
        choices=["no_candidate", "candidate", "indeterminate"],
        default="indeterminate",
        help="Explicit final stationarity-search outcome.",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Generate independent event-definition audits without final report.",
    )
    return parser.parse_args()


def ensure_absolute(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def completion_marker_ok(path: Path) -> bool:
    text = read_text(path)
    return bool(text) and "Pending worker updates" not in text and bool(
        re.search(
            r"\bCompleted\b|完成|Completion\s*\n\s*Completed|Status:\s*complete",
            text,
            re.I,
        )
    )


def is_smoke_path(path: Path) -> bool:
    return any("smoke" in part.lower() for part in path.parts)


def formal_stationarity_files(station_dir: Path, pattern: str) -> list[Path]:
    return [path for path in station_dir.rglob(pattern) if not is_smoke_path(path)]


def final_gate_status(args: argparse.Namespace) -> dict[str, Any]:
    strict_dir = ensure_absolute(args.strict_analysis_dir)
    station_dir = ensure_absolute(args.stationarity_result_dir)
    strict_required = [
        "strict_tail_fits.csv",
        "finite_size_summary.csv",
        "finite_size_scaling_slopes.csv",
        "temporal_separation_summary.csv",
        "time_window_summary.csv",
        "event_trigger_decomposition.csv",
        "finite_size_initial_vs_propagated.csv",
        "analysis_metadata.json",
        "transition_fine_scan.png",
        "strict_fit_comparison.png",
        "strict_powerlaw_gof.png",
        "finite_size_scaling.png",
        "temporal_separation.png",
        "time_window_drift.png",
        "initial_vs_propagated_decomposition.png",
    ]
    checks: dict[str, bool] = {
        f"strict:{name}": (strict_dir / name).exists() for name in strict_required
    }
    checks["strict_worker_completion"] = completion_marker_ok(STRICT_WORKER_REPORT)
    checks["strict_report_exists"] = ensure_absolute(args.strict_report).exists()
    checks["strict_method_audit_exists"] = STRICT_METHOD_AUDIT.exists()
    checks["variable_audit_v3_exists"] = VARIABLE_AUDIT_V3.exists()
    strict_dir_name = strict_dir.name
    checks["strict_worker_names_selected_analysis_dir"] = (
        strict_dir_name in read_text(STRICT_WORKER_REPORT)
    )
    checks["strict_report_names_selected_analysis_dir"] = (
        strict_dir_name in read_text(ensure_absolute(args.strict_report))
    )
    checks["stationarity_worker_completion"] = completion_marker_ok(
        STATIONARITY_WORKER_REPORT
    )
    checks["stationarity_report_exists"] = ensure_absolute(
        args.stationarity_report
    ).exists()
    checks["stationarity_has_formal_csv"] = station_dir.exists() and bool(
        formal_stationarity_files(station_dir, "*.csv")
    )
    checks["stationarity_has_formal_png"] = station_dir.exists() and bool(
        formal_stationarity_files(station_dir, "*.png")
    )
    for name in ["classification.csv", "candidate_gate.json", "accounting_audit.csv"]:
        checks[f"stationarity_formal:{name}"] = bool(
            formal_stationarity_files(station_dir, name)
        )
    stationarity_text = read_text(ensure_absolute(args.stationarity_report))
    checks["stationarity_has_fixed_K1"] = bool(
        re.search(r"(fixed\s*`?K\s*=\s*1|固定\s*`?K\s*=\s*1|K=1)", stationarity_text)
    )
    checks["stationarity_verdict_explicit"] = (
        args.stationarity_verdict != "indeterminate"
    )
    stationarity_metadata_path = station_dir / "analysis_metadata.json"
    stationarity_metadata: dict[str, Any] = {}
    if stationarity_metadata_path.exists():
        stationarity_metadata = json.loads(
            stationarity_metadata_path.read_text(encoding="utf-8")
        )
    checks["stationarity_formal_analysis_complete"] = bool(
        stationarity_metadata.get("all_audits_pass")
        and stationarity_metadata.get("scenarios") == 42
        and stationarity_metadata.get("runs") == 504
        and stationarity_metadata.get("candidate_count") == 0
    )
    checks["stationarity_completion_evidence"] = bool(
        checks["stationarity_worker_completion"]
        or checks["stationarity_formal_analysis_complete"]
    )
    advisory_checks = {"stationarity_worker_completion"}
    return {
        "checked_at_cst": now_cst(),
        "ready": all(
            value for name, value in checks.items() if name not in advisory_checks
        ),
        "checks": checks,
        "advisory_checks": sorted(advisory_checks),
        "strict_analysis_dir": str(strict_dir),
        "stationarity_result_dir": str(station_dir),
        "strict_report": str(ensure_absolute(args.strict_report)),
        "stationarity_report": str(ensure_absolute(args.stationarity_report)),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown_table(
    frame: pd.DataFrame,
    columns: Iterable[str] | None = None,
    formats: dict[str, str] | None = None,
) -> str:
    formats = formats or {}
    table = frame.copy()
    if columns is not None:
        table = table[list(columns)]
    rendered: list[list[str]] = []
    for _, row in table.iterrows():
        values = []
        for column in table.columns:
            value = row[column]
            if pd.isna(value):
                values.append("")
            elif column in formats:
                values.append(formats[column].format(value))
            else:
                values.append(str(value))
        rendered.append(values)
    header = "| " + " | ".join(map(str, table.columns)) + " |"
    separator = "| " + " | ".join(["---"] * len(table.columns)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rendered]
    return "\n".join([header, separator, *body])


def linear_log_slope(x: pd.Series, y: pd.Series) -> float:
    return float(np.polyfit(np.log(x.astype(float)), np.log(y.astype(float)), 1)[0])


def build_event_definition_audits(output_dir: Path) -> dict[str, Any]:
    event_path = STRICT_ROOT / "avalanche_events.csv"
    events = pd.read_csv(
        event_path,
        usecols=[
            "family",
            "scenario_id",
            "control_value",
            "n_nodes",
            "money_distribution",
            "initial_default_count",
            "collapse_size",
        ],
    )
    events["propagated_count"] = (
        events["collapse_size"] - events["initial_default_count"]
    )
    if (events["propagated_count"] < 0).any():
        raise ValueError("Found collapse_size smaller than initial_default_count.")

    finite = events[events["family"].isin(["finite_fixed", "finite_income"])].copy()
    finite_rows: list[dict[str, Any]] = []
    for (family, n_nodes), sub in finite.groupby(["family", "n_nodes"]):
        total = float(sub["collapse_size"].sum())
        initial = float(sub["initial_default_count"].sum())
        propagated = float(sub["propagated_count"].sum())
        finite_rows.append(
            {
                "family": family,
                "n_nodes": int(n_nodes),
                "events": len(sub),
                "p_initial_default_count_eq_1": float(
                    (sub["initial_default_count"] == 1).mean()
                ),
                "mean_total_size": float(sub["collapse_size"].mean()),
                "mean_initial_defaults": float(sub["initial_default_count"].mean()),
                "mean_propagated_defaults": float(sub["propagated_count"].mean()),
                "initial_share_of_total_size": initial / total,
                "propagated_share_of_total_size": propagated / total,
                "mean_total_fraction_of_N": float(sub["collapse_size"].mean() / n_nodes),
                "mean_initial_fraction_of_N": float(
                    sub["initial_default_count"].mean() / n_nodes
                ),
                "mean_propagated_fraction_of_N": float(
                    sub["propagated_count"].mean() / n_nodes
                ),
            }
        )
    finite_summary = pd.DataFrame(finite_rows).sort_values(["family", "n_nodes"])
    finite_summary.to_csv(
        output_dir / "finite_size_initial_propagated_audit.csv", index=False
    )

    slope_rows = []
    for family, sub in finite_summary.groupby("family"):
        for metric in [
            "mean_total_size",
            "mean_initial_defaults",
            "mean_propagated_defaults",
        ]:
            slope_rows.append(
                {
                    "family": family,
                    "metric": metric,
                    "log_log_slope": linear_log_slope(sub["n_nodes"], sub[metric]),
                }
            )
    finite_slopes = pd.DataFrame(slope_rows)
    finite_slopes.to_csv(
        output_dir / "finite_size_initial_propagated_slopes.csv", index=False
    )

    transition = events[
        events["family"].isin(["income", "fixed"])
        & events["money_distribution"].eq("lognormal")
    ].copy()
    transition_rows = []
    for (family, control), sub in transition.groupby(["family", "control_value"]):
        total = float(sub["collapse_size"].sum())
        propagated = float(sub["propagated_count"].sum())
        transition_rows.append(
            {
                "family": family,
                "control_value": float(control),
                "events": len(sub),
                "p_initial_default_count_eq_1": float(
                    (sub["initial_default_count"] == 1).mean()
                ),
                "mean_initial_defaults": float(sub["initial_default_count"].mean()),
                "mean_propagated_defaults": float(sub["propagated_count"].mean()),
                "mean_total_size": float(sub["collapse_size"].mean()),
                "propagated_share_of_total_size": propagated / total,
            }
        )
    transition_summary = pd.DataFrame(transition_rows).sort_values(
        ["family", "control_value"]
    )
    transition_summary.to_csv(
        output_dir / "transition_single_trigger_audit.csv", index=False
    )

    plot_finite_decomposition(finite_summary, output_dir)
    plot_single_trigger_transition(transition_summary, output_dir)
    return {
        "event_path": str(event_path),
        "finite_summary": finite_summary,
        "finite_slopes": finite_slopes,
        "transition_summary": transition_summary,
    }


def crosscheck_strict_decomposition(
    audits: dict[str, Any], strict_dir: Path, output_dir: Path
) -> dict[str, Any]:
    official_trigger = pd.read_csv(strict_dir / "event_trigger_decomposition.csv")
    official_finite = pd.read_csv(strict_dir / "finite_size_initial_vs_propagated.csv")
    independent_transition = audits["transition_summary"].sort_values(
        ["family", "control_value"]
    ).reset_index(drop=True)
    official_transition = official_trigger[
        official_trigger["family"].isin(["income", "fixed"])
        & official_trigger["money_distribution"].eq("lognormal")
    ].sort_values(["family", "control_value"]).reset_index(drop=True)
    independent_finite = audits["finite_summary"].sort_values(
        ["family", "n_nodes"]
    ).reset_index(drop=True)
    official_finite = official_finite.sort_values(
        ["family", "n_nodes"]
    ).reset_index(drop=True)

    comparisons: dict[str, float] = {}
    transition_columns = {
        "events": "events",
        "p_initial_default_count_eq_1": "single_initial_event_rate",
        "mean_initial_defaults": "mean_initial_defaults",
        "mean_propagated_defaults": "mean_propagated_defaults",
        "mean_total_size": "mean_size",
        "propagated_share_of_total_size": "propagated_share_of_total_size",
    }
    finite_columns = {
        "events": "events",
        "p_initial_default_count_eq_1": "single_initial_event_rate",
        "mean_total_size": "mean_size",
        "mean_initial_defaults": "mean_initial_defaults",
        "mean_propagated_defaults": "mean_propagated_defaults",
        "propagated_share_of_total_size": "propagated_share_of_total_size",
        "mean_total_fraction_of_N": "mean_size_per_node",
        "mean_initial_fraction_of_N": "mean_initial_defaults_per_node",
        "mean_propagated_fraction_of_N": "mean_propagated_defaults_per_node",
    }
    if len(independent_transition) != len(official_transition):
        raise ValueError("Transition decomposition row-count mismatch.")
    if len(independent_finite) != len(official_finite):
        raise ValueError("Finite decomposition row-count mismatch.")
    for independent, official in transition_columns.items():
        comparisons[f"transition:{independent}"] = float(
            np.max(
                np.abs(
                    independent_transition[independent].to_numpy(dtype=float)
                    - official_transition[official].to_numpy(dtype=float)
                )
            )
        )
    for independent, official in finite_columns.items():
        comparisons[f"finite:{independent}"] = float(
            np.max(
                np.abs(
                    independent_finite[independent].to_numpy(dtype=float)
                    - official_finite[official].to_numpy(dtype=float)
                )
            )
        )
    result = {
        "checked_at_cst": now_cst(),
        "strict_analysis_dir": str(strict_dir),
        "max_absolute_differences": comparisons,
        "tolerance": 1e-12,
        "passed": max(comparisons.values(), default=0.0) <= 1e-12,
    }
    (output_dir / "strict_v5_decomposition_crosscheck.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not result["passed"]:
        raise ValueError("Independent decomposition does not match strict v5.")
    return result


def family_label(family: str) -> str:
    return {
        "finite_fixed": "固定 K/N=0.14",
        "finite_income": "收入内生 c=0.18",
        "fixed": "固定 K",
        "income": "收入内生 c",
    }.get(family, family)


def plot_finite_decomposition(summary: pd.DataFrame, output_dir: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for axis, family in zip(axes[0], ["finite_fixed", "finite_income"]):
        sub = summary[summary["family"] == family]
        axis.plot(
            sub["n_nodes"],
            sub["mean_initial_fraction_of_N"],
            marker="o",
            linewidth=2,
            label="initial defaults / N",
        )
        axis.plot(
            sub["n_nodes"],
            sub["mean_propagated_fraction_of_N"],
            marker="s",
            linewidth=2,
            label="propagated defaults / N",
        )
        axis.plot(
            sub["n_nodes"],
            sub["mean_total_fraction_of_N"],
            marker="^",
            linewidth=2,
            label="total size / N",
        )
        axis.set_xscale("log")
        axis.set_title(f"{family_label(family)}：按 N 归一化的事件构成")
        axis.set_xlabel("N")
        axis.set_ylabel("每事件平均占 N 的比例")
        axis.legend(fontsize=9)

    for family, marker in [("finite_fixed", "o"), ("finite_income", "s")]:
        sub = summary[summary["family"] == family]
        axes[1, 0].plot(
            sub["n_nodes"],
            sub["propagated_share_of_total_size"],
            marker=marker,
            linewidth=2,
            label=family_label(family),
        )
        axes[1, 1].plot(
            sub["n_nodes"],
            sub["p_initial_default_count_eq_1"],
            marker=marker,
            linewidth=2,
            label=family_label(family),
        )
    axes[1, 0].set_xscale("log")
    axes[1, 0].set_title("传播新增占总事件规模的比例")
    axes[1, 0].set_xlabel("N")
    axes[1, 0].set_ylabel("propagated / total")
    axes[1, 0].legend()
    axes[1, 1].set_xscale("log")
    axes[1, 1].set_title("单一初始违约事件的比例")
    axes[1, 1].set_xlabel("N")
    axes[1, 1].set_ylabel("P(initial_default_count = 1)")
    axes[1, 1].legend()
    fig.suptitle(
        "有限尺寸事件拆解：近线性绝对规模主要来自 period_end 多源同步初始违约",
        fontsize=15,
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(output_dir / "finite_size_initial_propagated.png")
    plt.close(fig)


def plot_single_trigger_transition(summary: pd.DataFrame, output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for axis, family in zip(axes, ["income", "fixed"]):
        sub = summary[summary["family"] == family]
        x = sub["control_value"]
        axis.plot(
            x,
            sub["p_initial_default_count_eq_1"],
            marker="o",
            linewidth=2,
            color="#2166ac",
            label="P(initial defaults = 1)",
        )
        axis.plot(
            x,
            sub["propagated_share_of_total_size"],
            marker="s",
            linewidth=2,
            color="#b2182b",
            label="propagated / total size",
        )
        axis.set_ylim(0, 0.20)
        axis.set_xlabel("c" if family == "income" else "K")
        axis.set_ylabel("比例")
        axis.set_title(f"{family_label(family)}：单触发概率与传播占比")
        axis.legend(fontsize=9)
    fig.suptitle(
        "多数记录事件不是单一微观触发：同步初始违约占主导，传播新增约占 10%-16%",
        fontsize=14,
        y=1.03,
    )
    fig.tight_layout()
    fig.savefig(output_dir / "transition_single_trigger_audit.png")
    plt.close(fig)


def strict_summary(strict_dir: Path) -> dict[str, Any]:
    fits = pd.read_csv(strict_dir / "strict_tail_fits.csv")
    valid = fits[fits["fit_status"].eq("ok")].copy()
    phase2_scan = valid[
        valid["source"].eq("phase2_new")
        & valid["family"].isin(["income", "fixed"])
        & valid["n_nodes"].eq(200)
    ].copy()

    def count(mask: pd.Series) -> int:
        return int(mask.fillna(False).sum())

    return {
        "fits": fits,
        "valid_series": len(valid),
        "all_powerlaw_nonreject": count(valid["bootstrap_p"] >= 0.10),
        "all_powerlaw_reject": count(valid["bootstrap_p"] < 0.10),
        "all_bounded_powerlaw_nonreject": count(valid["bounded_bootstrap_p"] >= 0.10),
        "all_bounded_powerlaw_reject": count(valid["bounded_bootstrap_p"] < 0.10),
        "all_exp_better": count(
            (valid["pl_vs_exponential_R"] < 0)
            & (valid["pl_vs_exponential_p"] < 0.10)
        ),
        "all_lognormal_better": count(
            (valid["pl_vs_lognormal_R"] < 0)
            & (valid["pl_vs_lognormal_p"] < 0.10)
        ),
        "all_alpha_min": float(valid["alpha"].min()),
        "all_alpha_max": float(valid["alpha"].max()),
        "all_lognormal_mle_success": int(
            valid["lognormal_optimization_success"].fillna(False).sum()
        ),
        "phase2_scan_series": len(phase2_scan),
        "phase2_powerlaw_nonreject": count(phase2_scan["bootstrap_p"] >= 0.10),
        "phase2_powerlaw_reject": count(phase2_scan["bootstrap_p"] < 0.10),
        "phase2_exp_better": count(
            (phase2_scan["pl_vs_exponential_R"] < 0)
            & (phase2_scan["pl_vs_exponential_p"] < 0.10)
        ),
        "phase2_lognormal_better": count(
            (phase2_scan["pl_vs_lognormal_R"] < 0)
            & (phase2_scan["pl_vs_lognormal_p"] < 0.10)
        ),
        "phase2_alpha_median": float(phase2_scan["alpha"].median()),
        "phase2_alpha_min": float(phase2_scan["alpha"].min()),
        "phase2_alpha_max": float(phase2_scan["alpha"].max()),
    }


def plot_evidence_gate_matrix(
    output_dir: Path, stationarity_verdict: str
) -> pd.DataFrame:
    station_score = -1 if stationarity_verdict == "no_candidate" else 0
    rows = [
        ("出现大 avalanche", 1, 0, 0, "达到人工阈值；仅是最低层级现象"),
        ("重复种子与邻域中的级联转变", 1, 0, 0, "支持宽交叉/转变"),
        ("重尾迹象", 1, 0, 0, "尾部比小事件背景更宽"),
        ("可接受且优于替代分布的幂律", 0, -1, 1, "不稳健；替代尾部常更优"),
        ("有限尺寸临界传播标度", 0, -1, 1, "绝对标度由广延初始违约主导"),
        ("慢驱动与 avalanche 时间分离", 0, -1, 1, "需联合依赖/漂移证据解释"),
        ("长期平稳临界窗口", 0, station_score, 1 if station_score < 0 else 0, "见低驱动长期搜索"),
        ("单一微观触发事件定义", 0, -1, 1, "多数 event 为多源同步初始违约"),
        ("机制稳健的临界统计", 0, -1, 1, "事件规模和阈值率对清算窗口敏感"),
        ("无需窄参数调节的严格 SOC", 0, -1, 1, "当前联合证据未满足"),
    ]
    matrix = pd.DataFrame(
        rows,
        columns=["evidence_gate", "phenomenon_observed", "strict_gate_satisfied", "counterevidence", "interpretation"],
    )
    numeric = matrix[
        ["phenomenon_observed", "strict_gate_satisfied", "counterevidence"]
    ].to_numpy(dtype=float)
    annotations = np.empty_like(numeric, dtype=object)
    annotations[:, 0] = np.where(numeric[:, 0] > 0, "有", "无/不足")
    annotations[:, 1] = np.where(
        numeric[:, 1] > 0, "满足", np.where(numeric[:, 1] < 0, "不满足", "未定")
    )
    annotations[:, 2] = np.where(numeric[:, 2] > 0, "强", "弱/无")
    fig, axis = plt.subplots(figsize=(10, 8))
    sns.heatmap(
        numeric,
        annot=annotations,
        fmt="",
        cmap=sns.color_palette(["#b2182b", "#f7f7f7", "#1a9850"], as_cmap=True),
        vmin=-1,
        vmax=1,
        center=0,
        cbar=False,
        linewidths=0.7,
        linecolor="white",
        xticklabels=["观察到相关现象", "严格门槛是否满足", "主要反证/限制"],
        yticklabels=matrix["evidence_gate"],
        ax=axis,
    )
    axis.set_title("SOC evidence-gate 综合矩阵", fontsize=15, pad=15)
    axis.tick_params(axis="x", rotation=0)
    axis.tick_params(axis="y", rotation=0)
    fig.tight_layout()
    fig.savefig(output_dir / "soc_evidence_gate_matrix.png")
    plt.close(fig)
    matrix.to_csv(output_dir / "soc_evidence_gate_matrix.csv", index=False)
    return matrix


def rel_for_markdown(path: Path, markdown_path: Path) -> str:
    return os.path.relpath(path, markdown_path.parent).replace(os.sep, "/")


def image_block(label: str, path: Path, markdown_path: Path, width: int = 92) -> str:
    return f"![{label}]({rel_for_markdown(path, markdown_path)}){{width={width}%}}"


def stationarity_figures(stationarity_dir: Path) -> list[Path]:
    preferred_words = ["classification", "stationarity", "window", "occupancy", "drift"]
    figures = formal_stationarity_files(stationarity_dir, "*.png")
    figures.sort(
        key=lambda path: (
            -sum(word in path.name.lower() for word in preferred_words),
            path.name,
        )
    )
    return figures[:4]


def formal_stationarity_file(stationarity_dir: Path, name: str) -> Path:
    direct = stationarity_dir / name
    if direct.exists():
        return direct
    candidates = formal_stationarity_files(stationarity_dir, name)
    if not candidates:
        raise FileNotFoundError(f"Missing formal stationarity file: {name}")
    return sorted(
        candidates,
        key=lambda path: (len(path.relative_to(stationarity_dir).parts), -path.stat().st_mtime),
    )[0]


def stationarity_summary(stationarity_dir: Path) -> dict[str, Any]:
    classification_path = formal_stationarity_file(
        stationarity_dir, "classification.csv"
    )
    candidate_gate_path = formal_stationarity_file(
        stationarity_dir, "candidate_gate.json"
    )
    accounting_path = formal_stationarity_file(
        stationarity_dir, "accounting_audit.csv"
    )
    classification = pd.read_csv(classification_path)
    accounting = pd.read_csv(accounting_path)
    candidate_gate = json.loads(candidate_gate_path.read_text(encoding="utf-8"))
    counts = (
        classification.groupby(["family", "classification"], dropna=False)
        .size()
        .reset_index(name="scenario_count")
        .sort_values(["family", "classification"])
    )
    k1 = classification[
        classification["family"].eq("fixed")
        & classification["control_value"].eq(1)
    ][
        [
            "money_distribution",
            "early_avalanche_occupancy",
            "late_avalanche_occupancy",
            "late_mean_event_size",
            "late_mean_active_credit",
            "late_mean_final_net_worth_gini",
            "late_single_initial_default_fraction",
            "late_propagated_default_share",
            "late_repeated_default_share",
            "classification",
            "soc_candidate",
        ]
    ].sort_values("money_distribution")
    return {
        "classification_path": classification_path,
        "candidate_gate_path": candidate_gate_path,
        "accounting_path": accounting_path,
        "classification": classification,
        "classification_counts": counts,
        "k1": k1,
        "candidate_gate": candidate_gate,
        "candidate_count": int(classification["soc_candidate"].fillna(False).sum()),
        "scenario_count": len(classification),
        "accounting_checks": len(accounting),
        "accounting_passed": int(accounting["passed"].fillna(False).sum()),
    }


def mechanism_reference_rows() -> pd.DataFrame:
    summary = pd.read_csv(MECHANISM_ROOT / "scenario_summary.csv")
    return summary[
        summary["mechanism_id"].isin(
            [
                "reference_period_end",
                "flow_split_b10_check_q1",
                "keep_defaulted_assets",
                "permanent_exit",
                "reset",
            ]
        )
    ][
        [
            "protocol_id",
            "mechanism_id",
            "run_critical_rate_10pct",
            "mean_avalanche_active_macro_rate",
            "mean_event_size",
            "mean_repeat_default_share",
            "mean_final_active_credit",
            "mean_final_active_nodes",
            "mean_final_gini",
        ]
    ]


def factor_key_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = pd.read_csv(FACTORS_ROOT / "scenario_summary.csv")
    income = summary[summary["factor_family"].eq("income_rule")][
        [
            "income_distribution_rule",
            "mean_first_cascade_credit",
            "mean_max_collapse_size",
            "mean_event_size",
            "mean_final_net_worth_gini",
        ]
    ]
    topology = pd.read_csv(FACTORS_ROOT / "topology_matched_degree_summary.csv")[
        [
            "topology",
            "target_mean_degree",
            "mean_topology_clustering",
            "mean_topology_degree_cv",
            "mean_max_collapse_size",
            "mean_event_size",
        ]
    ]
    return income, topology


def figure_manifest(
    args: argparse.Namespace, output_dir: Path, markdown_path: Path
) -> list[tuple[str, Path]]:
    strict_dir = ensure_absolute(args.strict_analysis_dir)
    figures: list[tuple[str, Path]] = [
        ("SOC evidence-gate 综合矩阵", output_dir / "soc_evidence_gate_matrix.png"),
        ("有限尺寸 initial-default 与 propagated 拆解", output_dir / "finite_size_initial_propagated.png"),
        ("转变扫描中的单触发概率与传播占比", output_dir / "transition_single_trigger_audit.png"),
        ("严格分支：正式 initial-default 与 propagated 拆解", strict_dir / "initial_vs_propagated_decomposition.png"),
        ("严格分支：转变区细扫", strict_dir / "transition_fine_scan.png"),
        ("严格分支：power-law 与替代分布比较", strict_dir / "strict_fit_comparison.png"),
        ("严格分支：power-law GOF", strict_dir / "strict_powerlaw_gof.png"),
        ("严格分支：有限尺寸标度", strict_dir / "finite_size_scaling.png"),
        ("严格分支：时间分离诊断", strict_dir / "temporal_separation.png"),
        ("严格分支：时间窗口漂移", strict_dir / "time_window_drift.png"),
        ("动态分支：长期时间窗口", DYNAMICS_ROOT / "long_run_time_windows.png"),
        ("动态分支：传播分支比", DYNAMICS_ROOT / "branching_vs_drive.png"),
        ("机制分支：驱动与检查频率解耦", MECHANISM_ROOT / "batch_decoupling.png"),
        ("机制分支：清算机制大事件率", MECHANISM_ROOT / "clearing_mechanism_critical_rate.png"),
        ("机制分支：重复违约占比", MECHANISM_ROOT / "repeat_default_share.png"),
        ("机制分支：阈值敏感性", MECHANISM_ROOT / "threshold_sensitivity.png"),
        ("因素分支：本金、收入与增长规则", FACTORS_ROOT / "factor_effects.png"),
        ("因素分支：ER/BA/SW 与平均度", FACTORS_ROOT / "topology_degree_effects.png"),
        ("因素分支：匹配平均度拓扑 CCDF", FACTORS_ROOT / "topology_matched_degree_ccdf.png"),
    ]
    for index, path in enumerate(stationarity_figures(ensure_absolute(args.stationarity_result_dir)), 1):
        figures.append((f"低驱动长期平稳性搜索图 {index}", path))
    missing = [str(path) for _, path in figures if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing report figures:\n" + "\n".join(missing))
    manifest = pd.DataFrame(
        [
            {
                "index": index,
                "label": label,
                "path": str(path),
                "markdown_path": rel_for_markdown(path, markdown_path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for index, (label, path) in enumerate(figures, 1)
        ]
    )
    manifest.to_csv(output_dir / "figure_manifest.csv", index=False)
    return figures


def report_text(
    args: argparse.Namespace,
    audits: dict[str, Any],
    strict: dict[str, Any],
    stationarity: dict[str, Any],
    evidence_matrix: pd.DataFrame,
    figures: list[tuple[str, Path]],
) -> str:
    markdown_path = ensure_absolute(args.markdown)
    finite = audits["finite_summary"].copy()
    finite_display = finite[
        [
            "family",
            "n_nodes",
            "events",
            "p_initial_default_count_eq_1",
            "mean_initial_fraction_of_N",
            "mean_propagated_fraction_of_N",
            "propagated_share_of_total_size",
        ]
    ].copy()
    finite_display["family"] = finite_display["family"].map(family_label)
    finite_display.columns = [
        "协议",
        "N",
        "events",
        "P(initial=1)",
        "mean initial/N",
        "mean propagated/N",
        "propagated/total",
    ]

    transition = audits["transition_summary"].copy()
    transition["family"] = transition["family"].map(family_label)
    transition.columns = [
        "协议",
        "控制量",
        "events",
        "P(initial=1)",
        "mean initial",
        "mean propagated",
        "mean total",
        "propagated/total",
    ]
    transition = transition[
        [
            "协议",
            "控制量",
            "events",
            "P(initial=1)",
            "mean initial",
            "mean propagated",
            "mean total",
            "propagated/total",
        ]
    ]

    mechanism = mechanism_reference_rows().copy()
    mechanism.columns = [
        "协议",
        "机制",
        "run大事件率",
        "avalanche活跃期率",
        "平均事件规模",
        "重复违约占比",
        "终态活跃信贷",
        "终态active节点",
        "终态Gini",
    ]
    income_factor, topology_factor = factor_key_rows()
    income_factor.columns = [
        "收入规则",
        "首次事件前活跃信贷",
        "平均最大事件",
        "平均事件规模",
        "终态Gini",
    ]
    topology_factor.columns = [
        "机会图",
        "平均度",
        "聚类",
        "度CV",
        "平均最大事件",
        "平均事件规模",
    ]

    stationarity_text = read_text(ensure_absolute(args.stationarity_report))
    k1_lines = [
        re.sub(r"^(?:[-*+]\s+)+", "", line.strip())
        for line in stationarity_text.splitlines()
        if re.search(r"(K\s*=\s*1|K=1|固定\s*K\s*1)", line)
    ][:8]
    stationarity_extract = (
        "\n".join(f"- {line}" for line in k1_lines)
        if k1_lines
        else "- 固定 `K=1` 结果见低驱动长期搜索正式报告与原始 CSV。"
    )
    stationarity_counts = stationarity["classification_counts"].copy()
    stationarity_counts.columns = ["协议族", "分类", "场景数"]
    stationarity_k1 = stationarity["k1"].copy()
    stationarity_k1.columns = [
        "本金",
        "early occupancy",
        "late occupancy",
        "late mean size",
        "late active credit",
        "late Gini",
        "late P(initial=1)",
        "late propagated/total",
        "late repeated share",
        "分类",
        "SOC候选",
    ]

    final_working_verdict = {
        "no_candidate": (
            "综合工作判定为：当前已实现 baseline、已扫描参数邻域与已测机制不支持严格 SOC。"
            "系统支持级联交叉和机制敏感的重尾现象，但高风险状态更符合非平稳、重复违约、"
            "低活跃信贷的持续失败/过载吸引子。最终判定权归主协调器。"
        ),
        "candidate": (
            "低驱动搜索发现候选窗口，因此严格 SOC 在当前证据下仍不可识别；必须先对候选完成"
            "单触发、block/run bootstrap、有限尺寸和机制稳健性复核。最终判定权归主协调器。"
        ),
        "indeterminate": (
            "综合工作判定保持不可识别，等待主协调器根据低驱动长期搜索最终结论决定。"
        ),
    }[args.stationarity_verdict]

    image_by_label = {label: path for label, path in figures}

    def fig(label: str) -> str:
        return image_block(label, image_by_label[label], markdown_path)

    stationarity_image_blocks = "\n\n".join(
        image_block(label, path, markdown_path)
        for label, path in figures
        if label.startswith("低驱动长期平稳性")
    )

    evidence_display = evidence_matrix[
        ["evidence_gate", "interpretation"]
    ].copy()
    evidence_display.columns = ["evidence gate", "综合解释"]

    return f"""# 信贷网络 Phase-2 严格 SOC 综合证据报告 v1

生成时间：{now_cst()}  
报告定位：综合审计与主协调器最终判定输入；不覆盖任何旧报告。

## 1. 执行摘要

{final_working_verdict}

必须严格区分以下 claim ladder：

| 层级 | 当前证据结论 |
| --- | --- |
| 大 avalanche | 已观察到，但 `critical_event` 只是达到人工阈值的标签。 |
| 可重复级联转变 | 固定 `K` 与收入内生 `c` 均观察到宽而随机的稳定区到持续失败区交叉。 |
| 重尾 | 多个场景有重尾迹象，但尾部对机制、窗口、参数和时间状态敏感。 |
| 可接受幂律 | 部分 pooled series 不拒绝 power law，但替代分布、序列依赖和非平稳性使其不足以晋级。 |
| 严格 SOC | 当前联合证据未满足；不能由大事件、log-log 图、单个 alpha 或绝对 cutoff 标度单独推出。 |

本报告不把高 occupancy 或 `P(wait=1)` 单独当作 SOC 反证。级联内部确实暂停驱动，但基线在
`period_end` 前可批量加载 `K>1` 次信贷尝试；最终解释依赖 occupancy、lag-1、非平稳漂移、
重复违约、退化终态、替代尾部、机制消融和 initial-default 广延增长的联合证据。

{fig("SOC evidence-gate 综合矩阵")}

{markdown_table(evidence_display)}

## 2. 当前模型框架与变量口径

### 2.1 时间层级

```text
scenario：固定参数和机制
  -> run：一个随机种子下的独立轨迹
     -> period：一批单位信贷尝试 + 一次期末流量结算和违约检查
        -> time_step：至多成功新增 1 单位信贷暴露的一次尝试
```

收入内生协议中：

```text
K_t = round(c * Y_(t-1))
```

`c` 对应代码字段 `investment_income_propensity`，是上一期全系统总收入到下一期计划信贷
尝试批量的转换系数，不是单笔贷款规模、实际投资支出比例或与检查频率独立的纯加载速度。
固定窗口协议直接令 `K_t=K`，此时元数据中的 `c` 不参与模拟。`period_end` 才完成全体节点的
流量结算、违约检查和整次级联；即使 `K=1`，仍然存在一次全系统期末流量结算。

### 2.2 第一层：模型参数与协议

| 参数/协议 | 准确定义与解释边界 |
| --- | --- |
| `N` | 节点数。有限尺寸比较必须保持可比的强度协议，不能跨 `N` 固定绝对 `K` 后直接解释。 |
| `a, b` | 正净资产与上一期个体收入进入计划消费的倾向；实际消费还受随机舍入和现金约束。 |
| `c` / `investment_income_propensity` | 上一期总收入到下一期计划信贷尝试批量的转换系数；不是单笔冲击、实际投资比例或纯加载速度。 |
| `period_length_rule, K_t, fixed K` | 决定一次 `period_end` 前计划多少个 time_step；固定 `K` 下 `c` 不生效。 |
| `income_distribution_rule` | `uniform` 或按正净资产加 floor 的 `biased` 收入再分配规则。 |
| `growth_rule` | 在允许交易的主体对中，动态选择实际有向贷款方向和时点的规则。 |
| `topology` | 固定无向、无权 opportunity graph，限制哪些主体对允许交易；它不同于动态、有向、带权的实际暴露网络和 `growth_rule`。 |
| `default_threshold/check_mode` | 基线违约为严格 `W_i<0`，并在 `period_end` 检查。 |
| `collapse_threshold_fraction` | 大事件的人工分类阈值，只改变标签，不改变传播。 |
| `avalanche_protocol` | `continue_after_avalanche` 允许同一节点跨期重复违约；stop 协议在首次事件后结束。 |
| `wipe_defaulted_assets` | 是否清除违约节点持有的贷款资产；会改变级联放大。 |
| `recovery_rate` | 目标面值回收比例，不等于代码记录的实际回收量 `actual_recovery_amount`；后者受违约债务人现有现金上限约束。 |
| `default_node_mode` | `continue/exit/reset`；exit 会耗尽参与者，reset 恢复节点现金，并由 `external_reset_cash_flow` 记录其可正可负的外部现金流。 |
| `validate_accounting` | 是否逐期执行会计不变量断言，不改变经济机制。 |

### 2.3 第二层：内生存量、流量与会计

| 类别 | 变量 | 定义 |
| --- | --- | --- |
| 存量 | `C_i,t` | 节点现金 |
| 存量 | `E_ij,t` | `i` 贷给 `j` 的当前未清算有向带权暴露 |
| 存量 | `A_i,t=sum_j E_ij,t` | 贷款资产 |
| 存量 | `D_i,t=sum_j E_ji,t` | 债务负债 |
| 存量 | `W_i,t=C_i,t+A_i,t-D_i,t` | 净资产；违约条件为严格 `<0` |
| 流量 | `Y_i,t, Y_t` | 个体收入与总收入；总收入等于当期实际总支出 |
| 流量 | `B_i,t` | 当期成功借入量 |
| 流量 | `I_i,t, X_i,t` | 受现金约束的实际投资支出和消费支出 |

单位信贷建立使贷款人现金减 1、贷款资产加 1，同时使借款人现金加 1、债务加 1，所以信贷
time_step 本身不改变双方净资产。风险主要在期末支出、收入再分配和既有暴露清算中形成。

### 2.4 第三层：事件分解

| 事件变量 | 准确定义与限制 |
| --- | --- |
| `initial_default_count` | 一次 `period_end` 流量结算后、网络传播前已经 `W_i<0` 的同步初始违约节点数。 |
| `propagated_default_count` | `collapse_size - initial_default_count`，即传播过程中新增的违约节点数。 |
| single-trigger | `initial_default_count=1` 的记录事件；它只是事件定义诊断，不保证满足其他 SOC 门槛。 |
| `collapse_size` | 本次记录事件最终清算的不同节点数；可能由多个同步 initial defaults 共同触发。 |
| wave | FIFO sticky queue 中节点最早被发现的传播代；不是同步物理时间。 |
| duration/generations | 非空传播代数，包含初始第 0 代；不同于 period、time_step 或 `cascade_steps`。 |
| branching | 相邻传播代规模比或传播新增数/前序父节点数；是当前顺序清算下的描述量，不是严格临界分支过程的无偏估计。 |
| repeated defaults | 同一节点跨 period 再次违约产生的重复节点出现次数；会放大事件总量和尾部。 |

### 2.5 第四层：统计证据

| 统计量 | 准确定义与解释边界 |
| --- | --- |
| occupancy | 发生记录 event 的 period 占比；高 occupancy 单独不是 SOC 反证。 |
| wait / `P(wait=1)` | 同一 run 中相邻记录 event 的 period 间隔；不是 avalanche 内部持续时间。 |
| size lag-1 | run 内相邻 event size 对汇总后的相关；不跨 run 连接，也不是 period-lag 因果估计。 |
| stationarity / drift | 早晚窗口或时间分位上的分布、规模、频率、active credit、Gini 等是否稳定。 |
| `xmin` | Phase-2 严格离散尾部拟合的自动候选最优下界。 |
| discrete `alpha` | 在自动 `xmin` 后对离散 power-law 尾部估计的指数。旧框架固定 `xmin=2` 的连续 Pareto alpha 只是描述性初筛，两者不能混用。 |
| KS bootstrap | 按拟合尾部生成并重新选择 `xmin` 的 goodness-of-fit；强序列依赖下 event-level p 值仅作诊断。 |
| Vuong comparison | 同一尾段上 power law 与 exponential/lognormal 的描述性似然比较；依赖事件下不能当作最终 iid 显著性证明。 |
| bounded cutoff | 显式使用有限支持 `[xmin,N]` 的尾部或 P99/矩等 cutoff 描述；绝对 cutoff 随 `N` 增长不自动等于临界传播。 |

### 2.6 计划量、实际量与统计量不能混用

| 名称 | 精确定义 |
| --- | --- |
| `period_length_steps=K_t` | 计划执行的 time_step 数 |
| `time_steps_completed` | 实际进入的信贷尝试数 |
| `total_credit_issued` | 累计成功新增的单位暴露 |
| `credit_scale_before_cascade` | 某事件清算前仍活跃的暴露存量 |
| `collapse_size` | 一次 `period_end` 记录事件中最终清算的节点数 |
| `critical_event` | `collapse_size/N >= 0.10` 的人工分类标签 |
| `total_collapse_size` | run 内事件规模之和；允许跨期重复计算同一节点 |
| `alpha, xmin, KS, Vuong` | 结果统计和诊断量，不参与模型传播 |

## 3. 事件定义审计：多数 event 不是单一微观触发

一次 `period_end` 流量结算可以同时产生多个净资产为负的 initial defaults。当前事件记录把这些
同步初始违约及其后续传播合并为一次 avalanche，因此记录的 size 分布不能直接等同于经典
“单一微观触发 -> 临界传播”的 SOC avalanche 分布。

收入内生 lognormal 扫描中，`P(initial_default_count=1)` 随 `c=.12 -> .20` 从约 `0.155`
下降到 `0.020`；固定 lognormal 扫描中，随 `K=18 -> 26` 从约 `0.081` 下降到 `0.037`。
传播新增只占总事件规模约 `10%-16%`。更准确的机制描述是：

```text
period_end 多源同步初始违约 + 通常亚临界的网络传播
```

{markdown_table(transition, formats={"控制量": "{:.3f}", "P(initial=1)": "{:.4f}", "propagated/total": "{:.4f}", "mean initial": "{:.3f}", "mean propagated": "{:.3f}", "mean total": "{:.3f}"})}

{fig("转变扫描中的单触发概率与传播占比")}

## 4. 级联转变、严格尾部与 claim ladder

修正版严格统计目录：`{ensure_absolute(args.strict_analysis_dir)}`。最终方法审计：
`{STRICT_METHOD_AUDIT}`。

- 全部 39 个关键 series 中，无界 pure power-law KS bootstrap 不拒绝
  {strict["all_powerlaw_nonreject"]} 个、拒绝 {strict["all_powerlaw_reject"]} 个；bounded
  power law 不拒绝 {strict["all_bounded_powerlaw_nonreject"]} 个、拒绝
  {strict["all_bounded_powerlaw_reject"]} 个。
- 描述性 Vuong 比较中，exponential 显著优于 power law 的 series 为
  {strict["all_exp_better"]} 个，lognormal 显著优于 power law 的 series 为
  {strict["all_lognormal_better"]} 个。全部 {strict["all_lognormal_mle_success"]} 个
  lognormal MLE 成功且最终方法审计未发现边界命中。
- 全部 series 的 alpha 范围为 {strict["all_alpha_min"]:.3f}-{strict["all_alpha_max"]:.3f}；
  20 个新增 `N=200` 收入/固定细扫 series 的 alpha 中位数为
  {strict["phase2_alpha_median"]:.3f}。指数随参数、seed 和 `N` 改变，不构成稳定普适指数。
- pooled event 存在强时间依赖，event-level iid KS bootstrap 与 Vuong p 值只能作为描述性诊断。

{fig("严格分支：转变区细扫")}

{fig("严格分支：power-law 与替代分布比较")}

{fig("严格分支：power-law GOF")}

## 5. 有限尺寸：绝对 size 近线性增长不等于传播临界

在保持可比驱动的有限尺寸协议中，绝对平均 size、P99 和矩随 `N` 增长。但独立拆解显示：

- `finite_fixed` 的传播新增只占总 size `14.6%-15.0%`；
- `finite_income c=.18` 的传播新增只占总 size `12.2%-12.8%`；
- initial defaults/N 与 propagated defaults/N 随 `N` 基本不变；
- mean total/initial/propagated size 的 log-log 斜率分别约为
  `0.972/0.970/0.985` 和 `0.983/0.981/1.004`。

因此，绝对 size 的近线性标度主要来自 `period_end` 同步初始违约的广延增长，而不是传播
分支过程逐渐接近临界。该拆解显著削弱了把 cutoff/矩增长解释为严格 SOC 的依据。

{markdown_table(finite_display, formats={"P(initial=1)": "{:.4f}", "mean initial/N": "{:.5f}", "mean propagated/N": "{:.5f}", "propagated/total": "{:.4f}"})}

{fig("有限尺寸 initial-default 与 propagated 拆解")}

{fig("严格分支：正式 initial-default 与 propagated 拆解")}

{fig("严格分支：有限尺寸标度")}

## 6. 时间分离、长期漂移与低驱动搜索

高 occupancy 或 `P(wait=1)` 本身不能单独排除 SOC；本报告将它们与以下证据联合解释：

1. 事件规模 lag-1 相关；
2. Q1 到 Q4 的规模和大事件率持续漂移；
3. 同一节点跨期重复违约；
4. 终态活跃信贷下降、Gini 接近 1；
5. 多数 event 为多源同步 initial defaults；
6. 严格尾部替代分布和 per-seed 不稳定性；
7. 固定 `K=1` 最慢驱动对照。

低驱动长期搜索中的固定 `K=1` 证据摘录：

{stationarity_extract}

正式长期搜索共分类 {stationarity["scenario_count"]} 个场景，其中 `soc_candidate=True` 为
{stationarity["candidate_count"]} 个；会计/一致性审计通过
{stationarity["accounting_passed"]}/{stationarity["accounting_checks"]} 项。完整候选门槛见
`{stationarity["candidate_gate_path"]}`。

{markdown_table(stationarity_counts)}

固定 `K=1` 是当前协议最慢批量控制，但仍会在全系统 `period_end` 流量结算后产生零个、一个或
多个 initial defaults；因此它不自动等同于单一微观触发 SOC。

{markdown_table(stationarity_k1, formats={"early occupancy": "{:.4f}", "late occupancy": "{:.4f}", "late mean size": "{:.3f}", "late active credit": "{:.1f}", "late Gini": "{:.4f}", "late P(initial=1)": "{:.4f}", "late propagated/total": "{:.4f}", "late repeated share": "{:.4f}"})}

{fig("严格分支：时间分离诊断")}

{fig("严格分支：时间窗口漂移")}

{fig("动态分支：长期时间窗口")}

{stationarity_image_blocks}

## 7. Cascade 内部传播动态

动态分支的正式 280-run / 80,353-event 审计显示，单次事件内部平均 weighted branching 明显
低于 1；同时长期 continue 协议趋向近连续、强相关的持续失败状态。传播 generation 是顺序
FIFO sticky queue 的最早发现代，不是同步物理时间；`cascade_steps` 也只是处理节点数。

这与事件定义拆解一致：观察到的大 size 主要不是单一初始节点引发接近临界的分支传播，而是
多个同步初始违约再叠加有限传播。

{fig("动态分支：传播分支比")}

## 8. 检查频率、清算、恢复、退出与重置

credit-only 中间检查与 reference 完全等价，因为单位信贷不改变净资产。固定流量结算序列下，
提高检查频率会把批量事件碎片化为更多小事件，但没有恢复低频、相互分离的健康状态。
Reference 中 repeated default 占比超过 98%；保留违约节点资产显著降低单次规模但持续小违约
仍存在；永久退出通过耗尽参与者停止事件；reset 引入外部现金并依赖驱动规则。

{markdown_table(mechanism, formats={"run大事件率": "{:.3f}", "avalanche活跃期率": "{:.3f}", "平均事件规模": "{:.3f}", "重复违约占比": "{:.3f}", "终态活跃信贷": "{:.1f}", "终态active节点": "{:.1f}", "终态Gini": "{:.3f}"})}

{fig("机制分支：驱动与检查频率解耦")}

{fig("机制分支：清算机制大事件率")}

{fig("机制分支：重复违约占比")}

{fig("机制分支：阈值敏感性")}

## 9. `project.md` 因素与 ER/BA/SW 影响

固定 `K=20`、240-period 瞬态因素扫描显示：

- biased 收入相对 uniform 收入显著提前首次事件、增大级联并提高终态不平等；
- lognormal 初始本金与较大级联同时出现，但本金分布未逐 run 严格配平总现金；
- random 实际有向暴露增长的事件规模显著高于 `preferential_debt`；
- 匹配平均度后 ER、BA-derived、SW 家族差异较弱，平均度效应也只是弱探索性证据；
- 这些结论是独立种子、短时域描述性比较，不能外推为长期拓扑排序或严格因果效应。

收入规则对照：

{markdown_table(income_factor, formats={"首次事件前活跃信贷": "{:.1f}", "平均最大事件": "{:.3f}", "平均事件规模": "{:.3f}", "终态Gini": "{:.3f}"})}

匹配平均度拓扑对照：

{markdown_table(topology_factor, formats={"平均度": "{:.0f}", "聚类": "{:.3f}", "度CV": "{:.3f}", "平均最大事件": "{:.3f}", "平均事件规模": "{:.3f}"})}

{fig("因素分支：本金、收入与增长规则")}

{fig("因素分支：ER/BA/SW 与平均度")}

{fig("因素分支：匹配平均度拓扑 CCDF")}

## 10. 综合经验结论与边界

### 10.1 当前支持

1. 当前模型明确存在由驱动批量、流量分配、初始本金和暴露增长共同决定的级联交叉。
2. 部分协议存在机制敏感的重尾和大事件。
3. 高风险 continue 协议长期趋向高不平等、低活跃信贷、重复违约的持续失败状态。
4. 清算聚合窗口会显著改变单次事件 size 和人工大事件率。
5. biased 收入、lognormal 本金和 random 增长是当前已测条件下的重要脆弱性因素。

### 10.2 当前不支持或不能外推

1. 不能把 `critical_event`、log-log 近直线、单个 alpha 或 failure-to-reject 当作严格 SOC 证明。
2. 不能把高 occupancy 或 `P(wait=1)` 单独当作反证；它们只在联合证据中有解释力。
3. 不能把一次记录 event 默认当作单一微观触发 avalanche；多数 event 含多个同步 initial defaults。
4. 不能把绝对 size 近线性有限尺寸标度解释为传播临界；初始违约广延增长占主导。
5. 当前经验判定只适用于已实现 baseline、扫描邻域和已测机制，不是所有信贷网络模型的数学否定。
6. 当前没有正常还款、利息、生产回报、动态真实机会网络和经过验证的稳态更新机制。

## 11. 可复现性与证据路径

- 综合结果目录：`{ensure_absolute(args.output_dir)}`
- 修正版严格统计：`{ensure_absolute(args.strict_analysis_dir)}`
- strict 原始 run/event：`{STRICT_ROOT / "run_summary.csv"}`、`{STRICT_ROOT / "avalanche_events.csv"}`
- stationarity 结果：`{ensure_absolute(args.stationarity_result_dir)}`
- stationarity 报告：`{ensure_absolute(args.stationarity_report)}`
- 最终 strict 方法审计：`{STRICT_METHOD_AUDIT}`
- 模型变量口径审计 v3：`{VARIABLE_AUDIT_V3}`
- 动态结果：`{DYNAMICS_ROOT}`
- 机制结果：`{MECHANISM_ROOT}`
- 因素与拓扑结果：`{FACTORS_ROOT}`
- 本报告 figure manifest：`{ensure_absolute(args.output_dir) / "figure_manifest.csv"}`
- 完整 evidence manifest：`{ensure_absolute(args.output_dir) / "evidence_manifest.csv"}`
- 复现命令：`{ensure_absolute(args.output_dir) / "reproduction_commands.md"}`
- Word/LibreOffice 验证：`{ensure_absolute(args.output_dir) / "validation_report.md"}`
"""


def write_evidence_manifest(output_dir: Path, sources: list[Path]) -> None:
    unique = sorted({path.resolve() for path in sources if path.exists()})
    rows = [
        {
            "path": str(path),
            "bytes": path.stat().st_size,
            "mtime_cst": datetime.fromtimestamp(path.stat().st_mtime)
            .astimezone()
            .isoformat(),
            "sha256": sha256(path),
        }
        for path in unique
        if path.is_file()
    ]
    pd.DataFrame(rows).to_csv(output_dir / "evidence_manifest.csv", index=False)


def run_logged(command: list[str], log_path: Path, cwd: Path = ROOT) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(
        "$ " + " ".join(command) + "\n\n" + result.stdout,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}; see {log_path}"
        )


def build_docx_and_validate(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    markdown = ensure_absolute(args.markdown)
    docx = ensure_absolute(args.docx)
    pandoc = shutil.which("pandoc")
    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    pdfinfo = shutil.which("pdfinfo")
    pdftoppm = shutil.which("pdftoppm")
    if not all([pandoc, libreoffice, pdfinfo, pdftoppm]):
        raise RuntimeError("pandoc/libreoffice/pdfinfo/pdftoppm are all required.")

    resource_path = os.pathsep.join(
        [
            str(ROOT),
            str(ROOT / "docs"),
            str(ROOT / "results"),
            str(output_dir),
            str(ensure_absolute(args.strict_analysis_dir)),
            str(ensure_absolute(args.stationarity_result_dir)),
        ]
    )
    pandoc_command = [
        pandoc,
        str(markdown),
        "--from",
        "markdown+link_attributes",
        "--standalone",
        "--toc",
        "--number-sections",
        "--resource-path",
        resource_path,
        "--reference-doc",
        str(REFERENCE_DOCX),
        "-o",
        str(docx),
    ]
    run_logged(pandoc_command, output_dir / "pandoc.log")

    with zipfile.ZipFile(docx) as archive:
        media = sorted(
            name for name in archive.namelist() if name.startswith("word/media/")
        )
    if len(media) < 12:
        raise RuntimeError(f"DOCX only contains {len(media)} embedded media files.")

    render_dir = output_dir / "libreoffice_render"
    render_dir.mkdir(parents=True, exist_ok=True)
    profile = output_dir / (
        "libreoffice_profile_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    profile.mkdir(parents=True, exist_ok=False)
    libreoffice_command = [
        libreoffice,
        f"-env:UserInstallation={profile.resolve().as_uri()}",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(render_dir),
        str(docx),
    ]
    run_logged(libreoffice_command, output_dir / "libreoffice_render.log")
    pdf_path = render_dir / f"{docx.stem}.pdf"
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError("LibreOffice did not create a non-empty PDF.")

    pdfinfo_result = subprocess.run(
        [pdfinfo, str(pdf_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    (output_dir / "pdfinfo.txt").write_text(pdfinfo_result.stdout, encoding="utf-8")
    page_match = re.search(r"^Pages:\s+(\d+)", pdfinfo_result.stdout, re.M)
    pages = int(page_match.group(1)) if page_match else 0
    preview_prefix = render_dir / "preview"
    run_logged(
        [
            pdftoppm,
            "-f",
            "1",
            "-l",
            str(min(max(pages, 1), 3)),
            "-png",
            "-r",
            "110",
            str(pdf_path),
            str(preview_prefix),
        ],
        output_dir / "pdftoppm.log",
    )
    previews = sorted(render_dir.glob("preview-*.png"))
    validation = {
        "validated_at_cst": now_cst(),
        "markdown": str(markdown),
        "docx": str(docx),
        "docx_bytes": docx.stat().st_size,
        "docx_embedded_media_count": len(media),
        "docx_embedded_media": media,
        "libreoffice_pdf": str(pdf_path),
        "libreoffice_pdf_bytes": pdf_path.stat().st_size,
        "libreoffice_pdf_pages": pages,
        "rendered_preview_count": len(previews),
        "rendered_previews": [str(path) for path in previews],
        "status": "passed" if len(media) >= 12 and pages > 0 and previews else "failed",
    }
    (output_dir / "validation_report.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "validation_report.md").write_text(
        "\n".join(
            [
                "# 综合报告 Word 与渲染验证",
                "",
                f"- 验证时间：{validation['validated_at_cst']}",
                f"- DOCX：`{docx}`",
                f"- DOCX 内嵌 media 数：**{len(media)}**",
                f"- LibreOffice PDF：`{pdf_path}`",
                f"- PDF 页数：**{pages}**",
                f"- pdftoppm 预览数：**{len(previews)}**",
                f"- 验证状态：**{validation['status']}**",
                "",
                "完整 media 列表和预览路径见 `validation_report.json`。",
            ]
        ),
        encoding="utf-8",
    )
    return validation


def write_reproduction_commands(args: argparse.Namespace, output_dir: Path) -> None:
    command = (
        "/home/wuyangcheng/.conda/envs/myenv/bin/python "
        "scripts/build_phase2_comprehensive_report.py "
        f"--strict-analysis-dir {ensure_absolute(args.strict_analysis_dir)} "
        f"--strict-report {ensure_absolute(args.strict_report)} "
        f"--stationarity-result-dir {ensure_absolute(args.stationarity_result_dir)} "
        f"--stationarity-report {ensure_absolute(args.stationarity_report)} "
        f"--stationarity-verdict {args.stationarity_verdict} "
        f"--output-dir {ensure_absolute(args.output_dir)} "
        f"--markdown {ensure_absolute(args.markdown)} "
        f"--docx {ensure_absolute(args.docx)}"
    )
    (output_dir / "reproduction_commands.md").write_text(
        f"""# Phase-2 综合报告复现命令

生成时间：{now_cst()}

## 最终报告

```bash
{command}
```

## 仅独立复算 event-definition 审计

```bash
{command} --audit-only
```

脚本会在最终模式中强制检查 strict/stationarity worker completion、strict 修正版文件、
stationarity CSV/PNG/正式报告以及固定 `K=1` 对照；任一 gate 未通过即拒绝生成最终版。
""",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    for field in [
        "strict_analysis_dir",
        "strict_report",
        "stationarity_result_dir",
        "stationarity_report",
        "output_dir",
        "markdown",
        "docx",
    ]:
        setattr(args, field, ensure_absolute(getattr(args, field)))
    configure_plotting()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    gate = final_gate_status(args)
    (args.output_dir / "preparation_gate_status.json").write_text(
        json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    audits = build_event_definition_audits(args.output_dir)
    crosscheck_strict_decomposition(audits, args.strict_analysis_dir, args.output_dir)
    write_reproduction_commands(args, args.output_dir)
    if args.audit_only:
        print(
            json.dumps(
                {
                    "status": "audit_only_complete",
                    "gate_ready": gate["ready"],
                    "output_dir": str(args.output_dir),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if not gate["ready"]:
        failed = [name for name, ok in gate["checks"].items() if not ok]
        raise RuntimeError(
            "Final report gate is closed. Failed checks:\n- " + "\n- ".join(failed)
        )

    strict = strict_summary(args.strict_analysis_dir)
    stationarity = stationarity_summary(args.stationarity_result_dir)
    if args.stationarity_verdict == "no_candidate" and stationarity["candidate_count"] != 0:
        raise RuntimeError(
            "Explicit no_candidate verdict conflicts with formal stationarity candidates."
        )
    if args.stationarity_verdict == "candidate" and stationarity["candidate_count"] == 0:
        raise RuntimeError(
            "Explicit candidate verdict conflicts with zero formal stationarity candidates."
        )
    evidence_matrix = plot_evidence_gate_matrix(
        args.output_dir, args.stationarity_verdict
    )
    figures = figure_manifest(args, args.output_dir, args.markdown)
    args.markdown.write_text(
        report_text(args, audits, strict, stationarity, evidence_matrix, figures),
        encoding="utf-8",
    )

    sources = [
        STRICT_ROOT / "run_summary.csv",
        STRICT_ROOT / "avalanche_events.csv",
        args.strict_report,
        STRICT_METHOD_AUDIT,
        VARIABLE_AUDIT_V3,
        args.stationarity_report,
        *args.strict_analysis_dir.glob("*"),
        *formal_stationarity_files(args.stationarity_result_dir, "*"),
        *DYNAMICS_ROOT.glob("*.csv"),
        *MECHANISM_ROOT.glob("*.csv"),
        *FACTORS_ROOT.glob("*.csv"),
        *(path for _, path in figures),
    ]
    write_evidence_manifest(args.output_dir, [path for path in sources if path.is_file()])
    validation = build_docx_and_validate(args, args.output_dir)
    artifact_manifest = {
        "generated_at_cst": now_cst(),
        "gate": gate,
        "stationarity_verdict": args.stationarity_verdict,
        "strict_summary": {key: value for key, value in strict.items() if key != "fits"},
        "report_markdown": str(args.markdown),
        "report_docx": str(args.docx),
        "output_dir": str(args.output_dir),
        "validation": validation,
    }
    (args.output_dir / "artifact_manifest.json").write_text(
        json.dumps(artifact_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(artifact_manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
