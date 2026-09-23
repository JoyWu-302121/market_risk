"""Tests for hypothetical stress shapes, attribution, and key-rate risk."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.curves import ZeroCurve
from bond_risk.portfolio import build_target_weight_portfolio
from bond_risk.risk import key_rate_dv01
from bond_risk.scenarios import (
    CurveStressScenario,
    build_hypothetical_scenarios,
    butterfly_shape,
    evaluate_stress_scenarios,
    slope_shape,
)


class StressEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.curve = ZeroCurve(
            date(2026, 9, 18),
            np.array([1.0, 3.0, 7.0, 15.0, 30.0]),
            np.array([0.02, 0.03, 0.04, 0.05, 0.055]),
        )
        self.portfolio = build_target_weight_portfolio(
            portfolio_id="stress_test",
            curve=self.curve,
            total_market_value=10_000_000.0,
            instrument_specs=[
                {"instrument_id": "ZERO_3Y", "maturity_years": 3.0, "target_weight": 0.5},
                {"instrument_id": "ZERO_15Y", "maturity_years": 15.0, "target_weight": 0.5},
            ],
        )

    def test_slope_and_butterfly_anchor_shapes(self) -> None:
        slope = slope_shape(self.curve.tenors_years, pivot_years=7.0)
        butterfly = butterfly_shape(self.curve.tenors_years, center_years=7.0)

        np.testing.assert_allclose(slope[[0, 2, 4]], [-1.0, 0.0, 1.0])
        np.testing.assert_allclose(butterfly[[0, 2, 4]], [0.0, 1.0, 0.0])

    def test_hypothetical_library_has_all_accepted_scenarios(self) -> None:
        scenarios = build_hypothetical_scenarios(
            tenors_years=self.curve.tenors_years,
            parallel_amplitudes_bps=[50, 100, 200],
            slope_pivot_years=7.0,
            slope_amplitudes_bps=[50, 100],
            butterfly_center_years=7.0,
            butterfly_amplitudes_bps=[50, 100],
        )

        self.assertEqual(len(scenarios), 14)
        self.assertEqual(len({scenario.scenario_id for scenario in scenarios}), 14)

    def test_full_repricing_and_attributions_reconcile(self) -> None:
        scenario = CurveStressScenario(
            scenario_id="UP_100",
            scenario_family="test",
            description="parallel up 100 bp",
            tenors_years=self.curve.tenors_years,
            shock_decimal=np.repeat(0.01, len(self.curve.tenors_years)),
        )
        result = evaluate_stress_scenarios(
            base_curve=self.curve, portfolio=self.portfolio, scenarios=[scenario]
        ).iloc[0]

        self.assertEqual(result["status"], "success")
        self.assertGreater(result["loss"], 0.0)
        self.assertAlmostEqual(
            sum(json.loads(result["position_loss_contributions"]).values()),
            result["loss"],
            places=8,
        )
        self.assertAlmostEqual(
            sum(json.loads(result["linear_key_rate_contributions"]).values()),
            result["linear_sensitivity_loss"],
            places=8,
        )
        self.assertNotEqual(result["full_minus_linear"], 0.0)

    def test_key_rate_sensitivity_is_concentrated_at_cashflow_nodes(self) -> None:
        sensitivities = key_rate_dv01(self.portfolio, self.curve)

        self.assertAlmostEqual(sensitivities[0], 0.0)
        self.assertGreater(sensitivities[1], 0.0)
        self.assertAlmostEqual(sensitivities[2], 0.0)
        self.assertGreater(sensitivities[3], 0.0)
        self.assertAlmostEqual(sensitivities[4], 0.0)


if __name__ == "__main__":
    unittest.main()
