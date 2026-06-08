# 信贷网络自组织临界持续自主实验跟进 v2

## 总目标

在 `project.md` 当前约束及其可解释扩展下，持续检验：

1. 信贷网络是否存在严格意义上的自组织临界；
2. 若严格 SOC 不成立，模型中实际存在的是何种级联转变、重尾或过载状态；
3. 初始本金分布、收入分配、信贷增长机制、消费参数、网络拓扑和清算规则分别如何影响级联；
4. 哪些结论对系统规模、随机种子、事件阈值和模型机制稳健。

## 当前阶段起点

时间：2026-06-04 12:20:00 CST

已有证据支持：

- 固定 `K` 和收入内生 `K_t` 下均存在从小级联向大级联的转变；
- biased 收入、random 交叉暴露和不平等本金分布会放大级联；
- `c=0.20` 主协议下存在大 avalanche 和重尾迹象。

尚不能证明严格 SOC，主要缺口：

- 尚无自动 `xmin`、KS bootstrap 和分布似然比检验；
- 尚无有限尺寸标度；
- `c` 的驱动效应与 period_end 检查间隔效应未分离；
- 清算规则、违约节点退出、回收率等机制未做稳健性消融；
- 显式 ER、BA、SW 拓扑与 `a/b` 参数影响未覆盖。

## 第二阶段并行实验线

### A. 严格 SOC 证据线

- 实现离散 power-law、exponential、lognormal 尾部比较；
- 自动选择 `xmin`，进行 KS bootstrap；
- 细扫收入内生 `c=0.12-0.20` 和固定 `K=18-26`；
- 扫描 `N=100/200/500/1000`，检查 avalanche cutoff 与系统规模的关系；
- 区分临界边界、过载态和非幂律重尾。

### B. 机制稳健性与解耦线

- 分离信贷驱动批量与违约检查间隔；
- 比较全额资产减记、部分回收、违约节点退出或重置；
- 检查当前 `continue_after_avalanche` 下节点可重复违约是否主导重尾；
- 评估结论对大崩塌阈值和运行时会计校验的稳健性。

### C. project.md 因素覆盖线

- 扫描 `a/b` 消费参数；
- 扩展 equal、normal 等初始本金分布；
- 实现显式 ER、BA、SW 可借贷拓扑约束；
- 比较稀疏度、平均度、聚类和度异质性对级联的影响；
- 继续比较 uniform/biased 收入与多种增长规则。

## 阶段报告规则

- 每次形成重大阶段结论时，派生新的 Markdown 与 Word 图文报告；
- 新报告使用新版本号，不覆盖任何旧报告；
- 报告必须写明模型版本、完整参数、样本数、随机种子范围、统计检验、图片和证据路径；
- 明确区分“出现大级联”“重尾”“临界转变”“严格 SOC”四种不同结论。

## 最终完成门槛

只有在以下项目均有直接实验或明确不可识别结论时，才结束总目标：

1. 严格尾部检验和有限尺寸分析完成；
2. 关键转变区经过高重复细扫；
3. `c` 与检查间隔效应完成解耦；
4. 初始本金、收入分配、消费参数、增长机制和显式拓扑均有对照；
5. 关键清算规则有稳健性消融；
6. 最终报告能够明确回答当前约束下 SOC 存在、不存在或不可识别，并给出证据边界。

## 2026-06-04 12:20:00 CST：启动第二阶段

证据检查：

- 当前详细框架报告：`docs/credit_soc_project_framework_detailed_analysis_20260604.md`
- 当前综合报告：`docs/credit_soc_autonomous_experiment_report_20260604.md`
- 当前结果显示级联转变和重尾迹象，但严格 SOC 证据不足。

决策：

- 启动三条并行实验线；
- CPU 实验每条分支最多同时运行 3 个重任务；
- 保留所有旧产物，新结果写入版本化目录；
- 主协调只在检查 worker 报告和原始证据后集成结论。

下一检查点：

- 三条 worker 实验线完成协议审计、代码计划和首批可运行实验。

## 2026-06-04 12:32:00 CST：主协议事件时序与重复违约审计

审计数据：

- `results/credit_soc_continue_income_c020_random_focus_20260604_v1/avalanche_events.csv`
- `results/credit_soc_continue_income_c020_random_focus_20260604_v1/run_summary.csv`

关键结果：

- 180 个 run 共 32826 个 avalanche，其中 427 个达到 10% 大崩塌阈值；
- 大 avalanche 的发生期中位数为 173，最早为第 51 期，不存在第一期大 avalanche；
- 大 avalanche 所在 period 的 `K_t` 中位数为 28，范围为 20-35，而第一期计划 `K_1=200`；
- 大 avalanche 前活跃信贷中位数为 692，小 avalanche 前为 1225；
- 每个 run 的 `total_collapse_size` 都超过 `N=200`，最大达到 3021，说明同一节点跨 period 重复违约是长期序列的重要组成部分。

判断：

- 当前 `c=0.20` 主协议的大事件不能简单归因于第一期大批量冲击；
- 大事件更接近长期演化后、较低活跃信贷存量和 `K_t=20-35` 下的脆弱状态；
- 但重复违约可能显著影响 avalanche 频率与尾部，必须通过永久退出、重置和唯一违约口径消融。

决策：

- 严格 SOC 分支优先围绕 `K=20-35` 和后期事件做统计与有限尺寸检验；
- 机制分支优先检查重复违约与节点退出机制；
- 显式拓扑和因素分支优先使用 `K=20-26` 的边界协议。

## 2026-06-04 12:36:00 CST：收入内生 c 细扫预审计

主协调使用独立随机种子、`N=200`、200 periods、`validate_accounting=True`，对 lognormal/pareto + biased + random 做每点 20 runs 的小规模预审计。

run 级大崩塌率：

| 本金分布 | c=0.12 | c=0.14 | c=0.16 | c=0.18 | c=0.20 |
| --- | ---: | ---: | ---: | ---: | ---: |
| lognormal | 0.00 | 0.00 | 0.05 | 0.40 | 0.80 |
| pareto | 0.00 | 0.00 | 0.00 | 0.05 | 0.10 |

判断：

- lognormal 场景在 `c=0.16-0.20` 呈连续、随机性的转变，而不是单个参数点突变；
- pareto 的转变更晚且 seed 方差更大，本次 `c=0.20` 的 20-run 比例明显低于旧 60-run 结果；
- 正式细扫必须增加重复数、给出置信区间，并避免把一次样本比例当作稳定临界点。

## 2026-06-04 12:39:00 CST：有限尺寸预审计

主协调使用 lognormal + biased + random、`c=0.18`、200 periods、每个 `N` 10 runs、`validate_accounting=True` 做预审计：

| N | run级10%大崩塌率 | 平均最大avalanche占比 | 最大avalanche占比 |
| ---: | ---: | ---: | ---: |
| 100 | 0.90 | 0.1200 | 0.160 |
| 200 | 0.40 | 0.0930 | 0.130 |
| 500 | 0.00 | 0.0756 | 0.088 |
| 1000 | 0.00 | 0.0758 | 0.094 |

判断：

- 人为设置的 10% 大崩塌率对系统规模高度敏感；
- 最大 avalanche 占比随 `N` 增大而下降，当前小样本结果不支持直接声称存在系统尺度崩塌；
- 正式有限尺寸分析必须检查绝对 cutoff、矩标度和尾部，而不能仅比较 10% 阈值事件率。

## 2026-06-04 12:43:00 CST：avalanche 时间分离审计

主协调对现有长期 avalanche 序列计算事件期占比、相邻事件等待时间和规模一阶相关：

- `c=0.20` 聚焦协议中，91.2% 的 period 发生 avalanche；
- lognormal、uniform、pareto 的事件期占比分别为 99.15%、97.83%、76.58%；
- 97.0% 的相邻 avalanche 等待时间仅为 1 period；
- 相邻 avalanche size 的一阶相关系数约为 0.713；
- 固定 `K=20` 与 `K=30` 的 size 一阶相关约为 0.801 和 0.916。

判断：

- 高风险协议中的 avalanche 并非时间上充分分离的独立稀有事件，而接近持续活跃的失败状态；
- 大小重尾可能与强时间相关、重复违约和持续脆弱共同形成；
- 即使严格尾部拟合不拒绝 power-law，也不能忽略时间分离不足对 SOC 解释的削弱。

决策：

- 新增 avalanche 动态分支，记录传播代数、持续时间、分支比、等待时间和 size-duration 关系；
- 严格 SOC 和机制分支必须把持续活跃态与 SOC avalanche 区分开。

## 2026-06-04 12:48:00 CST：序列平稳性审计

主协调将现有事件按 run 的 period 四分位窗口聚合，发现 avalanche 分布随时间持续漂移：

- `c=0.20` 聚焦协议的平均 avalanche size 从 Q1 的 3.49 上升到 Q4 的 10.86；
- 同协议的大事件率从 Q1 的 0 上升到 Q4 的 3.54%；
- 固定 `K=20` 的平均 avalanche size 从 2.23 上升到 7.56；
- 固定 `K=30` 的平均 avalanche size 从 3.58 上升到 13.04，Q4 大事件率达到 36.27%。

判断：

- 当前汇总尾部分布混合了明显非平稳的早期、中期和后期状态；
- 该过程可能仍在持续积累不平等与脆弱性，而不是进入稳定的临界稳态；
- 对全部 period 事件直接做 iid 尾部拟合会夸大证据强度。

决策：

- 严格统计分支必须增加时间窗口、burn-in 或更长运行的平稳性检查；
- 动态与机制分支检查节点退出、重置和清算规则是否恢复平稳性。

## 2026-06-04 12:52:00 CST：1000-period 长程行为预审计

主协调对 `N=200`、lognormal + biased + random、`validate_accounting=True` 运行每场景 5 个 1000-period 长序列。最后 250 periods 的结果：

| 协议 | 大事件率 | 平均avalanche size | 平均活跃信贷 | 最终净资产Gini范围 |
| --- | ---: | ---: | ---: | --- |
| fixed K=20 | 0.196 | 17.32 | 185.1 | 0.975-0.991 |
| fixed K=30 | 0.962 | 25.78 | 102.5 | 0.987-0.991 |
| income c=0.18 | 0.399 | 18.72 | 150.6 | 0.970-0.995 |
| income c=0.20 | 0.614 | 20.26 | 120.2 | 0.982-0.989 |

每个场景后期均接近每期发生 avalanche。随着演化推进：

- 净资产分化接近极端状态；
- 活跃信贷持续下降；
- avalanche 频率和规模上升；
- 同一节点持续重新参与并重复违约。

阶段性判断：

> 当前基线高风险协议的长程行为更接近“低活跃信贷、高财富不平等、持续重复违约”的退化失败吸引态，而不是稳定的稀有 avalanche 临界态。

这构成对严格 SOC 解释的实质性反证，但仍需严格统计、传播动态及机制消融确认。240/400-period 结果应解释为有限时域转变过程，不能直接作为长期稳态结论。

## 2026-06-04 12:46:50 CST：因素与显式拓扑分支完成

第二阶段因素与显式拓扑分支完成首批固定时域扫描：

- 协议：`N=200`、固定 `K=20`、240 periods、`continue_after_avalanche`、逐期会计校验；
- 31 个场景、248 个 run、51,401 个 avalanche 事件；
- 显式 ER/BA/SW 无向机会图精确匹配平均度 6/12/24，实际信贷暴露仍为有向带权网络；
- 同平均度 12 下 ER/BA/SW 平均最大 avalanche 均约为 15-16，当前重复数下没有稳定家族排序；
- biased 收入和 random 增长的效应明显强于机会图家族；提高 `a` 到 0.04 在该固定时域下减弱级联，`b=0.10-0.30` 未显示稳定效应。

证据：

- `docs/credit_soc_phase2_factors_topology_report_20260604_v1.md`
- `results/credit_soc_phase2_factors_topology_20260604_v1/`

判断：

- `project.md` 的初始本金、收入分配、消费参数、增长规则和显式拓扑关注点已获得首批统一协议对照；
- 该扫描每场景仅 8 runs 且固定为 240 periods，只能解释因素方向和有限时域差异，不能外推长期稳态拓扑排序。

## 2026-06-04 12:51:52 CST：模型变量口径审计与新版图文报告

根据用户对“驱动强度 `c`”和模型框架可解释性的审计要求，已完成：

- 将 `c` 明确定义为上一期总收入到下一期计划信贷尝试批量的转换系数：`K_t=round(c*Y_(t-1))`；
- 明确严格量纲为“计划尝试数/收入单位”，只因单位归一化才作为无量纲比例使用；
- 明确 `c` 不是单笔冲击、实际投资支出比例或已分离出的纯驱动速度；
- 区分计划尝试、实际尝试、成功发放、实际投资支出、活跃信贷和累计发放量；
- 补齐基线全部参数、run/event 输出字段、统计标签，以及显式拓扑和机制扩展变量字典；
- 明确基线内部 `cascade_steps` 等于已处理违约节点数，不是传播 duration。

更新产物：

- `project.md`
- `docs/credit_soc_project_framework_detailed_analysis_20260604_v2.md`
- `docs/credit_soc_project_framework_detailed_analysis_20260604_v2.docx`

验证：

- 代码字段审计确认 `CreditNetworkParams` 与 `RunResult` 全部字段均在新版报告中解释；
- 12 张图片路径全部存在并内嵌 Word；
- DOCX 压缩结构无错误，LibreOffice 正常渲染为 33 页 PDF；
- 基线 sanity check 与当前 phase-2 脚本静态编译通过。

## 2026-06-04 13:00:56 CST：Phase-2 正式结果交叉审计与低驱动长期搜索启动

主协调器已独立对账四条正式分支的关键原始结果：

- 严格 SOC 分支：1440 个 run、28 个场景、368042 个 avalanche 与 run 汇总逐项一致；所有新 run 开启会计校验，现金残差为 0；
- 动态分支：6/6 baseline equivalence 通过，wave size 总和与 avalanche size、wave 数与 duration 均为 0 mismatch；
- 机制分支：264 个 run、22 个场景、537387 个事件对账；reference 与 credit-only `check_only_b10` 逐 seed 全字段一致；非 reset 现金残差小于 `1e-12`，reset 外部现金流恒等式残差为 0；
- 因素拓扑分支：248 个 run、31 个场景、51401 个事件对账；机会图边数、平均度、run/event 最大规模和事件计数均为 0 mismatch。

严格尾部最终方法审计发现并修正两项不会增强 SOC 证据、但会影响可复现性的统计实现问题：

1. 首版 `alpha` 搜索上限为 12，多个陡尾拟合碰到上限；已改为 50；
2. 首版最多抽取 80 个 `xmin` 候选，`finite_fixed N=1000,K=140` 的穷举最优 `xmin=98` 被近似为 94；已改为对当前数据实际穷举全部候选。

修正版正在新目录 `results/credit_soc_phase2_strict_soc_20260604_v1/analysis_final_allxmin_v3/` 运行，旧结果保留。严格 worker 还独立验证了离散幂律 MLE、bootstrap 重选 `xmin`、离散指数 MLE和拒绝采样器。

为排除现有细扫只聚焦转变/高风险区域而遗漏低驱动 SOC 候选，已启动 `stationarity-search` 分支：

- 搜索 income `c=0.02-0.20` 与 fixed `K=2-30`；
- 使用 lognormal/pareto、biased、random、continue、period_end；
- 每场景至少 12 seeds、2000 periods；
- 按晚期 occupancy、等待时间、lag-1、漂移、活跃信贷和 Gini 区分无事件稳定区、稀有平稳事件候选和持续失效区；
- 只有发现可信候选时才追加有限尺寸验证。

新增用户导航页：

- `docs/credit_soc_key_results_dashboard.md`

导航页 24 个本地链接和必需章节均已通过自动校验。当前工作判定仍为：严格 SOC 不受支持，高风险区最符合持续失败/过载吸引子；最终结论等待修正版尾部统计和低驱动长期搜索。

## 2026-06-04 13:11:48 CST：模型事件拆分与严格统计变量口径审计 v3

针对用户指出的“驱动强度 `c` 和当前模型框架细节未解释清楚”，继续审计了与 `c` 类似、容易造成结论误读的变量，并更新 `project.md`：

- `c` 继续严格定义为 `K_t=round(c*Y_(t-1))` 中的收入到计划信贷尝试批量转换系数，不称为已分离的纯驱动速度；
- 将一次事件拆成 `initial_default_count`、`propagated_default_count=collapse_size-initial_default_count`、`propagation_share` 和 `single_trigger_event`；
- 明确 `single_trigger_event` 仍不等于外生单微观冲击，即使 `K=1`，全系统 `period_end` 流量结算仍可能同时产生多个初始违约；
- 定义 wave、duration、propagation depth、branching、occupancy、waiting、lag-1、unique/repeated default 和长期稳态诊断；
- 区分旧版固定 `xmin=2` 连续 Pareto 描述性 `alpha` 与第二阶段自动 `xmin` 离散幂律 `alpha`；
- 定义 KS bootstrap、Vuong、bounded power law、cutoff/moment scaling、实际回收与 reset 外部现金流。

派生新版报告，未覆盖 v2：

- `docs/credit_soc_project_framework_detailed_analysis_20260604_v3.md`
- `docs/credit_soc_project_framework_detailed_analysis_20260604_v3.docx`

验证：V3 Word 内嵌 12 张实验图，DOCX 压缩结构无错误，LibreOffice 正常渲染为 36 页 PDF；渲染文本中可检索新增事件拆分、传播动态、严格离散幂律和 reset 外部现金流定义。

## 2026-06-04 13:17:10 CST：严格 SOC 最终 v5 完成并独立复算

严格统计分支最终产物已稳定在：

- `results/credit_soc_phase2_strict_soc_20260604_v1/analysis_final_v5/`
- `docs/credit_soc_phase2_strict_soc_report_20260604_v1.md`
- `results/credit_soc_phase2_strict_soc_20260604_v1/method_audit_final_v4.md`

主协调器独立复算确认：

- 39 个 series 中，无界离散 power law 为 26 个不拒绝、13 个拒绝；bounded 为 27 个不拒绝、12 个拒绝；
- exponential 在 21/39、lognormal 在 10/39 中以描述性 `p<0.10` 优于 power law；
- 39 个 lognormal 优化全部成功且无边界命中；自动 `xmin` 的离散 `alpha` 为 4.947-27.567；
- 28 个事件拆分场景和 8 个有限尺寸场景全部满足 `initial + propagated = total`；
- 近线性有限尺寸总规模主要由同步 initial defaults 的广延增长主导，传播只占约 12%-15%。

正式报告中已移除旧 `16/23`、`9/11` 与 `alpha<=12` 口径。严格统计分支状态改为边界完成；低驱动长期扫描的 fixed/income 两个正式 shard 正在运行。

## 2026-06-04 13:27:00 CST：低驱动长期搜索与最终综合判定完成

- stationarity 正式扫描完成：42 场景、504 runs、1008000 periods、773242 events；11/11 对账通过，`candidate_count=0`。
- 分类结果为 36 个 `drift_or_persistent_failure` 和 6 个 `sparse_but_nonstationary`；不存在遗漏的稀有、分离、近平稳 SOC 候选。
- `K=1` 的 late occupancy 为 0.0275-0.0354，事件在样本中均为单 initial default，但 late P99 仅 3.00-3.69、没有 10% 大事件，late/early active-credit 比为 7.17-7.36。
- 主协调器完成最终 7 项完成门槛审计。当前约束下严格 SOC 不存在，属于经验判定；该结论不外推为所有信贷网络模型的数学不可能性。
- 最终综合 Markdown/Word 与完成性审计已生成，旧版本均保留。

最终路径：

- `docs/credit_soc_phase2_comprehensive_report_20260604_v1.md`
- `docs/credit_soc_phase2_comprehensive_report_20260604_v1.docx`
- `docs/credit_soc_phase2_completion_audit_20260604_v1.md`
- `results/credit_soc_phase2_comprehensive_20260604_v1/`
