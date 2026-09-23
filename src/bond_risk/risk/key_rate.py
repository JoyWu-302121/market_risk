"""Curve-node sensitivities for stress-test attribution."""

from __future__ import annotations

import numpy as np

from bond_risk.curves import ZeroCurve
from bond_risk.portfolio import Portfolio


def key_rate_dv01(
    portfolio: Portfolio,
    curve: ZeroCurve,
    *,
    bump_decimal: float = 1e-4,
) -> np.ndarray:
    """Return central-difference loss sensitivity for a +1 bump at each node."""

    if not np.isfinite(bump_decimal) or bump_decimal <= 0:
        raise ValueError("bump_decimal must be finite and strictly positive")
    sensitivities = np.empty(len(curve.tenors_years), dtype=float)
    for index in range(len(curve.tenors_years)):
        upward_rates = curve.zero_rates_cc.copy()
        downward_rates = curve.zero_rates_cc.copy()
        upward_rates[index] += bump_decimal
        downward_rates[index] -= bump_decimal
        upward_curve = ZeroCurve(curve.observation_date, curve.tenors_years, upward_rates)
        downward_curve = ZeroCurve(curve.observation_date, curve.tenors_years, downward_rates)
        sensitivities[index] = (
            portfolio.value(downward_curve) - portfolio.value(upward_curve)
        ) / 2.0
    return sensitivities


def linear_key_rate_contributions(
    *,
    key_rate_dv01_values: np.ndarray,
    shock_decimal: np.ndarray,
    bump_decimal: float = 1e-4,
) -> np.ndarray:
    """Return node-level first-order loss contributions for a curve shock."""

    sensitivities = np.asarray(key_rate_dv01_values, dtype=float)
    shock = np.asarray(shock_decimal, dtype=float)
    if sensitivities.ndim != 1 or shock.ndim != 1 or len(sensitivities) != len(shock):
        raise ValueError("Sensitivity and shock vectors must have matching dimensions")
    if not np.isfinite(sensitivities).all() or not np.isfinite(shock).all():
        raise ValueError("Sensitivity and shock vectors must be finite")
    if not np.isfinite(bump_decimal) or bump_decimal <= 0:
        raise ValueError("bump_decimal must be finite and strictly positive")
    return sensitivities * shock / bump_decimal
