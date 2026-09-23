"""Tests for rolling historical VaR and ES backtesting."""

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
from bond_risk.risk import (
    christoffersen_independence,
    exact_zero_coupon_portfolio_losses,
    kupiec_unconditional_coverage,
    run_rolling_historical_backtest,
    summarize_es_diagnostics,
    summarize_var_backtests,
)
from bond_risk.scenarios import HistoricalCurveShock, HistoricalShockSet


class BacktestingTests(unittest.TestCase):
    def test_exact_loss_formula_matches_portfolio_full_repricing(self) -> None:
        curve = ZeroCurve(
            date(2026, 9, 18),
            np.array([1.0, 3.0, 7.0, 15.0]),
            np.array([0.02, 0.03, 0.04, 0.05]),
        )
        specifications = [
            {"instrument_id": "Z3", "maturity_years": 3.0, "target_weight": 0.4},
            {"instrument_id": "Z7", "maturity_years": 7.0, "target_weight": 0.6},
        ]
        portfolio = build_target_weight_portfolio(
            portfolio_id="backtest",
            curve=curve,
            total_market_value=1_000_000.0,
            instrument_specs=specifications,
        )
        full_shock = np.array([0.0002, 0.0010, -0.0005, 0.0003])
        shocked_curve = ZeroCurve(
            curve.observation_date,
            curve.tenors_years,
            curve.zero_rates_cc + full_shock,
        )
        exact_loss = exact_zero_coupon_portfolio_losses(
            full_shock[[1, 2]],
            maturity_years=[3.0, 7.0],
            target_weights=[0.4, 0.6],
            total_market_value=1_000_000.0,
        )[0]

        self.assertAlmostEqual(exact_loss, portfolio.loss(curve, shocked_curve), places=8)

    def test_rolling_forecast_uses_only_shocks_available_before_outcome(self) -> None:
        start = date(2026, 1, 1)
        tenors = np.array([1.0, 3.0, 7.0])
        shocks = []
        audit_rows = []
        for index in range(8):
            scenario_id = f"HIST_{index + 1}"
            shocks.append(
                HistoricalCurveShock(
                    scenario_id=scenario_id,
                    start_date=start + timedelta(days=index),
                    end_date=start + timedelta(days=index + 1),
                    tenors_years=tenors,
                    zero_rate_changes_cc=np.array([1.0, 2.0, 3.0]) * (index + 1) * 1e-4,
                )
            )
            audit_rows.append(
                {
                    "scenario_id": scenario_id,
                    "scenario_type": "historical",
                    "horizon_days": 1,
                    "shock_start_date": (start + timedelta(days=index)).isoformat(),
                    "shock_end_date": (start + timedelta(days=index + 1)).isoformat(),
                    "status": "success",
                    "failure_reason": None,
                }
            )
        audit_rows.insert(
            3,
            {
                "scenario_id": "FAILED",
                "scenario_type": "historical",
                "horizon_days": 1,
                "shock_start_date": (start + timedelta(days=20)).isoformat(),
                "shock_end_date": (start + timedelta(days=21)).isoformat(),
                "status": "missing_input",
                "failure_reason": "missing curve",
            },
        )
        run = run_rolling_historical_backtest(
            shock_set=HistoricalShockSet(tuple(shocks), pd.DataFrame(audit_rows)),
            maturity_years=[3.0, 7.0],
            target_weights=[0.5, 0.5],
            total_market_value=1_000_000.0,
            windows=[3],
            var_confidence_levels=[0.95],
            es_confidence_levels=[0.975],
        )

        first_forecast = run.forecasts.sort_values("realization_date").iloc[0]
        self.assertEqual(first_forecast["scenario_id"], "HIST_4")
        self.assertEqual(first_forecast["sample_end_scenario_id"], "HIST_3")
        failed = run.audit.loc[run.audit["scenario_id"] == "FAILED"].iloc[0]
        self.assertEqual(failed["status"], "missing_realized_input")
        self.assertGreater(
            int((run.audit["status"] == "insufficient_history").sum()), 0
        )

    def test_coverage_statistics_and_es_diagnostics(self) -> None:
        exceptions = [False] * 95 + [True] * 5
        kupiec = kupiec_unconditional_coverage(exceptions, confidence_level=0.95)
        independence = christoffersen_independence(exceptions)

        self.assertEqual(kupiec["exception_count"], 5)
        self.assertAlmostEqual(kupiec["exception_rate"], 0.05)
        self.assertGreater(kupiec["p_value"], 0.05)
        self.assertEqual(independence["n11"], 4)

        masked = christoffersen_independence(
            [False, True, True], contiguous_transitions=[True, False]
        )
        self.assertEqual(masked["transition_count"], 1)
        self.assertEqual(masked["n01"], 1)
        self.assertEqual(masked["n11"], 0)

        dates = pd.date_range("2026-01-01", periods=6, freq="D").date.astype(str)
        forecasts = pd.DataFrame(
            {
                "window_size": [3] * 12,
                "measure": ["VaR"] * 6 + ["ES"] * 6,
                "confidence_level": [0.95] * 6 + [0.975] * 6,
                "realization_date": list(dates) * 2,
                "forecast_date": list(
                    (pd.to_datetime(dates) - pd.Timedelta(days=1)).date.astype(str)
                )
                * 2,
                "exception": [False, False, True, False, False, True] + [False] * 6,
                "tail_observation": [False] * 6 + [False, False, True, False, False, True],
                "es_breach": [False] * 6 + [False, False, True, False, False, False],
                "realized_loss": [1, 2, 8, 1, 2, 6] * 2,
                "forecast_value": [5] * 6 + [7, 7, 7, 7, 7, 7],
            }
        )
        var_summary = summarize_var_backtests(forecasts)
        es_summary = summarize_es_diagnostics(forecasts)

        self.assertEqual(var_summary.iloc[0]["kupiec_exception_count"], 2)
        self.assertEqual(var_summary.iloc[0]["maximum_consecutive_exceptions"], 1)
        self.assertEqual(es_summary.iloc[0]["tail_observation_count"], 2)
        self.assertEqual(es_summary.iloc[0]["es_breach_count"], 1)
        self.assertAlmostEqual(es_summary.iloc[0]["mean_realized_tail_loss"], 7.0)


if __name__ == "__main__":
    unittest.main()
