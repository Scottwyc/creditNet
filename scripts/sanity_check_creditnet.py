#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creditnet import CreditNetworkParams, simulate_one_run


def main() -> None:
    scenarios = [
        ("equal_uniform", "equal", "uniform", "random"),
        ("uniform_biased", "uniform", "biased", "random"),
        ("pareto_biased_pref", "pareto", "biased", "preferential"),
    ]
    rows = []
    for offset, (name, money_dist, income_rule, growth_rule) in enumerate(scenarios):
        params = CreditNetworkParams(
            n_nodes=40,
            mean_initial_money=15,
            money_distribution=money_dist,
            income_distribution_rule=income_rule,
            growth_rule=growth_rule,
            max_periods=80,
            collapse_threshold_fraction=0.10,
        )
        result = simulate_one_run(params=params, seed=20260602 + offset, keep_period_history=True)
        row = result.summary_row()
        row["scenario"] = name
        row["history_rows"] = len(result.period_history)
        rows.append(row)

    if not any(row["ended_by_default"] for row in rows):
        raise RuntimeError("sanity check did not trigger any default; parameters may be too mild")
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
