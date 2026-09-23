"""Continuously compounded zero curve with log-discount interpolation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd


def latest_complete_curve_date(
    frame: pd.DataFrame,
    *,
    required_tenors: Iterable[float],
) -> pd.Timestamp:
    """Return the latest date with every required observed tenor exactly once."""

    required_columns = {"observation_date", "tenor_years", "is_observed"}
    missing = required_columns.difference(frame.columns)
    if missing:
        raise ValueError(f"Curve frame is missing columns: {sorted(missing)}")
    tenors = np.asarray(tuple(required_tenors), dtype=float)
    if len(tenors) < 2 or not np.isfinite(tenors).all() or (np.diff(tenors) <= 0).any():
        raise ValueError("required_tenors must be finite and strictly increasing")
    dates = pd.to_datetime(frame["observation_date"], errors="coerce").dt.normalize()
    if dates.isna().any():
        raise ValueError("Curve frame contains invalid observation dates")

    observed = frame.loc[frame["is_observed"] == True].copy()  # noqa: E712
    observed["_normalized_date"] = dates.loc[observed.index]
    required = set(tenors)
    complete_dates = []
    for observation_date, group in observed.groupby("_normalized_date", sort=True):
        tenor_values = pd.to_numeric(group["tenor_years"], errors="coerce")
        if (
            tenor_values.notna().all()
            and not tenor_values.duplicated().any()
            and required.issubset(set(tenor_values.astype(float)))
        ):
            complete_dates.append(pd.Timestamp(observation_date))
    if not complete_dates:
        raise ValueError("No complete observed curve is available for the required tenors")
    return max(complete_dates)


@dataclass(frozen=True)
class ZeroCurve:
    """A zero curve represented by tenor and continuously compounded rates.

    Interpolation is linear in log discount factors. Extrapolation is rejected
    because the public GSW inputs do not define an approved extrapolation rule
    for this project.
    """

    observation_date: date
    tenors_years: np.ndarray
    zero_rates_cc: np.ndarray

    def __post_init__(self) -> None:
        tenors = np.asarray(self.tenors_years, dtype=float)
        rates = np.asarray(self.zero_rates_cc, dtype=float)
        if tenors.ndim != 1 or rates.ndim != 1:
            raise ValueError("Curve tenors and rates must be one-dimensional")
        if len(tenors) < 2 or len(tenors) != len(rates):
            raise ValueError("Curve requires at least two matching tenor-rate nodes")
        if not np.isfinite(tenors).all() or not np.isfinite(rates).all():
            raise ValueError("Curve nodes must be finite")
        if (tenors <= 0).any():
            raise ValueError("Curve tenors must be strictly positive")
        if (np.diff(tenors) <= 0).any():
            raise ValueError("Curve tenors must be strictly increasing and unique")

        object.__setattr__(self, "tenors_years", tenors.copy())
        object.__setattr__(self, "zero_rates_cc", rates.copy())

    @property
    def minimum_tenor(self) -> float:
        return float(self.tenors_years[0])

    @property
    def maximum_tenor(self) -> float:
        return float(self.tenors_years[-1])

    @property
    def log_discount_factors(self) -> np.ndarray:
        return -self.zero_rates_cc * self.tenors_years

    @classmethod
    def from_long_frame(
        cls,
        frame: pd.DataFrame,
        *,
        observation_date: str | date | pd.Timestamp | None = None,
    ) -> "ZeroCurve":
        """Construct a curve from the normalized M02 long-form GSW table."""

        required_columns = {
            "observation_date",
            "tenor_years",
            "zero_yield_cc",
            "is_observed",
        }
        missing = required_columns.difference(frame.columns)
        if missing:
            raise ValueError(f"Curve frame is missing columns: {sorted(missing)}")

        dates = pd.to_datetime(frame["observation_date"], errors="coerce")
        if dates.isna().any():
            raise ValueError("Curve frame contains invalid observation dates")
        if observation_date is not None:
            selected_date = pd.Timestamp(observation_date).normalize()
        else:
            observed_dates = dates.loc[frame["is_observed"] == True]  # noqa: E712
            if observed_dates.empty:
                raise ValueError("Curve frame contains no observed curve nodes")
            selected_date = observed_dates.max().normalize()
        selected = frame.loc[(dates.dt.normalize() == selected_date) & frame["is_observed"]].copy()
        if selected.empty:
            raise ValueError(f"No observed curve nodes for {selected_date.date().isoformat()}")
        if selected["tenor_years"].duplicated().any():
            raise ValueError("Curve frame contains duplicate tenors on the selected date")

        selected = selected.sort_values("tenor_years")
        return cls(
            observation_date=selected_date.date(),
            tenors_years=selected["tenor_years"].to_numpy(dtype=float),
            zero_rates_cc=selected["zero_yield_cc"].to_numpy(dtype=float),
        )

    def _validated_maturities(self, maturities: float | Iterable[float]) -> tuple[np.ndarray, bool]:
        scalar_input = np.isscalar(maturities)
        values = np.atleast_1d(np.asarray(maturities, dtype=float))
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Maturities must be finite and strictly positive")
        if (values < self.minimum_tenor).any() or (values > self.maximum_tenor).any():
            raise ValueError(
                f"Maturities must lie within [{self.minimum_tenor}, {self.maximum_tenor}] years"
            )
        return values, bool(scalar_input)

    def discount_factor(self, maturity_years: float | Iterable[float]) -> float | np.ndarray:
        """Return discount factors using linear interpolation in log discount factors."""

        maturities, scalar_input = self._validated_maturities(maturity_years)
        interpolated_log_discount = np.interp(
            maturities,
            self.tenors_years,
            self.log_discount_factors,
        )
        discounts = np.exp(interpolated_log_discount)
        return float(discounts[0]) if scalar_input else discounts

    def zero_rate(self, maturity_years: float | Iterable[float]) -> float | np.ndarray:
        """Return the continuously compounded rate implied by the interpolated discount factor."""

        maturities, scalar_input = self._validated_maturities(maturity_years)
        discounts = np.asarray(self.discount_factor(maturities), dtype=float)
        rates = -np.log(discounts) / maturities
        return float(rates[0]) if scalar_input else rates

    def parallel_shift(self, shift_decimal: float) -> "ZeroCurve":
        """Return a curve with a parallel additive zero-rate shift in decimal units."""

        if not np.isfinite(shift_decimal):
            raise ValueError("Curve shift must be finite")
        return ZeroCurve(
            observation_date=self.observation_date,
            tenors_years=self.tenors_years,
            zero_rates_cc=self.zero_rates_cc + float(shift_decimal),
        )

    def to_frame(self) -> pd.DataFrame:
        """Return the curve nodes and derived discount factors."""

        return pd.DataFrame(
            {
                "observation_date": self.observation_date,
                "tenor_years": self.tenors_years,
                "zero_rate_cc": self.zero_rates_cc,
                "log_discount_factor": self.log_discount_factors,
                "discount_factor": np.exp(self.log_discount_factors),
            }
        )
