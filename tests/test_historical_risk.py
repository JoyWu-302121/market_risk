"""Tests for finite-sample historical VaR and Expected Shortfall."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.risk import (
    empirical_es,
    empirical_tail_weights,
    empirical_var,
    estimate_historical_risk,
)


class HistoricalRiskTests(unittest.TestCase):
    def test_nearest_rank_var_and_fractional_es_are_exact(self) -> None:
        losses = np.arange(1.0, 8.0)

        self.assertEqual(empirical_var(losses, 0.75), 6.0)
        self.assertAlmostEqual(empirical_es(losses, 0.75), (7.0 + 0.75 * 6.0) / 1.75)
        self.assertGreaterEqual(empirical_es(losses, 0.75), empirical_var(losses, 0.75))

    def test_tail_weights_sum_to_one_and_select_worst_losses(self) -> None:
        losses = np.array([4.0, 1.0, 3.0, 2.0])
        weights = empirical_tail_weights(losses, 0.625)

        self.assertAlmostEqual(float(weights.sum()), 1.0)
        np.testing.assert_allclose(weights, [2 / 3, 0.0, 1 / 3, 0.0])

    def test_non_finite_losses_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            empirical_var([1.0, np.nan], 0.99)

    def test_windows_use_latest_successful_scenarios_without_lookahead(self) -> None:
        dates = pd.date_range("2026-09-01", periods=7, freq="D")
        scenarios = pd.DataFrame(
            {
                "scenario_id": [f"S{index}" for index in range(7)],
                "shock_end_date": dates,
                "status": ["success", "success", "missing_input", "success", "success", "success", "success"],
                "loss": [1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 1000.0],
                "position_loss__A": [0.4, 0.8, np.nan, 1.6, 2.0, 2.4, 400.0],
                "position_loss__B": [0.6, 1.2, np.nan, 2.4, 3.0, 3.6, 600.0],
            }
        )
        estimates = estimate_historical_risk(
            scenarios,
            valuation_date="2026-09-06",
            windows=[3],
            var_confidence_levels=[0.50],
            es_confidence_levels=[0.50],
        )

        self.assertTrue((estimates["sample_start_date"] == "2026-09-04").all())
        self.assertTrue((estimates["sample_end_date"] == "2026-09-06").all())
        var_row = estimates.loc[estimates["measure"] == "VaR"].iloc[0]
        es_row = estimates.loc[estimates["measure"] == "ES"].iloc[0]
        self.assertEqual(var_row["value"], 5.0)
        self.assertAlmostEqual(es_row["value"], (6.0 + 0.5 * 5.0) / 1.5)
        self.assertAlmostEqual(sum(json.loads(es_row["position_contributions"]).values()), es_row["value"])

    def test_insufficient_successful_scenarios_are_rejected(self) -> None:
        scenarios = pd.DataFrame(
            {
                "scenario_id": ["S1"],
                "shock_end_date": ["2026-09-01"],
                "status": ["success"],
                "loss": [1.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "requires 2"):
            estimate_historical_risk(
                scenarios,
                valuation_date="2026-09-02",
                windows=[2],
                var_confidence_levels=[0.95],
                es_confidence_levels=[0.975],
            )


if __name__ == "__main__":
    unittest.main()
