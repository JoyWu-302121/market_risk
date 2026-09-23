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
