# M04 Historical-Simulation VaR and Expected Shortfall

Status: **Complete for the phase-one synthetic zero-coupon portfolio**

## Objective

Estimate one-day market risk for the current frozen 3Y/7Y/15Y synthetic Treasury portfolio by replaying complete historical changes in the Federal Reserve GSW continuously compounded zero curve. M04 uses the same curve conventions, quantities, valuation function, and positive-loss definition accepted in M03.

## Portfolio and information set

The engine selects the latest date containing all configured 1Y-30Y GSW zero-yield nodes and calibrates the USD 10 million portfolio on that date. For an estimate dated `t`, only curve changes ending on or before `t` are eligible. Historical dates are risk-factor observations; they are not portfolio purchase dates.

The three position quantities and remaining maturities are frozen during every one-day scenario. Carry, roll-down, passage of time, financing, trading, and rebalancing remain outside the M04 market-P&L definition.

## Historical curve shocks

For adjacent source dates `s-1` and `s`, and every configured curve node `T_i`, the additive shock is:

```text
shock_s(T_i) = y_s(T_i) - y_(s-1)(T_i)
```

The current scenario curve is:

```text
scenario_curve_s(T_i) = y_t(T_i) + shock_s(T_i)
```

A scenario succeeds only if both adjacent dates contain all 30 observed nodes. The engine does not bridge a failed date by differencing non-adjacent valid curves. Every candidate transition remains in the scenario audit with `success`, `missing_input`, or `valuation_error` status; failed transitions never become zero shocks or zero losses.

## Frozen-position full repricing

For the current quantities `q(t)` and the accepted M03 pricing function:

```text
base_value = V(y_t, q(t))
stressed_value_s = V(y_t + shock_s, q(t))
pnl_s = stressed_value_s - base_value
loss_s = -pnl_s
```

Each position is fully repriced from the shocked discount factors. Scenario position losses must sum to portfolio loss. No DV01 approximation enters the primary M04 estimates.

## Finite-sample VaR convention

Let `L_(1) <= ... <= L_(n)` denote the ordered successful scenario losses. At confidence level `alpha`, nearest-rank historical VaR is:

```text
k = ceil(alpha * n)
VaR_alpha = L_(k)
```

The reported VaR position contribution is the position-loss vector from that exact boundary scenario. Stable ordering makes the result deterministic when losses tie.

## Finite-sample ES convention

Expected Shortfall averages exactly `n * (1 - alpha)` observations of upper-tail probability mass. Sort losses from worst to best and define:

```text
tail_mass = n * (1 - alpha)
m = floor(tail_mass)
f = tail_mass - m
ES_alpha = (sum of the m worst losses + f * next-worst loss) / tail_mass
```

The same normalized tail weights are applied to position losses, so ES contributions sum to portfolio ES. This fractional-boundary rule avoids an undocumented include/exclude decision at the empirical quantile.

## Estimation windows

The current report uses the latest successful scenarios available as of the valuation date:

- 750 observations: primary estimate
- 500 observations: shorter-window sensitivity
- 1,250 observations: longer-window sensitivity

Failed transitions remain in the full audit table but do not count as valid observations. The report records the actual first and last scenario date and exact sample size for every rolling lookback window.

## Live validation snapshot

The engine was validated against the official GSW dataset with a valuation date of 2026-09-18.

| Window | Sample start | 95% VaR | 99% VaR | 97.5% ES | 99% ES |
|---:|---:|---:|---:|---:|---:|
| 500 | 2024-08-14 | USD 62,834.87 | USD 101,680.58 | USD 100,917.51 | USD 117,319.91 |
| 750 | 2023-07-31 | USD 73,279.18 | USD 118,476.34 | USD 115,182.16 | USD 128,201.20 |
| 1,250 | 2021-06-25 | USD 79,681.69 | USD 122,926.26 | USD 121,814.86 | USD 138,470.41 |

The 2005-01-01 onward audit contained 5,664 candidate adjacent-date transitions: 5,200 succeeded and 464 remained explicitly marked `missing_input`. The largest loss across all successful scenarios was USD 257,172.37 under the curve change ending 2020-03-17. This maximum uses the complete eligible history and is not a window-specific VaR estimate.

These values are a reproducible public-data research result. They are sensitive to the 2026-09-18 curve, synthetic zero-coupon portfolio, frozen maturity assumption, GSW data vintage, lookback window, and empirical estimator convention. They are not a bank quote, regulatory-capital result, or investment recommendation.

## Acceptance evidence

- All configured 1Y-30Y nodes are present on the base curve.
- At least 1,250 complete successful one-day shocks are available.
- No shock ending after the valuation date enters an estimate.
- Failed transitions remain explicit and never become zero losses.
- Base and stressed values use the same frozen position quantities.
- Scenario position losses sum to total portfolio loss.
- VaR uses the documented nearest-rank order statistic.
- ES uses the documented fractional tail-mass weights.
- At the same confidence level, empirical ES is not below empirical VaR.
- VaR and ES position contributions sum to their portfolio measures.
- Thirty-six standard-library unit tests pass across M02-M04.
- The live end-to-end M04 report passes every configured check.

## Completion boundary

M04 produces current historical-simulation risk estimates over three rolling lookback windows. It does not claim that the forecasts are calibrated or predictive. Hypothetical, historical-event, PCA-factor, and reverse stress tests are M05 work. Out-of-sample VaR exceptions and ES tail diagnostics remain M06 work.
