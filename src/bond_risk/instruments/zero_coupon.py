"""Synthetic zero-coupon bond used by the phase-one portfolio."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from bond_risk.curves import ZeroCurve


@dataclass(frozen=True)
class ZeroCouponBond:
    """A single principal payment at a positive remaining maturity."""

    instrument_id: str
    maturity_years: float
    face_value: float = 1.0
    currency: str = "USD"

    def __post_init__(self) -> None:
        if not self.instrument_id:
            raise ValueError("instrument_id must be non-empty")
        if not np.isfinite(self.maturity_years) or self.maturity_years <= 0:
            raise ValueError("maturity_years must be finite and strictly positive")
        if not np.isfinite(self.face_value) or self.face_value <= 0:
            raise ValueError("face_value must be finite and strictly positive")
        if self.currency != "USD":
            raise ValueError("Phase one supports USD instruments only")

    def price(self, curve: ZeroCurve) -> float:
        """Return the clean value per instrument unit under the zero curve."""

        return self.face_value * float(curve.discount_factor(self.maturity_years))

    def linear_parallel_dv01(self, curve: ZeroCurve, bump_decimal: float = 1e-4) -> float:
        """Return the positive first-order loss for an upward parallel bump."""

        if not np.isfinite(bump_decimal) or bump_decimal <= 0:
            raise ValueError("bump_decimal must be finite and strictly positive")
        return self.price(curve) * self.maturity_years * bump_decimal
