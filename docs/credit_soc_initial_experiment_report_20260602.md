# 信贷网络自组织临界初始实验报告

生成时间：2026-06-02 20:45:00 CST

## 结论摘要

已完成第一版信贷网络自组织临界仿真器和 5 批实验，共 3880 次 run。

当前结果需要保守解读：

- 在随机增长、净资产偏好拓扑、债务集中拓扑的常规参数下，没有出现稳健的大面积级联违约。
- 在高杠杆压力参数下，出现了少量达到 10% 节点阈值的崩塌，但这些崩塌集中发生在第 1 期，更像“初始高杠杆冲击临界”，还不是慢增长后的自组织临界态。
- 当前结果还不能支持“崩塌规模服从幂律”的结论；尾部样本不足，且大崩塌频率低。

## 实验协议

模型代码：

- `/data/WYC/class/creditNet/src/creditnet/simulation.py`
- `/data/WYC/class/creditNet/scripts/run_credit_soc_experiment.py`
- `/data/WYC/class/creditNet/scripts/analyze_credit_soc_results.py`

核心机制：

- 节点为个体，状态为现金、贷款资产、债务负债、净资产；
- 信贷边为 `lender -> borrower`，每条边 1 单位；
- 借贷不直接改变净资产，投资支出和消费支出降低现金/净资产，收入分配提高现金/净资产；
- 违约条件为 `net_worth < 0`；
- 级联机制为债务人违约导致债权人贷款资产减记，债权人净资产转负后继续传播；
- 大崩塌阈值为 `collapse_fraction >= 0.10`。

## 批次汇总

| 批次 | run 数 | 大崩塌数 | 大崩塌率 | 最大崩塌规模 | 平均崩塌规模 | 最大级联前信贷规模 | 结果目录 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 随机增长基线 | 800 | 0 | 0.00000 | 14 | 1.769 | 14505 | `results/credit_soc_baseline_20260602_small_v1` |
| 净资产偏好拓扑 | 640 | 0 | 0.00000 | 5 | 0.536 | 16640 | `results/credit_soc_topology_20260602_v1` |
| 债务集中拓扑 | 640 | 0 | 0.00000 | 14 | 2.305 | 4578 | `results/credit_soc_debt_topology_20260602_v1` |
| 高杠杆压力 | 800 | 1 | 0.00125 | 20 | 3.169 | 12440 | `results/credit_soc_high_leverage_20260602_v1` |
| 高杠杆聚焦确认 | 1000 | 10 | 0.01000 | 23 | 10.768 | 800 | `results/credit_soc_high_leverage_focus_20260602_v1` |

## 关键发现

### 1. 随机增长基线没有形成大级联

路径：`results/credit_soc_baseline_20260602_small_v1`

参数：

- `N=200`
- 每场景 80 次重复；
- 初始本金分布：`equal / uniform / normal / lognormal / pareto`
- 收入分配：`uniform / biased`
- 增长规则：`random`
- `a=0.02, b=0.20, c=0.20`

结果：

- 10 个场景共 800 次 run；
- 大崩塌数为 0；
- `equal + uniform` 和 `pareto + uniform` 多数能在 500 期内积累较高信贷规模而不违约；
- `biased` 收入分配显著提高违约率，但多为单点或小规模违约。

### 2. 净资产偏好拓扑降低了部分场景的早期脆弱性

路径：`results/credit_soc_topology_20260602_v1`

参数：

- 初始本金分布：`equal / uniform / lognormal / pareto`
- 收入分配：`uniform / biased`
- 增长规则：`borrower_preferential / preferential`
- 每场景 40 次重复

结果：

- 大崩塌数为 0；
- 最大崩塌规模只有 5；
- 按净资产偏好选择借款人会把债务更多分配给富裕个体，反而不容易形成脆弱债务中心。

### 3. 债务集中拓扑提高了早期违约率，但仍不够产生稳健大崩塌

路径：`results/credit_soc_debt_topology_20260602_v1`

新增增长规则：

- `borrower_debt_preferential`：借款人按既有债务规模偏好选择；
- `preferential_debt`：贷款人按现金规模偏好选择，借款人按既有债务规模偏好选择。

结果：

- 大崩塌数为 0；
- 最大崩塌规模为 14/200；
- 债务集中会更快触发违约，但常规杠杆下仍以局部违约为主。

### 4. 高杠杆压力参数首次触及 10% 崩塌阈值

路径：`results/credit_soc_high_leverage_20260602_v1`

参数变化：

- `mean_initial_money=50`
- `c=0.40`
- `initial_income_per_capita=10`
- 增长规则：`borrower_debt_preferential / preferential_debt`

结果：

- 800 次 run 中出现 1 次大崩塌；
- 最大崩塌规模为 20/200，刚好达到 10% 阈值；
- 触发场景是 `uniform + biased + preferential_debt`；
- 该崩塌发生在第 1 期，说明它更像高初始信贷冲击，而不是长时间自组织后的临界崩塌。

### 5. 聚焦确认显示高杠杆临界信号低频稳定存在

路径：`results/credit_soc_high_leverage_focus_20260602_v1`

参数：

- `mean_initial_money=50`
- `c=0.40`
- `initial_income_per_capita=10`
- 收入分配：`biased`
- 增长规则：`preferential_debt`
- 初始本金分布：`uniform / lognormal`
- 每场景 500 次重复

结果：

- 共 1000 次 run，出现 10 次大崩塌；
- `uniform + biased + preferential_debt`：大崩塌率 1.8%，最大崩塌 23/200；
- `lognormal + biased + preferential_debt`：大崩塌率 0.2%，最大崩塌 18/200；
- 所有样本均在第 1 期违约，仍不构成慢增长 SOC 证据。

## 图表与结果文件

每个结果目录均包含：

- `run_summary.csv`：逐 run 结果；
- `scenario_summary.csv`：按场景聚合；
- `tail_alpha_screen.csv`：崩塌规模尾部 alpha 初筛；
- `analysis_report.md`：单批次中文报告；
- `collapse_size_ccdf.png`：崩塌规模 CCDF；
- `credit_scale_boxplot.png`：级联前信贷规模箱线图。

## 当前判断

第一版模型已经能稳定表达：

- 初始本金不平等；
- 收入分配偏置；
- 信贷网络增长；
- 资产负债表违约；
- 信用资产减记级联；
- 临界信贷规模统计。

但当前机制还没有自然产生稳健的自组织临界幂律。主要原因可能是：

- “首次违约即停止并重置”的协议会截断小 avalanche 后继续积累的过程；
- 当前级联只通过贷款资产减记传播，信用网络损失传播偏保守；
- 常规参数下，违约节点的债权人损失不足以系统性击穿债权人净资产；
- 高杠杆参数下的崩塌发生太早，不是慢驱动形成的临界态。

## 下一步建议

1. 增加“慢驱动 + avalanche 后继续增长”协议：小违约不重置系统，只清算违约节点并继续落沙，记录一个长序列中的 avalanche 分布。
2. 扫描 `a/b/c` 与初始收入引导参数，寻找违约不在第 1 期发生、但最终能形成大级联的参数区间。
3. 增加更强的资产负债表失效规则，例如违约节点导致相邻资产按 haircut 比例折损，而不是只清零债务人入边。
4. 增加固定拓扑或显式 BA/SW 生成机制，和当前内生信贷增长规则区分开。
5. 在出现足够尾部样本后，再进行严格幂律、指数、lognormal 的似然比检验。
