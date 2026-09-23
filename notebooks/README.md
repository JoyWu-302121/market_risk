# Notebooks

Reviewable research notebooks will be added after reusable logic is implemented under `src/`. Notebooks must not contain secrets or become the sole source of pricing and risk logic.

- [`00_colab_setup.ipynb`](00_colab_setup.ipynb): initializes and verifies a Google Colab runtime.
- [`01_public_data_ingestion.ipynb`](01_public_data_ingestion.ipynb): downloads, versions, normalizes, and audits GSW/FRED public data.
- [`02_curve_and_valuation.ipynb`](02_curve_and_valuation.ipynb): constructs the zero curve, calibrates the phase-one portfolio, and validates full repricing and DV01.
- [`03_historical_var_es.ipynb`](03_historical_var_es.ipynb): builds complete historical curve shocks and estimates full-revaluation VaR and Expected Shortfall over the accepted windows.
- [`04_stress_testing.ipynb`](04_stress_testing.ipynb): runs hypothetical, historical, PCA-factor, and reverse stress tests with full-repricing and key-rate diagnostics.
- [`05_backtesting.ipynb`](05_backtesting.ipynb): reproduces rolling Historical VaR coverage tests and separate Expected Shortfall tail diagnostics.
- [`06_parametric_pca_monte_carlo.ipynb`](06_parametric_pca_monte_carlo.ipynb): compares Historical Simulation, Parametric Normal, and complete-covariance PCA Monte Carlo risk with residual and position attribution.
- [`07_research_report.ipynb`](07_research_report.ipynb): reruns M03-M08 from official GSW data and displays the consolidated phase-one tables and figures.
