"""Frozen-position portfolio valuation for phase-one zero-coupon bonds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from bond_risk.curves import ZeroCurve
from bond_risk.instruments import ZeroCouponBond


@dataclass(frozen=True)
class Position:
    instrument: ZeroCouponBond
    quantity: float
    target_weight: float | None = None

    def __post_init__(self) -> None:
        if not np.isfinite(self.quantity) or self.quantity < 0:
            raise ValueError("Phase-one position quantity must be finite and non-negative")
        if self.target_weight is not None and (
            not np.isfinite(self.target_weight) or self.target_weight < 0
        ):
            raise ValueError("target_weight must be finite and non-negative")

    def market_value(self, curve: ZeroCurve) -> float:
        return self.quantity * self.instrument.price(curve)

    def linear_parallel_dv01(self, curve: ZeroCurve, bump_decimal: float = 1e-4) -> float:
        return self.quantity * self.instrument.linear_parallel_dv01(curve, bump_decimal)


@dataclass(frozen=True)
class Portfolio:
    portfolio_id: str
    positions: tuple[Position, ...]

    def __post_init__(self) -> None:
        if not self.portfolio_id:
            raise ValueError("portfolio_id must be non-empty")
        if not self.positions:
            raise ValueError("Portfolio requires at least one position")
        instrument_ids = [position.instrument.instrument_id for position in self.positions]
        if len(instrument_ids) != len(set(instrument_ids)):
            raise ValueError("Portfolio instrument IDs must be unique")

    def value(self, curve: ZeroCurve) -> float:
        return float(sum(position.market_value(curve) for position in self.positions))

    def pnl(self, base_curve: ZeroCurve, shocked_curve: ZeroCurve) -> float:
        """Return shocked value minus base value using frozen quantities."""

        return self.value(shocked_curve) - self.value(base_curve)

    def loss(self, base_curve: ZeroCurve, shocked_curve: ZeroCurve) -> float:
        """Return positive loss, defined as the negative frozen-position P&L."""

        return -self.pnl(base_curve, shocked_curve)

    def full_revaluation_parallel_dv01(
        self,
        curve: ZeroCurve,
        bump_decimal: float = 1e-4,
    ) -> float:
        """Return positive loss under an upward parallel one-bump scenario."""

        if not np.isfinite(bump_decimal) or bump_decimal <= 0:
            raise ValueError("bump_decimal must be finite and strictly positive")
        return self.loss(curve, curve.parallel_shift(bump_decimal))

    def linear_parallel_dv01(
        self,
        curve: ZeroCurve,
        bump_decimal: float = 1e-4,
    ) -> float:
        return float(
            sum(
                position.linear_parallel_dv01(curve, bump_decimal)
                for position in self.positions
            )
        )

    def position_report(
        self,
        curve: ZeroCurve,
        bump_decimal: float = 1e-4,
    ) -> pd.DataFrame:
        portfolio_value = self.value(curve)
        rows = []
        shocked_curve = curve.parallel_shift(bump_decimal)
        for position in self.positions:
            base_value = position.market_value(curve)
            shocked_value = position.market_value(shocked_curve)
            rows.append(
                {
                    "instrument_id": position.instrument.instrument_id,
                    "maturity_years": position.instrument.maturity_years,
                    "quantity": position.quantity,
                    "price_per_unit": position.instrument.price(curve),
                    "market_value": base_value,
                    "actual_weight": base_value / portfolio_value,
                    "target_weight": position.target_weight,
                    "linear_dv01": position.linear_parallel_dv01(curve, bump_decimal),
                    "full_revaluation_dv01": base_value - shocked_value,
                }
            )
        return pd.DataFrame(rows)


def build_target_weight_portfolio(
    *,
    portfolio_id: str,
    curve: ZeroCurve,
    total_market_value: float,
    instrument_specs: Iterable[Mapping[str, float | str]],
) -> Portfolio:
    """Calibrate quantities so base-date market values match target weights."""

    if not np.isfinite(total_market_value) or total_market_value <= 0:
        raise ValueError("total_market_value must be finite and strictly positive")
    specifications = list(instrument_specs)
    if not specifications:
        raise ValueError("At least one instrument specification is required")

    weights = np.asarray([float(specification["target_weight"]) for specification in specifications])
    if (weights < 0).any() or not np.isfinite(weights).all():
        raise ValueError("Target weights must be finite and non-negative")
    if not np.isclose(weights.sum(), 1.0, atol=1e-12):
        raise ValueError("Target weights must sum to one")

    positions = []
    for specification, weight in zip(specifications, weights, strict=True):
        bond = ZeroCouponBond(
            instrument_id=str(specification["instrument_id"]),
            maturity_years=float(specification["maturity_years"]),
            face_value=float(specification.get("face_value", 1.0)),
        )
        target_value = total_market_value * float(weight)
        quantity = target_value / bond.price(curve)
        positions.append(Position(bond, quantity, float(weight)))
    return Portfolio(portfolio_id=portfolio_id, positions=tuple(positions))
