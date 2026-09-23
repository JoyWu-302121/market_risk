"""Tests for extreme historical one-day and multi-day scenario selection."""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.curves import ZeroCurve
from bond_risk.portfolio import build_target_weight_portfolio
from bond_risk.scenarios import HistoricalCurveShock, select_historical_extreme_scenarios


class HistoricalEventTests(unittest.TestCase):
    def test_multiday_windows_do_not_bridge_incomplete_curves(self) -> None:
        start = date(2026, 9, 1)
        tenors = np.array([1.0, 3.0, 7.0])
        rows = []
        curves = []
        for index in range(8):
            rates = np.array([0.02, 0.03, 0.04]) + index * np.array([1, 2, 3]) * 1e-4
            curves.append(rates)
            for tenor, rate in zip(tenors, rates, strict=True):
                observed = not (index == 3 and tenor == 3.0)
                rows.append(
                    {
                        "observation_date": start + timedelta(days=index),
                        "tenor_years": tenor,
                        "zero_yield_cc": rate if observed else np.nan,
                        "is_observed": observed,
                    }
                )
        one_day = [
            HistoricalCurveShock(
                scenario_id=f"H{index}",
                start_date=start + timedelta(days=index),
                end_date=start + timedelta(days=index + 1),
                tenors_years=tenors,
                zero_rate_changes_cc=curves[index + 1] - curves[index],
            )
            for index in range(7)
        ]
        base_curve = ZeroCurve(start + timedelta(days=7), tenors, curves[-1])
        portfolio = build_target_weight_portfolio(
            portfolio_id="history",
            curve=base_curve,
            total_market_value=1_000_000.0,
            instrument_specs=[
                {"instrument_id": "ZERO_7Y", "maturity_years": 7.0, "target_weight": 1.0}
            ],
        )
        selection = select_historical_extreme_scenarios(
            one_day_shocks=one_day,
            curve_frame=pd.DataFrame(rows),
            base_curve=base_curve,
            portfolio=portfolio,
            top_one_day_scenarios=2,
            multi_day_horizons=[2],
            top_scenarios_per_horizon=1,
        )

        self.assertEqual(len(selection.scenarios), 3)
        self.assertGreater(
            int((selection.multi_day_audit["status"] == "missing_input").sum()), 0
        )
        failed = selection.multi_day_audit.loc[
            selection.multi_day_audit["status"] == "missing_input"
        ]
        self.assertTrue(failed["failure_reason"].str.contains("2026-09-04").any())


if __name__ == "__main__":
    unittest.main()
