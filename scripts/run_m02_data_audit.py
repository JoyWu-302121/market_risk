#!/usr/bin/env python3
"""Run the M02 public-data ingestion and audit pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from bond_risk.data.pipeline import run_fred_pipeline, run_gsw_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Root directory for raw, processed, and audit outputs",
    )
    parser.add_argument("--analysis-start", default="2005-01-01")
    parser.add_argument(
        "--include-fred",
        action="store_true",
        help="Download DFF and DGS3MO using the FRED_API_KEY environment variable",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "data_sources.yaml").read_text(encoding="utf-8")
    )
    gsw_configuration = configuration["gsw"]
    report: dict[str, object] = {
        "gsw": run_gsw_pipeline(
            args.output_root,
            analysis_start=args.analysis_start,
            required_tenors=gsw_configuration["required_tenors_years"],
            source_url=gsw_configuration["url"],
            stale_after_days=gsw_configuration["stale_after_calendar_days"],
        )
    }

    if args.include_fred:
        api_key = os.environ.get("FRED_API_KEY", "")
        if not api_key:
            raise SystemExit("FRED_API_KEY is required when --include-fred is used")
        report["fred"] = {
            series_id: run_fred_pipeline(
                args.output_root,
                series_id=series_id,
                api_key=api_key,
                observation_start=args.analysis_start,
            )
            for series_id in ("DFF", "DGS3MO")
        }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["gsw"]["audit"]["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
