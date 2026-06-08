from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .simulation import gini, sample_initial_money, stochastic_round


SETTLEMENT_MODES = {"period_end", "check_only", "settle_and_check"}
DEFAULT_NODE_MODES = {"continue", "exit", "reset"}


@dataclass(frozen=True)
class MechanismParams:
    """Parameters for the independent phase-2 clearing-mechanism extension.

    A macro period first fixes its total planned credit attempts. The attempts can
    then be split into multiple batches without recomputing that total. In
    ``check_only`` mode, intermediate batches only inspect net worth; because a
    unit loan preserves both counterparties' net worth, these inspections should
    not create defaults. In ``settle_and_check`` mode, each batch settles flows
    and clearing follows ``default_check_every_settlements``, allowing a clean
    check-frequency intervention while the settlement schedule stays fixed.
    """

    n_nodes: int = 200
    mean_initial_money: float = 20.0
    money_distribution: str = "lognormal"
    income_distribution_rule: str = "biased"
    growth_rule: str = "random"
    consumption_wealth_propensity: float = 0.02
    consumption_income_propensity: float = 0.20
    investment_income_propensity: float = 0.20
    initial_income_per_capita: float = 5.0
    income_bias_floor: float = 1.0
    collapse_threshold_fraction: float = 0.10
    max_macro_periods: int = 200
    default_threshold: float = 0.0
    drive_rule: str = "income"
    fixed_drive_steps: int = 20
    max_drive_steps_per_macro: int = 500
    settlement_mode: str = "period_end"
    settlement_batches: int = 1
    default_check_every_settlements: int = 1
    recovery_rate: float = 0.0
    wipe_defaulted_assets: bool = True
    default_node_mode: str = "continue"
    validate_accounting: bool = True


@dataclass
class MechanismRunResult:
    params: dict[str, Any]
    seed: int
    summary: dict[str, Any]
    avalanche_history: list[dict[str, Any]]
    macro_history: list[dict[str, Any]]

    def summary_row(self) -> dict[str, Any]:
        return {"seed": self.seed, **self.summary, **self.params}


def validate_params(params: MechanismParams) -> None:
    if params.n_nodes < 0:
        raise ValueError("n_nodes must be non-negative")
    if params.growth_rule != "random":
        raise ValueError("phase2 mechanism extension currently supports growth_rule='random' only")
    if params.drive_rule not in {"income", "fixed"}:
        raise ValueError(f"unknown drive_rule: {params.drive_rule}")
    if params.settlement_mode not in SETTLEMENT_MODES:
        raise ValueError(f"unknown settlement_mode: {params.settlement_mode}")
    if params.default_node_mode not in DEFAULT_NODE_MODES:
        raise ValueError(f"unknown default_node_mode: {params.default_node_mode}")
    if params.settlement_batches < 1:
        raise ValueError("settlement_batches must be at least 1")
    if params.default_check_every_settlements < 1:
        raise ValueError("default_check_every_settlements must be at least 1")
    if not 0.0 <= params.recovery_rate <= 1.0:
        raise ValueError("recovery_rate must be in [0, 1]")
    if params.max_drive_steps_per_macro < 0:
        raise ValueError("max_drive_steps_per_macro must be non-negative")


def phase2_net_worth(
    cash: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
) -> np.ndarray:
    return cash + loan_assets - debt_liabilities


def partition_integer(total: int, parts: int) -> list[int]:
    total = max(int(total), 0)
    parts = max(int(parts), 1)
    quotient, remainder = divmod(total, parts)
    return [quotient + (index < remainder) for index in range(parts)]


def compute_drive_steps(last_macro_income: float, params: MechanismParams) -> tuple[int, int]:
    if params.drive_rule == "income":
        uncapped = max(0, int(round(params.investment_income_propensity * last_macro_income)))
    else:
        uncapped = max(0, int(params.fixed_drive_steps))
    if params.max_drive_steps_per_macro > 0:
        return uncapped, min(uncapped, int(params.max_drive_steps_per_macro))
    return uncapped, uncapped


def validate_phase2_state(
    cash: np.ndarray,
    exposure: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    expected_cash_total: float,
) -> None:
    tolerance = 1e-7
    if np.any(cash < -tolerance):
        raise RuntimeError("accounting violation: negative cash balance")
    if np.any(exposure < -tolerance):
        raise RuntimeError("accounting violation: negative credit exposure")
    if np.any(loan_assets < -tolerance) or np.any(debt_liabilities < -tolerance):
        raise RuntimeError("accounting violation: negative balance-sheet credit item")
    if np.any(np.abs(np.diag(exposure)) > tolerance):
        raise RuntimeError("accounting violation: self-credit exposure exists")
    if not np.isclose(float(cash.sum()), float(expected_cash_total), atol=tolerance, rtol=0):
        raise RuntimeError(
            "accounting violation: cash total differs from initial cash plus external reset flow"
        )
    if not np.allclose(loan_assets, exposure.sum(axis=1), atol=tolerance, rtol=0):
        raise RuntimeError("accounting violation: loan assets do not match exposure rows")
    if not np.allclose(debt_liabilities, exposure.sum(axis=0), atol=tolerance, rtol=0):
        raise RuntimeError("accounting violation: debt liabilities do not match exposure columns")


def grow_credit_batch(
    cash: np.ndarray,
    exposure: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    active: np.ndarray,
    planned_attempts: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int, int, int]:
    borrowed = np.zeros(cash.size, dtype=np.int64)
    issued = 0
    failed = 0
    attempted = 0
    planned_attempts = max(int(planned_attempts), 0)

    for attempt_index in range(planned_attempts):
        attempted += 1
        valid_lenders = np.flatnonzero(active & (cash >= 1.0 - 1e-9))
        if valid_lenders.size == 0 or int(active.sum()) <= 1:
            remaining = planned_attempts - attempt_index
            failed += remaining
            attempted += remaining - 1
            break
        lender = int(rng.choice(valid_lenders))
        valid_borrowers = np.flatnonzero(active)
        valid_borrowers = valid_borrowers[valid_borrowers != lender]
        if valid_borrowers.size == 0:
            failed += 1
            continue
        borrower = int(rng.choice(valid_borrowers))
        cash[lender] -= 1.0
        cash[borrower] += 1.0
        exposure[lender, borrower] += 1.0
        loan_assets[lender] += 1.0
        debt_liabilities[borrower] += 1.0
        borrowed[borrower] += 1
        issued += 1

    return borrowed, issued, failed, attempted


def settle_flows(
    cash: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    active: np.ndarray,
    macro_reference_income: np.ndarray,
    borrowed_since_settlement: np.ndarray,
    consumption_scale: float,
    params: MechanismParams,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int, int, int]:
    """Settle one flow batch while preserving total cash.

    For multiple settlements, the previous macro-period income is frozen as the
    consumption reference and the planned consumption propensity is divided by
    the number of batches. This keeps ex-ante macro consumption approximately
    comparable while allowing within-macro income redistribution to differ.
    """

    worth = phase2_net_worth(cash, loan_assets, debt_liabilities)
    consumption_plan = consumption_scale * (
        params.consumption_wealth_propensity * np.maximum(worth, 0.0)
        + params.consumption_income_propensity * np.maximum(macro_reference_income, 0.0)
    )
    planned_consumption = stochastic_round(consumption_plan, rng)
    planned_consumption[~active] = 0

    available_units = np.floor(np.maximum(cash, 0.0) + 1e-9).astype(np.int64)
    investment_spending = np.minimum(available_units, borrowed_since_settlement).astype(np.int64)
    investment_spending[~active] = 0
    cash -= investment_spending

    available_units = np.floor(np.maximum(cash, 0.0) + 1e-9).astype(np.int64)
    consumption_spending = np.minimum(available_units, planned_consumption).astype(np.int64)
    consumption_spending[~active] = 0
    cash -= consumption_spending
    total_spending = int(investment_spending.sum() + consumption_spending.sum())

    new_income = np.zeros(cash.size, dtype=np.int64)
    active_indices = np.flatnonzero(active)
    if total_spending > 0 and active_indices.size > 0:
        if params.income_distribution_rule == "uniform":
            probs = np.full(active_indices.size, 1.0 / active_indices.size)
        elif params.income_distribution_rule == "biased":
            worth_after_spending = phase2_net_worth(cash, loan_assets, debt_liabilities)
            weights = (
                np.maximum(worth_after_spending[active_indices], 0.0)
                + params.income_bias_floor
            )
            probs = weights / weights.sum()
        else:
            raise ValueError(f"unknown income_distribution_rule: {params.income_distribution_rule}")
        new_income[active_indices] = rng.multinomial(total_spending, probs).astype(np.int64)
        cash += new_income

    return (
        new_income,
        total_spending,
        int(investment_spending.sum()),
        int(consumption_spending.sum()),
    )


def resolve_phase2_cascade(
    exposure: np.ndarray,
    cash: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    active: np.ndarray,
    initial_money: np.ndarray,
    initial_defaults: np.ndarray,
    params: MechanismParams,
) -> dict[str, Any]:
    """Clear one cascade with explicit cash-capped recovery accounting.

    Incoming defaulted debt contracts are closed at face value. Creditors receive
    up to ``recovery_rate * face`` from the defaulted debtor's existing cash,
    allocated pro-rata and capped by that cash. The unpaid face value is the
    creditor asset loss. Recovery therefore never injects external money.

    ``reset`` is deliberately different: after clearing, the node's cash is set
    back to its run-specific initial cash. The resulting external cash flow is
    recorded so the accounting identity remains explicit.
    """

    defaulted = np.zeros(cash.size, dtype=bool)
    queue: deque[int] = deque(map(int, initial_defaults))
    target_recovery_total = 0.0
    actual_recovery_total = 0.0
    creditor_loss_total = 0.0
    wiped_asset_face_total = 0.0

    while queue:
        node = queue.popleft()
        if defaulted[node] or not active[node]:
            continue
        defaulted[node] = True

        incoming = exposure[:, node].copy()
        incoming_face = float(incoming.sum())
        if incoming_face > 0:
            target_by_creditor = incoming * params.recovery_rate
            target_total = float(target_by_creditor.sum())
            actual_total = min(max(float(cash[node]), 0.0), target_total)
            paid_by_creditor = (
                target_by_creditor * (actual_total / target_total)
                if target_total > 0
                else np.zeros_like(incoming)
            )
            cash[node] -= actual_total
            cash += paid_by_creditor
            target_recovery_total += target_total
            actual_recovery_total += actual_total
            creditor_loss_total += incoming_face - actual_total
            loan_assets -= incoming
            debt_liabilities[node] -= incoming_face
            exposure[:, node] = 0.0

        if params.wipe_defaulted_assets:
            outgoing = exposure[node, :].copy()
            outgoing_face = float(outgoing.sum())
            if outgoing_face > 0:
                debt_liabilities -= outgoing
                loan_assets[node] -= outgoing_face
                exposure[node, :] = 0.0
                wiped_asset_face_total += outgoing_face

        worth = phase2_net_worth(cash, loan_assets, debt_liabilities)
        new_defaults = np.flatnonzero(
            active & (~defaulted) & (worth < params.default_threshold)
        )
        queue.extend(map(int, new_defaults))

    external_reset_cash_flow = 0.0
    reset_cleared_asset_face = 0.0
    if params.default_node_mode == "exit":
        active[defaulted] = False
    elif params.default_node_mode == "reset":
        for node in np.flatnonzero(defaulted):
            outgoing = exposure[node, :].copy()
            outgoing_face = float(outgoing.sum())
            if outgoing_face > 0:
                debt_liabilities -= outgoing
                loan_assets[node] -= outgoing_face
                exposure[node, :] = 0.0
                reset_cleared_asset_face += outgoing_face
        old_cash = cash[defaulted].copy()
        cash[defaulted] = initial_money[defaulted]
        external_reset_cash_flow = float((cash[defaulted] - old_cash).sum())
        active[defaulted] = True

    return {
        "defaulted_mask": defaulted,
        "cascade_steps": int(defaulted.sum()),
        "target_recovery": target_recovery_total,
        "actual_recovery": actual_recovery_total,
        "creditor_loss": creditor_loss_total,
        "wiped_asset_face": wiped_asset_face_total,
        "reset_cleared_asset_face": reset_cleared_asset_face,
        "external_reset_cash_flow": external_reset_cash_flow,
    }


def simulate_mechanism_run(
    params: MechanismParams,
    seed: int,
    keep_macro_history: bool = False,
) -> MechanismRunResult:
    validate_params(params)
    rng = np.random.default_rng(seed)
    cash = sample_initial_money(params, rng).astype(float)
    initial_money = cash.copy()
    initial_cash_total = float(cash.sum())
    exposure = np.zeros((params.n_nodes, params.n_nodes), dtype=float)
    loan_assets = np.zeros(params.n_nodes, dtype=float)
    debt_liabilities = np.zeros(params.n_nodes, dtype=float)
    active = np.ones(params.n_nodes, dtype=bool)
    last_macro_income = np.full(
        params.n_nodes,
        int(round(params.initial_income_per_capita)),
        dtype=np.int64,
    )
    default_counts = np.zeros(params.n_nodes, dtype=np.int64)

    avalanche_history: list[dict[str, Any]] = []
    macro_history: list[dict[str, Any]] = []
    total_credit_issued = 0
    total_attempts = 0
    failed_credit_events = 0
    settlements_completed = 0
    checks_completed = 0
    total_drive_steps = 0
    uncapped_total_drive_steps = 0
    capped_macro_periods = 0
    total_external_reset_cash_flow = 0.0
    total_target_recovery = 0.0
    total_actual_recovery = 0.0
    total_creditor_loss = 0.0
    active_credit_snapshots: list[float] = []
    macro_periods_completed = 0

    def inspect_and_clear(
        macro_period: int,
        batch_index: int,
        check_kind: str,
        macro_drive_steps: int,
        batch_planned_attempts: int,
    ) -> None:
        nonlocal checks_completed
        nonlocal total_external_reset_cash_flow
        nonlocal total_target_recovery
        nonlocal total_actual_recovery
        nonlocal total_creditor_loss

        checks_completed += 1
        worth = phase2_net_worth(cash, loan_assets, debt_liabilities)
        initial_defaults = np.flatnonzero(
            active & (worth < params.default_threshold)
        )
        if initial_defaults.size == 0:
            return

        pre_credit = float(exposure.sum())
        result = resolve_phase2_cascade(
            exposure,
            cash,
            loan_assets,
            debt_liabilities,
            active,
            initial_money,
            initial_defaults,
            params,
        )
        defaulted = result["defaulted_mask"]
        repeat_default_nodes = int(np.sum(default_counts[defaulted] > 0))
        first_time_default_nodes = int(np.sum(default_counts[defaulted] == 0))
        default_counts[defaulted] += 1
        collapse_size = int(defaulted.sum())
        collapse_fraction = collapse_size / params.n_nodes if params.n_nodes else 0.0
        total_external_reset_cash_flow += float(result["external_reset_cash_flow"])
        total_target_recovery += float(result["target_recovery"])
        total_actual_recovery += float(result["actual_recovery"])
        total_creditor_loss += float(result["creditor_loss"])
        avalanche_history.append(
            {
                "event_index": len(avalanche_history) + 1,
                "macro_period": macro_period,
                "batch_index": batch_index,
                "check_kind": check_kind,
                "macro_drive_steps": macro_drive_steps,
                "batch_planned_attempts": batch_planned_attempts,
                "time_steps_completed": total_attempts,
                "total_credit_issued": total_credit_issued,
                "credit_scale_before_cascade": pre_credit,
                "active_credit_after_cascade": float(exposure.sum()),
                "active_nodes_after_cascade": int(active.sum()),
                "initial_default_count": int(initial_defaults.size),
                "collapse_size": collapse_size,
                "collapse_fraction": float(collapse_fraction),
                "critical_event": bool(
                    collapse_fraction >= params.collapse_threshold_fraction
                ),
                "first_time_default_nodes": first_time_default_nodes,
                "repeat_default_nodes": repeat_default_nodes,
                "target_recovery": float(result["target_recovery"]),
                "actual_recovery": float(result["actual_recovery"]),
                "creditor_loss": float(result["creditor_loss"]),
                "wiped_asset_face": float(result["wiped_asset_face"]),
                "reset_cleared_asset_face": float(result["reset_cleared_asset_face"]),
                "external_reset_cash_flow": float(result["external_reset_cash_flow"]),
                "cash_total_after_cascade": float(cash.sum()),
            }
        )
        if params.validate_accounting:
            validate_phase2_state(
                cash,
                exposure,
                loan_assets,
                debt_liabilities,
                initial_cash_total + total_external_reset_cash_flow,
            )

    for macro_period in range(1, params.max_macro_periods + 1):
        macro_periods_completed = macro_period
        uncapped_drive, drive_steps = compute_drive_steps(float(last_macro_income.sum()), params)
        uncapped_total_drive_steps += uncapped_drive
        total_drive_steps += drive_steps
        if drive_steps < uncapped_drive:
            capped_macro_periods += 1

        batches = (
            1 if params.settlement_mode == "period_end" else params.settlement_batches
        )
        batch_attempts = partition_integer(drive_steps, batches)
        macro_borrowed = np.zeros(params.n_nodes, dtype=np.int64)
        macro_new_income = np.zeros(params.n_nodes, dtype=np.int64)
        macro_issued = 0
        macro_failed = 0
        macro_attempted = 0
        macro_investment_spending = 0
        macro_consumption_spending = 0
        macro_event_count_before = len(avalanche_history)
        macro_reference_income = last_macro_income.copy()

        for batch_index, planned_attempts in enumerate(batch_attempts, start=1):
            borrowed, issued, failed, attempted = grow_credit_batch(
                cash,
                exposure,
                loan_assets,
                debt_liabilities,
                active,
                planned_attempts,
                rng,
            )
            total_credit_issued += issued
            total_attempts += attempted
            failed_credit_events += failed
            macro_issued += issued
            macro_failed += failed
            macro_attempted += attempted

            if params.settlement_mode == "settle_and_check":
                income, _, investment_spending, consumption_spending = settle_flows(
                    cash,
                    loan_assets,
                    debt_liabilities,
                    active,
                    macro_reference_income,
                    borrowed,
                    1.0 / batches,
                    params,
                    rng,
                )
                macro_new_income += income
                macro_investment_spending += investment_spending
                macro_consumption_spending += consumption_spending
                settlements_completed += 1
                if params.validate_accounting:
                    validate_phase2_state(
                        cash,
                        exposure,
                        loan_assets,
                        debt_liabilities,
                        initial_cash_total + total_external_reset_cash_flow,
                    )
                should_check = (
                    batch_index % params.default_check_every_settlements == 0
                    or batch_index == batches
                )
                if should_check:
                    inspect_and_clear(
                        macro_period,
                        batch_index,
                        f"settlement_check_q{params.default_check_every_settlements}",
                        drive_steps,
                        planned_attempts,
                    )
                active_credit_snapshots.append(float(exposure.sum()))
            else:
                macro_borrowed += borrowed
                if params.settlement_mode == "check_only":
                    inspect_and_clear(
                        macro_period,
                        batch_index,
                        "check_only_no_flow",
                        drive_steps,
                        planned_attempts,
                    )

        if params.settlement_mode in {"period_end", "check_only"}:
            income, _, investment_spending, consumption_spending = settle_flows(
                cash,
                loan_assets,
                debt_liabilities,
                active,
                macro_reference_income,
                macro_borrowed,
                1.0,
                params,
                rng,
            )
            macro_new_income = income
            macro_investment_spending = investment_spending
            macro_consumption_spending = consumption_spending
            settlements_completed += 1
            if params.validate_accounting:
                validate_phase2_state(
                    cash,
                    exposure,
                    loan_assets,
                    debt_liabilities,
                    initial_cash_total + total_external_reset_cash_flow,
                )
            inspect_and_clear(
                macro_period,
                batches,
                "settlement",
                drive_steps,
                batch_attempts[-1] if batch_attempts else 0,
            )
            active_credit_snapshots.append(float(exposure.sum()))

        last_macro_income = macro_new_income
        if keep_macro_history:
            macro_history.append(
                {
                    "macro_period": macro_period,
                    "uncapped_drive_steps": uncapped_drive,
                    "drive_steps": drive_steps,
                    "batches": batches,
                    "attempted": macro_attempted,
                    "issued": macro_issued,
                    "failed": macro_failed,
                    "investment_spending": macro_investment_spending,
                    "consumption_spending": macro_consumption_spending,
                    "macro_income": int(macro_new_income.sum()),
                    "active_credit": float(exposure.sum()),
                    "active_nodes": int(active.sum()),
                    "avalanche_count": len(avalanche_history) - macro_event_count_before,
                    "cash_total": float(cash.sum()),
                    "external_reset_cash_flow_total": total_external_reset_cash_flow,
                }
            )

        if int(active.sum()) == 0:
            break

    final_worth = phase2_net_worth(cash, loan_assets, debt_liabilities)
    event_sizes = [int(event["collapse_size"]) for event in avalanche_history]
    max_collapse_size = max(event_sizes, default=0)
    total_default_occurrences = int(default_counts.sum())
    unique_default_nodes = int(np.sum(default_counts > 0))
    repeat_default_occurrences = total_default_occurrences - unique_default_nodes
    active_avalanche_macro_periods = len(
        {int(event["macro_period"]) for event in avalanche_history}
    )
    summary = {
        "ended_by_default": bool(avalanche_history),
        "macro_periods_completed": macro_periods_completed,
        "settlements_completed": settlements_completed,
        "checks_completed": checks_completed,
        "uncapped_total_drive_steps": uncapped_total_drive_steps,
        "total_drive_steps": total_drive_steps,
        "capped_macro_periods": capped_macro_periods,
        "time_steps_completed": total_attempts,
        "total_credit_issued": total_credit_issued,
        "failed_credit_events": failed_credit_events,
        "avalanche_count": len(avalanche_history),
        "active_avalanche_macro_periods": active_avalanche_macro_periods,
        "avalanche_active_macro_rate": (
            active_avalanche_macro_periods / macro_periods_completed
            if macro_periods_completed
            else 0.0
        ),
        "max_collapse_size": max_collapse_size,
        "total_collapse_size": int(sum(event_sizes)),
        "collapse_fraction": max_collapse_size / params.n_nodes if params.n_nodes else 0.0,
        "critical_event": any(bool(event["critical_event"]) for event in avalanche_history),
        "unique_default_nodes": unique_default_nodes,
        "total_default_occurrences": total_default_occurrences,
        "repeat_default_occurrences": repeat_default_occurrences,
        "repeat_default_share": (
            repeat_default_occurrences / total_default_occurrences
            if total_default_occurrences
            else 0.0
        ),
        "initial_total_money": initial_cash_total,
        "final_cash_total": float(cash.sum()),
        "external_reset_cash_flow": total_external_reset_cash_flow,
        "final_active_credit": float(exposure.sum()),
        "mean_active_credit_after_settlement": (
            float(np.mean(active_credit_snapshots)) if active_credit_snapshots else 0.0
        ),
        "final_active_nodes": int(active.sum()),
        "initial_money_gini": gini(initial_money),
        "final_net_worth_gini": gini(final_worth),
        "total_target_recovery": total_target_recovery,
        "total_actual_recovery": total_actual_recovery,
        "total_creditor_loss": total_creditor_loss,
        "realized_recovery_share": (
            total_actual_recovery / total_target_recovery
            if total_target_recovery > 0
            else 0.0
        ),
        "total_income_last_macro": int(last_macro_income.sum()),
    }
    return MechanismRunResult(
        params=asdict(params),
        seed=seed,
        summary=summary,
        avalanche_history=avalanche_history,
        macro_history=macro_history,
    )


def run_phase2_accounting_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    rng = np.random.default_rng(17)
    cash = np.array([3.0, 2.0, 1.0])
    exposure = np.zeros((3, 3), dtype=float)
    assets = np.zeros(3, dtype=float)
    debts = np.zeros(3, dtype=float)
    active = np.ones(3, dtype=bool)
    worth_before = phase2_net_worth(cash, assets, debts).copy()
    _, issued, _, _ = grow_credit_batch(
        cash, exposure, assets, debts, active, planned_attempts=1, rng=rng
    )
    unit_invariant = issued == 1 and np.allclose(
        worth_before, phase2_net_worth(cash, assets, debts)
    )
    checks.append(
        {
            "check": "unit_credit_preserves_counterparty_net_worth",
            "passed": bool(unit_invariant),
            "detail": "One issued unit changes cash/assets/debt but not node net worth.",
        }
    )

    common = dict(
        n_nodes=50,
        mean_initial_money=15.0,
        money_distribution="lognormal",
        income_distribution_rule="biased",
        fixed_drive_steps=15,
        drive_rule="fixed",
        max_macro_periods=30,
        validate_accounting=True,
    )
    reference = simulate_mechanism_run(
        MechanismParams(**common, settlement_mode="period_end", settlement_batches=1),
        seed=2026060401,
    )
    check_only = simulate_mechanism_run(
        MechanismParams(**common, settlement_mode="check_only", settlement_batches=5),
        seed=2026060401,
    )
    comparison_keys = [
        "total_credit_issued",
        "avalanche_count",
        "max_collapse_size",
        "total_collapse_size",
        "final_active_credit",
        "final_cash_total",
        "final_active_nodes",
    ]
    equivalent = all(
        np.isclose(reference.summary[key], check_only.summary[key])
        for key in comparison_keys
    ) and [
        (event["macro_period"], event["collapse_size"])
        for event in reference.avalanche_history
    ] == [
        (event["macro_period"], event["collapse_size"])
        for event in check_only.avalanche_history
    ]
    checks.append(
        {
            "check": "check_only_split_matches_period_end_state",
            "passed": bool(equivalent),
            "detail": "Five no-flow checks reproduce the one-settlement reference for the same seed.",
        }
    )

    recovery = simulate_mechanism_run(
        MechanismParams(
            **(
                common
                | {
                    "fixed_drive_steps": 30,
                    "max_macro_periods": 50,
                    "recovery_rate": 0.5,
                    "settlement_mode": "period_end",
                }
            )
        ),
        seed=2026060402,
    )
    recovery_cash_ok = np.isclose(
        recovery.summary["final_cash_total"], recovery.summary["initial_total_money"]
    )
    checks.append(
        {
            "check": "cash_capped_recovery_conserves_cash",
            "passed": bool(recovery_cash_ok),
            "detail": (
                f"events={recovery.summary['avalanche_count']}, "
                f"actual_recovery={recovery.summary['total_actual_recovery']:.3f}"
            ),
        }
    )

    reset = simulate_mechanism_run(
        MechanismParams(
            **(
                common
                | {
                    "fixed_drive_steps": 30,
                    "max_macro_periods": 50,
                    "default_node_mode": "reset",
                    "settlement_mode": "period_end",
                }
            )
        ),
        seed=2026060403,
    )
    reset_identity_ok = np.isclose(
        reset.summary["final_cash_total"],
        reset.summary["initial_total_money"] + reset.summary["external_reset_cash_flow"],
    )
    checks.append(
        {
            "check": "reset_external_cash_flow_is_explicit",
            "passed": bool(reset_identity_ok and reset.summary["avalanche_count"] > 0),
            "detail": (
                f"events={reset.summary['avalanche_count']}, "
                f"external_flow={reset.summary['external_reset_cash_flow']:.3f}"
            ),
        }
    )

    if not all(bool(check["passed"]) for check in checks):
        failed = [check["check"] for check in checks if not check["passed"]]
        raise RuntimeError(f"phase2 accounting checks failed: {failed}")
    return checks
