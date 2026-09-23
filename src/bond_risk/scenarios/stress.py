"""Common stress-scenario representation and full-repricing evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
import pandas as pd

from bond_risk.curves import ZeroCurve
from bond_risk.portfolio import Portfolio
from bond_risk.risk.key_rate import key_rate_dv01, linear_key_rate_contributions


@dataclass(frozen=True)
class CurveStressScenario:
    scenario_id: str
    scenario_family: str
    description: str
    tenors_years: np.ndarray
    shock_decimal: np.ndarray
    horizon_days: int = 1
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        tenors = np.asarray(self.tenors_years, dtype=float)
        shock = np.asarray(self.shock_decimal, dtype=float)
        if not self.scenario_id or not self.scenario_family:
            raise ValueError("Stress scenario ID and family must be non-empty")
        if tenors.ndim != 1 or shock.ndim != 1 or len(tenors) != len(shock):
            raise ValueError("Stress tenors and shocks must be matching vectors")
        if len(tenors) < 2 or not np.isfinite(tenors).all() or not np.isfinite(shock).all():
            raise ValueError("Stress scenario requires finite curve nodes")
        if (np.diff(tenors) <= 0).any():
            raise ValueError("Stress tenors must be strictly increasing")
        if self.horizon_days <= 0:
            raise ValueError("horizon_days must be strictly positive")
        object.__setattr__(self, "tenors_years", tenors.copy())
        object.__setattr__(self, "shock_decimal", shock.copy())


def evaluate_stress_scenarios(
    *,
    base_curve: ZeroCurve,
    portfolio: Portfolio,
    scenarios: list[CurveStressScenario] | tuple[CurveStressScenario, ...],
    key_rate_bump_decimal: float = 1e-4,
) -> pd.DataFrame:
    """Fully reprice curve stresses and reconcile position and key-rate attribution."""

    base_value = portfolio.value(base_curve)
    key_rates = key_rate_dv01(
        portfolio, base_curve, bump_decimal=key_rate_bump_decimal
    )
    rows: list[dict[str, object]] = []
    for scenario in scenarios:
        row: dict[str, object] = {
            "scenario_id": scenario.scenario_id,
            "scenario_family": scenario.scenario_family,
            "description": scenario.description,
            "horizon_days": scenario.horizon_days,
            "status": "success",
            "failure_reason": None,
            "metadata": json.dumps(dict(scenario.metadata), sort_keys=True),
        }
        try:
            if not np.array_equal(scenario.tenors_years, base_curve.tenors_years):
                raise ValueError("Stress tenors do not match base-curve nodes")
            shocked_curve = ZeroCurve(
                observation_date=base_curve.observation_date,
                tenors_years=base_curve.tenors_years,
                zero_rates_cc=base_curve.zero_rates_cc + scenario.shock_decimal,
            )
            stressed_value = portfolio.value(shocked_curve)
            full_loss = base_value - stressed_value
            position_losses = {
                position.instrument.instrument_id: float(
                    position.market_value(base_curve) - position.market_value(shocked_curve)
                )
                for position in portfolio.positions
            }
            node_contributions = linear_key_rate_contributions(
                key_rate_dv01_values=key_rates,
                shock_decimal=scenario.shock_decimal,
                bump_decimal=key_rate_bump_decimal,
            )
            linear_loss = float(node_contributions.sum())
            if not np.isclose(sum(position_losses.values()), full_loss, atol=1e-8):
                raise ArithmeticError("Position losses do not sum to full-repricing loss")
            row.update(
                {
                    "base_value": base_value,
                    "stressed_value": stressed_value,
                    "pnl": stressed_value - base_value,
                    "loss": full_loss,
                    "position_loss_contributions": json.dumps(position_losses, sort_keys=True),
                    "linear_key_rate_contributions": json.dumps(
                        {
                            f"{tenor:g}Y": float(value)
                            for tenor, value in zip(
                                base_curve.tenors_years, node_contributions, strict=True
                            )
                        },
                        sort_keys=True,
                    ),
                    "linear_sensitivity_loss": linear_loss,
                    "full_minus_linear": full_loss - linear_loss,
                    "maximum_absolute_shock_bps": float(
                        np.max(np.abs(scenario.shock_decimal)) * 10_000.0
                    ),
                    "minimum_shocked_zero_rate": float(shocked_curve.zero_rates_cc.min()),
                    "maximum_shocked_zero_rate": float(shocked_curve.zero_rates_cc.max()),
                    "shock_bps": json.dumps(
                        {
                            f"{tenor:g}Y": float(shock * 10_000.0)
                            for tenor, shock in zip(
                                scenario.tenors_years, scenario.shock_decimal, strict=True
                            )
                        },
                        sort_keys=True,
                    ),
                }
            )
        except (ArithmeticError, ValueError, FloatingPointError) as error:
            row["status"] = "valuation_error"
            row["failure_reason"] = str(error)
        rows.append(row)
    return pd.DataFrame(rows)
