"""Tests for continuously compounded zero-curve construction."""

from __future__ import annotations

import math
import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.curves import ZeroCurve


class ZeroCurveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.curve = ZeroCurve(
            observation_date=date(2026, 9, 11),
            tenors_years=np.array([1.0, 3.0, 7.0, 15.0, 30.0]),
            zero_rates_cc=np.array([0.02, 0.03, 0.05, 0.055, 0.06]),
        )

    def test_exact_node_discount_factor(self) -> None:
        self.assertAlmostEqual(self.curve.discount_factor(3.0), math.exp(-0.03 * 3.0))

    def test_interpolation_is_linear_in_log_discount_factor(self) -> None:
        expected_log_discount = (-0.03 * 3.0 + -0.05 * 7.0) / 2.0
        self.assertAlmostEqual(self.curve.discount_factor(5.0), math.exp(expected_log_discount))
        self.assertAlmostEqual(self.curve.zero_rate(5.0), -expected_log_discount / 5.0)

    def test_parallel_shift_changes_each_node_by_decimal_amount(self) -> None:
        shifted = self.curve.parallel_shift(0.0001)
        np.testing.assert_allclose(shifted.zero_rates_cc - self.curve.zero_rates_cc, 0.0001)

    def test_extrapolation_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "within"):
            self.curve.discount_factor(0.5)
        with self.assertRaisesRegex(ValueError, "within"):
            self.curve.discount_factor(31.0)

    def test_invalid_nodes_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            ZeroCurve(
                observation_date=date(2026, 9, 11),
                tenors_years=np.array([1.0, 1.0]),
                zero_rates_cc=np.array([0.02, 0.03]),
            )

    def test_from_long_frame_uses_selected_observed_date(self) -> None:
        frame = pd.DataFrame(
            {
                "observation_date": ["2026-09-10", "2026-09-10", "2026-09-11", "2026-09-11"],
                "tenor_years": [1, 3, 1, 3],
                "zero_yield_cc": [0.02, 0.03, 0.021, 0.031],
                "is_observed": [True, True, True, True],
            }
        )
        curve = ZeroCurve.from_long_frame(frame, observation_date="2026-09-10")

        self.assertEqual(curve.observation_date, date(2026, 9, 10))
        self.assertAlmostEqual(curve.zero_rate(3.0), 0.03)

    def test_from_long_frame_skips_latest_empty_curve_date(self) -> None:
        frame = pd.DataFrame(
            {
                "observation_date": ["2026-09-18", "2026-09-18", "2026-09-21", "2026-09-21"],
                "tenor_years": [1, 3, 1, 3],
                "zero_yield_cc": [0.02, 0.03, np.nan, np.nan],
                "is_observed": [True, True, False, False],
            }
        )
        curve = ZeroCurve.from_long_frame(frame)

        self.assertEqual(curve.observation_date, date(2026, 9, 18))
        self.assertAlmostEqual(curve.zero_rate(3.0), 0.03)


if __name__ == "__main__":
    unittest.main()
