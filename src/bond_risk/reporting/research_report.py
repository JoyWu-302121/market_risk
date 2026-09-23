"""Consolidate validated milestone artifacts into the M08 research report."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


MILESTONE_PREFIXES = {
    "M03": "m03_valuation_",
    "M04": "m04_historical_risk_",
    "M05": "m05_stress_testing_",
    "M06": "m06_backtesting_",
    "M07": "m07_model_comparison_",
}


@dataclass(frozen=True)
class ResearchReportRun:
    summary: dict[str, object]
    checks: dict[str, bool]
    tables: dict[str, pd.DataFrame]
    figure_paths: tuple[Path, ...]


def _latest_json(directory: Path, prefix: str) -> Path:
    matches = sorted(directory.glob(f"{prefix}*.json"))
    if not matches:
        raise FileNotFoundError(f"No {prefix} report found in {directory}")
    return matches[-1]


def _read_reports(output_root: Path) -> tuple[dict[str, dict[str, object]], dict[str, Path]]:
    audit_directory = output_root / "audit"
    paths = {
        milestone: _latest_json(audit_directory, prefix)
        for milestone, prefix in MILESTONE_PREFIXES.items()
    }
    reports = {
        milestone: json.loads(path.read_text(encoding="utf-8"))
        for milestone, path in paths.items()
    }
    return reports, paths


def _valuation_date(milestone: str, report: Mapping[str, object]) -> str:
    if milestone == "M03":
        return str(report["curve"]["observation_date"])
    return str(report["portfolio"]["valuation_date"])


def _portfolio_id(milestone: str, report: Mapping[str, object]) -> str:
    if milestone == "M03":
        return str(report["portfolio"]["portfolio_id"])
    return str(report["portfolio"]["portfolio_id"])


def _portfolio_value(milestone: str, report: Mapping[str, object]) -> float:
    portfolio = report["portfolio"]
    if milestone in {"M03", "M04", "M05"}:
        return float(portfolio["base_market_value"])
    return float(portfolio["target_market_value"])


def validate_milestone_reports(
    reports: Mapping[str, Mapping[str, object]],
) -> dict[str, bool]:
    """Validate the common date, portfolio, value, and PASS status contracts."""

    required = set(MILESTONE_PREFIXES)
    if set(reports) != required:
        raise ValueError(f"Reports must contain exactly {sorted(required)}")
    dates = {_valuation_date(name, reports[name]) for name in sorted(required)}
    portfolio_ids = {_portfolio_id(name, reports[name]) for name in sorted(required)}
    values = np.asarray(
        [_portfolio_value(name, reports[name]) for name in sorted(required)], dtype=float
    )
    return {
        "all_milestone_reports_pass": all(
            report.get("status") == "PASS" for report in reports.values()
        ),
        "common_valuation_date": len(dates) == 1,
        "common_portfolio_id": len(portfolio_ids) == 1,
        "common_portfolio_value": bool(
            np.isfinite(values).all() and np.allclose(values, values[0], atol=1e-6)
        ),
    }


def historical_estimates_match(
    m04_estimates: pd.DataFrame,
    m07_comparison: pd.DataFrame,
    *,
    tolerance: float = 1e-8,
) -> bool:
    """Check that M07 Historical Simulation exactly preserves M04 estimates."""

    keys = ["window_size", "measure", "confidence_level"]
    required = set(keys + ["value"])
    if not required.issubset(m04_estimates.columns) or not required.union(
        {"method"}
    ).issubset(m07_comparison.columns):
        return False
    left = m04_estimates[keys + ["value"]].rename(columns={"value": "m04_value"})
    right = m07_comparison.loc[
        m07_comparison["method"] == "Historical Simulation", keys + ["value"]
    ].rename(columns={"value": "m07_value"})
    merged = left.merge(right, on=keys, how="outer", validate="one_to_one")
    return len(merged) == len(left) == len(right) and bool(
        np.allclose(merged["m04_value"], merged["m07_value"], atol=tolerance, rtol=0.0)
    )


def _find_processed(output_root: Path, prefix: str, valuation_date: str) -> Path:
    matches = sorted((output_root / "processed").glob(f"{prefix}{valuation_date}.csv.gz"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected one {prefix}{valuation_date}.csv.gz artifact; found {len(matches)}"
        )
    return matches[0]


def _save_figure(figure: plt.Figure, path: Path) -> Path:
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return path


def _generate_figures(
    *,
    figure_directory: Path,
    valuation_date: str,
    curve: pd.DataFrame,
    m03_report: Mapping[str, object],
    model_comparison: pd.DataFrame,
    pca_loadings: pd.DataFrame,
    factor_contributions: pd.DataFrame,
    stress_results: pd.DataFrame,
    var_backtests: pd.DataFrame,
) -> tuple[Path, ...]:
    figure_directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    selected_curve = curve.loc[
        pd.to_datetime(curve["observation_date"]).dt.date.astype(str) == valuation_date
    ].sort_values("tenor_years")
    figure, axis = plt.subplots(figsize=(8, 4))
    axis.plot(selected_curve["tenor_years"], selected_curve["zero_yield_cc"] * 100.0)
    axis.set(title=f"GSW zero curve on {valuation_date}", xlabel="Tenor (years)", ylabel="Yield (%)")
    axis.grid(alpha=0.25)
    paths.append(_save_figure(figure, figure_directory / "01_zero_curve.png"))

    positions = pd.DataFrame(m03_report["portfolio"]["positions"])
    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].bar(positions["instrument_id"], positions["market_value"] / 1e6)
    axes[0].set(title="Position market values", ylabel="USD millions")
    axes[0].tick_params(axis="x", rotation=20)
    axes[1].bar(positions["instrument_id"], positions["full_revaluation_dv01"])
    axes[1].set(title="Full-revaluation DV01", ylabel="USD per 1 bp")
    axes[1].tick_params(axis="x", rotation=20)
    paths.append(_save_figure(figure, figure_directory / "02_portfolio_and_dv01.png"))

    primary = model_comparison.loc[model_comparison["window_size"] == 750].copy()
    primary["metric"] = primary["measure"] + " " + primary["confidence_level"].map(
        lambda value: f"{value:.1%}"
    )
    pivot = primary.pivot(index="metric", columns="method", values="value") / 1000.0
    figure, axis = plt.subplots(figsize=(10, 5))
    pivot.plot.bar(ax=axis)
    axis.set(title="750-day current risk estimates", xlabel="Risk measure", ylabel="USD thousands")
    axis.tick_params(axis="x", rotation=0)
    paths.append(_save_figure(figure, figure_directory / "03_model_comparison.png"))

    sensitivity = model_comparison.loc[
        (model_comparison["measure"] == "VaR")
        & (model_comparison["confidence_level"] == 0.99)
    ].pivot(index="window_size", columns="method", values="value") / 1000.0
    figure, axis = plt.subplots(figsize=(8, 4))
    sensitivity.plot(marker="o", ax=axis)
    axis.set(title="99% VaR window sensitivity", xlabel="Estimation window", ylabel="USD thousands")
    axis.grid(alpha=0.25)
    paths.append(_save_figure(figure, figure_directory / "04_window_sensitivity.png"))

    loading_sample = pca_loadings.loc[pca_loadings["window_size"] == 750]
    contribution_sample = factor_contributions.loc[
        factor_contributions["window_size"] == 750
    ].groupby("factor", as_index=False)["portfolio_variance_share"].sum()
    figure, axes = plt.subplots(1, 2, figsize=(11, 4))
    for component in ("PC1", "PC2", "PC3"):
        axes[0].plot(loading_sample["tenor_years"], loading_sample[component], label=component)
    axes[0].set(title="750-day PCA loadings", xlabel="Tenor (years)", ylabel="Loading")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    axes[1].bar(contribution_sample["factor"], contribution_sample["portfolio_variance_share"] * 100.0)
    axes[1].set(title="Portfolio variance attribution", ylabel="Share (%)")
    for index, value in enumerate(contribution_sample["portfolio_variance_share"]):
        axes[1].text(index, value * 100.0 + 0.5, f"{value:.2%}", ha="center")
    paths.append(_save_figure(figure, figure_directory / "05_pca_attribution.png"))

    worst = stress_results.loc[stress_results["status"] == "success"].nlargest(10, "loss")
    figure, axis = plt.subplots(figsize=(10, 5))
    axis.barh(worst["scenario_id"][::-1], worst["loss"][::-1] / 1000.0)
    axis.set(title="Ten largest standard stress losses", xlabel="USD thousands")
    paths.append(_save_figure(figure, figure_directory / "06_stress_losses.png"))

    figure, axis = plt.subplots(figsize=(8, 4))
    for confidence, group in var_backtests.groupby("confidence_level"):
        axis.plot(
            group["window_size"],
            group["kupiec_exception_rate"] * 100.0,
            marker="o",
            label=f"Observed {confidence:.0%}",
        )
        axis.axhline((1.0 - confidence) * 100.0, linestyle="--", alpha=0.5)
    axis.set(title="Historical VaR exception rates", xlabel="Estimation window", ylabel="Exception rate (%)")
    axis.legend()
    axis.grid(alpha=0.25)
    paths.append(_save_figure(figure, figure_directory / "07_backtesting.png"))
    return tuple(paths)


def generate_research_report(
    output_root: str | Path,
    *,
    git_commit: str,
    runtime: Mapping[str, str],
) -> ResearchReportRun:
    """Validate M03-M07 artifacts and create M08 summary tables and figures."""

    root = Path(output_root)
    reports, report_paths = _read_reports(root)
    checks = validate_milestone_reports(reports)
    valuation_date = _valuation_date("M07", reports["M07"])
    processed = root / "processed"

    curve_path = sorted(processed.glob("gsw_zero_curve_long_*.csv.gz"))[-1]
    curve = pd.read_csv(curve_path)
    m04_estimates = pd.read_csv(
        _find_processed(root, "m04_historical_risk_", valuation_date)
    )
    stress_results = pd.read_csv(
        _find_processed(root, "m05_stress_results_", valuation_date)
    )
    reverse_stress = pd.read_csv(
        _find_processed(root, "m05_reverse_stress_", valuation_date)
    )
    var_backtests = pd.read_csv(
        _find_processed(root, "m06_var_backtest_summary_", valuation_date)
    )
    es_diagnostics = pd.read_csv(
        _find_processed(root, "m06_es_diagnostics_", valuation_date)
    )
    model_comparison = pd.read_csv(
        _find_processed(root, "m07_model_comparison_", valuation_date)
    )
    pca_loadings = pd.read_csv(
        _find_processed(root, "m07_pca_loadings_", valuation_date)
    )
    factor_contributions = pd.read_csv(
        _find_processed(root, "m07_factor_contributions_", valuation_date)
    )

    checks.update(
        {
            "m04_and_m07_historical_estimates_match": historical_estimates_match(
                m04_estimates, model_comparison
            ),
            "all_three_estimation_windows_reported": set(
                model_comparison["window_size"].astype(int)
            )
            == {500, 750, 1250},
            "all_three_risk_methods_reported": set(model_comparison["method"])
            == {"Historical Simulation", "Parametric Normal", "PCA Monte Carlo"},
            "backtesting_is_explicitly_historical_only": (
                reports["M06"]["interpretation"].get("validated_model")
                == "Historical Simulation"
                and reports["M06"]["interpretation"].get(
                    "gaussian_models_backtested"
                )
                is False
            ),
            "pca_residual_curve_variance_is_positive": all(
                row["explained_variance_ratio"] > 0.0
                for row in reports["M07"]["primary_750_day_curve_variance"]
                if row["factor"] == "residual"
            ),
            "pca_residual_portfolio_variance_is_positive": all(
                row["portfolio_variance_share"] > 0.0
                for row in reports["M07"]["primary_750_day_portfolio_variance"]
                if row["factor"] == "residual"
            ),
        }
    )

    figures = _generate_figures(
        figure_directory=root / "reports" / "generated" / f"m08_{valuation_date}",
        valuation_date=valuation_date,
        curve=curve,
        m03_report=reports["M03"],
        model_comparison=model_comparison,
        pca_loadings=pca_loadings,
        factor_contributions=factor_contributions,
        stress_results=stress_results,
        var_backtests=var_backtests,
    )
    checks["all_required_figures_created"] = len(figures) == 7 and all(
        path.is_file() and path.stat().st_size > 0 for path in figures
    )

    primary_risk = model_comparison.loc[model_comparison["window_size"] == 750]
    summary: dict[str, object] = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "valuation_date": valuation_date,
        "portfolio": {
            "portfolio_id": _portfolio_id("M07", reports["M07"]),
            "market_value_usd": _portfolio_value("M07", reports["M07"]),
            "position_count": len(reports["M03"]["portfolio"]["positions"]),
        },
        "reproducibility": {
            "git_commit": git_commit,
            **dict(runtime),
            "source": "Federal Reserve GSW nominal zero-coupon yield curve",
            "monte_carlo_base_seed": reports["M07"]["configuration"][
                "pca_monte_carlo"
            ]["random_seed"],
        },
        "primary_750_day_risk": json.loads(
            primary_risk[
                ["method", "measure", "confidence_level", "value"]
            ].to_json(orient="records")
        ),
        "maximum_historical_loss": reports["M04"]["maximum_loss"],
        "worst_standard_stresses": reports["M05"]["worst_standard_scenarios"],
        "minimum_reverse_stresses": reports["M05"]["minimum_reverse_stresses"],
        "historical_var_backtests": reports["M06"]["var_backtests"],
        "historical_es_diagnostics": reports["M06"]["es_diagnostics"],
        "pca_curve_variance": reports["M07"]["primary_750_day_curve_variance"],
        "pca_portfolio_variance": reports["M07"][
            "primary_750_day_portfolio_variance"
        ],
        "report_boundaries": {
            "gaussian_models_have_rolling_backtests": False,
            "regulatory_capital_claim": False,
            "investment_recommendation": False,
            "phase_one_instruments": "synthetic_zero_coupon_bonds",
        },
        "source_reports": {name: str(path) for name, path in report_paths.items()},
        "figures": [str(path) for path in figures],
    }
    return ResearchReportRun(
        summary=summary,
        checks=checks,
        tables={
            "model_comparison": model_comparison,
            "stress_results": stress_results,
            "reverse_stress": reverse_stress,
            "var_backtests": var_backtests,
            "es_diagnostics": es_diagnostics,
            "factor_contributions": factor_contributions,
        },
        figure_paths=figures,
    )
