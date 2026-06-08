# 信贷网络自组织临界实验跟进

## 当前目标

根据 `/data/WYC/class/creditNet/project.md` 建立信贷网络自组织临界仿真实验：先完成可复现仿真器、sanity check、第一批小规模参数对照和结果报告。

## 2026-06-02 00:00:00 CST Update: 项目正式启动

已确认第一阶段工作范围：

- 实现离散单位信贷网络仿真器；
- 固定第一版会计、流量和级联违约协议；
- 跑通 sanity check；
- 运行初始本金分布和收入分配机制的第一批对照实验；
- 输出 CSV、图表和中文报告。

当前尚未报告任何实验结论。

## 2026-06-02 20:37:59 CST Update: 随机增长基线完成

完成 `results/credit_soc_baseline_20260602_small_v1`：

- 模型：离散单位信贷网络仿真器 `src/creditnet/simulation.py`；
- 数据：合成信贷网络，`N=200`；
- 场景：5 种初始本金分布，2 种收入分配，`random` 增长；
- 重复：每场景 80 次，共 800 次 run；
- 参数：`a=0.02, b=0.20, c=0.20, max_periods=500`；
- 结果：大崩塌数 0，最大崩塌规模 14/200。

结论：随机增长基线没有形成稳健大级联。

## 2026-06-02 20:42:11 CST Update: 净资产偏好拓扑完成

完成 `results/credit_soc_topology_20260602_v1`：

- 场景：`borrower_preferential / preferential` 增长；
- 重复：640 次 run；
- 结果：大崩塌数 0，最大崩塌规模 5/200。

结论：按净资产偏好选择借款人会把债务分配给更富个体，没有放大级联。

## 2026-06-02 20:43:14 CST Update: 债务集中拓扑完成

完成 `results/credit_soc_debt_topology_20260602_v1`：

- 新增规则：`borrower_debt_preferential / preferential_debt`；
- 重复：640 次 run；
- 结果：大崩塌数 0，最大崩塌规模 14/200。

结论：债务集中提高早期违约率，但常规杠杆下仍以局部违约为主。

## 2026-06-02 20:44:58 CST Update: 高杠杆压力和聚焦确认完成

完成：

- `results/credit_soc_high_leverage_20260602_v1`
- `results/credit_soc_high_leverage_focus_20260602_v1`

高杠杆参数：

- `mean_initial_money=50`
- `c=0.40`
- `initial_income_per_capita=10`
- 收入分配：`biased`
- 增长规则：重点为 `preferential_debt`

结果：

- 高杠杆压力批次：800 次 run，1 次大崩塌，最大 20/200；
- 聚焦确认批次：1000 次 run，10 次大崩塌，最大 23/200；
- 聚焦批次中 `uniform + biased + preferential_debt` 大崩塌率约 1.8%，`lognormal + biased + preferential_debt` 约 0.2%。

结论：高杠杆债务集中场景存在低频临界信号，但崩塌集中发生在第 1 期，还不是慢增长后的自组织临界。

综合报告：

- `docs/credit_soc_initial_experiment_report_20260602.md`

## 2026-06-04 07:40:00 CST Update: 新协议长序列avalanche实验完成

根据 `project.md` 中 `time_step + period` 和 `period_end` 的新协议，已完成代码修正、长序列实验、可视化和综合报告。

代码更新：

- `src/creditnet/simulation.py`：新增 `time_steps_completed`、`period_length_steps`、`avalanche_count`、`continue_after_avalanche` 等协议字段；
- `scripts/run_credit_soc_experiment.py`：新增 `avalanche_events.csv` 输出、`period_length_rule`、`avalanche_protocol` 参数；
- `scripts/analyze_credit_soc_results.py`：优先基于 avalanche 事件绘图和尾部初筛；
- `scripts/summarize_fixed_k_sweep.py`：新增固定K扫描汇总和可视化脚本。

新协议实验共 1500 个 run，记录 254752 个 avalanche 事件，其中 33292 个达到 10% 节点阈值。

核心结果：

- 固定K扫描：`K=20` 开始出现稀有大 avalanche，`K=30/50` 进入高频大 avalanche 的持续脆弱状态；
- 收入内生K扫描：`c=0.02/0.05/0.10` 未出现大 avalanche，`c=0.20` 在 biased收入 + random增长下稳定出现大 avalanche；
- `c=0.20` 聚焦确认：lognormal 初始本金分布下 run级大崩塌率 75.0%，pareto 下 36.7%，uniform 下未达到 10% 阈值；
- `preferential_debt` 在当前清算规则下多数产生小 avalanche，random 增长更容易形成广泛级联。

综合报告：

- `docs/credit_soc_autonomous_experiment_report_20260604.md`

关键结果目录：

- `results/credit_soc_fixedK_sweep_20260604_v1`
- `results/credit_soc_income_c_sweep_20260604_v1`
- `results/credit_soc_continue_income_c020_random_focus_20260604_v1`

## 2026-06-04 10:45:00 CST Update: project.md框架详细分析报告完成

已按 `project.md` 的场景、存量、流量、信贷关系、初始化、网络增长、收入分配、级联失效、自组织临界和实验分类框架，补充详细机制分析。

新增报告：

- `docs/credit_soc_project_framework_detailed_analysis_20260604.md`

新增分析脚本与结果：

- `scripts/build_project_framework_analysis.py`
- `results/credit_soc_project_framework_analysis_20260604_v1`

新增证据包括：

- 初始本金分布对大崩塌率、首次级联和最终净资产Gini的影响；
- uniform/biased收入分配对avalanche频率和首次级联前信贷规模的影响；
- random/preferential_debt增长机制在不同K下的级联差异；
- 大小级联发生前活跃信贷规模的对照。

详细报告明确区分了当前已实现机制和未实现内容，包括显式ER/BA/SW拓扑、还款、利息、违约回收率、a/b扫描与严格幂律检验。
