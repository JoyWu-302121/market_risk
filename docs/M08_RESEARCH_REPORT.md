# Phase-One Bond Portfolio Market-Risk Research Report

Status: **M08 complete; official GSW end-to-end validation passed**

## Executive summary

This project measures the one-day yield-curve risk of a synthetic USD 10 million US Treasury zero-coupon portfolio. The portfolio holds equal market-value exposures at 3, 7, and 15 years. The primary valuation date is 2026-09-18, selected automatically as the latest complete Federal Reserve Gürkaynak-Sack-Wright (GSW) nominal zero-curve date available during the validation run.

The primary 750-observation Historical Simulation estimates are USD 73,279 for 95% VaR, USD 118,476 for 99% VaR, USD 115,182 for 97.5% ES, and USD 128,201 for 99% ES. Parametric Normal and PCA Monte Carlo produce similar 95% VaR, but lower 99% VaR and ES than Historical Simulation. The difference is evidence that observed losses in the selected sample have a more severe upper tail than the fitted Gaussian benchmarks.

The primary 750-day Historical Simulation VaR model is not rejected by Kupiec unconditional coverage, Christoffersen independence, or combined conditional coverage tests at the 5% significance level. Results are sensitive to the estimation window: the 500-day model has rejections, and the 1,250-day 95% model rejects independence. These backtests apply only to Historical Simulation. The Gaussian benchmarks have not received rolling out-of-sample validation.

This is a public-data research model. It is not a bank quote, regulatory capital model, or investment recommendation.

## Portfolio and valuation

The portfolio contains three synthetic zero-coupon bonds, each calibrated to one third of the initial market value.

| Position | Maturity | Market value | Full-revaluation DV01 |
|---|---:|---:|---:|
| `UST_ZERO_3Y` | 3 years | USD 3,333,333.33 | USD 999.85 |
| `UST_ZERO_7Y` | 7 years | USD 3,333,333.33 | USD 2,332.52 |
| `UST_ZERO_15Y` | 15 years | USD 3,333,333.33 | USD 4,996.25 |
| **Portfolio** | — | **USD 10,000,000.00** | **USD 8,328.62** |

The engine uses continuously compounded zero rates and linear interpolation in log discount factors. Automatic extrapolation below 1 year or above 30 years is rejected. Quantities are calibrated on the valuation curve and frozen over the risk horizon. For maturity `T`, quantity `q`, face value `N`, and zero yield `y`, value is:

```text
V = q * N * exp(-y * T)
loss = -(V_shocked - V_base)
```

Losses are positive. Full repricing is the primary result; DV01 and key-rate sensitivities are explanatory approximations. The linear-versus-full portfolio DV01 relative error is 0.0566%, below the accepted 0.1% tolerance.

## Data and scenario population

The primary market input is the Federal Reserve GSW nominal Treasury curve. `SVENY01` through `SVENY30` are treated as continuously compounded zero-coupon yields. Par-yield fields are not substituted. The pipeline stores source payload hashes, retrieval metadata, normalized decimal yields, and explicit quality flags.

Historical shocks use changes between adjacent source dates. Both dates must contain every required observed curve node. An incomplete transition remains an explicit failed observation and is never converted to zero or bridged by differencing non-adjacent valid dates.

The one-day risk horizon means one adjacent GSW source-date transition. It is not guaranteed to equal one calendar day. Carry, roll-down, financing, rebalancing, and transaction costs are excluded.

## Current VaR and Expected Shortfall

### Primary 750-observation comparison

| Method | 95% VaR | 99% VaR | 97.5% ES | 99% ES |
|---|---:|---:|---:|---:|
| Historical Simulation | USD 73,279.18 | USD 118,476.34 | USD 115,182.16 | USD 128,201.20 |
| Parametric Normal | USD 74,041.09 | USD 104,717.73 | USD 105,233.36 | USD 119,971.38 |
| PCA Monte Carlo | USD 73,579.71 | USD 104,136.32 | USD 104,481.96 | USD 119,260.51 |

Historical Simulation applies complete observed curve changes to the current portfolio and uses exact full repricing. Parametric Normal uses the sample yield-change covariance and current key-rate sensitivity vector under a zero-mean normal assumption. PCA Monte Carlo draws 100,000 fixed-seed Gaussian scenarios from the complete covariance eigensystem and fully reprices each position.

Parametric Normal and PCA Monte Carlo are close because they share the same Gaussian covariance assumption. Monte Carlo sampling and full-repricing convexity account for their remaining difference. Historical Simulation retains observed tail shape and therefore produces materially higher 99% estimates in the primary window.

## Estimation-window sensitivity

| Window | Method | 95% VaR | 99% VaR | 97.5% ES | 99% ES |
|---:|---|---:|---:|---:|---:|
| 500 | Historical Simulation | USD 62,834.87 | USD 101,680.58 | USD 100,917.51 | USD 117,319.91 |
| 500 | Parametric Normal | USD 64,781.55 | USD 91,621.78 | USD 92,072.93 | USD 104,967.83 |
| 500 | PCA Monte Carlo | USD 64,661.62 | USD 91,235.60 | USD 91,900.33 | USD 104,745.06 |
| 750 | Historical Simulation | USD 73,279.18 | USD 118,476.34 | USD 115,182.16 | USD 128,201.20 |
| 750 | Parametric Normal | USD 74,041.09 | USD 104,717.73 | USD 105,233.36 | USD 119,971.38 |
| 750 | PCA Monte Carlo | USD 73,579.71 | USD 104,136.32 | USD 104,481.96 | USD 119,260.51 |
| 1,250 | Historical Simulation | USD 79,681.69 | USD 122,926.26 | USD 121,814.86 | USD 138,470.41 |
| 1,250 | Parametric Normal | USD 81,371.69 | USD 115,085.54 | USD 115,652.22 | USD 131,849.42 |
| 1,250 | PCA Monte Carlo | USD 81,034.10 | USD 113,841.42 | USD 114,354.30 | USD 130,322.51 |

Risk increases with the estimation window in this data vintage. The longer samples include higher-volatility historical periods. This sensitivity is material and supports reporting all three windows rather than treating the 750-day estimate as parameter-free truth.

## PCA interpretation and residual risk

| Component group | Curve variance share | Portfolio linear variance share |
|---|---:|---:|
| PC1 | 88.0012% | 98.6039% |
| PC2 | 8.4506% | 0.9318% |
| PC3 | 2.6154% | 0.3218% |
| Remaining 27 components | 0.9328% | 0.1425% |

Loading inspection supports level, slope, and curvature-like descriptions for the first three components in the primary sample. These labels are empirical and can change with the window. All 27 remaining components enter every Monte Carlo path. Their variance is measured and never silently set to zero.

Residual curve variance is 0.9013%, 0.9328%, and 1.6026% for the 500, 750, and 1,250 windows. The variation across windows is another source of model risk.

## Stress testing

M05 evaluates 43 standard scenarios: 14 hypothetical, 11 selected historical, and 18 PCA-factor shocks. It also searches reverse-stress boundaries across configured direction families.

The largest standard scenario loss is USD 1,493,530 under a +200 bp parallel shock. The largest selected historical multi-day loss is USD 486,628 for the 10-source-day move ending 2010-12-14. The largest observed one-day Historical Simulation loss is USD 257,172 for the transition ending 2020-03-17.

| Reverse-stress loss target | Minimum parallel-up amplitude | Achieved loss |
|---:|---:|---:|
| USD 100,000 | 12.0859 bp | USD 100,030.84 |
| USD 200,000 | 24.3359 bp | USD 200,035.82 |
| USD 300,000 | 36.7578 bp | USD 300,044.24 |

Stress losses are conditional results, not probability forecasts. Reverse-stress thresholds are constrained to the configured curve-shape families and should not be interpreted as global minima over every possible yield curve.

## Historical Simulation backtesting

| Window | VaR level | Forecasts | Exceptions | Exception rate | Kupiec p | Independence p | Conditional p | 5% decision |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 500 | 95% | 4,700 | 262 | 5.57% | 0.0758 | 0.0596 | 0.0351 | Conditional coverage rejected |
| 500 | 99% | 4,700 | 70 | 1.49% | 0.0017 | 0.9625 | 0.0071 | Coverage and conditional coverage rejected |
| 750 | 95% | 4,450 | 232 | 5.21% | 0.5163 | 0.1828 | 0.3335 | Not rejected |
| 750 | 99% | 4,450 | 53 | 1.19% | 0.2138 | 0.6083 | 0.4049 | Not rejected |
| 1,250 | 95% | 3,950 | 186 | 4.71% | 0.3967 | 0.0297 | 0.0657 | Independence rejected |
| 1,250 | 99% | 3,950 | 44 | 1.11% | 0.4798 | 0.0905 | 0.1860 | Not rejected |

The maximum realized one-day loss is USD 257,172. The reported maximum cumulative drawdown of the daily recalibrated research portfolio is USD 3,472,198. This is a hypothetical research sequence, not the drawdown of a funded buy-and-hold account.

For the primary 750-day model, the mean realized-tail-loss to forecast-ES ratios are 1.0017 at 97.5% and 0.9674 at 99%. These are descriptive severity diagnostics rather than formal ES calibration tests. Passing VaR coverage does not validate ES.

## Risk interpretation

The portfolio has equal market values but unequal yield sensitivity. The 15-year position contributes approximately 60% of parallel DV01, compared with 28% for the 7-year position and 12% for the 3-year position. PC1 accounts for 98.60% of primary-window linear portfolio variance because this long-duration positive-notional portfolio is dominated by broadly level-like rate moves.

The combination of VaR, ES, stress testing, backtesting, and factor attribution supports several distinct decisions:

- Current VaR and ES quantify model-dependent one-day loss thresholds.
- Stress tests expose losses outside ordinary distributional estimates.
- Backtests assess only the forecast model and window actually tested.
- Factor and position attribution identify the sources of risk concentration.
- Window sensitivity measures estimation risk and prevents false precision.

## Model limitations

Phase one excludes coupon cash flows, accrued interest, actual Treasury security identifiers, maturity decay, carry, roll-down, funding, bid-ask costs, liquidation costs, credit spreads, default, liquidity, embedded options, intraday risk, and regulatory capital rules.

The GSW curve is an estimated public curve rather than an executable dealer surface. A one-source-day change can span weekends or holidays. Historical Simulation assumes past shocks remain relevant. Parametric Normal and PCA Monte Carlo assume Gaussian factor scores and zero daily mean. PCA factors depend on the selected window. Fixed-seed Monte Carlo controls numerical reproducibility but does not remove model uncertainty.

## Reproducibility

From a fresh checkout, run:

```bash
python scripts/run_m08_research_report.py \
  --output-root data \
  --run-prerequisites
```

The command reruns M03-M07, preserves each milestone log, validates the common date and portfolio contracts, reconciles M04 and M07 Historical Simulation estimates, creates consolidated compressed CSV tables, writes an M08 audit JSON, and generates seven PNG figures. The Colab notebook performs the same workflow from the public GitHub repository.

The live acceptance run used Python 3.12.4, NumPy 2.0.0, pandas 2.2.2, SciPy 1.14.0, Matplotlib 3.9.1, and Monte Carlo base seed `20260923`. Runtime versions are recorded dynamically in every M08 audit report.

## Acceptance evidence

- M03-M07 reports all have `PASS` status.
- Every milestone uses valuation date 2026-09-18, portfolio `treasury_zero_core`, and USD 10 million market value.
- M04 and M07 Historical Simulation estimates reconcile exactly.
- All three estimation windows and all three current-risk methods are present.
- Historical-only backtesting scope is explicit.
- PCA residual curve and portfolio variance are positive.
- All seven required figures are created and non-empty.
- Fifty-four standard-library tests pass across M02-M08.
- The clean official-GSW integration run passes all eleven M08 checks.

## Completion boundary

M08 completes the phase-one research report. It does not add coupon-bond valuation or credit-spread risk. M09 is the coupon-bond extension; M10 is the credit-risk extension. Gaussian-model rolling backtests remain a possible future validation extension and are not implied by M08 completion.
