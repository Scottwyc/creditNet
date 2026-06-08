from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


BORROWER_WEIGHTED_RULES = {
    "borrower_preferential",
    "preferential",
    "borrower_debt_preferential",
    "preferential_debt",
}
LENDER_CASH_WEIGHTED_RULES = {"cash_weighted", "preferential", "preferential_debt"}


def gini(values: np.ndarray) -> float:
    """Return the Gini coefficient for a vector."""
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


def stochastic_round(values: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    floors = np.floor(values).astype(np.int64)
    probs = np.clip(values - floors, 0.0, 1.0)
    return floors + (rng.random(values.shape) < probs)


@dataclass(frozen=True)
class CreditNetworkParams:
    n_nodes: int = 200
    mean_initial_money: float = 20.0
    money_distribution: str = "equal"
    income_distribution_rule: str = "uniform"
    growth_rule: str = "random"
    consumption_wealth_propensity: float = 0.02
    consumption_income_propensity: float = 0.20
    investment_income_propensity: float = 0.20
    initial_income_per_capita: float = 5.0
    income_bias_floor: float = 1.0
    collapse_threshold_fraction: float = 0.10
    max_periods: int = 500
    max_time_steps: int = 0
    default_threshold: float = 0.0
    wipe_defaulted_assets: bool = True
    validate_accounting: bool = True
    period_length_rule: str = "income"
    fixed_period_length_steps: int = 100
    avalanche_protocol: str = "stop_on_first_default"
    default_check_mode: str = "period_end"


@dataclass
class RunResult:
    params: dict[str, Any]
    seed: int
    ended_by_default: bool
    periods_completed: int
    time_steps_completed: int
    first_cascade_period: int
    first_cascade_time_steps: int
    last_period_length_steps: int
    max_period_length_steps: int
    total_credit_issued: int
    credit_scale_before_cascade: int
    active_credit_after_cascade: int
    collapse_size: int
    max_collapse_size: int
    total_collapse_size: int
    avalanche_count: int
    collapse_fraction: float
    critical_event: bool
    initial_total_money: int
    final_cash_total: int
    final_active_credit: int
    initial_money_gini: float
    final_net_worth_gini: float
    failed_credit_events: int
    total_income_last_period: int
    period_history: list[dict[str, Any]]
    avalanche_history: list[dict[str, Any]]

    def summary_row(self) -> dict[str, Any]:
        row = {
            "seed": self.seed,
            "ended_by_default": self.ended_by_default,
            "periods_completed": self.periods_completed,
            "time_steps_completed": self.time_steps_completed,
            "first_cascade_period": self.first_cascade_period,
            "first_cascade_time_steps": self.first_cascade_time_steps,
            "last_period_length_steps": self.last_period_length_steps,
            "max_period_length_steps": self.max_period_length_steps,
            "total_credit_issued": self.total_credit_issued,
            "credit_scale_before_cascade": self.credit_scale_before_cascade,
            "active_credit_after_cascade": self.active_credit_after_cascade,
            "collapse_size": self.collapse_size,
            "max_collapse_size": self.max_collapse_size,
            "total_collapse_size": self.total_collapse_size,
            "avalanche_count": self.avalanche_count,
            "collapse_fraction": self.collapse_fraction,
            "critical_event": self.critical_event,
            "initial_total_money": self.initial_total_money,
            "final_cash_total": self.final_cash_total,
            "final_active_credit": self.final_active_credit,
            "initial_money_gini": self.initial_money_gini,
            "final_net_worth_gini": self.final_net_worth_gini,
            "failed_credit_events": self.failed_credit_events,
            "total_income_last_period": self.total_income_last_period,
        }
        row.update(self.params)
        return row


def sample_initial_money(params: CreditNetworkParams, rng: np.random.Generator) -> np.ndarray:
    n = params.n_nodes
    mean = max(float(params.mean_initial_money), 0.0)
    if params.money_distribution == "equal":
        money = np.full(n, int(round(mean)), dtype=np.int64)
    elif params.money_distribution == "uniform":
        high = max(1, int(round(2.0 * mean)))
        money = rng.integers(0, high + 1, size=n, dtype=np.int64)
    elif params.money_distribution == "normal":
        raw = rng.normal(loc=mean, scale=max(mean * 0.5, 1.0), size=n)
        money = np.clip(np.rint(raw), 0, None).astype(np.int64)
    elif params.money_distribution == "lognormal":
        sigma = 1.0
        mu = np.log(max(mean, 1e-6)) - 0.5 * sigma * sigma
        money = np.rint(rng.lognormal(mean=mu, sigma=sigma, size=n)).astype(np.int64)
    elif params.money_distribution == "pareto":
        alpha = 2.0
        raw = rng.pareto(alpha, size=n) + 1.0
        scaled = raw * (mean / max(float(np.mean(raw)), 1e-9))
        money = np.rint(scaled).astype(np.int64)
    else:
        raise ValueError(f"unknown money_distribution: {params.money_distribution}")

    if int(money.sum()) <= 0 and n > 0:
        money[rng.integers(0, n)] = 1
    return money


def compute_period_length(last_total_income: int, params: CreditNetworkParams) -> int:
    if params.period_length_rule == "income":
        return max(0, int(round(params.investment_income_propensity * last_total_income)))
    if params.period_length_rule == "fixed":
        return max(0, int(params.fixed_period_length_steps))
    raise ValueError(f"unknown period_length_rule: {params.period_length_rule}")


def net_worth(
    cash: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
) -> np.ndarray:
    return cash + loan_assets - debt_liabilities


def validate_state(
    cash: np.ndarray,
    exposure: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    expected_cash_total: int,
) -> None:
    if np.any(cash < 0):
        raise RuntimeError("accounting violation: negative cash balance")
    if np.any(exposure < 0):
        raise RuntimeError("accounting violation: negative credit exposure")
    if np.any(loan_assets < 0) or np.any(debt_liabilities < 0):
        raise RuntimeError("accounting violation: negative balance-sheet credit item")
    if np.any(np.diag(exposure) != 0):
        raise RuntimeError("accounting violation: self-credit exposure exists")
    if int(cash.sum()) != int(expected_cash_total):
        raise RuntimeError(
            f"accounting violation: cash total changed from {expected_cash_total} to {int(cash.sum())}"
        )
    if not np.array_equal(loan_assets, exposure.sum(axis=1)):
        raise RuntimeError("accounting violation: loan assets do not match exposure rows")
    if not np.array_equal(debt_liabilities, exposure.sum(axis=0)):
        raise RuntimeError("accounting violation: debt liabilities do not match exposure columns")


def choose_lender(
    cash: np.ndarray,
    worth: np.ndarray,
    params: CreditNetworkParams,
    rng: np.random.Generator,
) -> int | None:
    valid = np.flatnonzero(cash >= 1)
    if valid.size == 0:
        return None
    if params.growth_rule in LENDER_CASH_WEIGHTED_RULES:
        weights = cash[valid].astype(float)
        weights = weights / weights.sum()
        return int(rng.choice(valid, p=weights))
    return int(rng.choice(valid))


def choose_borrower(
    lender: int,
    worth: np.ndarray,
    params: CreditNetworkParams,
    rng: np.random.Generator,
    borrower_cum_weights: np.ndarray | None = None,
) -> int | None:
    n = worth.size
    if n <= 1:
        return None
    if params.growth_rule not in BORROWER_WEIGHTED_RULES:
        borrower = int(rng.integers(0, n - 1))
        if borrower >= lender:
            borrower += 1
        return borrower

    if borrower_cum_weights is None:
        weights = np.maximum(worth, 0).astype(float) + params.income_bias_floor
        borrower_cum_weights = np.cumsum(weights)
    total_weight = float(borrower_cum_weights[-1])
    lender_left = float(borrower_cum_weights[lender - 1]) if lender > 0 else 0.0
    lender_weight = float(borrower_cum_weights[lender] - lender_left)
    effective_total = total_weight - lender_weight
    if effective_total <= 0:
        borrower = int(rng.integers(0, n - 1))
        if borrower >= lender:
            borrower += 1
        return borrower

    draw = float(rng.random() * effective_total)
    if draw >= lender_left:
        draw += lender_weight
    borrower = int(np.searchsorted(borrower_cum_weights, draw, side="right"))
    if borrower == lender:
        borrower = (borrower + 1) % n
    return borrower


def grow_credit_network(
    cash: np.ndarray,
    exposure: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    last_total_income: int,
    params: CreditNetworkParams,
    rng: np.random.Generator,
    period_length_steps: int | None = None,
) -> tuple[np.ndarray, int, int, int]:
    planned_credit_events = (
        compute_period_length(last_total_income, params)
        if period_length_steps is None
        else int(period_length_steps)
    )
    borrowed_this_period = np.zeros(params.n_nodes, dtype=np.int64)
    issued = 0
    failed = 0
    attempted = 0
    worth = net_worth(cash, loan_assets, debt_liabilities)
    borrower_cum_weights = None
    if params.growth_rule in {"borrower_preferential", "preferential"}:
        borrower_weights = np.maximum(worth, 0).astype(float) + params.income_bias_floor
        borrower_cum_weights = np.cumsum(borrower_weights)

    for _ in range(max(planned_credit_events, 0)):
        attempted += 1
        lender = choose_lender(cash, worth, params, rng)
        if lender is None:
            failed += 1
            break
        if params.growth_rule in {"borrower_debt_preferential", "preferential_debt"}:
            borrower_weights = debt_liabilities.astype(float) + params.income_bias_floor
            borrower_cum_weights = np.cumsum(borrower_weights)
        borrower = choose_borrower(lender, worth, params, rng, borrower_cum_weights)
        if borrower is None:
            failed += 1
            continue
        cash[lender] -= 1
        cash[borrower] += 1
        exposure[lender, borrower] += 1
        loan_assets[lender] += 1
        debt_liabilities[borrower] += 1
        borrowed_this_period[borrower] += 1
        issued += 1

    return borrowed_this_period, issued, failed, attempted


def spend_and_distribute_income(
    cash: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    last_income: np.ndarray,
    borrowed_this_period: np.ndarray,
    params: CreditNetworkParams,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int, int, int]:
    worth_before_spending = net_worth(cash, loan_assets, debt_liabilities)
    consumption_plan = (
        params.consumption_wealth_propensity * np.maximum(worth_before_spending, 0)
        + params.consumption_income_propensity * np.maximum(last_income, 0)
    )
    planned_consumption = stochastic_round(consumption_plan, rng)

    investment_spending = np.minimum(cash, borrowed_this_period).astype(np.int64)
    cash -= investment_spending
    consumption_spending = np.minimum(cash, planned_consumption).astype(np.int64)
    cash -= consumption_spending
    total_spending = int(investment_spending.sum() + consumption_spending.sum())

    if total_spending <= 0:
        new_income = np.zeros_like(cash)
        return new_income, 0, int(investment_spending.sum()), int(consumption_spending.sum())

    if params.income_distribution_rule == "uniform":
        probs = np.full(params.n_nodes, 1.0 / params.n_nodes)
    elif params.income_distribution_rule == "biased":
        worth_after_spending = net_worth(cash, loan_assets, debt_liabilities)
        weights = np.maximum(worth_after_spending, 0).astype(float) + params.income_bias_floor
        probs = weights / weights.sum()
    else:
        raise ValueError(f"unknown income_distribution_rule: {params.income_distribution_rule}")

    new_income = rng.multinomial(total_spending, probs).astype(np.int64)
    cash += new_income
    return (
        new_income,
        int(new_income.sum()),
        int(investment_spending.sum()),
        int(consumption_spending.sum()),
    )


def resolve_cascade(
    exposure: np.ndarray,
    cash: np.ndarray,
    loan_assets: np.ndarray,
    debt_liabilities: np.ndarray,
    initial_defaults: np.ndarray,
    params: CreditNetworkParams,
) -> tuple[np.ndarray, int]:
    defaulted = np.zeros(params.n_nodes, dtype=bool)
    queue = list(map(int, initial_defaults))
    cascade_steps = 0

    while queue:
        node = queue.pop(0)
        if defaulted[node]:
            continue
        defaulted[node] = True
        cascade_steps += 1

        incoming = exposure[:, node].copy()
        loan_assets -= incoming
        debt_liabilities[node] -= int(incoming.sum())
        exposure[:, node] = 0

        if params.wipe_defaulted_assets:
            outgoing = exposure[node, :].copy()
            debt_liabilities -= outgoing
            loan_assets[node] -= int(outgoing.sum())
            exposure[node, :] = 0

        worth = net_worth(cash, loan_assets, debt_liabilities)
        new_defaults = np.flatnonzero((worth < params.default_threshold) & (~defaulted))
        queue.extend(map(int, new_defaults))

    return defaulted, cascade_steps


def simulate_one_run(
    params: CreditNetworkParams,
    seed: int,
    keep_period_history: bool = False,
) -> RunResult:
    if params.default_check_mode != "period_end":
        raise ValueError("only default_check_mode='period_end' is implemented")
    if params.avalanche_protocol not in {"stop_on_first_default", "continue_after_avalanche"}:
        raise ValueError(f"unknown avalanche_protocol: {params.avalanche_protocol}")

    rng = np.random.default_rng(seed)
    cash = sample_initial_money(params, rng)
    initial_money = cash.copy()
    initial_cash_total = int(initial_money.sum())
    exposure = np.zeros((params.n_nodes, params.n_nodes), dtype=np.int64)
    loan_assets = np.zeros(params.n_nodes, dtype=np.int64)
    debt_liabilities = np.zeros(params.n_nodes, dtype=np.int64)
    last_income = np.full(
        params.n_nodes,
        int(round(params.initial_income_per_capita)),
        dtype=np.int64,
    )
    last_total_income = int(last_income.sum())

    total_credit_issued = 0
    time_steps_completed = 0
    failed_credit_events = 0
    period_history: list[dict[str, Any]] = []
    avalanche_history: list[dict[str, Any]] = []
    ended_by_default = False
    max_collapse_size = 0
    total_collapse_size = 0
    credit_scale_before_cascade = 0
    first_cascade_period = 0
    first_cascade_time_steps = 0
    last_period_length_steps = 0
    max_period_length_steps = 0
    periods_completed = 0

    for period in range(1, params.max_periods + 1):
        period_length_steps = compute_period_length(last_total_income, params)
        last_period_length_steps = period_length_steps
        max_period_length_steps = max(max_period_length_steps, period_length_steps)
        borrowed, issued, failed, attempted = grow_credit_network(
            cash,
            exposure,
            loan_assets,
            debt_liabilities,
            last_total_income,
            params,
            rng,
            period_length_steps=period_length_steps,
        )
        time_steps_completed += attempted
        total_credit_issued += issued
        failed_credit_events += failed

        last_income, total_income, investment_spend, consumption_spend = (
            spend_and_distribute_income(
                cash, loan_assets, debt_liabilities, last_income, borrowed, params, rng
            )
        )
        last_total_income = total_income

        if params.validate_accounting:
            validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)

        worth = net_worth(cash, loan_assets, debt_liabilities)
        initial_defaults = np.flatnonzero(worth < params.default_threshold)
        periods_completed = period

        if keep_period_history:
            period_history.append(
                {
                    "period": period,
                    "period_length_steps": period_length_steps,
                    "time_steps_completed": time_steps_completed,
                    "issued_credit": issued,
                    "failed_credit_events": failed,
                    "active_credit": int(exposure.sum()),
                    "investment_spending": investment_spend,
                    "consumption_spending": consumption_spend,
                    "total_income": total_income,
                    "min_net_worth": float(worth.min()) if worth.size else 0.0,
                    "negative_net_worth_nodes": int(initial_defaults.size),
                    "cash_total": int(cash.sum()),
                }
            )

        if initial_defaults.size > 0:
            ended_by_default = True
            pre_cascade_credit = int(exposure.sum())
            defaulted, _ = resolve_cascade(
                exposure, cash, loan_assets, debt_liabilities, initial_defaults, params
            )
            if params.validate_accounting:
                validate_state(cash, exposure, loan_assets, debt_liabilities, initial_cash_total)
            event_collapse_size = int(defaulted.sum())
            event_collapse_fraction = event_collapse_size / params.n_nodes if params.n_nodes else 0.0
            if not avalanche_history:
                credit_scale_before_cascade = pre_cascade_credit
                first_cascade_period = period
                first_cascade_time_steps = time_steps_completed
            max_collapse_size = max(max_collapse_size, event_collapse_size)
            total_collapse_size += event_collapse_size
            avalanche_history.append(
                {
                    "period": period,
                    "period_length_steps": period_length_steps,
                    "time_steps_completed": time_steps_completed,
                    "credit_scale_before_cascade": pre_cascade_credit,
                    "active_credit_after_cascade": int(exposure.sum()),
                    "initial_default_count": int(initial_defaults.size),
                    "collapse_size": event_collapse_size,
                    "collapse_fraction": float(event_collapse_fraction),
                    "critical_event": bool(
                        event_collapse_fraction >= params.collapse_threshold_fraction
                    ),
                }
            )
            if params.avalanche_protocol == "stop_on_first_default":
                break

        if params.max_time_steps > 0 and time_steps_completed >= params.max_time_steps:
            break
    else:
        periods_completed = params.max_periods

    if not avalanche_history:
        credit_scale_before_cascade = int(exposure.sum())

    final_worth = net_worth(cash, loan_assets, debt_liabilities)
    collapse_size = max_collapse_size
    collapse_fraction = collapse_size / params.n_nodes if params.n_nodes > 0 else 0.0
    critical_event = any(event["critical_event"] for event in avalanche_history)

    return RunResult(
        params=asdict(params),
        seed=seed,
        ended_by_default=ended_by_default,
        periods_completed=periods_completed,
        time_steps_completed=time_steps_completed,
        first_cascade_period=first_cascade_period,
        first_cascade_time_steps=first_cascade_time_steps,
        last_period_length_steps=last_period_length_steps,
        max_period_length_steps=max_period_length_steps,
        total_credit_issued=total_credit_issued,
        credit_scale_before_cascade=credit_scale_before_cascade,
        active_credit_after_cascade=int(exposure.sum()),
        collapse_size=collapse_size,
        max_collapse_size=max_collapse_size,
        total_collapse_size=total_collapse_size,
        avalanche_count=len(avalanche_history),
        collapse_fraction=float(collapse_fraction),
        critical_event=bool(critical_event),
        initial_total_money=int(initial_money.sum()),
        final_cash_total=int(cash.sum()),
        final_active_credit=int(exposure.sum()),
        initial_money_gini=gini(initial_money),
        final_net_worth_gini=gini(final_worth),
        failed_credit_events=failed_credit_events,
        total_income_last_period=int(last_total_income),
        period_history=period_history,
        avalanche_history=avalanche_history,
    )
