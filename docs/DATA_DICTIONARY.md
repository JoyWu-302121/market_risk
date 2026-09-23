# M01 Data Dictionary

Status: **Locked for phase-one implementation**

## Yield-curve observations

| Field | Type | Unit | Frequency | Source / rule |
|---|---|---:|---|---|
| `observation_date` | date | ISO date | Daily business date | Date represented by the source observation |
| `retrieved_at_utc` | datetime | UTC | Per download | Timestamp recorded by the pipeline |
| `source_name` | string | — | Per record | `Federal Reserve GSW` or named approved source |
| `source_series` | string | — | Per tenor | Original source field such as `SVENY05` |
| `source_vintage` | date/string | — | Per download | Release/vintage identifier when available |
| `tenor_years` | float | years | Per curve node | Maturity represented by the source field |
| `zero_yield_cc` | float | decimal p.a. | Daily | Continuously compounded zero yield; 1% is `0.01` |
| `discount_factor` | float | price per USD 1 | Derived daily | `exp(-zero_yield_cc * tenor_years)` at the curve date |
| `is_observed` | boolean | — | Per value | True only for an original source value |
| `interpolation_method` | string/null | — | Per value | Null for observed values; method name otherwise |
| `quality_flag` | enum | — | Per value | `valid`, `missing`, `interpolated`, `stale`, or `invalid` |

## Instrument master

| Field | Type | Unit | Rule |
|---|---|---:|---|
| `instrument_id` | string | — | Stable internal identifier |
| `instrument_type` | string | — | Phase one: `zero_coupon_bond` |
| `currency` | string | ISO 4217 | Phase one: `USD` |
| `maturity_date` | date | ISO date | Contractual cash-flow date |
| `notional` | float | USD | Final principal payment |
| `day_count` | string | — | Explicitly configured; no implicit library default |

## Portfolio snapshot

| Field | Type | Unit | Rule |
|---|---|---:|---|
| `valuation_date` | date | ISO date | Date on which positions and market inputs are frozen |
| `portfolio_id` | string | — | Stable portfolio identifier |
| `instrument_id` | string | — | Foreign key to instrument master |
| `quantity` | float | units | Signed position quantity |
| `clean_market_value` | float | USD | Phase-one zero-coupon value; accrued interest is zero |
| `portfolio_weight` | float | decimal | Instrument value divided by core portfolio value |

## Scenario and risk results

| Field | Type | Unit | Rule |
|---|---|---:|---|
| `scenario_id` | string | — | Unique reproducible scenario identifier |
| `scenario_type` | string | — | Historical, parametric, PCA, hypothetical, or reverse |
| `horizon_days` | integer | trading days | Phase-one primary value: 1 |
| `confidence_level` | float/null | decimal | Required for VaR/ES; null for deterministic stresses |
| `base_value` | float | USD | Full-revaluation portfolio value before shock |
| `stressed_value` | float | USD | Full-revaluation portfolio value after shock |
| `pnl` | float | USD | `stressed_value - base_value` |
| `loss` | float | USD | `-pnl`; positive values denote losses |
| `status` | enum | — | `success`, `missing_input`, `invalid_curve`, or `valuation_error` |

## M04 historical-risk fields

| Field | Type | Unit | Rule |
|---|---|---:|---|
| `shock_start_date` | date | ISO date | Earlier date in an adjacent source-date pair |
| `shock_end_date` | date | ISO date | Later date in an adjacent source-date pair; never after the valuation date |
| `failure_reason` | string/null | — | Explicit reason when a scenario is not successful |
| `window_size` | integer | valid observations | One of 500, 750, or 1,250 |
| `sample_start_date` | date | ISO date | First successful shock date in the selected window |
| `sample_end_date` | date | ISO date | Last successful shock date in the selected window |
| `measure` | enum | — | `VaR` or `ES` |
| `confidence_level` | float | decimal | 0.95/0.99 for VaR; 0.975/0.99 for ES |
| `value` | float | USD loss | Positive-loss empirical risk estimate |
| `convention` | enum | — | `nearest_rank_order_statistic` or `fractional_tail_mass` |
| `position_contributions` | object | USD loss | Contributions that reconcile exactly to the portfolio measure |

## M05 stress-testing fields

| Field | Type | Unit | Rule |
|---|---|---:|---|
| `scenario_family` | enum | — | Hypothetical, historical, PCA factor, or reverse stress family |
| `shock_bps` | object | basis points | Complete 1Y-30Y node-shock vector |
| `position_loss_contributions` | object | USD loss | Full-repricing position losses that sum to portfolio loss |
| `linear_key_rate_contributions` | object | USD loss | Central-difference node contributions that sum to the linear estimate |
| `linear_sensitivity_loss` | float | USD loss | Sum of key-rate contributions |
| `full_minus_linear` | float | USD loss | Full-repricing loss minus linear sensitivity loss |
| `maximum_absolute_shock_bps` | float | basis points | Largest absolute node shock in the scenario |
| `loss_threshold_usd` | float/null | USD loss | Reverse-stress breach target |
| `amplitude_bps` | float/null | basis points | Reverse-stress maximum-node amplitude at the boundary |
| `residual_variance_ratio` | float/null | decimal | PCA variation outside the retained factors |

## M06 backtesting fields

| Field | Type | Unit | Rule |
|---|---|---:|---|
| `forecast_date` | date | ISO date | Curve date on which positions and the information set are frozen |
| `realization_date` | date | ISO date | Next adjacent source curve date used for realized loss |
| `forecast_value` | float | USD loss | Rolling Historical VaR or ES estimate |
| `realized_loss` | float | USD loss | Exact frozen-position next-source-date loss |
| `exception` | boolean | — | True only when realized loss is strictly greater than VaR |
| `tail_var_value` | float | USD loss | Same-confidence VaR boundary used for ES tail-date selection |
| `tail_observation` | boolean | — | Realized loss exceeds the same-confidence tail VaR |
| `es_breach` | boolean | — | Realized loss exceeds forecast ES; descriptive only |
| `kupiec_p_value` | float | decimal | Unconditional-coverage chi-square p-value |
| `independence_p_value` | float | decimal | First-order exception-independence p-value |
| `conditional_coverage_p_value` | float | decimal | Combined coverage and independence p-value |

## M07 model-comparison fields

| Field | Type | Unit | Rule |
|---|---|---:|---|
| `method` | enum | — | Historical Simulation, Parametric Normal, or PCA Monte Carlo |
| `probability_measure` | enum | — | `P` for physical-measure market-risk estimation |
| `loss_standard_deviation` | float/null | USD loss | Parametric or simulated daily loss standard deviation |
| `component` | string | — | Individual PCA component such as `PC1` through `PC30` |
| `factor` | string | — | `PC1`, `PC2`, `PC3`, or aggregated `residual` label |
| `eigenvalue` | float | decimal yield squared | Sample variance of the orthogonal factor score |
| `explained_variance_ratio` | float | decimal | Component eigenvalue divided by total curve variance |
| `portfolio_variance_share` | float | decimal | Orthogonal factor contribution divided by total linear loss variance |
| `simulated_covariance_relative_error` | float | decimal | Frobenius norm error relative to fitted covariance |
| `position_contributions` | object | USD loss | Euler or empirical full-repricing contributions that sum to the risk measure |

## Missing-data rules

1. Preserve raw missing values.
2. Never forward-fill a yield across an unrestricted date range.
3. Interpolation across tenor is permitted only through an accepted curve rule and must set `is_observed = false`.
4. A missing or invalid required curve invalidates the affected valuation unless an accepted fallback is recorded.
5. Failed observations remain in the audit table and are excluded from statistics only under an explicit documented rule.
