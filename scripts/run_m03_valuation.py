#!/usr/bin/env python3
"""Run M02 ingestion followed by M03 curve, portfolio, and DV01 validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from bond_risk.curves import ZeroCurve
from bond_risk.data.pipeline import run_gsw_pipeline
from bond_risk.data.storage import atomic_write_json
from bond_risk.portfolio import build_target_weight_portfolio


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Root directory for reproducible data and valuation artifacts",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "data_sources.yaml").read_text(encoding="utf-8")
    )["gsw"]
    portfolio_configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "portfolio.yaml").read_text(encoding="utf-8")
    )

    ingestion = run_gsw_pipeline(
        args.output_root,
        analysis_start=data_configuration["analysis_start"],
        required_tenors=data_configuration["required_tenors_years"],
        source_url=data_configuration["url"],
        stale_after_days=data_configuration["stale_after_calendar_days"],
    )
    if ingestion["audit"]["status"] == "FAIL":
        raise SystemExit(f"GSW data audit failed: {ingestion['audit']['failures']}")

    curve_data = pd.read_csv(ingestion["processed_path"], parse_dates=["observation_date"])
    curve = ZeroCurve.from_long_frame(curve_data)
    portfolio = build_target_weight_portfolio(
        portfolio_id=portfolio_configuration["portfolio_id"],
        curve=curve,
        total_market_value=float(portfolio_configuration["initial_market_value"]),
        instrument_specs=portfolio_configuration["positions"],
    )

    bump = float(portfolio_configuration["dv01"]["parallel_bump_decimal"])
    tolerance = float(
        portfolio_configuration["dv01"]["maximum_relative_linearization_error"]
    )
    base_value = portfolio.value(curve)
    zero_shock_pnl = portfolio.pnl(curve, curve.parallel_shift(0.0))
    full_dv01 = portfolio.full_revaluation_parallel_dv01(curve, bump)
    linear_dv01 = portfolio.linear_parallel_dv01(curve, bump)
    relative_error = abs(linear_dv01 - full_dv01) / full_dv01
    position_report = portfolio.position_report(curve, bump)

    checks = {
        "base_value_matches_configuration": abs(
            base_value - float(portfolio_configuration["initial_market_value"])
        )
        < 1e-6,
        "dv01_is_positive": full_dv01 > 0,
        "linear_dv01_within_tolerance": relative_error <= tolerance,
        "target_weights_match": bool(
            np_allclose(
                position_report["actual_weight"],
                position_report["target_weight"],
                atol=1e-12,
            )
        ),
        "zero_shock_pnl_is_zero": abs(zero_shock_pnl) < 1e-12,
    }
    report = {
        "checks": checks,
        "curve": {
            "interpolation": "linear_log_discount_factor",
            "maximum_tenor_years": curve.maximum_tenor,
            "minimum_tenor_years": curve.minimum_tenor,
            "node_count": len(curve.tenors_years),
            "observation_date": curve.observation_date.isoformat(),
        },
        "portfolio": {
            "base_market_value": base_value,
            "currency": portfolio_configuration["currency"],
            "full_revaluation_dv01": full_dv01,
            "linear_dv01": linear_dv01,
            "linearization_relative_error": relative_error,
            "portfolio_id": portfolio.portfolio_id,
            "positions": json.loads(position_report.to_json(orient="records")),
            "zero_shock_pnl": zero_shock_pnl,
        },
        "status": "PASS" if all(checks.values()) else "FAIL",
    }

    report_path = (
        args.output_root
        / "audit"
        / f"m03_valuation_{curve.observation_date.isoformat()}.json"
    )
    atomic_write_json(report_path, report)
    report["report_path"] = str(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def np_allclose(left: pd.Series, right: pd.Series, *, atol: float) -> bool:
    """Avoid an additional top-level dependency import in CLI setup."""

    return bool(((left - right).abs() <= atol).all())


if __name__ == "__main__":
    raise SystemExit(main())
