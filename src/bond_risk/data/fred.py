"""FRED observations ingestion with explicit secret handling."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .storage import persist_versioned_payload

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


def download_fred_series(
    series_id: str,
    api_key: str,
    destination: Path,
    *,
    observation_start: str = "2005-01-01",
    observation_end: str | None = None,
    timeout: float = 60.0,
) -> tuple[Path, Path, dict[str, Any]]:
    """Download and version one FRED series without persisting the API key."""

    if not api_key:
        raise ValueError("A non-empty FRED API key is required")
    public_parameters = {
        "file_type": "json",
        "observation_start": observation_start,
        "series_id": series_id,
    }
    if observation_end:
        public_parameters["observation_end"] = observation_end

    response = requests.get(
        FRED_OBSERVATIONS_URL,
        params={**public_parameters, "api_key": api_key},
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
        prefix=f"fred_{series_id.lower()}",
        extension="json",
        source_url=FRED_OBSERVATIONS_URL,
        response_headers=headers,
        request_parameters=public_parameters,
    )


def parse_fred_observations(
    payload: dict[str, Any],
    *,
    series_id: str,
    percent_to_decimal: bool = True,
) -> pd.DataFrame:
    """Normalize FRED observations while retaining real-time-period fields."""

    records = payload.get("observations")
    if not isinstance(records, list):
        raise ValueError("FRED payload does not contain an observations list")

    frame = pd.DataFrame.from_records(records)
    required = {"date", "value"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"FRED observations are missing fields: {sorted(missing)}")

    frame["observation_date"] = pd.to_datetime(frame["date"], errors="coerce")
    if frame["observation_date"].isna().any():
        raise ValueError("FRED observations contain invalid dates")
    frame["value_original"] = pd.to_numeric(frame["value"].replace(".", None), errors="coerce")
    frame["value_decimal"] = (
        frame["value_original"] / 100.0 if percent_to_decimal else frame["value_original"]
    )
    frame["series_id"] = series_id
    frame["is_observed"] = frame["value_original"].notna()
    frame["quality_flag"] = frame["is_observed"].map({True: "valid", False: "missing"})

    for column in ("realtime_start", "realtime_end"):
        if column not in frame:
            frame[column] = None

    return frame[
        [
            "observation_date",
            "series_id",
            "value_original",
            "value_decimal",
            "realtime_start",
            "realtime_end",
            "is_observed",
            "quality_flag",
        ]
    ].sort_values("observation_date", ignore_index=True)


def audit_fred_series(
    observations: pd.DataFrame,
    *,
    as_of: str | date | None = None,
    stale_after_days: int = 14,
) -> dict[str, Any]:
    """Audit one normalized FRED series."""

    failures: list[str] = []
    warnings: list[str] = []
    duplicates = int(observations["observation_date"].duplicated().sum())
    if duplicates:
        failures.append(f"Found {duplicates} duplicate observation dates")

    observed = observations.loc[observations["is_observed"]]
    if observed.empty:
        failures.append("Series contains no observed values")
        latest_date = None
        stale_days = None
    else:
        latest_timestamp = pd.Timestamp(observed["observation_date"].max())
        latest_date = latest_timestamp.date().isoformat()
        audit_date = pd.Timestamp(as_of or date.today())
        stale_days = int((audit_date.normalize() - latest_timestamp.normalize()).days)
        if stale_days > stale_after_days:
            warnings.append(
                f"Latest observation is {stale_days} calendar days before the audit date"
            )

    missing_values = int((~observations["is_observed"]).sum())
    if missing_values:
        warnings.append(f"Series contains {missing_values} missing values")

    status = "FAIL" if failures else ("WARN" if warnings else "PASS")
    return {
        "duplicate_dates": duplicates,
        "failures": failures,
        "latest_observation_date": latest_date,
        "missing_value_count": missing_values,
        "observed_count": int(len(observed)),
        "stale_after_days": stale_after_days,
        "stale_days": stale_days,
        "status": status,
        "warnings": warnings,
    }
