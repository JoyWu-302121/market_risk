"""Versioned storage helpers for downloaded public data."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


def sha256_bytes(payload: bytes) -> str:
    """Return a hexadecimal SHA-256 digest for a payload."""

    return hashlib.sha256(payload).hexdigest()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Write bytes atomically so an interrupted run cannot leave a partial file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Serialize a JSON object atomically with stable formatting."""

    encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write_bytes(path, encoded)


def persist_versioned_payload(
    *,
    payload: bytes,
    destination: Path,
    prefix: str,
    extension: str,
    source_url: str,
    retrieved_at: datetime | None = None,
    response_headers: Mapping[str, str] | None = None,
    request_parameters: Mapping[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    """Persist immutable raw bytes and a sidecar metadata file.

    The retrieval timestamp preserves each downloaded vintage. The content hash
    in the filename makes identical payloads detectable across vintages.
    """

    timestamp = retrieved_at or utc_now()
    if timestamp.tzinfo is None:
        raise ValueError("retrieved_at must be timezone-aware")

    digest = sha256_bytes(payload)
    stamp = timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{prefix}_{stamp}_{digest[:12]}.{extension.lstrip('.')}"
    raw_path = destination / filename
    metadata_path = raw_path.with_suffix(raw_path.suffix + ".metadata.json")

    metadata: dict[str, Any] = {
        "byte_count": len(payload),
        "retrieved_at_utc": timestamp.astimezone(timezone.utc).isoformat(),
        "sha256": digest,
        "source_url": source_url,
    }
    if response_headers:
        metadata["response_headers"] = dict(response_headers)
    if request_parameters:
        metadata["request_parameters"] = dict(request_parameters)

    if not raw_path.exists():
        atomic_write_bytes(raw_path, payload)
    atomic_write_json(metadata_path, metadata)
    return raw_path, metadata_path, metadata
