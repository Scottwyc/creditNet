# 信贷网络 SOC 关键结果看板

- 更新时间：2026-06-09 13:30:00 CST
- 项目目标：确认当前信贷网络约束下是否存在严格自组织临界，并量化 `project.md` 各关注因素对级联的影响。
- 权威状态依据：[第二阶段关键总结](credit_soc_phase2_summary_20260604_v1.md)与[持续跟进日志](credit_soc_autonomous_followup_20260604_v2.md)
- 状态词：已完成 / 边界完成 / 进行中 / 待推进

## 目标总览

| Target | 状态 | 最新结论 | 关键结果文档 | 关键结果目录 | 正在进行 | 下一 gate |
| --- | --- | --- | --- | --- | --- | --- |
| 模型框架与变量口径 | 已完成 | `c` 是上一期总收入到下一期计划信贷尝试批量的转换系数；级联失效、事件内部初始/传播拆分、大级联标签和严格 SOC 证据门槛已逐项定义。 | [级联与 SOC 口径说明](credit_soc_cascade_soc_definitions_20260608.md) / [变量审计详细报告 v3](credit_soc_project_framework_detailed_analysis_20260604_v3.md) / [Word v3](credit_soc_project_framework_detailed_analysis_20260604_v3.docx) | [框架分析结果](../results/credit_soc_project_framework_analysis_20260604_v1/) | 无 | 仅在模型变量新增或语义变化时刷新 |
| `project.md` 因素与显式拓扑 | 已完成 | biased 收入、lognormal 本金和 random 增长显著放大级联；匹配平均度后 ER/BA/SW 家族差异较弱，密度效应较小。 | [因素与拓扑报告](credit_soc_phase2_factors_topology_report_20260604_v1.md) | [因素与拓扑结果](../results/credit_soc_phase2_factors_topology_20260604_v1/) | 无 | 已纳入最终综合报告 |
| Avalanche 动态与时间分离 | 已完成 | 单次事件内部传播通常亚临界；continue 协议长期趋向近连续、强相关、低信贷的持续失败状态，不能把 pooled events 当作独立 SOC avalanche。 | [动态报告](credit_soc_phase2_dynamics_report_20260604_v1.md) | [动态结果](../results/credit_soc_phase2_dynamics_20260604_v1/) | 无 | 已通过最终方法审计 |
| 检查频率、清算、恢复与退出机制 | 已完成 | 高频检查主要碎片化事件；重复违约与持续失败对检查频率和现金受限回收稳健。永久退出通过耗尽主体停止事件，reset 引入外部现金。 | [机制稳健性报告](credit_soc_phase2_mechanism_report_20260604_v1.md) | [机制稳健性结果](../results/credit_soc_phase2_mechanism_20260604_v1/longrun_20260604_1244_r2/) | 无 | 已通过 paired 对照与现金恒等式审计 |
| 严格尾部与有限尺寸 SOC 证据 | 已完成 | 最终 v5 中无界离散幂律 26/39 不拒绝、13/39 拒绝，但指数不普适、替代分布常更优，且有限尺寸增长主要由同步初始违约的广延增长主导。 | [严格 SOC 报告 v1](credit_soc_phase2_strict_soc_report_20260604_v1.md) | [严格 SOC v5](../results/credit_soc_phase2_strict_soc_20260604_v1/analysis_final_v5/) | 无 | 已纳入最终判定 |
| 低驱动长期平稳性候选搜索 | 已完成 | 42 场景、504 runs、100.8 万 periods 中没有场景通过 SOC 候选门槛；6 个低驱动场景稀疏但非平稳，36 个场景漂移或持续失败。 | [长期平稳性报告](credit_soc_phase2_stationarity_search_report_20260604_v1.md) | [长期平稳性结果](../results/credit_soc_phase2_stationarity_search_20260604_v1/) | 无 | `candidate_count=0`，无需追加有限尺寸候选验证 |
| 完备场景扫描与相图 | 已完成 | 覆盖本金、支出、收入分配、增长规则、显式拓扑和 `c=0.10..0.80` 的 8000 scenarios/24000 runs。级联失效相图显示清楚过载转变；SOC 快筛候选数为 0。 | [完备场景扫描报告 v1](credit_soc_comprehensive_parameter_scan_report_20260608_v1.md) / [Word v1](credit_soc_comprehensive_parameter_scan_report_20260608_v1.docx) | [相图分析结果](../results/credit_soc_comprehensive_scan_analysis_20260608_v1/) | 无 | 若需推进，只对边界高分场景做有限尺寸和长时复核 |
| timestep 尺度 SOC 对照 | 已完成 | 同一 8000 场景轴改为每个 credit time_step 后微结算/检查/清算；v2 为 `1 seed × 20 periods`、每宏观期最多 500 微步。4,539,260 个事件中无 10%N 大级联，最大事件 10/120；严格 SOC 快候选数为 0，仅有 28 个小尺度尾部候选。 | [timestep SOC 对照报告 v2](credit_soc_timestep_soc_counterfactual_report_20260609_v2.md) / [Word v2](credit_soc_timestep_soc_counterfactual_report_20260609_v2.docx) | [timestep 对照分析结果](../results/credit_soc_timestep_scan_analysis_20260609_v2/) | 无 | 若需严格确认，需对少数小尺度尾部候选做多 seed、长时、无/高 cap 与有限尺寸复核 |
| 当前约束下最终 SOC 判定 | 已完成 | 当前已实现 baseline、已扫描参数邻域和已测机制下，严格 SOC 不存在（经验判定）；存在级联交叉和机制敏感重尾，高风险状态是非平稳持续失败/过载吸引子。 | [最终综合报告](credit_soc_phase2_comprehensive_report_20260604_v1.md) / [最终 Word](credit_soc_phase2_comprehensive_report_20260604_v1.docx) / [完成性审计](credit_soc_phase2_completion_audit_20260604_v1.md) | [最终综合结果](../results/credit_soc_phase2_comprehensive_20260604_v1/) | 无 | 当前项目目标已完成 |

## 正在进行

| Target/分支 | Owner | 当前进展 | 预期产物 | 下一关键检查 |
| --- | --- | --- | --- | --- |
| 严格 SOC 最终方法修正 | `strict-soc-evidence` | 已完成并关闭 | [严格 SOC 报告](credit_soc_phase2_strict_soc_report_20260604_v1.md)与[方法审计](../results/credit_soc_phase2_strict_soc_20260604_v1/method_audit_final_v4.md) | 无 |
| 低驱动长期平稳性搜索 | `stationarity-search` | 已完成并关闭，0/42 SOC 候选 | [长期平稳性报告](credit_soc_phase2_stationarity_search_report_20260604_v1.md) | 无 |
| 综合证据集成 | 主协调器 | 已完成最终图文 Markdown、Word 和完成性审计 | [最终综合报告](credit_soc_phase2_comprehensive_report_20260604_v1.md) / [完成性审计](credit_soc_phase2_completion_audit_20260604_v1.md) | 无 |

## 术语口径

- [级联失效与 SOC 判定口径说明 v1](credit_soc_cascade_soc_definitions_20260608.md)
- 当前 `critical_event` 是 `collapse_size/N >= collapse_threshold_fraction` 的人工大级联标签，不是临界证明。
- 严格 SOC 必须同时满足无需精细调参、慢驱动/快清算分离、长期统计稳定、事件定义可解释、可信尾部统计、有限尺寸相容和机制稳健性。

## 关键结果索引

### 面向外部读者的报告

- [最终综合证据报告 v1](credit_soc_phase2_comprehensive_report_20260604_v1.md)
- [timestep尺度 SOC 对照实验报告 v2](credit_soc_timestep_soc_counterfactual_report_20260609_v2.md) / [Word v2](credit_soc_timestep_soc_counterfactual_report_20260609_v2.docx)
- [完备场景扫描与 SOC 相图报告 v1](credit_soc_comprehensive_parameter_scan_report_20260608_v1.md)
- [完备场景扫描与 SOC 相图 Word v1](credit_soc_comprehensive_parameter_scan_report_20260608_v1.docx)
- [级联失效与 SOC 判定口径说明 v1](credit_soc_cascade_soc_definitions_20260608.md)
- [最终综合证据 Word v1](credit_soc_phase2_comprehensive_report_20260604_v1.docx)
- [最终完成性审计 v1](credit_soc_phase2_completion_audit_20260604_v1.md)
- [模型框架与变量口径详细报告 v3](credit_soc_project_framework_detailed_analysis_20260604_v3.md)
- [低驱动长期平稳性报告](credit_soc_phase2_stationarity_search_report_20260604_v1.md)
- [严格 SOC 证据报告 v1](credit_soc_phase2_strict_soc_report_20260604_v1.md)
- [Avalanche 动态报告](credit_soc_phase2_dynamics_report_20260604_v1.md)
- [机制稳健性报告](credit_soc_phase2_mechanism_report_20260604_v1.md)
- [因素与显式拓扑报告](credit_soc_phase2_factors_topology_report_20260604_v1.md)

### 核心结果目录

- [最终综合结果](../results/credit_soc_phase2_comprehensive_20260604_v1/)
- [低驱动长期平稳性结果](../results/credit_soc_phase2_stationarity_search_20260604_v1/)
- [严格 SOC 结果](../results/credit_soc_phase2_strict_soc_20260604_v1/)
- [Avalanche 动态结果](../results/credit_soc_phase2_dynamics_20260604_v1/)
- [机制稳健性结果](../results/credit_soc_phase2_mechanism_20260604_v1/longrun_20260604_1244_r2/)
- [因素与显式拓扑结果](../results/credit_soc_phase2_factors_topology_20260604_v1/)
- [完备场景扫描相图分析结果](../results/credit_soc_comprehensive_scan_analysis_20260608_v1/)
- [timestep SOC 对照分析结果](../results/credit_soc_timestep_scan_analysis_20260609_v2/)

## 阻塞与结论边界

- 当前没有未完成的证据分支或结果阻塞。
- “当前约束下不存在严格 SOC”是对已实现 baseline、已扫描参数邻域和已测机制的经验判定，不是对所有可能信贷网络模型的数学不可能性证明。
- 10% 大 avalanche 是人工分类标签；检查频率会改变事件聚合窗口，因此其发生率不能单独证明临界。
- 稳健大级联只说明级联转变或过载区稳健存在，不自动推出 SOC；需要继续拆分初始同步违约、传播新增违约和重复违约。
- 完备场景扫描报告中的 SOC 快筛是候选筛选，不替代有限尺寸和长时平稳性复核；本轮筛选没有发现值得直接提升为严格 SOC 的候选带。
- timestep 对照 v2 是快速全景筛查：使用 `1 seed × 20 periods` 与 `max_period_length_steps=500`，不能替代长时稳态最终证明；但它清楚显示 period_end 大崩塌在微步结算下被碎片化，未出现达到 10%N 的尺度候选。
- pooled event 的 KS bootstrap 和 Vuong p 值在强序列相关下仅作描述性诊断；最终判定必须同时使用时间分离、非平稳性、有限尺寸和机制证据。
