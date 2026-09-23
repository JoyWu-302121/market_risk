#!/usr/bin/env python3
"""Run M07 historical, parametric-normal, and PCA Monte Carlo risk comparison."""

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
    empirical_risk_with_contributions,
    factor_variance_contributions,
    fit_pca_covariance_model,
    key_rate_dv01,
    parametric_normal_risk,
    simulate_pca_full_repricing,
)
from bond_risk.scenarios import build_historical_curve_shocks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Root directory for reproducible data and M07 artifacts",
    )
    return parser.parse_args()


def _position_losses(
    shock_matrix: np.ndarray,
    *,
    maturities: np.ndarray,
    weights: np.ndarray,
    total_market_value: float,
) -> np.ndarray:
    return total_market_value * weights * (1.0 - np.exp(-shock_matrix * maturities))


def _parametric_position_contributions(
    risk: pd.DataFrame,
    *,
    position_sensitivities: np.ndarray,
    covariance: np.ndarray,
    position_ids: list[str],
) -> pd.DataFrame:
    result = risk.copy()
    total_sensitivity = position_sensitivities.sum(axis=0)
    sigma = float(np.sqrt(total_sensitivity @ covariance @ total_sensitivity))
    marginal_covariance = position_sensitivities @ covariance @ total_sensitivity
    contribution_per_sigma = marginal_covariance / sigma
    encoded = []
    for row in result.itertuples(index=False):
        multiplier = float(row.value) / sigma
        values = contribution_per_sigma * multiplier
        encoded.append(json.dumps(dict(zip(position_ids, values, strict=True)), sort_keys=True))
    result["position_contributions"] = encoded
    return result


def _contributions_reconcile(frame: pd.DataFrame) -> bool:
    return all(
        np.isclose(
            sum(json.loads(row.position_contributions).values()),
            row.value,
            atol=1e-7,
        )
        for row in frame.itertuples(index=False)
    )


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
    configuration = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "model_comparison.yaml").read_text(encoding="utf-8")
    )["model_comparison"]

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
    required_tenors = np.asarray(
        risk_configuration["required_curve_tenors_years"], dtype=float
    )
    valuation_date = latest_complete_curve_date(
        curve_data, required_tenors=required_tenors
    )
    base_curve = ZeroCurve.from_long_frame(curve_data, observation_date=valuation_date)
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
    ordered_shocks = sorted(
        shock_set.shocks, key=lambda shock: (shock.end_date, shock.scenario_id)
    )

    specifications = portfolio_configuration["positions"]
    position_ids = [str(item["instrument_id"]) for item in specifications]
    maturities = np.asarray([item["maturity_years"] for item in specifications], dtype=float)
    weights = np.asarray([item["target_weight"] for item in specifications], dtype=float)
    total_market_value = float(portfolio_configuration["initial_market_value"])
    maturity_indices = np.asarray(
        [int(np.flatnonzero(np.isclose(required_tenors, maturity))[0]) for maturity in maturities]
    )
    bump_decimal = float(portfolio_configuration["dv01"]["parallel_bump_decimal"])
    loss_sensitivity = key_rate_dv01(
        portfolio, base_curve, bump_decimal=bump_decimal
    ) / bump_decimal
    position_sensitivities = np.zeros((len(maturities), len(required_tenors)))
    position_sensitivities[np.arange(len(maturities)), maturity_indices] = (
        total_market_value
        * weights
        * np.sinh(maturities * bump_decimal)
        / bump_decimal
    )

    comparison_frames: list[pd.DataFrame] = []
    diagnostic_frames: list[pd.DataFrame] = []
    factor_frames: list[pd.DataFrame] = []
    loading_frames: list[pd.DataFrame] = []
    simulation_digests: dict[str, list[float]] = {}
    monte_carlo_configuration = configuration["pca_monte_carlo"]
    for window_value in configuration["estimation_windows"]:
        window = int(window_value)
        sample = ordered_shocks[-window:]
        historical_matrix = np.vstack(
            [shock.zero_rate_changes_cc for shock in sample]
        )
        historical_position_losses = _position_losses(
            historical_matrix[:, maturity_indices],
            maturities=maturities,
            weights=weights,
            total_market_value=total_market_value,
        )
        historical_risk = empirical_risk_with_contributions(
            losses=historical_position_losses.sum(axis=1),
            position_losses=historical_position_losses,
            position_ids=position_ids,
            var_confidence_levels=configuration["var_confidence_levels"],
            es_confidence_levels=configuration["es_confidence_levels"],
            convention_prefix="historical_full_repricing",
        )
        historical_risk.insert(0, "method", "Historical Simulation")

        model = fit_pca_covariance_model(
            ordered_shocks,
            estimation_window=window,
            factor_count=int(monte_carlo_configuration["factor_count"]),
        )
        parametric_risk = parametric_normal_risk(
            loss_sensitivity_per_decimal=loss_sensitivity,
            covariance=model.covariance,
            var_confidence_levels=configuration["var_confidence_levels"],
            es_confidence_levels=configuration["es_confidence_levels"],
        )
        parametric_risk = _parametric_position_contributions(
            parametric_risk,
            position_sensitivities=position_sensitivities,
            covariance=model.covariance,
            position_ids=position_ids,
        )
        parametric_risk.insert(0, "method", "Parametric Normal")

        seed = int(monte_carlo_configuration["random_seed"]) + window
        monte_carlo = simulate_pca_full_repricing(
            model,
            simulation_count=int(monte_carlo_configuration["simulation_count"]),
            seed=seed,
            maturity_years=maturities,
            target_weights=weights,
            total_market_value=total_market_value,
        )
        monte_carlo_risk = empirical_risk_with_contributions(
            losses=monte_carlo.losses,
            position_losses=monte_carlo.position_losses,
            position_ids=position_ids,
            var_confidence_levels=configuration["var_confidence_levels"],
            es_confidence_levels=configuration["es_confidence_levels"],
            convention_prefix="pca_gaussian_full_repricing",
        )
        monte_carlo_risk["loss_standard_deviation"] = float(
            np.std(monte_carlo.losses, ddof=1)
        )
        monte_carlo_risk.insert(0, "method", "PCA Monte Carlo")

        common = {
            "valuation_date": valuation_date.date().isoformat(),
            "horizon_days": int(configuration["horizon_days"]),
            "window_size": window,
            "sample_start_date": model.sample_start_date.isoformat(),
            "sample_end_date": model.sample_end_date.isoformat(),
            "sample_size": model.sample_size,
            "probability_measure": configuration["probability_measure"],
        }
        for frame in (historical_risk, parametric_risk, monte_carlo_risk):
            for name, value in common.items():
                frame[name] = value
            comparison_frames.append(frame)

        factor_diagnostics = model.factor_diagnostics_frame()
        factor_diagnostics.insert(0, "window_size", window)
        diagnostic_frames.append(factor_diagnostics)
        factor_contributions = factor_variance_contributions(
            model, loss_sensitivity_per_decimal=loss_sensitivity
        )
        factor_contributions.insert(0, "window_size", window)
        factor_frames.append(factor_contributions)
        loadings = model.loadings_frame()
        loadings.insert(0, "window_size", window)
        loading_frames.append(loadings)
        simulation_digests[str(window)] = [
            float(monte_carlo.losses.min()),
            float(monte_carlo.losses.max()),
            float(monte_carlo.losses.mean()),
            float(np.std(monte_carlo.losses, ddof=1)),
            monte_carlo.simulated_covariance_relative_error,
        ]

    comparison = pd.concat(comparison_frames, ignore_index=True)
    factor_diagnostics = pd.concat(diagnostic_frames, ignore_index=True)
    factor_contributions = pd.concat(factor_frames, ignore_index=True)
    loadings = pd.concat(loading_frames, ignore_index=True)

    expected_rows = len(configuration["estimation_windows"]) * 3 * (
        len(configuration["var_confidence_levels"])
        + len(configuration["es_confidence_levels"])
    )
    expected_methods = {"Historical Simulation", "Parametric Normal", "PCA Monte Carlo"}
    covariance_errors = [values[-1] for values in simulation_digests.values()]
    residual_diagnostics = factor_diagnostics.loc[
        factor_diagnostics["factor"] == "residual"
    ]
    residual_portfolio = factor_contributions.loc[
        factor_contributions["factor"] == "residual"
    ]
    es_99 = comparison.loc[
        (comparison["measure"] == "ES") & (comparison["confidence_level"] == 0.99)
    ].set_index(["method", "window_size"])["value"]
    var_99 = comparison.loc[
        (comparison["measure"] == "VaR") & (comparison["confidence_level"] == 0.99)
    ].set_index(["method", "window_size"])["value"]
    checks = {
        "every_requested_model_window_measure_is_reported": len(comparison) == expected_rows
        and set(comparison["method"]) == expected_methods,
        "all_samples_end_no_later_than_valuation_date": bool(
            (pd.to_datetime(comparison["sample_end_date"]) <= valuation_date).all()
        ),
        "position_contributions_reconcile": _contributions_reconcile(comparison),
        "pca_full_eigensystem_is_orthonormal": bool(
            all(
                np.allclose(
                    fit_pca_covariance_model(
                        ordered_shocks,
                        estimation_window=int(window),
                        factor_count=int(monte_carlo_configuration["factor_count"]),
                    ).eigenvectors
                    @ fit_pca_covariance_model(
                        ordered_shocks,
                        estimation_window=int(window),
                        factor_count=int(monte_carlo_configuration["factor_count"]),
                    ).eigenvectors.T,
                    np.eye(len(required_tenors)),
                    atol=1e-12,
                )
                for window in configuration["estimation_windows"]
            )
        ),
        "residual_curve_variance_is_retained": bool(
            (residual_diagnostics["explained_variance_ratio"] > 0.0).all()
        ),
        "residual_portfolio_variance_is_retained": bool(
            (residual_portfolio["portfolio_variance_share"] > 0.0).all()
        ),
        "factor_variance_shares_reconcile": bool(
            np.allclose(
                factor_contributions.groupby("window_size")["portfolio_variance_share"].sum(),
                1.0,
                atol=1e-12,
            )
        ),
        "simulated_covariance_relative_error_below_three_percent": max(covariance_errors)
        < 0.03,
        "same_level_99_es_is_not_below_var": bool((es_99 >= var_99).all()),
        "simulation_digests_are_finite": bool(
            np.isfinite(np.asarray(list(simulation_digests.values()), dtype=float)).all()
        ),
    }

    processed_directory = args.output_root / "processed"
    audit_directory = args.output_root / "audit"
    processed_directory.mkdir(parents=True, exist_ok=True)
    audit_directory.mkdir(parents=True, exist_ok=True)
    label = valuation_date.date().isoformat()
    comparison_path = processed_directory / f"m07_model_comparison_{label}.csv.gz"
    diagnostics_path = processed_directory / f"m07_pca_diagnostics_{label}.csv.gz"
    factors_path = processed_directory / f"m07_factor_contributions_{label}.csv.gz"
    loadings_path = processed_directory / f"m07_pca_loadings_{label}.csv.gz"
    report_path = audit_directory / f"m07_model_comparison_{label}.json"
    comparison.to_csv(comparison_path, index=False, compression="gzip")
    factor_diagnostics.to_csv(diagnostics_path, index=False, compression="gzip")
    factor_contributions.to_csv(factors_path, index=False, compression="gzip")
    loadings.to_csv(loadings_path, index=False, compression="gzip")

    primary_window = 750
    primary_results = comparison.loc[
        comparison["window_size"] == primary_window,
        ["method", "measure", "confidence_level", "value"],
    ]
    primary_curve_variance = factor_diagnostics.loc[
        factor_diagnostics["window_size"] == primary_window
    ].groupby("factor", as_index=False)["explained_variance_ratio"].sum()
    primary_portfolio_variance = factor_contributions.loc[
        factor_contributions["window_size"] == primary_window
    ].groupby("factor", as_index=False)["portfolio_variance_share"].sum()
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "configuration": configuration,
        "portfolio": {
            "portfolio_id": portfolio_configuration["portfolio_id"],
            "target_market_value": total_market_value,
            "valuation_date": label,
        },
        "primary_750_day_results": json.loads(primary_results.to_json(orient="records")),
        "primary_750_day_curve_variance": json.loads(
            primary_curve_variance.to_json(orient="records")
        ),
        "primary_750_day_portfolio_variance": json.loads(
            primary_portfolio_variance.to_json(orient="records")
        ),
        "simulation_digests": simulation_digests,
        "interpretation": {
            "first_three_components_are_interpretive_factors": True,
            "remaining_components_are_retained_in_simulation": True,
            "model_is_physical_measure_not_risk_neutral_pricing": True,
        },
        "artifacts": {
            "comparison_path": str(comparison_path),
            "factor_diagnostics_path": str(diagnostics_path),
            "factor_contributions_path": str(factors_path),
            "loadings_path": str(loadings_path),
        },
    }
    atomic_write_json(report_path, report)
    report["artifacts"]["report_path"] = str(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
