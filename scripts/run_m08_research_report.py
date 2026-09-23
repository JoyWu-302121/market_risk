#!/usr/bin/env python3
"""Run or consolidate M03-M07 artifacts into the M08 research report."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import scipy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from bond_risk.data.storage import atomic_write_json
from bond_risk.reporting import generate_research_report


PREREQUISITE_SCRIPTS = (
    "run_m03_valuation.py",
    "run_m04_historical_risk.py",
    "run_m05_stress_testing.py",
    "run_m06_backtesting.py",
    "run_m07_model_comparison.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data",
        help="Root directory containing or receiving milestone artifacts",
    )
    parser.add_argument(
        "--run-prerequisites",
        action="store_true",
        help="Run M03-M07 pipelines before consolidating the report",
    )
    return parser.parse_args()


def _git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()


def _run_prerequisites(output_root: Path) -> dict[str, str]:
    log_directory = output_root / "audit" / "m08_prerequisite_logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    logs: dict[str, str] = {}
    for script_name in PREREQUISITE_SCRIPTS:
        milestone = script_name.split("_", 2)[1].upper()
        completed = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / script_name),
                "--output-root",
                str(output_root),
            ],
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log_path = log_directory / f"{script_name.removesuffix('.py')}.log"
        log_path.write_text(completed.stdout, encoding="utf-8")
        logs[milestone] = str(log_path)
        if completed.returncode != 0:
            raise RuntimeError(
                f"{script_name} failed with exit code {completed.returncode}; see {log_path}"
            )
    return logs


def main() -> int:
    args = parse_args()
    prerequisite_logs = (
        _run_prerequisites(args.output_root) if args.run_prerequisites else {}
    )
    runtime = {
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "scipy_version": scipy.__version__,
        "matplotlib_version": matplotlib.__version__,
    }
    run = generate_research_report(
        args.output_root,
        git_commit=_git_commit(),
        runtime=runtime,
    )
    valuation_date = str(run.summary["valuation_date"])
    processed_directory = args.output_root / "processed"
    audit_directory = args.output_root / "audit"
    processed_directory.mkdir(parents=True, exist_ok=True)
    audit_directory.mkdir(parents=True, exist_ok=True)

    table_paths: dict[str, str] = {}
    for name, frame in run.tables.items():
        path = processed_directory / f"m08_{name}_{valuation_date}.csv.gz"
        frame.to_csv(path, index=False, compression="gzip")
        table_paths[name] = str(path)

    report = {
        **run.summary,
        "checks": run.checks,
        "prerequisite_logs": prerequisite_logs,
        "consolidated_tables": table_paths,
    }
    report["status"] = "PASS" if all(run.checks.values()) else "FAIL"
    report_path = audit_directory / f"m08_research_report_{valuation_date}.json"
    atomic_write_json(report_path, report)
    report["report_path"] = str(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
