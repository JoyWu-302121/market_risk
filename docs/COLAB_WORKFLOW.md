# Google Colab Workflow

Google Colab is the primary interactive development environment for this project. GitHub is the source of truth for notebooks, source modules, configuration, tests, and documentation.

## 1. Open the project notebook

Open the setup notebook from the repository:

[Open `00_colab_setup.ipynb` in Google Colab](https://colab.research.google.com/github/JoyWu-302121/market_risk/blob/main/notebooks/00_colab_setup.ipynb)

Alternatively, in Colab select **File > Open notebook > GitHub**, enter `JoyWu-302121/market_risk`, and choose the notebook.

## 2. Initialize the runtime

Run the notebook from top to bottom. It will:

1. Confirm that it is running in Colab.
2. Clone the repository into `/content/market_risk`, or fast-forward an existing runtime copy.
3. Install packages from `requirements-colab.txt`.
4. Add `src/` to the Python import path.
5. Print dependency versions and verify required project documents.

The clone is intentionally read-only for the standard workflow. No GitHub credential is required to run a public repository.

## 3. Store API keys safely

Use the **Secrets** panel in Colab for credentials such as a FRED API key:

1. Open the key icon in the left sidebar.
2. Add a secret named `FRED_API_KEY`.
3. Grant the notebook permission to access the secret.
4. Read it with `google.colab.userdata.get("FRED_API_KEY")`.

Never paste an API key into a notebook cell, configuration file, output, Git remote URL, or committed `.env` file. The setup notebook checks whether the secret exists without displaying its value.

## 4. Save notebook changes

For notebook-only changes, use **File > Save a copy in GitHub** and select:

- Repository: `JoyWu-302121/market_risk`
- Branch: `main`, unless a separate working branch is intentionally created
- Path: the appropriate location under `notebooks/`

Before saving, clear temporary outputs or enable Colab's option to omit code-cell output when saving. Outputs may contain large tables, local paths, or sensitive data.

For changes to reusable Python modules, tests, configurations, or documentation, make the change in the local Git checkout and push it through the normal reviewed Git workflow. This keeps notebook experimentation separate from reusable model logic.

## 5. Persist research outputs

The Colab runtime filesystem is temporary. Use one of these patterns:

- Commit small, reviewable notebooks, configurations, and documentation to GitHub.
- Download compact result tables needed for review.
- Mount Google Drive for private intermediate research outputs.
- Recreate raw and processed public data through versioned pipeline code.

Do not commit raw market-data archives, large generated results, API keys, or Drive-mounted files.

## 6. Recommended notebook responsibilities

Notebooks should:

- Call reusable functions from `src/`.
- Display data-audit summaries and research results.
- State the valuation date, data vintage, configuration, and random seed.
- Separate observable inputs, estimated parameters, assumptions, and unavailable data.

Notebooks should not become the only location for curve construction, pricing, VaR, ES, stress testing, or backtesting logic.

## 7. Runtime reproducibility

Colab updates its runtime packages over time. The notebook installs this repository's declared dependency ranges and prints the resulting versions. Each completed research result should record:

- Git commit hash
- Python version
- Package versions
- Valuation date and data vintage
- Configuration file or parameters
- Random seed for simulation

GPU acceleration is unnecessary for the initial bond-pricing and historical-simulation milestones. A standard CPU runtime is sufficient.
