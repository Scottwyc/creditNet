# Phase 2 机制稳健性消融分析摘要

生成时间：2026-06-04 12:55:21 CST

## 口径

- Run 数：264；avalanche 事件数：537387。
- `check_only_b10` 是可识别性负对照：拆分信贷驱动批次，但中间不结算流量。
- `flow_split_b10_check_q10/q5/q2/q1` 固定为十次相同流量结算，只改变每隔多少次结算检查清算；这是纯检查频率对照。
- `reference_period_end` 对比 `flow_split_b10_check_q10` 同时改变流量结算频率，必须视为收入/消费动态机制变化。
- 回收率是从违约债务人现有现金支付的目标比例，受现金上限约束，不注入外部现金。
- reset 会恢复节点的本轮初始现金，外部现金流单独记录，因此不能视为守恒机制。
- 阈值敏感性只重分类同一批事件，不改变传播机制。

## 场景汇总

| protocol_id | mechanism_id | runs | run_critical_rate_10pct | events | mean_event_size | p90_event_size | mean_final_active_credit | mean_repeat_default_share | mean_final_active_nodes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| high_risk_income_c020 | reference_period_end | 12 | 1.000 | 11974 | 16.860 | 23.000 | 72.667 | 0.988 | 200.000 |
| high_risk_income_c020 | check_only_b10 | 12 | 1.000 | 11974 | 16.860 | 23.000 | 72.667 | 0.988 | 200.000 |
| high_risk_income_c020 | flow_split_b10_check_q10 | 12 | 1.000 | 11991 | 19.264 | 25.000 | 36.000 | 0.990 | 200.000 |
| high_risk_income_c020 | flow_split_b10_check_q5 | 12 | 0.167 | 23806 | 10.038 | 14.000 | 35.500 | 0.990 | 200.000 |
| high_risk_income_c020 | flow_split_b10_check_q2 | 12 | 0.000 | 58016 | 4.203 | 6.000 | 32.083 | 0.990 | 200.000 |
| high_risk_income_c020 | flow_split_b10_check_q1 | 12 | 0.000 | 110602 | 2.210 | 3.000 | 25.333 | 0.990 | 200.000 |
| high_risk_income_c020 | recovery_50pct | 12 | 1.000 | 11982 | 17.093 | 23.000 | 57.250 | 0.988 | 200.000 |
| high_risk_income_c020 | recovery_90pct | 12 | 1.000 | 11983 | 17.027 | 22.000 | 75.000 | 0.988 | 200.000 |
| high_risk_income_c020 | keep_defaulted_assets | 12 | 0.917 | 10954 | 4.010 | 8.000 | 1294.833 | 0.946 | 200.000 |
| high_risk_income_c020 | permanent_exit | 12 | 0.000 | 1415 | 1.688 | 3.000 | 0.000 | 0.000 | 1.000 |
| high_risk_income_c020 | reset_to_initial_cash | 12 | 1.000 | 11574 | 18.802 | 45.000 | 2579.750 | 0.990 | 200.000 |
| boundary_fixed_k20 | reference_period_end | 12 | 1.000 | 11842 | 13.648 | 19.000 | 86.500 | 0.986 | 200.000 |
| boundary_fixed_k20 | check_only_b10 | 12 | 1.000 | 11842 | 13.648 | 19.000 | 86.500 | 0.986 | 200.000 |
| boundary_fixed_k20 | flow_split_b10_check_q10 | 12 | 1.000 | 11859 | 14.711 | 20.000 | 48.000 | 0.986 | 200.000 |
| boundary_fixed_k20 | flow_split_b10_check_q5 | 12 | 0.000 | 23344 | 7.644 | 10.000 | 35.583 | 0.987 | 200.000 |
| boundary_fixed_k20 | flow_split_b10_check_q2 | 12 | 0.000 | 55627 | 3.288 | 4.000 | 41.417 | 0.987 | 200.000 |
| boundary_fixed_k20 | flow_split_b10_check_q1 | 12 | 0.000 | 102718 | 1.776 | 2.000 | 39.750 | 0.987 | 200.000 |
| boundary_fixed_k20 | recovery_50pct | 12 | 1.000 | 11878 | 13.853 | 19.000 | 81.250 | 0.986 | 200.000 |
| boundary_fixed_k20 | recovery_90pct | 12 | 1.000 | 11879 | 13.842 | 19.000 | 86.250 | 0.986 | 200.000 |
| boundary_fixed_k20 | keep_defaulted_assets | 12 | 1.000 | 10368 | 3.624 | 7.000 | 1317.667 | 0.937 | 200.000 |
| boundary_fixed_k20 | permanent_exit | 12 | 0.000 | 1531 | 1.558 | 3.000 | 1490.667 | 0.000 | 1.250 |
| boundary_fixed_k20 | reset_to_initial_cash | 12 | 0.000 | 8228 | 2.150 | 4.000 | 2181.500 | 0.889 | 200.000 |

## 大崩塌阈值敏感性

| protocol_id | mechanism_id | threshold_fraction | run_critical_rate | event_critical_rate |
| --- | --- | --- | --- | --- |
| high_risk_income_c020 | reference_period_end | 0.050 | 1.000 | 0.890 |
| high_risk_income_c020 | reference_period_end | 0.100 | 1.000 | 0.339 |
| high_risk_income_c020 | reference_period_end | 0.200 | 0.000 | 0.000 |
| high_risk_income_c020 | flow_split_b10_check_q1 | 0.050 | 0.083 | 0.000 |
| high_risk_income_c020 | flow_split_b10_check_q1 | 0.100 | 0.000 | 0.000 |
| high_risk_income_c020 | flow_split_b10_check_q1 | 0.200 | 0.000 | 0.000 |
| high_risk_income_c020 | recovery_90pct | 0.050 | 1.000 | 0.907 |
| high_risk_income_c020 | recovery_90pct | 0.100 | 1.000 | 0.339 |
| high_risk_income_c020 | recovery_90pct | 0.200 | 0.000 | 0.000 |
| high_risk_income_c020 | permanent_exit | 0.050 | 0.000 | 0.000 |
| high_risk_income_c020 | permanent_exit | 0.100 | 0.000 | 0.000 |
| high_risk_income_c020 | permanent_exit | 0.200 | 0.000 | 0.000 |
| high_risk_income_c020 | reset_to_initial_cash | 0.050 | 1.000 | 0.567 |
| high_risk_income_c020 | reset_to_initial_cash | 0.100 | 1.000 | 0.391 |
| high_risk_income_c020 | reset_to_initial_cash | 0.200 | 1.000 | 0.165 |
| boundary_fixed_k20 | reference_period_end | 0.050 | 1.000 | 0.787 |
| boundary_fixed_k20 | reference_period_end | 0.100 | 1.000 | 0.092 |
| boundary_fixed_k20 | reference_period_end | 0.200 | 0.000 | 0.000 |
| boundary_fixed_k20 | flow_split_b10_check_q1 | 0.050 | 0.083 | 0.000 |
| boundary_fixed_k20 | flow_split_b10_check_q1 | 0.100 | 0.000 | 0.000 |
| boundary_fixed_k20 | flow_split_b10_check_q1 | 0.200 | 0.000 | 0.000 |
| boundary_fixed_k20 | recovery_90pct | 0.050 | 1.000 | 0.805 |
| boundary_fixed_k20 | recovery_90pct | 0.100 | 1.000 | 0.089 |
| boundary_fixed_k20 | recovery_90pct | 0.200 | 0.000 | 0.000 |
| boundary_fixed_k20 | permanent_exit | 0.050 | 0.250 | 0.002 |
| boundary_fixed_k20 | permanent_exit | 0.100 | 0.000 | 0.000 |
| boundary_fixed_k20 | permanent_exit | 0.200 | 0.000 | 0.000 |
| boundary_fixed_k20 | reset_to_initial_cash | 0.050 | 0.833 | 0.002 |
| boundary_fixed_k20 | reset_to_initial_cash | 0.100 | 0.000 | 0.000 |
| boundary_fixed_k20 | reset_to_initial_cash | 0.200 | 0.000 | 0.000 |

## 持续失效与非平稳性诊断

| protocol_id | mechanism_id | avalanche_active_macro_rate | wait_one_share | macro_event_size_lag1_corr | q1_mean_macro_event_size | q4_mean_macro_event_size | final_20pct_avalanche_active_rate | final_20pct_large_event_rate_per_macro |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| high_risk_income_c020 | reference_period_end | 0.998 | 0.998 | 0.696 | 10.425 | 19.620 | 1.000 | 0.525 |
| high_risk_income_c020 | flow_split_b10_check_q1 | 0.999 | 0.999 | 0.280 | 2.639 | 3.114 | 1.000 | 0.000 |
| high_risk_income_c020 | recovery_90pct | 0.999 | 0.999 | 0.667 | 11.023 | 19.592 | 1.000 | 0.521 |
| high_risk_income_c020 | permanent_exit | 0.118 | 0.379 | 0.063 | 1.797 | 1.000 | 0.000 | 0.000 |
| high_risk_income_c020 | reset_to_initial_cash | 0.965 | 0.968 | 0.862 | 3.039 | 42.035 | 1.000 | 0.999 |
| boundary_fixed_k20 | reference_period_end | 0.987 | 0.992 | 0.752 | 6.474 | 17.522 | 1.000 | 0.218 |
| boundary_fixed_k20 | flow_split_b10_check_q1 | 0.989 | 0.993 | 0.139 | 1.959 | 2.223 | 1.000 | 0.000 |
| boundary_fixed_k20 | recovery_90pct | 0.990 | 0.994 | 0.724 | 7.233 | 17.412 | 1.000 | 0.213 |
| boundary_fixed_k20 | permanent_exit | 0.128 | 0.336 | 0.051 | 1.659 | 1.000 | 0.003 | 0.000 |
| boundary_fixed_k20 | reset_to_initial_cash | 0.686 | 0.681 | -0.032 | 1.990 | 2.245 | 0.716 | 0.000 |

## 图表

- `batch_decoupling.png`：信贷驱动总量与结算/检查频率解耦。
- `clearing_mechanism_critical_rate.png`：各清算机制的 run 级大崩塌率。
- `repeat_default_share.png`：重复违约占比。
- `threshold_sensitivity.png`：大崩塌分类阈值敏感性。
- `selected_mechanism_ccdf.png`：选定机制的事件规模 CCDF。
- `temporal_quartile_event_size.png`：事件规模在运行时间四分位上的变化。

连续 Pareto alpha 仅保留为重尾初筛，不构成严格 SOC 或幂律证明。
