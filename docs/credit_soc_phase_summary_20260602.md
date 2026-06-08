# 信贷网络自组织临界阶段总结

更新时间：2026-06-02 20:45:00 CST

## 阶段定义

当前阶段是项目启动和第一轮机制验证阶段。已经从 `project.md` 的机制描述落地为可复现实验框架，并完成随机增长、净资产偏好拓扑、债务集中拓扑、高杠杆压力和聚焦确认实验。

## 数据与实验

第一阶段没有外部数据集，全部为合成个体信贷网络仿真。已完成 3880 次 run。核心变量包括：

- 节点数量；
- 初始本金分布；
- 收入分配方式；
- 信贷增长规则；
- 消费倾向参数 `a/b`；
- 投资/信贷增长参数 `c`；
- 级联违约阈值。

## 模型框架

模型采用离散单位信贷仿真。每条信贷边代表 1 单位贷款，方向为贷款人到借款人。节点净资产由现金、贷款资产和债务负债共同决定。

## 当前产物

- 协议文档：`/data/WYC/class/creditNet/docs/experiment_protocol_20260602.md`
- 跟进文档：`/data/WYC/class/creditNet/docs/credit_soc_followup_20260602.md`
- 阶段总结：`/data/WYC/class/creditNet/docs/credit_soc_phase_summary_20260602.md`
- 初始实验报告：`/data/WYC/class/creditNet/docs/credit_soc_initial_experiment_report_20260602.md`
- 随机增长基线：`/data/WYC/class/creditNet/results/credit_soc_baseline_20260602_small_v1`
- 净资产偏好拓扑：`/data/WYC/class/creditNet/results/credit_soc_topology_20260602_v1`
- 债务集中拓扑：`/data/WYC/class/creditNet/results/credit_soc_debt_topology_20260602_v1`
- 高杠杆压力：`/data/WYC/class/creditNet/results/credit_soc_high_leverage_20260602_v1`
- 高杠杆聚焦确认：`/data/WYC/class/creditNet/results/credit_soc_high_leverage_focus_20260602_v1`

## 阶段结果

第一轮结果不支持直接声称已经观察到稳健自组织临界幂律：

- 常规随机增长、净资产偏好拓扑和债务集中拓扑均没有出现 10% 以上的大崩塌；
- 高杠杆压力参数下出现少量大崩塌，聚焦确认批次 1000 次 run 中出现 10 次，最大崩塌 23/200；
- 大崩塌集中发生在第 1 期，更像高初始信贷冲击下的临界边界，而不是慢驱动积累出来的 SOC 稳态。

## 2026-06-04 新协议阶段结果

已按 `time_step + period` 和 `period_end` 协议重构仿真，并运行长序列 `continue_after_avalanche` 实验。

新增产物：

- 综合报告：`/data/WYC/class/creditNet/docs/credit_soc_autonomous_experiment_report_20260604.md`
- 固定K扫描：`/data/WYC/class/creditNet/results/credit_soc_fixedK_sweep_20260604_v1`
- 收入内生c扫描：`/data/WYC/class/creditNet/results/credit_soc_income_c_sweep_20260604_v1`
- 主协议聚焦确认：`/data/WYC/class/creditNet/results/credit_soc_continue_income_c020_random_focus_20260604_v1`

新增实验规模：

- 新协议有效 run：1500；
- avalanche事件：254752；
- 大avalanche事件：33292；
- 最大 avalanche：54/200。

阶段性结论：

- 固定K实验显示低驱动稳定区、过渡区和高频脆弱区；
- 收入内生K下，`c=0.02/0.05/0.10` 无大崩塌，`c=0.20` 在 biased收入 + random增长 + 不平等本金下稳定产生大 avalanche；
- 当前证据支持存在级联转变区，但尚未严格证明幂律 SOC。

## 风险

- 第一版级联规则是简化口径，后续需要与其他资产负债表失效规则对照。
- 第一批小规模实验只能作为机制验证，不能直接声称发现严格幂律。
- 当前“首次违约即停止并重置”协议会截断小 avalanche 后继续积累的过程，下一阶段应实现“慢驱动 + avalanche 后继续增长”的长序列协议。
