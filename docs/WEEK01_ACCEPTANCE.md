# M01 Acceptance Criteria

Status: **Accepted specification; implementation evidence pending**

M01 is complete as a documentation milestone when every item below is represented in the research and data contracts. These checks become executable tests in later milestones.

## Units and conventions

- [x] Yield storage uses decimal annual rates: 100 basis points equals `0.01`.
- [x] Continuously compounded zero yields and par yields are explicitly separated.
- [x] Loss is defined as negative P&L, so losses are positive.
- [x] The risk horizon and confidence level are stored with every VaR/ES result.

## Valuation invariants

- [x] A zero curve shock must produce zero market P&L before carry and time passage.
- [x] A positive parallel yield shock must reduce the value of a standard positive-notional zero-coupon bond.
- [x] For a sufficiently small parallel shock, full-revaluation P&L must agree with the DV01 approximation within a documented tolerance.
- [x] Base and shocked valuations must use the same frozen positions.

## Risk-measure invariants

- [x] At the same confidence level and under the positive-loss convention, empirical ES must not be lower than empirical VaR.
- [x] Historical, parametric, and PCA methods use the same valuation date and portfolio snapshot.
- [x] PCA reports explained and residual variance; residual risk is not silently set to zero.
- [x] VaR exception diagnostics and ES tail diagnostics are reported separately.

## Data and auditability

- [x] Every model field has a source, unit, frequency, and missing-data rule.
- [x] Raw observations are never overwritten by interpolated values.
- [x] Retrieval time and source vintage are retained when available.
- [x] Missing inputs and valuation failures receive an explicit status rather than a zero value or a silently deleted row.

## M01 completion boundary

Documentation is complete. No claim is made that pricing, scenario generation, VaR, ES, stress testing, or backtesting has been implemented or empirically validated.
