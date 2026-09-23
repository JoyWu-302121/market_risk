"""Finite-sample historical-simulation VaR and Expected Shortfall."""

from __future__ import annotations

import json
from collections.abc import Iterable

import numpy as np
import pandas as pd


def _validated_losses(losses: Iterable[float], confidence_level: float) -> np.ndarray:
    values = np.asarray(tuple(losses), dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("Losses must be a non-empty finite vector")
    if not np.isfinite(confidence_level) or not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must lie strictly between zero and one")
    return values


def empirical_var(losses: Iterable[float], confidence_level: float) -> float:
    """Return nearest-rank empirical VaR under the positive-loss convention."""

    values = _validated_losses(losses, confidence_level)
    rank = int(np.ceil(confidence_level * len(values)))
    return float(np.sort(values, kind="stable")[rank - 1])


def empirical_tail_weights(losses: Iterable[float], confidence_level: float) -> np.ndarray:
    """Return normalized weights for the worst ``n * (1-alpha)`` observations.

    Full worst observations receive equal unnormalized weight one. When the
    finite-sample tail mass is fractional, the next loss receives the remaining
    fractional weight. Returned weights sum to one.
    """

    values = _validated_losses(losses, confidence_level)
    tail_mass = len(values) * (1.0 - confidence_level)
    full_count = int(np.floor(tail_mass + 1e-12))
    fractional_count = tail_mass - full_count
    order = np.argsort(-values, kind="stable")
    weights = np.zeros(len(values), dtype=float)
    if full_count:
        weights[order[:full_count]] = 1.0
    if fractional_count > 1e-12:
        weights[order[full_count]] = fractional_count
    if weights.sum() == 0.0:
        weights[order[0]] = tail_mass
    return weights / tail_mass


def empirical_es(losses: Iterable[float], confidence_level: float) -> float:
    """Return empirical ES using fractional finite-sample tail mass."""

    values = _validated_losses(losses, confidence_level)
    return float(np.dot(empirical_tail_weights(values, confidence_level), values))


def _position_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column.startswith("position_loss__")]


def estimate_historical_risk(
    scenario_results: pd.DataFrame,
    *,
    valuation_date: str,
    windows: Iterable[int],
    var_confidence_levels: Iterable[float],
    es_confidence_levels: Iterable[float],
    horizon_days: int = 1,
) -> pd.DataFrame:
    """Estimate current historical VaR and ES over latest valid lookback windows."""

    required = {"scenario_id", "shock_end_date", "status", "loss"}
    missing = required.difference(scenario_results.columns)
    if missing:
        raise ValueError(f"Scenario results are missing columns: {sorted(missing)}")
    if horizon_days != 1:
        raise ValueError("Phase-one historical simulation requires a one-day horizon")

    cutoff = pd.Timestamp(valuation_date).normalize()
    working = scenario_results.copy()
    working["shock_end_date"] = pd.to_datetime(working["shock_end_date"], errors="coerce")
    if working["shock_end_date"].isna().any():
        raise ValueError("Scenario results contain invalid shock_end_date values")
    eligible = working.loc[
        (working["status"] == "success") & (working["shock_end_date"] <= cutoff)
    ].sort_values(["shock_end_date", "scenario_id"], kind="stable")
    if not np.isfinite(pd.to_numeric(eligible["loss"], errors="coerce")).all():
        raise ValueError("Successful scenarios must contain finite losses")

    position_columns = _position_columns(eligible)
    records: list[dict[str, object]] = []
    for window in (int(value) for value in windows):
        if window <= 0:
            raise ValueError("Estimation windows must be strictly positive")
        if len(eligible) < window:
            raise ValueError(
                f"Window {window} requires {window} successful scenarios; found {len(eligible)}"
            )
        sample = eligible.tail(window).reset_index(drop=True)
        losses = sample["loss"].to_numpy(dtype=float)
        common = {
            "valuation_date": cutoff.date().isoformat(),
            "horizon_days": horizon_days,
            "window_size": window,
            "sample_start_date": sample["shock_end_date"].iloc[0].date().isoformat(),
            "sample_end_date": sample["shock_end_date"].iloc[-1].date().isoformat(),
            "sample_size": len(sample),
        }

        stable_order = np.argsort(losses, kind="stable")
        for confidence_level in (float(value) for value in var_confidence_levels):
            var_value = empirical_var(losses, confidence_level)
            rank = int(np.ceil(confidence_level * len(losses)))
            scenario_index = int(stable_order[rank - 1])
            contributions = {
                column.removeprefix("position_loss__"): float(sample.loc[scenario_index, column])
                for column in position_columns
            }
            records.append(
                {
                    **common,
                    "measure": "VaR",
                    "confidence_level": confidence_level,
                    "value": var_value,
                    "boundary_scenario_id": sample.loc[scenario_index, "scenario_id"],
                    "position_contributions": json.dumps(contributions, sort_keys=True),
                    "convention": "nearest_rank_order_statistic",
                }
            )

        for confidence_level in (float(value) for value in es_confidence_levels):
            weights = empirical_tail_weights(losses, confidence_level)
            contributions = {
                column.removeprefix("position_loss__"): float(
                    np.dot(weights, sample[column].to_numpy(dtype=float))
                )
                for column in position_columns
            }
            records.append(
                {
                    **common,
                    "measure": "ES",
                    "confidence_level": confidence_level,
                    "value": empirical_es(losses, confidence_level),
                    "boundary_scenario_id": None,
                    "position_contributions": json.dumps(contributions, sort_keys=True),
                    "convention": "fractional_tail_mass",
                }
            )
    return pd.DataFrame(records)
