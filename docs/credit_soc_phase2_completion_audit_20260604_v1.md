# 信贷网络 Phase-2 最终完成性审计 v1

审计时间：2026-06-04 13:27:00 CST

## 最终判定

当前已实现 baseline、已扫描参数邻域和已测机制下，严格自组织临界（SOC）不存在，属于经验判定。系统明确存在级联交叉、机制敏感的大事件和重尾迹象，但联合证据更支持非平稳、重复违约、低活跃信贷的持续失败/过载吸引子。

该结论不是对所有可能信贷网络模型的数学不可能性证明。

## 技能完成门槛审计

| 门槛 | 直接证据 | 审计结论 |
| --- | --- | --- |
| 自动 `xmin`、GOF 与替代尾部 | [严格 SOC 报告](credit_soc_phase2_strict_soc_report_20260604_v1.md)、[strict v5](../results/credit_soc_phase2_strict_soc_20260604_v1/analysis_final_v5/)、[方法审计](../results/credit_soc_phase2_strict_soc_20260604_v1/method_audit_final_v4.md) | 已完成。39 个 series 全部使用自动 `xmin` 离散拟合、KS bootstrap、exponential/lognormal 比较。 |
| 有限尺寸标度或反证 | [strict v5](../results/credit_soc_phase2_strict_soc_20260604_v1/analysis_final_v5/)、[最终综合报告](credit_soc_phase2_comprehensive_report_20260604_v1.md) | 已完成。近线性绝对规模增长主要由同步 initial defaults 广延增长主导，传播占比约 12%-15%。 |
| 高重复转变区扫描 | [严格 SOC 报告](credit_soc_phase2_strict_soc_report_20260604_v1.md) | 已完成。28 场景、1440 runs、42 万 periods、368042 events；转变是宽交叉而非无需调参的稳定临界态。 |
| 驱动与检查/结算间隔分离 | [机制稳健性报告](credit_soc_phase2_mechanism_report_20260604_v1.md) | 已完成。credit-only 检查负对照完全等价；固定流量序列下高频检查主要碎片化事件，不恢复稀有平稳 avalanche。 |
| 本金、收入、消费、增长、ER/BA/SW | [因素与拓扑报告](credit_soc_phase2_factors_topology_report_20260604_v1.md) | 已完成当前约束下的统一固定时域覆盖。biased 收入、lognormal 本金、random 增长效应较强；匹配平均度后拓扑家族差异较弱。 |
| 清算、恢复、退出与 reset | [机制稳健性报告](credit_soc_phase2_mechanism_report_20260604_v1.md) | 已完成。现金受限回收、资产保留、永久退出、reset 外部现金流和重复违约均有直接实验。 |
| 最终版本化中文图文报告 | [最终综合报告](credit_soc_phase2_comprehensive_report_20260604_v1.md)、[最终 Word](credit_soc_phase2_comprehensive_report_20260604_v1.docx) | 已完成。Markdown 含 22 张实验图；Word 结构、内嵌媒体和 LibreOffice 渲染均通过验证。 |

## 最终独立审计摘要

- 模型变量覆盖：`project.md` 已覆盖 `CreditNetworkParams` 20/20 字段和 `RunResult` 27/27 字段。
- 严格尾部：无界幂律 26/39 不拒绝、13/39 拒绝；bounded 幂律 27/39 不拒绝、12/39 拒绝；exponential/lognormal 分别在 21/39、10/39 中描述性优于幂律；自动 `xmin` 离散 `alpha` 为 4.947-27.567。
- 事件定义：多数强驱动事件包含多个同步 initial defaults；传播新增通常只占总事件规模约 10%-16%。
- 动态传播：单事件内部传播通常亚临界；长期 continue 协议向持续失败/过载状态漂移。
- 长期平稳性：42 场景、504 runs、1008000 periods、773242 events，11/11 对账通过，0 个 SOC 候选；6 个低驱动场景稀疏但非平稳，36 个场景漂移或持续失败。
- 最慢 `K=1` 对照：事件在样本中均为单 initial default，但 P99 仅 3.00-3.69、无 10% 大事件，且 late/early active-credit 比为 7.17-7.36，因此不是平稳 SOC 候选。
- 最终 Word：DOCX 压缩结构无错误，内嵌媒体不低于 32 个，LibreOffice 正常渲染为 22 页 PDF。

## 变量解释完成情况

`c` 的代码字段为 `investment_income_propensity`，其作用为：

```text
K_t = round(c * Y_(t-1))
```

它将上一期总收入转换为下一期计划单位信贷尝试批量，不是单笔冲击、实际投资支出比例或已经与结算间隔解耦的纯驱动率。固定 `K` 协议中 `c` 不参与模拟。

与 `c` 类似、此前容易混淆的变量均已补充：计划/实际尝试/成功发放、initial/propagated defaults、single-trigger、wave/duration/branching、occupancy/wait/lag-1、unique/repeated defaults、自动 `xmin` 离散 `alpha`、KS bootstrap、Vuong、bounded cutoff、目标/实际回收和 reset 外部现金流。

完整变量词典见 [变量口径审计 v3](credit_soc_project_framework_detailed_analysis_20260604_v3.md)。
