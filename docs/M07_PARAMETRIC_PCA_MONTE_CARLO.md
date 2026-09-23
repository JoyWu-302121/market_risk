# M07 Parametric Normal and PCA Monte Carlo Benchmarks

Status: **Complete for the phase-one synthetic zero-coupon portfolio**

## Objective

M07 adds two comparable one-day market-risk benchmarks to M04 Historical Simulation. All three methods use the same latest valid GSW curve date, USD 10 million equal-weight 3Y/7Y/15Y frozen portfolio, positive-loss convention, estimation windows, confidence levels, and continuously compounded zero-rate changes.

The models estimate physical-measure (`P`) portfolio risk. They are not risk-neutral (`Q`) derivative-pricing calibrations, regulatory capital models, or executable market quotes.

## Models

### Historical Simulation

The benchmark reuses observed complete 1Y-30Y curve changes and exact zero-coupon full repricing. VaR is the nearest-rank order statistic. ES uses fractional finite-sample tail mass. This model preserves observed skewness, tails, and cross-tenor dependence inside the selected window.

### Parametric Normal

The parametric benchmark estimates the 30-by-30 sample covariance matrix from the same historical window and assumes a zero-mean multivariate normal curve change. Portfolio loss is linearized with the current central-difference key-rate sensitivity vector `g`:

```text
sigma_loss = sqrt(g' * covariance * g)
VaR_alpha = normal_quantile(alpha) * sigma_loss
ES_alpha = normal_density(normal_quantile(alpha)) / (1 - alpha) * sigma_loss
```

Euler position contributions use each position's sensitivity covariance with total portfolio loss and reconcile exactly to VaR or ES. The model is transparent and fast, but normality and linear valuation suppress historical tail shape and convexity.

### PCA Gaussian Monte Carlo

For each window, M07 centers the complete curve-change matrix and applies singular-value decomposition. The first three principal components are reported as interpretable factors. Every remaining orthogonal component is retained in the simulation, so the simulated covariance reconstructs the full sample covariance rather than truncating it at three factors.

The engine draws 100,000 independent standard-normal factor vectors with a fixed seed, scales them by all 30 historical eigenvalue standard deviations, reconstructs curve shocks, and fully reprices every frozen zero-coupon position:

```text
position_loss_i = market_value_i * [1 - exp(-shock_i * maturity_i)]
```

Monte Carlo VaR and ES use the same finite-sample conventions as Historical Simulation. Boundary-scenario VaR contributions and fractional-tail ES contributions reconcile exactly to portfolio risk.

## Live model comparison

The official GSW validation ends on 2026-09-18. The primary window contains the latest 750 successful complete curve changes.

| Method | 95% VaR | 99% VaR | 97.5% ES | 99% ES |
|---|---:|---:|---:|---:|
| Historical Simulation | USD 73,279.18 | USD 118,476.34 | USD 115,182.16 | USD 128,201.20 |
| Parametric Normal | USD 74,041.09 | USD 104,717.73 | USD 105,233.36 | USD 119,971.38 |
| PCA Monte Carlo | USD 73,579.71 | USD 104,136.32 | USD 104,481.96 | USD 119,260.51 |

Parametric Normal and PCA Monte Carlo are close because they share the same Gaussian covariance assumption; their difference comes primarily from Monte Carlo sampling and full-repricing convexity. Historical 99% VaR and both ES measures are higher, which is evidence that the observed 750-day loss distribution has more severe upper-tail behavior than the fitted Gaussian benchmark. It does not prove that any model is universally superior.

## PCA and residual risk

| Component group | Curve variance share | Portfolio linear variance share |
|---|---:|---:|
| PC1 | 88.0012% | 98.6039% |
| PC2 | 8.4506% | 0.9318% |
| PC3 | 2.6154% | 0.3218% |
| Remaining 27 components | 0.9328% | 0.1425% |

The first three components explain 99.0672% of total curve-change variance, but this does not justify deleting the remaining components. Residual factors explain 0.9328% of curve variance and 0.1425% of this portfolio's linear loss variance. M07 retains that contribution in every simulated path.

The factor labels should be assigned only after inspecting loading shapes. In the current sample, the first three resemble level, slope, and curvature-like movements, consistent with M05. These are empirical descriptions and can change with the data window.

## Reproducibility and diagnostics

- Windows: 500, 750, and 1,250 successful curve changes.
- Simulations: 100,000 per window.
- Base seed: `20260923`; the window size is added to produce a stable per-window seed.
- Probability measure: `P`.
- Mean assumption: zero daily curve change for the Gaussian benchmarks.
- Covariance estimator: sample covariance with `n - 1` denominator.
- PCA residual rule: retain all components after PC3.
- Valuation: linear key-rate approximation for Parametric Normal; exact frozen-position repricing for Historical Simulation and PCA Monte Carlo.

The simulated-versus-target covariance Frobenius relative errors were 0.27%, 0.40%, and 0.41% for the 500, 750, and 1,250 windows. All were below the 3% acceptance threshold.

## Acceptance evidence

- Every method, window, measure, and confidence level is present.
- Every estimation sample ends no later than the valuation date.
- Full PCA eigenvectors are orthonormal and reconstruct sample covariance.
- Residual curve and portfolio variance are positive and retained.
- Simulated covariance error is below 3% for every window.
- Factor variance shares sum to one.
- Position contributions reconcile to every reported risk measure.
- Same-confidence 99% ES is not below 99% VaR.
- Fixed seeds produce identical simulation losses.
- Fifty standard-library tests pass across M02-M07.
- The live end-to-end report passes all ten M07 implementation checks.

## Completion boundary

M07 compares current risk estimates; it does not backtest the new Gaussian models. M06's historical-model coverage conclusions do not transfer to Parametric Normal or PCA Monte Carlo. The phase-one data also omit coupon cash flows, Treasury-specific instrument metadata, carry, roll-down, bid-ask costs, funding, credit spreads, liquidity, and intraday risk. M08 consolidates these results, limitations, and reproducibility evidence in the phase-one research report.
