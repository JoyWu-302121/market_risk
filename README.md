# Bond Portfolio Risk Engine

Research-grade market-risk engine for a US Treasury bond portfolio, covering Value at Risk (VaR), Expected Shortfall (ES), stress testing, backtesting, and yield-curve risk decomposition.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/JoyWu-302121/market_risk/blob/main/notebooks/00_colab_setup.ipynb)

## Current status

**Milestone M08 — phase-one research report and reproducibility validation complete.**

This repository contains the research contract, a tested and versioned GSW/FRED ingestion layer, a validated phase-one pricing engine, historical-simulation VaR/ES, full-repricing stress testing, rolling backtest diagnostics, parametric/PCA Monte Carlo benchmarks, and a reproducible research report for synthetic Treasury zero-coupon positions.

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
- [Google Colab workflow](docs/COLAB_WORKFLOW.md)
- [M02 data ingestion and acceptance](docs/M02_DATA_INGESTION.md)
- [M03 curve and valuation acceptance](docs/M03_CURVE_VALUATION.md)
- [M04 historical VaR and ES acceptance](docs/M04_HISTORICAL_VAR_ES.md)
- [M05 stress-testing acceptance](docs/M05_STRESS_TESTING.md)
- [M06 backtesting acceptance](docs/M06_BACKTESTING.md)
- [M07 parametric and PCA Monte Carlo acceptance](docs/M07_PARAMETRIC_PCA_MONTE_CARLO.md)
- [M08 phase-one research report](docs/M08_RESEARCH_REPORT.md)

## Planned repository structure

```text
configs/       Model, portfolio, and stress-scenario configuration
data/          Local raw/interim/processed data; excluded from Git
docs/          Research contracts and validation documentation
notebooks/     Reviewable research notebooks
src/           Reusable pricing and risk modules
tests/         Financial invariants and integration tests
```

## Google Colab

Google Colab is the primary interactive development environment for this project. Use the badge above to open the setup notebook directly from GitHub. The notebook clones the current `main` branch into the Colab runtime, installs the declared dependencies, and verifies the repository layout.

Colab runtimes are temporary. GitHub remains the source of truth for notebooks, source code, configuration, and documentation. Do not rely on files under `/content` as permanent storage.

After the setup notebook succeeds, run [`01_public_data_ingestion.ipynb`](notebooks/01_public_data_ingestion.ipynb) to reproduce the M02 GSW download and audit.

Run [`02_curve_and_valuation.ipynb`](notebooks/02_curve_and_valuation.ipynb) to reproduce M03 curve construction, portfolio calibration, full repricing, and DV01 checks.

Run [`03_historical_var_es.ipynb`](notebooks/03_historical_var_es.ipynb) to reproduce M04 complete-curve shock construction, scenario auditing, and rolling-window historical VaR/ES.

Run [`04_stress_testing.ipynb`](notebooks/04_stress_testing.ipynb) to reproduce M05 hypothetical, historical, PCA-factor, and reverse stress tests.

Run [`05_backtesting.ipynb`](notebooks/05_backtesting.ipynb) to reproduce M06 rolling VaR coverage and Expected Shortfall tail diagnostics.

Run [`06_parametric_pca_monte_carlo.ipynb`](notebooks/06_parametric_pca_monte_carlo.ipynb) to reproduce M07 Historical Simulation, Parametric Normal, and full-covariance PCA Monte Carlo comparisons.

Run [`07_research_report.ipynb`](notebooks/07_research_report.ipynb) to reproduce the complete M03-M08 validation, consolidated tables, and report figures.

## Reproducibility rules

1. Keep raw, cleaned, and model-input data separate.
2. Store source, retrieval date, units, tenor, and revision/vintage metadata.
3. Use the same frozen portfolio and valuation function across competing risk methods.
4. Record missing inputs and failed scenarios explicitly; never replace them with zero or silently remove dates.
5. Keep P-measure risk scenarios separate from Q-measure derivative-pricing calibration.
