"""Auditable one-day historical zero-curve shocks and full repricing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd

from bond_risk.curves import ZeroCurve
from bond_risk.portfolio import Portfolio


@dataclass(frozen=True)
class HistoricalCurveShock:
    """A complete observed change between two adjacent source curve dates."""

    scenario_id: str
    start_date: date
    end_date: date
    tenors_years: np.ndarray
    zero_rate_changes_cc: np.ndarray

    def __post_init__(self) -> None:
        tenors = np.asarray(self.tenors_years, dtype=float)
        changes = np.asarray(self.zero_rate_changes_cc, dtype=float)
        if tenors.ndim != 1 or changes.ndim != 1 or len(tenors) != len(changes):
            raise ValueError("Historical shock tenors and changes must be matching vectors")
        if len(tenors) < 2 or not np.isfinite(tenors).all() or not np.isfinite(changes).all():
            raise ValueError("Historical shock requires at least two finite curve nodes")
        if (np.diff(tenors) <= 0).any():
            raise ValueError("Historical shock tenors must be strictly increasing")
        if self.end_date <= self.start_date:
            raise ValueError("Historical shock end_date must be after start_date")
        object.__setattr__(self, "tenors_years", tenors.copy())
        object.__setattr__(self, "zero_rate_changes_cc", changes.copy())


@dataclass(frozen=True)
class HistoricalShockSet:
    """Successful curve shocks plus an audit row for every candidate transition."""

    shocks: tuple[HistoricalCurveShock, ...]
    audit: pd.DataFrame


def _date_curve(
    frame: pd.DataFrame,
    normalized_dates: pd.Series,
    selected_date: pd.Timestamp,
    required_tenors: np.ndarray,
) -> tuple[np.ndarray | None, str | None]:
    selected = frame.loc[normalized_dates == selected_date].copy()
    observed = selected.loc[selected["is_observed"] == True].copy()  # noqa: E712
    observed["tenor_years"] = pd.to_numeric(observed["tenor_years"], errors="coerce")
    observed["zero_yield_cc"] = pd.to_numeric(observed["zero_yield_cc"], errors="coerce")
    if observed["tenor_years"].duplicated().any():
        return None, "duplicate_observed_tenor"
    by_tenor = observed.set_index("tenor_years")["zero_yield_cc"]
    missing = [float(tenor) for tenor in required_tenors if tenor not in by_tenor.index]
    if missing:
        return None, "missing_required_tenors:" + ",".join(f"{value:g}" for value in missing)
    values = by_tenor.reindex(required_tenors).to_numpy(dtype=float)
    if not np.isfinite(values).all():
        return None, "non_finite_required_yield"
    return values, None


def build_historical_curve_shocks(
    curve_frame: pd.DataFrame,
    *,
    required_tenors: Iterable[float],
    as_of_date: str | date | pd.Timestamp,
) -> HistoricalShockSet:
    """Build adjacent-date zero-rate changes without skipping failed dates.

    Every source-date transition at or before ``as_of_date`` receives an audit
    row. A shock is successful only when both adjacent dates contain every
    required observed tenor. Missing inputs are never converted to zero and a
    failed date is never bridged by differencing two non-adjacent valid curves.
    """

    required_columns = {"observation_date", "tenor_years", "zero_yield_cc", "is_observed"}
    missing_columns = required_columns.difference(curve_frame.columns)
    if missing_columns:
        raise ValueError(f"Curve frame is missing columns: {sorted(missing_columns)}")

    tenors = np.asarray(tuple(required_tenors), dtype=float)
    if len(tenors) < 2 or not np.isfinite(tenors).all() or (np.diff(tenors) <= 0).any():
        raise ValueError("required_tenors must be finite and strictly increasing")

    parsed_dates = pd.to_datetime(curve_frame["observation_date"], errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError("Curve frame contains invalid observation dates")
    normalized_dates = parsed_dates.dt.normalize()
    cutoff = pd.Timestamp(as_of_date).normalize()
    dates = sorted(pd.Timestamp(value) for value in normalized_dates.loc[normalized_dates <= cutoff].unique())
    if len(dates) < 2:
        raise ValueError("At least two source curve dates are required")

    curves: dict[pd.Timestamp, tuple[np.ndarray | None, str | None]] = {
        selected_date: _date_curve(curve_frame, normalized_dates, selected_date, tenors)
        for selected_date in dates
    }
    shocks: list[HistoricalCurveShock] = []
    audit_rows: list[dict[str, object]] = []
    for start_date, end_date in zip(dates[:-1], dates[1:], strict=True):
        scenario_id = f"HIST_{end_date.date().isoformat()}"
        start_curve, start_error = curves[start_date]
        end_curve, end_error = curves[end_date]
        errors = []
        if start_error:
            errors.append(f"start:{start_error}")
        if end_error:
            errors.append(f"end:{end_error}")
        if errors:
            status = "missing_input"
            failure_reason = ";".join(errors)
        else:
            assert start_curve is not None and end_curve is not None
            changes = end_curve - start_curve
            shock = HistoricalCurveShock(
                scenario_id=scenario_id,
                start_date=start_date.date(),
                end_date=end_date.date(),
                tenors_years=tenors,
                zero_rate_changes_cc=changes,
            )
            shocks.append(shock)
            status = "success"
            failure_reason = None
        audit_rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_type": "historical",
                "horizon_days": 1,
                "shock_start_date": start_date.date().isoformat(),
                "shock_end_date": end_date.date().isoformat(),
                "status": status,
                "failure_reason": failure_reason,
            }
        )
    return HistoricalShockSet(tuple(shocks), pd.DataFrame(audit_rows))


def revalue_historical_scenarios(
    *,
    base_curve: ZeroCurve,
    portfolio: Portfolio,
    shock_set: HistoricalShockSet,
) -> pd.DataFrame:
    """Apply complete historical shocks to a current frozen portfolio."""

    audit = shock_set.audit.copy()
    value_columns = [
        "base_value",
        "stressed_value",
        "pnl",
        "loss",
        "maximum_absolute_node_shock_bps",
    ]
    position_columns = [
        f"position_loss__{position.instrument.instrument_id}"
        for position in portfolio.positions
    ]
    for column in value_columns + position_columns:
        audit[column] = np.nan

    base_value = portfolio.value(base_curve)
    row_by_id = {scenario_id: index for index, scenario_id in audit["scenario_id"].items()}
    for shock in shock_set.shocks:
        row_index = row_by_id[shock.scenario_id]
        try:
            if not np.array_equal(shock.tenors_years, base_curve.tenors_years):
                raise ValueError("Shock tenors do not match base-curve nodes")
            shocked_curve = ZeroCurve(
                observation_date=base_curve.observation_date,
                tenors_years=base_curve.tenors_years,
                zero_rates_cc=base_curve.zero_rates_cc + shock.zero_rate_changes_cc,
            )
            stressed_value = portfolio.value(shocked_curve)
            pnl = stressed_value - base_value
            loss = -pnl
            position_losses = {
                f"position_loss__{position.instrument.instrument_id}": (
                    position.market_value(base_curve) - position.market_value(shocked_curve)
                )
                for position in portfolio.positions
            }
            if not np.isclose(sum(position_losses.values()), loss, atol=1e-8):
                raise ArithmeticError("Position losses do not sum to portfolio loss")
            audit.loc[row_index, value_columns] = [
                base_value,
                stressed_value,
                pnl,
                loss,
                float(np.max(np.abs(shock.zero_rate_changes_cc)) * 10_000.0),
            ]
            for column, value in position_losses.items():
                audit.loc[row_index, column] = value
        except (ArithmeticError, ValueError, FloatingPointError) as error:
            audit.loc[row_index, "status"] = "valuation_error"
            audit.loc[row_index, "failure_reason"] = str(error)
    return audit
