# Tests

Executable financial invariants and integration tests will be introduced with the corresponding implementation milestones.

Run the current standard-library test suite from the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

M04 tests verify adjacent-date shock construction, explicit missing transitions, no lookahead, frozen-position loss identities, position contribution reconciliation, exact nearest-rank VaR, fractional-tail ES, and insufficient-window rejection.

M05 tests verify hypothetical curve shapes, full and key-rate attribution identities, PCA orthonormality and residual variance, historical multi-day missing-data boundaries, and reverse-stress threshold bracketing.
