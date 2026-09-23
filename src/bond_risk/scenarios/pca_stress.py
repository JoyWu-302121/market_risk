"""Deterministic principal-component stresses for historical curve changes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from collections.abc import Iterable

import numpy as np
import pandas as pd

from .historical import HistoricalCurveShock
from .stress import CurveStressScenario


@dataclass(frozen=True)
class PCAStressModel:
    tenors_years: np.ndarray
    loadings: np.ndarray
    factor_standard_deviations: np.ndarray
    explained_variance_ratios: np.ndarray
    residual_variance_ratio: float
    sample_start_date: date
    sample_end_date: date
    sample_size: int

    def diagnostics_frame(self) -> pd.DataFrame:
        rows = []
        for index, loading in enumerate(self.loadings, start=1):
            signs = np.sign(loading[np.abs(loading) > 1e-12])
            sign_changes = int(np.sum(signs[1:] != signs[:-1])) if len(signs) > 1 else 0
            tenor_correlation = float(np.corrcoef(self.tenors_years, loading)[0, 1])
            rows.append(
                {
                    "factor": f"PC{index}",
                    "explained_variance_ratio": float(
                        self.explained_variance_ratios[index - 1]
                    ),
                    "factor_standard_deviation_decimal": float(
                        self.factor_standard_deviations[index - 1]
                    ),
                    "same_sign_fraction": float(
                        max(np.mean(loading >= 0), np.mean(loading <= 0))
                    ),
                    "tenor_loading_correlation": tenor_correlation,
                    "loading_sign_changes": sign_changes,
                }
            )
        return pd.DataFrame(rows)

    def loadings_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame({"tenor_years": self.tenors_years})
        for index, loading in enumerate(self.loadings, start=1):
            frame[f"PC{index}"] = loading
        return frame


def fit_pca_stress_model(
    shocks: Iterable[HistoricalCurveShock],
    *,
    estimation_window: int,
    factor_count: int = 3,
) -> PCAStressModel:
    """Fit PCA to the latest complete historical zero-rate changes."""

    ordered = sorted(shocks, key=lambda shock: (shock.end_date, shock.scenario_id))
    if estimation_window <= 1 or len(ordered) < estimation_window:
        raise ValueError("PCA estimation window requires enough successful shocks")
    sample = ordered[-estimation_window:]
    tenors = sample[0].tenors_years
    if any(not np.array_equal(shock.tenors_years, tenors) for shock in sample):
        raise ValueError("PCA shocks must share identical curve nodes")
    if factor_count <= 0 or factor_count > len(tenors):
        raise ValueError("factor_count must lie within the curve dimension")

    changes = np.vstack([shock.zero_rate_changes_cc for shock in sample])
    centered = changes - changes.mean(axis=0, keepdims=True)
    _, singular_values, right_vectors = np.linalg.svd(centered, full_matrices=False)
    total_variance = float(np.sum(singular_values**2))
    if total_variance <= 0:
        raise ValueError("PCA input has no historical variation")
    explained = singular_values**2 / total_variance
    loadings = right_vectors[:factor_count].copy()
    for index in range(factor_count):
        largest_index = int(np.argmax(np.abs(loadings[index])))
        if loadings[index, largest_index] < 0:
            loadings[index] *= -1.0
    factor_standard_deviations = singular_values[:factor_count] / np.sqrt(
        estimation_window - 1
    )
    return PCAStressModel(
        tenors_years=tenors.copy(),
        loadings=loadings,
        factor_standard_deviations=factor_standard_deviations,
        explained_variance_ratios=explained[:factor_count],
        residual_variance_ratio=float(1.0 - explained[:factor_count].sum()),
        sample_start_date=sample[0].end_date,
        sample_end_date=sample[-1].end_date,
        sample_size=estimation_window,
    )


def build_pca_stress_scenarios(
    model: PCAStressModel,
    *,
    standard_deviation_multiples: Iterable[float],
) -> list[CurveStressScenario]:
    """Build +/- deterministic shocks for every retained PCA factor."""

    scenarios: list[CurveStressScenario] = []
    for factor_index, (loading, standard_deviation) in enumerate(
        zip(model.loadings, model.factor_standard_deviations, strict=True), start=1
    ):
        for multiple in (float(value) for value in standard_deviation_multiples):
            if multiple <= 0:
                raise ValueError("PCA stress multiples must be strictly positive")
            for sign, label in ((1.0, "PLUS"), (-1.0, "MINUS")):
                signed_multiple = sign * multiple
                scenarios.append(
                    CurveStressScenario(
                        scenario_id=f"PCA_PC{factor_index}_{label}_{multiple:g}SD",
                        scenario_family="pca_factor",
                        description=f"PC{factor_index} {signed_multiple:+g} historical standard deviations",
                        tenors_years=model.tenors_years,
                        shock_decimal=loading * standard_deviation * signed_multiple,
                        metadata={
                            "factor": f"PC{factor_index}",
                            "standard_deviation_multiple": signed_multiple,
                            "estimation_window": model.sample_size,
                            "sample_start_date": model.sample_start_date.isoformat(),
                            "sample_end_date": model.sample_end_date.isoformat(),
                        },
                    )
                )
    return scenarios
