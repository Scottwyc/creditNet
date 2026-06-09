
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

P: 我们这个探索其实要考虑很多不同场景条件，不同本金初始化、不同支出机制、不同分配机制、不同网络拓扑结构，那么，请你根据这些不同场景条件进行完备的参数扫描，分析里面的级联失效和SOC，最终得到关于级联失效规模，关于SOC，它们各自的相图；另外，也要有各个场景下，级联失效规模和频率的关系图，方便直接观察是否存在SOC。请你进行完备实验，整理详细分析报告。你可以启动 tmux codex worker并行推进；请尽量快速进行，时间有限。

P: 请你给模拟结果进行可视化，取一些典型例子的场景，渲染出timestep/期 下的信贷网络演化过程，要能够体现信贷增强、违约等过程。请你分配 tmux codex worker来推进这个支线，主进程要和我继续讨论。

生成动画gif


P: 你现在要补充说明，不同场景的扫描实验中，固定的参数基线都是什么样的，而不仅仅是扫描参数的变化，请你在各个相关报告中补充说明。
另外，一个提问，现在的网络拓扑限制，是指初始化就设置了允许连边的拓扑结构边界吗？还是说后续增加信贷连边的过程符合网络拓扑结构



## 分析
P: 你解释一下你的级联失效是怎么定义的，你认为的SOC要满足什么条件？请在相关文档中补充详细解释


Q: ccdf 是什么？
A: • CCDF 是 Complementary Cumulative Distribution Function，中文通常叫 互补累积分
  布函数 或 生存函数。

  在你的级联失效图里，如果横轴是级联规模 s，那么：

  CCDF(s) = P(S >= s)

  意思是：一次级联事件的规模 S 至少达到 s 的概率。

  为什么用 CCDF 看 SOC：

  - 它比普通频率直方图更稳定，尤其适合看尾部大事件。
  - 如果级联规模服从幂律，CCDF 在 log-log 图上通常会接近一条直线。
  - 但注意：CCDF 近似直线只能说明可能有重尾或幂律相似现象，不能单独证明 SOC。

  在报告里的“级联失效规模-频率关系图”，例如 ccdf_by_c.png，就是在看不同 c 下：

  级联规模 >= s 的事件比例

  也就是大级联尾部有多厚。

Q: 近持续失败/饱和场景，你是怎么定义的？对应什么样的指标？

A: • “近持续失败/饱和场景”是我在这轮完备扫描里用的一个操作性标签，对应指标是：

  event_occupancy = 该 scenario 中发生 avalanche 的 period 数 / 该 scenario 总完
  成 period 数

  当前基线是 period_end 检查，并且每个 period 最多记录一次 avalanche，所以
  event_occupancy 的取值在 0-1 之间。

  我在报告中定义：

  近持续失败/饱和场景 = event_occupancy >= 0.80

  也就是：一个场景下，至少 80% 的 period 都发生了违约/级联事件。

  例如本轮每个 scenario 是 3 个 seed、每个 run 最多 120 periods，所以总观察窗口
  大约是：

  3 * 120 = 360 periods

  如果其中约 288 个以上 period 都发生 avalanche，那么这个 scenario 就被标为“近持
  续失败/饱和”。

  它不是 SOC 证据，而是一个排除信号。因为严格 SOC 需要“慢驱动、快 avalanche、事
  件之间有分离”，而 event_occupancy 接近 1 表示系统几乎每期都在违约，更像持续过
  载或持续失败状态。

  在 SOC 快筛里对应的 gate 是：

  gate_not_saturated = event_occupancy < 0.80

  如果 event_occupancy >= 0.80，就认为它没有通过“非饱和/非持续失败”门槛。

  这轮结果里，随着 c 增大，饱和场景明显增加：

  c=0.10: 43 / 1000 个场景近饱和
  c=0.50: 653 / 1000 个场景近饱和
  c=0.80: 966 / 1000 个场景近饱和

  所以高 c 区域虽然大级联很多，但主要表现为“几乎每期都崩”，不是稀疏、分离、长期
  稳定的 SOC avalanche。


Q: 当前实验里面，每期内部会有小的时间步，小的时间步里面对应信贷增长，那么持续失败的级联失效过程中，上一期失效节点后，下一期也不会恢复对吗？

A: • 不完全对。当前基线实现里，continue_after_avalanche 下上一期失效节点不会永久退
  出，也不会保持一个“已失败/破产”状态到下一期。

  更准确地说：

  1. 在某一期 period_end，若节点违约，会进入本期级联清算。
  2. 清算会移除与该节点相关的信贷暴露：
      - 它作为债务人的负债会被清掉；
      - 债权人的贷款资产会被减记；
      - 若 wipe_defaulted_assets=True，它自己持有的贷款资产也会被清掉。

  3. 级联结束后，这个节点下一期仍然可以继续参与：
      - 可以获得收入；
      - 可以消费/投资；
      - 可以作为贷款人或借款人参与信贷增长；
      - 不会因为上一期违约而自动退出系统。

  所以当前“持续失败/近饱和”不是指“同一批节点失败后永远不恢复、一直挂在那里”，而
  是指：

  系统在很多连续 period 的期末都会重新产生违约/级联事件

  并且因为违约节点没有永久退出，也没有彻底外生重置为健康主体，所以同一节点可能在
  多个 period 中反复违约，这就是报告里提到的：

  repeat_default_share

  也就是重复违约占比。

  因此当前机制更像：

  违约清算 -> 节点继续留在系统 -> 下一期继续借贷/收入分配 -> 可能再次违约

  不是：

  违约 -> 永久破产退出

  也不是：

  违约 -> 外部注资完全重置

  后两种只在机制消融实验里作为 permanent_exit 或 reset 类对照机制讨论过。当前基
  线持续失败的核心含义是“事件几乎每期都发生、重复违约很高、系统处在过载吸引子”，
  不是“节点一旦失败就永不恢复”。


Q: 目前机制的问题，采取那种？：
1.  违约清算 -> 节点继续留在系统 -> 下一期继续借贷/收入分配 -> 可能再次违约
2.  违约 -> 永久破产退出
3.  违约 -> 外部注资完全重置

NOTE 
• 是的，已经试验过，但范围不是全量参数扫描，而是 Phase-2 机制稳健性实验里的两个
  代表性协议对照：high_risk_income_c020 和 boundary_fixed_k20。记录在 class/
  creditNet/docs/credit_soc_phase2_mechanism_report_20260604_v1.md:74 和 class/
  creditNet/results/credit_soc_phase2_mechanism_20260604_v1/
  longrun_20260604_1244_r2/analysis_summary.md:28。

  核心结果如下，按原报告的 10%N 大级联阈值：

   场景                机制                结果
  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   high_risk_income    permanent_exit      12 次运行中大级联率 0.000；事件数
   _c020                                   1415；平均事件规模 1.69；最终平均活
                                           跃节点只剩 1.0。说明永久退出会耗尽系
                                           统，级联变小并逐渐消失，不是 SOC。
  ──────────────────  ──────────────────  ──────────────────────────────────────
   high_risk_income    reset_to_initial    大级联率 1.000；事件数 11574；平均事
   _c020               _cash               件规模 18.80；重复违约占比 0.990；最
                                           终活跃节点 200；外部 reset 现金流约
                                           136438。说明 reset 让系统持续活跃，
                                           但靠外部注入/重置维持，表现更像持续
                                           高频失效，不是封闭系统 SOC。
  ──────────────────  ──────────────────  ──────────────────────────────────────
   boundary_fixed_k    permanent_exit      大级联率 0.000；事件数 1531；平均事
   20                                      件规模 1.56；最终平均活跃节点 1.25。
                                           同样是节点被退出机制耗尽。
  ──────────────────  ──────────────────  ──────────────────────────────────────
   boundary_fixed_k    reset_to_initial    大级联率 0.000；事件数 8228；平均事
   20                  _cash               件规模 2.15；重复违约占比 0.889；最
                                           终活跃节点 200；外部 reset 现金流约
                                           7966。说明 reset 保持失败反复发生，
                                           但在这个固定 K 场景下事件偏小。

  所以结论是：这两种机制已经作为对照试过。permanent_exit 会消除重复违约，但代价
  是系统人口被逐步清空；reset 会保留系统活性，但引入外部现金流，已经不再是原始封
  闭信用网络。因此它们可以作为机制消融说明“恢复/退出规则很重要”，但不能作为当前
  主模型的 SOC 证据。


Q: 每一期内实际上都有timestep小的信贷增长，所以你的阐述是不是有问题？实际上一个期内出现崩塌是正常的；然后每期恢复节点，继续增长信贷，“持续崩溃”不就是SOC? SOC的尺度不久可以是 timestep？

A:• 你的质疑是对的：我之前把“几乎每期都有崩塌”直接称为“持续失败/饱和”时，表述偏
  强，容易误导。

  更准确应当这样说：

  1. 当前模型里，一个 period 内确实包含很多 time_step，每个 time_step 至多新增 1
     单位信贷。当前基线只在 period_end 做支出、收入分配、违约检查和级联清算。因
     此，“某一期内出现崩塌”是正常的慢驱动-快清算循环，不表示系统终止。

  2. 每期清算后节点继续参与下一期，这本身也不是问题。SOC 里也可以是“加沙粒-雪崩-
     再加沙粒”的反复过程。所以“每期都有 avalanche”不能单独作为否定 SOC 的理由。

  3. 但“持续崩溃”也不能自动等同于 SOC。它只能说明系统处在高活动状态。要叫 SOC，
     还需要看到：
      - avalanche 规模跨尺度分布，而不是集中在小规模或接近全系统规模；
      - 长期统计平稳，事件规模、活跃信贷、Gini 等没有持续漂移；
      - 不依赖把 c 或 K 精细调到某个窄点；
      - 有有限尺寸标度，比如随 N 增大尾部截止也相容地扩展；
      - 幂律/重尾拟合过严格检验，且指数/对数正态等替代分布没有明显更好；
      - 事件规模不是主要由同一批节点跨期重复违约堆出来的。

  关于 timestep 尺度：理论上可以，SOC 的自然尺度完全可以定义在微观驱动步上。但当
  前基线还不是“每个 timestep 后检查 avalanche”的模型，因为单纯新增一笔单位信贷本
  身保持净资产不变，违约主要来自期末支出和收入重新分配。若要做 timestep-SOC，需
  要改成每若干个甚至每 1 个 time_step 就结算/检查，或在每个微步引入收益/损失流，
  然后一旦违约就暂停信贷增长并完成级联清算。

  已有的近似对照是 flow_split_b10_check_q1：在两个代表场景里，把检查/结算推到更
  细粒度后，10%N 大级联率反而降到 0，平均事件规模约 2.21 和 1.78。这说明原来很多
  大崩塌确实受 period_end 批量结算尺度影响。但这还不是全场景的 timestep-SOC 完备
  证明。

  所以我会把口径修正为：event_occupancy≈1 是“可能过载或采样尺度过粗”的诊断指标，
  不是自动否定 SOC 的条件。真正判断 SOC，要回到规模分布、平稳性、有限尺寸标度和
  无精细调参这些联合证据。


P: 那么，你在和刚刚相同的各个场景条件扫描下，基于timestep考查SOC，形成一个对照实验，请更新project.md，并进行完备实验，形成新报告。你可以启动 tmux codex worker并行推进；请尽量快速进行，时间有限。

P: 我觉得timestep尺度下出现了比较明显的幂律现象，只是没有出现大规模的级联失效，对吗？

A:• 对，基本可以这样理解，但要加一个限定：

  timestep 尺度下确实出现了比较明显的小尺度重尾/幂律样貌，尤其在 CCDF 图和尾部拟
  合筛选里能看到一些候选。当前分析表里有：

  - 160 个尾部拟合筛选行；
  - 159 个拟合成功；
  - 28 个场景通过“小尺度尾部候选”筛选；
  - 但严格 SOC 快筛候选数仍是 0。

  关键限制是：这些幂律样貌主要发生在很小的 avalanche 规模范围内。本轮 N=120，
  10%N 大级联阈值是 12 个节点；实际全场景最大事件规模只有 10，小尺度尾部候选里常
  见最大规模大约是 5-6 个节点。因此它更像：

  > timestep 逐步结算后，系统产生了高频、小规模、带重尾/近幂律特征的 micro-
  > avalanche；但没有形成跨到系统尺度的大级联。

  所以不能说“没有 SOC”，只能更精确地说：

  1. 有小尺度幂律样貌/重尾现象；
  2. 没有大规模级联失效；
  3. 还不足以证明严格 SOC，因为严格 SOC 需要更宽尺度范围、有限尺寸 cutoff 随 N
     扩展、长时平稳性、多 seed 稳健性，以及不能被对数正态/指数等替代分布更好解
     释。

  换句话说，timestep 对照把原来 period_end 的大崩塌“打碎”了：大级联消失，但小
  avalanche 的规模分布反而更像有幂律尾部。这是一个值得继续复核的方向。






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

## 2026-06-08 23:25:56 CST：完备场景扫描与 SOC 相图完成

按“不同本金初始化、不同支出机制、不同收入分配机制、不同网络拓扑结构”的要求完成全因子场景扫描和相图分析。

新增脚本：

- `scripts/run_comprehensive_scenario_scan.py`
- `scripts/analyze_comprehensive_scenario_scan.py`

实验范围：

- `N=120`、每 scenario 3 个 seed、每 run 120 periods；
- `c=0.10,0.20,...,0.80`；
- 5 类本金初始化：equal、uniform、normal、lognormal、pareto；
- 2 类收入分配：uniform、biased；
- 2 类增长规则：random、preferential_debt；
- 5 类支出机制：low、baseline、high_income、high_wealth、high_both；
- 10 类拓扑：complete、ER/BA/SW 的 `k=6/12/24`；
- 总计 8000 scenarios、24000 runs、1915216 avalanche events。

核心产物：

- 原始扫描目录：`results/credit_soc_comprehensive_scan_20260608_v1/`
- 相图分析目录：`results/credit_soc_comprehensive_scan_analysis_20260608_v1/`
- 报告：`docs/credit_soc_comprehensive_parameter_scan_report_20260608_v1.md`
- Word：`docs/credit_soc_comprehensive_parameter_scan_report_20260608_v1.docx`，已确认内嵌 17 张图片。

主要结论：

- 级联失效规模相图存在清楚过载转变：全场景平均事件级大级联率从 `c=0.10` 的 0.0001 升至 `c=0.80` 的 0.7576；
- 事件占用率从 0.1913 升至 0.9749，高 `c` 区域主要是近连续失败/过载状态；
- biased 收入、高支出机制、重尾/不均匀本金和部分高连接拓扑显著放大级联；
- SOC 快筛候选数为 0；没有场景同时满足非饱和、转变区、传播占比、尾部可信和替代分布不过强；
- 因此本轮完备场景扫描支持级联失效和过载转变相图，但不支持存在严格 SOC 相图中的稳定临界带。

跟踪口径：

- `avalanche_events.csv` 约 586MB，为逐事件原始表，保留本地但默认不进入 Git；
- Git 只跟踪核心报告、脚本、metadata、摘要表和相图/CCDF 图片。

## 2026-06-09 13:30:15 CST：完成 timestep 尺度 SOC 对照实验

根据“同一场景条件扫描下，基于 timestep 考查 SOC”的要求，新增并完成 `timestep_settle_check` 对照协议。

新增代码与脚本：

- `src/creditnet/timestep.py`
- `scripts/run_timestep_soc_comprehensive_scan.py`
- `scripts/merge_timestep_soc_shards.py`
- `scripts/analyze_timestep_soc_comprehensive_scan.py`

协议口径：

- 保持上一轮完备扫描的场景轴：5 类本金初始化、2 类收入分配、2 类增长规则、5 类支出机制、10 类拓扑、`c=0.10..0.80`；
- 宏观期仍先计算 `K_t=round(cY_{t-1})`，但将一个 period 内的计划信贷拆成最多 `K_t` 个单位 credit `time_step`；
- 每个微步后立即按 `1/K_t` 缩放结算当期支出/收入、检查违约，并在下一次信贷增长前清完整次 avalanche；
- 为快速完成 8000 场景全景对照，v2 设置 `runs_per_scenario=1`、`max_periods=20`、`max_period_length_steps=500`。

核心产物：

- 扫描目录：`results/credit_soc_timestep_scan_20260609_v2/`
- 合并摘要：`results/credit_soc_timestep_scan_20260609_v2/merged/`
- 分析目录：`results/credit_soc_timestep_scan_analysis_20260609_v2/`
- 报告：`docs/credit_soc_timestep_soc_counterfactual_report_20260609_v2.md`

主要结果：

- 8 个 tmux 分片 worker 完成 8000 scenarios、8000 runs，共记录 4539260 个 timestep avalanche 事件；
- 所有场景的大级联率均为 0，最大事件规模为 10/120=0.0833，低于 `collapse_size/N >= 0.10` 的大级联阈值；
- 严格 SOC 快筛候选数为 0；有 28 个小尺度尾部候选，但全部未通过尺度范围门槛；
- 与 `period_end` 同场景对照相比，平均大级联率下降约 0.321，平均事件规模比例下降约 0.102；
- 解释为：timestep 逐步结算/检查会把 period_end 批量结算下的大崩塌切碎成高频、小规模、重复违约事件；这说明上一轮大级联相图对“期末批量结算尺度”高度敏感，不是独立于观测/结算尺度的严格 SOC 证据。

边界说明：

- 本轮是时间有限下的快速全景对照，不是 3 seed、120 periods、无微步上限的最终长时稳态证明；
- 原始 `avalanche_events.csv` 约 1.6GB，保留本地但不进入 Git；Git 只跟踪合并摘要、分析表、图和报告。

## 2026-06-09 15:20:44 CST：导出 timestep 对照 Word 报告

- 已由 `docs/credit_soc_timestep_soc_counterfactual_report_20260609_v2.md` 导出 Word：`docs/credit_soc_timestep_soc_counterfactual_report_20260609_v2.docx`。
- 使用 pandoc 从 `docs/` 目录导出，保持报告中的 `../results/...` 图片相对路径可解析。
- 验证：`.docx` 约 2.0MB，内部 `word/media/` 嵌入 19 张 PNG，与 Markdown 中 19 张图片引用一致。
- 更新 `docs/credit_soc_key_results_dashboard.md`，补充 Word 报告入口。

## 2026-06-09 16:05:17 CST：补充扫描固定参数基线与拓扑机会图口径

- `project.md` 已补充两轮扫描的固定参数基线：`period_end` 完备扫描为 `N=120`、`3 seed/scenario`、`120 periods`、`K_t=round(cY_(t-1))`、`default_threshold=0`、`collapse_threshold_fraction=0.10`、`continue_after_avalanche`、`validate_accounting=True`；`timestep_settle_check` 对照为同一场景轴、`1 seed/scenario`、`20 periods`、`max_period_length_steps=500`、微步后缩放结算/检查/清算、正式 v2 `validate_accounting=False`。
- `docs/credit_soc_comprehensive_parameter_scan_report_20260608_v1.md` 已补“扫描轴与固定参数基线”表，说明除 `c`、本金、收入、增长、支出、拓扑外，哪些机制保持固定。
- `docs/credit_soc_timestep_soc_counterfactual_report_20260609_v2.md` 已补同类固定参数表，并强调 v2 是快速全景对照。
- 拓扑口径已统一：`er/ba/sw` 不是初始化已有信贷暴露网络，而是先生成无向交易机会图；初始信贷暴露矩阵为空，后续 credit `time_step` 只能在机会图允许的节点对之间增长有向、带权、可重复累积的信贷暴露。
- 已重新导出 `project_20260609_v3.docx`，修复标题被正文吞并/缩进的问题；验证“存量”等标题为无缩进 `Heading3`。
- 已重新导出两份报告 Word：完备扫描 Word 内嵌 17 张图片，timestep 对照 Word 内嵌 19 张图片。
