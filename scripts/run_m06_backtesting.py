#!/usr/bin/env python3
"""Run M06 rolling historical VaR backtests and ES tail diagnostics."""

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
from bond_risk.risk import (
    exact_zero_coupon_portfolio_losses,
    run_rolling_historical_backtest,
    summarize_es_diagnostics,
    summarize_var_backtests,
)
from bond_risk.scenarios import build_historical_curve_shocks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Root directory for reproducible data and backtest artifacts",
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
    risk_configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "risk.yaml").read_text(encoding="utf-8")
    )["historical_simulation"]
    backtest_configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "backtesting.yaml").read_text(encoding="utf-8")
    )["backtesting"]

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
    historical_shocks = build_historical_curve_shocks(
        curve_data,
        required_tenors=required_tenors,
        as_of_date=valuation_date,
    )

    specifications = portfolio_configuration["positions"]
    maturities = [float(specification["maturity_years"]) for specification in specifications]
    weights = [float(specification["target_weight"]) for specification in specifications]
    total_market_value = float(portfolio_configuration["initial_market_value"])
    run = run_rolling_historical_backtest(
        shock_set=historical_shocks,
        maturity_years=maturities,
        target_weights=weights,
        total_market_value=total_market_value,
        windows=backtest_configuration["estimation_windows"],
        var_confidence_levels=backtest_configuration["var_confidence_levels"],
        es_confidence_levels=backtest_configuration["es_confidence_levels"],
    )
    significance_level = float(backtest_configuration["significance_level"])
    var_summary = summarize_var_backtests(
        run.forecasts, significance_level=significance_level
    )
    es_summary = summarize_es_diagnostics(run.forecasts)

    shock_date_by_id = {
        shock.scenario_id: pd.Timestamp(shock.end_date)
        for shock in historical_shocks.shocks
    }
    sample_end_dates = run.forecasts["sample_end_scenario_id"].map(shock_date_by_id)
    forecast_dates = pd.to_datetime(run.forecasts["forecast_date"])
    no_lookahead = bool((sample_end_dates <= forecast_dates).all())

    latest_shock = max(historical_shocks.shocks, key=lambda shock: shock.end_date)
    latest_curve_before = ZeroCurve.from_long_frame(
        curve_data, observation_date=latest_shock.start_date
    )
    latest_portfolio = build_target_weight_portfolio(
        portfolio_id=portfolio_configuration["portfolio_id"],
        curve=latest_curve_before,
        total_market_value=total_market_value,
        instrument_specs=specifications,
    )
    latest_shocked_curve = ZeroCurve(
        latest_curve_before.observation_date,
        latest_curve_before.tenors_years,
        latest_curve_before.zero_rates_cc + latest_shock.zero_rate_changes_cc,
    )
    maturity_indices = [
        int(np.flatnonzero(np.isclose(latest_shock.tenors_years, maturity))[0])
        for maturity in maturities
    ]
    analytic_latest_loss = exact_zero_coupon_portfolio_losses(
        latest_shock.zero_rate_changes_cc[maturity_indices],
        maturity_years=maturities,
        target_weights=weights,
        total_market_value=total_market_value,
    )[0]
    explicit_latest_loss = latest_portfolio.loss(
        latest_curve_before, latest_shocked_curve
    )

    successful_audit = run.audit.loc[run.audit["status"] == "success"]
    expected_groups = len(backtest_configuration["estimation_windows"])
    expected_var_groups = expected_groups * len(
        backtest_configuration["var_confidence_levels"]
    )
    expected_es_groups = expected_groups * len(
        backtest_configuration["es_confidence_levels"]
    )
    checks = {
        "backtest_forecasts_are_nonempty": not run.forecasts.empty,
        "all_requested_windows_have_successful_forecasts": set(
            successful_audit["window_size"].astype(int)
        )
        == set(int(value) for value in backtest_configuration["estimation_windows"]),
        "no_forecast_lookahead": no_lookahead,
        "realized_loss_matches_explicit_full_repricing": bool(
            np.isclose(analytic_latest_loss, explicit_latest_loss, atol=1e-8)
        ),
        "var_summary_has_every_requested_group": len(var_summary)
        == expected_var_groups,
        "es_summary_has_every_requested_group": len(es_summary) == expected_es_groups,
        "coverage_p_values_are_valid": bool(
            var_summary[
                [
                    "kupiec_p_value",
                    "independence_p_value",
                    "conditional_coverage_p_value",
                ]
            ]
            .apply(lambda column: column.between(0.0, 1.0).all())
            .all()
        ),
        "exception_transitions_reconcile": bool(
            (
                var_summary[
                    [
                        "independence_n00",
                        "independence_n01",
                        "independence_n10",
                        "independence_n11",
                    ]
                ].sum(axis=1)
                == var_summary["independence_transition_count"]
            ).all()
        ),
        "es_forecasts_are_not_below_same_level_var": bool(
            (
                run.forecasts.loc[run.forecasts["measure"] == "ES", "forecast_value"]
                >= run.forecasts.loc[
                    run.forecasts["measure"] == "ES", "tail_var_value"
                ]
            ).all()
        ),
        "es_tail_diagnostics_have_observations": bool(
            (es_summary["tail_observation_count"] > 0).all()
        ),
        "failed_and_insufficient_forecasts_remain_explicit": bool(
            run.audit["status"].isin(
                ["success", "missing_realized_input", "insufficient_history"]
            ).all()
            and (run.audit["status"] != "success").any()
        ),
    }

    processed_directory = args.output_root / "processed"
    audit_directory = args.output_root / "audit"
    processed_directory.mkdir(parents=True, exist_ok=True)
    audit_directory.mkdir(parents=True, exist_ok=True)
    label = valuation_date.date().isoformat()
    forecasts_path = processed_directory / f"m06_backtest_forecasts_{label}.csv.gz"
    audit_path = processed_directory / f"m06_backtest_audit_{label}.csv.gz"
    var_summary_path = processed_directory / f"m06_var_backtest_summary_{label}.csv.gz"
    es_summary_path = processed_directory / f"m06_es_diagnostics_{label}.csv.gz"
    report_path = audit_directory / f"m06_backtesting_{label}.json"
    run.forecasts.to_csv(forecasts_path, index=False, compression="gzip")
    run.audit.to_csv(audit_path, index=False, compression="gzip")
    var_summary.to_csv(var_summary_path, index=False, compression="gzip")
    es_summary.to_csv(es_summary_path, index=False, compression="gzip")

    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "configuration": backtest_configuration,
        "portfolio": {
            "portfolio_id": portfolio_configuration["portfolio_id"],
            "target_market_value": total_market_value,
            "valuation_date": label,
            "rolling_portfolio_rule": backtest_configuration["portfolio_rule"],
        },
        "forecast_audit": {
            "row_count": len(run.audit),
            "status_counts": {
                str(status): int(count)
                for status, count in run.audit["status"].value_counts().items()
            },
        },
        "var_backtests": json.loads(var_summary.to_json(orient="records")),
        "es_diagnostics": json.loads(es_summary.to_json(orient="records")),
        "interpretation": {
            "coverage_rejection_is_model_evidence_not_pipeline_failure": True,
            "es_diagnostics_are_separate_from_var_coverage": True,
        },
        "artifacts": {
            "audit_path": str(audit_path),
            "es_summary_path": str(es_summary_path),
            "forecasts_path": str(forecasts_path),
            "var_summary_path": str(var_summary_path),
        },
    }
    atomic_write_json(report_path, report)
    report["artifacts"]["report_path"] = str(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
