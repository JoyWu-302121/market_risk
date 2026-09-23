"""Family-constrained reverse stress search using full portfolio repricing."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from bond_risk.curves import ZeroCurve
from bond_risk.portfolio import Portfolio
if TYPE_CHECKING:
    from bond_risk.scenarios.stress import CurveStressScenario


@dataclass(frozen=True)
class ReverseStressSearch:
    results: pd.DataFrame
    breach_scenarios: tuple["CurveStressScenario", ...]


def _loss_at_amplitude(
    *,
    base_curve: ZeroCurve,
    portfolio: Portfolio,
    direction: np.ndarray,
    amplitude_bps: float,
) -> float:
    shocked_curve = ZeroCurve(
        base_curve.observation_date,
        base_curve.tenors_years,
        base_curve.zero_rates_cc + direction * amplitude_bps / 10_000.0,
    )
    return portfolio.loss(base_curve, shocked_curve)


def search_reverse_stress(
    *,
    base_curve: ZeroCurve,
    portfolio: Portfolio,
    directions: Mapping[str, np.ndarray],
    loss_thresholds_usd: Iterable[float],
    maximum_amplitude_bps: float,
    grid_step_bps: float,
    tolerance_bps: float,
) -> ReverseStressSearch:
    """Find the first loss-threshold crossing within each normalized direction."""

    from bond_risk.scenarios.stress import CurveStressScenario

    if maximum_amplitude_bps <= 0 or grid_step_bps <= 0 or tolerance_bps <= 0:
        raise ValueError("Reverse-stress amplitude controls must be strictly positive")
    if tolerance_bps >= grid_step_bps:
        raise ValueError("Reverse-stress tolerance must be below the grid step")
    rows: list[dict[str, object]] = []
    scenarios: list[CurveStressScenario] = []
    grid = np.arange(0.0, maximum_amplitude_bps + grid_step_bps, grid_step_bps)
    grid = grid[grid <= maximum_amplitude_bps + 1e-12]
    for threshold in (float(value) for value in loss_thresholds_usd):
        if threshold <= 0:
            raise ValueError("Reverse-stress loss thresholds must be strictly positive")
        for family, raw_direction in directions.items():
            direction = np.asarray(raw_direction, dtype=float)
            if direction.shape != base_curve.tenors_years.shape or not np.isfinite(direction).all():
                raise ValueError("Reverse-stress directions must match the base curve")
            maximum = float(np.max(np.abs(direction)))
            if maximum <= 0:
                raise ValueError("Reverse-stress directions must contain a non-zero node")
            direction = direction / maximum
            previous_amplitude = 0.0
            previous_loss = 0.0
            bracket: tuple[float, float] | None = None
            upper_loss: float | None = None
            for amplitude in grid[1:]:
                loss = _loss_at_amplitude(
                    base_curve=base_curve,
                    portfolio=portfolio,
                    direction=direction,
                    amplitude_bps=float(amplitude),
                )
                if loss >= threshold:
                    bracket = (previous_amplitude, float(amplitude))
                    upper_loss = loss
                    break
                previous_amplitude = float(amplitude)
                previous_loss = loss
            scenario_id = f"REVERSE_{family.upper()}_{threshold:.0f}USD"
            if bracket is None:
                rows.append(
                    {
                        "scenario_id": scenario_id,
                        "direction_family": family,
                        "loss_threshold_usd": threshold,
                        "status": "threshold_not_reached",
                        "amplitude_bps": np.nan,
                        "achieved_loss": np.nan,
                        "lower_bound_loss": previous_loss,
                        "maximum_amplitude_bps": maximum_amplitude_bps,
                    }
                )
                continue
            lower, upper = bracket
            while upper - lower > tolerance_bps:
                midpoint = (lower + upper) / 2.0
                midpoint_loss = _loss_at_amplitude(
                    base_curve=base_curve,
                    portfolio=portfolio,
                    direction=direction,
                    amplitude_bps=midpoint,
                )
                if midpoint_loss >= threshold:
                    upper = midpoint
                    upper_loss = midpoint_loss
                else:
                    lower = midpoint
                    previous_loss = midpoint_loss
            assert upper_loss is not None
            scenario = CurveStressScenario(
                scenario_id=scenario_id,
                scenario_family="reverse_stress",
                description=(
                    f"Minimum {family.replace('_', ' ')} maximum-node amplitude to breach "
                    f"USD {threshold:,.0f} loss"
                ),
                tenors_years=base_curve.tenors_years,
                shock_decimal=direction * upper / 10_000.0,
                metadata={
                    "direction_family": family,
                    "loss_threshold_usd": threshold,
                    "amplitude_bps": upper,
                    "search_tolerance_bps": tolerance_bps,
                },
            )
            scenarios.append(scenario)
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "direction_family": family,
                    "loss_threshold_usd": threshold,
                    "status": "success",
                    "amplitude_bps": upper,
                    "achieved_loss": upper_loss,
                    "lower_bound_loss": previous_loss,
                    "maximum_amplitude_bps": maximum_amplitude_bps,
                }
            )
    results = pd.DataFrame(rows)
    results["is_minimum_amplitude_for_threshold"] = False
    successful = results.loc[results["status"] == "success"]
    for threshold, group in successful.groupby("loss_threshold_usd"):
        minimum_index = group["amplitude_bps"].idxmin()
        results.loc[minimum_index, "is_minimum_amplitude_for_threshold"] = True
    return ReverseStressSearch(results, tuple(scenarios))
