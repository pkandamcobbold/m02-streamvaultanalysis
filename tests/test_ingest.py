"""Stage 1 tests.

The analysis as a whole cannot be unit tested — it depends on live data. The
parser can, and it is where a silent error is most expensive: a mis-parsed id
either disappears from the analysis or, worse, fetches a different real film.

Every fixture below is a shape that actually occurs in the real id_list.csv.
"""
from __future__ import annotations

import pandas as pd
import pytest

from streamvault.ingest import (
    build_ledger,
    classify_value,
    reconciliation_summary,
    assert_ledger,
)


# --------------------------------------------------------------------------
# classify_value — one cell at a time
# --------------------------------------------------------------------------

def test_plain_id():
    assert classify_value("550") == (550, "parsed", "")


def test_whitespace_and_quotes_are_stripped():
    assert classify_value('  "550" ')[0] == 550
    assert classify_value("'550'")[0] == 550


def test_byte_order_mark_does_not_break_the_first_id():
    assert classify_value("﻿550")[0] == 550


def test_non_breaking_space_is_stripped():
    assert classify_value(" 550 ")[0] == 550


def test_float_formatted_id_is_recovered():
    tmdb_id, status, reason = classify_value("550.0")
    assert (tmdb_id, status) == (550, "parsed")
    assert "float" in reason


def test_imdb_id_is_invalid_and_says_why():
    tmdb_id, status, reason = classify_value("tt0468569")
    assert tmdb_id is None
    assert status == "invalid_id"
    assert "IMDb" in reason


def test_blank_is_accounted_for_not_dropped():
    tmdb_id, status, reason = classify_value("")
    assert (tmdb_id, status) == (None, "invalid_id")
    assert reason == "blank row"


@pytest.mark.parametrize("sentinel", ["-1", "0", "N/A", "n/a", "NULL", "TBC", "?", "-"])
def test_sentinels_are_flagged_as_placeholders_not_ids(sentinel):
    """None of these would ever appear in a null count: they are real values."""
    tmdb_id, status, _ = classify_value(sentinel)
    assert tmdb_id is None
    assert status == "invalid_id"


def test_header_detected_anywhere_in_the_file():
    for header in ["id", "tmdb_id", "movie_id", "TMDB_ID"]:
        assert classify_value(header)[1] == "header_row"


def test_genuinely_unparseable_is_reported_as_such():
    tmdb_id, status, reason = classify_value("Space Raider 4")
    assert (tmdb_id, status) == (None, "invalid_id")
    assert "unparseable" in reason


# --------------------------------------------------------------------------
# build_ledger — the whole file
# --------------------------------------------------------------------------

@pytest.fixture
def messy_file(tmp_path):
    """Every fault found in the real file, plus CRLF line endings."""
    path = tmp_path / "id_list.csv"
    path.write_bytes(
        b"tmdb_id\r\n"
        b"155\r\n"       # row 2  valid
        b"550\r\n"       # row 3  valid
        b"-1\r\n"        # row 4  sentinel
        b"\r\n"          # row 5  blank
        b"tt0468569\r\n" # row 6  IMDb id
        b"N/A\r\n"       # row 7  sentinel
        b"155\r\n"       # row 8  duplicate of row 2
        b"603.0\r\n"     # row 9  float-formatted, recovered
    )
    return path


def test_ledger_never_loses_a_row(messy_file):
    ledger = build_ledger(messy_file, expected_id_count=8)
    assert len(ledger) == 9           # 1 header + 8 data rows
    assert ledger.attrs["header_rows"] == 1
    assert ledger.attrs["data_rows"] == 8


def test_ledger_statuses_reconcile_exactly(messy_file):
    ledger = build_ledger(messy_file, expected_id_count=8)
    total = int(reconciliation_summary(ledger)["rows"].sum())
    assert total == ledger.attrs["data_rows"]


def test_ids_queued_for_fetch_are_unique(messy_file):
    ledger = build_ledger(messy_file, expected_id_count=8)
    to_fetch = ledger.loc[ledger["status"] == "parsed", "tmdb_id"]
    assert to_fetch.is_unique
    assert sorted(to_fetch.tolist()) == [155, 550, 603]


def test_duplicate_points_back_to_its_first_occurrence(messy_file):
    ledger = build_ledger(messy_file, expected_id_count=8)
    dup = ledger.loc[ledger["status"] == "duplicate"].iloc[0]
    assert dup["source_row"] == 8
    assert "source_row 2" in dup["reason"]


def test_id_column_is_integer_not_float(messy_file):
    """The whole point of stage 1: 550 must never become 550.0."""
    ledger = build_ledger(messy_file, expected_id_count=8)
    assert str(ledger["tmdb_id"].dtype) == "Int64"
    assert ledger.loc[ledger["status"] == "parsed", "tmdb_id"].tolist() == [155, 550, 603]


def test_crlf_leaves_no_carriage_return_in_values(messy_file):
    ledger = build_ledger(messy_file, expected_id_count=8)
    assert not ledger["raw_value"].str.contains("\r").any()


def test_every_unusable_row_carries_a_reason(messy_file):
    ledger = build_ledger(messy_file, expected_id_count=8)
    unusable = ledger.loc[ledger["status"].isin(["invalid_id", "duplicate"])]
    assert (unusable["reason"].str.len() > 0).all()


def test_count_mismatch_is_a_note_not_a_crash(messy_file, capsys):
    """Next year the list is ~500 titles. A hard assert would break the rerun."""
    notes = assert_ledger(build_ledger(messy_file, expected_id_count=127))
    assert any("RECONCILIATION NOTE" in note for note in notes)


def test_matching_count_produces_no_note(messy_file):
    notes = assert_ledger(build_ledger(messy_file, expected_id_count=8))
    assert not any("RECONCILIATION NOTE" in note for note in notes)


def test_extra_column_is_recorded(tmp_path):
    path = tmp_path / "two_cols.csv"
    path.write_text("tmdb_id,notes\n550,from Adjoa\n", encoding="utf-8")
    ledger = build_ledger(path, expected_id_count=1)
    assert ledger.attrs["extra_columns"] == 1


def test_clean_file_has_no_findings(tmp_path):
    """A file with nothing wrong must produce nothing alarming."""
    path = tmp_path / "clean.csv"
    path.write_text("tmdb_id\n550\n155\n603\n", encoding="utf-8")
    ledger = build_ledger(path, expected_id_count=3)
    assert assert_ledger(ledger) == []
    assert (ledger.loc[ledger["status"] != "header_row", "status"] == "parsed").all()
