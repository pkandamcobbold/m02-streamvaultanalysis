"""How long each stage took, recorded durably rather than printed.

A number quoted in a report and held nowhere else is not a measurement, it is
a memory. `fetch_log.csv` is overwritten by every run, so after one cached
re-run it says the fetch made 1 API call in 2.6s — true of that run, and no
longer evidence for the claim in the decision log that acquisition took 20.3s
and 117 calls from an empty cache.

So every run appends a row here instead. This is also exactly what stage 8
needs: a measured per-stage time budget, with acquisition separated from
analysis, and a basis for projecting to ~500 titles that is arithmetic on real
numbers rather than a guess.

The file grows by a handful of rows per run. That is the point — the history is
the evidence, and `--force` runs can be compared against cached ones.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

TIMING_COLUMNS = [
    "run_at", "stage", "seconds", "api_calls", "cache_hits", "rows", "note",
]

TIMING_DTYPES = {
    "run_at": "str",
    "stage": "str",
    "seconds": "float",
    "api_calls": "Int64",
    "cache_hits": "Int64",
    "rows": "Int64",
    "note": "str",
}


def record(
    path: Path,
    stage: str,
    seconds: float,
    api_calls: int = 0,
    cache_hits: int = 0,
    rows: int = 0,
    note: str = "",
    run_at: str | None = None,
) -> None:
    """Append one stage's timing. Creates the file and header if absent.

    Appended with the csv module rather than a DataFrame write, because a
    read-modify-write of the whole file would lose every earlier run if the
    process died halfway, and the history is the only reason this file exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    row = {
        "run_at": run_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stage": stage,
        "seconds": round(float(seconds), 3),
        "api_calls": int(api_calls),
        "cache_hits": int(cache_hits),
        "rows": int(rows),
        "note": note,
    }
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIMING_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def load(path: Path) -> pd.DataFrame:
    """Read the timings back with explicit dtypes, never by inference."""
    frame = pd.read_csv(path, dtype=TIMING_DTYPES)
    frame["note"] = frame["note"].fillna("")
    return frame


def latest_run(path: Path) -> pd.DataFrame:
    """Just the most recent run's rows — what a report should quote."""
    frame = load(path)
    if frame.empty:
        return frame
    return frame.loc[frame["run_at"] == frame["run_at"].max()]
