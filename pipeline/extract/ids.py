"""The candidate list: one ledger row per source row, forever.

Rows are never dropped. A row that cannot be used gets a status and a reason
instead, which is how "127 received, 112 analysed, here is the rest" is proved
rather than remembered.

The file is read as text and nothing else. Letting pandas infer dtypes on a
column of ids is how `550` becomes `550.0` — one blank row anywhere forces the
column to float64, because NaN cannot live in an int column — and the failure
then surfaces three stages later as a 404 from the API. See ADR-004.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


# ===========================================================================
# The candidate list: one row per source row, forever
# (was src/streamvault/ingest.py)
# ===========================================================================

# ---------------------------------------------------------------------------
# What a TMDb movie id looks like, and what the near-misses look like.
# ---------------------------------------------------------------------------
TMDB_ID_RE = re.compile(r"^\d+$")              # 550


IMDB_ID_RE = re.compile(r"^tt\d+$", re.I)      # tt0468569 — wrong namespace


FLOAT_LIKE_RE = re.compile(r"^\d+\.0+$")       # 550.0 — a dtype accident upstream


# Values that are a header, not data. Three sources merged over four years
# means a header can survive into the middle of the file.
HEADER_VALUES = frozenset({
    "id", "ids", "movie_id", "movie_ids", "tmdb_id", "tmdb ids", "tmdb id",
    "film_id", "title_id", "movie id", "movieid", "tmdbid",
})


# A human's way of writing "no data". Each is a real value to pandas, which is
# why none of them would ever show up in a null count.
SENTINEL_VALUES = frozenset({
    "-1", "0", "n/a", "na", "#n/a", "null", "none", "nil", "nan",
    "tbc", "tbd", "unknown", "?", "-", "--", "missing",
})


LEDGER_COLUMNS = [
    "source_row", "raw_value", "tmdb_id", "status", "reason", "in_money_metrics",
]


# Read the ledger back with these, never with inference. The written CSV holds
# `155`, but pandas reading it unaided returns `155.0`, because the column also
# holds the blanks belonging to rows that have no id — the blank row, the
# placeholders, the header. That is this module's entire reason for existing,
# undone at the file boundary, so load_ledger below is not optional politeness.
LEDGER_DTYPES = {
    "source_row": "Int64",
    "raw_value": "str",
    "tmdb_id": "Int64",
    "status": "str",
    "reason": "str",
    "in_money_metrics": "boolean",
}


# Statuses a row can carry leaving stage 1. Later stages add not_found_404,
# not_released, analysed and excluded_<reason>.
STATUS_PARSED = "parsed"


STATUS_DUPLICATE = "duplicate"


STATUS_INVALID = "invalid_id"


STATUS_HEADER = "header_row"


def read_raw_rows(path: Path) -> pd.DataFrame:
    """Read the file as text and nothing else. One row out per row in.

    dtype=str            explicit dtype; pandas infers nothing
    na_filter=False      "" stays "", never becomes NaN, never forces float64
    keep_default_na=False  belt and braces: "N/A" and "NULL" stay as text so we
                         classify them ourselves rather than having pandas
                         silently agree they are missing
    header=None          we decide what counts as a header, in classify_value
    skip_blank_lines=False  a blank line is a row we must account for
    encoding utf-8-sig   strips a byte-order mark if the file has one
    """
    read_kwargs = dict(
        dtype=str,
        na_filter=False,
        keep_default_na=False,
        header=None,
        skip_blank_lines=False,
    )
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig", **read_kwargs)
    except UnicodeDecodeError:
        # A file exported by an older Windows tool may not be UTF-8. Fall back,
        # but record it: it is a finding about the source, not a detail.
        frame = pd.read_csv(path, encoding="latin-1", **read_kwargs)
        frame.attrs["encoding_fallback"] = "latin-1"

    if frame.shape[1] != 1:
        # The brief says one column. More means the file is not what we were
        # told, which belongs in the diagnosis.
        frame.attrs["extra_columns"] = frame.shape[1] - 1

    return frame


def normalise_cell(raw: str) -> str:
    """Strip the invisible junk a spreadsheet leaves behind, then the quotes.

    Written with escapes rather than the characters themselves so that the
    thing being removed is visible to whoever reads this next: ﻿ is a
    byte-order mark,   a non-breaking space. Both render as nothing or as
    an ordinary space, which is exactly why they cost hours.
    """
    return (
        raw.replace("﻿", "")
        .replace(" ", " ")
        .strip()
        .strip('"')
        .strip("'")
        .strip()
    )


def classify_value(raw: str) -> tuple[int | None, str, str]:
    """Classify one raw cell. Returns (tmdb_id, status, reason).

    Order matters. Sentinels are checked before the digits pattern so that a
    bare "0" is reported as a placeholder rather than as a valid id, and the
    IMDb check comes before the catch-all so the reason names what it actually
    is instead of calling it unparseable.
    """
    text = normalise_cell(raw)

    if text == "":
        return None, STATUS_INVALID, "blank row"

    if text.lower() in HEADER_VALUES:
        return None, STATUS_HEADER, f"header value {text!r} in the data"

    if text.lower() in SENTINEL_VALUES:
        return None, STATUS_INVALID, f"placeholder {text!r} — a human's 'no data'"

    if IMDB_ID_RE.match(text):
        return None, STATUS_INVALID, (
            f"IMDb id {text!r}, not a TMDb id — resolvable via /find, "
            "but check it is not already on the list under its TMDb id"
        )

    if FLOAT_LIKE_RE.match(text):
        # 550.0 is near-certainly 550 that passed through a float column
        # somewhere upstream. Recovering it is a judgement call; see the
        # decision log. The recovered id is verifiable: if it is wrong, TMDb
        # either 404s or returns a film whose title does not fit the list.
        return int(float(text)), STATUS_PARSED, f"float-formatted {text!r}, recovered as integer"

    if TMDB_ID_RE.match(text):
        value = int(text)
        if value == 0:
            return None, STATUS_INVALID, "id 0 is not a valid TMDb id"
        return value, STATUS_PARSED, ""

    return None, STATUS_INVALID, f"unparseable value {text!r}"


def build_ledger(path: Path, expected_id_count: int) -> pd.DataFrame:
    """Build the id ledger. One row per source row. Nothing is ever dropped."""
    raw = read_raw_rows(path)
    values = raw.iloc[:, 0].astype(str)

    classified = [classify_value(value) for value in values]
    ledger = pd.DataFrame(
        {
            "source_row": range(1, len(values) + 1),   # 1-based, matching an editor
            "raw_value": values.to_numpy(),
            "tmdb_id": pd.array([item[0] for item in classified], dtype="Int64"),
            "status": [item[1] for item in classified],
            "reason": [item[2] for item in classified],
        }
    )
    ledger["in_money_metrics"] = pd.NA   # decided at stage 6, not here

    # --- duplicates: keep the first occurrence, flag every later one --------
    is_dup = ledger["tmdb_id"].notna() & ledger["tmdb_id"].duplicated(keep="first")
    if is_dup.any():
        first_rows = (
            ledger.loc[ledger["tmdb_id"].notna()]
            .drop_duplicates("tmdb_id")
            .set_index("tmdb_id")["source_row"]
        )
        ledger.loc[is_dup, "status"] = STATUS_DUPLICATE
        ledger.loc[is_dup, "reason"] = [
            f"same id as source_row {first_rows[value]}"
            for value in ledger.loc[is_dup, "tmdb_id"]
        ]

    ledger.attrs["file_rows"] = int(len(ledger))
    ledger.attrs["header_rows"] = int((ledger["status"] == STATUS_HEADER).sum())
    ledger.attrs["data_rows"] = ledger.attrs["file_rows"] - ledger.attrs["header_rows"]
    ledger.attrs["expected_id_count"] = int(expected_id_count)
    ledger.attrs["unique_ids_to_fetch"] = int((ledger["status"] == STATUS_PARSED).sum())
    if "extra_columns" in raw.attrs:
        ledger.attrs["extra_columns"] = raw.attrs["extra_columns"]
    if "encoding_fallback" in raw.attrs:
        ledger.attrs["encoding_fallback"] = raw.attrs["encoding_fallback"]
    return ledger


def reconciliation_summary(ledger: pd.DataFrame) -> pd.DataFrame:
    """Status counts over the data rows. These must add to data_rows exactly."""
    data = ledger.loc[ledger["status"] != STATUS_HEADER]
    counts = data["status"].value_counts()
    return counts.rename_axis("status").reset_index(name="rows")


def assert_ledger(ledger: pd.DataFrame) -> list[str]:
    """Assertions that must hold before we spend a single API call.

    Returns the notes worth printing and recording. Hard-asserts what is
    logically required; reports rather than crashes on what is merely
    different from what the brief claimed.
    """
    notes: list[str] = []
    data_rows = ledger.attrs["data_rows"]
    expected = ledger.attrs["expected_id_count"]

    # 1. No row has gone missing.
    assert len(ledger) == ledger.attrs["file_rows"], "ledger lost a row"

    # 2. What we will actually fetch is unique. If this fails we would pay for
    #    the same film twice and double-count it in every KPI downstream.
    to_fetch = ledger.loc[ledger["status"] == STATUS_PARSED, "tmdb_id"]
    assert to_fetch.is_unique, "ids queued for fetching are not unique"
    assert to_fetch.notna().all(), "a parsed row has no id"

    # 3. The counts reconcile. This is the arithmetic the memo quotes.
    counted = int(reconciliation_summary(ledger)["rows"].sum())
    assert counted == data_rows, (
        f"status counts ({counted}) do not add up to data rows ({data_rows})"
    )

    # 4. The brief's number is a claim; the file is the evidence. A mismatch is
    #    a finding, not a crash — and next year this list is expected to hold
    #    ~500 titles, so a hard assert here would break Adjoa's run for being
    #    correct. expected_id_count lives in settings.toml for exactly that.
    if data_rows != expected:
        notes.append(
            f"RECONCILIATION NOTE: the brief says {expected} titles, the file has "
            f"{data_rows} data rows. Recorded as a diagnosis finding; all "
            f"reconciliation below is against {data_rows}."
        )

    if "extra_columns" in ledger.attrs:
        notes.append(
            f"NOTE: the file has {ledger.attrs['extra_columns']} column(s) beyond the "
            "single column of ids the brief describes. Only the first was read."
        )
    if "encoding_fallback" in ledger.attrs:
        notes.append(
            f"NOTE: the file is not valid UTF-8; read as "
            f"{ledger.attrs['encoding_fallback']}. Check for mangled characters."
        )
    return notes


def save_ledger(ledger: pd.DataFrame, path: Path) -> None:
    """Write the ledger. The one artefact stage 1 must leave behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(path, index=False)


def load_ledger(path: Path) -> pd.DataFrame:
    """Read the ledger back with explicit dtypes, never by inference.

    Use this everywhere — later stages, the notebook, the spot-check. A plain
    `pd.read_csv` on this file returns `tmdb_id` as float64, and every id then
    carries a `.0` that 404s against the API. The round trip is tested, because
    an artefact that silently degrades on the way back in is a worse fault than
    one that never existed: the numbers still look right.

    `reason` is read as a string and empty reasons come back as NA, so it is
    filled: "no reason recorded" and "nothing to report" are different facts,
    and only rows that failed should carry text.
    """
    ledger = pd.read_csv(path, dtype=LEDGER_DTYPES, keep_default_na=True)
    ledger["reason"] = ledger["reason"].fillna("")
    return ledger


def load_id_list(path: Path, expected_id_count: int) -> tuple[pd.DataFrame, list[int]]:
    """Read the candidate list. Returns (ledger, the unique ids to fetch)."""
    ledger = build_ledger(path, expected_id_count)
    for note in assert_ledger(ledger):
        print(f"[extract] {note}")
    ids = ledger.loc[ledger["status"] == STATUS_PARSED, "tmdb_id"].astype(int).tolist()
    return ledger, ids
