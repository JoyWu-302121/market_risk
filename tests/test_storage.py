"""Tests for immutable raw-data storage metadata."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bond_risk.data.storage import persist_versioned_payload, sha256_bytes


class StorageTests(unittest.TestCase):
    def test_persisted_payload_and_metadata_are_verifiable(self) -> None:
        payload = b"date,value\n2026-09-18,4.25\n"
        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_path, metadata_path, metadata = persist_versioned_payload(
                payload=payload,
                destination=Path(temporary_directory),
                prefix="sample",
                extension="csv",
                source_url="https://example.test/sample.csv",
                retrieved_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
                request_parameters={"series_id": "DFF"},
            )

            self.assertEqual(raw_path.read_bytes(), payload)
            self.assertEqual(metadata["sha256"], sha256_bytes(payload))
            stored_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(stored_metadata["request_parameters"], {"series_id": "DFF"})
            self.assertNotIn("api_key", stored_metadata["request_parameters"])

    def test_naive_retrieval_timestamp_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "timezone-aware"):
                persist_versioned_payload(
                    payload=b"payload",
                    destination=Path(temporary_directory),
                    prefix="sample",
                    extension="bin",
                    source_url="https://example.test/sample.bin",
                    retrieved_at=datetime(2026, 9, 21),
                )


if __name__ == "__main__":
    unittest.main()
