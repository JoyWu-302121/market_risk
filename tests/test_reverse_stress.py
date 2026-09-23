"""Tests for family-constrained reverse stress search."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.curves import ZeroCurve
from bond_risk.portfolio import build_target_weight_portfolio
from bond_risk.risk.reverse_stress import search_reverse_stress


class ReverseStressTests(unittest.TestCase):
    def test_search_brackets_minimum_parallel_threshold_breach(self) -> None:
        curve = ZeroCurve(
            date(2026, 9, 18),
            np.array([1.0, 3.0, 7.0]),
            np.array([0.02, 0.03, 0.04]),
        )
        portfolio = build_target_weight_portfolio(
            portfolio_id="reverse",
            curve=curve,
            total_market_value=1_000_000.0,
            instrument_specs=[
                {"instrument_id": "ZERO_7Y", "maturity_years": 7.0, "target_weight": 1.0}
            ],
        )
        result = search_reverse_stress(
            base_curve=curve,
            portfolio=portfolio,
            directions={"parallel_up": np.ones(3), "parallel_down": -np.ones(3)},
            loss_thresholds_usd=[10_000.0],
            maximum_amplitude_bps=100.0,
            grid_step_bps=1.0,
            tolerance_bps=0.01,
        )
        upward = result.results.loc[
            result.results["direction_family"] == "parallel_up"
        ].iloc[0]
        downward = result.results.loc[
            result.results["direction_family"] == "parallel_down"
        ].iloc[0]

        self.assertEqual(upward["status"], "success")
        self.assertGreaterEqual(upward["achieved_loss"], 10_000.0)
        self.assertLess(upward["lower_bound_loss"], 10_000.0)
        self.assertEqual(downward["status"], "threshold_not_reached")
        self.assertEqual(len(result.breach_scenarios), 1)


if __name__ == "__main__":
    unittest.main()
