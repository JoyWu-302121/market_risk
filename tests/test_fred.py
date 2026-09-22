"""Tests for FRED observation parsing and audit rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.data.fred import audit_fred_series, parse_fred_observations


class FredParsingTests(unittest.TestCase):
    def test_parse_converts_percent_and_retains_realtime_fields(self) -> None:
        payload = {
            "observations": [
                {
                    "date": "2026-09-17",
                    "value": "4.25",
                    "realtime_start": "2026-09-18",
                    "realtime_end": "2026-09-18",
                },
                {
                    "date": "2026-09-18",
                    "value": ".",
                    "realtime_start": "2026-09-19",
                    "realtime_end": "2026-09-19",
                },
            ]
        }

        observations = parse_fred_observations(payload, series_id="DFF")

        self.assertAlmostEqual(observations.loc[0, "value_decimal"], 0.0425)
        self.assertEqual(observations.loc[0, "realtime_start"], "2026-09-18")
        self.assertFalse(bool(observations.loc[1, "is_observed"]))
        self.assertTrue(pd.isna(observations.loc[1, "value_decimal"]))

    def test_audit_reports_missing_value_as_warning(self) -> None:
        payload = {
            "observations": [
                {"date": "2026-09-17", "value": "4.25"},
                {"date": "2026-09-18", "value": "."},
            ]
        }
        observations = parse_fred_observations(payload, series_id="DFF")
        audit = audit_fred_series(observations, as_of="2026-09-20")

        self.assertEqual(audit["status"], "WARN")
        self.assertEqual(audit["missing_value_count"], 1)
        self.assertEqual(audit["failures"], [])

    def test_parse_rejects_invalid_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "observations list"):
            parse_fred_observations({}, series_id="DFF")


if __name__ == "__main__":
    unittest.main()
