"""Tests for synthetic zero-coupon bond valuation."""

from __future__ import annotations

import math
import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.curves import ZeroCurve
from bond_risk.instruments import ZeroCouponBond


class ZeroCouponBondTests(unittest.TestCase):
    def setUp(self) -> None:
        self.curve = ZeroCurve(
            observation_date=date(2026, 9, 11),
            tenors_years=np.array([1.0, 3.0, 7.0, 15.0, 30.0]),
            zero_rates_cc=np.array([0.02, 0.03, 0.04, 0.05, 0.055]),
        )

    def test_price_matches_continuous_compounding_formula(self) -> None:
        bond = ZeroCouponBond("UST_ZERO_7Y", maturity_years=7.0, face_value=100.0)
        self.assertAlmostEqual(bond.price(self.curve), 100.0 * math.exp(-0.04 * 7.0))

    def test_upward_yield_shift_reduces_price(self) -> None:
        bond = ZeroCouponBond("UST_ZERO_15Y", maturity_years=15.0)
        self.assertLess(bond.price(self.curve.parallel_shift(0.0001)), bond.price(self.curve))

    def test_invalid_instrument_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "maturity_years"):
            ZeroCouponBond("INVALID", maturity_years=0.0)
        with self.assertRaisesRegex(ValueError, "USD"):
            ZeroCouponBond("EUR_ZERO", maturity_years=3.0, currency="EUR")


if __name__ == "__main__":
    unittest.main()
