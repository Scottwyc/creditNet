# 信贷网络自组织临界第二阶段关键总结 v1

更新时间：2026-06-04 12:51:52 CST

## 阶段目标

第二阶段从“已观察到级联转变和重尾迹象”推进到可审计的 SOC 判定。重点补足严格统计检验、有限尺寸标度、机制解耦和 `project.md` 各关注因素的覆盖。

## 当前结论边界

本总结中的“驱动强度 `c`”是便于叙述的简称。其准确定义是上一期总收入到下一期计划信贷尝试批量的转换系数：

```text
K_t = round(c * Y_(t-1))
```

它不是单笔贷款规模、实际投资支出比例或已分离出的纯加载速度。提高 `c` 会同时增加计划信贷尝试和下一次流量结算/违约检查前形成的暴露批量。固定 `K` 实验中 `c` 不生效。

当前可以确认：

- 信贷驱动强度、收入分配、初始本金分布和增长规则会显著改变 avalanche；
- 固定 `K` 存在稳定区、转变区和过载区；
- 收入内生 `K_t` 在高 `c`、biased 收入和不平等本金下可稳定产生大 avalanche。

第二阶段主协调预审计进一步发现：

- `c=0.20` 的 427 个大 avalanche 均发生在第 51 期以后，事件期 `K_t` 中位数为 28，并非第一期 `K_1=200` 的直接冲击；
- 大 avalanche 前活跃信贷中位数低于小 avalanche，支持长期状态依赖脆弱性；
- 所有聚焦 run 的累计违约节点计数均超过 `N`，说明节点重复违约不可忽略；
- 高风险协议中 avalanche 几乎每期发生且具有强一阶相关，更接近持续活跃失败态，而不是时间上充分分离的稀有 avalanche；
- `c=0.18` 的有限尺寸预审计中，最大 avalanche 占比随 `N` 增大而下降，10% 阈值事件率对 `N` 高度敏感。

当前不能确认：

- avalanche 尾部是否优于 lognormal 或 exponential；
- cutoff 是否随 `N` 呈有限尺寸标度；
- `c` 转变是否来自信贷驱动本身，还是 period_end 流量结算/检查批量变化；
- 结论是否对清算、节点退出、显式拓扑和消费参数稳健。

## 当前工作假设

截至 2026-06-04 12:45:00 CST，新增预审计使证据方向从“可能存在严格 SOC”偏向：

> 当前模型明确存在由驱动、分配和网络暴露共同决定的级联转变；高风险区域可能是具有重尾大小分布的持续活跃失败态，而不是已经证明的严格 SOC。

支持这一工作假设的初步证据是事件几乎每期发生、规模强时间相关、节点重复违约明显，以及最大 avalanche 占比随系统规模上升而下降。该判断仍需严格统计、动态传播和机制消融分支确认。

## 并行分支

| 分支 | 核心问题 | 主要产物 |
| --- | --- | --- |
| 严格 SOC 证据 | 是否存在通过统计检验和有限尺寸标度的 SOC | 严格尾部脚本、细扫与规模扫描、统计图 |
| 机制稳健性 | 当前大级联是否依赖检查间隔和清算设定 | 解耦实验、清算消融、稳健性图 |
| 因素覆盖 | project.md 关注因素如何影响临界性 | `a/b`、本金、收入、增长规则、ER/BA/SW 对照 |
| Avalanche 动态 | 传播是否接近临界分支过程、事件是否充分分离 | 传播代数、分支比、等待时间、size-duration 图 |

因素覆盖分支已完成首批 31 场景、248-run 固定时域扫描。结果显示 biased 收入和 random 增长效应强于匹配平均度后的 ER/BA/SW 家族差异；该结果仍需长时域与高重复确认。

## 晋级门槛

- 严格 SOC：power-law 拟合不能被合理替代分布显著击败，KS bootstrap 可接受，并存在系统规模相关 cutoff 或矩标度证据；
- 非 SOC：替代分布显著更优、无有限尺寸标度，或所谓临界仅由固定过载/检查批量导致；
- 不可识别：统计检验和机制消融给出冲突结果，且当前约束不足以区分。

## 当前产物

- 跟进日志：`docs/credit_soc_autonomous_followup_20260604_v2.md`
- 旧版详细报告：`docs/credit_soc_project_framework_detailed_analysis_20260604.md`
- 旧版图文 Word：`docs/credit_soc_project_framework_detailed_analysis_20260604.docx`
- 变量口径审计新版详细报告：`docs/credit_soc_project_framework_detailed_analysis_20260604_v2.md`
- 变量口径审计新版图文 Word：`docs/credit_soc_project_framework_detailed_analysis_20260604_v2.docx`
- 事件拆分、动态与严格统计变量审计报告 v3：`docs/credit_soc_project_framework_detailed_analysis_20260604_v3.md`
- 事件拆分、动态与严格统计变量审计图文 Word v3：`docs/credit_soc_project_framework_detailed_analysis_20260604_v3.docx`
- 因素与显式拓扑分支报告：`docs/credit_soc_phase2_factors_topology_report_20260604_v1.md`

## 下一阶段动作

等待三条并行分支完成首批实验与证据报告，然后派生新的图文阶段报告，不覆盖旧版。

## 2026-06-04 13:27:00 CST：Phase-2 最终判定

全部完成门槛已通过。当前已实现 baseline、已扫描参数邻域和已测机制下，严格 SOC 不存在，属于经验判定；系统存在级联交叉和机制敏感重尾，但高风险长期状态更符合非平稳、重复违约、低活跃信贷的持续失败/过载吸引子。

关键收尾证据：

- 长期低驱动搜索完成 42 场景、504 runs、1008000 periods、773242 events，11/11 审计通过，0 个 SOC 候选；
- fixed `K=1` 虽然在样本中均为单 initial default，但事件尺度窄、无 10% 大事件，且 active credit 持续积累，不是平稳 SOC 候选；
- 最终严格 v5、动态、机制、因素/拓扑和变量口径审计已统一纳入综合报告；
- 最终 Word 已通过 DOCX 结构、内嵌媒体和 LibreOffice 渲染验证。

最终产物：

- `docs/credit_soc_phase2_comprehensive_report_20260604_v1.md`
- `docs/credit_soc_phase2_comprehensive_report_20260604_v1.docx`
- `docs/credit_soc_phase2_completion_audit_20260604_v1.md`
