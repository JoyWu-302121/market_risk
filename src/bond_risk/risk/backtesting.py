"""Rolling historical-simulation backtests and coverage diagnostics."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from collections.abc import Iterable
import math

import numpy as np
import pandas as pd
from scipy.stats import chi2

from bond_risk.scenarios.historical import HistoricalCurveShock, HistoricalShockSet

from .historical_simulation import empirical_es, empirical_var


@dataclass(frozen=True)
class HistoricalBacktestRun:
    forecasts: pd.DataFrame
    audit: pd.DataFrame


def exact_zero_coupon_portfolio_losses(
    shock_matrix_decimal: np.ndarray,
    *,
    maturity_years: Iterable[float],
    target_weights: Iterable[float],
    total_market_value: float,
) -> np.ndarray:
    """Return exact frozen-position losses for target-value zero-coupon positions.

    Quantities are calibrated on each forecast date. For a zero-coupon position
    with base market value ``M``, the shocked/base price ratio is
    ``exp(-Delta_y * T)``. This is exact full repricing, not a duration estimate.
    """

    shocks = np.asarray(shock_matrix_decimal, dtype=float)
    maturities = np.asarray(tuple(maturity_years), dtype=float)
    weights = np.asarray(tuple(target_weights), dtype=float)
    if shocks.ndim == 1:
        shocks = shocks.reshape(1, -1)
    if shocks.ndim != 2 or shocks.shape[1] != len(maturities):
        raise ValueError("Shock matrix columns must match portfolio maturities")
    if len(maturities) == 0 or len(maturities) != len(weights):
        raise ValueError("Portfolio maturities and weights must be non-empty and matching")
    if not np.isfinite(shocks).all() or not np.isfinite(maturities).all():
        raise ValueError("Shocks and maturities must be finite")
    if not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(
        weights.sum(), 1.0, atol=1e-12
    ):
        raise ValueError("Target weights must be finite, non-negative, and sum to one")
    if not np.isfinite(total_market_value) or total_market_value <= 0:
        raise ValueError("total_market_value must be finite and strictly positive")
    target_values = total_market_value * weights
    return np.sum(
        target_values * (1.0 - np.exp(-shocks * maturities)),
        axis=1,
    )


def _maturity_node_indices(
    curve_tenors: np.ndarray, maturity_years: np.ndarray
) -> np.ndarray:
    indices = []
    for maturity in maturity_years:
        matches = np.flatnonzero(np.isclose(curve_tenors, maturity, atol=1e-12))
        if len(matches) != 1:
            raise ValueError(f"Portfolio maturity {maturity:g}Y must match one curve node")
        indices.append(int(matches[0]))
    return np.asarray(indices, dtype=int)


def run_rolling_historical_backtest(
    *,
    shock_set: HistoricalShockSet,
    maturity_years: Iterable[float],
    target_weights: Iterable[float],
    total_market_value: float,
    windows: Iterable[int],
    var_confidence_levels: Iterable[float],
    es_confidence_levels: Iterable[float],
) -> HistoricalBacktestRun:
    """Create no-lookahead forecasts and next-source-date realized losses."""

    maturities = np.asarray(tuple(maturity_years), dtype=float)
    weights = np.asarray(tuple(target_weights), dtype=float)
    successful_shocks = sorted(
        shock_set.shocks, key=lambda shock: (shock.end_date, shock.scenario_id)
    )
    if not successful_shocks:
        raise ValueError("Backtesting requires successful historical shocks")
    curve_tenors = successful_shocks[0].tenors_years
    if any(not np.array_equal(shock.tenors_years, curve_tenors) for shock in successful_shocks):
        raise ValueError("Backtest shocks must share identical curve nodes")
    maturity_indices = _maturity_node_indices(curve_tenors, maturities)
    shock_matrix = np.vstack(
        [shock.zero_rate_changes_cc[maturity_indices] for shock in successful_shocks]
    )
    losses = exact_zero_coupon_portfolio_losses(
        shock_matrix,
        maturity_years=maturities,
        target_weights=weights,
        total_market_value=total_market_value,
    )
    shock_by_id = {
        shock.scenario_id: (shock, float(loss))
        for shock, loss in zip(successful_shocks, losses, strict=True)
    }
    history_end_dates = [shock.end_date for shock in successful_shocks]
    requested_windows = [int(value) for value in windows]
    if not requested_windows or any(window <= 0 for window in requested_windows):
        raise ValueError("Backtest windows must be strictly positive")

    audit_rows: list[dict[str, object]] = []
    forecast_rows: list[dict[str, object]] = []
    for audit_row in shock_set.audit.itertuples(index=False):
        for window in requested_windows:
            common = {
                "scenario_id": audit_row.scenario_id,
                "forecast_date": audit_row.shock_start_date,
                "realization_date": audit_row.shock_end_date,
                "window_size": window,
            }
            if audit_row.status != "success":
                audit_rows.append(
                    {
                        **common,
                        "status": "missing_realized_input",
                        "failure_reason": audit_row.failure_reason,
                        "available_history_count": np.nan,
                    }
                )
                continue
            realized_shock, realized_loss = shock_by_id[audit_row.scenario_id]
            available_count = bisect_right(history_end_dates, realized_shock.start_date)
            if available_count < window:
                audit_rows.append(
                    {
                        **common,
                        "status": "insufficient_history",
                        "failure_reason": (
                            f"requires_{window}_successful_shocks_found_{available_count}"
                        ),
                        "available_history_count": available_count,
                    }
                )
                continue
            sample_losses = losses[available_count - window : available_count]
            audit_rows.append(
                {
                    **common,
                    "status": "success",
                    "failure_reason": None,
                    "available_history_count": available_count,
                }
            )
            for confidence_level in (float(value) for value in var_confidence_levels):
                forecast_value = empirical_var(sample_losses, confidence_level)
                forecast_rows.append(
                    {
                        **common,
                        "measure": "VaR",
                        "confidence_level": confidence_level,
                        "forecast_value": forecast_value,
                        "tail_var_value": forecast_value,
                        "realized_loss": realized_loss,
                        "exception": bool(realized_loss > forecast_value),
                        "tail_observation": bool(realized_loss > forecast_value),
                        "es_breach": False,
                        "sample_start_scenario_id": successful_shocks[
                            available_count - window
                        ].scenario_id,
                        "sample_end_scenario_id": successful_shocks[
                            available_count - 1
                        ].scenario_id,
                    }
                )
            for confidence_level in (float(value) for value in es_confidence_levels):
                tail_var = empirical_var(sample_losses, confidence_level)
                forecast_value = empirical_es(sample_losses, confidence_level)
                forecast_rows.append(
                    {
                        **common,
                        "measure": "ES",
                        "confidence_level": confidence_level,
                        "forecast_value": forecast_value,
                        "tail_var_value": tail_var,
                        "realized_loss": realized_loss,
                        "exception": False,
                        "tail_observation": bool(realized_loss > tail_var),
                        "es_breach": bool(realized_loss > forecast_value),
                        "sample_start_scenario_id": successful_shocks[
                            available_count - window
                        ].scenario_id,
                        "sample_end_scenario_id": successful_shocks[
                            available_count - 1
                        ].scenario_id,
                    }
                )
    forecasts = pd.DataFrame(forecast_rows).sort_values(
        ["window_size", "measure", "confidence_level", "realization_date"],
        ignore_index=True,
    )
    audit = pd.DataFrame(audit_rows).sort_values(
        ["window_size", "realization_date"], ignore_index=True
    )
    return HistoricalBacktestRun(forecasts=forecasts, audit=audit)


def _bernoulli_log_likelihood(successes: int, trials: int, probability: float) -> float:
    failures = trials - successes
    if probability <= 0.0:
        return 0.0 if successes == 0 else -math.inf
    if probability >= 1.0:
        return 0.0 if failures == 0 else -math.inf
    return successes * math.log(probability) + failures * math.log1p(-probability)


def kupiec_unconditional_coverage(
    exceptions: Iterable[bool], *, confidence_level: float
) -> dict[str, float | int]:
    """Return Kupiec's proportion-of-failures likelihood-ratio test."""

    values = np.asarray(tuple(exceptions), dtype=bool)
    if len(values) == 0 or not 0.0 < confidence_level < 1.0:
        raise ValueError("Kupiec test requires observations and a valid confidence level")
    count = int(values.sum())
    expected_probability = 1.0 - confidence_level
    observed_probability = count / len(values)
    null_ll = _bernoulli_log_likelihood(count, len(values), expected_probability)
    alternative_ll = _bernoulli_log_likelihood(count, len(values), observed_probability)
    statistic = max(0.0, -2.0 * (null_ll - alternative_ll))
    return {
        "observation_count": len(values),
        "exception_count": count,
        "expected_exception_count": len(values) * expected_probability,
        "exception_rate": observed_probability,
        "lr_statistic": statistic,
        "p_value": float(chi2.sf(statistic, df=1)),
    }


def christoffersen_independence(
    exceptions: Iterable[bool],
    *,
    contiguous_transitions: Iterable[bool] | None = None,
) -> dict[str, float | int]:
    """Return Christoffersen's first-order exception-independence test."""

    values = np.asarray(tuple(exceptions), dtype=int)
    if len(values) < 2:
        raise ValueError("Christoffersen test requires at least two observations")
    previous = values[:-1]
    current = values[1:]
    if contiguous_transitions is not None:
        mask = np.asarray(tuple(contiguous_transitions), dtype=bool)
        if len(mask) != len(values) - 1:
            raise ValueError("contiguous_transitions must contain n - 1 values")
        previous = previous[mask]
        current = current[mask]
    if len(previous) == 0:
        raise ValueError("Christoffersen test requires at least one eligible transition")
    n00 = int(((previous == 0) & (current == 0)).sum())
    n01 = int(((previous == 0) & (current == 1)).sum())
    n10 = int(((previous == 1) & (current == 0)).sum())
    n11 = int(((previous == 1) & (current == 1)).sum())
    pi01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    total_transitions = n00 + n01 + n10 + n11
    pooled = (n01 + n11) / total_transitions
    restricted_ll = _bernoulli_log_likelihood(n01 + n11, total_transitions, pooled)
    unrestricted_ll = _bernoulli_log_likelihood(n01, n00 + n01, pi01) + _bernoulli_log_likelihood(
        n11, n10 + n11, pi11
    )
    statistic = max(0.0, -2.0 * (restricted_ll - unrestricted_ll))
    return {
        "n00": n00,
        "n01": n01,
        "n10": n10,
        "n11": n11,
        "transition_count": total_transitions,
        "lr_statistic": statistic,
        "p_value": float(chi2.sf(statistic, df=1)),
    }


def _maximum_consecutive_true(values: np.ndarray) -> int:
    maximum = 0
    current = 0
    for value in values:
        current = current + 1 if value else 0
        maximum = max(maximum, current)
    return maximum


def _maximum_cumulative_drawdown(realized_losses: np.ndarray) -> float:
    cumulative_pnl = np.concatenate(([0.0], np.cumsum(-realized_losses)))
    running_peak = np.maximum.accumulate(cumulative_pnl)
    return float(np.max(running_peak - cumulative_pnl))


def summarize_var_backtests(
    forecasts: pd.DataFrame, *, significance_level: float = 0.05
) -> pd.DataFrame:
    """Summarize VaR coverage, independence, conditional coverage, and clustering."""

    if not 0.0 < significance_level < 1.0:
        raise ValueError("significance_level must lie strictly between zero and one")
    var_rows = forecasts.loc[forecasts["measure"] == "VaR"].copy()
    summaries = []
    for (window, confidence), group in var_rows.groupby(
        ["window_size", "confidence_level"], sort=True
    ):
        group = group.sort_values("realization_date")
        exceptions = group["exception"].to_numpy(dtype=bool)
        forecast_dates = pd.to_datetime(group["forecast_date"]).to_numpy()
        realization_dates = pd.to_datetime(group["realization_date"]).to_numpy()
        contiguous_transitions = forecast_dates[1:] == realization_dates[:-1]
        kupiec = kupiec_unconditional_coverage(
            exceptions, confidence_level=float(confidence)
        )
        independence = christoffersen_independence(
            exceptions, contiguous_transitions=contiguous_transitions
        )
        conditional_statistic = kupiec["lr_statistic"] + independence["lr_statistic"]
        conditional_p_value = float(chi2.sf(conditional_statistic, df=2))
        summaries.append(
            {
                "window_size": int(window),
                "confidence_level": float(confidence),
                "sample_start_date": group["realization_date"].iloc[0],
                "sample_end_date": group["realization_date"].iloc[-1],
                **{f"kupiec_{key}": value for key, value in kupiec.items()},
                **{
                    f"independence_{key}": value
                    for key, value in independence.items()
                },
                "conditional_coverage_lr_statistic": conditional_statistic,
                "conditional_coverage_p_value": conditional_p_value,
                "kupiec_reject_at_significance": bool(
                    kupiec["p_value"] < significance_level
                ),
                "independence_reject_at_significance": bool(
                    independence["p_value"] < significance_level
                ),
                "conditional_coverage_reject_at_significance": bool(
                    conditional_p_value < significance_level
                ),
                "maximum_consecutive_exceptions": _maximum_consecutive_true(exceptions),
                "maximum_realized_loss": float(group["realized_loss"].max()),
                "maximum_cumulative_drawdown": _maximum_cumulative_drawdown(
                    group["realized_loss"].to_numpy(dtype=float)
                ),
            }
        )
    return pd.DataFrame(summaries)


def summarize_es_diagnostics(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Compare forecast ES with realized losses on same-level VaR tail dates."""

    es_rows = forecasts.loc[forecasts["measure"] == "ES"].copy()
    summaries = []
    for (window, confidence), group in es_rows.groupby(
        ["window_size", "confidence_level"], sort=True
    ):
        group = group.sort_values("realization_date")
        tail = group.loc[group["tail_observation"]]
        if tail.empty:
            mean_tail_loss = math.nan
            mean_tail_es = math.nan
            mean_excess = math.nan
            ratio = math.nan
            status = "insufficient_tail_observations"
        else:
            mean_tail_loss = float(tail["realized_loss"].mean())
            mean_tail_es = float(tail["forecast_value"].mean())
            mean_excess = mean_tail_loss - mean_tail_es
            ratio = mean_tail_loss / mean_tail_es if mean_tail_es != 0 else math.nan
            status = "success"
        summaries.append(
            {
                "window_size": int(window),
                "confidence_level": float(confidence),
                "sample_start_date": group["realization_date"].iloc[0],
                "sample_end_date": group["realization_date"].iloc[-1],
                "observation_count": len(group),
                "expected_tail_count": len(group) * (1.0 - float(confidence)),
                "tail_observation_count": len(tail),
                "tail_observation_rate": len(tail) / len(group),
                "mean_realized_tail_loss": mean_tail_loss,
                "mean_forecast_es_on_tail_dates": mean_tail_es,
                "mean_tail_loss_minus_forecast_es": mean_excess,
                "tail_loss_to_es_ratio": ratio,
                "es_breach_count": int(group["es_breach"].sum()),
                "es_breach_rate": float(group["es_breach"].mean()),
                "status": status,
            }
        )
    return pd.DataFrame(summaries)
