"""Tests for frozen-position portfolio valuation and DV01."""

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


class PortfolioValuationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.curve = ZeroCurve(
            observation_date=date(2026, 9, 11),
            tenors_years=np.array([1.0, 3.0, 7.0, 15.0, 30.0]),
            zero_rates_cc=np.array([0.02, 0.03, 0.04, 0.05, 0.055]),
        )
        self.specifications = [
            {"instrument_id": "UST_ZERO_3Y", "maturity_years": 3.0, "target_weight": 1 / 3},
            {"instrument_id": "UST_ZERO_7Y", "maturity_years": 7.0, "target_weight": 1 / 3},
            {"instrument_id": "UST_ZERO_15Y", "maturity_years": 15.0, "target_weight": 1 / 3},
        ]
        self.portfolio = build_target_weight_portfolio(
            portfolio_id="treasury_zero_core",
            curve=self.curve,
            total_market_value=10_000_000.0,
            instrument_specs=self.specifications,
        )

    def test_calibrated_value_and_weights_match_targets(self) -> None:
        self.assertAlmostEqual(self.portfolio.value(self.curve), 10_000_000.0, places=6)
        report = self.portfolio.position_report(self.curve)
        np.testing.assert_allclose(report["actual_weight"], np.repeat(1 / 3, 3), atol=1e-12)

    def test_zero_shock_produces_zero_pnl_and_loss(self) -> None:
        self.assertEqual(self.portfolio.pnl(self.curve, self.curve.parallel_shift(0.0)), 0.0)
        self.assertEqual(self.portfolio.loss(self.curve, self.curve.parallel_shift(0.0)), 0.0)

    def test_upward_parallel_shift_produces_positive_loss(self) -> None:
        self.assertGreater(self.portfolio.loss(self.curve, self.curve.parallel_shift(0.0001)), 0.0)

    def test_linear_dv01_agrees_with_full_revaluation(self) -> None:
        full_dv01 = self.portfolio.full_revaluation_parallel_dv01(self.curve)
        linear_dv01 = self.portfolio.linear_parallel_dv01(self.curve)
        relative_error = abs(linear_dv01 - full_dv01) / full_dv01

        self.assertLess(relative_error, 0.001)

    def test_invalid_target_weights_are_rejected(self) -> None:
        invalid = [
            {"instrument_id": "A", "maturity_years": 3.0, "target_weight": 0.4},
            {"instrument_id": "B", "maturity_years": 7.0, "target_weight": 0.4},
        ]
        with self.assertRaisesRegex(ValueError, "sum to one"):
            build_target_weight_portfolio(
                portfolio_id="invalid",
                curve=self.curve,
                total_market_value=10_000_000.0,
                instrument_specs=invalid,
            )


if __name__ == "__main__":
    unittest.main()
