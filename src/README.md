# Source modules

Reusable data, curve, instrument, portfolio, scenario, risk, backtesting, and reporting modules will be implemented milestone by milestone.

The M02 `bond_risk.data` package provides:

- Immutable, hash-verifiable raw-payload storage with metadata sidecars
- Federal Reserve GSW download, normalization, and curve-coverage auditing
- FRED observation download and normalization without persisting the API key
- Pipeline orchestration for raw, processed, and audit artifacts

The M03 packages provide:

- A continuously compounded zero curve with linear log-discount interpolation
- Explicit rejection of unapproved curve extrapolation
- Synthetic USD zero-coupon bond pricing
- Target-market-value portfolio construction
- Frozen-position full repricing and positive-loss conventions
- Linear and full-revaluation parallel DV01 diagnostics

The M04 packages provide:

- Complete adjacent-date historical zero-curve shock construction
- Explicit missing-input and valuation-failure scenario audit rows
- Frozen-position full repricing with position-level loss contributions
- Nearest-rank empirical VaR and fractional-tail empirical ES
- Current estimates over 500, 750, and 1,250 valid-observation windows
