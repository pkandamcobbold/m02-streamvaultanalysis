"""Tests for the orchestrator's durable record of a run.

The point of the timings file on disk is that a number quoted in an ADR can be
checked against something. So what matters here is that appending never loses
an earlier run, and that reading back does not turn the counts into floats —
the same fault the id ledger is guarded against (ADR-008, ADR-011).
"""
from __future__ import annotations

import pandas as pd

from pipeline.checks import latest_timing_run, load_timings
from run_pipeline import record_timing



def test_the_first_record_creates_the_file_with_a_header(tmp_path):
    path = tmp_path / "run_timings.csv"
    record_timing(path, "1_ingest", 0.12, rows=127, note="127 rows")

    assert path.exists()
    assert path.read_text(encoding="utf-8").splitlines()[0].startswith("run_at,stage")
    frame = load_timings(path)
    assert len(frame) == 1
    assert frame["stage"].item() == "1_ingest"
    assert frame["rows"].item() == 127


def test_appending_never_loses_an_earlier_run(tmp_path):
    """The history *is* the evidence. A read-modify-write could drop it."""
    path = tmp_path / "run_timings.csv"
    record_timing(path, "1_ingest", 0.1, run_at="2026-11-19T10:00:00+00:00")
    record_timing(path, "2_acquire", 26.4, api_calls=114, run_at="2026-11-19T10:00:00+00:00")
    record_timing(path, "1_ingest", 0.1, run_at="2026-11-19T11:00:00+00:00")
    record_timing(path, "2_acquire", 2.2, api_calls=0, cache_hits=117,
                   run_at="2026-11-19T11:00:00+00:00")

    frame = load_timings(path)
    assert len(frame) == 4
    assert frame["api_calls"].tolist() == [0, 114, 0, 0]
    assert sorted(set(frame["run_at"])) == [
        "2026-11-19T10:00:00+00:00", "2026-11-19T11:00:00+00:00",
    ]


def test_counts_read_back_as_integers(tmp_path):
    path = tmp_path / "run_timings.csv"
    record_timing(path, "2_acquire", 26.41, api_calls=114, cache_hits=3, rows=117)
    frame = load_timings(path)

    assert str(frame["api_calls"].dtype) == "Int64"
    assert str(frame["rows"].dtype) == "Int64"
    assert frame["seconds"].item() == 26.41


def test_latest_run_returns_only_the_most_recent(tmp_path):
    """What a report should quote: this run, not an average over history."""
    path = tmp_path / "run_timings.csv"
    record_timing(path, "2_acquire", 26.4, api_calls=114,
                   run_at="2026-11-19T10:00:00+00:00")
    record_timing(path, "1_ingest", 0.1, run_at="2026-11-19T11:00:00+00:00")
    record_timing(path, "2_acquire", 2.2, cache_hits=117,
                   run_at="2026-11-19T11:00:00+00:00")

    latest = latest_timing_run(path)
    assert len(latest) == 2
    assert set(latest["stage"]) == {"1_ingest", "2_acquire"}
    assert int(latest["api_calls"].sum()) == 0


def test_a_run_with_no_note_reads_back_as_empty_not_missing(tmp_path):
    path = tmp_path / "run_timings.csv"
    record_timing(path, "1_ingest", 0.1)
    frame = load_timings(path)
    assert frame["note"].item() == ""
    assert frame["note"].notna().all()


def test_seconds_are_rounded_but_not_truncated(tmp_path):
    path = tmp_path / "run_timings.csv"
    record_timing(path, "2_acquire", 26.414159)
    assert load_timings(path)["seconds"].item() == 26.414


def test_a_missing_file_is_not_silently_an_empty_timing_table(tmp_path):
    """Quoting a budget from a file that does not exist should fail loudly."""
    try:
        load_timings(tmp_path / "absent.csv")
    except FileNotFoundError:
        return
    raise AssertionError("load() invented a timings table")


def test_pandas_can_group_the_history_by_run(tmp_path):
    """The shape stage 8 needs: per-run totals, acquisition separable."""
    path = tmp_path / "run_timings.csv"
    for run, (ingest, acquire, calls) in {
        "2026-11-19T10:00:00+00:00": (0.1, 26.4, 114),
        "2026-11-19T11:00:00+00:00": (0.1, 2.2, 0),
    }.items():
        record_timing(path, "1_ingest", ingest, run_at=run)
        record_timing(path, "2_acquire", acquire, api_calls=calls, run_at=run)

    frame = load_timings(path)
    analysis_only = frame.loc[frame["stage"] != "2_acquire"]
    by_run = analysis_only.groupby("run_at", as_index=False).agg(
        analysis_seconds=pd.NamedAgg("seconds", "sum"),
    )
    assert len(by_run) == 2
    assert by_run["analysis_seconds"].tolist() == [0.1, 0.1]
