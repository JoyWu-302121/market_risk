"""Federal Reserve Gürkaynak-Sack-Wright yield-curve ingestion."""

from __future__ import annotations

import io
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

from .storage import persist_versioned_payload

GSW_CSV_URL = (
    "https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv"
)
GSW_SOURCE_NAME = "Federal Reserve GSW nominal yield curve"
ZERO_YIELD_PATTERN = re.compile(r"^SVENY(\d{2})$")


def download_gsw_csv(
    destination: Path,
    *,
    url: str = GSW_CSV_URL,
    timeout: float = 60.0,
) -> tuple[Path, Path, dict[str, Any]]:
    """Download and version the official GSW CSV without modifying its bytes."""

    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "bond-portfolio-risk-engine/0.2 research"},
    )
    response.raise_for_status()
    headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() in {"content-type", "etag", "last-modified"}
    }
    return persist_versioned_payload(
        payload=response.content,
        destination=destination,
        prefix="gsw_nominal_curve",
        extension="csv",
        source_url=url,
        response_headers=headers,
    )


def _decode_payload(payload: bytes | str | Path) -> str:
    if isinstance(payload, Path):
        return payload.read_text(encoding="utf-8-sig")
    if isinstance(payload, bytes):
        return payload.decode("utf-8-sig")
    return payload


def _header_row_index(text: str) -> int:
    for index, line in enumerate(text.splitlines()):
        if line.startswith("Date,"):
            return index
    raise ValueError("GSW CSV does not contain a Date header row")


def parse_gsw_csv(
    payload: bytes | str | Path,
    *,
    retrieved_at_utc: str | None = None,
) -> pd.DataFrame:
    """Parse GSW zero yields into an auditable long-form table.

    The source stores yields in percentage points. ``zero_yield_cc`` stores
    decimal continuously compounded rates, so a source value of 4.25 becomes
    0.0425. Missing curve nodes remain explicit rows with ``quality_flag`` set
    to ``missing``.
    """

    text = _decode_payload(payload)
    table = pd.read_csv(
        io.StringIO(text),
        skiprows=_header_row_index(text),
        na_values=["NA", -999.99],
    )
    if "Date" not in table.columns:
        raise ValueError("GSW table is missing the Date column")

    yield_columns = [column for column in table.columns if ZERO_YIELD_PATTERN.match(column)]
    if not yield_columns:
        raise ValueError("GSW table contains no SVENY zero-yield columns")

    dates = pd.to_datetime(table["Date"], errors="coerce")
    if dates.isna().any():
        invalid_count = int(dates.isna().sum())
        raise ValueError(f"GSW table contains {invalid_count} invalid dates")

    wide = table.loc[:, yield_columns].apply(pd.to_numeric, errors="coerce")
    wide.insert(0, "observation_date", dates)
    long = wide.melt(
        id_vars="observation_date",
        var_name="source_series",
        value_name="zero_yield_pct",
    )
    long["tenor_years"] = long["source_series"].str[-2:].astype(int)
    long["zero_yield_cc"] = long["zero_yield_pct"] / 100.0
    long["is_observed"] = long["zero_yield_cc"].notna()
    long["quality_flag"] = long["is_observed"].map({True: "valid", False: "missing"})
    long["source_name"] = GSW_SOURCE_NAME
    long["retrieved_at_utc"] = retrieved_at_utc

    return long[
        [
            "observation_date",
            "retrieved_at_utc",
            "source_name",
            "source_series",
            "tenor_years",
            "zero_yield_pct",
            "zero_yield_cc",
            "is_observed",
            "quality_flag",
        ]
    ].sort_values(["observation_date", "tenor_years"], ignore_index=True)


def audit_gsw_curve(
    curve: pd.DataFrame,
    *,
    required_tenors: Iterable[int] = (3, 7, 15),
    analysis_start: str | date = "2005-01-01",
    as_of: str | date | None = None,
    stale_after_days: int = 14,
) -> dict[str, Any]:
    """Audit coverage and integrity for the phase-one analysis window."""

    required = tuple(int(tenor) for tenor in required_tenors)
    start = pd.Timestamp(analysis_start)
    as_of_date = pd.Timestamp(as_of or date.today())
    window = curve.loc[curve["observation_date"] >= start].copy()
    active_date_mask = window.groupby("observation_date")["is_observed"].transform("any")
    empty_curve_dates = int(window.loc[~active_date_mask, "observation_date"].nunique())
    working = window.loc[active_date_mask].copy()
    observed = working.loc[working["is_observed"]].copy()

    if observed.empty:
        return {
            "status": "FAIL",
            "failures": ["No observed GSW zero yields in the analysis window"],
            "warnings": [],
        }

    failures: list[str] = []
    warnings: list[str] = []
    duplicates = int(
        working.duplicated(subset=["observation_date", "tenor_years"]).sum()
    )
    if duplicates:
        failures.append(f"Found {duplicates} duplicate date-tenor rows")

    invalid_yields = int(
        ((observed["zero_yield_cc"] < -0.05) | (observed["zero_yield_cc"] > 0.25)).sum()
    )
    if invalid_yields:
        failures.append(f"Found {invalid_yields} yields outside [-5%, 25%]")

    maximum_date = pd.Timestamp(observed["observation_date"].max())
    stale_days = int((as_of_date.normalize() - maximum_date.normalize()).days)
    if stale_days > stale_after_days:
        warnings.append(
            f"Latest observation is {stale_days} calendar days before the audit date"
        )

    coverage: dict[str, dict[str, Any]] = {}
    latest_date = maximum_date
    for tenor in required:
        subset = working.loc[working["tenor_years"] == tenor]
        observed_count = int(subset["is_observed"].sum())
        total_count = int(len(subset))
        latest_available = bool(
            subset.loc[subset["observation_date"] == latest_date, "is_observed"].any()
        )
        coverage[str(tenor)] = {
            "latest_available": latest_available,
            "missing_count": total_count - observed_count,
            "observed_count": observed_count,
            "observed_ratio": observed_count / total_count if total_count else 0.0,
        }
        if total_count == 0 or not latest_available:
            failures.append(f"Required {tenor}Y tenor is unavailable on the latest date")
        elif observed_count != total_count:
            warnings.append(f"Required {tenor}Y tenor has missing history")

    status = "FAIL" if failures else ("WARN" if warnings else "PASS")
    return {
        "analysis_start": start.date().isoformat(),
        "duplicate_date_tenor_rows": duplicates,
        "empty_curve_date_count": empty_curve_dates,
        "failures": failures,
        "invalid_yield_count": invalid_yields,
        "latest_observation_date": maximum_date.date().isoformat(),
        "observation_count": int(observed["observation_date"].nunique()),
        "required_tenor_coverage": coverage,
        "stale_after_days": stale_after_days,
        "stale_days": stale_days,
        "status": status,
        "warnings": warnings,
    }
