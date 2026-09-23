"""Historical and hypothetical market-risk scenario construction."""

from .historical import (
    HistoricalCurveShock,
    HistoricalShockSet,
    build_historical_curve_shocks,
    revalue_historical_scenarios,
)
from .historical_events import HistoricalEventSelection, select_historical_extreme_scenarios
from .hypothetical import (
    build_hypothetical_scenarios,
    butterfly_shape,
    slope_shape,
    stress_direction_templates,
)
from .stress import CurveStressScenario, evaluate_stress_scenarios
from .pca_stress import PCAStressModel, build_pca_stress_scenarios, fit_pca_stress_model

__all__ = [
    "HistoricalCurveShock",
    "HistoricalShockSet",
    "build_historical_curve_shocks",
    "revalue_historical_scenarios",
    "CurveStressScenario",
    "evaluate_stress_scenarios",
    "build_hypothetical_scenarios",
    "butterfly_shape",
    "slope_shape",
    "stress_direction_templates",
    "PCAStressModel",
    "build_pca_stress_scenarios",
    "fit_pca_stress_model",
    "HistoricalEventSelection",
    "select_historical_extreme_scenarios",
]
