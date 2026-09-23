"""Research-report consolidation and visualization utilities."""

from .research_report import (
    ResearchReportRun,
    generate_research_report,
    historical_estimates_match,
    validate_milestone_reports,
)

__all__ = [
    "ResearchReportRun",
    "generate_research_report",
    "historical_estimates_match",
    "validate_milestone_reports",
]
