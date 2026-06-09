# 信贷网络自组织临界
## 场景
只考虑简化的个体之间的信贷网络（不考虑银行等）。网络节点对应个体，个体属性包括资产负债表、收入/支出、个体的初始货币量【既是货币资产，也是净资产】；网络连边对应个体之间的信贷关系。
## 机制
	两套机制：存量和流量。
	流量驱动存量。
### 存量
个体的资产负债表，
个体的货币量增量=收入-支出
个体的净资产结算=初始净资产+收入-支出
净资产制约信贷关系的形成

### 流量
#### 个体的支出决策
消费支出量 = a * 财富量 + b * 上一期收入量
投资支出量 = 上一期的借贷量
原始设想中的“计划总投资目标=c*上一期总收入”，在当前实现中具体操作化为每期计划执行的单位信贷time_step数：
`K_t = round(c * 上一期总收入)`。因此，当前 `c` 直接控制的是收入到计划信贷尝试批量的转换，不是实际投资支出比例。
实际成功借贷量不超过计划time_step数；当期成功借入量再作为期末投资支出目标，实际投资支出还会受到期末现金约束。

#### 收入分配方式
总支出决定总收入.
随机分配：每一单位的收入都按照相等的概率任意分配给一个主体
有偏分配：分配的概率与个体的净资产大小成正比。（这样一来，净资产对于资产负债表大小的制约作用也内生体现出来了）

### 信贷关系
在一期之内，可以计划尝试增加与计划投资总量对应的单位信贷暴露。
每个单位信贷暴露从任选两个主体产生，其中贷款人起码要有一个单位的货币，否则此次尝试失败。
建立个体i和个体j之间的信贷关系。比如i向j贷款x，那么i的货币量减少x，同时贷款资产增加x；与此同时，j的货币量增加x，债务负债增加x。相同i和j之间可以反复增加暴露权重。除非发生违约清算，由于没有还款行为，这个暴露会一直存在。
【这里每次成功信贷尝试假定只是一个单位的借贷，令x=1。】


### 信贷网络的初始化
N个节点，个体初始化货币本金，可以根据一个分布进行初始化。
初始化时，每个个体的资产负债表为空。
不同的初始化对结果的影响？比如均匀分布，正态分布，幂律分布等等。可以简化货币本金为离散整数。
这个是第一个关注点，初始净资产分布如何影响临界信贷规模？

（对应信贷增长每次1单位）


### 信贷网络的增长
简化的情形：只考虑信贷关系的不断增长，不考虑还债对应的消失。
（没有还债就没有债务负担，这个简化相当强。但是，尽管如此简化，最终得到的是一个具有特定结构的网络。而这个是第二个关注点：网络结构如何影响临界信贷规模）
信贷增长，就像是不断落下的沙粒。
每一个时间步，根据增长机制，尝试增加节点之间的1单位信贷暴露，比如随机选择一对符合要求的节点建立或加重信贷关系。
因为要形成流量，因此还要有单位时期，每个时期可以有一定数量的时间步，因此有一定量的新增信贷暴露。


### 信贷网络上的流量：收入支出
在每一个时期，每个个体都有支出和收入的操作，这个操作会改变个体的净资产。
收入支出机制的选择？
每一次成功新增信贷暴露的时候，总有一次借贷发生。一期内借到的资金以在本期作为投资支出为目标；当前实现中实际投资支出受期末现金约束。
一期的消费支出按照依赖财富的自发支出和依赖收入的引致支出来确定，都是线性关系
一期的总收入就是总支出，然后按照特定分配方式分配到每个个体。分配方式有随机分配和偏好依附的分配（富者愈富）。
第三个关注点：不同的分配方式如何影响临界信贷规模

### 信贷网络的级联失效
当前项目同时保留两种观测协议：

1. **基线 `period_end` 协议**：一级联失效是一次 `period_end` 事件。一个 `period` 先执行本期计划的 `K_t` 个单位信贷尝试，再完成期末投资/消费支出、收入分配和净资产更新；只有在这个期末检查点，才判断是否发生违约和级联。
2. **timestep 对照 `timestep_settle_check` 协议**：一个宏观 `period` 仍先由 `K_t=round(cY_(t-1))` 给出计划微步数，但该期被拆成 `K_t` 个微观 credit `time_step`。每个 `time_step` 至多新增 1 单位信贷，随后立刻进行一次按 `1/K_t` 缩放的投资/消费支出结算、收入分配、违约检查和完整级联清算。若触发 avalanche，则暂停信贷增长，先把清算队列处理完，再进入下一个 `time_step`。

因此，`period_end` 报告里的 avalanche 是“整期批量结算后的事件”，而 timestep 对照报告里的 avalanche 是“单个 credit 微步之后结算检查出的事件”。两者使用相同的净资产违约条件和清算规则，但事件采样尺度不同，不能把两个协议下的 `event_occupancy` 直接混为同一个统计量。

违约判定使用净资产：

```text
W_i = cash_i + loan_assets_i - debt_liabilities_i
default_i = 1(W_i < default_threshold)
```

当前基线中 `default_threshold=0`，且是严格小于零才违约，净资产等于零不违约。

在 `period_end` 协议中，一次记录的 avalanche / collapse / 级联失效按以下步骤定义：

1. `period_end` 流量结算后，同时找出所有已经满足 `W_i < default_threshold` 的节点，记为初始违约集合 `I_0`。
2. 将 `I_0` 放入违约清算队列。某个债务人 `j` 被清算时，所有指向 `j` 的贷款资产 `E_ij` 被减记，债权人 `i` 的贷款资产下降，`j` 的债务负债同步解除。
3. 若 `wipe_defaulted_assets=True`，还会清除违约节点 `j` 持有的贷款资产 `E_jk`，并解除对应借款人 `k` 的负债。
4. 每处理一个违约节点后重新计算全体净资产；如果新的债权人因资产减记而转为负净资产，则加入清算队列。
5. 队列为空时，本次级联结束。现金在级联清算中不被额外扣除；级联传播来自贷款资产和债务负债的表内减记。

因此，一次事件的规模不是“损失金额”，而是本次 `period_end` 清算中被处理的不同违约节点数：

```text
collapse_size = 本次事件中违约并被清算的不同节点数
collapse_fraction = collapse_size / N
```

大级联标签为：

```text
critical_event = 1(collapse_fraction >= collapse_threshold_fraction)
```

常用阈值 `collapse_threshold_fraction=0.10` 只是人工分类阈值，表示“本次事件波及至少 10% 节点”。它不参与模型演化，也不是严格临界或 SOC 的证明。

还必须区分：

```text
initial_default_count = |I_0|
propagated_default_count = collapse_size - initial_default_count
propagation_share = propagated_default_count / collapse_size
```

如果一次事件的规模主要来自 `initial_default_count`，说明它更多是同一个结算检查点同步出现的多源违约；只有 `propagated_default_count` 才表示信贷网络清算传播新增的违约。即使 `initial_default_count=1`，该节点也不是外部人为施加的微观冲击，而是在流量结算后内生出现的初始违约。

我们把问题简化为：无论级联波及多少节点，整次清算都在同一个 `period_end` 内完成。它没有新的物理时间跨度；后续动态分析里的传播代数只是清算队列诊断，不是新的 `time_step` 或 `period`。

在 `timestep_settle_check` 协议中，上述清算队列仍是瞬时完成的算法事件，但检查点变为单个 credit `time_step` 后的微结算时刻。此时一次 avalanche 的字段解释为：

```text
period = 该事件所在的宏观期
micro_step_in_period = 该宏观期内第几个 credit time_step 后触发
time_steps_completed = 截至该事件前累计实际尝试过的 credit time_step 数
event_timestep_rate = avalanche_count / time_steps_completed
event_period_occupancy = 有 avalanche 的宏观 period 数 / 完成的宏观 period 数
```

timestep 对照实验中的“高频崩塌”应优先看 `event_timestep_rate`，而不是只看每个宏观期是否至少发生过一次事件。因为在 timestep 协议下，一个宏观期内可以发生多次 avalanche。

### 信贷网络的自组织临界分析
本项目中，“自组织临界”不是简单地观察到一次大崩塌，也不是看到崩塌规模频率图在 log-log 坐标下近似直线。我们采用更严格的操作性定义：系统在没有把外部控制参数精细调到狭窄临界点的情况下，通过慢驱动和快速级联清算自行进入一个长期统计稳定状态，并在该状态下产生跨尺度、可重复、有限尺寸标度相容的 avalanche 分布。

因此，严格 SOC 至少需要同时满足以下条件：

| 条件 | 本项目中的可检验含义 | 不能用什么替代 |
| --- | --- | --- |
| 无需精细调参 | 在相邻 `c`、固定 `K`、收入/本金/增长机制等参数邻域内仍可观察到同一类临界统计，而不是只在一个窄点出现 | 只在单个参数点出现大级联 |
| 慢驱动、快清算 | 信贷增长发生在 avalanche 之前；一旦进入清算，驱动暂停，事件在同一检查点内完成。`period_end` 协议检查每期末，timestep 协议检查每个微步后；两者都要求清算期间不继续加载信贷 | `c` 很大导致检查点上高频出现大事件 |
| 长期统计稳定 | avalanche 规模、活跃信贷、不平等和事件占用率在 early/late 或窗口比较中没有持续漂移 | 把非平稳 pooled events 直接拿去拟合幂律 |
| 单事件定义可解释 | 事件不应主要由同一检查点多个同步 initial defaults 或跨期/跨微步重复违约主导；需拆分 `initial_default_count`、`propagated_default_count` 与重复违约 | 只看总 `collapse_size` |
| 可信重尾和幂律证据 | 自动选择 `xmin` 的离散/有限支持幂律拟合不过度依赖个别点，替代分布不能系统性更优，指数在 seed 和相邻参数下相对稳健 | 单张 log-log 图、固定 `xmin=2` 的描述性 `alpha`、或 KS 不拒绝 |
| 有限尺寸标度 | cutoff、矩或分布形状随 `N` 的变化与临界传播相容，并且传播新增部分也有相容标度 | 绝对 `collapse_size` 随 `N` 增长，但主要由初始同步违约贡献 |
| 机制稳健性 | 对检查频率、清算规则、恢复/退出机制等合理消融不应完全依赖某个实现细节 | 单一机制下的偶然重尾 |

分层结论必须明确写成：

```text
大级联出现 < 稳健级联转变 < 重尾 < 统计上可信的幂律 < 严格 SOC
```

前一层不能自动推出后一层。特别是，`critical_event` 只是“事件规模超过人工阈值”的标签；“大级联多次稳定出现”只能说明存在稳健级联转变或过载区，不等于 SOC。


## 当前实现的模型变量与口径

### 先说明模型层级与 c（不要把简称误读为纯驱动速度）

当前主模拟器是一个离散时间、带权有向信贷暴露网络。一次完整演化使用四个层级：

```text
scenario：一组固定参数和机制
  -> run：一个随机种子下的完整独立演化轨迹
     -> period：一批单位信贷尝试 + 一次期末流量结算和违约检查
        -> time_step：至多成功新增1单位信贷暴露的一次尝试
```

报告中有时简称“驱动强度”的 `c`，代码字段为 `investment_income_propensity`。它的准确定义是：

```text
K_t = round(c * Y_(t-1))
```

即：`c` 把上一期全系统总收入 `Y_(t-1)` 转换为下一期计划执行的单位信贷尝试数 `K_t`。所以它更准确地是**收入到信贷尝试批量的转换系数**：

- 它不是单笔贷款规模；每个成功 time_step 始终只新增 1 单位信贷。
- 它不是直接施加到净资产上的冲击，也不直接改变违约阈值。
- 它不保证实际成功发放 `K_t` 单位信贷；现金约束可使尝试失败。
- 它也不等于实际投资支出；实际投资支出仍受借款人期末现金约束。
- 在当前 `period_end` 协议中，它同时改变下一次流量结算和违约检查前积累的信贷批量，因此不能把实验中的“`c` 效应”解释成已经分离出的纯驱动速度效应。
- 严格按量纲说，`c` 的单位是“计划信贷尝试数/上一期收入单位”；由于模型把 1 个货币单位、1 个信贷单位和 1 次单位尝试统一归一化，实验中可把它作为无量纲比例使用。

单位信贷建立本身保持贷款人与借款人的净资产不变。因此，只在每个 credit `time_step` 后做 `check_only` 检查而不做流量结算，理论上不会产生新的违约。若要在 timestep 尺度考察 SOC，必须把流量结算也推进到 timestep 后执行；本轮新增的 `timestep_settle_check` 对照正是这一协议。

需要区分三类量：

| 类型 | 例子 | 含义 |
| --- | --- | --- |
| 外生参数 | `N, a, b, c, K, default_threshold` | 在一个 scenario/run 开始前给定 |
| 内生状态和流量 | `C_i,t, E_ij,t, W_i,t, Y_i,t, K_t` | 随模型演化而变化 |
| 观测统计和标签 | `collapse_size, critical_event, Gini, alpha` | 用于记录或分析，不一定反过来影响模型 |

### 个体存量状态

对个体 `i`：

```text
C_i,t = cash，期末持有的货币现金
E_ij,t = exposure，个体i贷给个体j的未清算信贷单位数
A_i,t = sum_j(E_ij,t)，个体i持有的贷款资产
D_i,t = sum_j(E_ji,t)，个体i承担的债务负债
W_i,t = C_i,t + A_i,t - D_i,t，个体i的净资产
```

`E_ij,t` 是带权暴露矩阵。相同主体之间可以反复新增单位信贷，因此“新增1条边”更准确地说是“新增1单位信贷暴露”，不保证新增一条此前不存在的唯一关系。

### 流量变量与参数

```text
Y_i,t = 个体i在第t期获得的收入
Y_t = sum_i(Y_i,t)，第t期总收入，且等于第t期总支出
B_i,t = 个体i在第t期成功借入的信贷单位数
P_i,t = 个体i在第t期的计划消费量
I_i,t = 个体i在第t期的实际投资支出
X_i,t = 个体i在第t期的实际消费支出
S_t = sum_i(I_i,t + X_i,t)，第t期实际总支出，且Y_t = S_t
a = 财富消费倾向
b = 上一期收入消费倾向
c = 上一期总收入转化为下一期计划信贷time_step数量的转换系数
K_t = 第t期计划包含的time_step数量
```

收入内生时期长度定义为：

```text
K_t = round(c * Y_(t-1))
```

在模型的单位归一化下，`c` 可作为无量纲比例使用；更严格地说，它表示每 1 单位上一期收入对应多少次下一期计划信贷尝试。它不直接改变单笔贷款规模；每个 time_step 仍至多发放 1 单位信贷。`c` 越大，在下一次期末流量结算和 `period_end` 违约检查前计划执行的单位信贷尝试越多。

当前代码的单值默认是 `c=0.20`。早期探索曾使用 `0.02、0.05、0.10、0.20` 等低驱动点；后续若按“从 `0.10` 到 `0.80`、步长 `0.10`”重新扫描，则它不是把实际投资支出比例简单放大到 80%，而是把每期计划信贷尝试批量放大。

例如当前常用设置 `N=200`、`initial_income_per_capita=5`，初始参考总收入为 `Y_0=1000`，所以第一期：

| c | 第一时期计划time_step数 K_1 |
| ---: | ---: |
| 0.10 | 100 |
| 0.20 | 200 |
| 0.30 | 300 |
| 0.40 | 400 |
| 0.50 | 500 |
| 0.60 | 600 |
| 0.70 | 700 |
| 0.80 | 800 |

第一期以后，`Y_t` 由当期总支出内生决定，因而 `K_(t+1)` 也会随系统状态变化。`c=0.80` 这类设置意味着一次 `period_end` 违约检查前可能积累更多单位信贷暴露，属于高驱动压力扫描，运行成本和早期过载概率都可能明显高于 `c=0.20`。固定窗口对照实验直接令 `K_t=K`，此时 `c` 不参与时期长度计算。

实验结果中“级联发生在第1期”表示：系统已经先执行第一期计划的 `K_1` 个信贷尝试，再完成第一次期末支出、收入分配和违约检查，并在这次 `period_end` 发现级联；它不表示级联发生在第1个 time_step。

### 一次 period 内的操作量

必须区分以下四个信贷量：

| 量 | 代码/结果字段 | 准确定义 |
| --- | --- | --- |
| 计划尝试数 | `period_length_steps = K_t` | 期初计划执行多少个 time_step |
| 实际尝试数 | 当期 `attempted`；累计为 `time_steps_completed` | 实际进入过多少次尝试循环；若无可用贷款人，基线实现会记录本次失败并提前结束当期后续尝试 |
| 成功发放数 | 当期 `issued_credit`；累计为 `total_credit_issued` | 实际成功新增的单位信贷暴露数 |
| 失败尝试数 | 当期/累计 `failed_credit_events` | 已实际记录的失败尝试；它不包含因提前结束而未再进入循环的剩余计划步数 |

因此通常有：

```text
成功发放数 <= 实际尝试数 <= 计划尝试数 K_t
实际投资支出 <= 成功借入数
当前活跃信贷 <= 累计成功发放信贷
```

其中最后一个不等式来自级联清算会移除既有暴露。

### 消费、投资和收入分配

个体计划消费为：

```text
planned_consumption_i,t
    = a * max(W_i,t, 0) + b * max(Y_i,t-1, 0)
```

计划消费经过随机舍入成为整数。当前实现先支付投资支出，再支付消费支出，并均受现金约束：

```text
investment_spending_i,t = min(C_i,t, B_i,t)
consumption_spending_i,t = min(投资支出后的现金, planned_consumption_i,t)
```

因此，虽然设定目标是“当期借入资金当期支出”，但如果借款人在期内又把现金贷出，实际投资支出可能小于当期成功借入量。总收入严格等于实际总支出，并按多项分布分配：

```text
uniform: p_i,t = 1/N
biased:  p_i,t = [max(W_i,t, 0) + f] / sum_j[max(W_j,t, 0) + f]
```

当前 `income_bias_floor` 为 `f=1`，保证净资产为零或负数的主体仍有非零收入概率。

### 违约、级联与临界事件

当前违约阈值为：

```text
W_i,t < 0
```

注意是严格小于零，净资产等于零不违约。债务人违约后，其对应债权人的贷款资产被减记；若债权人净资产因此转负，则继续传播。当前还会清除违约节点持有的贷款资产，并解除对应借款人的负债。现金在级联中不被扣除。

一次 avalanche 的规模与大崩塌判定为：

```text
collapse_size = 本次period_end级联中违约的节点数
collapse_fraction = collapse_size / N
critical_event = collapse_fraction >= collapse_threshold_fraction
```

当前大崩塌阈值为 `collapse_threshold_fraction=0.10`。它是实验分类阈值，不是模型内生得到的临界点。

### 容易混淆的统计量

- `period_length_steps`：本期计划执行的 time_step 数，即 `K_t`。
- `time_steps_completed`：代码实际执行过的信贷尝试步数；不一定等于成功发放量。
- `total_credit_issued`：从 run 开始以来累计成功发放的单位信贷量。
- `credit_scale_before_cascade`：某次级联前仍然活跃的信贷暴露总量 `sum_ij(E_ij)`；不是累计发放量，也不是唯一连边数。
- `active_credit_after_cascade`：事件表中是该次级联清算后仍然活跃的信贷暴露；run 汇总表中实际保存 run 结束时的活跃信贷，与 `final_active_credit` 相同。
- `collapse_size`：在事件表中表示单次 avalanche 规模；在 run 汇总表中表示该 run 的最大 avalanche 规模。
- `critical_event`：在事件表中表示该次 avalanche 是否为大崩塌；在 run 汇总表中表示该 run 是否至少发生过一次大崩塌。
- `total_collapse_size`：一个 run 中各次 avalanche 规模之和；同一主体可在不同 period 再次违约并被重复计数。
- `initial_default_count`：某次期末结算后、级联传播开始前已经净资产低于阈值的节点数。
- `avalanche_count`：一个 run 中发生的 avalanche 事件数。
- `ended_by_default`：该 run 是否曾发生过违约；在 `continue_after_avalanche` 下不表示 run 当时终止。
- `first_cascade_period` / `first_cascade_time_steps`：首次 avalanche 所在期和此前累计尝试数；若 run 中无 avalanche，当前实现记录为 0。
- `periods_completed`：run 实际完成的 period 数。
- `last_period_length_steps` / `max_period_length_steps`：最后一期和整个 run 中最大的计划 `K_t`。
- `initial_total_money` / `final_cash_total`：该 run 抽样得到的初始现金总量与最终现金总量；基线模型中二者应相等。
- `total_income_last_period`：最后完成 period 的总收入，不是整个 run 的累计收入。
- `initial_money_gini` / `final_net_worth_gini`：初始现金和最终净资产的不平等度；最终净资产含负值时，当前 Gini 实现会先整体平移到最小值为 0。
- `period_history`：可选的逐 period 诊断记录；`avalanche_history`：逐 avalanche 事件记录。
- `params`：该 run 使用的完整 `CreditNetworkParams` 参数快照；用于复现，不是随 run 演化的状态。
- `seed`：控制初始本金抽样、信贷对象选择、消费随机舍入和收入多项分配的随机种子。
- `max_collapse_size`：一个 run 内最大的单次 avalanche size；当前基线 run 汇总中的 `collapse_size` 与它数值相同。
- 基线 `resolve_cascade` 内部的 `cascade_steps` 当前只是已处理违约节点数，数值上等于该次 `collapse_size`，不是 avalanche 的传播持续时间或代数。

### 级联事件内部的拆分口径

一次 `period_end` 先完成全系统流量结算，再同时识别所有净资产低于阈值的节点，最后才沿信贷暴露传播损失。因此，一次记录的 avalanche 不一定来自一个微观触发点，必须拆成：

| 量 | 定义 |
| --- | --- |
| `initial_default_count = I_0` | 流量结算和收入分配后、网络传播开始前已经满足 `W_i < default_threshold` 的节点数 |
| `propagated_default_count = P` | 因其他节点清算和贷款资产减记而新增的违约节点数，定义为 `collapse_size - initial_default_count` |
| `collapse_size = S` | 本次事件中最终被处理和清算的不同节点总数，满足 `S = I_0 + P` |
| `propagation_share` | `P / S`；衡量最终事件规模中真正由网络传播新增的比例 |
| `single_trigger_event` | `initial_default_count == 1` 的事件标签 |

`single_trigger_event` 只表示传播开始时有一个初始违约节点。它仍不等于一个外生微观冲击：该节点是在全系统统一流量结算后出现的。即使固定 `K=1`，一次 `period_end` 仍可能因全系统支出与收入重分配产生多个初始违约节点。

因此，有限尺寸中 `collapse_size` 随 `N` 增长必须同时检查 `initial_default_count` 和 `propagated_default_count`。如果总规模增长主要来自 `I_0` 随 `N` 的广延增长，就不能把它直接解释为传播过程接近临界。

### 传播动态与长期状态诊断变量

基线模型把整次级联视为一个 `period_end` 内的瞬时事件。第二阶段动态分析为审计传播结构，按 FIFO 清算队列记录“最早被发现的传播代”；这些代数是算法诊断，不是新的物理时间尺度。

| 变量 | 准确定义 | 不能误解为 |
| --- | --- | --- |
| `wave_size_g` | 最早在传播代 `g` 被发现的新违约节点数；第 0 代等于 `initial_default_count` | 一个新的 period 或同步物理波 |
| `duration_generations` | 非空传播代数量，包含第 0 代 | `cascade_steps`、time_step 数或物理持续时间 |
| `propagation_depth` | `duration_generations - 1` | avalanche 发生前经历的 period 数 |
| `branching_ratio_g` | 相邻代规模比 `wave_size_(g+1) / wave_size_g` | 严格临界分支过程的无偏估计 |
| `weighted_branching` | 所有传播新增节点数除以其前序代节点总数 | 单靠接近 1 即可证明 SOC 的指标 |
| `avalanche_period_occupancy` | 观测窗口中发生 avalanche 的 period 数占比；基线每期最多记录一次 | 独立事件发生概率 |
| `waiting_periods` | 同一 run 中相邻 avalanche 检测期索引之差 | avalanche 内部持续时间 |
| `size_lag1_correlation` | 同一 run 内相邻事件规模对汇总后的相关系数，不跨 run 连接 | 因果效应或平稳性证明 |
| `unique_default_nodes` | 一个 run 内至少违约一次的不同节点数 | 所有事件规模之和 |
| `total_default_occurrences` | 一个 run 内所有 `collapse_size` 之和；同一节点可跨期重复计数 | 不同违约节点数 |
| `repeat_default_occurrences` | `total_default_occurrences - unique_default_nodes` | 独立传播产生的新节点数 |
| `repeat_default_share` | `repeat_default_occurrences / total_default_occurrences` | 网络传播占比 |
| `final_active_credit` | run 结束时仍未被清算的活跃信贷暴露总量 | 累计成功发放信贷 |

`occupancy`、等待时间和 lag-1 相关用于识别相邻事件是否高度依赖；Q1-Q4、early/late 或滚动窗口比较用于识别分布是否随时间漂移。它们都只是依赖和非平稳性诊断，不能单独证明或否定 SOC。长期稳态候选至少还需同时满足：关键状态量无持续漂移、事件定义可解释、重复违约不过度主导、终态不退化，以及尾部和有限尺寸证据相容。

### 大级联、重尾、幂律与严格 SOC 的统计口径

详细定义见 [`docs/credit_soc_cascade_soc_definitions_20260608.md`](docs/credit_soc_cascade_soc_definitions_20260608.md)。本节给出分析表和结果字段中使用的最短口径。

以下结论层级不能混用：

| 术语/统计量 | 准确定义 |
| --- | --- |
| 大级联 / `critical_event` | `collapse_size / N` 达到人为设置的 `collapse_threshold_fraction`；只是分类标签 |
| 稳健出现大级联 | 大级联在多个独立 seed/run 及相邻参数点反复出现，并报告重复率或置信区间 |
| 重尾 | 大事件比薄尾模型更常见的分布特征，不要求幂律成立 |
| 描述性 `alpha` | 旧版固定 `xmin=2` 连续 Pareto 近似的初筛指数，只用于画图和探索 |
| 严格离散幂律 `alpha` | 在自动选择的 `xmin` 以上，对离散 avalanche size 最大似然估计的尾部指数 |
| `xmin` | 纳入尾部模型拟合的最小 avalanche size；严格分析中通过最小化 KS 距离自动选择 |
| KS 距离 | 经验尾部 CDF 与拟合模型 CDF 的最大差异 |
| KS bootstrap p 值 | 从拟合模型生成合成数据、每次重新选择 `xmin` 后得到的拟合优度；不拒绝不等于证明幂律 |
| `R = log L_powerlaw - log L_alternative` | 幂律与 exponential/lognormal 等替代分布的对数似然差；`R<0` 表示替代分布拟合更好 |
| Vuong p 值 | 非嵌套模型比较的描述性显著性；事件强相关时不能按 iid 最终检验解释 |
| bounded power law | 显式考虑 `collapse_size <= N` 的有限支持幂律模型 |
| cutoff / moment scaling | P99、最大规模、`E[S^2]/E[S]` 等随 `N` 的增长；需要同时审计初始违约与传播新增规模 |
| 严格 SOC | 无需把外部控制参数精细调到狭窄点，同时满足可信尾部、有限尺寸标度、慢驱动/快 avalanche 分离和长期统计稳定 |

旧版报告中固定 `xmin=2` 的连续 Pareto `alpha` 与第二阶段严格分析中的自动 `xmin` 离散幂律 `alpha` 是不同统计量，数值不可直接比较。任何单个 log-log 图、单个 `alpha`、单个大事件率或“不拒绝幂律”都不足以证明严格 SOC。

严格 SOC 的操作性证据门槛必须联合检查：

1. **无需精细调参**：不是只在一个狭窄 `c` 或 `K` 点出现。
2. **慢驱动/快清算分离**：信贷增长发生在事件前，清算期间不继续加载信贷；长期状态不能退化为持续过载。
3. **长期统计稳定**：事件规模、活跃信贷、Gini、occupancy 等关键统计量没有持续漂移。
4. **事件定义可解释**：`collapse_size` 需要拆分为 `initial_default_count` 和 `propagated_default_count`，不能由同步初始违约或重复违约完全主导。
5. **可信尾部统计**：幂律拟合、替代分布比较、seed/参数邻域稳健性同时可接受。
6. **有限尺寸相容**：cutoff 或矩随 `N` 的变化支持临界传播，而不仅是绝对规模随节点数广延增长。
7. **机制稳健性**：合理清算、检查频率、恢复/退出消融下不依赖单一实现细节。

### 当前实现需要注意的机制含义

- `c` 在 `period_end` 协议中不仅提高计划信贷批量，也扩大下一次期末流量结算和违约检查前形成的总暴露，因此该协议里的 `c` 效应同时包含“更多信贷驱动”和“更大结算/检查批量”；它不是已经分离出的纯速度参数。
- 在 `timestep_settle_check` 协议中，`c` 仍决定一个宏观期计划包含多少 credit 微步，但每个微步后都会结算和检查，因此它更接近“给定宏观收入参考下的微步数量/观测窗口长度”参数，而不再把全部 `K_t` 暴露积累到同一个期末检查点。
- 初始 `initial_income_per_capita` 先按每人四舍五入为整数，再用于构造 `Y_0`、第一期消费参考和第一期 `K_1`，不会向系统额外注入现金。一般公式为 `Y_0 = N * round(initial_income_per_capita)`。
- 支出后形成的收入会重新加入主体现金，总现金在 run 内守恒。
- `continue_after_avalanche` 下，违约节点完成清算后不会永久退出，下一期仍可参与借贷和收入分配。
- 固定 `K` 实验中，`c` 参数保留在元数据里，但不影响模拟。
- `max_time_steps` 在原 `period_end` 主模拟器中每个完整 period 结束后才检查，所以它是累计尝试数的期末软上限，最后一期可能使实际值超过该设定；在 timestep 对照模拟器中可在每个微步后检查。
- `validate_accounting` 只决定是否逐期检查现金守恒、资产负债与暴露矩阵一致性，不改变模型机制。
- `income_bias_floor` 虽按收入偏置命名，但当前代码也在部分偏好借款人选择规则中作为基础权重使用。
- `collapse_threshold_fraction` 和 `critical_event` 只用于结果分类，不参与违约传播，也不能作为严格临界或 SOC 的证明。

### 基线代码参数字段对照

为避免经济学简称与代码字段名脱节，当前 `CreditNetworkParams` 的全部字段如下：

| 代码字段 | 模型含义 |
| --- | --- |
| `n_nodes` | 节点数 `N` |
| `mean_initial_money` | 初始本金分布的目标人均值；除 equal 外不保证每个 run 的实际样本均值完全相同 |
| `money_distribution` | 初始本金分布类型 |
| `income_distribution_rule` | 收入分配规则：uniform 或 biased |
| `growth_rule` | 在允许交易的主体集合中选择贷款人和借款人的规则；不等于显式机会图 `topology` |
| `consumption_wealth_propensity` | 财富消费倾向 `a` |
| `consumption_income_propensity` | 上一期个体收入消费倾向 `b` |
| `investment_income_propensity` | 收入到下一期计划信贷尝试批量的转换系数 `c` |
| `initial_income_per_capita` | 第一期开启前的每人参考收入；用于构造 `Y_0`，不向系统注入现金 |
| `income_bias_floor` | biased 收入和部分偏好选择规则中的基础权重 `f` |
| `collapse_threshold_fraction` | 大级联分类阈值；不参与违约或传播 |
| `max_periods` | 单个 run 最多执行的 period 数 |
| `max_time_steps` | 累计实际尝试数的期末软上限；0 表示不单独限制 |
| `default_threshold` | 净资产违约阈值；当前判定为严格 `W_i < default_threshold` |
| `wipe_defaulted_assets` | 是否同时清除违约节点持有的贷款资产 |
| `validate_accounting` | 是否逐期执行会计恒等式断言；不改变机制 |
| `period_length_rule` | `income` 使用 `K_t=round(cY_(t-1))`，`fixed` 使用固定 `K` |
| `fixed_period_length_steps` | `period_length_rule=fixed` 时的固定计划尝试数 |
| `avalanche_protocol` | 首次违约后停止，或清算后继续下一期 |
| `default_check_mode` | 违约检查时间尺度；基线为 `period_end`，timestep 对照为 `timestep_settle_check` |

参数是否写入元数据与参数是否实际生效必须分开判断：固定 `K` 协议中的 `investment_income_propensity` 不参与 `K_t` 计算；收入内生协议中的 `fixed_period_length_steps` 也不生效。

### 第二阶段扩展实验中的额外变量

以下变量用于正在进行的第二阶段机制与显式拓扑消融，不属于基线 `simulation.py` 的默认机制。报告必须把它们与基线参数分开解释：

| 变量 | 含义 |
| --- | --- |
| `topology` | `er/ba/sw` 无向交易机会图；它只限定哪些主体可以成为信贷对手方，实际信贷暴露仍是有向、带权且可重复累积的 |
| `target_mean_degree` | 机会图目标平均度；ER/BA/SW 主对照通过匹配边数使平均度和密度可比 |
| `sw_rewire_probability` | SW 机会图的重连概率 |
| `topology_seed` | 机会图生成随机种子，与主体演化的 `seed` 分离 |
| `drive_rule` / `fixed_drive_steps` | 第二阶段机制扩展中，宏观期驱动量使用收入内生规则还是固定步数 |
| `max_drive_steps_per_macro` | 每个宏观期允许执行的最大驱动步数，用于防止收入反馈导致计算量无界增长 |
| `settlement_mode` | 机制消融扩展中的 `period_end`、只增加中间检查的 `check_only`，或固定批次数的分批流量结算并检查 `settle_and_check` |
| `settlement_batches` | 一个宏观期内将总驱动拆成多少个结算批次 |
| `default_check_every_settlements` | 每完成多少次流量结算检查一次违约 |
| `timestep_settle_check` | 本轮对照实验中的严格微步协议；每个宏观期动态拆成 `K_t` 个批次，每批至多 1 次 credit time_step，随后立即微结算、检查和清算 |
| `max_period_length_steps` / `max_period_length_steps_cap` | timestep 对照中的计算保护上限；先记录理论 `K_t`，再执行 `min(K_t, cap)` 个微步，避免高 `c` 与高支出反馈导致单个宏观期计算量无界 |
| `recovery_rate` | 债务人违约时目标回收比例；实际回收还受债务人现金约束 |
| `default_node_mode` | 违约清算后节点继续参与、永久退出或重置到初始现金 |
| `actual_recovery_amount` | 债务人实际支付并被债权人回收的现金；可能远低于 `recovery_rate * 债务面值` |
| `external_reset_cash_flow` | reset 将节点现金恢复到初始值时产生的累计外部现金变化；reset 协议不再满足原始封闭系统现金守恒 |
| `active` | 节点是否仍可参与信贷、支出和收入分配；只在永久退出协议下持续减少 |

其中，`check_only` 是重要负对照：因为单位信贷建立不改变净资产，只增加中间违约检查而不进行流量结算，理论上不应产生新的违约。只有改变流量结算频率，才真正改变负净资产出现的时机。


## 实验模拟算法流程
1. 初始化

   - 生成 `N` 个网络节点。
   - 按指定分布初始化每个节点的货币本金，例如随机分布、整体相同分布或幂律分布。
   - 初始化时每个节点的资产负债表为空，初始货币本金同时也是初始净资产。

2. 定义两层时间尺度

   - `time_step`：微观时间步。
     - 每个 `time_step` 只尝试新增 1 个单位信贷，也就是只尝试落下 1 粒沙。
     - 在一个 `time_step` 中，网络中符合本金约束的一对节点增加 1 单位信贷暴露。例如 `i -> j` 表示 `i` 向 `j` 贷款 1 单位：`i` 的 1 单位货币转移给 `j`，同时 `i` 的资产表增加 1 单位贷款资产，`j` 的负债表增加 1 单位债务负债。
     - 如果本次随机选择的贷款人没有至少 1 单位货币，则本次连边失败，需要重新选择，或将失败次数记入统计。

   - `period`：时期或结算周期。
     - 一个 `period` 由多个 `time_step` 组成。
     - 第 `t` 个 `period` 包含的计划 `time_step` 数量记为 `K_t`。
     - 收入内生协议中：

       ```text
       K_t = round(c * 上一期总收入)
       ```

       其中 `c` 是上一期收入到下一期计划信贷尝试批量的转换系数，初始可设为 `1/5`。
     - `c` 决定的是计划 `time_step` 数量，不改变每个 `time_step` 的单位信贷规模；`c` 越大，下一次期末流量结算和 `period_end` 违约检查前累积的信贷尝试越多。
     - 固定窗口对照实验可以直接令 `K_t = K`，例如每 100 个 `time_step` 结算一次；此时 `c` 不参与模拟，但主实验优先使用收入内生决定的 `K_t`。

3. 执行一个 `period` 内部的信贷增长

   - 在第 `t` 个 `period` 开始时，根据上一期总收入计算 `K_t`。
   - 连续执行 `K_t` 个 `time_step`。
   - 每个 `time_step` 至多成功增加 1 个单位信贷；如果没有满足现金约束的贷款人，则本次尝试可能失败。
   - 不能把 `K_t` 个信贷单位理解为一次性同时加入。
   - 在 `period_end` 协议中，当期所有成功借入资金记为当期累计借贷量，后续在 `period_end` 结算时作为投资支出目标。
   - 在 `timestep_settle_check` 协议中，不等待期末批量结算；每个 credit `time_step` 后立刻用本微步的成功借入量作为本微步投资支出目标。

4. 执行流量结算

   - `period_end` 基线：
     - 在整个 `period` 的 `K_t` 个信贷尝试结束后，统一结算一次。
     - 当期投资支出目标为该期累计成功借入量。
     - 消费支出按完整的 `a * 财富量 + b * 上一期收入量` 计划计算。
     - 结算后统一做一次收入分配和违约检查。

   - `timestep_settle_check` 对照：
     - 一个宏观期仍由 `K_t` 个计划 credit `time_step` 组成。
     - 每个 `time_step` 至多成功新增 1 单位信贷后，立即执行一次微结算。
     - 本微步投资支出目标只使用本微步成功借入量。
     - 消费支出计划使用上一宏观期收入作为参考，但缩放为 `1/K_t`：

       ```text
       P_i,step = (1/K_t) * (a * max(W_i,0) + b * max(Y_i,t-1,0))
       ```

     - 一个宏观期内各微步新收入累加为该期总收入，用于下一期计算 `K_(t+1)`。
     - 若 `K_t=0`，本轮 timestep 对照不产生 credit 微步，也不会在该期人为制造一个额外检查点。
     - 快速全景扫描 v2 使用 `max_period_length_steps=500` 作为计算保护：理论 `K_t` 仍记录为 `uncapped_period_length_steps` / `max_uncapped_period_length_steps`，实际微步数为 `min(K_t,500)`。这一设置用于避免高 `c`、高支出机制下收入反馈把单个宏观期推成无界长计算；它是本轮对照实验的协议条件之一。

   - 投资支出共同规则：
     - 对应结算窗口内成功借入的资金作为该窗口的投资支出目标。
     - 当前实现受现金约束；如果借款人在期内又把现金贷出，实际投资支出可能小于成功借入量。

   - 消费支出共同规则：
     - 消费支出量为 `a * 财富量 + b * 上一期收入量`。
     - 支出受个体现金约束，不能让现金余额因为支出变为负数。

   - 收入分配共同规则：
     - 总收入等于对应结算窗口内的总支出。
     - 收入按照指定规则分配到各个主体，例如随机均匀分配或按净资产偏好分配。

5. 执行违约检查与级联失效

   - `period_end` 基线只在期末检查个体是否违约。
   - `timestep_settle_check` 对照在每个 credit `time_step` 的微结算后检查个体是否违约。
   - 违约条件由净资产判断：`W_i = cash_i + loan_assets_i - debt_liabilities_i`，当前基线为严格 `W_i < 0`。
   - 如果出现违约节点，则在当前检查点内完成级联失效分析；级联清算期间不再新增信贷 time_step。
   - 先记录流量结算后同步出现的初始违约 `initial_default_count`，再沿信贷暴露清算传播新增违约。
   - 债务人违约时，其债权人的贷款资产被减记；若 `wipe_defaulted_assets=True`，违约节点持有的贷款资产也被清除，并解除对应借款人的负债。
   - 队列为空时，本次 avalanche 结束；`collapse_size` 是本次事件中被清算的不同节点数，`propagated_default_count = collapse_size - initial_default_count`。
   - 级联失效完成后，记录本次崩塌规模、崩塌前存量信贷规模、已经经历的 `period` 数和已经经历的 `time_step` 数；timestep 对照还记录 `micro_step_in_period`、`settlements_completed`、`checks_completed`。
   - 若采用“首次违约即重启”的实验协议，则结束本轮实验，并重新开始新一轮初始化。
   - 若采用“慢驱动 + avalanche 后继续增长”的实验协议，则清算违约节点后继续增长；在 `period_end` 协议中继续下一 `period`，在 timestep 对照中继续下一 credit 微步。

6. 记录每一轮实验的关键量

   - `period_index`：发生违约或级联时所处的 `period`。
   - `micro_step_in_period`：timestep 对照中，事件发生在该宏观期第几个 credit 微步之后；`period_end` 基线没有该字段。
   - `period_length_steps`：该 `period` 包含的计划 `time_step` 数量，即 `K_t`。
   - `time_steps_completed`：截至崩塌前累计执行的信贷尝试步数。
   - `event_timestep_rate`：timestep 对照中的 avalanche 频率，定义为 `avalanche_count / time_steps_completed`。
   - `event_period_occupancy`：发生过至少一次 avalanche 的宏观 period 占比；在 timestep 对照中，一个 period 可以包含多次 avalanche，因此它不同于事件率。
   - `total_credit_issued`：截至崩塌或 run 结束时累计成功发放的单位信贷数量。
   - `credit_scale_before_cascade`：级联发生前网络中的活跃信贷暴露总量。
   - `collapse_size`：本次级联违约波及的节点数量。
   - `collapse_fraction`：`collapse_size / N`。
   - `critical_event`：`collapse_fraction` 是否达到或超过预设大崩塌阈值。

重复上述实验M轮次，统计其中的失效规模与频率关系，分析是否有幂律关系


## 实验模拟结果的分类和讨论
### 不同本金初始化？
### 不同支出/收入分配机制？	
	说不定还能讨论不同的收入分配机制对级联失效/自组织临界的影响
### 不同网络拓扑结构？
	稀疏/密集？
	sw/ba？
