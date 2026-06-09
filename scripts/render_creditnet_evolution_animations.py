#!/usr/bin/env python3
"""Render short credit-network evolution animations.

The script intentionally keeps tracing local to this visualization branch. It
replays small representative runs with the same accounting, settlement, and
cascade rules used by the project simulators, then renders GIFs plus metadata.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.animation as animation
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from creditnet.simulation import (  # noqa: E402
    CreditNetworkParams,
    choose_borrower,
    choose_lender,
    compute_period_length,
    net_worth,
    sample_initial_money,
    spend_and_distribute_income,
    validate_state,
)
from creditnet.timestep import spend_and_distribute_income_scaled  # noqa: E402


CST = timezone(timedelta(hours=8))
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "credit_soc_visual_evolution_20260609_v1"
DEFAULT_SAME_PARAMS_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "credit_soc_visual_evolution_same_params_20260609_v1"
)
DEFAULT_SAME_PARAMS_V3_OUTPUT_DIR = (
    PROJECT_ROOT / "results" / "credit_soc_visual_evolution_same_params_20260609_v3"
)
DEFAULT_FPS = 6


@dataclass(frozen=True)
class SceneSpec:
    scene_id: str
    protocol: str
    description: str
    seed: int
    params: dict[str, Any]
    max_period_length_steps_cap: int = 0
    sample_every_steps: int = 8
    max_event_frame_events: int = 40
    event_frame_stride_after_limit: int = 10
    max_edges_drawn: int = 420
    max_render_frames: int = 120


@dataclass
class TraceFrame:
    scene_id: str
    protocol: str
    stage: str
    period: int
    period_length_steps: int
    micro_step_in_period: int
    time_steps_completed: int
    settlements_completed: int
    checks_completed: int
    total_credit_issued: int
    failed_credit_events: int
    avalanche_count_so_far: int
    event_index: int
    active_credit: int
    active_directed_pairs: int
    cash: np.ndarray
    exposure: np.ndarray
    loan_assets: np.ndarray
    debt_liabilities: np.ndarray
    highlight_nodes: tuple[int, ...] = ()
    new_default_nodes: tuple[int, ...] = ()
    ever_defaulted_nodes: tuple[int, ...] = ()
    impacted_edges: tuple[tuple[int, int], ...] = ()
    note: str = ""

    @property
    def worth(self) -> np.ndarray:
        return net_worth(self.cash, self.loan_assets, self.debt_liabilities)


@dataclass
class TraceResult:
    spec: SceneSpec
    frames: list[TraceFrame]
    event_history: list[dict[str, Any]]
    period_history: list[dict[str, Any]]
    summary: dict[str, Any]


SCENES = [
    SceneSpec(
        scene_id="period_end_overload",
        protocol="period_end",
        description=(
            "High-c biased/preferential-debt period_end replay; one full macro "
            "period accumulates credit before a batch settlement/check."
        ),
        seed=1000,
        params={
            "n_nodes": 40,
            "mean_initial_money": 10.0,
            "money_distribution": "lognormal",
            "income_distribution_rule": "biased",
            "growth_rule": "preferential_debt",
            "consumption_wealth_propensity": 0.10,
            "consumption_income_propensity": 0.70,
            "investment_income_propensity": 0.90,
            "initial_income_per_capita": 6.0,
            "collapse_threshold_fraction": 0.10,
            "max_periods": 8,
            "max_time_steps": 0,
            "default_threshold": 0.0,
            "wipe_defaulted_assets": True,
            "validate_accounting": True,
            "period_length_rule": "income",
            "fixed_period_length_steps": 100,
            "avalanche_protocol": "stop_on_first_default",
            "default_check_mode": "period_end",
        },
        sample_every_steps=4,
        max_edges_drawn=380,
    ),
    SceneSpec(
        scene_id="timestep_micro_tail",
        protocol="timestep_settle_check",
        description=(
            "High-c preferential-debt timestep replay; every credit micro-step "
            "settles and checks before the next credit attempt."
        ),
        seed=2018,
        params={
            "n_nodes": 60,
            "mean_initial_money": 12.0,
            "money_distribution": "lognormal",
            "income_distribution_rule": "biased",
            "growth_rule": "preferential_debt",
            "consumption_wealth_propensity": 0.04,
            "consumption_income_propensity": 0.45,
            "investment_income_propensity": 0.80,
            "initial_income_per_capita": 5.0,
            "collapse_threshold_fraction": 0.10,
            "max_periods": 12,
            "max_time_steps": 0,
            "default_threshold": 0.0,
            "wipe_defaulted_assets": True,
            "validate_accounting": True,
            "period_length_rule": "income",
            "fixed_period_length_steps": 100,
            "avalanche_protocol": "continue_after_avalanche",
            "default_check_mode": "timestep_settle_check",
        },
        max_period_length_steps_cap=120,
        sample_every_steps=30,
        max_event_frame_events=36,
        event_frame_stride_after_limit=12,
        max_edges_drawn=460,
    ),
    SceneSpec(
        scene_id="quiet_low_drive",
        protocol="period_end",
        description=(
            "Low-c uniform/random control; credit accumulates slowly and no "
            "avalanche is expected in the short visualization window."
        ),
        seed=2022,
        params={
            "n_nodes": 40,
            "mean_initial_money": 20.0,
            "money_distribution": "equal",
            "income_distribution_rule": "uniform",
            "growth_rule": "random",
            "consumption_wealth_propensity": 0.01,
            "consumption_income_propensity": 0.10,
            "investment_income_propensity": 0.10,
            "initial_income_per_capita": 4.0,
            "collapse_threshold_fraction": 0.10,
            "max_periods": 20,
            "max_time_steps": 0,
            "default_threshold": 0.0,
            "wipe_defaulted_assets": True,
            "validate_accounting": True,
            "period_length_rule": "income",
            "fixed_period_length_steps": 100,
            "avalanche_protocol": "continue_after_avalanche",
            "default_check_mode": "period_end",
        },
        sample_every_steps=1,
        max_edges_drawn=260,
    ),
]


SAME_PARAMS_BASE_PARAMS = {
    "n_nodes": 60,
    "mean_initial_money": 20.0,
    "money_distribution": "lognormal",
    "income_distribution_rule": "biased",
    "growth_rule": "preferential_debt",
    "consumption_wealth_propensity": 0.04,
    "consumption_income_propensity": 0.40,
    "investment_income_propensity": 0.80,
    "initial_income_per_capita": 5.0,
    "collapse_threshold_fraction": 0.10,
    "max_periods": 8,
    "max_time_steps": 0,
    "default_threshold": 0.0,
    "wipe_defaulted_assets": True,
    "validate_accounting": True,
    "period_length_rule": "income",
    "fixed_period_length_steps": 100,
    "avalanche_protocol": "continue_after_avalanche",
}
SAME_PARAMS_SEED = 2009
SAME_PARAMS_LAYOUT_SEED = SAME_PARAMS_SEED + 17
SAME_PARAMS_SEED_SELECTION = {
    "candidate_seed_range": "2000..2039",
    "selected_seed": SAME_PARAMS_SEED,
    "criterion": (
        "Choose a visual demonstration seed, within the fixed high-risk "
        "same-parameter scenario, where period_end reaches the 10%N large-event "
        "threshold and timestep_settle_check remains below that threshold. This "
        "is not a global statistical conclusion."
    ),
    "selected_seed_probe": {
        "period_end": {
            "avalanche_count": 8,
            "max_collapse_size": 49,
            "max_collapse_fraction": 49 / 60,
            "time_steps_completed": 4883,
        },
        "timestep_settle_check": {
            "avalanche_count": 343,
            "max_collapse_size": 3,
            "max_collapse_fraction": 3 / 60,
            "time_steps_completed": 5972,
        },
    },
}


SAME_PARAM_SCENES = [
    SceneSpec(
        scene_id="same_params_period_end",
        protocol="period_end",
        description=(
            "Same-parameter comparison branch: high-risk lognormal/biased/"
            "preferential_debt/high_both scenario with period_end batch "
            "settlement/checking."
        ),
        seed=SAME_PARAMS_SEED,
        params=SAME_PARAMS_BASE_PARAMS | {"default_check_mode": "period_end"},
        sample_every_steps=120,
        max_event_frame_events=18,
        event_frame_stride_after_limit=12,
        max_edges_drawn=500,
        max_render_frames=120,
    ),
    SceneSpec(
        scene_id="same_params_timestep",
        protocol="timestep_settle_check",
        description=(
            "Same-parameter comparison branch: identical high-risk scenario "
            "with timestep-level micro-settlement/checking after every unit "
            "credit step."
        ),
        seed=SAME_PARAMS_SEED,
        params=SAME_PARAMS_BASE_PARAMS | {"default_check_mode": "timestep_settle_check"},
        max_period_length_steps_cap=0,
        sample_every_steps=180,
        max_event_frame_events=24,
        event_frame_stride_after_limit=18,
        max_edges_drawn=500,
        max_render_frames=120,
    ),
]


def cst_now_iso() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


def params_from_spec(spec: SceneSpec) -> CreditNetworkParams:
    return CreditNetworkParams(**spec.params)


def to_builtin(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): to_builtin(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(item) for item in value]
    return value


def pressure_values(frame: TraceFrame) -> np.ndarray:
    backing = np.maximum(frame.cash + frame.loan_assets, 1)
    return frame.debt_liabilities / backing


def credit_step(
    cash: np.ndarray,
    exposure: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    params: CreditNetworkParams,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int, int, int, int | None, int | None]:
    """Execute exactly one credit attempt using the simulator's choice rules."""

    borrowed = np.zeros(params.n_nodes, dtype=np.int64)
    worth = net_worth(cash, loan_assets, debt_liabilities)
    lender = choose_lender(cash, worth, params, rng)
    if lender is None:
        return borrowed, 0, 1, 1, None, None

    borrower_cum_weights = None
    if params.growth_rule in {"borrower_debt_preferential", "preferential_debt"}:
        borrower_weights = debt_liabilities.astype(float) + params.income_bias_floor
        borrower_cum_weights = np.cumsum(borrower_weights)
    elif params.growth_rule in {"borrower_preferential", "preferential"}:
        borrower_weights = np.maximum(worth, 0).astype(float) + params.income_bias_floor
        borrower_cum_weights = np.cumsum(borrower_weights)

    borrower = choose_borrower(lender, worth, params, rng, borrower_cum_weights)
    if borrower is None:
        return borrowed, 0, 1, 1, lender, None

    cash[lender] -= 1
    cash[borrower] += 1
    exposure[lender, borrower] += 1
    loan_assets[lender] += 1
    debt_liabilities[borrower] += 1
    borrowed[borrower] += 1
    return borrowed, 1, 0, 1, lender, borrower


class TraceBuilder:
    def __init__(self, spec: SceneSpec):
        self.spec = spec
        self.params = params_from_spec(spec)
        self.rng = np.random.default_rng(spec.seed)
        self.cash = sample_initial_money(self.params, self.rng)
        self.initial_money = self.cash.copy()
        self.initial_cash_total = int(self.cash.sum())
        n = self.params.n_nodes
        self.exposure = np.zeros((n, n), dtype=np.int64)
        self.loan_assets = np.zeros(n, dtype=np.int64)
        self.debt_liabilities = np.zeros(n, dtype=np.int64)
        self.last_income = np.full(
            n,
            int(round(self.params.initial_income_per_capita)),
            dtype=np.int64,
        )
        self.last_total_income = int(self.last_income.sum())
        self.frames: list[TraceFrame] = []
        self.event_history: list[dict[str, Any]] = []
        self.period_history: list[dict[str, Any]] = []
        self.ever_defaulted = np.zeros(n, dtype=bool)
        self.total_credit_issued = 0
        self.time_steps_completed = 0
        self.settlements_completed = 0
        self.checks_completed = 0
        self.failed_credit_events = 0
        self.max_collapse_size = 0
        self.total_collapse_size = 0
        self.ended_by_default = False
        self.first_cascade_period = 0
        self.first_cascade_time_steps = 0
        self.credit_scale_before_cascade = 0

    def capture(
        self,
        stage: str,
        period: int,
        period_length_steps: int,
        micro_step_in_period: int = 0,
        event_index: int = 0,
        highlight_nodes: Iterable[int] = (),
        new_default_nodes: Iterable[int] = (),
        impacted_edges: Iterable[tuple[int, int]] = (),
        note: str = "",
    ) -> None:
        self.frames.append(
            TraceFrame(
                scene_id=self.spec.scene_id,
                protocol=self.spec.protocol,
                stage=stage,
                period=int(period),
                period_length_steps=int(period_length_steps),
                micro_step_in_period=int(micro_step_in_period),
                time_steps_completed=int(self.time_steps_completed),
                settlements_completed=int(self.settlements_completed),
                checks_completed=int(self.checks_completed),
                total_credit_issued=int(self.total_credit_issued),
                failed_credit_events=int(self.failed_credit_events),
                avalanche_count_so_far=len(self.event_history),
                event_index=int(event_index),
                active_credit=int(self.exposure.sum()),
                active_directed_pairs=int(np.count_nonzero(self.exposure)),
                cash=self.cash.copy(),
                exposure=self.exposure.copy(),
                loan_assets=self.loan_assets.copy(),
                debt_liabilities=self.debt_liabilities.copy(),
                highlight_nodes=tuple(int(node) for node in highlight_nodes),
                new_default_nodes=tuple(int(node) for node in new_default_nodes),
                ever_defaulted_nodes=tuple(map(int, np.flatnonzero(self.ever_defaulted))),
                impacted_edges=tuple((int(i), int(j)) for i, j in impacted_edges),
                note=note,
            )
        )

    def should_render_event(self, event_index: int) -> bool:
        if event_index <= self.spec.max_event_frame_events:
            return True
        stride = max(int(self.spec.event_frame_stride_after_limit), 1)
        return event_index % stride == 0

    def resolve_cascade_with_trace(
        self,
        initial_defaults: np.ndarray,
        period: int,
        period_length_steps: int,
        micro_step_in_period: int,
        check_kind: str,
    ) -> dict[str, Any]:
        event_index = len(self.event_history) + 1
        render_event = self.should_render_event(event_index)
        initial_defaults = np.asarray(initial_defaults, dtype=np.int64)
        pre_cascade_credit = int(self.exposure.sum())
        pre_directed_pairs = int(np.count_nonzero(self.exposure))

        if render_event:
            self.capture(
                "initial_defaults",
                period,
                period_length_steps,
                micro_step_in_period,
                event_index=event_index,
                highlight_nodes=initial_defaults,
                note=f"{check_kind}: initial defaults={initial_defaults.size}",
            )

        defaulted = np.zeros(self.params.n_nodes, dtype=bool)
        queued = np.zeros(self.params.n_nodes, dtype=bool)
        queue = [int(node) for node in initial_defaults]
        queued[initial_defaults] = True
        waves: list[dict[str, Any]] = []

        while queue:
            node = queue.pop(0)
            if defaulted[node]:
                continue

            incoming = self.exposure[:, node].copy()
            impacted_creditors = np.flatnonzero(incoming > 0)
            impacted_edges = [(int(i), int(node)) for i in impacted_creditors]
            if render_event:
                self.capture(
                    "cascade_wave_start",
                    period,
                    period_length_steps,
                    micro_step_in_period,
                    event_index=event_index,
                    highlight_nodes=[node],
                    impacted_edges=impacted_edges,
                    note=f"clearing node {node}",
                )

            defaulted[node] = True
            self.loan_assets -= incoming
            self.debt_liabilities[node] -= int(incoming.sum())
            self.exposure[:, node] = 0

            wiped_outgoing_total = 0
            if self.params.wipe_defaulted_assets:
                outgoing = self.exposure[node, :].copy()
                wiped_outgoing_total = int(outgoing.sum())
                self.debt_liabilities -= outgoing
                self.loan_assets[node] -= wiped_outgoing_total
                self.exposure[node, :] = 0

            worth = net_worth(self.cash, self.loan_assets, self.debt_liabilities)
            raw_new_defaults = np.flatnonzero(
                (worth < self.params.default_threshold) & (~defaulted) & (~queued)
            )
            for new_node in raw_new_defaults:
                queued[int(new_node)] = True
                queue.append(int(new_node))

            waves.append(
                {
                    "wave_index": len(waves) + 1,
                    "cleared_node": int(node),
                    "incoming_loss": int(incoming.sum()),
                    "impacted_creditor_count": int(impacted_creditors.size),
                    "wiped_outgoing_credit": wiped_outgoing_total,
                    "new_default_nodes": [int(item) for item in raw_new_defaults],
                    "active_credit_after_wave": int(self.exposure.sum()),
                    "min_net_worth_after_wave": float(worth.min()) if worth.size else 0.0,
                }
            )

            if render_event:
                self.capture(
                    "cascade_wave_done",
                    period,
                    period_length_steps,
                    micro_step_in_period,
                    event_index=event_index,
                    highlight_nodes=[node],
                    new_default_nodes=raw_new_defaults,
                    impacted_edges=impacted_edges,
                    note=f"new defaults={raw_new_defaults.size}",
                )

        if self.params.validate_accounting:
            validate_state(
                self.cash,
                self.exposure,
                self.loan_assets,
                self.debt_liabilities,
                self.initial_cash_total,
            )

        self.ever_defaulted |= defaulted
        collapse_size = int(defaulted.sum())
        collapse_fraction = collapse_size / self.params.n_nodes if self.params.n_nodes else 0.0
        propagated = max(collapse_size - int(initial_defaults.size), 0)
        self.max_collapse_size = max(self.max_collapse_size, collapse_size)
        self.total_collapse_size += collapse_size
        self.ended_by_default = True
        if not self.event_history:
            self.first_cascade_period = int(period)
            self.first_cascade_time_steps = int(self.time_steps_completed)
            self.credit_scale_before_cascade = pre_cascade_credit

        event = {
            "event_index": event_index,
            "protocol": self.spec.protocol,
            "check_kind": check_kind,
            "period": int(period),
            "period_length_steps": int(period_length_steps),
            "micro_step_in_period": int(micro_step_in_period),
            "time_steps_completed": int(self.time_steps_completed),
            "settlements_completed": int(self.settlements_completed),
            "checks_completed": int(self.checks_completed),
            "credit_scale_before_cascade": pre_cascade_credit,
            "directed_pairs_before_cascade": pre_directed_pairs,
            "active_credit_after_cascade": int(self.exposure.sum()),
            "initial_default_count": int(initial_defaults.size),
            "collapse_size": collapse_size,
            "collapse_fraction": float(collapse_fraction),
            "critical_event": bool(
                collapse_fraction >= self.params.collapse_threshold_fraction
            ),
            "propagated_default_count": int(propagated),
            "rendered_in_gif": bool(render_event),
            "waves": waves,
        }
        self.event_history.append(event)

        if render_event:
            self.capture(
                "cascade_event_done",
                period,
                period_length_steps,
                micro_step_in_period,
                event_index=event_index,
                highlight_nodes=np.flatnonzero(defaulted),
                note=f"collapse size={collapse_size}",
            )

        return event

    def run_period_end(self) -> TraceResult:
        self.capture("initial_state", 0, 0, note="initial balances")

        for period in range(1, self.params.max_periods + 1):
            period_length_steps = compute_period_length(self.last_total_income, self.params)
            borrowed_this_period = np.zeros(self.params.n_nodes, dtype=np.int64)
            period_issued = 0
            period_failed = 0
            period_attempted = 0
            self.capture("period_start", period, period_length_steps)

            for micro_step in range(1, max(period_length_steps, 0) + 1):
                borrowed, issued, failed, attempted, lender, borrower = credit_step(
                    self.cash,
                    self.exposure,
                    self.loan_assets,
                    self.debt_liabilities,
                    self.params,
                    self.rng,
                )
                borrowed_this_period += borrowed
                self.total_credit_issued += issued
                self.time_steps_completed += attempted
                self.failed_credit_events += failed
                period_issued += issued
                period_failed += failed
                period_attempted += attempted
                if (
                    micro_step == 1
                    or micro_step == period_length_steps
                    or micro_step % max(self.spec.sample_every_steps, 1) == 0
                ):
                    note = (
                        f"credit {lender}->{borrower}"
                        if lender is not None and borrower is not None
                        else "failed credit attempt"
                    )
                    self.capture(
                        "credit_growth",
                        period,
                        period_length_steps,
                        micro_step,
                        note=note,
                    )
                if lender is None:
                    break

            (
                self.last_income,
                total_income,
                investment_spend,
                consumption_spend,
            ) = spend_and_distribute_income(
                self.cash,
                self.loan_assets,
                self.debt_liabilities,
                self.last_income,
                borrowed_this_period,
                self.params,
                self.rng,
            )
            self.last_total_income = int(total_income)
            self.settlements_completed += 1
            self.checks_completed += 1

            if self.params.validate_accounting:
                validate_state(
                    self.cash,
                    self.exposure,
                    self.loan_assets,
                    self.debt_liabilities,
                    self.initial_cash_total,
                )

            worth = net_worth(self.cash, self.loan_assets, self.debt_liabilities)
            initial_defaults = np.flatnonzero(worth < self.params.default_threshold)
            self.capture(
                "period_end_settlement",
                period,
                period_length_steps,
                period_length_steps,
                highlight_nodes=initial_defaults,
                note=(
                    f"investment={investment_spend}, consumption={consumption_spend}, "
                    f"initial defaults={initial_defaults.size}"
                ),
            )

            events_before = len(self.event_history)
            if initial_defaults.size > 0:
                self.resolve_cascade_with_trace(
                    initial_defaults,
                    period,
                    period_length_steps,
                    period_length_steps,
                    check_kind="period_end",
                )

            self.period_history.append(
                {
                    "period": period,
                    "period_length_steps": int(period_length_steps),
                    "time_steps_completed": int(self.time_steps_completed),
                    "issued_credit": int(period_issued),
                    "failed_credit_events": int(period_failed),
                    "attempted": int(period_attempted),
                    "active_credit": int(self.exposure.sum()),
                    "active_directed_pairs": int(np.count_nonzero(self.exposure)),
                    "investment_spending": int(investment_spend),
                    "consumption_spending": int(consumption_spend),
                    "total_income": int(total_income),
                    "avalanche_count": len(self.event_history) - events_before,
                    "min_net_worth": float(worth.min()) if worth.size else 0.0,
                    "negative_net_worth_nodes": int(initial_defaults.size),
                }
            )

            if (
                self.params.avalanche_protocol == "stop_on_first_default"
                and self.event_history
            ):
                break
            if (
                self.params.max_time_steps > 0
                and self.time_steps_completed >= self.params.max_time_steps
            ):
                break

        return self.result()

    def run_timestep(self) -> TraceResult:
        self.capture("initial_state", 0, 0, note="initial balances")

        for period in range(1, self.params.max_periods + 1):
            uncapped_steps = compute_period_length(self.last_total_income, self.params)
            period_length_steps = int(uncapped_steps)
            if self.spec.max_period_length_steps_cap > 0:
                period_length_steps = min(
                    period_length_steps,
                    int(self.spec.max_period_length_steps_cap),
                )
            steps_this_period = max(period_length_steps, 0)
            macro_reference_income = self.last_income.copy()
            macro_new_income = np.zeros(self.params.n_nodes, dtype=np.int64)
            macro_issued = 0
            macro_failed = 0
            macro_attempted = 0
            macro_investment_spending = 0
            macro_consumption_spending = 0
            events_before = len(self.event_history)

            self.capture("period_start", period, period_length_steps)
            if steps_this_period == 0:
                self.last_income = macro_new_income
                self.last_total_income = 0

            for micro_step in range(1, steps_this_period + 1):
                borrowed, issued, failed, attempted, lender, borrower = credit_step(
                    self.cash,
                    self.exposure,
                    self.loan_assets,
                    self.debt_liabilities,
                    self.params,
                    self.rng,
                )
                self.total_credit_issued += issued
                self.time_steps_completed += attempted
                self.failed_credit_events += failed
                macro_issued += issued
                macro_failed += failed
                macro_attempted += attempted

                income, _, investment_spend, consumption_spend = (
                    spend_and_distribute_income_scaled(
                        self.cash,
                        self.loan_assets,
                        self.debt_liabilities,
                        macro_reference_income,
                        borrowed,
                        1.0 / max(steps_this_period, 1),
                        self.params,
                        self.rng,
                    )
                )
                macro_new_income += income
                macro_investment_spending += investment_spend
                macro_consumption_spending += consumption_spend
                self.settlements_completed += 1

                if self.params.validate_accounting:
                    validate_state(
                        self.cash,
                        self.exposure,
                        self.loan_assets,
                        self.debt_liabilities,
                        self.initial_cash_total,
                    )

                self.checks_completed += 1
                worth = net_worth(self.cash, self.loan_assets, self.debt_liabilities)
                initial_defaults = np.flatnonzero(worth < self.params.default_threshold)

                if (
                    micro_step == 1
                    or micro_step == steps_this_period
                    or self.time_steps_completed % max(self.spec.sample_every_steps, 1) == 0
                    or initial_defaults.size > 0
                ):
                    note = (
                        f"credit {lender}->{borrower}; micro settlement"
                        if lender is not None and borrower is not None
                        else "failed credit attempt; micro settlement"
                    )
                    self.capture(
                        "timestep_settlement_check",
                        period,
                        period_length_steps,
                        micro_step,
                        highlight_nodes=initial_defaults,
                        note=note,
                    )

                if initial_defaults.size > 0:
                    self.resolve_cascade_with_trace(
                        initial_defaults,
                        period,
                        period_length_steps,
                        micro_step,
                        check_kind="timestep_settle_check",
                    )

                if (
                    self.params.avalanche_protocol == "stop_on_first_default"
                    and self.event_history
                ):
                    break
                if (
                    self.params.max_time_steps > 0
                    and self.time_steps_completed >= self.params.max_time_steps
                ):
                    break

            self.last_income = macro_new_income
            self.last_total_income = int(macro_new_income.sum())
            self.period_history.append(
                {
                    "period": period,
                    "uncapped_period_length_steps": int(uncapped_steps),
                    "period_length_steps": int(period_length_steps),
                    "time_steps_completed": int(self.time_steps_completed),
                    "settlements_completed": int(self.settlements_completed),
                    "checks_completed": int(self.checks_completed),
                    "issued_credit": int(macro_issued),
                    "failed_credit_events": int(macro_failed),
                    "attempted": int(macro_attempted),
                    "active_credit": int(self.exposure.sum()),
                    "active_directed_pairs": int(np.count_nonzero(self.exposure)),
                    "investment_spending": int(macro_investment_spending),
                    "consumption_spending": int(macro_consumption_spending),
                    "total_income": int(self.last_total_income),
                    "avalanche_count": len(self.event_history) - events_before,
                }
            )

            if (
                self.params.avalanche_protocol == "stop_on_first_default"
                and self.event_history
            ):
                break
            if (
                self.params.max_time_steps > 0
                and self.time_steps_completed >= self.params.max_time_steps
            ):
                break

        return self.result()

    def result(self) -> TraceResult:
        if not self.event_history:
            self.credit_scale_before_cascade = int(self.exposure.sum())
        final_worth = net_worth(self.cash, self.loan_assets, self.debt_liabilities)
        periods_completed = (
            max((item["period"] for item in self.period_history), default=0)
            if self.period_history
            else 0
        )
        large_threshold_nodes = int(
            math.ceil(self.params.collapse_threshold_fraction * self.params.n_nodes)
        )
        summary = {
            "scene_id": self.spec.scene_id,
            "protocol": self.spec.protocol,
            "seed": int(self.spec.seed),
            "n_nodes": int(self.params.n_nodes),
            "periods_completed": int(periods_completed),
            "time_steps_completed": int(self.time_steps_completed),
            "settlements_completed": int(self.settlements_completed),
            "checks_completed": int(self.checks_completed),
            "total_credit_issued": int(self.total_credit_issued),
            "failed_credit_events": int(self.failed_credit_events),
            "initial_total_money": int(self.initial_money.sum()),
            "final_cash_total": int(self.cash.sum()),
            "final_active_credit": int(self.exposure.sum()),
            "final_active_directed_pairs": int(np.count_nonzero(self.exposure)),
            "initial_money_gini": float(gini(self.initial_money)),
            "final_net_worth_gini": float(gini(final_worth)),
            "avalanche_count": int(len(self.event_history)),
            "max_collapse_size": int(self.max_collapse_size),
            "total_collapse_size": int(self.total_collapse_size),
            "max_collapse_fraction": (
                float(self.max_collapse_size / self.params.n_nodes)
                if self.params.n_nodes
                else 0.0
            ),
            "large_cascade_threshold_nodes": large_threshold_nodes,
            "large_cascade_event_count": int(
                sum(event["collapse_size"] >= large_threshold_nodes for event in self.event_history)
            ),
            "first_cascade_period": int(self.first_cascade_period),
            "first_cascade_time_steps": int(self.first_cascade_time_steps),
            "credit_scale_before_cascade": int(self.credit_scale_before_cascade),
            "critical_event": bool(
                any(event["critical_event"] for event in self.event_history)
            ),
            "ended_by_default": bool(self.ended_by_default),
            "frame_count_before_padding": int(len(self.frames)),
        }
        summary["frame_count_raw"] = int(len(self.frames))
        thin_frames(self.frames, max_frames=int(self.spec.max_render_frames))
        summary["frame_count_after_thinning"] = int(len(self.frames))
        pad_frames(self.frames, min_frames=48)
        summary["frame_count"] = int(len(self.frames))
        return TraceResult(
            spec=self.spec,
            frames=self.frames,
            event_history=self.event_history,
            period_history=self.period_history,
            summary=summary,
        )


def gini(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return 0.0
    min_x = float(np.min(x))
    if min_x < 0:
        x = x - min_x
    total = float(np.sum(x))
    if total <= 0:
        return 0.0
    x = np.sort(x)
    n = x.size
    index = np.arange(1, n + 1, dtype=float)
    return float((2.0 * np.sum(index * x) / (n * total)) - ((n + 1.0) / n))


def pad_frames(frames: list[TraceFrame], min_frames: int) -> None:
    if not frames:
        return
    while len(frames) < min_frames:
        frames.append(frames[-1])


def thin_frames(frames: list[TraceFrame], max_frames: int) -> None:
    if max_frames <= 0 or len(frames) <= max_frames:
        return

    def sampled_indices(indices: list[int], budget: int) -> set[int]:
        if budget <= 0 or not indices:
            return set()
        if len(indices) <= budget:
            return set(indices)
        positions = np.linspace(0, len(indices) - 1, budget, dtype=int)
        return {indices[int(pos)] for pos in positions}

    selected: set[int] = {0, len(frames) - 1}
    growth_stages = {
        "period_start",
        "credit_growth",
        "period_end_settlement",
        "timestep_settlement_check",
    }
    growth_indices = [
        index for index, frame in enumerate(frames) if frame.stage in growth_stages
    ]
    event_indices = [
        index
        for index, frame in enumerate(frames)
        if frame.stage in {"initial_defaults", "cascade_wave_start", "cascade_wave_done", "cascade_event_done"}
    ]

    growth_budget = min(max_frames // 2, 58)
    selected |= sampled_indices(growth_indices, growth_budget)

    remaining = max_frames - len(selected)
    event_budget = max(0, remaining - max(8, max_frames // 10))
    selected |= sampled_indices(event_indices, event_budget)

    remaining = max_frames - len(selected)
    if remaining > 0:
        selected |= sampled_indices(list(range(len(frames))), remaining)

    if len(selected) > max_frames:
        priority = {
            "initial_state": 0,
            "credit_growth": 1,
            "timestep_settlement_check": 1,
            "period_start": 1,
            "period_end_settlement": 2,
            "initial_defaults": 3,
            "cascade_wave_start": 4,
            "cascade_wave_done": 4,
            "cascade_event_done": 4,
        }
        removable = sorted(
            (idx for idx in selected if idx not in {0, len(frames) - 1}),
            key=lambda idx: (priority.get(frames[idx].stage, 9), idx),
            reverse=True,
        )
        for idx in removable:
            if len(selected) <= max_frames:
                break
            selected.remove(idx)

    thinned = [frames[idx] for idx in sorted(selected)]
    frames[:] = thinned


def run_trace(spec: SceneSpec) -> TraceResult:
    builder = TraceBuilder(spec)
    if spec.protocol == "period_end":
        return builder.run_period_end()
    if spec.protocol == "timestep_settle_check":
        return builder.run_timestep()
    raise ValueError(f"unknown protocol: {spec.protocol}")


def frame_csv_row(index: int, frame: TraceFrame) -> dict[str, Any]:
    worth = frame.worth
    return {
        "frame_index": index,
        "scene_id": frame.scene_id,
        "protocol": frame.protocol,
        "stage": frame.stage,
        "period": frame.period,
        "period_length_steps": frame.period_length_steps,
        "micro_step_in_period": frame.micro_step_in_period,
        "time_steps_completed": frame.time_steps_completed,
        "settlements_completed": frame.settlements_completed,
        "checks_completed": frame.checks_completed,
        "total_credit_issued": frame.total_credit_issued,
        "failed_credit_events": frame.failed_credit_events,
        "avalanche_count_so_far": frame.avalanche_count_so_far,
        "event_index": frame.event_index,
        "active_credit": frame.active_credit,
        "active_directed_pairs": frame.active_directed_pairs,
        "min_net_worth": float(worth.min()) if worth.size else 0.0,
        "median_net_worth": float(np.median(worth)) if worth.size else 0.0,
        "max_debt_pressure": float(pressure_values(frame).max()) if worth.size else 0.0,
        "highlight_nodes": " ".join(map(str, frame.highlight_nodes)),
        "new_default_nodes": " ".join(map(str, frame.new_default_nodes)),
        "note": frame.note,
    }


def write_trace_summary(trace: TraceResult, output_dir: Path) -> Path:
    path = output_dir / f"{trace.spec.scene_id}_trace_summary.csv"
    rows = [frame_csv_row(index, frame) for index, frame in enumerate(trace.frames)]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_metadata(
    trace: TraceResult,
    output_dir: Path,
    fps: int,
    gif_path: Path,
    keyframes_path: Path,
    trace_csv_path: Path,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    metadata_path = output_dir / f"{trace.spec.scene_id}_metadata.json"
    metadata = {
        "generated_at_cst": cst_now_iso(),
        "script": str(Path(__file__).relative_to(PROJECT_ROOT)),
        "scene": asdict(trace.spec),
        "params": trace.spec.params,
        "summary": trace.summary,
        "outputs": {
            "gif": str(gif_path.relative_to(PROJECT_ROOT)),
            "keyframes_png": str(keyframes_path.relative_to(PROJECT_ROOT)),
            "trace_summary_csv": str(trace_csv_path.relative_to(PROJECT_ROOT)),
            "metadata_json": str(metadata_path.relative_to(PROJECT_ROOT)),
        },
        "rendering": {
            "fps": int(fps),
            "duration_seconds": round(len(trace.frames) / fps, 3),
            "max_edges_drawn": int(trace.spec.max_edges_drawn),
            "layout_seed": int(trace.spec.seed + 17),
            "node_color": "net worth color scale; current/default nodes override to red/orange",
            "node_size": "debt pressure relative to cash plus loan assets",
            "edge_width": "sqrt(active directed exposure weight)",
            "cascade_highlight": "incoming exposures to the node being cleared are red",
            "legend": "drawn in the lower-right corner of each frame and keyframe panel",
        },
        "period_history": trace.period_history,
        "event_history": trace.event_history,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(to_builtin(metadata), handle, ensure_ascii=False, indent=2)
    return metadata_path


def build_layout(frames: list[TraceFrame], seed: int) -> dict[int, np.ndarray]:
    n = frames[0].cash.size
    aggregate = np.zeros((n, n), dtype=float)
    for frame in frames:
        aggregate = np.maximum(aggregate, frame.exposure)

    graph = nx.Graph()
    graph.add_nodes_from(range(n))
    rows, cols = np.nonzero(aggregate)
    for i, j in zip(rows, cols):
        if i == j:
            continue
        weight = float(aggregate[i, j] + aggregate[j, i])
        graph.add_edge(int(i), int(j), weight=max(weight, 1.0))

    if graph.number_of_edges() == 0 and n > 1:
        graph.add_edges_from((i, (i + 1) % n) for i in range(n))

    return nx.spring_layout(graph, seed=seed, weight="weight", iterations=150)


def compute_render_scale(frames: list[TraceFrame]) -> dict[str, float]:
    worth_values = np.concatenate([frame.worth for frame in frames])
    pressure = np.concatenate([pressure_values(frame) for frame in frames])
    positive_pressure = pressure[pressure > 0]
    worth_low = float(np.percentile(worth_values, 5)) if worth_values.size else -1.0
    worth_high = float(np.percentile(worth_values, 95)) if worth_values.size else 1.0
    if worth_high <= worth_low:
        worth_low -= 1.0
        worth_high += 1.0
    pressure_high = (
        float(np.percentile(positive_pressure, 95)) if positive_pressure.size else 1.0
    )
    return {
        "worth_low": worth_low,
        "worth_high": worth_high,
        "pressure_high": max(pressure_high, 0.25),
        "max_edge_weight": max(int(frame.exposure.max()) for frame in frames) or 1,
    }


def active_edges_for_frame(
    frame: TraceFrame,
    max_edges: int,
) -> list[tuple[int, int, int]]:
    rows, cols = np.nonzero(frame.exposure)
    edges = [
        (int(i), int(j), int(frame.exposure[i, j]))
        for i, j in zip(rows, cols)
        if frame.exposure[i, j] > 0
    ]
    edges.sort(key=lambda item: item[2], reverse=True)
    return edges[:max_edges]


def fmt_legend_value(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def draw_visual_legend(
    ax: plt.Axes,
    cmap: mcolors.Colormap,
    scale: dict[str, float],
) -> None:
    x0, y0, width, height = 0.765, 0.055, 0.220, 0.340
    panel = mpatches.Rectangle(
        (x0, y0),
        width,
        height,
        transform=ax.transAxes,
        facecolor="#fffffff0",
        edgecolor="#c7c7bd",
        linewidth=0.9,
        zorder=6,
    )
    ax.add_patch(panel)

    ax.text(
        x0 + 0.018,
        y0 + height - 0.024,
        "Legend",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=7.1,
        fontweight="bold",
        color="#1f2528",
        zorder=7,
    )

    ax.text(
        x0 + 0.018,
        y0 + height - 0.052,
        "Fill: net worth W",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=5.8,
        color="#1f2528",
        zorder=7,
    )
    grad_x = x0 + 0.014
    grad_y = y0 + height - 0.087
    grad_w = width - 0.028
    grad_h = 0.020
    for idx in range(8):
        seg_x = grad_x + grad_w * idx / 8.0
        seg_w = grad_w / 8.0 + 0.001
        rect = mpatches.Rectangle(
            (seg_x, grad_y),
            seg_w,
            grad_h,
            transform=ax.transAxes,
            facecolor=cmap(idx / 7.0),
            edgecolor="none",
            zorder=7,
        )
        ax.add_patch(rect)
    ax.add_patch(
        mpatches.Rectangle(
            (grad_x, grad_y),
            grad_w,
            grad_h,
            transform=ax.transAxes,
            facecolor="none",
            edgecolor="#6f746e",
            linewidth=0.5,
            zorder=8,
        )
    )
    low = fmt_legend_value(float(scale["worth_low"]))
    high = fmt_legend_value(float(scale["worth_high"]))
    ax.text(
        grad_x,
        grad_y - 0.008,
        f"low {low}",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=5.3,
        color="#1f2528",
        zorder=7,
    )
    ax.text(
        grad_x + grad_w,
        grad_y - 0.008,
        f"high {high}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=5.3,
        color="#1f2528",
        zorder=7,
    )

    y = y0 + height - 0.135
    rows = [
        ("#e31a1c", "#540000", "current default"),
        ("#ff8c1a", "#7f0000", "new default"),
        ("#f7f7f4", "#8b1e1e", "past outline"),
    ]
    for fill, edge, label in rows:
        ax.scatter(
            [x0 + 0.026],
            [y],
            s=48,
            c=[fill],
            edgecolors=[edge],
            linewidths=1.4,
            transform=ax.transAxes,
            zorder=7,
        )
        ax.text(
            x0 + 0.047,
            y,
            label,
            transform=ax.transAxes,
            ha="left",
            va="center",
            fontsize=5.5,
            color="#1f2528",
            zorder=7,
        )
        y -= 0.031

    y -= 0.004
    ax.plot(
        [x0 + 0.014, x0 + 0.052],
        [y, y],
        transform=ax.transAxes,
        color="#38424a",
        alpha=0.75,
        linewidth=2.4,
        zorder=7,
        solid_capstyle="round",
    )
    ax.text(
        x0 + 0.061,
        y,
        "credit edge",
        transform=ax.transAxes,
        ha="left",
        va="center",
        fontsize=5.5,
        color="#1f2528",
        zorder=7,
    )

    y -= 0.031
    ax.plot(
        [x0 + 0.014, x0 + 0.052],
        [y, y],
        transform=ax.transAxes,
        color="#d84a3a",
        alpha=0.85,
        linewidth=2.4,
        zorder=7,
        solid_capstyle="round",
    )
    ax.text(
        x0 + 0.061,
        y,
        "loss edge",
        transform=ax.transAxes,
        ha="left",
        va="center",
        fontsize=5.5,
        color="#1f2528",
        zorder=7,
    )

    y -= 0.031
    ax.scatter(
        [x0 + 0.022, x0 + 0.044],
        [y, y],
        s=[28, 82],
        c=["#9bd9c2", "#9bd9c2"],
        edgecolors=["#2f3437", "#2f3437"],
        linewidths=0.7,
        transform=ax.transAxes,
        zorder=7,
    )
    ax.text(
        x0 + 0.061,
        y,
        "size = debt pressure",
        transform=ax.transAxes,
        ha="left",
        va="center",
        fontsize=5.5,
        color="#1f2528",
        zorder=7,
    )


def draw_frame(
    ax: plt.Axes,
    frame: TraceFrame,
    pos: dict[int, np.ndarray],
    scale: dict[str, float],
    frame_index: int,
    total_frames: int,
    max_edges_drawn: int,
) -> None:
    ax.clear()
    ax.set_axis_off()
    ax.set_facecolor("#f7f7f4")

    impacted_edges = set(frame.impacted_edges)
    max_edge_weight = max(float(scale["max_edge_weight"]), 1.0)
    for i, j, weight in active_edges_for_frame(frame, max_edges_drawn):
        x0, y0 = pos[i]
        x1, y1 = pos[j]
        color = "#d84a3a" if (i, j) in impacted_edges else "#38424a"
        alpha = 0.22 + 0.58 * min(weight / max_edge_weight, 1.0)
        width = 0.25 + 2.8 * math.sqrt(weight / max_edge_weight)
        ax.plot(
            [x0, x1],
            [y0, y1],
            color=color,
            alpha=alpha,
            linewidth=width,
            zorder=1,
            solid_capstyle="round",
        )

    n = frame.cash.size
    xy = np.array([pos[i] for i in range(n)])
    worth = frame.worth
    norm = mcolors.Normalize(vmin=scale["worth_low"], vmax=scale["worth_high"])
    cmap = plt.get_cmap("YlGnBu")
    colors = [mcolors.to_hex(cmap(norm(float(value)))) for value in worth]
    pressure = pressure_values(frame)
    size_pressure = np.clip(pressure / scale["pressure_high"], 0.0, 1.4)
    sizes = 70.0 + 290.0 * size_pressure
    edgecolors = np.full(n, "#2f3437", dtype=object)
    linewidths = np.full(n, 0.8)

    ever_defaulted = set(frame.ever_defaulted_nodes)
    for node in ever_defaulted:
        if 0 <= node < n:
            edgecolors[node] = "#8b1e1e"
            linewidths[node] = 1.8

    for node in frame.new_default_nodes:
        if 0 <= node < n:
            colors[node] = "#ff8c1a"
            sizes[node] = max(float(sizes[node]), 430.0)
            edgecolors[node] = "#7f0000"
            linewidths[node] = 2.6

    flash_on = frame_index % 2 == 0
    for node in frame.highlight_nodes:
        if 0 <= node < n:
            colors[node] = "#e31a1c" if flash_on else "#ffd166"
            sizes[node] = max(float(sizes[node]), 500.0 if flash_on else 420.0)
            edgecolors[node] = "#540000"
            linewidths[node] = 3.0

    ax.scatter(
        xy[:, 0],
        xy[:, 1],
        s=sizes,
        c=colors,
        edgecolors=edgecolors,
        linewidths=linewidths,
        zorder=3,
    )

    label_nodes = set(frame.highlight_nodes) | set(frame.new_default_nodes)
    for node in label_nodes:
        if 0 <= node < n:
            ax.text(
                xy[node, 0],
                xy[node, 1],
                str(node),
                color="white" if flash_on else "#2a1b00",
                fontsize=7,
                ha="center",
                va="center",
                zorder=4,
                fontweight="bold",
            )

    worth_min = float(worth.min()) if worth.size else 0.0
    worth_med = float(np.median(worth)) if worth.size else 0.0
    event_text = (
        f"events={frame.avalanche_count_so_far}"
        if frame.event_index == 0
        else f"event={frame.event_index} events={frame.avalanche_count_so_far}"
    )
    header = (
        f"{frame.scene_id} | {frame.protocol} | {frame.stage} | "
        f"frame {frame_index + 1}/{total_frames}"
    )
    line2 = (
        f"period={frame.period} step={frame.micro_step_in_period}/"
        f"{frame.period_length_steps}  t={frame.time_steps_completed}  "
        f"credit={frame.active_credit} pairs={frame.active_directed_pairs}  "
        f"{event_text}"
    )
    line3 = (
        f"minW={worth_min:.1f} medianW={worth_med:.1f}  issued="
        f"{frame.total_credit_issued} failed={frame.failed_credit_events}"
    )
    ax.text(
        0.015,
        0.985,
        header,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        fontweight="bold",
        color="#1f2528",
        bbox={"facecolor": "#ffffffd9", "edgecolor": "#d0d0c8", "pad": 3},
        zorder=5,
    )
    ax.text(
        0.015,
        0.925,
        line2 + "\n" + line3,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8,
        color="#1f2528",
        bbox={"facecolor": "#ffffffcc", "edgecolor": "#d0d0c8", "pad": 3},
        zorder=5,
    )
    if frame.note:
        ax.text(
            0.015,
            0.045,
            frame.note[:120],
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=8,
            color="#1f2528",
            bbox={"facecolor": "#ffffffcc", "edgecolor": "#d0d0c8", "pad": 3},
            zorder=5,
        )
    draw_visual_legend(ax, cmap, scale)
    ax.set_aspect("equal")
    ax.margins(0.10)


def render_gif(
    trace: TraceResult,
    output_dir: Path,
    fps: int,
    pos: dict[int, np.ndarray] | None = None,
    scale: dict[str, float] | None = None,
) -> Path:
    gif_path = output_dir / f"{trace.spec.scene_id}.gif"
    pos = build_layout(trace.frames, seed=trace.spec.seed + 17) if pos is None else pos
    scale = compute_render_scale(trace.frames) if scale is None else scale
    fig, ax = plt.subplots(figsize=(9.6, 7.2), dpi=110)

    def update(index: int) -> None:
        draw_frame(
            ax,
            trace.frames[index],
            pos,
            scale,
            index,
            len(trace.frames),
            trace.spec.max_edges_drawn,
        )

    anim = animation.FuncAnimation(
        fig,
        update,
        frames=len(trace.frames),
        interval=1000 / fps,
        repeat=False,
    )
    writer = animation.PillowWriter(fps=fps)
    anim.save(gif_path, writer=writer)
    plt.close(fig)
    return gif_path


def render_keyframes(
    trace: TraceResult,
    output_dir: Path,
    pos: dict[int, np.ndarray] | None = None,
    scale: dict[str, float] | None = None,
) -> Path:
    keyframes_path = output_dir / f"{trace.spec.scene_id}_keyframes.png"
    pos = build_layout(trace.frames, seed=trace.spec.seed + 17) if pos is None else pos
    scale = compute_render_scale(trace.frames) if scale is None else scale
    indices = sorted(
        {
            0,
            len(trace.frames) // 3,
            (2 * len(trace.frames)) // 3,
            len(trace.frames) - 1,
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 10.0), dpi=130)
    for panel, index in zip(axes.ravel(), indices):
        draw_frame(
            panel,
            trace.frames[index],
            pos,
            scale,
            index,
            len(trace.frames),
            trace.spec.max_edges_drawn,
        )
    fig.suptitle(
        f"{trace.spec.scene_id}: selected animation frames",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(keyframes_path)
    plt.close(fig)
    return keyframes_path


def render_scene(
    trace: TraceResult,
    output_dir: Path,
    fps: int,
    pos: dict[int, np.ndarray] | None = None,
    scale: dict[str, float] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Path]:
    gif_path = render_gif(trace, output_dir, fps, pos=pos, scale=scale)
    keyframes_path = render_keyframes(trace, output_dir, pos=pos, scale=scale)
    trace_csv_path = write_trace_summary(trace, output_dir)
    metadata_path = write_metadata(
        trace,
        output_dir,
        fps,
        gif_path,
        keyframes_path,
        trace_csv_path,
        extra_metadata=extra_metadata,
    )
    return {
        "gif": gif_path,
        "keyframes_png": keyframes_path,
        "trace_summary_csv": trace_csv_path,
        "metadata_json": metadata_path,
    }


def cash_vector_hash(cash: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(cash, dtype=np.int64).tobytes()).hexdigest()


def combined_frames(traces: Iterable[TraceResult]) -> list[TraceFrame]:
    frames: list[TraceFrame] = []
    for trace in traces:
        frames.extend(trace.frames)
    return frames


def mapped_frame_index(index: int, source_len: int, target_len: int) -> int:
    if source_len <= 1 or target_len <= 1:
        return 0
    return int(round(index * (source_len - 1) / (target_len - 1)))


def side_by_side_csv_row(
    index: int,
    left_index: int,
    right_index: int,
    left: TraceFrame,
    right: TraceFrame,
) -> dict[str, Any]:
    return {
        "side_by_side_frame_index": index,
        "left_frame_index": left_index,
        "right_frame_index": right_index,
        "left_protocol": left.protocol,
        "right_protocol": right.protocol,
        "left_period": left.period,
        "right_period": right.period,
        "left_micro_step": left.micro_step_in_period,
        "right_micro_step": right.micro_step_in_period,
        "left_time_steps_completed": left.time_steps_completed,
        "right_time_steps_completed": right.time_steps_completed,
        "left_active_credit": left.active_credit,
        "right_active_credit": right.active_credit,
        "left_avalanche_count_so_far": left.avalanche_count_so_far,
        "right_avalanche_count_so_far": right.avalanche_count_so_far,
        "left_event_index": left.event_index,
        "right_event_index": right.event_index,
    }


def write_side_by_side_trace_summary(
    left: TraceResult,
    right: TraceResult,
    output_dir: Path,
    total_frames: int,
) -> Path:
    path = output_dir / "same_params_period_vs_timestep_side_by_side_trace_summary.csv"
    rows = []
    for index in range(total_frames):
        left_index = mapped_frame_index(index, len(left.frames), total_frames)
        right_index = mapped_frame_index(index, len(right.frames), total_frames)
        rows.append(
            side_by_side_csv_row(
                index,
                left_index,
                right_index,
                left.frames[left_index],
                right.frames[right_index],
            )
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def render_side_by_side_gif(
    left: TraceResult,
    right: TraceResult,
    output_dir: Path,
    fps: int,
    pos: dict[int, np.ndarray],
    scale: dict[str, float],
) -> Path:
    gif_path = output_dir / "same_params_period_vs_timestep_side_by_side.gif"
    total_frames = max(len(left.frames), len(right.frames))
    fig, axes = plt.subplots(1, 2, figsize=(17.8, 7.4), dpi=110)
    fig.suptitle(
        "Same parameters, same seed/layout; only settlement/check granularity differs",
        fontsize=12,
        fontweight="bold",
    )

    def update(index: int) -> None:
        left_index = mapped_frame_index(index, len(left.frames), total_frames)
        right_index = mapped_frame_index(index, len(right.frames), total_frames)
        draw_frame(
            axes[0],
            left.frames[left_index],
            pos,
            scale,
            left_index,
            len(left.frames),
            left.spec.max_edges_drawn,
        )
        draw_frame(
            axes[1],
            right.frames[right_index],
            pos,
            scale,
            right_index,
            len(right.frames),
            right.spec.max_edges_drawn,
        )
        axes[0].set_title("period_end: batch settlement/check", fontsize=10)
        axes[1].set_title("timestep_settle_check: micro settlement/check", fontsize=10)

    anim = animation.FuncAnimation(
        fig,
        update,
        frames=total_frames,
        interval=1000 / fps,
        repeat=False,
    )
    writer = animation.PillowWriter(fps=fps)
    anim.save(gif_path, writer=writer)
    plt.close(fig)
    return gif_path


def render_side_by_side_keyframes(
    left: TraceResult,
    right: TraceResult,
    output_dir: Path,
    pos: dict[int, np.ndarray],
    scale: dict[str, float],
) -> Path:
    keyframes_path = output_dir / "same_params_period_vs_timestep_side_by_side_keyframes.png"
    total_frames = max(len(left.frames), len(right.frames))
    indices = sorted({0, total_frames // 3, (2 * total_frames) // 3, total_frames - 1})
    fig, axes = plt.subplots(4, 2, figsize=(15.2, 21.0), dpi=120)
    for row, index in enumerate(indices):
        left_index = mapped_frame_index(index, len(left.frames), total_frames)
        right_index = mapped_frame_index(index, len(right.frames), total_frames)
        draw_frame(
            axes[row, 0],
            left.frames[left_index],
            pos,
            scale,
            left_index,
            len(left.frames),
            left.spec.max_edges_drawn,
        )
        draw_frame(
            axes[row, 1],
            right.frames[right_index],
            pos,
            scale,
            right_index,
            len(right.frames),
            right.spec.max_edges_drawn,
        )
        axes[row, 0].set_title("period_end", fontsize=9)
        axes[row, 1].set_title("timestep_settle_check", fontsize=9)
    fig.suptitle(
        "Same-parameter protocol comparison keyframes",
        fontsize=13,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(keyframes_path)
    plt.close(fig)
    return keyframes_path


def write_side_by_side_metadata(
    left: TraceResult,
    right: TraceResult,
    output_dir: Path,
    fps: int,
    gif_path: Path,
    keyframes_path: Path,
    trace_csv_path: Path,
) -> Path:
    metadata_path = output_dir / "same_params_period_vs_timestep_side_by_side_metadata.json"
    payload = {
        "generated_at_cst": cst_now_iso(),
        "script": str(Path(__file__).relative_to(PROJECT_ROOT)),
        "description": "Side-by-side same-parameter protocol comparison.",
        "left_scene_id": left.spec.scene_id,
        "right_scene_id": right.spec.scene_id,
        "same_params_base": SAME_PARAMS_BASE_PARAMS,
        "seed_selection": SAME_PARAMS_SEED_SELECTION,
        "shared_seed": SAME_PARAMS_SEED,
        "shared_layout_seed": SAME_PARAMS_LAYOUT_SEED,
        "initial_cash_vectors_identical": bool(
            np.array_equal(left.frames[0].cash, right.frames[0].cash)
        ),
        "initial_cash_sha256": cash_vector_hash(left.frames[0].cash),
        "outputs": {
            "gif": str(gif_path.relative_to(PROJECT_ROOT)),
            "keyframes_png": str(keyframes_path.relative_to(PROJECT_ROOT)),
            "trace_summary_csv": str(trace_csv_path.relative_to(PROJECT_ROOT)),
            "metadata_json": str(metadata_path.relative_to(PROJECT_ROOT)),
        },
        "rendering": {
            "fps": int(fps),
            "duration_seconds": round(max(len(left.frames), len(right.frames)) / fps, 3),
            "layout": "shared spring layout built from both protocol traces",
            "color_scale": "shared net-worth/debt-pressure scale built from both protocol traces",
            "legend": "drawn in each panel",
        },
        "left_summary": left.summary,
        "right_summary": right.summary,
    }
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(to_builtin(payload), handle, ensure_ascii=False, indent=2)
    return metadata_path


def summary_for_comparison(trace: TraceResult) -> dict[str, Any]:
    time_steps = int(trace.summary["time_steps_completed"])
    event_count = int(trace.summary["avalanche_count"])
    periods = int(trace.summary["periods_completed"])
    avalanche_period_count = len({int(event["period"]) for event in trace.event_history})
    large_threshold = int(trace.summary["large_cascade_threshold_nodes"])
    return {
        "scene_id": trace.spec.scene_id,
        "protocol": trace.spec.protocol,
        "seed": int(trace.spec.seed),
        "n_nodes": int(trace.summary["n_nodes"]),
        "periods_completed": periods,
        "time_steps_completed": time_steps,
        "event_count": event_count,
        "event_timestep_rate": event_count / time_steps if time_steps else 0.0,
        "event_period_occupancy": avalanche_period_count / periods if periods else 0.0,
        "total_credit_issued": int(trace.summary["total_credit_issued"]),
        "final_active_credit": int(trace.summary["final_active_credit"]),
        "max_collapse_size": int(trace.summary["max_collapse_size"]),
        "max_collapse_fraction": float(trace.summary["max_collapse_fraction"]),
        "large_cascade_threshold_nodes": large_threshold,
        "reached_10pct_n": bool(trace.summary["max_collapse_size"] >= large_threshold),
        "large_cascade_event_count": int(trace.summary["large_cascade_event_count"]),
        "initial_money_gini": float(trace.summary["initial_money_gini"]),
        "final_net_worth_gini": float(trace.summary["final_net_worth_gini"]),
        "first_cascade_period": int(trace.summary["first_cascade_period"]),
        "first_cascade_time_steps": int(trace.summary["first_cascade_time_steps"]),
        "critical_event": bool(trace.summary["critical_event"]),
    }


def write_same_params_comparison_summary(
    left: TraceResult,
    right: TraceResult,
    output_dir: Path,
    paths: dict[str, dict[str, Path] | Path],
) -> Path:
    summary_path = output_dir / "same_params_comparison_summary.json"
    initial_identical = bool(np.array_equal(left.frames[0].cash, right.frames[0].cash))
    payload = {
        "generated_at_cst": cst_now_iso(),
        "script": str(Path(__file__).relative_to(PROJECT_ROOT)),
        "comparison": "same parameters; only default_check_mode/settlement-check granularity differs",
        "same_params_base": SAME_PARAMS_BASE_PARAMS,
        "shared_seed": SAME_PARAMS_SEED,
        "shared_layout_seed": SAME_PARAMS_LAYOUT_SEED,
        "seed_selection": SAME_PARAMS_SEED_SELECTION,
        "initial_cash_vectors_identical": initial_identical,
        "initial_cash_reproducibility_note": (
            "Both traces call sample_initial_money with the same seed and identical "
            "parameters before protocol-specific dynamics diverge, so the initial "
            "cash vectors are identical in this renderer."
        ),
        "initial_cash_sha256": cash_vector_hash(left.frames[0].cash),
        "period_end": summary_for_comparison(left),
        "timestep_settle_check": summary_for_comparison(right),
        "outputs": {
            key: (
                {subkey: str(path.relative_to(PROJECT_ROOT)) for subkey, path in value.items()}
                if isinstance(value, dict)
                else str(value.relative_to(PROJECT_ROOT))
            )
            for key, value in paths.items()
        },
    }
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(to_builtin(payload), handle, ensure_ascii=False, indent=2)
    return summary_path


def render_same_params_suite(output_dir: Path, fps: int) -> tuple[list[tuple[TraceResult, dict[str, Path]]], dict[str, Path]]:
    traces: list[TraceResult] = []
    for spec in SAME_PARAM_SCENES:
        print(f"[{cst_now_iso()}] tracing {spec.scene_id} ({spec.protocol})")
        trace = run_trace(spec)
        traces.append(trace)
        print(
            f"[{cst_now_iso()}] traced {spec.scene_id}: "
            f"frames={len(trace.frames)} events={len(trace.event_history)} "
            f"max_collapse={trace.summary['max_collapse_size']}"
        )

    period_trace, timestep_trace = traces
    shared_pos = build_layout(combined_frames(traces), seed=SAME_PARAMS_LAYOUT_SEED)
    shared_scale = compute_render_scale(combined_frames(traces))
    initial_cash_identical = bool(
        np.array_equal(period_trace.frames[0].cash, timestep_trace.frames[0].cash)
    )
    common_metadata = {
        "same_params_comparison": {
            "shared_seed": SAME_PARAMS_SEED,
            "shared_layout_seed": SAME_PARAMS_LAYOUT_SEED,
            "same_params_base": SAME_PARAMS_BASE_PARAMS,
            "seed_selection": SAME_PARAMS_SEED_SELECTION,
            "initial_cash_vectors_identical": initial_cash_identical,
            "initial_cash_sha256": cash_vector_hash(period_trace.frames[0].cash),
            "common_layout": "shared spring layout built from both protocol traces",
            "common_color_scale": "shared scale built from both protocol traces",
            "only_intended_protocol_difference": (
                "default_check_mode and resulting settlement/check granularity: "
                "period_end versus timestep_settle_check"
            ),
        }
    }

    rendered: list[tuple[TraceResult, dict[str, Path]]] = []
    for trace in traces:
        print(f"[{cst_now_iso()}] rendering {trace.spec.scene_id}")
        paths = render_scene(
            trace,
            output_dir,
            fps=fps,
            pos=shared_pos,
            scale=shared_scale,
            extra_metadata=common_metadata,
        )
        rendered.append((trace, paths))
        print(
            f"[{cst_now_iso()}] done {trace.spec.scene_id}: "
            f"gif={paths['gif']} metadata={paths['metadata_json']}"
        )

    print(f"[{cst_now_iso()}] rendering side-by-side comparison")
    side_gif = render_side_by_side_gif(
        period_trace,
        timestep_trace,
        output_dir,
        fps=fps,
        pos=shared_pos,
        scale=shared_scale,
    )
    side_keyframes = render_side_by_side_keyframes(
        period_trace,
        timestep_trace,
        output_dir,
        pos=shared_pos,
        scale=shared_scale,
    )
    side_csv = write_side_by_side_trace_summary(
        period_trace,
        timestep_trace,
        output_dir,
        total_frames=max(len(period_trace.frames), len(timestep_trace.frames)),
    )
    side_metadata = write_side_by_side_metadata(
        period_trace,
        timestep_trace,
        output_dir,
        fps=fps,
        gif_path=side_gif,
        keyframes_path=side_keyframes,
        trace_csv_path=side_csv,
    )
    side_paths = {
        "gif": side_gif,
        "keyframes_png": side_keyframes,
        "trace_summary_csv": side_csv,
        "metadata_json": side_metadata,
    }
    summary_path = write_same_params_comparison_summary(
        period_trace,
        timestep_trace,
        output_dir,
        paths={
            "same_params_period_end": rendered[0][1],
            "same_params_timestep": rendered[1][1],
            "side_by_side": side_paths,
        },
    )
    print(
        f"[{cst_now_iso()}] done side-by-side: gif={side_gif} "
        f"summary={summary_path}"
    )
    return rendered, side_paths | {"comparison_summary_json": summary_path}


def write_index(
    output_dir: Path,
    rendered: list[tuple[TraceResult, dict[str, Path]]],
    fps: int,
) -> Path:
    index_path = output_dir / "visual_evolution_index.json"
    payload = {
        "generated_at_cst": cst_now_iso(),
        "script": str(Path(__file__).relative_to(PROJECT_ROOT)),
        "fps": int(fps),
        "scene_count": len(rendered),
        "scenes": [
            {
                "scene_id": trace.spec.scene_id,
                "protocol": trace.spec.protocol,
                "description": trace.spec.description,
                "summary": trace.summary,
                "outputs": {
                    key: str(path.relative_to(PROJECT_ROOT))
                    for key, path in paths.items()
                },
            }
            for trace, paths in rendered
        ],
    }
    with index_path.open("w", encoding="utf-8") as handle:
        json.dump(to_builtin(payload), handle, ensure_ascii=False, indent=2)
    return index_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=["original", "same_params", "same_params_v3"],
        default="original",
        help="Render the original visual scenes or the same-parameter protocol comparison.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for GIFs, keyframes, metadata, and trace summaries.",
    )
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument(
        "--scene",
        action="append",
        choices=[scene.scene_id for scene in SCENES + SAME_PARAM_SCENES],
        help="Render only selected scene(s) in the selected suite. Defaults to all.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = (
            DEFAULT_SAME_PARAMS_V3_OUTPUT_DIR
            if args.suite == "same_params_v3"
            else DEFAULT_SAME_PARAMS_OUTPUT_DIR
            if args.suite == "same_params"
            else DEFAULT_OUTPUT_DIR
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    fps = max(args.fps, 1)

    if args.suite in {"same_params", "same_params_v3"}:
        if args.scene:
            invalid = set(args.scene) - {scene.scene_id for scene in SAME_PARAM_SCENES}
            if invalid:
                raise ValueError(
                    f"scene(s) not in same_params suite: {sorted(invalid)}"
                )
        print(f"[{cst_now_iso()}] output_dir={output_dir}")
        rendered, side_paths = render_same_params_suite(output_dir, fps=fps)
        index_path = write_index(output_dir, rendered, fps=fps)
        print(f"[{cst_now_iso()}] wrote index={index_path}")
        print(
            f"[{cst_now_iso()}] side-by-side outputs="
            f"{', '.join(str(path) for path in side_paths.values())}"
        )
        return 0

    selected = set(args.scene or [scene.scene_id for scene in SCENES])
    rendered: list[tuple[TraceResult, dict[str, Path]]] = []

    print(f"[{cst_now_iso()}] output_dir={output_dir}")
    for spec in SCENES:
        if spec.scene_id not in selected:
            continue
        print(f"[{cst_now_iso()}] tracing {spec.scene_id} ({spec.protocol})")
        trace = run_trace(spec)
        print(
            f"[{cst_now_iso()}] rendering {spec.scene_id}: "
            f"frames={len(trace.frames)} events={len(trace.event_history)} "
            f"max_collapse={trace.summary['max_collapse_size']}"
        )
        paths = render_scene(trace, output_dir, fps=fps)
        rendered.append((trace, paths))
        print(
            f"[{cst_now_iso()}] done {spec.scene_id}: "
            f"gif={paths['gif']} metadata={paths['metadata_json']}"
        )

    index_path = write_index(output_dir, rendered, fps=fps)
    print(f"[{cst_now_iso()}] wrote index={index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
