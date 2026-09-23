# Project Milestones

| ID | Milestone | Main deliverable | Status |
|---|---|---|---|
| M01 | Research and data contracts | Scope, dictionary, and acceptance criteria | Complete — documentation only |
| M02 | Public-data ingestion | Versioned GSW/FRED download and data audit | Complete — primary GSW live; optional FRED adapter ready |
| M03 | Curve and valuation engine | Curve interpolation, zero-coupon pricing, DV01 checks | Complete — live GSW valuation validated |
| M04 | Historical VaR and ES | Rolling-window full-revaluation estimates | Complete — live GSW validation passed |
| M05 | Stress-testing engine | Hypothetical, historical, PCA, and reverse stresses | Complete — live GSW validation passed |
| M06 | Backtesting | VaR exception and ES tail diagnostics | Complete — live GSW validation passed |
| M07 | Parametric and PCA simulation | Comparable benchmark models and residual risk | Not started |
| M08 | Research report | Results, limitations, sensitivities, and reproducibility | Not started |
| M09 | Coupon-bond extension | Cash-flow schedules and key-rate duration | Not started |
| M10 | Credit-risk extension | Spread risk and corporate-bond scenarios | Not started |

Each milestone must preserve the distinction among specification, implementation, test evidence, and empirical research results.

Google Colab is the primary interactive environment. GitHub remains the source of truth, and each executable milestone must run from a fresh Colab session using only committed code, declared dependencies, approved secrets, and reproducible public-data retrieval.
