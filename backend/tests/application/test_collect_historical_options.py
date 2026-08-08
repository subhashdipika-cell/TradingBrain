"""Tests for safe consolidation of accumulated option snapshots."""

from __future__ import annotations

import csv
from pathlib import Path

from app.application.collect_historical_options import collect_option_snapshots


def test_collection_deduplicates_overlapping_daily_files(tmp_path: Path) -> None:
    source_a = tmp_path / "a"
    source_b = tmp_path / "b"
    destination = tmp_path / "canonical"
    source_a.mkdir()
    source_b.mkdir()
    header = ["time", "underlying", "under_ltp", "expiry", "strike", "type", "ltp", "oi", "prev_oi", "iv", "volume", "delta", "theta", "vega", "bid", "ask"]
    row = {key: "1" for key in header}
    row.update({"time": "2026-08-10T09:30:00", "expiry": "2026-08-13", "strike": "25000", "type": "CALL"})
    for root in (source_a, source_b):
        with open(root / "NIFTY50_OPT_2026-08-10.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=header)
            writer.writeheader()
            writer.writerow(row)
    manifest = collect_option_snapshots(
        source_dirs=[str(source_a), str(source_b)], destination=str(destination)
    )
    assert manifest.files_written == 1
    assert manifest.rows_written == 1
    assert manifest.duplicate_rows == 1
