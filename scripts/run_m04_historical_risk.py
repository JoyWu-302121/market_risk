#!/usr/bin/env python3
"""Run M04 historical full-revaluation VaR and Expected Shortfall."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from bond_risk.curves import ZeroCurve, latest_complete_curve_date
from bond_risk.data.pipeline import run_gsw_pipeline
from bond_risk.data.storage import atomic_write_json
from bond_risk.portfolio import build_target_weight_portfolio
from bond_risk.risk import empirical_var, estimate_historical_risk
from bond_risk.scenarios import build_historical_curve_shocks, revalue_historical_scenarios


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Root directory for reproducible data, scenario, and risk artifacts",
    )
    return parser.parse_args()


def _metric_contributions_sum(estimates: pd.DataFrame) -> bool:
    for row in estimates.itertuples(index=False):
        contributions = json.loads(row.position_contributions)
        if not np.isclose(sum(contributions.values()), row.value, atol=1e-8):
            return False
    return True


def _es_dominates_same_level_var(
    estimates: pd.DataFrame,
    scenario_results: pd.DataFrame,
) -> bool:
    successful = scenario_results.loc[scenario_results["status"] == "success"].copy()
    successful["shock_end_date"] = pd.to_datetime(successful["shock_end_date"])
    for row in estimates.loc[estimates["measure"] == "ES"].itertuples(index=False):
        sample = successful.loc[
            (successful["shock_end_date"] >= pd.Timestamp(row.sample_start_date))
            & (successful["shock_end_date"] <= pd.Timestamp(row.sample_end_date))
        ].sort_values("shock_end_date").tail(row.window_size)
        same_level_var = empirical_var(sample["loss"], row.confidence_level)
        if row.value + 1e-8 < same_level_var:
            return False
    return True


def main() -> int:
    args = parse_args()
    data_configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "data_sources.yaml").read_text(encoding="utf-8")
    )["gsw"]
    portfolio_configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "portfolio.yaml").read_text(encoding="utf-8")
    )
    risk_configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "risk.yaml").read_text(encoding="utf-8")
    )["historical_simulation"]

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
    curve_data = curve_data.loc[
        curve_data["observation_date"] >= pd.Timestamp(data_configuration["analysis_start"])
    ].copy()
    required_tenors = [float(value) for value in risk_configuration["required_curve_tenors_years"]]
    valuation_date = latest_complete_curve_date(curve_data, required_tenors=required_tenors)
    base_curve = ZeroCurve.from_long_frame(curve_data, observation_date=valuation_date)
    if not np.array_equal(base_curve.tenors_years, np.asarray(required_tenors)):
        raise SystemExit("Latest curve nodes do not exactly match the configured M04 tenors")

    portfolio = build_target_weight_portfolio(
        portfolio_id=portfolio_configuration["portfolio_id"],
        curve=base_curve,
        total_market_value=float(portfolio_configuration["initial_market_value"]),
        instrument_specs=portfolio_configuration["positions"],
    )
    shock_set = build_historical_curve_shocks(
        curve_data,
        required_tenors=required_tenors,
        as_of_date=valuation_date,
    )
    scenario_results = revalue_historical_scenarios(
        base_curve=base_curve,
        portfolio=portfolio,
        shock_set=shock_set,
    )
    estimates = estimate_historical_risk(
        scenario_results,
        valuation_date=valuation_date.date().isoformat(),
        windows=risk_configuration["estimation_windows"],
        var_confidence_levels=risk_configuration["var_confidence_levels"],
        es_confidence_levels=risk_configuration["es_confidence_levels"],
        horizon_days=int(risk_configuration["horizon_days"]),
    )

    successful = scenario_results.loc[scenario_results["status"] == "success"]
    failed = scenario_results.loc[scenario_results["status"] != "success"]
    contribution_columns = [
        column for column in scenario_results if column.startswith("position_loss__")
    ]
    contribution_residual = (
        successful[contribution_columns].sum(axis=1) - successful["loss"]
    ).abs()
    requested_windows = sorted(int(value) for value in risk_configuration["estimation_windows"])
    checks = {
        "base_curve_has_all_required_nodes": bool(
            np.array_equal(base_curve.tenors_years, np.asarray(required_tenors))
        ),
        "enough_successful_scenarios_for_largest_window": len(successful) >= max(requested_windows),
        "es_not_below_same_confidence_var": _es_dominates_same_level_var(
            estimates, scenario_results
        ),
        "frozen_position_loss_contributions_sum": bool(
            contribution_residual.max() <= 1e-8
        ),
        "metric_position_contributions_sum": _metric_contributions_sum(estimates),
        "no_scenario_lookahead": bool(
            pd.to_datetime(scenario_results["shock_end_date"]).max() <= valuation_date
        ),
        "requested_windows_have_exact_sample_sizes": bool(
            set(estimates["sample_size"].astype(int)) == set(requested_windows)
        ),
    }

    output_directory = args.output_root / "processed"
    audit_directory = args.output_root / "audit"
    output_directory.mkdir(parents=True, exist_ok=True)
    audit_directory.mkdir(parents=True, exist_ok=True)
    date_label = valuation_date.date().isoformat()
    scenario_path = output_directory / f"m04_historical_scenarios_{date_label}.csv.gz"
    estimates_path = output_directory / f"m04_historical_risk_{date_label}.csv.gz"
    report_path = audit_directory / f"m04_historical_risk_{date_label}.json"
    scenario_results.to_csv(scenario_path, index=False, compression="gzip")
    estimates.to_csv(estimates_path, index=False, compression="gzip")

    maximum_loss_row = successful.loc[successful["loss"].idxmax()]
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "configuration": {
            "curve_shock_method": risk_configuration["curve_shock_method"],
            "empirical_es_convention": risk_configuration["empirical_es_convention"],
            "empirical_var_convention": risk_configuration["empirical_var_convention"],
            "es_confidence_levels": risk_configuration["es_confidence_levels"],
            "horizon_days": risk_configuration["horizon_days"],
            "requested_windows": requested_windows,
            "valuation_method": risk_configuration["valuation_method"],
            "var_confidence_levels": risk_configuration["var_confidence_levels"],
        },
        "data": {
            "failed_scenario_count": len(failed),
            "failure_status_counts": {
                str(status): int(count)
                for status, count in failed["status"].value_counts().items()
            },
            "first_successful_shock_date": successful["shock_end_date"].min(),
            "last_successful_shock_date": successful["shock_end_date"].max(),
            "source_audit_status": ingestion["audit"]["status"],
            "successful_scenario_count": len(successful),
            "total_candidate_scenario_count": len(scenario_results),
        },
        "maximum_loss": {
            "loss": float(maximum_loss_row["loss"]),
            "scenario_id": maximum_loss_row["scenario_id"],
            "shock_end_date": maximum_loss_row["shock_end_date"],
        },
        "portfolio": {
            "base_market_value": portfolio.value(base_curve),
            "portfolio_id": portfolio.portfolio_id,
            "valuation_date": date_label,
        },
        "risk_estimates": json.loads(estimates.to_json(orient="records")),
        "artifacts": {
            "estimates_path": str(estimates_path),
            "scenario_audit_path": str(scenario_path),
        },
    }
    atomic_write_json(report_path, report)
    report["artifacts"]["report_path"] = str(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
