# Tests

Executable financial invariants and integration tests will be introduced with the corresponding implementation milestones.

Run the current standard-library test suite from the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

M04 tests verify adjacent-date shock construction, explicit missing transitions, no lookahead, frozen-position loss identities, position contribution reconciliation, exact nearest-rank VaR, fractional-tail ES, and insufficient-window rejection.
