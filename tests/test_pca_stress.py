"""Tests for deterministic PCA curve stresses."""

from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.scenarios import (
    HistoricalCurveShock,
    build_pca_stress_scenarios,
    fit_pca_stress_model,
)


class PCAStressTests(unittest.TestCase):
    def test_fit_is_orthonormal_and_retains_residual_variance(self) -> None:
        tenors = np.arange(1.0, 6.0)
        shocks = []
        start = date(2026, 1, 1)
        for index in range(40):
            change = (
                np.sin(index / 3) * np.ones(5)
                + np.cos(index / 5) * np.linspace(-1, 1, 5)
                + np.sin(index / 7) * np.array([1, -1, 0.5, -0.5, 0.25])
                + np.cos(index / 11) * np.array([0.3, -0.2, 0.1, 0.2, -0.3])
            ) * 1e-4
            shocks.append(
                HistoricalCurveShock(
                    scenario_id=f"S{index}",
                    start_date=start + timedelta(days=index),
                    end_date=start + timedelta(days=index + 1),
                    tenors_years=tenors,
                    zero_rate_changes_cc=change,
                )
            )

        model = fit_pca_stress_model(shocks, estimation_window=30, factor_count=3)
        scenarios = build_pca_stress_scenarios(
            model, standard_deviation_multiples=[2, 3, 4]
        )

        np.testing.assert_allclose(model.loadings @ model.loadings.T, np.eye(3), atol=1e-12)
        self.assertGreater(model.residual_variance_ratio, 0.0)
        self.assertLess(model.residual_variance_ratio, 1.0)
        self.assertEqual(model.sample_size, 30)
        self.assertEqual(len(scenarios), 18)


if __name__ == "__main__":
    unittest.main()
