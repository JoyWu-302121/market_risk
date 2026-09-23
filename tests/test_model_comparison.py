"""Tests for M07 parametric and PCA Monte Carlo risk benchmarks."""

from __future__ import annotations

from datetime import date, timedelta
import json
import sys
import unittest
from pathlib import Path

import numpy as np
from scipy.stats import norm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.risk import (
    empirical_risk_with_contributions,
    factor_variance_contributions,
    fit_pca_covariance_model,
    parametric_normal_risk,
    simulate_pca_full_repricing,
)
from bond_risk.scenarios import HistoricalCurveShock


def synthetic_shocks(count: int = 120) -> list[HistoricalCurveShock]:
    random = np.random.default_rng(19)
    tenors = np.arange(1.0, 6.0)
    loading = np.array(
        [
            [1.0, 0.9, 0.8, 0.7, 0.6],
            [-1.0, -0.5, 0.0, 0.5, 1.0],
            [0.5, -0.5, 0.0, -0.5, 0.5],
            [0.2, -0.1, 0.3, -0.2, 0.1],
            [-0.1, 0.2, 0.1, -0.2, 0.3],
        ]
    )
    scales = np.array([8.0, 4.0, 2.0, 1.0, 0.5]) * 1e-4
    changes = random.standard_normal((count, 5)) @ (scales[:, None] * loading)
    start = date(2025, 1, 1)
    return [
        HistoricalCurveShock(
            scenario_id=f"S{index}",
            start_date=start + timedelta(days=index),
            end_date=start + timedelta(days=index + 1),
            tenors_years=tenors,
            zero_rate_changes_cc=change,
        )
        for index, change in enumerate(changes)
    ]


class ModelComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = fit_pca_covariance_model(
            synthetic_shocks(), estimation_window=100, factor_count=3
        )

    def test_full_eigensystem_reconstructs_sample_covariance_and_retains_residual(self) -> None:
        sample = synthetic_shocks()[-100:]
        changes = np.vstack([shock.zero_rate_changes_cc for shock in sample])
        expected = np.cov(changes, rowvar=False, ddof=1)
        np.testing.assert_allclose(self.model.covariance, expected, atol=1e-18)
        np.testing.assert_allclose(
            self.model.eigenvectors @ self.model.eigenvectors.T,
            np.eye(5),
            atol=1e-12,
        )
        self.assertGreater(self.model.residual_variance_ratio, 0.0)
        self.assertAlmostEqual(
            self.model.main_factor_variance_ratio + self.model.residual_variance_ratio,
            1.0,
        )

    def test_parametric_normal_matches_closed_form(self) -> None:
        sensitivity = np.array([2.0, 3.0])
        covariance = np.array([[4.0, 1.0], [1.0, 9.0]])
        result = parametric_normal_risk(
            loss_sensitivity_per_decimal=sensitivity,
            covariance=covariance,
            var_confidence_levels=[0.95],
            es_confidence_levels=[0.975],
        )
        sigma = np.sqrt(sensitivity @ covariance @ sensitivity)
        self.assertAlmostEqual(result.iloc[0]["value"], norm.ppf(0.95) * sigma)
        self.assertAlmostEqual(
            result.iloc[1]["value"], norm.pdf(norm.ppf(0.975)) / 0.025 * sigma
        )

    def test_monte_carlo_is_reproducible_and_preserves_covariance(self) -> None:
        kwargs = {
            "simulation_count": 60000,
            "seed": 7,
            "maturity_years": [1.0, 3.0, 5.0],
            "target_weights": [0.2, 0.3, 0.5],
            "total_market_value": 10_000_000.0,
        }
        first = simulate_pca_full_repricing(self.model, **kwargs)
        second = simulate_pca_full_repricing(self.model, **kwargs)
        np.testing.assert_array_equal(first.losses, second.losses)
        self.assertLess(first.simulated_covariance_relative_error, 0.03)

    def test_empirical_attribution_and_factor_shares_reconcile(self) -> None:
        run = simulate_pca_full_repricing(
            self.model,
            simulation_count=20000,
            seed=8,
            maturity_years=[1.0, 3.0, 5.0],
            target_weights=[0.2, 0.3, 0.5],
            total_market_value=10_000_000.0,
        )
        risk = empirical_risk_with_contributions(
            losses=run.losses,
            position_losses=run.position_losses,
            position_ids=["A", "B", "C"],
            var_confidence_levels=[0.95, 0.99],
            es_confidence_levels=[0.975, 0.99],
            convention_prefix="pca_mc_full_repricing",
        )
        for row in risk.itertuples(index=False):
            self.assertAlmostEqual(sum(json.loads(row.position_contributions).values()), row.value)
        self.assertGreaterEqual(
            risk.loc[(risk.measure == "ES") & (risk.confidence_level == 0.99), "value"].iloc[0],
            risk.loc[(risk.measure == "VaR") & (risk.confidence_level == 0.99), "value"].iloc[0],
        )
        factors = factor_variance_contributions(
            self.model, loss_sensitivity_per_decimal=np.arange(1.0, 6.0)
        )
        self.assertAlmostEqual(factors["portfolio_variance_share"].sum(), 1.0)
        self.assertGreater(
            factors.loc[factors["factor"] == "residual", "portfolio_variance_share"].sum(),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
