# Phase-2 strict SOC analysis artifact note

Generated: 2026-06-04 13:14:55 CST

## Statistical protocol

- Positive integer avalanche sizes; minimum accepted tail sample: 100.
- Pure unbounded discrete power law uses exact Hurwitz-zeta likelihood.
- `xmin` is selected by minimum KS over up to 10000 reproducible candidates.
- Semiparametric KS bootstrap reselects `xmin`; requested replicates per series: 200.
- A second power-law null is explicitly normalized on finite support `[xmin, N]` and bootstrapped separately.
- Alternatives share the selected tail: shifted discrete exponential and rounded/conditioned lognormal.
- Likelihood signs are `R = log L_powerlaw - log L_alternative`; Vuong p-values are descriptive.
- Per-seed fits use minimum tail size 30; pooled-event p-values are diagnostic because events are serially dependent.

## Counts

- Existing result directories audited: 13.
- Series fitted: 39; valid fits: 39.
- Pure power law not rejected at p>=0.10: 26.
- Pure power law rejected at p<0.10: 13.
- Lognormal significantly better at descriptive p<0.10: 10.
- Temporal-separation series analyzed: 37.
- Per-seed robustness scenarios analyzed: 28.
- Time-window rows analyzed: 140.
- Initial-versus-propagated scenario rows analyzed: 28.

## Limitations

- Avalanche events within a run are serially dependent; event-level bootstrap treats sizes as exchangeable and can overstate effective sample size.
- High event-period occupancy or one-period waits alone do not exclude SOC; here they are dependence diagnostics interpreted jointly with lag-1 correlation, drift, repeated defaults, and terminal degeneration.
- A recorded event can begin with multiple synchronous defaults at period-end settlement, so its size is not necessarily a single-trigger avalanche size.
- The pure unbounded power-law null conflicts with finite-network support; bounded-power-law fits describe finite cutoffs but do not prove strict SOC.
- Strong within-run quartile drift invalidates stationary pooled-tail interpretation unless a stationary window is established.
- Four system sizes can show cutoff growth but cannot establish a universal finite-size exponent.

## Evidence files

- `existing_result_audit.csv`
- `strict_tail_fits.csv`, `per_seed_tail_fits.csv`, and `seed_robustness_summary.csv`
- `finite_size_summary.csv`, `finite_size_scaling_slopes.csv`, `event_trigger_decomposition.csv`, `finite_size_initial_vs_propagated.csv`, `temporal_separation_summary.csv`, and `time_window_summary.csv`
- `transition_fine_scan.png`, `strict_fit_comparison.png`, `strict_powerlaw_gof.png`, `finite_size_scaling.png`, `initial_vs_propagated_decomposition.png`, `temporal_separation.png`, `time_window_drift.png`