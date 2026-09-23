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

## Missing-data rules

1. Preserve raw missing values.
2. Never forward-fill a yield across an unrestricted date range.
3. Interpolation across tenor is permitted only through an accepted curve rule and must set `is_observed = false`.
4. A missing or invalid required curve invalidates the affected valuation unless an accepted fallback is recorded.
5. Failed observations remain in the audit table and are excluded from statistics only under an explicit documented rule.
