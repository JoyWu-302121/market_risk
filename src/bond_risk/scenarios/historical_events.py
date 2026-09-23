"""Selection of extreme one-day and multi-day historical curve stresses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from collections.abc import Iterable

import numpy as np
import pandas as pd

from bond_risk.curves import ZeroCurve
from bond_risk.portfolio import Portfolio

from .historical import HistoricalCurveShock
from .stress import CurveStressScenario, evaluate_stress_scenarios


@dataclass(frozen=True)
class HistoricalEventSelection:
    scenarios: tuple[CurveStressScenario, ...]
    multi_day_audit: pd.DataFrame


def _generic_historical_scenario(
    shock: HistoricalCurveShock,
) -> CurveStressScenario:
    return CurveStressScenario(
        scenario_id=f"STRESS_{shock.scenario_id}_1D",
        scenario_family="historical_one_day",
        description=f"Historical one-day curve change ending {shock.end_date.isoformat()}",
        tenors_years=shock.tenors_years,
        shock_decimal=shock.zero_rate_changes_cc,
        horizon_days=1,
        metadata={
            "shock_start_date": shock.start_date.isoformat(),
            "shock_end_date": shock.end_date.isoformat(),
            "selection_rule": "largest_current_portfolio_loss",
        },
    )


def _complete_curve_by_date(
    curve_frame: pd.DataFrame,
    *,
    required_tenors: np.ndarray,
    as_of_date: date,
) -> tuple[list[pd.Timestamp], dict[pd.Timestamp, np.ndarray | None]]:
    parsed_dates = pd.to_datetime(curve_frame["observation_date"], errors="coerce").dt.normalize()
    if parsed_dates.isna().any():
        raise ValueError("Curve frame contains invalid observation dates")
    cutoff = pd.Timestamp(as_of_date)
    dates = sorted(pd.Timestamp(value) for value in parsed_dates.loc[parsed_dates <= cutoff].unique())
    curves: dict[pd.Timestamp, np.ndarray | None] = {}
    for selected_date in dates:
        selected = curve_frame.loc[parsed_dates == selected_date]
        observed = selected.loc[selected["is_observed"] == True].copy()  # noqa: E712
        observed["tenor_years"] = pd.to_numeric(observed["tenor_years"], errors="coerce")
        observed["zero_yield_cc"] = pd.to_numeric(observed["zero_yield_cc"], errors="coerce")
        if observed["tenor_years"].duplicated().any():
            curves[selected_date] = None
            continue
        values = observed.set_index("tenor_years")["zero_yield_cc"].reindex(required_tenors)
        curves[selected_date] = (
            values.to_numpy(dtype=float) if values.notna().all() else None
        )
    return dates, curves


def select_historical_extreme_scenarios(
    *,
    one_day_shocks: Iterable[HistoricalCurveShock],
    curve_frame: pd.DataFrame,
    base_curve: ZeroCurve,
    portfolio: Portfolio,
    top_one_day_scenarios: int,
    multi_day_horizons: Iterable[int],
    top_scenarios_per_horizon: int,
    key_rate_bump_decimal: float = 1e-4,
) -> HistoricalEventSelection:
    """Select worst full-repricing historical shocks for the current portfolio."""

    shocks = list(one_day_shocks)
    if top_one_day_scenarios <= 0 or top_scenarios_per_horizon <= 0:
        raise ValueError("Historical top-scenario counts must be strictly positive")
    generic_one_day = [_generic_historical_scenario(shock) for shock in shocks]
    one_day_results = evaluate_stress_scenarios(
        base_curve=base_curve,
        portfolio=portfolio,
        scenarios=generic_one_day,
        key_rate_bump_decimal=key_rate_bump_decimal,
    )
    successful_one_day = one_day_results.loc[one_day_results["status"] == "success"]
    selected_ids = set(
        successful_one_day.nlargest(top_one_day_scenarios, "loss")["scenario_id"]
    )
    selected_scenarios = [
        scenario for scenario in generic_one_day if scenario.scenario_id in selected_ids
    ]

    dates, curves = _complete_curve_by_date(
        curve_frame,
        required_tenors=base_curve.tenors_years,
        as_of_date=base_curve.observation_date,
    )
    audit_rows: list[dict[str, object]] = []
    for horizon in (int(value) for value in multi_day_horizons):
        if horizon <= 1:
            raise ValueError("Multi-day horizons must exceed one source-date transition")
        candidates: list[CurveStressScenario] = []
        for end_index in range(horizon, len(dates)):
            window_dates = dates[end_index - horizon : end_index + 1]
            end_date = window_dates[-1]
            scenario_id = f"STRESS_HIST_{horizon}D_{end_date.date().isoformat()}"
            missing_dates = [
                value.date().isoformat() for value in window_dates if curves[value] is None
            ]
            if missing_dates:
                audit_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "horizon_days": horizon,
                        "shock_start_date": window_dates[0].date().isoformat(),
                        "shock_end_date": end_date.date().isoformat(),
                        "status": "missing_input",
                        "failure_reason": "incomplete_curve_dates:" + ",".join(missing_dates),
                        "loss": np.nan,
                    }
                )
                continue
            start_curve = curves[window_dates[0]]
            end_curve = curves[end_date]
            assert start_curve is not None and end_curve is not None
            candidates.append(
                CurveStressScenario(
                    scenario_id=scenario_id,
                    scenario_family="historical_multi_day",
                    description=(
                        f"Historical {horizon}-source-day curve change ending "
                        f"{end_date.date().isoformat()}"
                    ),
                    tenors_years=base_curve.tenors_years,
                    shock_decimal=end_curve - start_curve,
                    horizon_days=horizon,
                    metadata={
                        "shock_start_date": window_dates[0].date().isoformat(),
                        "shock_end_date": end_date.date().isoformat(),
                        "selection_rule": "largest_current_portfolio_loss",
                    },
                )
            )
        results = evaluate_stress_scenarios(
            base_curve=base_curve,
            portfolio=portfolio,
            scenarios=candidates,
            key_rate_bump_decimal=key_rate_bump_decimal,
        )
        result_loss = results.set_index("scenario_id")["loss"].to_dict()
        result_status = results.set_index("scenario_id")["status"].to_dict()
        result_failure_reason = results.set_index("scenario_id")["failure_reason"].to_dict()
        for scenario in candidates:
            audit_rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "horizon_days": horizon,
                    "shock_start_date": scenario.metadata["shock_start_date"],
                    "shock_end_date": scenario.metadata["shock_end_date"],
                    "status": result_status[scenario.scenario_id],
                    "failure_reason": result_failure_reason[scenario.scenario_id],
                    "loss": result_loss[scenario.scenario_id],
                }
            )
        successful_results = results.loc[results["status"] == "success"]
        horizon_ids = set(
            successful_results.nlargest(top_scenarios_per_horizon, "loss")["scenario_id"]
        )
        selected_scenarios.extend(
            scenario for scenario in candidates if scenario.scenario_id in horizon_ids
        )
    audit = pd.DataFrame(audit_rows).sort_values(
        ["horizon_days", "shock_end_date"], ignore_index=True
    )
    return HistoricalEventSelection(tuple(selected_scenarios), audit)
