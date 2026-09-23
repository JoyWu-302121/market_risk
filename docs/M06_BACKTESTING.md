# M06 Rolling VaR Backtesting and ES Tail Diagnostics

Status: **Complete for the phase-one synthetic zero-coupon portfolio**

## Objective

Evaluate the out-of-sample behavior of the M04 historical-simulation model. M06 produces rolling one-day forecasts, compares each forecast with the next complete adjacent-date curve realization, applies VaR coverage and independence tests, and separately compares forecast Expected Shortfall with realized tail losses.

A successful pipeline means that the backtest was constructed and audited correctly. Statistical rejection is model evidence and is never converted into a pipeline failure.

## Rolling portfolio and realized loss

On every forecast date, the synthetic 3Y/7Y/15Y portfolio is recalibrated to the accepted USD 10 million total market value and equal target weights using that date's curve. Quantities are then frozen over the one-source-day horizon. This avoids applying quantities calibrated with a future 2026 curve to earlier historical dates.

For target market value `M_i`, maturity `T_i`, and realized continuously compounded zero-rate change `Delta y_i`, the exact zero-coupon full-repricing loss is:

```text
loss_i = M_i * [1 - exp(-Delta y_i * T_i)]
portfolio_loss = sum_i loss_i
```

This identity is analytically equivalent to calibrating quantities on the forecast curve and explicitly repricing each bond on the shocked curve. It is not a duration approximation. Carry, roll-down, maturity decay, financing, transaction costs, and intraday trading remain excluded.

## No-lookahead rolling forecasts

For an outcome from source date `t` to the next source date `t+1`:

1. Select only successful shocks whose end date is on or before `t`.
2. Take the latest 500, 750, or 1,250 successful shocks.
3. Recalculate each historical loss for the target-weight portfolio.
4. Estimate VaR and ES with the M04 nearest-rank and fractional-tail conventions.
5. Compare the forecast with the realized full-repricing loss from the `t` to `t+1` curve change.

An exception is recorded only when:

```text
realized_loss > forecast_VaR
```

Equality is not an exception. Missing realized curves and insufficient estimation history remain explicit audit statuses.

## VaR coverage tests

For `n` forecasts, `x` exceptions, and expected exception probability `p = 1 - alpha`, the Kupiec proportion-of-failures test compares the null likelihood at `p` with the unrestricted Bernoulli likelihood at `x/n`. Its likelihood-ratio statistic has an asymptotic chi-square distribution with one degree of freedom.

The Christoffersen independence test uses transition counts `n00`, `n01`, `n10`, and `n11` to compare an independent exception process with a first-order Markov alternative. Transitions are formed only when the previous realization date equals the next forecast date; missing curve outcomes break the transition sequence. Conditional coverage combines the Kupiec and independence statistics and uses two degrees of freedom.

The configured decision threshold is 5%. The report also retains exception rates, expected counts, transition counts, maximum consecutive exceptions, maximum realized loss, and the hypothetical cumulative drawdown of the daily recalibrated research portfolio.

## Live VaR results

The official GSW backtest ends on 2026-09-18.

| Window | Confidence | Forecasts | Exceptions | Expected | Rate | Kupiec p | Independence p | Conditional p | Result at 5% |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 500 | 95% | 4,700 | 262 | 235.0 | 5.57% | 0.0758 | 0.0596 | 0.0351 | Conditional coverage rejected |
| 500 | 99% | 4,700 | 70 | 47.0 | 1.49% | 0.0017 | 0.9625 | 0.0071 | Coverage and conditional coverage rejected |
| 750 | 95% | 4,450 | 232 | 222.5 | 5.21% | 0.5163 | 0.1828 | 0.3335 | Not rejected |
| 750 | 99% | 4,450 | 53 | 44.5 | 1.19% | 0.2138 | 0.6083 | 0.4049 | Not rejected |
| 1,250 | 95% | 3,950 | 186 | 197.5 | 4.71% | 0.3967 | 0.0297 | 0.0657 | Independence rejected |
| 1,250 | 99% | 3,950 | 44 | 39.5 | 1.11% | 0.4798 | 0.0905 | 0.1860 | Not rejected |

The primary 750-observation model is not rejected by the three reported tests at either 95% or 99%. This does not prove that the model is correct; it means the observed exception count and first-order exception dependence do not provide enough evidence for rejection at the configured threshold.

The maximum realized one-day loss was USD 257,172.37. Maximum consecutive exceptions ranged from two to three across the tested combinations.

## ES tail diagnostics

ES is assessed separately from VaR. For each ES confidence level, M06 calculates VaR at the same confidence, identifies dates where realized loss exceeds that tail boundary, and compares average realized tail loss with average forecast ES on those same dates.

| Window | ES level | Forecasts | Tail observations | Expected tail count | Mean realized tail loss | Mean forecast ES | Ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 97.5% | 4,700 | 132 | 117.5 | USD 109,847.16 | USD 107,305.88 | 1.0237 |
| 500 | 99% | 4,700 | 70 | 47.0 | USD 122,359.95 | USD 123,587.23 | 0.9901 |
| 750 | 97.5% | 4,450 | 127 | 111.25 | USD 111,860.12 | USD 111,671.95 | 1.0017 |
| 750 | 99% | 4,450 | 53 | 44.5 | USD 130,789.12 | USD 135,201.24 | 0.9674 |
| 1,250 | 97.5% | 3,950 | 102 | 98.75 | USD 108,451.86 | USD 110,308.57 | 0.9832 |
| 1,250 | 99% | 3,950 | 44 | 39.5 | USD 128,102.50 | USD 136,385.91 | 0.9393 |

A ratio above one means realized losses on tail dates were larger on average than forecast ES; a ratio below one means forecast ES was larger. These are descriptive tail-severity diagnostics, not a formal ES calibration test. Passing VaR coverage does not validate ES.

## Audit population

The complete backtest audit contains 16,992 date-window rows:

- 13,100 successful forecasts
- 2,500 `insufficient_history` rows
- 1,392 `missing_realized_input` rows

The 1,392 missing rows equal 464 incomplete one-day transitions across three windows. No failed outcome becomes a zero loss. The 2,500 insufficient-history rows preserve the warm-up periods required by the three estimation windows.

## Acceptance evidence

- Every requested window produces successful rolling forecasts.
- Historical estimation samples end on or before the forecast date.
- The analytic zero-coupon loss identity matches explicit portfolio full repricing.
- VaR summaries cover all six window-confidence combinations.
- ES summaries cover all six window-confidence combinations.
- Kupiec, independence, and conditional-coverage p-values lie within `[0, 1]`.
- Exception transition counts reconcile to the eligible contiguous-date transition count and never bridge missing outcomes.
- ES is not below same-confidence empirical VaR on any forecast row.
- Every ES diagnostic has realized tail observations.
- Missing inputs and insufficient history remain explicit.
- Forty-six standard-library unit tests pass across M02-M06.
- The live end-to-end report passes all eleven implementation checks.

## Completion boundary

M06 validates only the historical-simulation model under the phase-one synthetic portfolio and one-source-day frozen-position P&L definition. Results are sensitive to the public-data vintage, missing-data rule, target-weight recalibration, empirical estimator convention, and window length. M07 separately validates Parametric Normal and PCA Monte Carlo current-estimate benchmarks; those models do not inherit M06 coverage conclusions.
