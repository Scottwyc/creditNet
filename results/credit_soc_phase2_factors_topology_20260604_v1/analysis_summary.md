# Phase-2 因素与显式拓扑扫描自动摘要

生成时间：2026-06-04 12:41:17 CST

- Run 数：248
- Avalanche 事件数：51401
- 协议：`N=200`、`fixed K=20`、`max_periods=240`、`continue_after_avalanche`、`period_end` 检查。
- 结论口径：本扫描是统一 240-period 固定时域的瞬态比较，不代表长期稳态或长期拓扑效应。
- 注意：大 avalanche 与重尾迹象不等于严格 SOC 证明。

## 拓扑与密度汇总

| topology | target_mean_degree | runs | critical_run_rate | mean_first_cascade_credit | mean_max_collapse_size | mean_topology_clustering | mean_topology_degree_cv |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ba | 24 | 8 | 0.1250 | 47.5000 | 17.3750 | 0.2010 | 0.5617 |
| sw | 24 | 8 | 0.0000 | 92.5000 | 16.3750 | 0.5377 | 0.0620 |
| er | 6 | 8 | 0.0000 | 55.0000 | 16.1250 | 0.0297 | 0.3962 |
| er | 24 | 8 | 0.0000 | 32.5000 | 16.1250 | 0.1187 | 0.1843 |
| er | 12 | 8 | 0.0000 | 62.5000 | 15.7500 | 0.0595 | 0.2728 |
| sw | 12 | 8 | 0.0000 | 47.5000 | 15.6250 | 0.4978 | 0.0885 |
| ba | 6 | 8 | 0.0000 | 60.0000 | 15.0000 | 0.0934 | 0.9096 |
| ba | 12 | 8 | 0.0000 | 42.5000 | 15.0000 | 0.1382 | 0.7378 |
| sw | 6 | 8 | 0.0000 | 70.0000 | 14.5000 | 0.4537 | 0.1242 |

## 初始本金分布汇总

| money_distribution | runs | critical_run_rate | mean_first_cascade_credit | mean_max_collapse_size | mean_initial_gini | mean_final_net_worth_gini |
| --- | --- | --- | --- | --- | --- | --- |
| lognormal | 8 | 0.0000 | 72.5000 | 16.2500 | 0.5213 | 0.8460 |
| pareto | 8 | 0.0000 | 607.5000 | 13.0000 | 0.3377 | 0.8073 |
| uniform | 8 | 0.0000 | 42.5000 | 11.1250 | 0.3372 | 0.6553 |
| normal | 8 | 0.0000 | 25.0000 | 9.6250 | 0.2795 | 0.6363 |
| equal | 8 | 0.0000 | 1392.5000 | 7.0000 | 0.0000 | 0.5266 |

## 结构量 Spearman 相关

| scope | structure_metric | outcome | n | spearman_rho | pvalue |
| --- | --- | --- | --- | --- | --- |
| topology_degree_runs | topology_mean_degree | credit_scale_before_cascade | 72 | -0.1175 | 0.3255 |
| topology_degree_runs | topology_mean_degree | max_collapse_size | 72 | 0.2930 | 0.0125 |
| topology_degree_runs | topology_mean_degree | avalanche_count | 72 | 0.1376 | 0.2492 |
| topology_degree_runs | topology_mean_degree | final_net_worth_gini | 72 | 0.2668 | 0.0235 |
| topology_degree_runs | topology_clustering | credit_scale_before_cascade | 72 | 0.0986 | 0.4098 |
| topology_degree_runs | topology_clustering | max_collapse_size | 72 | 0.0196 | 0.8702 |
| topology_degree_runs | topology_clustering | avalanche_count | 72 | 0.0052 | 0.9654 |
| topology_degree_runs | topology_clustering | final_net_worth_gini | 72 | 0.1215 | 0.3092 |
| topology_degree_runs | topology_degree_cv | credit_scale_before_cascade | 72 | -0.1208 | 0.3122 |
| topology_degree_runs | topology_degree_cv | max_collapse_size | 72 | -0.0749 | 0.5317 |
| topology_degree_runs | topology_degree_cv | avalanche_count | 72 | 0.1508 | 0.2062 |
| topology_degree_runs | topology_degree_cv | final_net_worth_gini | 72 | -0.0938 | 0.4334 |
| topology_degree_runs | topology_lcc_average_path_length | credit_scale_before_cascade | 72 | 0.1436 | 0.2289 |
| topology_degree_runs | topology_lcc_average_path_length | max_collapse_size | 72 | -0.2327 | 0.0492 |
| topology_degree_runs | topology_lcc_average_path_length | avalanche_count | 72 | -0.2011 | 0.0903 |
| topology_degree_runs | topology_lcc_average_path_length | final_net_worth_gini | 72 | -0.2334 | 0.0485 |

## Avalanche 尾部初筛

以下 `alpha_continuous_screen` 固定使用 `xmin=2`，只用于同协议描述性比较，不是离散幂律检验或严格 SOC 证明。

| factor_family | scenario_id | tail_n | alpha_continuous_screen | max_event_size |
| --- | --- | --- | --- | --- |
| ab_grid | ab_grid__money-lognormal__income-biased__growth-random__a-0.010__b-0.100__topo-er__k-12 | 1658 | 1.6754 | 18 |
| ab_grid | ab_grid__money-lognormal__income-biased__growth-random__a-0.010__b-0.200__topo-er__k-12 | 1717 | 1.6792 | 18 |
| ab_grid | ab_grid__money-lognormal__income-biased__growth-random__a-0.010__b-0.300__topo-er__k-12 | 1731 | 1.6720 | 18 |
| ab_grid | ab_grid__money-lognormal__income-biased__growth-random__a-0.020__b-0.100__topo-er__k-12 | 1674 | 1.7373 | 19 |
| ab_grid | ab_grid__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-12 | 1675 | 1.7286 | 18 |
| ab_grid | ab_grid__money-lognormal__income-biased__growth-random__a-0.020__b-0.300__topo-er__k-12 | 1738 | 1.7143 | 18 |
| ab_grid | ab_grid__money-lognormal__income-biased__growth-random__a-0.040__b-0.100__topo-er__k-12 | 1559 | 1.9432 | 14 |
| ab_grid | ab_grid__money-lognormal__income-biased__growth-random__a-0.040__b-0.200__topo-er__k-12 | 1654 | 1.9123 | 16 |
| ab_grid | ab_grid__money-lognormal__income-biased__growth-random__a-0.040__b-0.300__topo-er__k-12 | 1623 | 1.9446 | 13 |
| income_rule | income_rule__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-12 | 1677 | 1.7310 | 18 |
| income_rule | income_rule__money-lognormal__income-uniform__growth-random__a-0.020__b-0.200__topo-er__k-12 | 0 |  | 1 |
| money_distribution | money_distribution__money-equal__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-12 | 454 | 2.6509 | 9 |
| money_distribution | money_distribution__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-12 | 1674 | 1.7377 | 18 |
| money_distribution | money_distribution__money-normal__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-12 | 1236 | 2.2246 | 12 |
| money_distribution | money_distribution__money-pareto__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-12 | 1080 | 1.8970 | 17 |
| money_distribution | money_distribution__money-uniform__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-12 | 1491 | 2.0437 | 13 |
| topology_degree | topology_degree__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-ba__k-12 | 1751 | 1.7160 | 17 |
| topology_degree | topology_degree__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-ba__k-24 | 1734 | 1.6930 | 20 |
| topology_degree | topology_degree__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-ba__k-6 | 1688 | 1.7314 | 19 |
| topology_degree | topology_degree__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-12 | 1679 | 1.7361 | 19 |
| topology_degree | topology_degree__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-24 | 1708 | 1.7186 | 19 |
| topology_degree | topology_degree__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-6 | 1700 | 1.7341 | 18 |
| topology_degree | topology_degree__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-sw__k-12 | 1669 | 1.7675 | 19 |
| topology_degree | topology_degree__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-sw__k-24 | 1703 | 1.7275 | 18 |
| topology_degree | topology_degree__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-sw__k-6 | 1687 | 1.7751 | 17 |
| topology_growth | topology_growth__money-lognormal__income-biased__growth-preferential_debt__a-0.020__b-0.200__topo-ba__k-12 | 674 | 3.0572 | 8 |
| topology_growth | topology_growth__money-lognormal__income-biased__growth-preferential_debt__a-0.020__b-0.200__topo-er__k-12 | 584 | 3.2203 | 8 |
| topology_growth | topology_growth__money-lognormal__income-biased__growth-preferential_debt__a-0.020__b-0.200__topo-sw__k-12 | 620 | 3.1126 | 7 |
| topology_growth | topology_growth__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-ba__k-12 | 1744 | 1.6944 | 23 |
| topology_growth | topology_growth__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-er__k-12 | 1675 | 1.7253 | 17 |
| topology_growth | topology_growth__money-lognormal__income-biased__growth-random__a-0.020__b-0.200__topo-sw__k-12 | 1694 | 1.7344 | 20 |

## 证据边界

- 每个场景重复数较小，结果用于因素方向和后续高重复筛选，不用于严格统计证明。
- 所有显式拓扑是固定的无向可借贷机会图；实际信贷暴露保持带权有向。
- 已知高风险协议在更长时域会向高频失效、高 Gini 和低活跃信贷漂移，因此不得把 240-period 差异外推为稳态排序。