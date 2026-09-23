"""Parametric-normal and PCA Monte Carlo market-risk benchmarks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
import json

import numpy as np
import pandas as pd
from scipy.stats import norm

from bond_risk.scenarios.historical import HistoricalCurveShock

from .historical_simulation import empirical_es, empirical_tail_weights, empirical_var


@dataclass(frozen=True)
class PCACovarianceModel:
    """Full historical covariance eigensystem with an interpretable PCA split."""

    tenors_years: np.ndarray
    eigenvalues: np.ndarray
    eigenvectors: np.ndarray
    explained_variance_ratios: np.ndarray
    factor_count: int
    sample_start_date: date
    sample_end_date: date
    sample_size: int

    @property
    def covariance(self) -> np.ndarray:
        return self.eigenvectors.T @ np.diag(self.eigenvalues) @ self.eigenvectors

    @property
    def main_factor_variance_ratio(self) -> float:
        return float(self.explained_variance_ratios[: self.factor_count].sum())

    @property
    def residual_variance_ratio(self) -> float:
        return float(self.explained_variance_ratios[self.factor_count :].sum())

    def factor_diagnostics_frame(self) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for index, (eigenvalue, ratio) in enumerate(
            zip(self.eigenvalues, self.explained_variance_ratios, strict=True), start=1
        ):
            rows.append(
                {
                    "factor": f"PC{index}" if index <= self.factor_count else "residual",
                    "component": f"PC{index}",
                    "is_main_factor": index <= self.factor_count,
                    "eigenvalue": float(eigenvalue),
                    "standard_deviation_decimal": float(np.sqrt(max(eigenvalue, 0.0))),
                    "explained_variance_ratio": float(ratio),
                }
            )
        return pd.DataFrame(rows)

    def loadings_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame({"tenor_years": self.tenors_years})
        for index in range(self.factor_count):
            frame[f"PC{index + 1}"] = self.eigenvectors[index]
        return frame


@dataclass(frozen=True)
class MonteCarloRun:
    shocks_decimal: np.ndarray
    position_losses: np.ndarray
    losses: np.ndarray
    simulated_covariance_relative_error: float


def fit_pca_covariance_model(
    shocks: Iterable[HistoricalCurveShock],
    *,
    estimation_window: int,
    factor_count: int = 3,
) -> PCACovarianceModel:
    """Fit a complete sample covariance eigensystem to latest curve changes."""

    ordered = sorted(shocks, key=lambda shock: (shock.end_date, shock.scenario_id))
    if estimation_window <= 1 or len(ordered) < estimation_window:
        raise ValueError("PCA estimation window requires enough successful shocks")
    sample = ordered[-estimation_window:]
    tenors = sample[0].tenors_years
    if any(not np.array_equal(shock.tenors_years, tenors) for shock in sample):
        raise ValueError("PCA shocks must share identical curve nodes")
    if factor_count <= 0 or factor_count >= len(tenors):
        raise ValueError("factor_count must leave at least one residual component")

    changes = np.vstack([shock.zero_rate_changes_cc for shock in sample])
    centered = changes - changes.mean(axis=0, keepdims=True)
    _, singular_values, right_vectors = np.linalg.svd(centered, full_matrices=False)
    eigenvalues = singular_values**2 / (estimation_window - 1)
    total_variance = float(eigenvalues.sum())
    if total_variance <= 0.0:
        raise ValueError("PCA input has no historical variation")
    eigenvectors = right_vectors.copy()
    for index in range(len(eigenvectors)):
        largest_index = int(np.argmax(np.abs(eigenvectors[index])))
        if eigenvectors[index, largest_index] < 0.0:
            eigenvectors[index] *= -1.0
    return PCACovarianceModel(
        tenors_years=tenors.copy(),
        eigenvalues=eigenvalues,
        eigenvectors=eigenvectors,
        explained_variance_ratios=eigenvalues / total_variance,
        factor_count=factor_count,
        sample_start_date=sample[0].end_date,
        sample_end_date=sample[-1].end_date,
        sample_size=estimation_window,
    )


def parametric_normal_risk(
    *,
    loss_sensitivity_per_decimal: Iterable[float],
    covariance: np.ndarray,
    var_confidence_levels: Iterable[float],
    es_confidence_levels: Iterable[float],
) -> pd.DataFrame:
    """Return zero-mean normal VaR and ES for a linear curve-risk exposure."""

    sensitivity = np.asarray(tuple(loss_sensitivity_per_decimal), dtype=float)
    matrix = np.asarray(covariance, dtype=float)
    if matrix.shape != (len(sensitivity), len(sensitivity)):
        raise ValueError("Covariance dimensions must match the sensitivity vector")
    if not np.isfinite(sensitivity).all() or not np.isfinite(matrix).all():
        raise ValueError("Sensitivity and covariance inputs must be finite")
    variance = float(sensitivity @ matrix @ sensitivity)
    if variance <= 0.0:
        raise ValueError("Portfolio loss variance must be strictly positive")
    sigma = float(np.sqrt(variance))
    rows: list[dict[str, object]] = []
    for confidence in (float(value) for value in var_confidence_levels):
        z_score = float(norm.ppf(confidence))
        rows.append(
            {
                "measure": "VaR",
                "confidence_level": confidence,
                "value": z_score * sigma,
                "loss_standard_deviation": sigma,
                "convention": "zero_mean_normal_linear_key_rate",
            }
        )
    for confidence in (float(value) for value in es_confidence_levels):
        z_score = float(norm.ppf(confidence))
        rows.append(
            {
                "measure": "ES",
                "confidence_level": confidence,
                "value": float(norm.pdf(z_score) / (1.0 - confidence) * sigma),
                "loss_standard_deviation": sigma,
                "convention": "zero_mean_normal_linear_key_rate",
            }
        )
    return pd.DataFrame(rows)

def simulate_pca_full_repricing(
    model: PCACovarianceModel,
    *,
    simulation_count: int,
    seed: int,
    maturity_years: Iterable[float],
    target_weights: Iterable[float],
    total_market_value: float,
) -> MonteCarloRun:
    """Simulate the complete PCA covariance and exactly reprice zero-coupon positions."""

    if simulation_count <= 1:
        raise ValueError("simulation_count must exceed one")
    maturities = np.asarray(tuple(maturity_years), dtype=float)
    weights = np.asarray(tuple(target_weights), dtype=float)
    if len(maturities) == 0 or len(maturities) != len(weights):
        raise ValueError("Portfolio maturities and weights must be non-empty and matching")
    if not np.isclose(weights.sum(), 1.0, atol=1e-12) or (weights < 0).any():
        raise ValueError("Target weights must be non-negative and sum to one")
    indices: list[int] = []
    for maturity in maturities:
        matches = np.flatnonzero(np.isclose(model.tenors_years, maturity, atol=1e-12))
        if len(matches) != 1:
            raise ValueError(f"Portfolio maturity {maturity:g}Y must match one curve node")
        indices.append(int(matches[0]))

    random = np.random.default_rng(seed)
    standard_normals = random.standard_normal((simulation_count, len(model.eigenvalues)))
    factor_scores = standard_normals * np.sqrt(np.maximum(model.eigenvalues, 0.0))
    simulated_shocks = factor_scores @ model.eigenvectors
    maturity_shocks = simulated_shocks[:, indices]
    target_values = total_market_value * weights
    position_losses = target_values * (1.0 - np.exp(-maturity_shocks * maturities))
    losses = position_losses.sum(axis=1)
    simulated_covariance = np.cov(simulated_shocks, rowvar=False, ddof=1)
    relative_error = float(
        np.linalg.norm(simulated_covariance - model.covariance, ord="fro")
        / np.linalg.norm(model.covariance, ord="fro")
    )
    return MonteCarloRun(
        shocks_decimal=simulated_shocks,
        position_losses=position_losses,
        losses=losses,
        simulated_covariance_relative_error=relative_error,
    )


def empirical_risk_with_contributions(
    *,
    losses: Iterable[float],
    position_losses: np.ndarray,
    position_ids: Iterable[str],
    var_confidence_levels: Iterable[float],
    es_confidence_levels: Iterable[float],
    convention_prefix: str,
) -> pd.DataFrame:
    """Return empirical risk measures with exactly reconciling position attribution."""

    values = np.asarray(tuple(losses), dtype=float)
    contributions = np.asarray(position_losses, dtype=float)
    identifiers = tuple(str(value) for value in position_ids)
    if contributions.shape != (len(values), len(identifiers)):
        raise ValueError("Position loss matrix dimensions must match losses and identifiers")
    rows: list[dict[str, object]] = []
    order = np.argsort(values, kind="stable")
    for confidence in (float(value) for value in var_confidence_levels):
        rank = int(np.ceil(confidence * len(values)))
        scenario_index = int(order[rank - 1])
        by_position = dict(
            zip(identifiers, contributions[scenario_index].astype(float), strict=True)
        )
        rows.append(
            {
                "measure": "VaR",
                "confidence_level": confidence,
                "value": empirical_var(values, confidence),
                "position_contributions": json.dumps(by_position, sort_keys=True),
                "convention": f"{convention_prefix}_nearest_rank",
            }
        )
    for confidence in (float(value) for value in es_confidence_levels):
        weights = empirical_tail_weights(values, confidence)
        by_position = dict(
            zip(identifiers, weights @ contributions, strict=True)
        )
        rows.append(
            {
                "measure": "ES",
                "confidence_level": confidence,
                "value": empirical_es(values, confidence),
                "position_contributions": json.dumps(by_position, sort_keys=True),
                "convention": f"{convention_prefix}_fractional_tail_mass",
            }
        )
    return pd.DataFrame(rows)


def factor_variance_contributions(
    model: PCACovarianceModel,
    *,
    loss_sensitivity_per_decimal: Iterable[float],
) -> pd.DataFrame:
    """Attribute linear portfolio variance to orthogonal PCA factors."""

    sensitivity = np.asarray(tuple(loss_sensitivity_per_decimal), dtype=float)
    if len(sensitivity) != len(model.tenors_years):
        raise ValueError("Sensitivity vector must match curve nodes")
    factor_exposures = model.eigenvectors @ sensitivity
    contributions = factor_exposures**2 * model.eigenvalues
    total = float(contributions.sum())
    if total <= 0.0:
        raise ValueError("Portfolio factor variance must be strictly positive")
    rows = [
        {
            "factor": f"PC{index + 1}" if index < model.factor_count else "residual",
            "component": f"PC{index + 1}",
            "is_main_factor": index < model.factor_count,
            "variance_contribution": float(value),
            "portfolio_variance_share": float(value / total),
        }
        for index, value in enumerate(contributions)
    ]
    return pd.DataFrame(rows)
