#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import optimize, special, stats


ROOT = Path(__file__).resolve().parents[1]
CST = ZoneInfo("Asia/Shanghai")
DEFAULT_RESULT = ROOT / "results" / "credit_soc_phase2_strict_soc_20260604_v1"
DEFAULT_EXISTING_C020 = ROOT / "results" / "credit_soc_continue_income_c020_random_focus_20260604_v1"
DEFAULT_EXISTING_FIXED = ROOT / "results" / "credit_soc_fixedK_sweep_20260604_v1"


@dataclass
class PowerLawFit:
    xmin: int
    alpha: float
    ks: float
    tail_n: int
    candidate_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strict discrete-tail and finite-size SOC analysis.")
    parser.add_argument("--result-dir", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--existing-c020-dir", type=Path, default=DEFAULT_EXISTING_C020)
    parser.add_argument("--existing-fixed-dir", type=Path, default=DEFAULT_EXISTING_FIXED)
    parser.add_argument("--min-tail", type=int, default=100)
    parser.add_argument("--bootstrap", type=int, default=200)
    parser.add_argument("--bootstrap-seed", type=int, default=2026130000)
    parser.add_argument(
        "--max-xmin-candidates",
        type=int,
        default=10_000,
        help="Maximum eligible xmin values to inspect; default is effectively exhaustive here.",
    )
    parser.add_argument("--per-seed-min-tail", type=int, default=30)
    parser.add_argument("--progress-every", type=int, default=5)
    return parser.parse_args()


def clean_sizes(values: np.ndarray | pd.Series) -> np.ndarray:
    array = np.asarray(values, dtype=np.int64)
    return array[array > 0]


def discrete_powerlaw_logpmf(values: np.ndarray, alpha: float, xmin: int) -> np.ndarray:
    return -alpha * np.log(values) - math.log(float(special.zeta(alpha, xmin)))


def powerlaw_ks(values: np.ndarray, alpha: float, xmin: int) -> float:
    tail = np.sort(values[values >= xmin])
    if tail.size == 0:
        return float("nan")
    unique, counts = np.unique(tail, return_counts=True)
    empirical_cdf = np.cumsum(counts) / tail.size
    model_cdf = 1.0 - special.zeta(alpha, unique + 1) / special.zeta(alpha, xmin)
    return float(np.max(np.abs(empirical_cdf - model_cdf)))


def fit_powerlaw_xmin(values: np.ndarray, xmin: int) -> PowerLawFit | None:
    tail = values[values >= xmin]
    if tail.size < 2:
        return None

    sum_log = float(np.log(tail).sum())
    n = int(tail.size)

    def objective(alpha: float) -> float:
        zeta = float(special.zeta(alpha, xmin))
        if not np.isfinite(zeta) or zeta <= 0:
            return float("inf")
        return alpha * sum_log + n * math.log(zeta)

    result = optimize.minimize_scalar(
        objective,
        bounds=(1.0001, 50.0),
        method="bounded",
        options={"xatol": 1e-8},
    )
    if not result.success:
        return None
    alpha = float(result.x)
    return PowerLawFit(
        xmin=int(xmin),
        alpha=alpha,
        ks=powerlaw_ks(values, alpha, xmin),
        tail_n=n,
        candidate_count=1,
    )


def candidate_xmins(
    values: np.ndarray,
    min_tail: int,
    max_candidates: int,
    minimum_unique_tail: int = 3,
) -> list[int]:
    unique = np.unique(values)
    candidates = [
        int(xmin)
        for xmin in unique
        if int((values >= xmin).sum()) >= min_tail
        and int(np.unique(values[values >= xmin]).size) >= minimum_unique_tail
    ]
    if len(candidates) <= max_candidates:
        return candidates
    indices = np.unique(np.linspace(0, len(candidates) - 1, max_candidates).round().astype(int))
    return [candidates[index] for index in indices]


def fit_powerlaw_auto(
    values: np.ndarray,
    min_tail: int,
    max_candidates: int,
) -> PowerLawFit | None:
    values = clean_sizes(values)
    candidates = candidate_xmins(values, min_tail, max_candidates)
    fits = [fit_powerlaw_xmin(values, xmin) for xmin in candidates]
    fits = [fit for fit in fits if fit is not None and np.isfinite(fit.ks)]
    if not fits:
        return None
    best = min(fits, key=lambda fit: (fit.ks, -fit.tail_n, fit.xmin))
    best.candidate_count = len(fits)
    return best


def bounded_powerlaw_logpmf(
    values: np.ndarray,
    alpha: float,
    xmin: int,
    xmax: int,
) -> np.ndarray:
    support = np.arange(xmin, xmax + 1, dtype=float)
    normalizer = float(np.sum(support ** (-alpha)))
    return -alpha * np.log(values) - math.log(normalizer)


def bounded_powerlaw_ks(values: np.ndarray, alpha: float, xmin: int, xmax: int) -> float:
    tail = np.sort(values[(values >= xmin) & (values <= xmax)])
    if tail.size == 0:
        return float("nan")
    support = np.arange(xmin, xmax + 1, dtype=float)
    cdf = np.cumsum(support ** (-alpha))
    cdf /= cdf[-1]
    unique, counts = np.unique(tail, return_counts=True)
    empirical_cdf = np.cumsum(counts) / tail.size
    model_cdf = cdf[unique - xmin]
    return float(np.max(np.abs(empirical_cdf - model_cdf)))


def fit_bounded_powerlaw_xmin(
    values: np.ndarray,
    xmin: int,
    xmax: int,
) -> PowerLawFit | None:
    tail = values[(values >= xmin) & (values <= xmax)]
    if tail.size < 2 or xmin >= xmax:
        return None
    support = np.arange(xmin, xmax + 1, dtype=float)
    sum_log = float(np.log(tail).sum())
    n = int(tail.size)

    def objective(alpha: float) -> float:
        normalizer = float(np.sum(support ** (-alpha)))
        return alpha * sum_log + n * math.log(normalizer)

    result = optimize.minimize_scalar(
        objective,
        bounds=(0.01, 50.0),
        method="bounded",
        options={"xatol": 1e-8},
    )
    if not result.success:
        return None
    alpha = float(result.x)
    return PowerLawFit(
        xmin=int(xmin),
        alpha=alpha,
        ks=bounded_powerlaw_ks(values, alpha, xmin, xmax),
        tail_n=n,
        candidate_count=1,
    )


def fit_bounded_powerlaw_auto(
    values: np.ndarray,
    xmax: int,
    min_tail: int,
    max_candidates: int,
) -> PowerLawFit | None:
    values = clean_sizes(values)
    values = values[values <= xmax]
    candidates = [
        xmin
        for xmin in candidate_xmins(values, min_tail, max_candidates)
        if xmin < xmax
    ]
    fits = [fit_bounded_powerlaw_xmin(values, xmin, xmax) for xmin in candidates]
    fits = [fit for fit in fits if fit is not None and np.isfinite(fit.ks)]
    if not fits:
        return None
    best = min(fits, key=lambda fit: (fit.ks, -fit.tail_n, fit.xmin))
    best.candidate_count = len(fits)
    return best


def sample_discrete_powerlaw(
    rng: np.random.Generator,
    alpha: float,
    xmin: int,
    size: int,
) -> np.ndarray:
    if alpha <= 1.05:
        raise ValueError("unbounded discrete power-law sampling is unstable for alpha <= 1.05")
    lower = float(xmin) - 0.5
    zeta = float(special.zeta(alpha, xmin))
    probe = np.arange(xmin, xmin + 10_001, dtype=float)
    proposal = (
        (probe - 0.5) ** (1.0 - alpha) - (probe + 0.5) ** (1.0 - alpha)
    ) / (lower ** (1.0 - alpha))
    target = probe ** (-alpha) / zeta
    asymptotic_ratio = 1.0 / (
        zeta * (alpha - 1.0) * lower ** (alpha - 1.0)
    )
    rejection_bound = max(float(np.max(target / proposal)), asymptotic_ratio) * 1.000001

    accepted: list[np.ndarray] = []
    count = 0
    while count < size:
        batch_size = max(1024, (size - count) * 2)
        continuous = lower * (1.0 + rng.pareto(alpha - 1.0, size=batch_size))
        finite = np.isfinite(continuous) & (continuous < np.iinfo(np.int64).max - 1)
        draws = np.floor(continuous[finite] + 0.5).astype(np.int64)
        if draws.size == 0:
            continue
        draw_values = draws.astype(float)
        proposal_mass = (
            (draw_values - 0.5) ** (1.0 - alpha)
            - (draw_values + 0.5) ** (1.0 - alpha)
        ) / (lower ** (1.0 - alpha))
        target_mass = draw_values ** (-alpha) / zeta
        acceptance = np.minimum(
            target_mass / np.maximum(rejection_bound * proposal_mass, 1e-300),
            1.0,
        )
        kept = draws[rng.random(draws.size) < acceptance]
        if kept.size:
            accepted.append(kept)
            count += int(kept.size)
    return np.concatenate(accepted)[:size].astype(np.int64)


def sample_bounded_powerlaw(
    rng: np.random.Generator,
    alpha: float,
    xmin: int,
    xmax: int,
    size: int,
) -> np.ndarray:
    support = np.arange(xmin, xmax + 1, dtype=np.int64)
    probabilities = support.astype(float) ** (-alpha)
    probabilities /= probabilities.sum()
    return rng.choice(support, size=size, replace=True, p=probabilities)


def bootstrap_powerlaw_gof(
    values: np.ndarray,
    observed: PowerLawFit,
    min_tail: int,
    max_candidates: int,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    if observed.alpha <= 1.05:
        return {
            "bootstrap_samples_requested": samples,
            "bootstrap_samples_valid": 0,
            "bootstrap_p": float("nan"),
            "bootstrap_ks_mean": float("nan"),
            "bootstrap_ks_p95": float("nan"),
            "bootstrap_status": "alpha_near_one_sampling_unstable",
        }
    rng = np.random.default_rng(seed)
    body = values[values < observed.xmin]
    body_n = int(body.size)
    ks_values: list[float] = []
    for _ in range(samples):
        synthetic_tail = sample_discrete_powerlaw(
            rng, observed.alpha, observed.xmin, observed.tail_n
        )
        if body_n:
            synthetic_body = rng.choice(body, size=body_n, replace=True)
            synthetic = np.concatenate([synthetic_body, synthetic_tail])
        else:
            synthetic = synthetic_tail
        refit = fit_powerlaw_auto(synthetic, min_tail, max_candidates)
        if refit is not None and np.isfinite(refit.ks):
            ks_values.append(refit.ks)
    valid = len(ks_values)
    p_value = (
        (1.0 + float(np.sum(np.asarray(ks_values) >= observed.ks))) / (valid + 1.0)
        if valid
        else float("nan")
    )
    return {
        "bootstrap_samples_requested": samples,
        "bootstrap_samples_valid": valid,
        "bootstrap_p": p_value,
        "bootstrap_ks_mean": float(np.mean(ks_values)) if valid else float("nan"),
        "bootstrap_ks_p95": float(np.quantile(ks_values, 0.95)) if valid else float("nan"),
        "bootstrap_status": "ok" if valid else "no_valid_refits",
    }


def bootstrap_bounded_powerlaw_gof(
    values: np.ndarray,
    observed: PowerLawFit,
    xmax: int,
    min_tail: int,
    max_candidates: int,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    body = values[values < observed.xmin]
    body_n = int(body.size)
    ks_values: list[float] = []
    for _ in range(samples):
        synthetic_tail = sample_bounded_powerlaw(
            rng, observed.alpha, observed.xmin, xmax, observed.tail_n
        )
        if body_n:
            synthetic_body = rng.choice(body, size=body_n, replace=True)
            synthetic = np.concatenate([synthetic_body, synthetic_tail])
        else:
            synthetic = synthetic_tail
        refit = fit_bounded_powerlaw_auto(synthetic, xmax, min_tail, max_candidates)
        if refit is not None and np.isfinite(refit.ks):
            ks_values.append(refit.ks)
    valid = len(ks_values)
    p_value = (
        (1.0 + float(np.sum(np.asarray(ks_values) >= observed.ks))) / (valid + 1.0)
        if valid
        else float("nan")
    )
    return {
        "bounded_bootstrap_samples_requested": samples,
        "bounded_bootstrap_samples_valid": valid,
        "bounded_bootstrap_p": p_value,
        "bounded_bootstrap_ks_mean": float(np.mean(ks_values)) if valid else float("nan"),
        "bounded_bootstrap_ks_p95": float(np.quantile(ks_values, 0.95))
        if valid
        else float("nan"),
    }


def exponential_logpmf(values: np.ndarray, xmin: int) -> tuple[np.ndarray, dict[str, float]]:
    shifted = values - xmin
    mean_shift = float(np.mean(shifted))
    q = mean_shift / (1.0 + mean_shift) if mean_shift > 0 else 1e-12
    q = float(np.clip(q, 1e-12, 1.0 - 1e-12))
    logpmf = math.log1p(-q) + shifted * math.log(q)
    return logpmf, {"exponential_q": q, "exponential_lambda": -math.log(q)}


def rounded_lognormal_logpmf(
    values: np.ndarray,
    xmin: int,
    mu: float,
    sigma: float,
) -> np.ndarray:
    lower = np.maximum(values - 0.5, 1e-12)
    upper = values + 0.5
    lower_z = (np.log(lower) - mu) / sigma
    upper_z = (np.log(upper) - mu) / sigma

    def logdiffexp(log_a: np.ndarray, log_b: np.ndarray) -> np.ndarray:
        delta = np.minimum(log_b - log_a, 0.0)
        return log_a + np.log(np.maximum(-np.expm1(delta), 1e-300))

    log_mass = np.empty_like(lower_z)
    positive = lower_z >= 0
    negative = upper_z <= 0
    crossing = ~(positive | negative)
    log_mass[positive] = logdiffexp(
        stats.norm.logsf(lower_z[positive]),
        stats.norm.logsf(upper_z[positive]),
    )
    log_mass[negative] = logdiffexp(
        stats.norm.logcdf(upper_z[negative]),
        stats.norm.logcdf(lower_z[negative]),
    )
    if np.any(crossing):
        mass = stats.norm.cdf(upper_z[crossing]) - stats.norm.cdf(lower_z[crossing])
        log_mass[crossing] = np.log(np.maximum(mass, 1e-300))
    threshold_z = (math.log(max(xmin - 0.5, 1e-12)) - mu) / sigma
    return log_mass - stats.norm.logsf(threshold_z)


def lognormal_logpmf(values: np.ndarray, xmin: int) -> tuple[np.ndarray, dict[str, float]]:
    logs = np.log(values.astype(float))
    initial_mu = float(logs.mean())
    initial_sigma = max(float(logs.std(ddof=0)), 0.2)

    def objective(theta: np.ndarray) -> float:
        mu = float(theta[0])
        sigma = math.exp(float(theta[1]))
        return -float(rounded_lognormal_logpmf(values, xmin, mu, sigma).sum())

    bounds = [(-50.0, 20.0), (math.log(0.02), math.log(30.0))]
    mu_starts = [
        initial_mu,
        math.log(float(xmin)),
        math.log(float(xmin)) - 2.0,
        math.log(float(np.max(values))),
    ]
    sigma_starts = [initial_sigma, 0.2, 0.5, 1.0, 2.0, 5.0]
    results = [
        optimize.minimize(
            objective,
            x0=np.array([mu_start, math.log(sigma_start)]),
            method="L-BFGS-B",
            bounds=bounds,
        )
        for mu_start in mu_starts
        for sigma_start in sigma_starts
    ]
    finite_results = [result for result in results if np.isfinite(result.fun)]
    if not finite_results:
        raise RuntimeError("lognormal optimization produced no finite likelihood")
    result = min(finite_results, key=lambda candidate: candidate.fun)
    mu = float(result.x[0])
    sigma = math.exp(float(result.x[1]))
    at_boundary = (
        abs(mu - bounds[0][0]) < 1e-5
        or abs(mu - bounds[0][1]) < 1e-5
        or abs(math.log(sigma) - bounds[1][0]) < 1e-5
        or abs(math.log(sigma) - bounds[1][1]) < 1e-5
    )
    return rounded_lognormal_logpmf(values, xmin, mu, sigma), {
        "lognormal_mu": mu,
        "lognormal_sigma": sigma,
        "lognormal_optimization_success": bool(result.success),
        "lognormal_optimization_at_boundary": bool(at_boundary),
        "lognormal_optimization_starts": len(results),
    }


def vuong_compare(reference_logp: np.ndarray, alternative_logp: np.ndarray) -> dict[str, float]:
    differences = reference_logp - alternative_logp
    ratio = float(differences.sum())
    if differences.size < 2 or float(differences.std(ddof=1)) <= 0:
        return {"loglikelihood_ratio": ratio, "vuong_z": float("nan"), "vuong_p": float("nan")}
    z_score = ratio / (math.sqrt(differences.size) * float(differences.std(ddof=1)))
    p_value = float(2.0 * stats.norm.sf(abs(z_score)))
    return {"loglikelihood_ratio": ratio, "vuong_z": z_score, "vuong_p": p_value}


def fit_series(
    values: np.ndarray,
    xmax: int,
    min_tail: int,
    max_candidates: int,
    bootstrap: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    values = clean_sizes(values)
    fit = fit_powerlaw_auto(values, min_tail, max_candidates)
    base = {
        "events": int(values.size),
        "unique_sizes": int(np.unique(values).size),
        "sample_min": int(values.min()) if values.size else None,
        "sample_max": int(values.max()) if values.size else None,
        "min_tail_required": min_tail,
    }
    if fit is None:
        return base | {"fit_status": "insufficient_tail"}
    tail = values[values >= fit.xmin]
    powerlaw_logp = discrete_powerlaw_logpmf(tail, fit.alpha, fit.xmin)
    exponential_logp, exponential_params = exponential_logpmf(tail, fit.xmin)
    lognormal_values, lognormal_params = lognormal_logpmf(tail, fit.xmin)
    exp_compare = vuong_compare(powerlaw_logp, exponential_logp)
    lognormal_compare = vuong_compare(powerlaw_logp, lognormal_values)
    bounded_fit = fit_bounded_powerlaw_auto(values, xmax, min_tail, max_candidates)
    bounded_stats: dict[str, Any] = {"bounded_fit_status": "insufficient_tail"}
    if bounded_fit is not None:
        bounded_tail = values[values >= bounded_fit.xmin]
        bounded_logp = bounded_powerlaw_logpmf(
            bounded_tail, bounded_fit.alpha, bounded_fit.xmin, xmax
        )
        bounded_bootstrap = bootstrap_bounded_powerlaw_gof(
            values,
            bounded_fit,
            xmax,
            min_tail,
            max_candidates,
            bootstrap,
            bootstrap_seed + 1,
        )
        bounded_stats = {
            "bounded_fit_status": "ok",
            "bounded_xmax": xmax,
            "bounded_xmin": bounded_fit.xmin,
            "bounded_alpha": bounded_fit.alpha,
            "bounded_ks": bounded_fit.ks,
            "bounded_tail_n": bounded_fit.tail_n,
            "bounded_candidate_count": bounded_fit.candidate_count,
            "bounded_powerlaw_loglikelihood": float(bounded_logp.sum()),
            **bounded_bootstrap,
        }
        if bounded_fit.xmin == fit.xmin:
            unbounded_same_tail = discrete_powerlaw_logpmf(
                bounded_tail, fit.alpha, bounded_fit.xmin
            )
            bounded_stats["bounded_vs_unbounded_R_same_xmin"] = float(
                bounded_logp.sum() - unbounded_same_tail.sum()
            )
        else:
            bounded_stats["bounded_vs_unbounded_R_same_xmin"] = float("nan")
    bootstrap_stats = bootstrap_powerlaw_gof(
        values,
        fit,
        min_tail,
        max_candidates,
        bootstrap,
        bootstrap_seed,
    )
    return base | {
        "fit_status": "ok",
        **asdict(fit),
        "powerlaw_loglikelihood": float(powerlaw_logp.sum()),
        **bootstrap_stats,
        **exponential_params,
        "pl_vs_exponential_R": exp_compare["loglikelihood_ratio"],
        "pl_vs_exponential_z": exp_compare["vuong_z"],
        "pl_vs_exponential_p": exp_compare["vuong_p"],
        **lognormal_params,
        "pl_vs_lognormal_R": lognormal_compare["loglikelihood_ratio"],
        "pl_vs_lognormal_z": lognormal_compare["vuong_z"],
        "pl_vs_lognormal_p": lognormal_compare["vuong_p"],
        **bounded_stats,
    }


def audit_existing_results() -> pd.DataFrame:
    rows = []
    for result_dir in sorted((ROOT / "results").glob("credit_soc_*20260604*")):
        run_path = result_dir / "run_summary.csv"
        event_path = result_dir / "avalanche_events.csv"
        if not run_path.exists() and not event_path.exists():
            continue
        run_df = pd.read_csv(run_path) if run_path.exists() else pd.DataFrame()
        event_df = pd.read_csv(event_path) if event_path.exists() else pd.DataFrame()
        rows.append(
            {
                "result_dir": str(result_dir),
                "runs": len(run_df),
                "scenarios": int(run_df["scenario_id"].nunique())
                if len(run_df) and "scenario_id" in run_df
                else 0,
                "events": len(event_df),
                "seed_min": int(run_df["seed"].min()) if len(run_df) and "seed" in run_df else None,
                "seed_max": int(run_df["seed"].max()) if len(run_df) and "seed" in run_df else None,
                "max_event_size": int(event_df["collapse_size"].max())
                if len(event_df) and "collapse_size" in event_df
                else 0,
            }
        )
    return pd.DataFrame(rows)


def add_existing_series(
    series: list[tuple[dict[str, Any], np.ndarray]],
    existing_c020_dir: Path,
    existing_fixed_dir: Path,
) -> None:
    c020_path = existing_c020_dir / "avalanche_events.csv"
    if c020_path.exists():
        events = pd.read_csv(c020_path)
        for scenario_id, sub in events.groupby("scenario_id"):
            series.append(
                (
                    {
                        "series_id": f"existing_c020__{scenario_id}",
                        "source": "existing_c020_focus",
                        "family": "existing_income_c020",
                        "scenario_id": scenario_id,
                        "control_value": 0.20,
                        "n_nodes": 200,
                        "money_distribution": sub["money_distribution"].iloc[0],
                    },
                    clean_sizes(sub["collapse_size"]),
                )
            )

    fixed_path = existing_fixed_dir / "combined_avalanche_events.csv"
    if fixed_path.exists():
        events = pd.read_csv(fixed_path)
        events = events[
            events["growth_rule"].eq("random")
            & events["income_distribution_rule"].eq("biased")
            & events["fixed_k"].isin([10, 20, 30, 50])
            & events["money_distribution"].isin(["lognormal", "pareto"])
        ]
        for keys, sub in events.groupby(["fixed_k", "money_distribution"]):
            fixed_k, distribution = keys
            series.append(
                (
                    {
                        "series_id": f"existing_fixed_K{fixed_k}__{distribution}",
                        "source": "existing_fixed_sweep",
                        "family": "existing_fixed",
                        "scenario_id": f"K{fixed_k}__{distribution}__biased__random",
                        "control_value": float(fixed_k),
                        "n_nodes": 200,
                        "money_distribution": distribution,
                    },
                    clean_sizes(sub["collapse_size"]),
                )
            )


def build_series(new_events: pd.DataFrame) -> list[tuple[dict[str, Any], np.ndarray]]:
    series = []
    for scenario_id, sub in new_events.groupby("scenario_id"):
        first = sub.iloc[0]
        series.append(
            (
                {
                    "series_id": f"phase2__{scenario_id}",
                    "source": "phase2_new",
                    "family": first["family"],
                    "scenario_id": scenario_id,
                    "control_value": float(first["control_value"]),
                    "n_nodes": int(first["n_nodes"]),
                    "money_distribution": first["money_distribution"],
                },
                clean_sizes(sub["collapse_size"]),
            )
        )
    return series


def per_seed_tail_fits(
    events: pd.DataFrame,
    min_tail: int,
    max_candidates: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for keys, sub in events.groupby(["scenario_id", "seed"]):
        scenario_id, seed = keys
        first = sub.iloc[0]
        values = clean_sizes(sub["collapse_size"])
        xmax = int(first["n_nodes"])
        fit = fit_powerlaw_auto(values, min_tail, max_candidates)
        bounded_fit = fit_bounded_powerlaw_auto(values, xmax, min_tail, max_candidates)
        rows.append(
            {
                "scenario_id": scenario_id,
                "family": first["family"],
                "control_value": float(first["control_value"]),
                "n_nodes": xmax,
                "money_distribution": first["money_distribution"],
                "seed": int(seed),
                "events": len(values),
                "fit_status": "ok" if fit is not None else "insufficient_tail",
                "xmin": fit.xmin if fit is not None else np.nan,
                "alpha": fit.alpha if fit is not None else np.nan,
                "ks": fit.ks if fit is not None else np.nan,
                "tail_n": fit.tail_n if fit is not None else 0,
                "bounded_fit_status": "ok" if bounded_fit is not None else "insufficient_tail",
                "bounded_xmin": bounded_fit.xmin if bounded_fit is not None else np.nan,
                "bounded_alpha": bounded_fit.alpha if bounded_fit is not None else np.nan,
                "bounded_ks": bounded_fit.ks if bounded_fit is not None else np.nan,
                "bounded_tail_n": bounded_fit.tail_n if bounded_fit is not None else 0,
            }
        )
    per_seed = pd.DataFrame(rows)
    summaries = []
    for scenario_id, sub in per_seed.groupby("scenario_id"):
        valid = sub[sub["fit_status"] == "ok"]
        bounded_valid = sub[sub["bounded_fit_status"] == "ok"]
        first = sub.iloc[0]
        summaries.append(
            {
                "scenario_id": scenario_id,
                "family": first["family"],
                "control_value": first["control_value"],
                "n_nodes": int(first["n_nodes"]),
                "money_distribution": first["money_distribution"],
                "seeds": len(sub),
                "unbounded_valid_seed_fraction": len(valid) / len(sub),
                "unbounded_alpha_median": float(valid["alpha"].median()) if len(valid) else np.nan,
                "unbounded_alpha_iqr": float(
                    valid["alpha"].quantile(0.75) - valid["alpha"].quantile(0.25)
                )
                if len(valid)
                else np.nan,
                "unbounded_xmin_median": float(valid["xmin"].median()) if len(valid) else np.nan,
                "unbounded_ks_median": float(valid["ks"].median()) if len(valid) else np.nan,
                "bounded_valid_seed_fraction": len(bounded_valid) / len(sub),
                "bounded_alpha_median": float(bounded_valid["bounded_alpha"].median())
                if len(bounded_valid)
                else np.nan,
                "bounded_alpha_iqr": float(
                    bounded_valid["bounded_alpha"].quantile(0.75)
                    - bounded_valid["bounded_alpha"].quantile(0.25)
                )
                if len(bounded_valid)
                else np.nan,
                "bounded_xmin_median": float(bounded_valid["bounded_xmin"].median())
                if len(bounded_valid)
                else np.nan,
                "bounded_ks_median": float(bounded_valid["bounded_ks"].median())
                if len(bounded_valid)
                else np.nan,
            }
        )
    return per_seed, pd.DataFrame(summaries)


def summarize_time_windows(
    events: pd.DataFrame,
    runs: pd.DataFrame,
    series_id: str,
    source: str,
    family: str,
) -> list[dict[str, Any]]:
    periods_by_seed = runs.set_index("seed")["periods_completed"].to_dict()
    period_counts = np.zeros(4, dtype=int)
    event_frames: list[pd.DataFrame] = []
    for seed, periods_completed in periods_by_seed.items():
        periods_completed = int(periods_completed)
        if periods_completed <= 0:
            continue
        period_numbers = np.arange(1, periods_completed + 1)
        period_quartiles = np.minimum(3, (period_numbers - 1) * 4 // periods_completed)
        period_counts += np.bincount(period_quartiles, minlength=4)
        seed_events = events[events["seed"] == seed].copy()
        if len(seed_events):
            seed_events["time_quartile"] = (
                np.minimum(
                    3,
                    (seed_events["period"].to_numpy(dtype=int) - 1)
                    * 4
                    // periods_completed,
                )
                + 1
            )
            event_frames.append(seed_events)
    tagged = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    rows = []
    for quartile in range(1, 5):
        sub = tagged[tagged["time_quartile"] == quartile] if len(tagged) else tagged
        sizes = sub["collapse_size"].to_numpy(dtype=float) if len(sub) else np.array([])
        rows.append(
            {
                "series_id": series_id,
                "source": source,
                "family": family,
                "time_quartile": quartile,
                "periods": int(period_counts[quartile - 1]),
                "events": len(sub),
                "event_period_fraction": len(sub) / period_counts[quartile - 1]
                if period_counts[quartile - 1]
                else np.nan,
                "mean_size": float(np.mean(sizes)) if sizes.size else np.nan,
                "median_size": float(np.median(sizes)) if sizes.size else np.nan,
                "p90_size": float(np.quantile(sizes, 0.90)) if sizes.size else np.nan,
                "large_event_rate": float(sub["critical_event"].mean()) if len(sub) else np.nan,
            }
        )
    return rows


def time_window_summary(
    new_events: pd.DataFrame,
    new_runs: pd.DataFrame,
    existing_c020_dir: Path,
    existing_fixed_dir: Path,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scenario_id, event_sub in new_events.groupby("scenario_id"):
        run_sub = new_runs[new_runs["scenario_id"] == scenario_id]
        rows.extend(
            summarize_time_windows(
                event_sub,
                run_sub,
                f"phase2__{scenario_id}",
                "phase2_new",
                event_sub["family"].iloc[0],
            )
        )

    c020_event_path = existing_c020_dir / "avalanche_events.csv"
    c020_run_path = existing_c020_dir / "run_summary.csv"
    if c020_event_path.exists() and c020_run_path.exists():
        c020_events = pd.read_csv(c020_event_path)
        c020_runs = pd.read_csv(c020_run_path)
        for scenario_id, event_sub in c020_events.groupby("scenario_id"):
            run_sub = c020_runs[c020_runs["scenario_id"] == scenario_id]
            rows.extend(
                summarize_time_windows(
                    event_sub,
                    run_sub,
                    f"existing_c020__{scenario_id}",
                    "existing_c020_focus",
                    "existing_income_c020",
                )
            )

    fixed_event_path = existing_fixed_dir / "combined_avalanche_events.csv"
    fixed_run_path = existing_fixed_dir / "combined_run_summary.csv"
    if fixed_event_path.exists() and fixed_run_path.exists():
        fixed_events = pd.read_csv(fixed_event_path)
        fixed_runs = pd.read_csv(fixed_run_path)
        for fixed_k in [20, 30]:
            for distribution in ["lognormal", "pareto"]:
                event_sub = fixed_events[
                    fixed_events["fixed_k"].eq(fixed_k)
                    & fixed_events["money_distribution"].eq(distribution)
                    & fixed_events["income_distribution_rule"].eq("biased")
                    & fixed_events["growth_rule"].eq("random")
                ]
                run_sub = fixed_runs[
                    fixed_runs["fixed_k"].eq(fixed_k)
                    & fixed_runs["money_distribution"].eq(distribution)
                    & fixed_runs["income_distribution_rule"].eq("biased")
                    & fixed_runs["growth_rule"].eq("random")
                ]
                if len(run_sub):
                    rows.extend(
                        summarize_time_windows(
                            event_sub,
                            run_sub,
                            f"existing_fixed_K{fixed_k}__{distribution}",
                            "existing_fixed_sweep",
                            "existing_fixed",
                        )
                    )
    return pd.DataFrame(rows)


def finite_size_summary(events: pd.DataFrame, runs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, sub in events[events["family"].isin(["finite_fixed", "finite_income"])].groupby(
        ["family", "n_nodes"]
    ):
        family, n_nodes = keys
        sizes = sub["collapse_size"].to_numpy(dtype=float)
        run_sub = runs[(runs["family"] == family) & (runs["n_nodes"] == n_nodes)]
        rows.append(
            {
                "family": family,
                "n_nodes": int(n_nodes),
                "fixed_k": int(sub["fixed_period_length_steps"].iloc[0]),
                "k_per_node": sub["k_per_node"].iloc[0],
                "c": sub["investment_income_propensity"].iloc[0],
                "runs": len(run_sub),
                "events": len(sizes),
                "events_per_run": len(sizes) / max(len(run_sub), 1),
                "mean_size": float(np.mean(sizes)),
                "second_moment": float(np.mean(sizes**2)),
                "moment_ratio_m2_m1": float(np.mean(sizes**2) / np.mean(sizes)),
                "p90": float(np.quantile(sizes, 0.90)),
                "p95": float(np.quantile(sizes, 0.95)),
                "p99": float(np.quantile(sizes, 0.99)),
                "max_size": int(np.max(sizes)),
                "p99_fraction": float(np.quantile(sizes, 0.99) / n_nodes),
                "max_fraction": float(np.max(sizes) / n_nodes),
                "event_critical_rate": float(np.mean(sizes >= 0.10 * n_nodes)),
            }
        )
    return pd.DataFrame(rows).sort_values(["family", "n_nodes"])


def event_trigger_decomposition(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario_id, sub in events.groupby("scenario_id"):
        n_nodes = int(sub["n_nodes"].iloc[0])
        initial = sub["initial_default_count"].to_numpy(dtype=float)
        sizes = sub["collapse_size"].to_numpy(dtype=float)
        propagated = sizes - initial
        total_size = float(np.sum(sizes))
        total_initial = float(np.sum(initial))
        total_propagated = float(np.sum(propagated))
        rows.append(
            {
                "family": sub["family"].iloc[0],
                "scenario_id": scenario_id,
                "control_name": sub["control_name"].iloc[0],
                "control_value": sub["control_value"].iloc[0],
                "n_nodes": n_nodes,
                "money_distribution": sub["money_distribution"].iloc[0],
                "events": len(sub),
                "single_initial_event_rate": float(np.mean(initial == 1)),
                "multi_initial_event_rate": float(np.mean(initial > 1)),
                "propagation_event_rate": float(np.mean(propagated > 0)),
                "total_size": int(total_size),
                "total_initial_defaults": int(total_initial),
                "total_propagated_defaults": int(total_propagated),
                "propagated_share_of_total_size": total_propagated / total_size,
                "mean_size": float(np.mean(sizes)),
                "mean_initial_defaults": float(np.mean(initial)),
                "mean_propagated_defaults": float(np.mean(propagated)),
                "mean_size_per_node": float(np.mean(sizes) / n_nodes),
                "mean_initial_defaults_per_node": float(np.mean(initial) / n_nodes),
                "mean_propagated_defaults_per_node": float(np.mean(propagated) / n_nodes),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["family", "n_nodes", "money_distribution", "control_value"]
    )


def finite_scaling_slopes(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for family, sub in summary.groupby("family"):
        for metric in ["mean_size", "second_moment", "moment_ratio_m2_m1", "p99", "max_size"]:
            regression = stats.linregress(np.log(sub["n_nodes"]), np.log(sub[metric]))
            rows.append(
                {
                    "family": family,
                    "metric": metric,
                    "log_log_slope": float(regression.slope),
                    "slope_stderr": float(regression.stderr),
                    "r_squared": float(regression.rvalue**2),
                    "p_value": float(regression.pvalue),
                    "n_sizes": len(sub),
                }
            )
    return pd.DataFrame(rows)


def temporal_metrics(events: pd.DataFrame, runs: pd.DataFrame, series_id: str) -> dict[str, Any]:
    total_periods = int(runs["periods_completed"].sum())
    wait_values: list[np.ndarray] = []
    current_sizes: list[np.ndarray] = []
    next_sizes: list[np.ndarray] = []
    for _, sub in events.groupby("seed"):
        ordered = sub.sort_values(["period", "avalanche_index"])
        periods = ordered["period"].to_numpy(dtype=int)
        sizes = ordered["collapse_size"].to_numpy(dtype=float)
        if periods.size >= 2:
            wait_values.append(np.diff(periods))
            current_sizes.append(sizes[:-1])
            next_sizes.append(sizes[1:])
    waits = np.concatenate(wait_values) if wait_values else np.array([], dtype=int)
    lag_current = np.concatenate(current_sizes) if current_sizes else np.array([], dtype=float)
    lag_next = np.concatenate(next_sizes) if next_sizes else np.array([], dtype=float)
    lag_correlation = (
        float(np.corrcoef(lag_current, lag_next)[0, 1])
        if lag_current.size >= 3
        and float(np.std(lag_current)) > 0
        and float(np.std(lag_next)) > 0
        else float("nan")
    )
    return {
        "series_id": series_id,
        "runs": len(runs),
        "total_periods": total_periods,
        "events": len(events),
        "event_period_fraction": len(events) / total_periods if total_periods else float("nan"),
        "inter_event_waits": len(waits),
        "wait_equal_1_fraction": float(np.mean(waits == 1)) if waits.size else float("nan"),
        "wait_median": float(np.median(waits)) if waits.size else float("nan"),
        "wait_p90": float(np.quantile(waits, 0.90)) if waits.size else float("nan"),
        "lag1_pairs": len(lag_current),
        "size_lag1_correlation": lag_correlation,
    }


def temporal_separation_summary(
    new_events: pd.DataFrame,
    new_runs: pd.DataFrame,
    existing_c020_dir: Path,
    existing_fixed_dir: Path,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scenario_id, event_sub in new_events.groupby("scenario_id"):
        run_sub = new_runs[new_runs["scenario_id"] == scenario_id]
        rows.append(
            temporal_metrics(event_sub, run_sub, f"phase2__{scenario_id}")
            | {"source": "phase2_new", "family": event_sub["family"].iloc[0]}
        )

    c020_event_path = existing_c020_dir / "avalanche_events.csv"
    c020_run_path = existing_c020_dir / "run_summary.csv"
    if c020_event_path.exists() and c020_run_path.exists():
        c020_events = pd.read_csv(c020_event_path)
        c020_runs = pd.read_csv(c020_run_path)
        for scenario_id, event_sub in c020_events.groupby("scenario_id"):
            run_sub = c020_runs[c020_runs["scenario_id"] == scenario_id]
            rows.append(
                temporal_metrics(event_sub, run_sub, f"existing_c020__{scenario_id}")
                | {"source": "existing_c020_focus", "family": "existing_income_c020"}
            )

    fixed_event_path = existing_fixed_dir / "combined_avalanche_events.csv"
    fixed_run_path = existing_fixed_dir / "combined_run_summary.csv"
    if fixed_event_path.exists() and fixed_run_path.exists():
        fixed_events = pd.read_csv(fixed_event_path)
        fixed_runs = pd.read_csv(fixed_run_path)
        fixed_events = fixed_events[
            fixed_events["growth_rule"].eq("random")
            & fixed_events["income_distribution_rule"].eq("biased")
            & fixed_events["fixed_k"].isin([20, 30])
        ]
        fixed_runs = fixed_runs[
            fixed_runs["growth_rule"].eq("random")
            & fixed_runs["income_distribution_rule"].eq("biased")
            & fixed_runs["fixed_k"].isin([20, 30])
        ]
        for keys, event_sub in fixed_events.groupby(["fixed_k", "money_distribution"]):
            fixed_k, distribution = keys
            run_sub = fixed_runs[
                fixed_runs["fixed_k"].eq(fixed_k)
                & fixed_runs["money_distribution"].eq(distribution)
            ]
            rows.append(
                temporal_metrics(
                    event_sub,
                    run_sub,
                    f"existing_fixed_K{fixed_k}__{distribution}",
                )
                | {"source": "existing_fixed_sweep", "family": "existing_fixed"}
            )
    return pd.DataFrame(rows)


def plot_transition_curves(summary: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.5))
    specs = [
        ("income", "event_critical_rate", "c", "Large-event rate"),
        ("income", "mean_event_size", "c", "Mean avalanche size"),
        ("fixed", "event_critical_rate", "Fixed K", "Large-event rate"),
        ("fixed", "mean_event_size", "Fixed K", "Mean avalanche size"),
    ]
    for ax, (family, metric, xlabel, ylabel) in zip(axes.flat, specs):
        sub = summary[summary["family"] == family]
        for distribution, dist_sub in sub.groupby("money_distribution"):
            dist_sub = dist_sub.sort_values("control_value")
            ax.plot(
                dist_sub["control_value"],
                dist_sub[metric],
                marker="o",
                linewidth=1.8,
                label=distribution,
            )
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("Phase-2 fine transition scans: biased income + random growth")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def plot_finite_size(summary: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.5))
    metrics = [
        ("p99", "P99 cutoff proxy"),
        ("moment_ratio_m2_m1", "Moment ratio E[S²]/E[S]"),
        ("p99_fraction", "P99 / N"),
        ("event_critical_rate", "P(S >= 0.1 N)"),
    ]
    for ax, (metric, ylabel) in zip(axes.flat, metrics):
        for family, sub in summary.groupby("family"):
            sub = sub.sort_values("n_nodes")
            ax.plot(sub["n_nodes"], sub[metric], marker="o", linewidth=1.8, label=family)
        ax.set_xscale("log")
        if metric in {"p99", "moment_ratio_m2_m1"}:
            ax.set_yscale("log")
        ax.set_xlabel("N")
        ax.set_ylabel(ylabel)
        ax.grid(True, which="both", alpha=0.25)
        ax.legend()
    fig.suptitle("Finite-size evidence under drive-preserving protocols")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def plot_trigger_decomposition(summary: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 9.0))
    fine_specs = [
        ("income", "Income-driven lognormal fine scan", "c"),
        ("fixed", "Fixed-K lognormal fine scan", "K"),
    ]
    for ax, (family, title, xlabel) in zip(axes[0], fine_specs):
        sub = summary[
            (summary["family"] == family)
            & (summary["money_distribution"] == "lognormal")
        ].sort_values("control_value")
        ax.plot(
            sub["control_value"],
            sub["single_initial_event_rate"],
            marker="o",
            linewidth=1.8,
            label="P(initial defaults = 1)",
        )
        ax.plot(
            sub["control_value"],
            sub["propagated_share_of_total_size"],
            marker="s",
            linewidth=1.8,
            label="Propagated / total size",
        )
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Fraction")
        ax.set_ylim(0, 0.22)
        ax.set_title(title)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)

    finite = summary[summary["family"].isin(["finite_fixed", "finite_income"])]
    ax = axes[1, 0]
    for family, sub in finite.groupby("family"):
        sub = sub.sort_values("n_nodes")
        ax.plot(
            sub["n_nodes"],
            sub["mean_initial_defaults_per_node"],
            marker="o",
            linewidth=1.8,
            label=f"{family}: initial / N",
        )
        ax.plot(
            sub["n_nodes"],
            sub["mean_propagated_defaults_per_node"],
            marker="s",
            linestyle="--",
            linewidth=1.8,
            label=f"{family}: propagated / N",
        )
    ax.set_xscale("log")
    ax.set_xlabel("N")
    ax.set_ylabel("Mean defaults per event / N")
    ax.set_title("Finite-size initial versus propagated components")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8)

    ax = axes[1, 1]
    for family, sub in finite.groupby("family"):
        sub = sub.sort_values("n_nodes")
        ax.plot(
            sub["n_nodes"],
            sub["propagated_share_of_total_size"],
            marker="o",
            linewidth=1.8,
            label=family,
        )
    ax.set_xscale("log")
    ax.set_xlabel("N")
    ax.set_ylabel("Propagated / total size")
    ax.set_ylim(0, 0.18)
    ax.set_title("Finite-size propagation share")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(fontsize=8)

    fig.suptitle("Event-definition audit: synchronous initial defaults dominate recorded size")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def plot_temporal_separation(summary: pd.DataFrame, output_path: Path) -> None:
    preferred = summary[
        summary["series_id"].str.contains(
            "existing_c020|existing_fixed_K20__lognormal|existing_fixed_K30__lognormal|"
            "phase2__income__c0p18__lognormal|phase2__fixed__K24__lognormal",
            regex=True,
        )
    ].copy()
    if preferred.empty:
        preferred = summary.head(8).copy()
    preferred = preferred.sort_values("series_id")
    labels = preferred["series_id"].str.replace("phase2__", "", regex=False)
    fig, axes = plt.subplots(1, 3, figsize=(15, 6.2))
    metrics = [
        ("event_period_fraction", "Fraction of periods with avalanche"),
        ("wait_equal_1_fraction", "P(inter-event wait = 1 period)"),
        ("size_lag1_correlation", "Avalanche-size lag-1 correlation"),
    ]
    for ax, (metric, ylabel) in zip(axes, metrics):
        ax.bar(np.arange(len(preferred)), preferred[metric], color="#4c78a8", alpha=0.85)
        ax.set_xticks(np.arange(len(preferred)), labels, rotation=70, ha="right", fontsize=7)
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, 1)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Temporal separation diagnostic: persistent activity versus isolated avalanches")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def plot_time_window_drift(summary: pd.DataFrame, output_path: Path) -> None:
    preferred = summary[
        summary["series_id"].str.contains(
            "existing_c020__lognormal|existing_fixed_K20__lognormal|"
            "existing_fixed_K30__lognormal|phase2__income__c0p18__lognormal|"
            "phase2__fixed__K24__lognormal",
            regex=True,
        )
    ]
    if preferred.empty:
        preferred = summary[summary["series_id"].isin(summary["series_id"].unique()[:5])]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5))
    for series_id, sub in preferred.groupby("series_id"):
        sub = sub.sort_values("time_quartile")
        label = series_id.replace("phase2__", "")
        axes[0].plot(sub["time_quartile"], sub["mean_size"], marker="o", label=label)
        axes[1].plot(sub["time_quartile"], sub["large_event_rate"], marker="o", label=label)
        axes[2].plot(sub["time_quartile"], sub["event_period_fraction"], marker="o", label=label)
    labels = ["Mean avalanche size", "Large-event rate", "Fraction of periods with event"]
    for ax, ylabel in zip(axes, labels):
        ax.set_xticks([1, 2, 3, 4])
        ax.set_xlabel("Run-time quartile")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
    axes[2].legend(fontsize=7, loc="best")
    fig.suptitle("Within-run distribution drift and nonstationarity")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def model_ccdf(x_values: np.ndarray, fit_row: pd.Series) -> dict[str, np.ndarray]:
    xmin = int(fit_row["xmin"])
    alpha = float(fit_row["alpha"])
    q = float(fit_row["exponential_q"])
    mu = float(fit_row["lognormal_mu"])
    sigma = float(fit_row["lognormal_sigma"])
    powerlaw = special.zeta(alpha, x_values) / special.zeta(alpha, xmin)
    exponential = q ** (x_values - xmin)
    lognormal = stats.norm.sf(
        (np.log(np.maximum(x_values - 0.5, 1e-12)) - mu) / sigma
    ) / stats.norm.sf((math.log(max(xmin - 0.5, 1e-12)) - mu) / sigma)
    return {"Power law": powerlaw, "Exponential": exponential, "Lognormal": lognormal}


def plot_fit_comparison(
    fits: pd.DataFrame,
    series_map: dict[str, np.ndarray],
    output_path: Path,
) -> None:
    preferred = [
        "phase2__income__c0p18__lognormal__biased__random",
        "phase2__fixed__K24__lognormal__biased__random",
        "existing_c020__lognormal__biased__random",
        "existing_fixed_K30__lognormal",
    ]
    selected = [series_id for series_id in preferred if series_id in series_map]
    if not selected:
        selected = fits.loc[fits["fit_status"].eq("ok"), "series_id"].head(4).tolist()
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.8))
    for ax, series_id in zip(axes.flat, selected):
        row = fits[fits["series_id"] == series_id].iloc[0]
        values = np.sort(series_map[series_id])
        xmin = int(row["xmin"])
        tail = values[values >= xmin]
        x_values = np.arange(xmin, int(tail.max()) + 1)
        empirical = np.array([(tail >= x).mean() for x in x_values])
        ax.loglog(x_values, empirical, "o", markersize=3.5, label="Empirical")
        for label, ccdf in model_ccdf(x_values, row).items():
            ax.loglog(x_values, ccdf, linewidth=1.5, label=label)
        ax.set_title(f"{series_id}\nxmin={xmin}, n_tail={int(row['tail_n'])}, p_boot={row['bootstrap_p']:.3f}", fontsize=9)
        ax.set_xlabel("Avalanche size")
        ax.set_ylabel("Conditional tail CCDF")
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(fontsize=7)
    for ax in axes.flat[len(selected) :]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def plot_strict_evidence(fits: pd.DataFrame, output_path: Path) -> None:
    sub = fits[(fits["source"] == "phase2_new") & fits["family"].isin(["income", "fixed"])]
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5))
    for ax, family in zip(axes, ["income", "fixed"]):
        family_sub = sub[sub["family"] == family].sort_values(
            ["money_distribution", "control_value"]
        )
        labels = [
            f"{row.money_distribution}:{row.control_value:g}" for row in family_sub.itertuples()
        ]
        x = np.arange(len(family_sub))
        width = 0.38
        ax.bar(
            x - width / 2,
            family_sub["bootstrap_p"],
            width=width,
            color="#e45756",
            alpha=0.8,
            label="Unbounded pure power law",
        )
        ax.bar(
            x + width / 2,
            family_sub["bounded_bootstrap_p"],
            width=width,
            color="#4c78a8",
            alpha=0.8,
            label="Bounded power law, xmax=N",
        )
        ax.axhline(0.10, color="black", linestyle="--", linewidth=1, label="p=0.10")
        ax.set_xticks(x, labels, rotation=50, ha="right", fontsize=8)
        ax.set_ylim(0, 1)
        ax.set_ylabel("KS bootstrap p-value")
        ax.set_title(f"{family}: unbounded versus finite-support power law")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=190)
    plt.close(fig)


def write_analysis_note(
    output_dir: Path,
    audit: pd.DataFrame,
    fits: pd.DataFrame,
    finite: pd.DataFrame,
    slopes: pd.DataFrame,
    temporal: pd.DataFrame,
    seed_robustness: pd.DataFrame,
    time_windows: pd.DataFrame,
    decomposition: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    valid = fits[fits["fit_status"] == "ok"]
    not_rejected = valid[valid["bootstrap_p"] >= 0.10]
    rejected = valid[valid["bootstrap_p"] < 0.10]
    lognormal_better = valid[
        (valid["pl_vs_lognormal_R"] < 0) & (valid["pl_vs_lognormal_p"] < 0.10)
    ]
    lines = [
        "# Phase-2 strict SOC analysis artifact note",
        "",
        f"Generated: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## Statistical protocol",
        "",
        f"- Positive integer avalanche sizes; minimum accepted tail sample: {args.min_tail}.",
        "- Pure unbounded discrete power law uses exact Hurwitz-zeta likelihood.",
        f"- `xmin` is selected by minimum KS over up to {args.max_xmin_candidates} reproducible candidates.",
        f"- Semiparametric KS bootstrap reselects `xmin`; requested replicates per series: {args.bootstrap}.",
        "- A second power-law null is explicitly normalized on finite support `[xmin, N]` and bootstrapped separately.",
        "- Alternatives share the selected tail: shifted discrete exponential and rounded/conditioned lognormal.",
        "- Likelihood signs are `R = log L_powerlaw - log L_alternative`; Vuong p-values are descriptive.",
        f"- Per-seed fits use minimum tail size {args.per_seed_min_tail}; pooled-event p-values are diagnostic because events are serially dependent.",
        "",
        "## Counts",
        "",
        f"- Existing result directories audited: {len(audit)}.",
        f"- Series fitted: {len(fits)}; valid fits: {len(valid)}.",
        f"- Pure power law not rejected at p>=0.10: {len(not_rejected)}.",
        f"- Pure power law rejected at p<0.10: {len(rejected)}.",
        f"- Lognormal significantly better at descriptive p<0.10: {len(lognormal_better)}.",
        f"- Temporal-separation series analyzed: {len(temporal)}.",
        f"- Per-seed robustness scenarios analyzed: {len(seed_robustness)}.",
        f"- Time-window rows analyzed: {len(time_windows)}.",
        f"- Initial-versus-propagated scenario rows analyzed: {len(decomposition)}.",
        "",
        "## Limitations",
        "",
        "- Avalanche events within a run are serially dependent; event-level bootstrap treats sizes as exchangeable and can overstate effective sample size.",
        "- High event-period occupancy or one-period waits alone do not exclude SOC; here they are dependence diagnostics interpreted jointly with lag-1 correlation, drift, repeated defaults, and terminal degeneration.",
        "- A recorded event can begin with multiple synchronous defaults at period-end settlement, so its size is not necessarily a single-trigger avalanche size.",
        "- The pure unbounded power-law null conflicts with finite-network support; bounded-power-law fits describe finite cutoffs but do not prove strict SOC.",
        "- Strong within-run quartile drift invalidates stationary pooled-tail interpretation unless a stationary window is established.",
        "- Four system sizes can show cutoff growth but cannot establish a universal finite-size exponent.",
        "",
        "## Evidence files",
        "",
        "- `existing_result_audit.csv`",
        "- `strict_tail_fits.csv`, `per_seed_tail_fits.csv`, and `seed_robustness_summary.csv`",
        "- `finite_size_summary.csv`, `finite_size_scaling_slopes.csv`, `event_trigger_decomposition.csv`, `finite_size_initial_vs_propagated.csv`, `temporal_separation_summary.csv`, and `time_window_summary.csv`",
        "- `transition_fine_scan.png`, `strict_fit_comparison.png`, `strict_powerlaw_gof.png`, `finite_size_scaling.png`, `initial_vs_propagated_decomposition.png`, `temporal_separation.png`, `time_window_drift.png`",
    ]
    (output_dir / "analysis_note.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or args.result_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    runs = pd.read_csv(args.result_dir / "run_summary.csv")
    events = pd.read_csv(args.result_dir / "avalanche_events.csv")
    sweep_summary = pd.read_csv(args.result_dir / "sweep_summary.csv")

    audit = audit_existing_results()
    audit.to_csv(output_dir / "existing_result_audit.csv", index=False)

    series = build_series(events)
    add_existing_series(series, args.existing_c020_dir, args.existing_fixed_dir)
    series_map = {metadata["series_id"]: values for metadata, values in series}
    fit_rows = []
    for index, (metadata, values) in enumerate(series):
        fit = fit_series(
            values,
            int(metadata["n_nodes"]),
            args.min_tail,
            args.max_xmin_candidates,
            args.bootstrap,
            args.bootstrap_seed + index * 10_000,
        )
        fit_rows.append(metadata | fit)
        if args.progress_every > 0 and ((index + 1) % args.progress_every == 0 or index + 1 == len(series)):
            print(
                f"fitted_series={index + 1}/{len(series)} "
                f"time={datetime.now(CST).isoformat()}",
                flush=True,
            )
    fits = pd.DataFrame(fit_rows)
    fits.to_csv(output_dir / "strict_tail_fits.csv", index=False)
    per_seed, seed_robustness = per_seed_tail_fits(
        events, args.per_seed_min_tail, args.max_xmin_candidates
    )
    per_seed.to_csv(output_dir / "per_seed_tail_fits.csv", index=False)
    seed_robustness.to_csv(output_dir / "seed_robustness_summary.csv", index=False)

    finite = finite_size_summary(events, runs)
    finite.to_csv(output_dir / "finite_size_summary.csv", index=False)
    slopes = finite_scaling_slopes(finite)
    slopes.to_csv(output_dir / "finite_size_scaling_slopes.csv", index=False)
    decomposition = event_trigger_decomposition(events)
    decomposition.to_csv(output_dir / "event_trigger_decomposition.csv", index=False)
    decomposition[decomposition["family"].isin(["finite_fixed", "finite_income"])].to_csv(
        output_dir / "finite_size_initial_vs_propagated.csv", index=False
    )
    temporal = temporal_separation_summary(
        events, runs, args.existing_c020_dir, args.existing_fixed_dir
    )
    temporal.to_csv(output_dir / "temporal_separation_summary.csv", index=False)
    time_windows = time_window_summary(
        events, runs, args.existing_c020_dir, args.existing_fixed_dir
    )
    time_windows.to_csv(output_dir / "time_window_summary.csv", index=False)

    plot_transition_curves(sweep_summary, output_dir / "transition_fine_scan.png")
    plot_finite_size(finite, output_dir / "finite_size_scaling.png")
    plot_trigger_decomposition(
        decomposition, output_dir / "initial_vs_propagated_decomposition.png"
    )
    plot_fit_comparison(fits, series_map, output_dir / "strict_fit_comparison.png")
    plot_strict_evidence(fits, output_dir / "strict_powerlaw_gof.png")
    plot_temporal_separation(temporal, output_dir / "temporal_separation.png")
    plot_time_window_drift(time_windows, output_dir / "time_window_drift.png")
    write_analysis_note(
        output_dir,
        audit,
        fits,
        finite,
        slopes,
        temporal,
        seed_robustness,
        time_windows,
        decomposition,
        args,
    )

    metadata = {
        "created_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "command_args": {
            key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
        },
        "statistical_hypotheses": {
            "powerlaw": "P(X=x|X>=xmin)=x^-alpha/zeta(alpha,xmin), alpha>1",
            "bounded_powerlaw": "P(X=x|xmin<=X<=N) proportional to x^-alpha",
            "exponential": "shifted geometric on X-xmin",
            "lognormal": "rounded continuous lognormal conditioned on X>=xmin",
            "bootstrap": "semiparametric body resampling plus fitted power-law tail; xmin reselected",
            "robustness": "per-seed fits and within-run quartile drift; pooled-event tests are diagnostic",
        },
        "series_count": len(series),
        "new_event_count": len(events),
        "new_run_count": len(runs),
        "artifacts": [
            str(output_dir / name)
            for name in [
                "existing_result_audit.csv",
                "strict_tail_fits.csv",
                "per_seed_tail_fits.csv",
                "seed_robustness_summary.csv",
                "finite_size_summary.csv",
                "finite_size_scaling_slopes.csv",
                "event_trigger_decomposition.csv",
                "finite_size_initial_vs_propagated.csv",
                "temporal_separation_summary.csv",
                "time_window_summary.csv",
                "transition_fine_scan.png",
                "strict_fit_comparison.png",
                "strict_powerlaw_gof.png",
                "finite_size_scaling.png",
                "initial_vs_propagated_decomposition.png",
                "temporal_separation.png",
                "time_window_drift.png",
                "analysis_note.md",
            ]
        ],
    }
    (output_dir / "analysis_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
