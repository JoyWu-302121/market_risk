"""M02 public-data pipeline orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .fred import audit_fred_series, download_fred_series, parse_fred_observations
from .gsw import GSW_CSV_URL, audit_gsw_curve, download_gsw_csv, parse_gsw_csv
from .storage import atomic_write_json


def _write_csv_gzip(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip")


def run_gsw_pipeline(
    output_root: Path,
    *,
    analysis_start: str = "2005-01-01",
    required_tenors: Iterable[int] = (3, 7, 15),
    as_of: str | None = None,
    source_url: str = GSW_CSV_URL,
    stale_after_days: int = 14,
) -> dict[str, Any]:
    """Download, normalize, audit, and persist the primary GSW curve."""

    raw_path, metadata_path, metadata = download_gsw_csv(
        output_root / "raw" / "gsw",
        url=source_url,
    )
    curve = parse_gsw_csv(
        raw_path,
        retrieved_at_utc=metadata["retrieved_at_utc"],
    )
    audit = audit_gsw_curve(
        curve,
        analysis_start=analysis_start,
        required_tenors=required_tenors,
        as_of=as_of,
        stale_after_days=stale_after_days,
    )

    digest = metadata["sha256"][:12]
    processed_path = output_root / "processed" / f"gsw_zero_curve_long_{digest}.csv.gz"
    audit_path = output_root / "audit" / f"gsw_data_audit_{digest}.json"
    _write_csv_gzip(curve, processed_path)
    atomic_write_json(audit_path, audit)

    return {
        "audit": audit,
        "audit_path": str(audit_path),
        "metadata_path": str(metadata_path),
        "processed_path": str(processed_path),
        "raw_path": str(raw_path),
    }


def run_fred_pipeline(
    output_root: Path,
    *,
    series_id: str,
    api_key: str,
    observation_start: str = "2005-01-01",
    observation_end: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Download, normalize, audit, and persist one FRED series."""

    raw_path, metadata_path, metadata = download_fred_series(
        series_id,
        api_key,
        output_root / "raw" / "fred",
        observation_start=observation_start,
        observation_end=observation_end,
    )
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    observations = parse_fred_observations(payload, series_id=series_id)
    audit = audit_fred_series(observations, as_of=as_of)

    digest = metadata["sha256"][:12]
    processed_path = output_root / "processed" / f"fred_{series_id.lower()}_{digest}.csv.gz"
    audit_path = output_root / "audit" / f"fred_{series_id.lower()}_audit_{digest}.json"
    _write_csv_gzip(observations, processed_path)
    atomic_write_json(audit_path, audit)

    return {
        "audit": audit,
        "audit_path": str(audit_path),
        "metadata_path": str(metadata_path),
        "processed_path": str(processed_path),
        "raw_path": str(raw_path),
    }
