"""Deterministic parallel, slope, and butterfly curve stresses."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from .stress import CurveStressScenario


def slope_shape(tenors_years: np.ndarray, *, pivot_years: float) -> np.ndarray:
    """Return a -1/0/+1 piecewise-linear steepener shape."""

    tenors = np.asarray(tenors_years, dtype=float)
    if not tenors[0] < pivot_years < tenors[-1]:
        raise ValueError("Slope pivot must lie strictly inside the curve range")
    return np.interp(tenors, [tenors[0], pivot_years, tenors[-1]], [-1.0, 0.0, 1.0])


def butterfly_shape(tenors_years: np.ndarray, *, center_years: float) -> np.ndarray:
    """Return a 0/+1/0 piecewise-linear positive butterfly shape."""

    tenors = np.asarray(tenors_years, dtype=float)
    if not tenors[0] < center_years < tenors[-1]:
        raise ValueError("Butterfly center must lie strictly inside the curve range")
    return np.interp(tenors, [tenors[0], center_years, tenors[-1]], [0.0, 1.0, 0.0])


def stress_direction_templates(
    tenors_years: np.ndarray,
    *,
    slope_pivot_years: float,
    butterfly_center_years: float,
) -> dict[str, np.ndarray]:
    """Return normalized directions whose maximum absolute value is one."""

    tenors = np.asarray(tenors_years, dtype=float)
    slope = slope_shape(tenors, pivot_years=slope_pivot_years)
    butterfly = butterfly_shape(tenors, center_years=butterfly_center_years)
    return {
        "parallel_up": np.ones_like(tenors),
        "steepener": slope,
        "flattener": -slope,
        "positive_butterfly": butterfly,
        "negative_butterfly": -butterfly,
    }


def build_hypothetical_scenarios(
    *,
    tenors_years: np.ndarray,
    parallel_amplitudes_bps: Iterable[float],
    slope_pivot_years: float,
    slope_amplitudes_bps: Iterable[float],
    butterfly_center_years: float,
    butterfly_amplitudes_bps: Iterable[float],
) -> list[CurveStressScenario]:
    """Build the accepted deterministic hypothetical stress library."""

    tenors = np.asarray(tenors_years, dtype=float)
    directions = stress_direction_templates(
        tenors,
        slope_pivot_years=slope_pivot_years,
        butterfly_center_years=butterfly_center_years,
    )
    scenarios: list[CurveStressScenario] = []
    for amplitude in (float(value) for value in parallel_amplitudes_bps):
        if amplitude <= 0:
            raise ValueError("Parallel amplitudes must be strictly positive")
        for sign, label in ((1.0, "UP"), (-1.0, "DOWN")):
            signed = sign * amplitude
            scenarios.append(
                CurveStressScenario(
                    scenario_id=f"HYP_PARALLEL_{label}_{amplitude:g}BP",
                    scenario_family="hypothetical_parallel",
                    description=f"Parallel {signed:+g} bp zero-curve shock",
                    tenors_years=tenors,
                    shock_decimal=np.ones_like(tenors) * signed / 10_000.0,
                    metadata={"amplitude_bps": signed},
                )
            )

    for amplitude in (float(value) for value in slope_amplitudes_bps):
        if amplitude <= 0:
            raise ValueError("Slope amplitudes must be strictly positive")
        for family in ("steepener", "flattener"):
            scenarios.append(
                CurveStressScenario(
                    scenario_id=f"HYP_{family.upper()}_{amplitude:g}BP",
                    scenario_family=f"hypothetical_{family}",
                    description=(
                        f"{family.title()} with {amplitude:g} bp maximum node amplitude "
                        f"and {slope_pivot_years:g}Y pivot"
                    ),
                    tenors_years=tenors,
                    shock_decimal=directions[family] * amplitude / 10_000.0,
                    metadata={
                        "maximum_amplitude_bps": amplitude,
                        "pivot_years": slope_pivot_years,
                    },
                )
            )

    for amplitude in (float(value) for value in butterfly_amplitudes_bps):
        if amplitude <= 0:
            raise ValueError("Butterfly amplitudes must be strictly positive")
        for family in ("positive_butterfly", "negative_butterfly"):
            scenarios.append(
                CurveStressScenario(
                    scenario_id=f"HYP_{family.upper()}_{amplitude:g}BP",
                    scenario_family=f"hypothetical_{family}",
                    description=(
                        f"{family.replace('_', ' ').title()} with {amplitude:g} bp maximum "
                        f"node amplitude and {butterfly_center_years:g}Y center"
                    ),
                    tenors_years=tenors,
                    shock_decimal=directions[family] * amplitude / 10_000.0,
                    metadata={
                        "maximum_amplitude_bps": amplitude,
                        "center_years": butterfly_center_years,
                    },
                )
            )
    return scenarios
