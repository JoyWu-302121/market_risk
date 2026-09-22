# Bond Portfolio Risk Engine

Research-grade market-risk engine for a US Treasury bond portfolio, covering Value at Risk (VaR), Expected Shortfall (ES), stress testing, backtesting, and yield-curve risk decomposition.

## Current status

**Milestone M01 — research specification locked.**

This repository currently contains the research scope, data contract, validation rules, and milestone plan. It does not yet contain a validated pricing engine, downloaded market data, VaR/ES estimates, or backtest results.

## Phase-one scope

- Portfolio: equal-weight synthetic 3Y, 7Y, and 15Y US Treasury zero-coupon bonds
- Initial core market value: USD 10,000,000
- Primary risk factors: continuously compounded zero-coupon Treasury yields
- Primary valuation: full repricing under yield-curve shocks
- Risk measures: 1-day 95% and 99% VaR; 1-day 97.5% and 99% ES
- Scenario methods: historical simulation, variance-covariance, and PCA Monte Carlo
- Stress testing: parallel, steepener/flattener, butterfly, historical replay, statistical, and reverse stress scenarios
- Primary estimation window: 750 trading days; 500 and 1,250 days as sensitivities

The phase-one result is a public-data research model. It is not a bank quote, a regulatory capital engine, or an investment recommendation.

## Documentation

- [Week 1 research specification](docs/WEEK01_RESEARCH_SPEC.md)
- [Data dictionary](docs/DATA_DICTIONARY.md)
- [Week 1 acceptance criteria](docs/WEEK01_ACCEPTANCE.md)
- [Milestones](docs/MILESTONES.md)

## Planned repository structure

```text
configs/       Model, portfolio, and stress-scenario configuration
data/          Local raw/interim/processed data; excluded from Git
docs/          Research contracts and validation documentation
notebooks/     Reviewable research notebooks
src/           Reusable pricing and risk modules
tests/         Financial invariants and integration tests
```

## Reproducibility rules

1. Keep raw, cleaned, and model-input data separate.
2. Store source, retrieval date, units, tenor, and revision/vintage metadata.
3. Use the same frozen portfolio and valuation function across competing risk methods.
4. Record missing inputs and failed scenarios explicitly; never replace them with zero or silently remove dates.
5. Keep P-measure risk scenarios separate from Q-measure derivative-pricing calibration.
