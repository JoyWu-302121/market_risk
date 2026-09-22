# Project instructions

- Treat all results as public-data theoretical/research estimates.
- Separate observable inputs, estimated parameters, assumptions, and unavailable institution-specific information.
- Implement one accepted milestone at a time.
- Preserve raw data and provenance; never overwrite source observations with interpolated values.
- Use positive numbers for losses in VaR, ES, and stress reports.
- Use full repricing as the primary risk calculation and sensitivity approximations as diagnostics.
- Never interpret a successful VaR exception test as validation of ES.
- Do not silently discard failed dates, infeasible scenarios, or residual PCA risk.
- Do not commit raw market-data archives, generated large results, credentials, or third-party documents.
- Write repository documentation, notebook narratives, configuration comments, and user-facing research outputs in English.
- Keep Colab notebooks thin: reusable pricing and risk logic belongs under `src/`.
