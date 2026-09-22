"""Tests for GSW curve parsing and audit rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.data.gsw import audit_gsw_curve, parse_gsw_csv


SAMPLE_GSW = """Research product notice

Series,Compounding Convention,Mnemonic(s)
Zero-coupon yield,Continuously Compounded,SVENYXX

Date,SVENY01,SVENY03,SVENY07,SVENY15,SVENPY03,TAU2
2005-01-03,2.00,3.00,4.00,5.00,3.10,1.00
2005-01-04,2.10,3.10,NA,5.10,3.20,1.00
2005-01-05,2.20,3.20,4.20,5.20,3.30,1.00
"""


class GswParsingTests(unittest.TestCase):
    def test_parse_selects_only_zero_yields_and_converts_percent(self) -> None:
        curve = parse_gsw_csv(SAMPLE_GSW, retrieved_at_utc="2026-09-21T00:00:00+00:00")

        self.assertEqual(set(curve["tenor_years"]), {1, 3, 7, 15})
        self.assertNotIn("SVENPY03", set(curve["source_series"]))
        value = curve.loc[
            (curve["observation_date"] == pd.Timestamp("2005-01-03"))
            & (curve["tenor_years"] == 3),
            "zero_yield_cc",
        ].item()
        self.assertAlmostEqual(value, 0.03)

    def test_parse_preserves_missing_curve_node(self) -> None:
        curve = parse_gsw_csv(SAMPLE_GSW)
        missing = curve.loc[
            (curve["observation_date"] == pd.Timestamp("2005-01-04"))
            & (curve["tenor_years"] == 7)
        ].iloc[0]

        self.assertFalse(bool(missing["is_observed"]))
        self.assertEqual(missing["quality_flag"], "missing")
        self.assertTrue(pd.isna(missing["zero_yield_cc"]))

    def test_audit_warns_for_missing_history_but_accepts_latest_curve(self) -> None:
        curve = parse_gsw_csv(SAMPLE_GSW)
        audit = audit_gsw_curve(
            curve,
            required_tenors=(3, 7, 15),
            analysis_start="2005-01-01",
            as_of="2005-01-06",
        )

        self.assertEqual(audit["status"], "WARN")
        self.assertEqual(audit["failures"], [])
        self.assertTrue(audit["required_tenor_coverage"]["7"]["latest_available"])

    def test_audit_fails_duplicate_date_tenor_rows(self) -> None:
        curve = parse_gsw_csv(SAMPLE_GSW)
        duplicated = pd.concat([curve, curve.iloc[[0]]], ignore_index=True)
        audit = audit_gsw_curve(duplicated, as_of="2005-01-06")

        self.assertEqual(audit["status"], "FAIL")
        self.assertEqual(audit["duplicate_date_tenor_rows"], 1)

    def test_audit_counts_empty_calendar_date_without_tenor_warning(self) -> None:
        sample = """Date,SVENY03,SVENY07,SVENY15
2005-01-03,3.00,4.00,5.00
2005-01-04,NA,NA,NA
2005-01-05,3.20,4.20,5.20
"""
        curve = parse_gsw_csv(sample)
        audit = audit_gsw_curve(curve, as_of="2005-01-06")

        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["empty_curve_date_count"], 1)
        self.assertEqual(audit["required_tenor_coverage"]["3"]["observed_ratio"], 1.0)

    def test_parse_rejects_missing_table_header(self) -> None:
        with self.assertRaisesRegex(ValueError, "Date header"):
            parse_gsw_csv("not,a,gsw,table\n")


if __name__ == "__main__":
    unittest.main()
