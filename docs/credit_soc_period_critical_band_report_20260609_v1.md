# period 粒度临界带细扫与 SOC 候选报告 v1

生成时间：2026-06-09 17:42 CST

## 1. 实验目标

粗网格扫描显示，`period_end` 协议下主要分为低风险区和持续失败/过载区。为了检验两者之间是否存在可观察 SOC 统计的临界带，本轮在相图边界附近进行更细的 `c` 扫描。

本报告只讨论 `period_end` 粒度。判定口径仍遵循项目证据阶梯：大级联、稳健转变、重尾、可信幂律、严格 SOC 需要逐级区分。

## 2. 扫描设计

第一阶段细扫：

- 目录：`results/credit_soc_period_critical_refined_20260609_v1/merged`
- 分析：`results/credit_soc_period_critical_refined_analysis_20260609_v1`
- 场景来源：从 2026-06-08 完备扫描中筛选非饱和转变带候选。
- 参数：12 个 base scenario，`c=center±0.10`，步长 `0.025`。
- 固定基线：`N=120`，每场景 24 个 seed，`max_periods=240`，`mean_initial_money=20`，`initial_income_per_capita=5`，大级联阈值 `10%N`，`continue_after_avalanche`，`period_end`。
- 规模：100 个场景、2400 个 run、441278 个 avalanche/event。

第二阶段窄带复核：

- 目录：`results/credit_soc_period_critical_stage2_20260609_v1/merged_exact_c`
- 分析：`results/credit_soc_period_critical_stage2_exact_analysis_20260609_v1`
- 目标带 1：`high_both=(a=0.04,b=0.40)`，`c=0.450..0.600`，步长 `0.005`。
- 目标带 2：`high_wealth=(a=0.04,b=0.20)`，`c=0.675..0.800`，步长 `0.005`。
- 固定机制：`uniform` 收入、`random` 增长、`complete` 拓扑，本金分布为 `equal/normal/pareto`。
- 固定基线：同第一阶段。
- 规模：171 个精确 `c` 场景、4104 个 run、555638 个 avalanche/event。

第二阶段运行后发现旧版 `run_comprehensive_scenario_scan.py` 的 `scenario_id` 只保留两位小数，可能把 `0.450/0.455` 这类细网格点折叠。已用原始 `investment_income_propensity` 重建三位小数 `scenario_id`，并将脚本修正为三位小数。报告只引用 `merged_exact_c` 结果。

## 3. 第一阶段发现

第一阶段自动快筛出现 18 个 `period_end` 候选，而此前粗网格快筛为 0。这说明中间转变带确实会被粗步长漏掉。

![第一阶段 SOC 快筛相图](../results/credit_soc_period_critical_refined_analysis_20260609_v1/global_soc_screen_phase_map.png)

![第一阶段候选 CCDF](../results/credit_soc_period_critical_refined_analysis_20260609_v1/top_candidate_ccdf_grid.png)

但第一阶段候选混有两类场景：

- `biased` 收入、高支出场景：大事件率高，但 event occupancy 往往接近过载区，仍有持续失败风险。
- `uniform` 收入、`complete` 拓扑、`random` 增长场景：大事件率较低，但传播新增占比高，事件分布更接近非饱和候选。

因此第二阶段只聚焦后一类非饱和候选族。

## 4. 第二阶段候选带

第二阶段精确分析的自动快筛候选数为 74，其中 3 个点达到 6/6 分。

![第二阶段 SOC 快筛相图](../results/credit_soc_period_critical_stage2_exact_analysis_20260609_v1/global_soc_screen_phase_map.png)

![第二阶段 c-CCDF](../results/credit_soc_period_critical_stage2_exact_analysis_20260609_v1/ccdf_by_c.png)

![第二阶段候选 CCDF](../results/credit_soc_period_critical_stage2_exact_analysis_20260609_v1/top_candidate_ccdf_grid.png)

最高分候选如下：

| c | 本金 | 支出机制 | event occupancy | 大事件率 | 平均事件规模 | p99 | 最大规模 | 传播新增占比 | alpha | bootstrap p | bounded p |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.590 | equal | high_both | 0.7884 | 0.0205 | 3.5732 | 13 | 25 | 0.4333 | 7.6678 | 0.3333 | 0.3810 |
| 0.770 | normal | high_wealth | 0.7891 | 0.0207 | 3.4359 | 13 | 26 | 0.4290 | 7.0888 | 0.8095 | 0.7619 |
| 0.780 | equal | high_wealth | 0.7962 | 0.0275 | 3.7072 | 14 | 33 | 0.4521 | 6.3323 | 0.3333 | 0.2857 |

这些点周围存在连续候选带，而非单点偶然：

- `high_both`：`c≈0.56..0.59`，`equal/normal/pareto` 本金下均出现非饱和候选。
- `high_wealth`：`c≈0.74..0.78`，`equal/normal/pareto` 本金下均出现非饱和候选。

## 5. 判定

可以说：本轮在 `period_end` 粒度下找到了临界候选带。它们具有以下特征：

- event occupancy 尚未达到持续失败区，约为 `0.56..0.80`。
- 大事件率约为 `0.01..0.03`，不是每期都大崩塌。
- 传播新增违约占比较高，约为 `0.40..0.45`，说明不是纯同步初始违约。
- 尾部拟合没有被指数或 lognormal 显著压倒，部分点 bootstrap p 较高。

但不能说：严格 SOC 已经被证明。主要限制是：

- 这些点仍需要外部参数 `c` 的窄带调节，更像调参临界带，而不是无调参自组织临界。
- event occupancy 已接近 `0.8`，临界带上沿离持续失败区很近。
- 拟合 alpha 较高，尾部衰减较陡；最大事件规模仍为 `25..33/120`，尚未展示真正跨尺度幂律。
- 尚未做 `N` 扩展、截止尺度随系统尺寸变化、长时平稳性和机制消融。

因此，本轮结论应写为：**period 粒度下存在值得继续验证的 SOC 候选临界带；当前证据支持“调参临界候选/过载边界附近重尾”，但尚不足以提升为严格 SOC。**
