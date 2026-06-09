# 信贷网络自组织临界完整实验报告 v1

生成时间：2026-06-09 16:13 CST

## 1. 报告定位

本报告基于 [`project.md`](../project.md) 的模型框架，整合当前已经完成的两条主实验线：

1. `period_end` 完备场景扫描：在期末统一做流量结算、违约检查和级联清算。
2. `timestep_settle_check` 对照扫描：在每个 credit `time_step` 后立即做缩放微结算、违约检查和级联清算。

报告目标不是只列出扫描变量，而是把模型机制、固定参数基线、扫描轴、级联失效相图、SOC 判定、timestep 对照和动画可视化统一放在一个完整实验叙述中。

核心结论是：

- `period_end` 粒度下，系统存在清楚的级联失效过载相图；高 `c`、高支出、biased 收入和部分高连接/异质拓扑会显著放大级联。
- `timestep` 粒度下，原先的期末大崩塌被切碎为高频、小规模 avalanche；出现小尺度重尾/近幂律样貌，但没有达到 `10%N` 的大级联。
- 当前证据支持“级联失效/过载转变”和“机制敏感的小尺度重尾”，但不支持严格自组织临界（SOC）。

## 2. 模型框架

系统是一个由个体组成的带权有向信贷暴露网络。每个主体有现金、贷款资产、债务负债和净资产：

```text
W_i = cash_i + loan_assets_i - debt_liabilities_i
```

每个成功 credit `time_step` 新增 1 单位有向信贷暴露。若 `i` 向 `j` 贷款 1 单位，则 `i` 的现金减少 1、贷款资产增加 1；`j` 的现金增加 1、债务负债增加 1。信贷建立本身保持双方净资产不变，违约主要来自后续支出、收入分配和清算减记。

宏观期长度由收入内生决定：

```text
K_t = round(c * Y_(t-1))
```

其中 `c` 是上一期总收入到下一期计划信贷尝试数的转换系数，不是单笔贷款规模，也不是实际投资支出比例。每个成功 `time_step` 的单位信贷规模始终为 1。

违约阈值为严格负净资产：

```text
default_i = 1(W_i < 0)
```

一次 avalanche 的规模定义为本次清算中被处理的不同违约节点数：

```text
collapse_size = initial_default_count + propagated_default_count
collapse_fraction = collapse_size / N
critical_event = 1(collapse_fraction >= 0.10)
```

`critical_event` 只是人工大级联标签，不是严格临界或 SOC 证明。

## 3. 拓扑口径

显式拓扑变量 `er/ba/sw` 表示交易机会图，不表示初始化时已经存在的信贷暴露网络。

- 初始化时，实际信贷暴露矩阵为空。
- `er/ba/sw` 先生成一张无向“允许交易机会图”。
- 后续每个 credit `time_step` 新增信贷时，只能在机会图允许的节点对之间发生。
- 实际信贷暴露是有向、带权、可重复累积的；方向由当次贷款人与借款人决定。
- `complete` 表示不施加额外机会边界，任意两主体都可成为候选对手方。

因此，拓扑实验考察的是“谁可以和谁发生后续信贷关系”的机会边界，而不是给定一张静态信贷网络让它直接失效。

## 4. 实验设计

### 4.1 扫描轴

两轮主扫描使用相同的场景轴：

| 轴 | 取值 |
| --- | --- |
| `c` | `0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80` |
| 初始本金分布 | `equal, uniform, normal, lognormal, pareto` |
| 收入分配规则 | `uniform, biased` |
| 信贷增长规则 | `random, preferential_debt` |
| 支出机制 `(a,b)` | `low=(0.01,0.10)`、`baseline=(0.02,0.20)`、`high_income=(0.02,0.40)`、`high_wealth=(0.04,0.20)`、`high_both=(0.04,0.40)` |
| 交易机会拓扑 | `complete`；`er/ba/sw` 的目标平均度 `k=6,12,24` |

### 4.2 固定参数基线

`period_end` 完备扫描的固定基线：

| 固定项 | 取值 |
| --- | --- |
| 节点数 | `N=120` |
| 独立重复 | 每个 scenario `3` 个 seed/run |
| 单 run 长度 | `max_periods=120`，`max_time_steps=0` |
| 初始本金规模 | `mean_initial_money=20.0` |
| 初始参考收入 | `initial_income_per_capita=5.0`，即 `Y_0=600` |
| period 长度 | `K_t=round(c*Y_(t-1))` |
| 违约阈值 | `default_threshold=0.0` |
| 大级联阈值 | `collapse_threshold_fraction=0.10`，即至少 12 个节点 |
| 清算与恢复 | `wipe_defaulted_assets=True`，`continue_after_avalanche` |
| 检查粒度 | `period_end` |
| 会计校验 | `validate_accounting=True` |

`timestep_settle_check` 对照扫描的固定基线：

| 固定项 | 取值 |
| --- | --- |
| 节点数 | `N=120` |
| 独立重复 | 每个 scenario `1` 个 seed/run |
| 单 run 长度 | `max_periods=20`，`max_time_steps=0` |
| 单 period 微步上限 | `max_period_length_steps=500` |
| 初始本金规模 | `mean_initial_money=20.0` |
| 初始参考收入 | `initial_income_per_capita=5.0`，即 `Y_0=600` |
| period 长度 | `K_t=round(c*Y_(t-1))`，实际执行 `min(K_t,500)` |
| 微结算 | 每个 credit `time_step` 后按 `1/K_t` 缩放结算、检查和清算 |
| 违约阈值 | `default_threshold=0.0` |
| 大级联阈值 | `collapse_threshold_fraction=0.10`，即至少 12 个节点 |
| 清算与恢复 | `wipe_defaulted_assets=True`，`continue_after_avalanche` |
| 检查粒度 | `timestep_settle_check` |
| 会计校验 | 正式 v2 为加速设置 `validate_accounting=False`；小样本 smoke test 已校验通过 |

## 5. period_end 完备扫描结果

原始扫描目录：`results/credit_soc_comprehensive_scan_20260608_v1/`  
分析目录：`results/credit_soc_comprehensive_scan_analysis_20260608_v1/`

规模：

- `8000` 个 scenario；
- `24000` 个 run；
- `1915216` 个 avalanche 事件。

按 `c` 聚合的相图骨架：

| c | 平均大级联率 | 平均事件规模占比 | 平均事件占用率 | 近饱和场景数/1000 |
| ---: | ---: | ---: | ---: | ---: |
| 0.10 | 0.0001 | 0.0094 | 0.1913 | 43 |
| 0.20 | 0.0371 | 0.0195 | 0.3720 | 194 |
| 0.30 | 0.1177 | 0.0372 | 0.5324 | 359 |
| 0.40 | 0.2124 | 0.0641 | 0.6655 | 527 |
| 0.50 | 0.3251 | 0.1075 | 0.7798 | 653 |
| 0.60 | 0.5026 | 0.1652 | 0.8710 | 804 |
| 0.70 | 0.6153 | 0.2133 | 0.9332 | 897 |
| 0.80 | 0.7576 | 0.2637 | 0.9749 | 966 |

![period_end 全局级联相图](../results/credit_soc_comprehensive_scan_analysis_20260608_v1/global_cascade_phase_map.png)

![period_end 按收入分配](../results/credit_soc_comprehensive_scan_analysis_20260608_v1/cascade_phase_by_income_rule.png)

![period_end 按支出机制](../results/credit_soc_comprehensive_scan_analysis_20260608_v1/cascade_phase_by_spending.png)

![period_end 按拓扑](../results/credit_soc_comprehensive_scan_analysis_20260608_v1/cascade_phase_by_topology.png)

主要解释：

- `c` 是最强控制轴。高 `c` 同时意味着更多计划信贷尝试和更大的期末批量结算窗口。
- biased 收入显著放大级联，因为收入继续向高净资产主体集中，弱主体更容易进入负净资产。
- 高支出机制提高资产负债表压力，使违约更早、更频繁发生。
- 拓扑会改变传播路径和风险集中方式，但在 `period_end` 粗粒度批量结算下不是唯一主导因素。
- 高风险区表现为事件占用率接近 1 的持续过载，不是稀疏、平稳的 SOC avalanche。

## 6. period_end 的 SOC 快筛

SOC 快筛 gate 情况：

| gate | 通过场景数 | 通过率 |
| --- | ---: | ---: |
| 事件数足够 | 6736 | 0.8420 |
| 非饱和占用 | 3557 | 0.4446 |
| 处于转变区 | 1365 | 0.1706 |
| 传播新增占比足够 | 2641 | 0.3301 |
| 尾部幂律诊断可接受 | 81 | 0.0101 |
| 替代分布没有更优 | 1 | 0.0001 |
| 快速 SOC 候选 | 0 | 0.0000 |

![period_end SOC 快筛相图](../results/credit_soc_comprehensive_scan_analysis_20260608_v1/global_soc_screen_phase_map.png)

![period_end 级联规模 CCDF](../results/credit_soc_comprehensive_scan_analysis_20260608_v1/ccdf_by_c.png)

![period_end 高分候选 CCDF](../results/credit_soc_comprehensive_scan_analysis_20260608_v1/top_candidate_ccdf_grid.png)

解释：

- 看到重尾或局部幂律拟合不拒绝，不足以推出 SOC。
- 许多高风险场景同时存在高占用、重复违约、期末同步初始违约和替代分布更优的问题。
- 因此，period_end 扫描支持级联失效相图和过载转变，不支持严格 SOC 相图存在稳定临界带。

## 7. timestep 对照结果

扫描目录：`results/credit_soc_timestep_scan_20260609_v2/merged/`  
分析目录：`results/credit_soc_timestep_scan_analysis_20260609_v2/`

规模：

- `8000` 个 scenario；
- `8000` 个 run；
- `4539260` 个 timestep avalanche 事件。

按 `c` 聚合的结果：

| c | 平均大级联率 | 平均事件规模占比 | timestep 事件率 | period 占用率 | 平均重复违约占比 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.10 | 0 | 0.00551 | 0.01965 | 0.18095 | 0.14154 |
| 0.20 | 0 | 0.00696 | 0.02543 | 0.35295 | 0.21146 |
| 0.30 | 0 | 0.00778 | 0.03736 | 0.53265 | 0.29679 |
| 0.40 | 0 | 0.00826 | 0.05684 | 0.68445 | 0.37950 |
| 0.50 | 0 | 0.00862 | 0.08973 | 0.80815 | 0.48701 |
| 0.60 | 0 | 0.00877 | 0.12442 | 0.88720 | 0.58486 |
| 0.70 | 0 | 0.00886 | 0.15293 | 0.94325 | 0.66819 |
| 0.80 | 0 | 0.00890 | 0.17019 | 0.96325 | 0.71677 |

![period/timestep 协议对比](../results/credit_soc_timestep_scan_analysis_20260609_v2/protocol_compare_by_c.png)

![同场景协议散点对比](../results/credit_soc_timestep_scan_analysis_20260609_v2/protocol_scenario_scatter.png)

![timestep 全局级联相图](../results/credit_soc_timestep_scan_analysis_20260609_v2/global_cascade_phase_map.png)

主要解释：

- timestep 协议下所有场景的大级联率均为 0，最大事件规模为 `10/120=0.0833`，低于 10%N 阈值。
- 高 `c` 仍会提高事件频率、period 占用率和重复违约占比，但不再产生 period_end 下的大规模同步崩塌。
- 这说明 period_end 大崩塌显著依赖期末批量结算窗口。

## 8. timestep 的尾部和 SOC 快筛

SOC gate 情况：

| gate | 通过场景数 | 通过率 |
| --- | ---: | ---: |
| 事件数足够 | 4758 | 0.5948 |
| 非饱和 | 7958 | 0.9948 |
| 处于转变区 | 0 | 0.0000 |
| 传播新增占比足够 | 150 | 0.0188 |
| 尾部幂律诊断可接受 | 146 | 0.0183 |
| 替代分布没有更优 | 131 | 0.0164 |
| 规模范围达标 | 0 | 0.0000 |
| 快速 SOC 候选 | 0 | 0.0000 |

![timestep SOC 快筛相图](../results/credit_soc_timestep_scan_analysis_20260609_v2/global_soc_screen_phase_map.png)

![timestep 级联规模 CCDF](../results/credit_soc_timestep_scan_analysis_20260609_v2/ccdf_by_c.png)

![timestep 小尺度候选 CCDF](../results/credit_soc_timestep_scan_analysis_20260609_v2/top_candidate_ccdf_grid.png)

解释：

- timestep 下确实出现小尺度重尾/近幂律样貌；有 28 个“小尺度尾部候选”。
- 但这些候选没有跨过 10%N 尺度门槛，最大事件规模仍低于大级联阈值。
- 当前证据更适合表述为“高频小 avalanche 的小尺度重尾”，不能直接表述为严格 SOC。

## 9. 动画可视化

动画输出目录：`results/credit_soc_visual_evolution_20260609_v1/`  
渲染脚本：`scripts/render_creditnet_evolution_animations.py`

动画读法：

- 边表示活跃信贷暴露，越粗/越深表示权重越高。
- 节点颜色表示净资产，节点大小表示债务压力。
- 红/橙节点表示当前或新增违约节点。
- 红色高亮边表示当前级联清算波次中被减记影响的债权边。

### 9.1 period_end 批量结算过载

![period_end_overload.gif](../results/credit_soc_visual_evolution_20260609_v1/period_end_overload.gif)

![period_end_overload_keyframes.png](../results/credit_soc_visual_evolution_20260609_v1/period_end_overload_keyframes.png)

该场景使用 `N=40`、`c=0.90`、lognormal 本金、biased 收入、preferential_debt 和高支出压力。第一期累计 216 次单位信贷尝试后，在期末统一结算和检查。结果出现 13 个同步初始违约，总清算规模为 20/40，达到 50%。动画显示了 period_end 大崩塌的批量结算放大效应。

### 9.2 timestep 微步结算小 avalanche

![timestep_micro_tail.gif](../results/credit_soc_visual_evolution_20260609_v1/timestep_micro_tail.gif)

![timestep_micro_tail_keyframes.png](../results/credit_soc_visual_evolution_20260609_v1/timestep_micro_tail_keyframes.png)

该场景使用 `N=60`、`c=0.80`、lognormal 本金、biased 收入、preferential_debt，并在每个微步后结算检查。12 个 period、1440 个 micro step 中出现 191 次 avalanche，但最大规模只有 4/60，没有大级联。动画显示了高频小事件如何替代 period_end 下的宏观大崩塌。

### 9.3 低驱动安静对照

![quiet_low_drive.gif](../results/credit_soc_visual_evolution_20260609_v1/quiet_low_drive.gif)

![quiet_low_drive_keyframes.png](../results/credit_soc_visual_evolution_20260609_v1/quiet_low_drive_keyframes.png)

该场景使用 `N=40`、`c=0.10`、equal 本金、uniform 收入和 random 增长。20 个 period 内只完成 40 次信贷尝试，没有出现违约或 avalanche。它说明低驱动下信贷网络可以缓慢增强而不进入持续失败状态。

## 10. 综合结论

本项目当前证据层级应写为：

```text
大级联出现 < 稳健级联转变 < 重尾 < 统计上可信的幂律 < 严格 SOC
```

综合两轮扫描和动画可视化，结论如下：

1. **级联失效相图成立**：`period_end` 粒度下，系统随 `c`、支出强度、收入分配偏置和本金/拓扑结构出现清晰的过载转变。
2. **period_end 大崩塌有批量结算依赖**：期末统一结算会聚合同步初始违约和传播清算，显著放大单次事件规模。
3. **timestep 粒度下大级联消失**：同一 8000 场景轴改为微步结算后，没有任何场景达到 10%N 大级联阈值。
4. **timestep 下有小尺度重尾/近幂律现象**：部分场景在小 avalanche 范围内具有尾部候选，但尺度范围不足，不能提升为严格 SOC。
5. **严格 SOC 当前不成立**：没有场景同时通过非饱和、转变区、传播占比、尾部可信、替代分布不过强和尺度范围门槛。

## 11. 边界与后续工作

当前报告的边界：

- `period_end` 完备扫描覆盖广，但仍是每 scenario 3 个 seed、120 periods 的相图筛查。
- `timestep` 对照是快速全景 v2：每 scenario 1 个 seed、20 periods、单期最多 500 微步。
- 动画是小规模代表性重跑，用于机制解释，不是新增严格统计证明。

后续若要继续检验 timestep 尺度的 SOC，应优先做：

1. 对 28 个小尺度尾部候选做多 seed、长时、无上限或更高 `max_period_length_steps` 复核。
2. 做 `N=120/240/500` 的有限尺寸标度，检查尾部 cutoff 是否随 `N` 扩展。
3. 明确拆分 `initial_default_count`、`propagated_default_count` 和 repeated defaults。
4. 比较 period_end、固定批次结算、timestep 结算在同一强度下的机制鲁棒性。

在当前证据下，最稳妥的表述是：该信贷网络模型存在机制敏感的级联失效和过载转变；timestep 尺度出现小 avalanche 重尾现象；但严格自组织临界尚无支持证据。
