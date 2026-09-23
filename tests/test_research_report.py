"""Tests for M08 research-report consistency checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.reporting import historical_estimates_match, validate_milestone_reports


def accepted_reports() -> dict[str, dict[str, object]]:
    common_portfolio = {
        "portfolio_id": "treasury_zero_core",
        "base_market_value": 10_000_000.0,
        "valuation_date": "2026-09-18",
    }
    return {
        "M03": {
            "status": "PASS",
            "curve": {"observation_date": "2026-09-18"},
            "portfolio": {
                "portfolio_id": "treasury_zero_core",
                "base_market_value": 10_000_000.0,
            },
        },
        "M04": {"status": "PASS", "portfolio": common_portfolio.copy()},
        "M05": {"status": "PASS", "portfolio": common_portfolio.copy()},
        "M06": {
            "status": "PASS",
            "portfolio": {
                "portfolio_id": "treasury_zero_core",
                "target_market_value": 10_000_000.0,
                "valuation_date": "2026-09-18",
            },
        },
        "M07": {
            "status": "PASS",
            "portfolio": {
                "portfolio_id": "treasury_zero_core",
                "target_market_value": 10_000_000.0,
                "valuation_date": "2026-09-18",
            },
        },
    }


class ResearchReportTests(unittest.TestCase):
    def test_common_milestone_contract_passes(self) -> None:
        checks = validate_milestone_reports(accepted_reports())
        self.assertTrue(all(checks.values()))

    def test_date_or_status_mismatch_is_explicit(self) -> None:
        reports = accepted_reports()
        reports["M05"]["portfolio"]["valuation_date"] = "2026-09-17"
        reports["M06"]["status"] = "FAIL"
        checks = validate_milestone_reports(reports)
        self.assertFalse(checks["common_valuation_date"])
        self.assertFalse(checks["all_milestone_reports_pass"])

    def test_historical_estimates_reconcile_across_m04_and_m07(self) -> None:
        m04 = pd.DataFrame(
            {
                "window_size": [500, 750],
                "measure": ["VaR", "ES"],
                "confidence_level": [0.95, 0.99],
                "value": [70_000.0, 120_000.0],
            }
        )
        m07 = m04.assign(method="Historical Simulation")
        self.assertTrue(historical_estimates_match(m04, m07))

    def test_historical_estimate_change_is_rejected(self) -> None:
        m04 = pd.DataFrame(
            {
                "window_size": [750],
                "measure": ["VaR"],
                "confidence_level": [0.99],
                "value": [118_000.0],
            }
        )
        m07 = m04.assign(method="Historical Simulation")
        m07.loc[0, "value"] += 1.0
        self.assertFalse(historical_estimates_match(m04, m07))


if __name__ == "__main__":
    unittest.main()
