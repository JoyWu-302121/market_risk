#!/usr/bin/env python3
"""Run M05 hypothetical, historical, PCA, and reverse stress testing."""

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
from bond_risk.risk.reverse_stress import search_reverse_stress
from bond_risk.scenarios import (
    CurveStressScenario,
    build_historical_curve_shocks,
    build_hypothetical_scenarios,
    build_pca_stress_scenarios,
    evaluate_stress_scenarios,
    fit_pca_stress_model,
    select_historical_extreme_scenarios,
    stress_direction_templates,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Root directory for reproducible data and stress-test artifacts",
    )
    return parser.parse_args()


def _json_contributions_sum(frame: pd.DataFrame, column: str, target: str) -> bool:
    for row in frame.itertuples(index=False):
        values = json.loads(getattr(row, column))
        if not np.isclose(sum(values.values()), getattr(row, target), atol=1e-8):
            return False
    return True


def _historical_dates_do_not_look_ahead(
    frame: pd.DataFrame, valuation_date: pd.Timestamp
) -> bool:
    historical = frame.loc[frame["scenario_family"].str.startswith("historical")]
    for metadata_text in historical["metadata"]:
        metadata = json.loads(metadata_text)
        if pd.Timestamp(metadata["shock_end_date"]) > valuation_date:
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
    stress_configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "stress_scenarios.yaml").read_text(encoding="utf-8")
    )["stress_testing"]

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
    portfolio = build_target_weight_portfolio(
        portfolio_id=portfolio_configuration["portfolio_id"],
        curve=base_curve,
        total_market_value=float(portfolio_configuration["initial_market_value"]),
        instrument_specs=portfolio_configuration["positions"],
    )
    bump = float(stress_configuration["key_rate_bump_decimal"])

    historical_shocks = build_historical_curve_shocks(
        curve_data,
        required_tenors=required_tenors,
        as_of_date=valuation_date,
    )
    hypothetical_configuration = stress_configuration["hypothetical"]
    hypothetical = build_hypothetical_scenarios(
        tenors_years=base_curve.tenors_years,
        parallel_amplitudes_bps=hypothetical_configuration["parallel_amplitudes_bps"],
        slope_pivot_years=float(hypothetical_configuration["slope_pivot_years"]),
        slope_amplitudes_bps=hypothetical_configuration["slope_amplitudes_bps"],
        butterfly_center_years=float(
            hypothetical_configuration["butterfly_center_years"]
        ),
        butterfly_amplitudes_bps=hypothetical_configuration[
            "butterfly_amplitudes_bps"
        ],
    )

    historical_configuration = stress_configuration["historical"]
    historical_events = select_historical_extreme_scenarios(
        one_day_shocks=historical_shocks.shocks,
        curve_frame=curve_data,
        base_curve=base_curve,
        portfolio=portfolio,
        top_one_day_scenarios=int(historical_configuration["top_one_day_scenarios"]),
        multi_day_horizons=historical_configuration["multi_day_horizons"],
        top_scenarios_per_horizon=int(
            historical_configuration["top_scenarios_per_horizon"]
        ),
        key_rate_bump_decimal=bump,
    )

    pca_configuration = stress_configuration["pca"]
    pca_model = fit_pca_stress_model(
        historical_shocks.shocks,
        estimation_window=int(pca_configuration["estimation_window"]),
        factor_count=int(pca_configuration["factor_count"]),
    )
    pca_scenarios = build_pca_stress_scenarios(
        pca_model,
        standard_deviation_multiples=pca_configuration["standard_deviation_multiples"],
    )

    standard_scenarios = [*hypothetical, *historical_events.scenarios, *pca_scenarios]
    standard_results = evaluate_stress_scenarios(
        base_curve=base_curve,
        portfolio=portfolio,
        scenarios=standard_scenarios,
        key_rate_bump_decimal=bump,
    )

    directions = stress_direction_templates(
        base_curve.tenors_years,
        slope_pivot_years=float(hypothetical_configuration["slope_pivot_years"]),
        butterfly_center_years=float(
            hypothetical_configuration["butterfly_center_years"]
        ),
    )
    reverse_configuration = stress_configuration["reverse_stress"]
    selected_directions = {
        family: directions[family]
        for family in reverse_configuration["direction_families"]
    }
    reverse_search = search_reverse_stress(
        base_curve=base_curve,
        portfolio=portfolio,
        directions=selected_directions,
        loss_thresholds_usd=reverse_configuration["loss_thresholds_usd"],
        maximum_amplitude_bps=float(reverse_configuration["maximum_amplitude_bps"]),
        grid_step_bps=float(reverse_configuration["grid_step_bps"]),
        tolerance_bps=float(reverse_configuration["tolerance_bps"]),
    )
    reverse_valuations = evaluate_stress_scenarios(
        base_curve=base_curve,
        portfolio=portfolio,
        scenarios=reverse_search.breach_scenarios,
        key_rate_bump_decimal=bump,
    )
    reverse_results = reverse_search.results.merge(
        reverse_valuations,
        on="scenario_id",
        how="left",
        suffixes=("_search", "_valuation"),
    )

    zero_scenario = CurveStressScenario(
        scenario_id="ACCEPTANCE_ZERO_SHOCK",
        scenario_family="acceptance",
        description="Zero-shock valuation invariant",
        tenors_years=base_curve.tenors_years,
        shock_decimal=np.zeros_like(base_curve.tenors_years),
    )
    zero_result = evaluate_stress_scenarios(
        base_curve=base_curve,
        portfolio=portfolio,
        scenarios=[zero_scenario],
        key_rate_bump_decimal=bump,
    ).iloc[0]

    successful_standard = standard_results.loc[standard_results["status"] == "success"]
    parallel_up = successful_standard.loc[
        successful_standard["scenario_id"].str.contains("HYP_PARALLEL_UP")
    ]
    parallel_down = successful_standard.loc[
        successful_standard["scenario_id"].str.contains("HYP_PARALLEL_DOWN")
    ]
    successful_reverse_search = reverse_search.results.loc[
        reverse_search.results["status"] == "success"
    ]
    thresholds = {float(value) for value in reverse_configuration["loss_thresholds_usd"]}
    checks = {
        "zero_shock_loss_is_zero": abs(float(zero_result["loss"])) < 1e-12,
        "all_standard_scenarios_value_successfully": len(successful_standard)
        == len(standard_results),
        "scenario_ids_are_unique": standard_results["scenario_id"].is_unique,
        "parallel_up_losses_are_positive": bool((parallel_up["loss"] > 0).all()),
        "parallel_down_losses_are_negative": bool((parallel_down["loss"] < 0).all()),
        "position_losses_reconcile": _json_contributions_sum(
            successful_standard, "position_loss_contributions", "loss"
        ),
        "linear_key_rate_contributions_reconcile": _json_contributions_sum(
            successful_standard,
            "linear_key_rate_contributions",
            "linear_sensitivity_loss",
        ),
        "full_minus_linear_reconciles": bool(
            np.allclose(
                successful_standard["loss"]
                - successful_standard["linear_sensitivity_loss"],
                successful_standard["full_minus_linear"],
                atol=1e-8,
            )
        ),
        "historical_scenarios_have_no_lookahead": _historical_dates_do_not_look_ahead(
            successful_standard, valuation_date
        ),
        "pca_loadings_are_orthonormal": bool(
            np.allclose(
                pca_model.loadings @ pca_model.loadings.T,
                np.eye(len(pca_model.loadings)),
                atol=1e-12,
            )
        ),
        "pca_residual_variance_is_retained": pca_model.residual_variance_ratio > 0,
        "reverse_stress_reaches_every_threshold": set(
            successful_reverse_search["loss_threshold_usd"]
        )
        == thresholds,
        "reverse_stress_boundary_is_bracketed": bool(
            (
                successful_reverse_search["achieved_loss"]
                >= successful_reverse_search["loss_threshold_usd"]
            ).all()
            and (
                successful_reverse_search["lower_bound_loss"]
                < successful_reverse_search["loss_threshold_usd"]
            ).all()
        ),
        "reverse_stress_valuations_succeed": bool(
            (reverse_valuations["status"] == "success").all()
        ),
    }

    processed_directory = args.output_root / "processed"
    audit_directory = args.output_root / "audit"
    processed_directory.mkdir(parents=True, exist_ok=True)
    audit_directory.mkdir(parents=True, exist_ok=True)
    label = valuation_date.date().isoformat()
    stress_path = processed_directory / f"m05_stress_results_{label}.csv.gz"
    historical_audit_path = processed_directory / f"m05_multiday_audit_{label}.csv.gz"
    reverse_path = processed_directory / f"m05_reverse_stress_{label}.csv.gz"
    pca_loadings_path = processed_directory / f"m05_pca_loadings_{label}.csv.gz"
    pca_diagnostics_path = processed_directory / f"m05_pca_diagnostics_{label}.csv.gz"
    report_path = audit_directory / f"m05_stress_testing_{label}.json"
    standard_results.to_csv(stress_path, index=False, compression="gzip")
    historical_events.multi_day_audit.to_csv(
        historical_audit_path, index=False, compression="gzip"
    )
    reverse_results.to_csv(reverse_path, index=False, compression="gzip")
    pca_model.loadings_frame().to_csv(pca_loadings_path, index=False, compression="gzip")
    pca_model.diagnostics_frame().to_csv(
        pca_diagnostics_path, index=False, compression="gzip"
    )

    minimum_reverse = reverse_search.results.loc[
        reverse_search.results["is_minimum_amplitude_for_threshold"]
    ]
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "portfolio": {
            "portfolio_id": portfolio.portfolio_id,
            "base_market_value": portfolio.value(base_curve),
            "valuation_date": label,
        },
        "scenario_counts": {
            "hypothetical": len(hypothetical),
            "historical_selected": len(historical_events.scenarios),
            "pca": len(pca_scenarios),
            "reverse_successful_families": len(reverse_search.breach_scenarios),
            "standard_total": len(standard_results),
        },
        "pca": {
            "sample_start_date": pca_model.sample_start_date.isoformat(),
            "sample_end_date": pca_model.sample_end_date.isoformat(),
            "sample_size": pca_model.sample_size,
            "explained_variance_ratios": pca_model.explained_variance_ratios.tolist(),
            "residual_variance_ratio": pca_model.residual_variance_ratio,
            "diagnostics": json.loads(
                pca_model.diagnostics_frame().to_json(orient="records")
            ),
        },
        "worst_standard_scenarios": json.loads(
            successful_standard.nlargest(10, "loss")[
                [
                    "scenario_id",
                    "scenario_family",
                    "horizon_days",
                    "loss",
                    "linear_sensitivity_loss",
                    "full_minus_linear",
                    "maximum_absolute_shock_bps",
                ]
            ].to_json(orient="records")
        ),
        "minimum_reverse_stresses": json.loads(
            minimum_reverse[
                [
                    "loss_threshold_usd",
                    "direction_family",
                    "amplitude_bps",
                    "achieved_loss",
                ]
            ].to_json(orient="records")
        ),
        "historical_multiday_audit": {
            "candidate_count": len(historical_events.multi_day_audit),
            "status_counts": {
                str(status): int(count)
                for status, count in historical_events.multi_day_audit["status"]
                .value_counts()
                .items()
            },
        },
        "artifacts": {
            "historical_multiday_audit_path": str(historical_audit_path),
            "pca_diagnostics_path": str(pca_diagnostics_path),
            "pca_loadings_path": str(pca_loadings_path),
            "reverse_stress_path": str(reverse_path),
            "stress_results_path": str(stress_path),
        },
    }
    atomic_write_json(report_path, report)
    report["artifacts"]["report_path"] = str(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
