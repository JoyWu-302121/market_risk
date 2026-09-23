"""Tests for historical curve-shock construction and full repricing."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.curves import ZeroCurve
from bond_risk.portfolio import build_target_weight_portfolio
from bond_risk.scenarios import build_historical_curve_shocks, revalue_historical_scenarios


def curve_history() -> pd.DataFrame:
    rows = []
    curves = {
        "2026-09-08": [0.0200, 0.0300, 0.0400],
        "2026-09-09": [0.0210, 0.0310, 0.0410],
        "2026-09-10": [0.0220, np.nan, 0.0420],
        "2026-09-11": [0.0205, 0.0305, 0.0405],
        "2026-09-14": [0.0215, 0.0315, 0.0415],
    }
    for observation_date, rates in curves.items():
        for tenor, rate in zip([1.0, 3.0, 7.0], rates, strict=True):
            rows.append(
                {
                    "observation_date": observation_date,
                    "tenor_years": tenor,
                    "zero_yield_cc": rate,
                    "is_observed": bool(np.isfinite(rate)),
                }
            )
    return pd.DataFrame(rows)


class HistoricalScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_curve = ZeroCurve(
            observation_date=date(2026, 9, 14),
            tenors_years=np.array([1.0, 3.0, 7.0]),
            zero_rates_cc=np.array([0.02, 0.03, 0.04]),
        )
        self.portfolio = build_target_weight_portfolio(
            portfolio_id="test",
            curve=self.base_curve,
            total_market_value=3_000_000.0,
            instrument_specs=[
                {"instrument_id": "ZERO_3Y", "maturity_years": 3.0, "target_weight": 0.5},
                {"instrument_id": "ZERO_7Y", "maturity_years": 7.0, "target_weight": 0.5},
            ],
        )

    def test_missing_date_is_explicit_and_is_not_bridged(self) -> None:
        shock_set = build_historical_curve_shocks(
            curve_history(), required_tenors=[1.0, 3.0, 7.0], as_of_date="2026-09-14"
        )

        self.assertEqual(len(shock_set.audit), 4)
        self.assertEqual(len(shock_set.shocks), 2)
        self.assertEqual(
            shock_set.audit["status"].tolist(),
            ["success", "missing_input", "missing_input", "success"],
        )
        self.assertIn("end:missing_required_tenors:3", shock_set.audit.iloc[1]["failure_reason"])

    def test_as_of_date_prevents_lookahead(self) -> None:
        shock_set = build_historical_curve_shocks(
            curve_history(), required_tenors=[1.0, 3.0, 7.0], as_of_date="2026-09-11"
        )

        self.assertEqual(shock_set.audit["shock_end_date"].max(), "2026-09-11")
        self.assertNotIn("2026-09-14", shock_set.audit["shock_end_date"].tolist())

    def test_full_repricing_preserves_loss_identity_and_contributions(self) -> None:
        shock_set = build_historical_curve_shocks(
            curve_history(), required_tenors=[1.0, 3.0, 7.0], as_of_date="2026-09-14"
        )
        results = revalue_historical_scenarios(
            base_curve=self.base_curve, portfolio=self.portfolio, shock_set=shock_set
        )
        successes = results.loc[results["status"] == "success"]
        contribution_columns = [column for column in results if column.startswith("position_loss__")]

        np.testing.assert_allclose(successes["loss"], -successes["pnl"], atol=1e-12)
        np.testing.assert_allclose(
            successes[contribution_columns].sum(axis=1), successes["loss"], atol=1e-8
        )
        self.assertGreater(successes.iloc[0]["loss"], 0.0)

    def test_shock_tenors_must_match_base_curve(self) -> None:
        shock_set = build_historical_curve_shocks(
            curve_history(), required_tenors=[1.0, 3.0], as_of_date="2026-09-09"
        )
        results = revalue_historical_scenarios(
            base_curve=self.base_curve, portfolio=self.portfolio, shock_set=shock_set
        )

        self.assertEqual(results.iloc[0]["status"], "valuation_error")
        self.assertIn("do not match", results.iloc[0]["failure_reason"])


if __name__ == "__main__":
    unittest.main()
