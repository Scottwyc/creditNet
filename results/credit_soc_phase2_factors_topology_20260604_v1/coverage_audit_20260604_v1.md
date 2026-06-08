# Phase-2 因素与显式拓扑最终覆盖审计 v1

审计完成时间：2026-06-04 13:05:33 CST

## 审计对象

- `project.md`
- `src/creditnet/simulation.py`
- `src/creditnet/phase2_topology.py`
- `scripts/run_phase2_factor_topology_sweeps.py`
- `scripts/analyze_phase2_factor_topology.py`
- `run_summary.csv`
- `avalanche_events.csv`
- `scenario_summary.csv`
- `topology_instances.csv`
- `first_run_histories.json`
- `metadata.json`
- `docs/credit_soc_phase2_factors_topology_report_20260604_v1.md`

## project.md 覆盖结论

| 因素 | 协议覆盖 | 可识别结论 | 主要限制 |
| --- | --- | --- | --- |
| 初始本金 | equal/uniform/normal/lognormal/pareto | 首次 avalanche、级联严重度、最终 Gini | 没有大 avalanche；实际总现金未逐 run 匹配 |
| 收入分配 | uniform/biased | 传播规模、首次 avalanche、最终 Gini | 没有大 avalanche；仅两种规则 |
| `a/b` | 3×3 温和网格 | 固定 K 下的现金流/级联差异 | 没有大 avalanche；固定 K 切断收入到下一期 K 的反馈 |
| 增长规则 | random/preferential_debt | 两种实际有向暴露增长规则的差异 | 未覆盖其余规则；未做配对 seed |
| 显式拓扑 | ER/BA-derived/SW，平均度 6/12/24 | 匹配平均度家族比较、固定 N 密度比较、结构量关系 | BA 有匹配边数补边；SW 仅 p=0.10；未做跨 N 固定密度 |

五类请求因素均有实验覆盖，但只有 3 个 event 达到 10% 大 avalanche 阈值。多数场景无法识别 `project.md` 定义的阈值临界信贷规模，只能比较首次 avalanche 前信贷规模和级联严重度。

## 独立结果对账

从原始文件重新计算并确认：

| 检查项 | 结果 |
| --- | --- |
| factor-family 单元 | 31 |
| 唯一参数配置 | 25 |
| 每单元 run 数 | 全部为 8 |
| 总 run 数 | 248 |
| 总 event 数 | 51,401 |
| `sum(avalanche_count)` 是否等于 event 行数 | 是 |
| 逐 run 最大 event / critical flag 是否与事件表一致 | 是 |
| 完成 240 period 的 run | 248/248 |
| 固定 K=20 是否全程成立 | 是 |
| 初始/最终现金不一致 | 0 |
| 机会图边数/目标平均度不一致 | 0 |
| 密度公式不一致 | 0 |
| 首 run 历史数与长度 | 31 个场景，全部 240 行 |
| 历史现金总量不守恒 | 0 |
| 10% 阈值大 avalanche | 3 |

3 个阈值事件：

| factor family | 场景 | seed | period | 阈值事件前活跃信贷 | collapse size |
| --- | --- | ---: | ---: | ---: | ---: |
| topology_degree | BA-derived，平均度 24，random | 2026060444 | 168 | 808 | 20 |
| topology_growth | BA-derived，平均度 12，random | 2026060622 | 226 | 666 | 23 |
| topology_growth | SW，平均度 12，random | 2026060633 | 236 | 531 | 20 |

## 审计发现与修正

1. 原文件名 `critical_credit_by_topology.png` 实际画的是 `mean_first_cascade_credit`，不是阈值临界信贷规模。分析脚本和正式报告已改用 `first_cascade_credit_by_topology.png`；旧文件保留但不再作为阈值证据。
2. 31 个 `scenario_id` 是 factor-family 单元，只有 25 组唯一参数配置；共同基准在不同 family 中用独立种子重复。
3. 场景之间没有共享 run seed 或 topology seed，因此不是配对消融，小样本差异只能作描述性比较。
4. 本金分布共享目标人均值 20，但实际总现金没有逐 run 匹配。正式本金扫描平均总现金为 equal 4000.0、uniform 3960.9、normal 3983.8、lognormal 4138.3、pareto 3998.6。
5. uniform 收入并未消除初始违约：8 个 run 中 6 个发生违约，共 7 个 event；但所有 event 规模均为 1，因此没有观察到传播。
6. random 规则下 event 前平均有向关系数高于 preferential_debt，但债务/贷款能力集中度没有直接记录；正式报告已删除把规则含义写成实测集中度的表述。
7. 固定 `K=20` 下元数据中的 `investment_income_propensity=0.20` 不参与 period 长度，`a/b` 结果不含收入反馈改变下一期 K 的效应。
8. BA 为匹配边数后的 BA-derived graph，SW 只覆盖 `rewire_probability=0.10`。
9. 结构相关的 p 值未控制拓扑家族、实际总现金或多重比较，只保留为探索性证据。

## 最终结论边界

当前可以说：

- biased 收入相对 uniform 收入观察到更早、更频繁且更大的 avalanche；
- random 相对 preferential_debt 观察到更大的 avalanche 和更广的 event 条件有向关系覆盖；
- equal 本金观察到更晚的首次 avalanche，lognormal 本金观察到更大的级联和最终 Gini；
- 匹配平均度后 ER/BA-derived/SW 的家族差异小于收入和增长规则的描述性差异；
- 平均度与最大 avalanche 有弱探索性正相关。

当前不能说：

- 已识别所有因素的阈值临界信贷规模；
- 已证明严格 SOC 或幂律；
- 已得到长期稳态拓扑排序；
- 已获得配对种子、严格总现金控制下的因果效应；
- BA、SW 或更高密度普遍必然更危险。

最终复核：代码语法、原始 run/event/history/topology 对账、正式报告六张图链接与覆盖术语检查均通过。
