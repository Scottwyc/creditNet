
## 项目跟进分析
p: › 请加载全局记忆/home/wuyangcheng/.codex/memories，这里面是以后codex补充全局记
  忆的地方。加载后请继续加载/home/wuyangcheng/.codex/skills，这里面是以后codex
  补充技能的地方。  现在，根据/data/WYC/class/creditNet/project.md  进行信贷网
  络自组织临界的实验。你先说明你后续的工作计划，我确认后展开


› 你在给出文献证据时，关键还要给出文献被期刊收录的时间，我们希望尽可能比较新，
  近5年的

A:   工作计划

  1. 建立实验工程骨架
      - 在 /data/WYC/class/creditNet 下建立 src/、scripts/、results/、docs/ 等目
        录。
      - 新建项目记忆 /home/wuyangcheng/.codex/memories/projects/creditNet/
        work_log.md。
      - 后续实验过程同步更新 credit_work.md 和项目记忆。
  2. 先固定一个可复现实验协议
      - 节点状态：现金、贷款资产、债务负债、净资产。
      - 信贷边方向：lender -> borrower，每条边 1 单位信贷。
      - 借贷本身不改变净资产，只改变现金/资产/负债结构。
      - 收入与支出改变净资产。
      - 违约条件：净资产小于 0。
      - 级联机制：违约节点相关信用资产减记，引发债权人净资产下降，继续传播。
  3. 实现基础仿真器
      - 使用 /home/wuyangcheng/.conda/envs/myenv/bin/python。
      - 支持随机种子、参数配置、批量重复实验。
      - 加会计恒等式和边界条件检查，例如贷款人现金不能为负、资产负债变化守恒、级
        联损失不重复计算。
  4. 先跑最小 sanity check
      - 小规模 N=50/100、少量轮次。
      - 检查网络增长、收入分配、违约触发、级联规模统计是否符合机制设定。
      - 这一步不追求结论，只排除模型实现错误。
  5. 主实验分三组
      - 初始本金分布：等额、均匀、正态/截断正态、幂律或 lognormal。
      - 收入分配机制：随机均匀 vs 按净资产偏好分配。
      - 网络增长机制：随机配对、偏好连接、不同稀疏/密集增长参数。
  6. 统计自组织临界指标
      - 每轮记录首次崩塌前的信贷规模。
      - 记录 avalanche/cascade size 分布。
      - 画崩塌规模频率、CCDF、临界信贷规模分布。
      - 初步拟合幂律，并和指数/lognormal 做对比，避免只看 log-log 图就下结论。
  7. 输出报告
      - 生成 CSV/JSON 原始结果、图表和中文实验报告。
      - 报告写清楚模型机制、参数、数据规模、随机种子、指标定义、主要结论和未解决
        风险。

  如果你确认，我会先从“实验协议固定 + 仿真器骨架 + sanity check”开始。


Q: 你是怎么定义“稳健的大级联”的？是指多次重复实验稳定出现吗？
A: • 是的，“稳健的大级联”我这里分了两层口径：

  1. 大级联的数值定义

  当前代码里的“大级联”定义是：

  collapse_fraction >= 0.10

  也就是一次级联违约波及节点数达到总节点数的 10% 以上。

  在当前实验 N=200，所以：

  collapse_size >= 20

  就被记为 critical_event=True。

  2. 稳健的含义

  “稳健”不只是某一次 run 出现，而是至少满足这些条件：

  - 多个随机种子重复实验中反复出现，不是单个 seed 的偶然结果；
  - 出现频率不能太低，比如不是 800 次里只出现 1 次；
  - 换相近参数后仍然存在，而不是只在一个非常窄的参数点出现；
  - 最好不是全部集中在第 1 期，否则更像初始冲击，而不是自组织临界的慢增长崩塌；
  - 如果要支持 SOC，还需要 avalanche size 分布有足够尾部样本，再做幂律/指数/
    lognormal 对比。

  所以你理解得对：“多次重复实验稳定出现”是稳健性的核心之一。但我还额外强调参数邻
  域、时间位置和分布尾部。

  当前结果按这个标准还不算稳健：

  - 常规参数：基本没有 10% 以上大级联；
  - 高杠杆聚焦批次：1000 次里有 10 次大级联，最高 23/200；
  - 但这些大级联都发生在第 1 期，所以我只把它称为“高初始信贷冲击临界信号”，不称
    为稳健 SOC。


Q: 什么叫“发生在第 1 期”？
A: • “发生在第 1 期”指的是：系统刚初始化后，执行第一个时期的信贷增长、支出、收入分
  配，然后立刻检查净资产时，就已经出现违约并触发级联。

  也就是流程上：

  初始化节点本金和空资产负债表
  -> 第 1 期新增信贷
  -> 第 1 期支出
  -> 第 1 期收入分配
  -> 第 1 期检查净资产
  -> 已经违约并级联

  所以它不是系统经过很多期“信贷网络逐步增长、风险慢慢积累”之后才崩塌，而是一开始
  参数就太激进，比如：

  - initial_income_per_capita=10
  - c=0.40
  - N=200

  第 1 期计划新增信贷大约是：

  planned_credit = round(c * previous_total_income)
  previous_total_income = 200 * 10 = 2000
  planned_credit = 0.40 * 2000 = 800

  也就是说，系统一开始空网络状态下，第一期就直接落下 800 个信贷单位。这个冲击很
  大，所以第 1 期就可能把部分节点推到资不抵债。

  因此我说它更像“初始高杠杆冲击临界”，不是严格意义上那种“长期慢驱动后自组织到临
  界态再崩塌”。


P: 嗯，所以你现在的实现并不是一个实验轮次内部进行逐个时间步的迭代？每个时间步应该只是加1个单位信贷吧？

NEW: 我建议下一版采用这个明确协议：

  time_step:
    新增 1 单位信贷

  period:
    包含 K_t = round(c * previous_total_income) 个 time_step
    period 末做投资支出、消费支出、收入分配、违约检查

  并在结果里记录：

  period_index
  period_length_steps
  time_steps_completed
  credit_scale_before_cascade
  collapse_size

  如果你的理论重点是“沙粒一粒一粒落下”，还可以进一步加一个选项：

  default_check_interval = "period_end" 或 "each_step"

  - period_end：每期末检查违约，更贴近流量结算。
  - each_step：每加 1 单位信贷后都检查净资产，更贴近沙堆临界过程。

  当前我建议先用 period_end，因为违约来自收入/支出结算后的净资产，而不是借贷本
  身。


P: 可以，那么就time_step和period相结合的方式，并用period_end 每期末检查违约；请你补充相应细节到 project.md 的算法实现部分中


Q: 驱动强度c是什么？报告里面似乎没有解释清楚当前的模型框架细节？请查看还有没有类似没有解释清楚的变量，补充并更新


## 项目推进
P: /goal 现在进行持续自主项目推进，根据目前总结文档里面提到的下一步建议，进一步推进实验，你可以启用codex worker并行推进，然后在得到大的阶段性成果后，给出在旧版的基础上派生新版总结报告（带实验图）（不覆盖旧版本），并不断重复上述步骤，直到彻底探索确认总目标结束：当前约束下，信贷网络自组织临界存在/不存在，各方面因素（project.md中提到的关注点）的影响如何。最终完成时，要给出最完备的实验分析报告


P: 给我建立一个creditNet项目的git仓库，要跟踪核心代码和核心结果、核心报告


P: 你解释一下你的级联失效是怎么定义的，你认为的SOC要满足什么条件？请在相关文档中补充详细解释



### 改进建议

P: 有人说，计划投资支出的比例c，刚开始的比例太小了，可以从0.1调整到0.8，调整步长就是0.1。你先说说现在是怎么设置的，然后你看看能不能改




## 2026-06-02 00:00:00 CST

正式启动信贷网络自组织临界实验。

当前第一阶段目标：

- 固定第一版仿真实验协议；
- 实现可复现实验代码；
- 完成 sanity check；
- 运行第一批小规模对照实验；
- 输出 CSV、图表和中文报告。

当前协议文档：

- `docs/experiment_protocol_20260602.md`

## 2026-06-02 20:45:00 CST

已完成第一版仿真器和 5 批实验，共 3880 次 run。

主要产物：

- 源码：`src/creditnet/simulation.py`
- 批量脚本：`scripts/run_credit_soc_experiment.py`
- 分析脚本：`scripts/analyze_credit_soc_results.py`
- 综合报告：`docs/credit_soc_initial_experiment_report_20260602.md`
- 随机增长基线：`results/credit_soc_baseline_20260602_small_v1`
- 净资产偏好拓扑：`results/credit_soc_topology_20260602_v1`
- 债务集中拓扑：`results/credit_soc_debt_topology_20260602_v1`
- 高杠杆压力：`results/credit_soc_high_leverage_20260602_v1`
- 高杠杆聚焦确认：`results/credit_soc_high_leverage_focus_20260602_v1`

关键结论：

- 常规参数下没有形成稳健大级联；
- 高杠杆 `uniform/lognormal + biased + preferential_debt` 场景出现低频 10% 崩塌；
- 当前大崩塌集中发生在第 1 期，还不能作为慢增长自组织临界证据；
- 下一步应实现“慢驱动 + avalanche 后继续增长”协议。

## 2026-06-02 21:00:00 CST

根据用户确认，已修订 `project.md` 的实验模拟算法流程：

- 明确定义 `time_step` 为微观时间步，每个 `time_step` 只新增 1 个单位信贷；
- 明确定义 `period` 为结算周期，一个 `period` 包含 `K_t = round(c * 上一期总收入)` 个 `time_step`；
- 主实验采用 `period_end` 违约检查，即只在每个 `period` 末完成支出、收入分配、违约判断和级联失效；
- 后续代码实现需要从“period 内批量新增信贷”的旧口径，改为“逐个 time_step 新增信贷 + period_end 结算”的新口径。

## 2026-06-04 07:40:00 CST

完成新协议下的自治实验、可视化整理和综合报告。

主要代码更新：

- `src/creditnet/simulation.py`
- `scripts/run_credit_soc_experiment.py`
- `scripts/analyze_credit_soc_results.py`
- `scripts/summarize_fixed_k_sweep.py`

新协议产物：

- 综合报告：`docs/credit_soc_autonomous_experiment_report_20260604.md`
- 固定K扫描汇总：`results/credit_soc_fixedK_sweep_20260604_v1`
- 收入内生c扫描汇总：`results/credit_soc_income_c_sweep_20260604_v1`
- 主协议聚焦确认：`results/credit_soc_continue_income_c020_random_focus_20260604_v1`

关键结论：

- 新协议有效实验共 1500 run，记录 254752 个 avalanche 事件；
- 固定K扫描中 `K=20` 开始出现稀有大 avalanche，`K=30/50` 进入高频脆弱状态；
- 收入内生K下 `c=0.20` 是当前关键转变点，lognormal+biased+random 的 run级大崩塌率为 75.0%，pareto 为 36.7%；
- 当前支持“存在级联转变区”，但尚未完成严格幂律/SOC证明。

## 2026-06-04 10:45:00 CST

已基于 `project.md` 框架补充详细分析报告：

- `docs/credit_soc_project_framework_detailed_analysis_20260604.md`

新增框架分析产物：

- 脚本：`scripts/build_project_framework_analysis.py`
- 结果目录：`results/credit_soc_project_framework_analysis_20260604_v1`

报告逐项分析了：

- 存量资产负债表与系统守恒；
- time_step、period和流量反馈；
- 初始本金分布；
- 网络增长机制；
- 收入分配机制；
- 级联失效与临界信贷规模；
- 自组织临界证据与未完成检验；
- `project.md` 已实现和未实现模块。

  主要实验结论：

  - 常规随机增长、净资产偏好拓扑、债务集中拓扑下，均未出现稳健的 10% 以上大级
    联。
  - 高杠杆压力场景首次出现 10% 崩塌：最大 23/200。
  - 聚焦确认批次中，uniform + biased + preferential_debt 的大崩塌率约 1.8%，
    lognormal + biased + preferential_debt 约 0.2%。
  - 但这些大崩塌都集中在第 1 期，更像“初始高杠杆冲击临界”，还不能作为慢增长自组
    织临界或幂律证据。

## 2026-06-04 图文版详细报告导出

已在 `docs/credit_soc_project_framework_detailed_analysis_20260604.md` 对应分析章节中嵌入 10 张关键实验结果图，并重新导出：

- `docs/credit_soc_project_framework_detailed_analysis_20260604.docx`

图片覆盖收入内生 `c` 扫描、初始本金分布、增长机制、收入分配、临界信贷规模、avalanche CCDF 和 avalanche 时间线。导出后已确认 Word 内嵌 10 张 PNG，压缩结构无错误，并可由 LibreOffice 正常渲染为 20 页 PDF。

## 2026-06-04 模型变量与框架口径补充

已更新：

- `project.md`
- `docs/experiment_protocol_20260602.md`
- `docs/credit_soc_project_framework_detailed_analysis_20260604.md`
- `docs/credit_soc_project_framework_detailed_analysis_20260604.docx`

重点明确：

- `c` 是上一期总收入转化为下一期计划信贷 time_step 数的比例，`K_t=round(c*Y_(t-1))`；
- 当前 `N=200`、初始人均参考收入为 5，因此 `c=0.02/0.05/0.10/0.20` 对应第一期 `K_1=20/50/100/200`；
- `c` 同时改变信贷驱动批量和两次 period_end 违约检查之间的间隔，固定 K 实验中 `c` 不生效；
- 区分计划步数、实际尝试步数、成功发放量、实际投资支出、活跃信贷暴露和累计发放量；
- 补充 `a/b/f`、初始收入种子、增长规则、违约阈值、清算规则及事件级/run级指标定义。

新版 Word 内嵌 10 张 PNG，压缩结构正常，可正常渲染为 27 页 PDF。

## 2026-06-04 12:51:52 CST：变量口径审计 v2 与显式拓扑首批结果

根据用户对“驱动强度 `c`”和当前模型框架解释完整性的要求，已派生新版详细报告且未覆盖旧版：

- `project.md`
- `docs/credit_soc_project_framework_detailed_analysis_20260604_v2.md`
- `docs/credit_soc_project_framework_detailed_analysis_20260604_v2.docx`

关键修订：

- `c` 的准确定义为上一期总收入到下一期计划信贷尝试批量的转换系数，`K_t=round(c*Y_(t-1))`；它不是单笔冲击、实际投资支出比例或纯加载速度；
- 区分计划尝试、实际尝试、成功发放、实际投资支出、活跃信贷和累计发放；
- 补齐全部基线参数、run/event 字段、统计标签和第二阶段扩展变量；
- 明确 `cascade_steps` 在基线中只是已处理违约节点数，不是传播 duration。

验证：

- `CreditNetworkParams` 与 `RunResult` 全部字段均在新版报告中解释；
- Word 内嵌 12 张实验图，DOCX 结构正常，LibreOffice 正常渲染为 33 页 PDF；
- 基线 sanity check 与 phase-2 当前脚本静态编译通过。

同期因素与显式拓扑分支已完成 31 场景、248 runs、51,401 事件的首批固定 240-period 扫描。匹配平均度后的 ER/BA/SW 家族差异较弱，biased 收入和 random 增长效应更强；结果只用于固定时域因素方向，不代表长期稳态排序。

## 2026-06-04 13:00:56 CST：Phase-2 交叉审计与低驱动长期平稳性搜索

四条正式分支完成主协调器独立对账，未发现改变主结论的数据一致性错误：

- strict：1440 runs / 368042 events，会计和 run/event 聚合一致；
- dynamics：baseline equivalence、wave size 和 duration 计数零失配；
- mechanism：paired credit-only 负对照零失配，现金与 reset 外部流量恒等式通过；
- factors/topology：248 runs / 51401 events，机会图结构与 run/event 汇总零失配。

严格统计审计发现首版 `alpha=12` 上限截断与最多 80 个 `xmin` 候选的近似问题。旧版结果保留，正在
`results/credit_soc_phase2_strict_soc_20260604_v1/analysis_final_allxmin_v3/`
运行 `alpha<=50`、穷举 `xmin`、200 bootstrap 的修正版。

为排除低驱动区域存在遗漏的稀有平稳 avalanche 窗口，新增 `stationarity-search` worker，覆盖 income `c=0.02-0.20` 与 fixed `K=2-30` 的 2000-period 长期搜索；只有发现可信候选才追加有限尺寸验证。

新增结果导航：

- `/data/WYC/class/creditNet/docs/credit_soc_key_results_dashboard.md`

该导航页的 24 个本地链接和必需章节已通过自动校验。

## 2026-06-04 13:11:48 CST：变量口径审计 v3

继续补充 `c` 之外易混淆的模型与统计变量：

- 级联事件拆分：`initial_default_count`、`propagated_default_count`、`propagation_share`、`single_trigger_event`；
- 动态和长期诊断：wave、duration、branching、occupancy、waiting、lag-1、unique/repeated default；
- 严格统计：自动 `xmin` 离散幂律 `alpha`、KS bootstrap、Vuong、bounded power law 和 cutoff/moment scaling；
- 机制扩展：目标与实际回收、reset 外部现金流和 active 状态。

新增产物：

- `docs/credit_soc_project_framework_detailed_analysis_20260604_v3.md`
- `docs/credit_soc_project_framework_detailed_analysis_20260604_v3.docx`

验证：Word 内嵌 12 张实验图，DOCX 结构正常，LibreOffice 可正常渲染为 36 页 PDF。

## 2026-06-04 13:17:10 CST：严格 SOC v5 最终审计

最终严格统计目录为 `results/credit_soc_phase2_strict_soc_20260604_v1/analysis_final_v5/`。

- 无界离散幂律：26/39 不拒绝、13/39 拒绝；
- bounded 幂律：27/39 不拒绝、12/39 拒绝；
- exponential/lognormal 分别在 21/39、10/39 中描述性显著优于 power law；
- 自动 `xmin` 离散 `alpha` 为 4.947-27.567，无优化边界命中；
- 有限尺寸总规模近线性增长主要由同步初始违约的广延增长主导，传播占比约 12%-15%。

协调器独立校验 strict CSV、事件拆分恒等式和报告图片链接均通过。低驱动长期 fixed/income 两个 shard 正在运行。

## 2026-06-04 13:27:00 CST：当前约束下 SOC 最终判定完成

状态：项目当前目标完成。

- 低驱动长期搜索完成 42 场景、504 runs、1008000 periods、773242 events，11/11 审计通过，0 个 SOC 候选；
- 当前 baseline、参数邻域和已测机制下，严格 SOC 不存在，属于经验判定；
- 存在宽级联交叉和机制敏感重尾，但强驱动长期行为更符合非平稳、重复违约、低活跃信贷的持续失败/过载吸引子；
- `project.md` 已覆盖全部 20 个 `CreditNetworkParams` 和 27 个 `RunResult` 字段，`c` 与其余易混淆变量均已补充定义；
- 最终图文报告与 Word 已通过链接、DOCX、媒体内嵌和 LibreOffice 渲染验证。

最终产物：

- `docs/credit_soc_phase2_comprehensive_report_20260604_v1.md`
- `docs/credit_soc_phase2_comprehensive_report_20260604_v1.docx`
- `docs/credit_soc_phase2_completion_audit_20260604_v1.md`

## 2026-06-05 17:24:29 CST：收入内生 c 高驱动扫描网格调整

根据后续讨论，新增“`c=0.10-0.80`、步长 `0.10`”作为收入内生协议的默认高驱动扫描网格。这里的 `c` 仍按模型口径解释为上一期总收入到下一期计划信贷尝试批量的转换系数，`K_t=round(c*Y_(t-1))`，不是实际投资支出的硬比例。

代码与文档更新：

- `scripts/run_credit_soc_experiment.py` 新增 `--c-values` 批量扫描入口，单值 `--c` 默认仍为 `0.20`；
- `scripts/run_phase2_strict_soc_sweeps.py` 与 `scripts/run_phase2_stationarity_search.py` 的 income 默认网格调整为 `0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80`；
- `project.md` 补充当前默认、旧低驱动探索点、新高驱动网格，以及 `N=200, Y_0=1000` 下第一期 `K_1=100-800` 的换算表。

验证：

- `py_compile` 通过；
- `run_credit_soc_experiment.py --c-values 0.10,0.20` 小样本 smoke test 通过，输出按 `investment_income_propensity` 正确分组；
- strict 与 stationarity dry-run 均确认默认收入内生网格覆盖 `0.10-0.80`。

## 2026-06-05 18:54:17 CST：c=0.10-0.80 收入内生重扫完成

按新规则完成收入内生高驱动重扫：

- 目录：`results/credit_soc_phase2_income_c010_c080_20260605_v1/`
- 协议：`period_length_rule=income`、`K_t=round(cY_(t-1))`、`period_end` 检查、`continue_after_avalanche`
- 参数：`N=200`、biased 收入、random 增长、lognormal/pareto 初始本金、`c=0.10,0.20,...,0.80`
- 规模：16 scenarios、960 runs、271044 avalanche events，验证会计一致性开启

主要发现：

- 高 `c` 明显增加 period-end 批量结算压力，`c>=0.50` 后两种本金分布几乎每期都有 avalanche；
- lognormal 下事件级大级联率从 `c<=0.20` 平均 0.045 升到 `c>=0.50` 平均 0.997；pareto 从 0.027 升到 0.982；
- 平均事件规模也随 `c` 单调增大，lognormal `c=0.10 -> 0.80` 为 2.8 -> 72.8，pareto 为 2.0 -> 71.5；
- 传播占比随 `c` 上升，但这是在事件几乎每期发生、等待时间约等于 1 的过载背景中出现，不能解释为稳定稀疏单触发临界传播；
- 新旧 `c=0.20` 重复结果方向一致，旧低驱动结论不是由遗漏 `c>0.20` 偶然造成。

新增分析产物：

- `docs/credit_soc_high_c_rescan_report_20260605_v1.md`
- `docs/credit_soc_high_c_rescan_report_20260605_v1.docx`
- `results/credit_soc_high_c_rescan_analysis_20260605_v1/`

验证：

- `scripts/analyze_high_c_rescan.py` 静态编译通过；
- 分析报告生成 5 张 PNG 图；
- Word 文档已确认包含 5 个 `word/media/*.png`。

## 2026-06-05 23:02:57 CST：高 c SOC 验证补充实验完成

在 `c=0.10-0.80` 重扫基础上补齐 SOC 关键证据门槛中的有限尺寸和平稳性实验。

新增实验：

- 高 c 有限尺寸：`results/credit_soc_high_c_finite_size_20260605_v1/`
  - `N=100/200/500`，`c=0.30/0.50/0.80`，lognormal/pareto；
  - 18 scenarios、432 runs、102094 events；
  - 会计校验开启。
- 高 c 长时平稳性：`results/credit_soc_high_c_stationarity_20260605_v1/income/`
  - `N=200`，`c=0.30/0.50/0.80`，lognormal/pareto；
  - 6 scenarios、48 runs、57600 periods、57418 events；
  - baseline 等价校验通过、现金残差为零。

关键验证结果：

- 大级联稳健存在：`c>=0.50` 平均事件级大级联率约 0.990；
- 有限尺寸不支持 SOC：`mean_size` 对 `N` 的 log-log 斜率约为 1，但 `mean_size/N` 斜率接近 0，表示广延同步失败；
- 相对 cutoff 不增长：`p99/N` 斜率多为负或近 0，中位数约 -0.098；
- 长时不满足慢驱快崩：late avalanche occupancy 全部为 1.000，几乎每期发生事件；
- late repeated-default share 为 0.972-0.987，说明事件尾部和大级联高度依赖重复违约状态；
- 高 c 扩展结论：稳健大级联和过载转变成立，但严格 SOC 仍不受支持。

新增产物：

- `docs/credit_soc_high_c_soc_validation_report_20260605_v1.md`
- `docs/credit_soc_high_c_soc_validation_report_20260605_v1.docx`
- `results/credit_soc_high_c_soc_validation_20260605_v1/`
- 新增脚本：`scripts/run_high_c_finite_size.py`、`scripts/analyze_high_c_soc_validation.py`

验证：

- 两个新增脚本 `py_compile` 通过；
- SOC 验证报告生成 3 张 PNG 图；
- Word 文档已确认包含 3 个 `word/media/*.png`。

## 2026-06-08 16:11:54 CST：建立 creditNet Git 仓库跟踪口径

按“核心代码、核心结果、核心报告”原则初始化项目 Git 仓库：

- 新增 `.gitignore`，默认忽略运行缓存、Codex worker 状态、日志、临时 Word 渲染目录和 `results/` 下未筛选的大体量实验输出；
- 新增 `README.md`，说明主文档、源码、脚本、报告和结果的跟踪边界；
- 计划将 `src/`、`scripts/`、`docs/`、`project.md`、Word 导出、关键 summary/metadata/figures 纳入 Git；
- 逐事件原始数据如 `avalanche_events.csv`、`avalanche_waves.csv` 和逐期 history 文件继续保留在本地磁盘，但默认不进入 Git 历史。

## 2026-06-08 18:07:45 CST：GitHub 远端发布完成

已将本地 Git 仓库发布到 GitHub：

- 远端：`git@github.com:Scottwyc/creditNet.git`
- 分支：`main`
- 初始提交：`c1f07e1 Initialize creditNet project repository`
- 本地 `main` 已设置跟踪 `origin/main`

发布口径沿用建仓规则：GitHub 仓库只包含核心代码、核心报告、主文档和精选结果摘要/图表；大体量逐事件流与逐期历史文件仍保留本地并由 `.gitignore` 默认排除。

## 2026-06-08 21:42:53 CST：补充级联失效与 SOC 判定定义

根据“级联失效如何定义、SOC 要满足什么条件”的追问，完成文档口径补充：

- `project.md` 前置补充当前实现中的级联定义：`period_end` 流量结算后识别 `W_i < default_threshold` 的初始违约，沿信贷暴露清算传播，队列为空时记录一次 avalanche；
- 明确 `collapse_size` 是单次事件中被清算的不同节点数，`critical_event` 只是 `collapse_size/N >= collapse_threshold_fraction` 的人工大级联标签；
- 明确需要拆分 `initial_default_count`、`propagated_default_count`、`propagation_share`，避免把同步初始违约当成单一微观触发 SOC avalanche；
- 新增 `docs/credit_soc_cascade_soc_definitions_20260608.md`，系统说明大级联、稳健级联转变、重尾、幂律和严格 SOC 的层级关系；
- 更新 `docs/credit_soc_key_results_dashboard.md`，加入术语口径入口和结论边界。

本次只更新文档定义，不改变仿真代码、结果数据或既有 SOC 经验判定。
