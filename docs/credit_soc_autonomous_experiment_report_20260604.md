# 信贷网络自组织临界自治实验综合报告

生成时间：2026-06-04 07:40:00 CST

基于 `project.md` 各模块展开的详细机制分析见：

- `/data/WYC/class/creditNet/docs/credit_soc_project_framework_detailed_analysis_20260604.md`

## 结论摘要

本轮工作基于 `project.md` 修订后的 `time_step + period` 协议，重新实现并运行信贷网络自组织临界实验。新协议明确：

- 每个 `time_step` 只新增 1 个单位信贷；
- 一个 `period` 包含 `K` 或 `K_t` 个 `time_step`；
- 只在 `period_end` 做投资支出、消费支出、收入分配、违约检查和级联；
- 采用 `continue_after_avalanche` 长序列协议时，级联清算后继续下一期并记录完整 avalanche 序列。

有效新协议实验共完成 1500 个 run，记录 254752 个 avalanche 事件，其中 33292 个事件达到 10% 节点阈值。当前最重要的发现是：

- 固定 `K` 扫描显示清楚的驱动强度转变：`K=5/10` 基本只有小 avalanche；`K=20` 开始出现稀有大 avalanche；`K=30/50` 进入高频大 avalanche 的持续脆弱状态。
- 收入内生 `K_t = round(c * 上一期总收入)` 会显著抑制过载；`c=0.02/0.05/0.10` 没有出现 10% 大 avalanche。
- 在 `c=0.20`、biased 收入、random 增长下，大 avalanche 稳定出现：lognormal 初始本金分布下 75.0% 的 run 出现大 avalanche，pareto 下 36.7%，uniform 下未越过 10% 阈值。
- `preferential_debt` 债务集中增长在当前机制下反而压低 avalanche 规模；random 增长更容易形成广泛信用损失传播。
- 当前结果支持“存在驱动强度和分配机制共同决定的临界转变区”，但仍不能直接声称严格幂律。尾部 alpha 只是初筛，后续需要做 KS 与似然比检验。

## 代码与协议产物

核心代码：

- `/data/WYC/class/creditNet/src/creditnet/simulation.py`
- `/data/WYC/class/creditNet/scripts/run_credit_soc_experiment.py`
- `/data/WYC/class/creditNet/scripts/analyze_credit_soc_results.py`
- `/data/WYC/class/creditNet/scripts/summarize_fixed_k_sweep.py`

协议文档：

- `/data/WYC/class/creditNet/project.md`
- `/data/WYC/class/creditNet/docs/experiment_protocol_20260602.md`

相对 2026-06-02 第一版实现，本轮关键修正包括：

- `RunResult` 新增 `time_steps_completed`、`period_length_steps`、`avalanche_count`、`max_collapse_size` 等字段；
- runner 新增 `avalanche_events.csv`，逐事件记录每个 avalanche；
- runner 支持 `stop_on_first_default` 和 `continue_after_avalanche`；
- runner 支持 `period_length_rule=income/fixed`；
- 分析脚本优先使用 `avalanche_events.csv` 绘制和估计 avalanche 分布。

## 实验批次

| 批次 | run数 | avalanche事件数 | 大avalanche事件数 | 最大avalanche | 结果目录 |
| --- | ---: | ---: | ---: | ---: | --- |
| 固定K=5 | 120 | 10383 | 0 | 6 | `results/credit_soc_continue_fixedK5_20260604_v1` |
| 固定K=10 | 120 | 22799 | 0 | 11 | `results/credit_soc_continue_fixedK10_20260604_v1` |
| 固定K=20 | 120 | 33902 | 36 | 24 | `results/credit_soc_continue_fixedK20_20260604_v1` |
| 固定K=30 | 120 | 38786 | 6044 | 35 | `results/credit_soc_continue_fixedK30_20260604_v1` |
| 固定K=50 | 180 | 65719 | 26738 | 54 | `results/credit_soc_continue_fixedK50_20260604_v1` |
| 收入内生c=0.02 | 240 | 3371 | 0 | 3 | `results/credit_soc_continue_income_c002_20260604_v1` |
| 收入内生c=0.05 | 240 | 11496 | 0 | 8 | `results/credit_soc_continue_income_c005_20260604_v1` |
| 收入内生c=0.10 | 120 | 26243 | 0 | 15 | `results/credit_soc_continue_income_c010_biased_20260604_v1` |
| 收入内生c=0.20小批次 | 60 | 9227 | 47 | 28 | `results/credit_soc_continue_income_c020_biased_20260604_v1` |
| 收入内生c=0.20随机增长聚焦 | 180 | 32826 | 427 | 30 | `results/credit_soc_continue_income_c020_random_focus_20260604_v1` |

## 固定K扫描结果

汇总目录：

- `results/credit_soc_fixedK_sweep_20260604_v1`

关键图表：

- `results/credit_soc_fixedK_sweep_20260604_v1/event_critical_rate_by_k.png`
- `results/credit_soc_fixedK_sweep_20260604_v1/mean_event_size_by_k.png`
- `results/credit_soc_fixedK_sweep_20260604_v1/mean_avalanche_count_by_k.png`
- `results/credit_soc_fixedK_sweep_20260604_v1/ccdf_by_k_random.png`
- `results/credit_soc_fixedK_sweep_20260604_v1/ccdf_by_k_preferential_debt.png`

主要结果：

- `K=5`：所有场景最大 avalanche 不超过 6，没有大 avalanche。
- `K=10`：最大 avalanche 为 11，仍没有大 avalanche。
- `K=20`：random 增长开始出现稀有大 avalanche。lognormal+biased+random 的事件级大 avalanche 率约 0.3%，pareto+biased+random 约 0.2%。
- `K=30`：random 增长进入转变后状态。lognormal+biased+random 的事件级大 avalanche 率约 41.6%，pareto 约 32.7%，uniform 约 5.7%。
- `K=50`：random 增长出现高频大 avalanche。lognormal 约 83.9%，pareto 约 79.9%，uniform 约 64.6%。
- `preferential_debt` 在所有 K 下均未出现 10% 大 avalanche，最大仅 14。

解释：

固定 K 扫描更像外生驱动实验。它展示了“低驱动稳定区 -> 过渡区 -> 持续脆弱区”的清楚变化，但 `K=30/50` 下大 avalanche 太高频，不宜直接解释为稀有 SOC 临界。`K=20` 附近更接近值得细扫的边界。

## 收入内生K扫描结果

汇总目录：

- `results/credit_soc_income_c_sweep_20260604_v1`

关键图表：

- `results/credit_soc_income_c_sweep_20260604_v1/critical_rate_by_c.png`
- `results/credit_soc_income_c_sweep_20260604_v1/max_collapse_by_c.png`
- `results/credit_soc_income_c_sweep_20260604_v1/mean_avalanche_count_by_c.png`

biased收入 + random增长主线：

| c | lognormal大崩塌run率 | pareto大崩塌run率 | uniform大崩塌run率 | 最大avalanche |
| ---: | ---: | ---: | ---: | ---: |
| 0.02 | 0.000 | 0.000 | 0.000 | 3 |
| 0.05 | 0.000 | 0.000 | 0.000 | 8 |
| 0.10 | 0.000 | 0.000 | 0.000 | 15 |
| 0.20 | 0.750 | 0.367 | 0.000 | 30 |

`c=0.20` 聚焦结果：

- lognormal+biased+random：60 runs，run级大崩塌率 75.0%，最大 avalanche 30/200，tail alpha 初筛约 1.58；
- pareto+biased+random：60 runs，run级大崩塌率 36.7%，最大 avalanche 27/200，tail alpha 初筛约 1.71；
- uniform+biased+random：60 runs，未达到 10% 阈值，最大 avalanche 19/200，tail alpha 初筛约 1.80。

解释：

收入内生 `K_t` 与固定 K 的最大差别是反馈：收入下降会降低下一期 `K_t`，从而削弱继续加信贷的驱动力。因此 `c=0.02/0.05/0.10` 没有达到大崩塌阈值。`c=0.20` 接近 `project.md` 初始建议的 1/5，此时 biased收入 + random增长 + 不平等初始本金能稳定产生大 avalanche。

## 收入分配机制影响

收入内生 `c=0.02/0.05` 的完整矩阵包含 uniform 与 biased 收入分配。结果显示：

- uniform 收入分配下，违约和 avalanche 极少，最大规模通常不超过 1-4；
- biased 收入分配下，所有本金分布都会产生频繁小 avalanche；
- 只有 biased 收入叠加足够高的 `c`，才会越过 10% 大崩塌阈值。

这支持 `project.md` 的第三个关注点：收入分配方式会强烈改变临界信贷规模和级联失效概率。

## 网络增长机制影响

本轮重点比较了：

- `random`：随机贷款人、随机借款人；
- `preferential_debt`：贷款人按现金偏好选择，借款人按既有债务规模偏好选择。

结果与直觉不完全一致：

- `preferential_debt` 确实会更快形成债务集中，但在当前会计和清算规则下，它多数只产生小 avalanche；
- `random` 增长更容易让信用暴露分散在系统中，使债务人违约时触发更广范围的资产减记；
- 因此，大 avalanche 在当前模型中主要来自“广泛交叉暴露 + biased收入导致的净资产脆弱性”，而不是简单债务 hub。

## 是否已经证明自组织临界

还不能说已经严格证明 SOC。

已经成立的证据：

- 新协议下可以记录长序列 avalanche，而不是首次违约即停止；
- 固定 K 扫描存在清晰的驱动强度转变；
- 收入内生 K 在 `c=0.20`、biased收入、random增长、不平等初始本金下稳定出现大 avalanche；
- avalanche CCDF 和 tail alpha 初筛显示存在重尾迹象。

尚未成立的证据：

- 没有做严格幂律拟合的 xmin 选择、KS 检验和似然比对照；
- `K=30/50` 的固定 K 场景更像过载脆弱态，而不是临界态；
- 收入内生 `c=0.20` 已出现稳定大事件，但需要在 `c=0.12-0.20` 附近细扫，确认是否存在窄临界区；
- 当前级联清算规则仍偏简化，尚未比较 haircut 级联、节点退出/重置等替代机制。

当前最稳妥的判断是：

> 该信贷网络模型在 `period_end` 结算和长序列 avalanche 协议下，显示出由信贷驱动强度、收入分配偏置、初始本金不平等和网络增长机制共同决定的级联转变。它具备进一步检验自组织临界的实验基础，但尚未完成严格 SOC 证明。

## 下一步实验建议

1. 在收入内生协议下细扫 `c=0.12/0.14/0.16/0.18/0.20`，重点看 lognormal/pareto + biased + random。
2. 对 `K=18/20/22/24/26` 固定窗口做高重复数扫描，定位过渡边界。
3. 引入严格幂律检验：自动选择 xmin，比较 power-law、exponential、lognormal。
4. 对级联清算规则做 ablation：债权资产全额减记、比例 haircut、违约节点退出、违约节点资产重置。
5. 引入真实网络拓扑或显式 ER/BA/SW 底层约束，区分“内生信贷增长网络”和“给定拓扑上的信贷增长”。
