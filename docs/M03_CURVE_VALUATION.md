# M03 Curve Construction, Valuation, and DV01

Status: **Complete for the phase-one synthetic zero-coupon portfolio**

## Objective

Convert the accepted M02 GSW zero-yield observations into a valuation curve, price the phase-one 3Y/7Y/15Y synthetic Treasury portfolio, and demonstrate that the full-revaluation engine satisfies the financial invariants required before historical VaR and ES.

## Curve convention

The source fields `SVENY01` through `SVENY30` are continuously compounded zero yields. For node maturity `T_i` and decimal zero yield `y_i`, the discount factor is:

```text
D(T_i) = exp(-y_i * T_i)
```

Between two curve nodes, the engine interpolates linearly in log discount factors:

```text
log D(T) = w * log D(T_i) + (1 - w) * log D(T_(i+1))
```

The implied continuously compounded rate is:

```text
y(T) = -log D(T) / T
```

This rule preserves the pricing relationship between zero rates and discount factors. The engine rejects maturities outside the observed 1Y-30Y range rather than applying an undocumented extrapolation.

## Instrument valuation

Each phase-one instrument is a synthetic USD zero-coupon bond with one payment at its remaining maturity:

```text
price = face_value * D(maturity)
```

The 3Y, 7Y, and 15Y positions are calibrated to one-third of the USD 10,000,000 initial market value:

```text
quantity_i = target_weight_i * portfolio_market_value / price_i
```

Quantities are then frozen when the portfolio is repriced under a curve shock. The M03 shock comparison holds remaining maturity fixed; carry, roll-down, and passage of time are outside this valuation invariant.

## P&L and loss convention

For base curve `y` and shocked curve `y*`:

```text
pnl = V(y*, q) - V(y, q)
loss = -pnl
```

An upward yield shock therefore produces negative P&L and positive loss for the long-only zero-coupon portfolio.

## DV01 definitions

The full-revaluation parallel DV01 is the positive loss from an upward one-basis-point shift:

```text
full_revaluation_dv01 = V(y, q) - V(y + 0.0001, q)
```

The first-order zero-coupon approximation is:

```text
linear_dv01 = sum_i market_value_i * maturity_i * 0.0001
```

The configured acceptance tolerance requires the relative difference between the two measures to be no greater than 0.1% for the 1 bp diagnostic.

## Live validation snapshot

The engine was revalidated against the official GSW curve dated 2026-09-18.

| Check | Result |
|---|---:|
| Curve nodes | 30 |
| Curve range | 1Y-30Y |
| Base portfolio market value | USD 10,000,000.00 |
| 3Y market value | USD 3,333,333.33 |
| 7Y market value | USD 3,333,333.33 |
| 15Y market value | USD 3,333,333.33 |
| Full-revaluation DV01 | USD 8,328.62 |
| Linear DV01 | USD 8,333.33 |
| Relative linearization error | 0.0566% |
| Zero-shock P&L | USD 0.00 |
| Validation status | PASS |

Position-level full-revaluation DV01 was approximately USD 999.85 for 3Y, USD 2,332.52 for 7Y, and USD 4,996.25 for 15Y. These amounts show the intended concentration of parallel-rate risk in the longest maturity even though market-value weights are equal.

## Acceptance evidence

- Exact curve nodes reproduce their continuously compounded discount factors.
- Intermediate maturities use linear interpolation in log discount factors.
- Unapproved extrapolation below 1Y or above 30Y raises an error.
- Positive parallel yield shocks reduce long zero-coupon bond values.
- Portfolio calibration reproduces USD 10 million and equal market-value weights.
- A zero curve shock produces exactly zero frozen-position P&L.
- Full-revaluation DV01 is positive.
- Linear DV01 agrees with full repricing within the configured tolerance.
- Twenty-six standard-library unit tests pass across M02 and M03.

## Completion boundary

M03 validates one-date curve construction and frozen-position repricing. M04 will apply historical daily curve changes to a current frozen portfolio and estimate empirical VaR and Expected Shortfall. Backtesting forecast exceptions remains M06 work.
