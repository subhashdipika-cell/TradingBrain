"""Consolidate and extend the local Dhan option-snapshot history.

Dhan does not provide a free backfilled option-premium database. This command
therefore focuses on the safe part we can automate: merge accumulated daily
CSV snapshots from one or more collectors, deduplicate overlapping files, and
write a coverage manifest. Future live collector runs can append new source
files without changing the raw AlphaEdge archive.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date


REQUIRED_COLUMNS = {
    "time", "underlying", "under_ltp", "expiry", "strike", "type", "ltp",
    "oi", "iv", "volume", "delta", "theta", "vega", "bid", "ask",
}
DATE_RE = re.compile(
    r"^(?P<symbol>[A-Z0-9]+)_OPT_(?P<date>\d{4}-\d{2}-\d{2})\.csv$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CollectionManifest:
    destination: str
    symbols: tuple[str, ...]
    files_written: int
    rows_written: int
    duplicate_rows: int
    first_date: str | None
    last_date: str | None
    source_files: int


def collect_option_snapshots(
    *,
    source_dirs: list[str],
    destination: str,
    symbols: list[str] | None = None,
) -> CollectionManifest:
    """Merge daily snapshots into a separate canonical directory."""
    wanted = {symbol.upper() for symbol in symbols} if symbols else None
    grouped: dict[tuple[str, str], dict[tuple[str, ...], dict[str, str]]] = defaultdict(dict)
    source_files = 0
    duplicate_rows = 0

    for source_dir in source_dirs:
        for name in sorted(os.listdir(source_dir)):
            match = DATE_RE.match(name)
            if match is None or (wanted and match.group("symbol") not in wanted):
                continue
            path = os.path.join(source_dir, name)
            if not os.path.isfile(path):
                continue
            source_files += 1
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                columns = set(reader.fieldnames or [])
                missing = REQUIRED_COLUMNS - columns
                if missing:
                    raise ValueError(f"{path} missing columns: {sorted(missing)}")
                key = (match.group("symbol"), match.group("date"))
                for row in reader:
                    row_key = tuple(
                        str(row.get(column, "")).strip()
                        for column in ("time", "expiry", "strike", "type")
                    )
                    if row_key in grouped[key]:
                        duplicate_rows += 1
                        continue
                    grouped[key][row_key] = {
                        column: str(row.get(column, "")) for column in sorted(columns)
                    }

    os.makedirs(destination, exist_ok=True)
    files_written = 0
    rows_written = 0
    dates: list[date] = []
    for (symbol, day), rows in sorted(grouped.items()):
        path = os.path.join(destination, f"{symbol}_OPT_{day}.csv")
        fieldnames = sorted(next(iter(rows.values())).keys()) if rows else []
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows.values())
        files_written += 1
        rows_written += len(rows)
        dates.append(date.fromisoformat(day))

    manifest = CollectionManifest(
        destination=os.path.abspath(destination),
        symbols=tuple(sorted({symbol for symbol, _ in grouped})),
        files_written=files_written,
        rows_written=rows_written,
        duplicate_rows=duplicate_rows,
        first_date=min(dates).isoformat() if dates else None,
        last_date=max(dates).isoformat() if dates else None,
        source_files=source_files,
    )
    _write_manifest(destination, manifest)
    return manifest


def _write_manifest(destination: str, manifest: CollectionManifest) -> None:
    path = os.path.join(destination, "collection_manifest.json")
    payload = {
        "version": 1,
        "destination": manifest.destination,
        "symbols": list(manifest.symbols),
        "files_written": manifest.files_written,
        "rows_written": manifest.rows_written,
        "duplicate_rows": manifest.duplicate_rows,
        "first_date": manifest.first_date,
        "last_date": manifest.last_date,
        "source_files": manifest.source_files,
    }
    fd, temp_path = tempfile.mkstemp(prefix="collection-", suffix=".json", dir=destination)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate Dhan option CSV history.")
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--symbol", action="append")
    args = parser.parse_args()
    manifest = collect_option_snapshots(
        source_dirs=args.source, destination=args.destination, symbols=args.symbol
    )
    print(json.dumps(asdict(manifest), indent=2))


if __name__ == "__main__":
    main()
