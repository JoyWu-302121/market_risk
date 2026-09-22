# M01 Research Specification

Status: **Locked for phase-one implementation**

## 1. Objective

Build a reproducible research engine that measures the market risk of a US Treasury portfolio through VaR, Expected Shortfall, and stress testing. All methods must use the same portfolio snapshot, yield-curve inputs, valuation function, loss convention, and forecast horizon.

## 2. Phase-one portfolio

At the initial valuation date, the core portfolio contains synthetic zero-coupon Treasury exposures with remaining maturities of 3, 7, and 15 years. Each position has one-third of the USD 10,000,000 core market value.

Zero-coupon instruments isolate yield-curve risk and provide an exact phase-one valuation benchmark. Fixed-rate coupon bonds, credit spreads, liquidity risk, default risk, and embedded options are later extensions.

## 3. Market inputs

The primary curve source is the Federal Reserve Gürkaynak-Sack-Wright nominal Treasury curve. Phase one uses `SVENYXX` continuously compounded zero-coupon yields. `SVENPYXX` par yields must not be substituted or mixed with zero yields.

FRED series may be used for cash/funding proxies. These proxies must be identified by series ID and must retain retrieval and vintage metadata.

## 4. Valuation and P&L contract

For a zero-coupon cash flow with notional `N`, continuously compounded zero yield `y`, and year fraction `tau`:

```text
P = N * exp(-y * tau)
```

The one-day frozen-position market P&L is:

```text
market_pnl(t+1) = V(y(t+1), q(t)) - V(y(t), q(t))
loss(t+1) = -market_pnl(t+1)
```

Losses are positive. The position vector is frozen over the risk horizon. Primary risk results use full repricing. DV01, key-rate DV01, duration, and convexity are explanatory approximations.

Carry, roll-down, financing, rebalancing, and transaction costs must be reported separately before any total-P&L aggregation.

## 5. Risk measures

The engine reports:

- 1-day historical-simulation VaR at 95% and 99%
- 1-day historical-simulation ES at 97.5% and 99%
- Parametric normal VaR as a benchmark
- PCA Monte Carlo VaR and ES after the simulation model is accepted
- Maximum loss, maximum drawdown, and risk contributions by instrument and curve factor

The primary rolling window is 750 valid trading days. Results are repeated with 500 and 1,250 days as sensitivity checks.

Finite-sample VaR and ES must use a documented empirical-quantile and tail-weight convention. ES must not be computed by an undocumented filtering rule around the quantile boundary.

## 6. Historical simulation

For each historical date `s`, apply the complete observed zero-curve change to the current curve and fully reprice the current frozen portfolio:

```text
shock(s) = y(s) - y(s-1)
scenario_curve(s) = y(t) + shock(s)
scenario_loss(s) = -(V(scenario_curve(s), q(t)) - V(y(t), q(t)))
```

Historical shocks must be selected only from information available at the forecast date. Failed curve construction or valuation remains an explicit failed observation and is never converted to a zero loss.

## 7. Parametric and PCA models

The variance-covariance benchmark uses the current key-rate sensitivity vector and an estimated yield-change covariance matrix.

PCA is fitted to historical zero-curve changes within the rolling estimation window. The first three factors are interpreted as level, slope, and curvature only after inspecting their loadings. Residual variation outside the first three factors must be measured and retained in the risk report.

Any Vasicek/OU or PCA-OU process is a P-measure scenario model. It must not be presented as a Q-measure calibration for derivative pricing.

## 8. Stress-testing framework

The initial library contains:

- Parallel shocks: +/-50, +/-100, and +/-200 basis points
- Steepener and flattener shocks across defined curve nodes
- Butterfly shocks concentrated in intermediate maturities
- Historical replay of extreme one-day and multi-day curve changes
- PCA factor shocks of +/-2, +/-3, and +/-4 historical standard deviations
- Reverse stress: minimum permitted curve shock that breaches a specified loss threshold

Each result includes total loss, position-level contribution, curve-node contribution, and the difference between full repricing and sensitivity approximation.

## 9. Backtesting

VaR validation reports exception counts, Kupiec unconditional coverage, Christoffersen independence/conditional coverage, and exception clustering.

ES validation separately compares forecast ES with realised tail losses. Passing VaR coverage tests does not validate ES.

## 10. Research boundaries

Phase one excludes:

- Corporate-credit and default risk
- Bid-ask and liquidation-cost modelling
- Callable or puttable bonds
- Mortgage-backed securities
- Regulatory capital claims
- Live trading or investment recommendations
