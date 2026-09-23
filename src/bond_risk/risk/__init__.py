"""Market-risk estimators and diagnostics."""

from .historical_simulation import (
    empirical_es,
    empirical_tail_weights,
    empirical_var,
    estimate_historical_risk,
)
from .backtesting import (
    HistoricalBacktestRun,
    christoffersen_independence,
    exact_zero_coupon_portfolio_losses,
    kupiec_unconditional_coverage,
    run_rolling_historical_backtest,
    summarize_es_diagnostics,
    summarize_var_backtests,
)
from .key_rate import key_rate_dv01, linear_key_rate_contributions
from .reverse_stress import ReverseStressSearch, search_reverse_stress

__all__ = [
    "empirical_es",
    "empirical_tail_weights",
    "empirical_var",
    "estimate_historical_risk",
    "key_rate_dv01",
    "linear_key_rate_contributions",
    "ReverseStressSearch",
    "search_reverse_stress",
    "HistoricalBacktestRun",
    "christoffersen_independence",
    "exact_zero_coupon_portfolio_losses",
    "kupiec_unconditional_coverage",
    "run_rolling_historical_backtest",
    "summarize_es_diagnostics",
    "summarize_var_backtests",
]
