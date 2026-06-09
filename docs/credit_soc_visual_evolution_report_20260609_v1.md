# 信贷网络演化动画可视化支线报告 v1

生成时间：2026-06-09 15:47 CST

图例更新：2026-06-09 16:11 CST 已在每个 GIF 帧和关键帧 PNG 的右下角加入画面内图例。

## 1. 目标与实现口径

本支线按当前模拟框架重跑三个小规模代表性场景，输出“信贷网络演化过程”动画，而不是只给静态图。脚本为 `scripts/render_creditnet_evolution_animations.py`，输出目录为 `results/credit_soc_visual_evolution_20260609_v1/`。

实现原则：

- 不读取上一轮 1.6GB 级 `avalanche_events.csv`，只重跑小规模 deterministic trace。
- 不修改 `src/creditnet/simulation.py`、`src/creditnet/timestep.py` 或既有实验接口；动画脚本在本地复用相同的借贷选择、支出/收入结算、净资产违约和级联清算规则。
- 使用 `matplotlib.animation.PillowWriter` 只输出 GIF；同一动画内固定 `networkx.spring_layout` 布局 seed。
- 每个 GIF 旁边写入 metadata JSON 和 trace summary CSV，记录参数、seed、事件计数、帧数、时长、阈值和输出路径。

动画读法：

- 每帧右下角的 `Legend` 面板给出颜色、边和节点大小的对应关系；图内使用英文短标签以避免中文字体渲染缺失。
- 边表示活跃信贷暴露，边越粗/越深表示该方向的暴露权重越高；密集场景为可读性只渲染权重最高的一组边，完整暴露统计写入 metadata。
- 节点颜色按净资产刻度变化；节点大小按债务压力相对放大。
- 红/橙节点表示当前违约或新增违约；级联清算帧中，正在清算节点的入边用红色高亮，展示债权人资产减记与传播波次。
- 左上角文字给出协议、period、micro step/time step、活跃信贷、事件计数和净资产摘要。

## 2. 场景与结果摘要

| 场景 | 协议 | N | seed | c | 主要机制 | time steps | 事件数 | 最大级联 | 大事件数 | GIF 时长 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `period_end_overload` | `period_end` | 40 | 1000 | 0.90 | lognormal 本金、biased 收入、preferential_debt、高消费/投资压力 | 216 | 1 | 20/40 = 50.0% | 1 | 16.0s |
| `timestep_micro_tail` | `timestep_settle_check` | 60 | 2018 | 0.80 | lognormal 本金、biased 收入、preferential_debt、每微步结算检查，单期微步上限 120 | 1440 | 191 | 4/60 = 6.67% | 0 | 18.24s |
| `quiet_low_drive` | `period_end` | 40 | 2022 | 0.10 | equal 本金、uniform 收入、random 增长、低消费/投资压力 | 40 | 0 | 0 | 0 | 12.96s |

完整机器可读索引：`results/credit_soc_visual_evolution_20260609_v1/visual_evolution_index.json`。

## 3. 动画 1：period_end 批量结算过载

![period_end_overload.gif](../results/credit_soc_visual_evolution_20260609_v1/period_end_overload.gif)

关键帧预览：

![period_end_overload_keyframes.png](../results/credit_soc_visual_evolution_20260609_v1/period_end_overload_keyframes.png)

该动画展示 `period_end` 协议下的高驱动压力：第一期先累计 216 次单位信贷尝试，活跃信贷网络快速增密；随后在单个期末统一做投资/消费支出、收入分配和违约检查。

本次期末检查产生 13 个同步初始违约，级联清算后总违约规模为 20 个节点，占 N=40 的 50%。其中传播新增违约为 7 个节点，清算后活跃信贷从 216 降至 41。这个动画直观说明：`period_end` 大崩塌包含“整期信贷积累 + 批量流量结算 + 同步初始违约”的放大效应，不能把一次大 avalanche 直接解释成严格 SOC。

metadata：`results/credit_soc_visual_evolution_20260609_v1/period_end_overload_metadata.json`

## 4. 动画 2：timestep 微步结算小 avalanche

![timestep_micro_tail.gif](../results/credit_soc_visual_evolution_20260609_v1/timestep_micro_tail.gif)

关键帧预览：

![timestep_micro_tail_keyframes.png](../results/credit_soc_visual_evolution_20260609_v1/timestep_micro_tail_keyframes.png)

该动画展示 `timestep_settle_check` 协议：宏观 period 仍由 `K_t` 给出计划微步数，但每个 credit time_step 后立刻做按 `1/K_t` 缩放的支出/收入结算、违约检查和完整级联清算，清算期间不继续新增信贷。

本场景 12 个 period、1440 个 micro step 中出现 191 次 avalanche，但最大规模只有 4/60，未达到 10%N 的大事件阈值；规模分布为 169 次单节点事件、18 次两节点事件、3 次三节点事件、1 次四节点事件。动画上可见红色违约节点频繁闪现，但每次清算后网络继续微步增长，没有形成 `period_end_overload` 那样的宏观大崩塌。

这与 timestep v2 报告的总体判断一致：把检查点移到 credit 微步后，大级联率和平均规模明显下降；高频小事件本身不是 SOC 证明，还需要尾部拟合、平稳性、有限尺寸标度和机制鲁棒性证据。

metadata：`results/credit_soc_visual_evolution_20260609_v1/timestep_micro_tail_metadata.json`

## 5. 动画 3：低驱动安静对照

![quiet_low_drive.gif](../results/credit_soc_visual_evolution_20260609_v1/quiet_low_drive.gif)

关键帧预览：

![quiet_low_drive_keyframes.png](../results/credit_soc_visual_evolution_20260609_v1/quiet_low_drive_keyframes.png)

该动画使用低 `c=0.10`、均匀初始本金、均匀收入分配和随机增长。20 个 period 内只完成 40 次信贷尝试，活跃暴露缓慢增加，没有出现违约或 avalanche。它作为视觉对照说明：在低驱动和较温和支出下，网络可以缓慢增信而不进入持续失败吸引子。

metadata：`results/credit_soc_visual_evolution_20260609_v1/quiet_low_drive_metadata.json`

## 6. 对 SOC 判定的含义

这组三个动画主要服务于机制解释和口径展示，不是新的严格 SOC 统计证明。

- `period_end_overload` 说明大崩塌可以由期末批量结算和同步初始违约放大产生。
- `timestep_micro_tail` 说明微步结算会把许多压力释放为小 avalanche，事件频率可以很高，但最大规模未跨过大事件阈值。
- `quiet_low_drive` 给出低驱动对照，显示信贷增强本身不必然导致级联。

因此，本支线结论保持项目证据层级：大级联出现 < 稳健级联转变 < 重尾 < 可信幂律 < 严格 SOC。动画能够辅助解释事件尺度差异，但严格 SOC 是否成立仍以大样本尾部拟合、有限尺寸标度、平稳性和机制消融为准。

## 7. 产物清单

- 渲染脚本：`scripts/render_creditnet_evolution_animations.py`
- 输出目录：`results/credit_soc_visual_evolution_20260609_v1/`
- 渲染日志：`results/credit_soc_visual_evolution_20260609_v1/render.log`
- 总索引：`results/credit_soc_visual_evolution_20260609_v1/visual_evolution_index.json`
- 三个 GIF：`period_end_overload.gif`、`timestep_micro_tail.gif`、`quiet_low_drive.gif`
- 三个关键帧 PNG：`period_end_overload_keyframes.png`、`timestep_micro_tail_keyframes.png`、`quiet_low_drive_keyframes.png`
- 三个 metadata JSON 与 trace summary CSV：同目录下对应 `*_metadata.json`、`*_trace_summary.csv`

复现命令：

```bash
/home/wuyangcheng/.conda/envs/myenv/bin/python scripts/render_creditnet_evolution_animations.py --fps 6
```
