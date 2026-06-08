# 严格 SOC 分支最终方法审计

审计时间：2026-06-04 13:00 CST；最终集成复核：2026-06-04 13:15 CST  
最终分析目录：`analysis_final_v5/`（严格尾部统计与已审计的 `analysis_final_v4/` 一致，新增事件定义拆解）

## 1. 原始数据独立复算

直接从 `run_summary.csv` 与 `avalanche_events.csv` 复算，不依赖分析汇总：

- 1440 个 run、368042 个 avalanche、420000 个 period；
- 1440 个全局唯一 seed；无重复 `scenario_id + seed`；
- 1440 个 run 的 `validate_accounting` 全部为 `True`；
- `sum(run.avalanche_count) == 368042`；
- run 级 avalanche 数量、最大规模、总规模和 `critical_event` 与事件表逐 seed 聚合完全一致；
- 所有事件满足 `1 <= collapse_size <= N`；
- `collapse_fraction == collapse_size / N`；
- 事件级 `critical_event` 与 `collapse_fraction >= 0.10` 完全一致。

## 2. 自动 `xmin`

- 候选为观测到的正整数 avalanche size；
- 候选必须保留至少 100 个尾部样本和至少 3 个不同尾部取值；
- 每个候选上重新做离散 power-law MLE，并选择 KS 最小值；
- 最终分析检查全部合格候选，不再做候选下采样。

审计发现并修正：早期分析把候选上限设为 80，`finite_fixed N=1000,K=140` 有 100 个合格候选，导致近似选择 `xmin=94` 而非穷举最优 `xmin=98`，KS 相差 0.0080。最终 `analysis_final_v4/` 与 `analysis_final_v5/` 使用 `--max-xmin-candidates 10000`，对当前全部 series 等价于穷举。

## 3. 无界与有限支持离散幂律

无界模型：

```text
P(X=x | X>=xmin) = x^(-alpha) / zeta(alpha, xmin), alpha>1
```

有限支持模型：

```text
P(X=x | xmin<=X<=N) = x^(-alpha) / sum_(k=xmin)^N k^(-alpha)
```

- 两者均使用离散整数似然而非连续近似；
- KS 比较经验离散 CDF 与相应模型 CDF；
- 最终 `alpha` 搜索上界为 50；全部新实验穷举拟合的最大 MLE 为 27.57，无结果触及上界。

独立使用似然 score 方程求根复核五个关键场景，无界和有限支持 MLE 与实现结果的绝对误差均小于 `3e-6`。

## 4. KS bootstrap

- 经验 body 在 `X<xmin` 内有放回重采样；
- 尾部由拟合 power law 生成；
- 每个 bootstrap 样本均重新执行自动 `xmin` 和 MLE，而不是固定原始 `xmin`；
- p 值使用 `(1 + #KS_boot>=KS_obs)/(B+1)`；最终 `B=200`。

抽查 `income c=0.18 lognormal` 的 20 个合成样本，重新拟合得到 `xmin=20/21/22`，确认 bootstrap 确实重选 `xmin`。

无界离散 power-law 生成器使用 rounded continuous-Pareto proposal 的精确 rejection sampling。对四组代表性 `(alpha,xmin)` 各生成 100 万样本，前 20 个整数格点的经验质量与 Hurwitz-zeta 目标质量的最大绝对误差不超过 0.0011。

**限制**：event-level bootstrap 把事件作为可交换样本；实际 avalanche 在同一 run 内强序列相关，因此该 p 值只能作为 pooled-tail 描述，不能作为严格 SOC 的最终显著性检验。

## 5. 替代分布与 Vuong

### Exponential

- 使用 `X-xmin` 上的 shifted geometric；
- MLE `q = mean(X-xmin)/(1+mean(X-xmin))`；
- 两个关键场景的独立 score 复算误差小于 `3e-13`。

### Lognormal

- 使用连续 lognormal 在整数区间 `[x-0.5,x+0.5]` 的概率质量，并按 `X>=xmin` 条件化；
- 最终实现使用稳定的 `logcdf/logsf` 区间差，避免直接 CDF 相减的灾难性消减；
- 使用 24 个确定性起点做有界 L-BFGS-B 优化，并记录收敛和边界状态；
- 三组代表参数下，对从 `xmin` 到 199999 的整数概率求和为 `1.0000000000000002-1.0000000000000053`。

审计发现并修正：早期直接 CDF 相减会在极端参数起点产生虚假较高似然。最终替代分布比较仅使用统计一致的 `analysis_final_v4/` 或集成拆解后的 `analysis_final_v5/`。

最终 v4/v5 的 39 个 lognormal 优化全部成功，且没有边界命中。

### Vuong 限制

`R = log L_powerlaw - log L_alternative`。实现的 Vuong z/p 使用逐事件 log-likelihood 差的 iid 标准误。由于事件强序列相关且分布随 run 时间漂移，Vuong p 值仅作描述；最终判定不把它当作独立显著性证据。

## 6. Per-seed、有限尺寸和时间漂移

- per-seed：每个独立 run 单独自动选择 `xmin` 并拟合无界/有限支持 power law，最低尾部样本数为 30；用于检查参数跨 seed 稳定性，不当作 per-seed GOF p 值。
- 有限尺寸：同时使用固定 `K/N=0.14` 和收入内生 `c=0.18`，避免用固定绝对 `K` 跨 `N` 推断；直接复算绝对 P99、最大值、一/二阶矩和 `E[S²]/E[S]`。
- 时间分离：按 seed 计算事件期占比、相邻事件等待和 size lag-1 相关。
- 时间漂移：按每个 run 实际完成 period 分成四个时间分位，比较事件期占比、均值和大事件率。

## 7. 事件定义、单触发与传播拆解

直接从正式 `avalanche_events.csv` 独立复算：

```text
propagated_default_count = collapse_size - initial_default_count
```

- income lognormal `c=.12/.14/.16/.18/.20` 的 `P(initial_default_count=1)` 为 `0.1549/0.0875/0.0507/0.0338/0.0205`；
- fixed lognormal `K=18/20/22/24/26` 为 `0.0812/0.0645/0.0492/0.0418/0.0371`；
- 上述细扫的 propagated share 为总 `collapse_size` 的约 10%-16%；
- `finite_fixed N=100/200/500/1000` 的 propagated share 为 `0.1459/0.1460/0.1473/0.1504`，initial/N 为 `0.0520/0.0487/0.0478/0.0484`，propagated/N 为 `0.00888/0.00833/0.00826/0.00856`；
- `finite_income c=.18` 的 propagated share 为 `0.1218/0.1241/0.1253/0.1281`，initial/N 为 `0.0381/0.0395/0.0364/0.0374`，propagated/N 为 `0.00528/0.00559/0.00521/0.00549`。

因此记录事件多数是 `period_end` 多源同步初始违约加较小传播增量；近线性有限尺寸总规模主要由 initial defaults 的广延缩放主导。证据文件为 `analysis_final_v5/event_trigger_decomposition.csv`、`analysis_final_v5/finite_size_initial_vs_propagated.csv` 和 `analysis_final_v5/initial_vs_propagated_decomposition.png`。

## 8. 最终严格尾部统计

- 39 个有效 series：无界离散 pure power law 在 `p>=0.10` 下不拒绝 26 个、拒绝 13 个；有限支持结果为 27 个、12 个；
- 自动 `xmin` 的离散尾部 pooled `alpha` 最大为 27.5673，全部未触及搜索上界 50；
- exponential 在 21/39、lognormal 在 10/39 中以描述性 Vuong `p<0.10` 优于 power law；
- 这些严格 `alpha` 与旧框架固定 `xmin=2` 的连续 Pareto 初筛不同。

## 9. 剩余不可消除限制

- 未实现 run/block bootstrap 的正式 GOF；per-seed 拟合只能说明参数不稳定性。
- 只有四个 `N`，不足以估计可信的普适有限尺寸指数。
- 当前 `c` 同时改变计划信贷尝试批量和 `period_end` 检查间隔，不能解释为独立纯驱动率。
- 当前 continue 协议允许节点清算后继续参与，长期行为是机制特定的持续失败吸引子。

这些限制均使“严格 SOC”更难识别，不影响“存在级联交叉、但当前证据不支持严格 SOC”的最终判定。
