# Configurations

Portfolio, risk-model, and stress-scenario configuration files will be added in M02-M05. Units and defaults must be explicit and validated before use.

- [`data_sources.yaml`](data_sources.yaml) defines the approved GSW/FRED endpoints, analysis start date, required tenors, source units, model units, and staleness threshold.
- [`portfolio.yaml`](portfolio.yaml) defines the phase-one portfolio, curve convention, DV01 bump, and validation tolerance.
- [`risk.yaml`](risk.yaml) defines the M04 one-day historical-simulation windows, confidence levels, complete curve-node set, full-repricing method, and finite-sample VaR/ES conventions.
