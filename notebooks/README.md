# Notebooks

Reviewable research notebooks will be added after reusable logic is implemented under `src/`. Notebooks must not contain secrets or become the sole source of pricing and risk logic.

- [`00_colab_setup.ipynb`](00_colab_setup.ipynb): initializes and verifies a Google Colab runtime.
- [`01_public_data_ingestion.ipynb`](01_public_data_ingestion.ipynb): downloads, versions, normalizes, and audits GSW/FRED public data.
- [`02_curve_and_valuation.ipynb`](02_curve_and_valuation.ipynb): constructs the zero curve, calibrates the phase-one portfolio, and validates full repricing and DV01.
