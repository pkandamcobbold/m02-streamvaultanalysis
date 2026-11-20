"""Tests for the extract stage: the candidate list, the fetch, the shaping.

Three sections, one per job the stage does. What they have in common is that
every fault they pin is one that **does not raise**: an id read as a float,
a duplicate counted twice, a half-written cache entry, a film that loses its
row because it had no cast. Each of those produces a plausible wrong number
rather than an error, which is why they are worth a test each.
"""
from __future__ import annotations

import json
import pytest
import time

import pandas as pd

from pipeline.config import Settings
from pipeline.extract import (
    CAST_COLUMNS,
    CREW_COLUMNS,
    ENDPOINT_CREDITS,
    ENDPOINT_DETAILS,
    ENDPOINT_DETAILS_CREDITS,
    FILM_COLUMNS,
    RateLimiter,
    STATUS_CROSS_NAMESPACE_DUPLICATE,
    STATUS_FETCHED,
    STATUS_NOT_FOUND,
    add_franchise_flags,
    apply_to_ledger,
    assert_fetch,
    assert_grains,
    assert_ledger,
    build_cast,
    build_crew,
    build_films,
    build_genres,
    build_ledger,
    build_session,
    cache_path,
    classify_value,
    context_from_settings,
    fetch_all,
    fetch_film,
    fetch_one,
    find_by_external_id,
    load_fetch_log,
    load_ledger,
    load_payloads,
    movie_ids_from_find,
    reconciliation_summary,
    request_path_for,
    resolve_foreign_ids,
    save_fetch_log,
    save_ledger,
)

# ==========================================================================
# Reading the id list: one row per source row, forever
# ==========================================================================

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


def test_count_mismatch_is_a_note_not_a_crash(messy_file):
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


# --------------------------------------------------------------------------
# The artefact round trip — the file boundary is where the guarantee leaks
# --------------------------------------------------------------------------

def test_ledger_round_trips_without_floating_the_ids(messy_file, tmp_path):
    """Writing it right is half the job; reading it back is the other half.

    A plain pd.read_csv on this file returns tmdb_id as float64, because the
    column also holds the blanks belonging to rows with no id. Every id would
    then carry a .0 and 404 against the API — this module's whole purpose,
    undone one line after it succeeded.
    """
    ledger = build_ledger(messy_file, expected_id_count=8)
    path = tmp_path / "id_ledger.csv"
    save_ledger(ledger, path)

    naive = pd.read_csv(path)
    assert str(naive["tmdb_id"].dtype) == "float64", (
        "if this ever fails, pandas changed and load_ledger may be redundant"
    )

    back = load_ledger(path)
    assert str(back["tmdb_id"].dtype) == "Int64"
    assert back.loc[back["status"] == "parsed", "tmdb_id"].tolist() == [155, 550, 603]
    assert back["status"].tolist() == ledger["status"].tolist()
    assert len(back) == len(ledger)


def test_round_trip_keeps_reasons_as_text_not_missing(messy_file, tmp_path):
    """An empty reason means "nothing to report", not "no reason recorded"."""
    ledger = build_ledger(messy_file, expected_id_count=8)
    path = tmp_path / "id_ledger.csv"
    save_ledger(ledger, path)
    back = load_ledger(path)

    assert back["reason"].notna().all()
    unusable = back.loc[back["status"].isin(["invalid_id", "duplicate"])]
    assert (unusable["reason"].str.len() > 0).all()
    assert (back.loc[back["status"] == "parsed", "reason"] == "").any()

# ==========================================================================
# Fetching: caching, retries, rate limiting and the 404 contract
# ==========================================================================

FAKE_TOKEN = "eyJ-this-is-not-a-real-token-only-its-shape"


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code: int, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if self._payload is None:
            raise ValueError("no JSON body")
        return self._payload


class FakeSession:
    """Records every call. Routes on the path, so params stay assertable."""

    def __init__(self, routes: dict[str, FakeResponse] | None = None,
                 default: FakeResponse | None = None) -> None:
        self.routes = routes or {}
        self.default = default or FakeResponse(200, {"id": 0, "title": "Default"})
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, params=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "params": params or {}, "timeout": timeout})
        for path, response in self.routes.items():
            if url.endswith(path):
                return response
        return self.default

    @property
    def urls(self) -> list[str]:
        return [str(call["url"]) for call in self.calls]


def film_payload(tmdb_id: int = 550, with_credits: bool = True,
                 n_cast: int = 3, n_crew: int = 2) -> dict:
    payload: dict = {
        "id": tmdb_id,
        "title": "Test Film",
        "release_date": "1999-10-15",
        "budget": 63_000_000,
        "revenue": 100_853_753,
        "belongs_to_collection": None,
    }
    if with_credits:
        payload["credits"] = {
            "cast": [{"id": i, "name": f"Actor {i}", "order": i} for i in range(n_cast)],
            "crew": [{"id": i, "job": "Director"} for i in range(n_crew)],
        }
    return payload


@pytest.fixture
def settings(tmp_path):
    """Real Settings, rooted at tmp_path so no test writes into data/raw."""
    return Settings(
        raw={
            "paths": {
                "raw_dir": "data/raw",
                "interim_dir": "data/interim",
                "processed_dir": "data/processed",
            },
            "api": {
                "base_url": "https://api.themoviedb.org/3",
                "timeout_seconds": 10,
                "max_retries": 5,
                "backoff_factor": 0.5,
                "min_seconds_between_calls": 0.0,   # tests must not sleep
                "append_credits": True,
                "progress_every": 25,
            },
        },
        root=tmp_path,
    )


@pytest.fixture
def ctx(settings):
    return context_from_settings(settings)


@pytest.fixture
def no_wait():
    return RateLimiter(0.0)


# --------------------------------------------------------------------------
# The envelope: what gets written to disk
# --------------------------------------------------------------------------

def test_envelope_records_status_path_and_time(tmp_path, no_wait):
    session = FakeSession(default=FakeResponse(200, film_payload()))
    envelope, from_cache = fetch_one(
        session, "https://api.themoviedb.org/3", tmp_path, no_wait,
        550, ENDPOINT_DETAILS, timeout=10,
    )
    assert from_cache is False
    assert envelope["http_status"] == 200
    assert envelope["request_path"] == "/movie/550"
    assert envelope["fetched_at"].endswith("+00:00")   # UTC, and says so
    assert envelope["payload"]["title"] == "Test Film"


def test_every_call_carries_a_timeout(tmp_path, no_wait):
    """A request without a timeout can hang forever. There is no 'usually'."""
    session = FakeSession(default=FakeResponse(200, film_payload()))
    fetch_one(session, "https://x", tmp_path, no_wait, 550, ENDPOINT_DETAILS, timeout=7)
    assert session.calls[0]["timeout"] == 7


def test_request_path_for_rejects_an_unknown_endpoint():
    assert request_path_for(550, ENDPOINT_DETAILS) == "/movie/550"
    assert request_path_for(550, ENDPOINT_CREDITS) == "/movie/550/credits"
    with pytest.raises(ValueError):
        request_path_for(550, "reviews")


# --------------------------------------------------------------------------
# The token: in a header, nowhere else, ever
# --------------------------------------------------------------------------

def test_token_goes_in_a_header_not_a_url():
    session = build_session(FAKE_TOKEN, max_retries=5, backoff_factor=0.5)
    assert session.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"


def test_token_never_reaches_the_url_or_the_cache_file(tmp_path, no_wait):
    """The v4-token decision (ADR-001) is only worth anything if this holds."""
    session = FakeSession(default=FakeResponse(200, film_payload()))
    fetch_one(session, "https://api.themoviedb.org/3", tmp_path, no_wait,
              550, ENDPOINT_DETAILS, timeout=10)

    assert all(FAKE_TOKEN not in url for url in session.urls)
    assert all("api_key" not in url for url in session.urls)

    written = cache_path(tmp_path, 550, ENDPOINT_DETAILS).read_text(encoding="utf-8")
    assert "Bearer" not in written
    assert FAKE_TOKEN not in written
    assert "Authorization" not in written


# --------------------------------------------------------------------------
# The cache: fetch once, resume for free
# --------------------------------------------------------------------------

def test_second_call_reads_the_cache_and_makes_no_request(tmp_path, no_wait):
    session = FakeSession(default=FakeResponse(200, film_payload()))
    args = (session, "https://x", tmp_path, no_wait, 550, ENDPOINT_DETAILS)
    fetch_one(*args, timeout=10)
    first, _ = fetch_one(*args, timeout=10)
    second, from_cache = fetch_one(*args, timeout=10)

    assert len(session.calls) == 1, "the cached call went to the network"
    assert from_cache is True
    assert second["fetched_at"] == first["fetched_at"], "cache rewrote the as-of date"


def test_force_refetches(tmp_path, no_wait):
    session = FakeSession(default=FakeResponse(200, film_payload()))
    args = (session, "https://x", tmp_path, no_wait, 550, ENDPOINT_DETAILS)
    fetch_one(*args, timeout=10)
    _, from_cache = fetch_one(*args, timeout=10, force=True)
    assert len(session.calls) == 2
    assert from_cache is False


def test_the_envelope_names_the_id_it_actually_holds(tmp_path, no_wait):
    """`tmdb_id` holding "tt0468569" was a field name that lied."""
    session = FakeSession(default=FakeResponse(200, film_payload()))
    movie, _ = fetch_one(session, "https://x", tmp_path, no_wait, 550,
                         ENDPOINT_DETAILS, timeout=10)
    found, _ = find_by_external_id(session, "https://x", tmp_path, no_wait,
                                   "tt0468569", timeout=10)

    assert (movie["requested_id"], movie["id_namespace"]) == (550, "tmdb")
    assert (found["requested_id"], found["id_namespace"]) == ("tt0468569", "imdb_id")
    assert "tmdb_id" not in found


def test_a_corrupt_cache_entry_is_refetched_not_raised(tmp_path, no_wait):
    """A run interrupted mid-write used to poison the cache permanently.

    The old behaviour was a JSONDecodeError naming neither the film nor the
    remedy, on this run and every run after it, because nothing ever rewrote
    the bad file.
    """
    session = FakeSession(default=FakeResponse(200, film_payload()))
    args = (session, "https://x", tmp_path, no_wait, 550, ENDPOINT_DETAILS)
    fetch_one(*args, timeout=10)

    path = cache_path(tmp_path, 550, ENDPOINT_DETAILS)
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: len(text) // 2], encoding="utf-8")   # half-written

    envelope, from_cache = fetch_one(*args, timeout=10)

    assert from_cache is False, "the truncated file was served as a cache hit"
    assert envelope["payload"]["title"] == "Test Film"
    assert len(session.calls) == 2
    assert json.loads(path.read_text(encoding="utf-8"))["http_status"] == 200


def test_a_corrupt_entry_is_reported_as_a_note(settings):
    session = FakeSession(default=FakeResponse(200, film_payload()))
    fetch_all([550], settings, session_factory=lambda: session, progress=None)

    path = cache_path(settings.path("data/raw"), 550, ENDPOINT_DETAILS_CREDITS)
    path.write_text("{ truncated", encoding="utf-8")

    log = fetch_all([550], settings, session_factory=lambda: session, progress=None)
    notes = assert_fetch(log, [550])

    assert log.attrs["corrupt_cache"] == [path.name]
    assert any("could not be read" in note for note in notes)


def test_an_interrupted_write_leaves_no_partial_file(tmp_path, no_wait):
    """os.replace means a reader sees the whole old file or the whole new one."""
    class Boom(FakeSession):
        def get(self, *args, **kwargs):
            raise KeyboardInterrupt("Ctrl-C mid-fetch")

    with pytest.raises(KeyboardInterrupt):
        fetch_one(Boom(), "https://x", tmp_path, no_wait, 550,
                  ENDPOINT_DETAILS, timeout=10)

    assert not cache_path(tmp_path, 550, ENDPOINT_DETAILS).exists()
    assert list(tmp_path.glob("*.tmp")) == [], "a temp file was left behind"


def test_the_fetch_log_round_trips_without_floating_the_counts(settings, tmp_path):
    """Reading the artefact back must not undo what writing it got right."""
    session = FakeSession(routes={
        "/movie/155": FakeResponse(404),
    }, default=FakeResponse(200, film_payload()))
    log = fetch_all([550, 155], settings, session_factory=lambda: session,
                    progress=None)

    path = tmp_path / "fetch_log.csv"
    save_fetch_log(log, path)
    back = load_fetch_log(path)

    assert str(back["tmdb_id"].dtype) == "Int64"
    assert str(back["n_cast"].dtype) == "Int64"
    assert str(back["http_status"].dtype) == "Int64"
    assert back.loc[back["tmdb_id"] == 550, "n_cast"].item() == 3
    assert pd.isna(back.loc[back["tmdb_id"] == 155, "n_cast"].item())
    assert back["tmdb_id"].tolist() == log["tmdb_id"].tolist()


def test_from_cache_is_not_written_to_disk(tmp_path, no_wait):
    """It describes this run, not the response. On disk it would be a lie."""
    session = FakeSession(default=FakeResponse(200, film_payload()))
    fetch_one(session, "https://x", tmp_path, no_wait, 550, ENDPOINT_DETAILS, timeout=10)
    on_disk = json.loads(cache_path(tmp_path, 550, ENDPOINT_DETAILS).read_text())
    assert "from_cache" not in on_disk


# --------------------------------------------------------------------------
# 404: an answer, not a failure
# --------------------------------------------------------------------------

def test_404_is_recorded_not_raised(tmp_path, no_wait):
    session = FakeSession(default=FakeResponse(404))
    envelope, _ = fetch_one(session, "https://x", tmp_path, no_wait,
                            999_999_999, ENDPOINT_DETAILS, timeout=10)
    assert envelope["http_status"] == 404
    assert envelope["payload"] is None
    assert cache_path(tmp_path, 999_999_999, ENDPOINT_DETAILS).exists(), (
        "a 404 must be cached too, or every rerun asks again"
    )


def test_404_is_not_retried():
    """Retrying a missing film five times is rude and changes nothing."""
    session = build_session(FAKE_TOKEN, max_retries=5, backoff_factor=0.5)
    retry = session.get_adapter("https://api.themoviedb.org").max_retries
    assert 404 not in retry.status_forcelist
    assert 429 in retry.status_forcelist, "rate limiting is exactly what to retry"
    assert set(retry.status_forcelist) >= {500, 502, 503, 504}


def test_retry_policy_waits_as_the_server_asks():
    session = build_session(FAKE_TOKEN, max_retries=5, backoff_factor=0.5)
    retry = session.get_adapter("https://api.themoviedb.org").max_retries
    assert retry.respect_retry_after_header is True
    assert retry.total == 5
    assert retry.backoff_factor == 0.5
    assert retry.raise_on_status is False, "we classify the status, urllib3 does not"


# --------------------------------------------------------------------------
# Pacing
# --------------------------------------------------------------------------

def test_rate_limiter_enforces_the_minimum_gap():
    limiter = RateLimiter(0.05)
    started = time.monotonic()
    limiter.wait()
    limiter.wait()
    assert time.monotonic() - started >= 0.05


def test_rate_limiter_does_not_delay_the_very_first_call():
    limiter = RateLimiter(5.0)
    started = time.monotonic()
    limiter.wait()
    assert time.monotonic() - started < 1.0


# --------------------------------------------------------------------------
# One call per film, or two — and the cache keys that keep them apart
# --------------------------------------------------------------------------

def test_append_mode_makes_one_call_per_film(ctx):
    session = FakeSession(default=FakeResponse(200, film_payload()))
    row = fetch_film(session, ctx, 550)

    assert len(session.calls) == 1
    assert session.calls[0]["params"] == {"append_to_response": "credits"}
    assert row["calls_made"] == 1
    assert row["has_credits"] is True
    assert (row["n_cast"], row["n_crew"]) == (3, 2)


def test_two_call_mode_makes_two_calls(ctx):
    ctx.append_credits = False
    session = FakeSession(routes={
        "/movie/550/credits": FakeResponse(200, {"cast": [{"id": 1}], "crew": []}),
        "/movie/550": FakeResponse(200, film_payload(with_credits=False)),
    })
    row = fetch_film(session, ctx, 550)

    assert len(session.calls) == 2
    assert row["calls_made"] == 2
    assert row["has_credits"] is True
    assert (row["n_cast"], row["n_crew"]) == (1, 0)


def test_toggling_append_does_not_serve_a_credit_less_cache(ctx, tmp_path):
    """The flag changes what is requested, so it must change where it is cached.

    Otherwise switching api.append_credits reads a file fetched under the other
    policy, and the fetcher reports credits it never received.
    """
    ctx.append_credits = False
    session = FakeSession(default=FakeResponse(200, film_payload(with_credits=False)))
    fetch_film(session, ctx, 550)

    assert cache_path(ctx.raw_dir, 550, ENDPOINT_DETAILS).exists()
    assert not cache_path(ctx.raw_dir, 550, ENDPOINT_DETAILS_CREDITS).exists()

    ctx.append_credits = True
    fresh = FakeSession(default=FakeResponse(200, film_payload()))
    row = fetch_film(fresh, ctx, 550)

    assert len(fresh.calls) == 1, "the appended request was served from the plain cache"
    assert row["has_credits"] is True


def test_404_in_two_call_mode_skips_the_credits_call(ctx):
    ctx.append_credits = False
    session = FakeSession(default=FakeResponse(404))
    row = fetch_film(session, ctx, 999_999_999)

    assert len(session.calls) == 1, "asked for the credits of a film that does not exist"
    assert row["http_status"] == 404
    assert row["has_credits"] is False


# --------------------------------------------------------------------------
# A missing credits block is not an empty cast list
# --------------------------------------------------------------------------

def test_no_credits_block_is_distinct_from_an_empty_cast(ctx):
    """One means we cannot see the cast; the other means there isn't one."""
    session = FakeSession(default=FakeResponse(200, film_payload(with_credits=False)))
    absent = fetch_film(session, ctx, 1)

    empty = film_payload(tmdb_id=2)
    empty["credits"] = {"cast": [], "crew": []}
    other = fetch_film(FakeSession(default=FakeResponse(200, empty)), ctx, 2)

    assert absent["has_credits"] is False and absent["n_cast"] is None
    assert other["has_credits"] is True and other["n_cast"] == 0


# --------------------------------------------------------------------------
# The fetch log
# --------------------------------------------------------------------------

def test_fetch_log_has_one_row_per_id(settings):
    session = FakeSession(default=FakeResponse(200, film_payload()))
    log = fetch_all([550, 155, 603], settings, session_factory=lambda: session,
                    progress=None)
    assert len(log) == 3
    assert log["tmdb_id"].tolist() == [550, 155, 603]
    assert log.attrs["calls_made"] == 3


def test_counts_stay_integer_when_a_film_has_no_credits(settings):
    """The stage-1 lesson, again: one missing value must not float the column."""
    session = FakeSession(routes={
        "/movie/155": FakeResponse(200, film_payload(155, with_credits=False)),
    }, default=FakeResponse(200, film_payload()))
    log = fetch_all([550, 155], settings, session_factory=lambda: session, progress=None)

    assert str(log["n_cast"].dtype) == "Int64"
    assert str(log["http_status"].dtype) == "Int64"
    assert log.loc[log["tmdb_id"] == 550, "n_cast"].item() == 3
    assert pd.isna(log.loc[log["tmdb_id"] == 155, "n_cast"].item())


def test_a_second_run_is_all_cache_and_costs_no_calls(settings):
    session = FakeSession(default=FakeResponse(200, film_payload()))
    fetch_all([550, 155], settings, session_factory=lambda: session, progress=None)
    again = fetch_all([550, 155], settings, session_factory=lambda: session,
                      progress=None)

    assert len(session.calls) == 2, "the second run went back to the network"
    assert again["from_cache"].all()
    assert again.attrs["calls_made"] == 0


def test_a_fully_cached_run_needs_neither_token_nor_network(settings):
    """Why the session is built lazily: a rerun in a meeting, offline."""
    session = FakeSession(default=FakeResponse(200, film_payload()))
    fetch_all([550], settings, session_factory=lambda: session, progress=None)

    def explode():
        raise AssertionError("built a session for a run with nothing to fetch")

    log = fetch_all([550], settings, session_factory=explode, progress=None)
    assert log["from_cache"].all()


# --------------------------------------------------------------------------
# assert_fetch — hard on what is required, soft on what is a finding
# --------------------------------------------------------------------------

def test_a_404_is_reported_as_a_note_not_a_crash(settings):
    session = FakeSession(routes={"/movie/999": FakeResponse(404)},
                          default=FakeResponse(200, film_payload()))
    log = fetch_all([550, 999], settings, session_factory=lambda: session, progress=None)
    notes = assert_fetch(log, [550, 999])

    assert any("404" in note and "999" in note for note in notes)


def test_a_missing_credits_block_is_reported(settings):
    session = FakeSession(default=FakeResponse(200, film_payload(with_credits=False)))
    log = fetch_all([550], settings, session_factory=lambda: session, progress=None)
    notes = assert_fetch(log, [550])

    assert any("without credits" in note for note in notes)


def test_a_clean_fetch_produces_no_notes(settings):
    session = FakeSession(default=FakeResponse(200, film_payload()))
    log = fetch_all([550, 155], settings, session_factory=lambda: session, progress=None)
    assert assert_fetch(log, [550, 155]) == []


def test_a_log_missing_a_row_is_a_hard_failure(settings):
    """A denominator that silently shrinks is the one thing not to be lenient about."""
    session = FakeSession(default=FakeResponse(200, film_payload()))
    log = fetch_all([550, 155], settings, session_factory=lambda: session, progress=None)
    with pytest.raises(AssertionError):
        assert_fetch(log.iloc[:1], [550, 155])


# --------------------------------------------------------------------------
# Back onto the ledger
# --------------------------------------------------------------------------

@pytest.fixture
def small_ledger(tmp_path):
    path = tmp_path / "ids.csv"
    path.write_bytes(b"tmdb_id\r\n550\r\n155\r\n550\r\nN/A\r\n")
    return build_ledger(path, expected_id_count=3)


def test_ledger_records_fetched_and_404(small_ledger):
    log = pd.DataFrame({
        "tmdb_id": pd.array([550, 155], dtype="Int64"),
        "http_status": pd.array([200, 404], dtype="Int64"),
    })
    updated = apply_to_ledger(small_ledger, log)

    assert updated.loc[updated["tmdb_id"] == 550, "status"].iloc[0] == STATUS_FETCHED
    assert updated.loc[updated["tmdb_id"] == 155, "status"].iloc[0] == STATUS_NOT_FOUND
    assert "404" in updated.loc[updated["tmdb_id"] == 155, "reason"].iloc[0]


def test_ledger_rows_never_queued_are_left_alone(small_ledger):
    """The duplicate and the placeholder keep stage 1's verdict and its reason."""
    log = pd.DataFrame({
        "tmdb_id": pd.array([550, 155], dtype="Int64"),
        "http_status": pd.array([200, 200], dtype="Int64"),
    })
    updated = apply_to_ledger(small_ledger, log)
    by_row = updated.set_index("source_row")

    assert by_row.loc[4, "status"] == "duplicate"
    assert "source_row 2" in by_row.loc[4, "reason"]
    assert by_row.loc[5, "status"] == "invalid_id"
    assert len(updated) == len(small_ledger), "the ledger lost a row at stage 2"


def test_ledger_still_accounts_for_every_source_row(small_ledger):
    log = pd.DataFrame({
        "tmdb_id": pd.array([550, 155], dtype="Int64"),
        "http_status": pd.array([200, 404], dtype="Int64"),
    })
    updated = apply_to_ledger(small_ledger, log)
    data_rows = updated.loc[updated["status"] != "header_row"]
    assert int(data_rows["status"].value_counts().sum()) == small_ledger.attrs["data_rows"]


# --------------------------------------------------------------------------
# F-09: the IMDb id in row 95
# --------------------------------------------------------------------------

def test_find_resolves_an_imdb_id_and_caches_it(tmp_path, no_wait):
    session = FakeSession(default=FakeResponse(200, {
        "movie_results": [{"id": 155, "title": "The Dark Knight"}],
        "tv_results": [],
    }))
    envelope, from_cache = find_by_external_id(
        session, "https://api.themoviedb.org/3", tmp_path, no_wait,
        "tt0468569", timeout=10,
    )

    assert from_cache is False
    assert envelope["request_path"] == "/find/tt0468569"
    assert session.calls[0]["params"] == {"external_source": "imdb_id"}
    assert movie_ids_from_find(envelope) == [155]

    _, again = find_by_external_id(
        session, "https://api.themoviedb.org/3", tmp_path, no_wait,
        "tt0468569", timeout=10,
    )
    assert again is True and len(session.calls) == 1


def test_an_imdb_id_already_on_the_list_is_excluded_not_recovered(settings, tmp_path):
    """The real case. tt0468569 resolves to 155, which is on the list twice.

    The obvious fix recovers the film. The correct answer excludes it, because
    recovering it would be a third copy of one film inside a franchise.
    """
    path = tmp_path / "ids.csv"
    path.write_bytes(b"tmdb_id\r\n155\r\n550\r\ntt0468569\r\n155\r\n")
    ledger = build_ledger(path, expected_id_count=3)

    session = FakeSession(default=FakeResponse(200, {
        "movie_results": [{"id": 155, "title": "The Dark Knight"}],
    }))
    updated, findings = resolve_foreign_ids(
        ledger, settings, session_factory=lambda: session
    )
    row = updated.set_index("source_row").loc[4]

    assert row["status"] == STATUS_CROSS_NAMESPACE_DUPLICATE
    assert pd.isna(row["tmdb_id"]), "the film was recovered and will be counted twice"
    assert "source_row 2" in row["reason"]
    assert any("double-counted" in finding for finding in findings)
    assert updated.loc[updated["status"] == "parsed", "tmdb_id"].tolist() == [155, 550]


def test_an_imdb_id_not_otherwise_on_the_list_is_recovered(settings, tmp_path):
    path = tmp_path / "ids.csv"
    path.write_bytes(b"tmdb_id\r\n550\r\ntt0133093\r\n")
    ledger = build_ledger(path, expected_id_count=2)

    session = FakeSession(default=FakeResponse(200, {
        "movie_results": [{"id": 603, "title": "The Matrix"}],
    }))
    updated, findings = resolve_foreign_ids(
        ledger, settings, session_factory=lambda: session
    )
    row = updated.set_index("source_row").loc[3]

    assert row["status"] == "parsed"
    assert row["tmdb_id"] == 603
    assert "spot-check" in row["reason"]
    assert str(updated["tmdb_id"].dtype) == "Int64", "recovery floated the id column"
    assert any("NOT otherwise on the list" in finding for finding in findings)


def test_an_imdb_id_matching_nothing_stays_unusable(settings, tmp_path):
    path = tmp_path / "ids.csv"
    path.write_bytes(b"tmdb_id\r\n550\r\ntt9999999\r\n")
    ledger = build_ledger(path, expected_id_count=2)

    session = FakeSession(default=FakeResponse(200, {"movie_results": []}))
    updated, findings = resolve_foreign_ids(
        ledger, settings, session_factory=lambda: session
    )
    row = updated.set_index("source_row").loc[3]

    assert row["status"] == "invalid_id"
    assert "no film" in row["reason"]
    assert len(findings) == 1


def test_resolution_needs_no_session_when_there_is_no_foreign_id(settings, tmp_path):
    path = tmp_path / "ids.csv"
    path.write_bytes(b"tmdb_id\r\n550\r\n155\r\n")
    ledger = build_ledger(path, expected_id_count=2)

    def explode():
        raise AssertionError("called /find with nothing to resolve")

    updated, findings = resolve_foreign_ids(ledger, settings, session_factory=explode)
    assert findings == []
    assert updated["status"].tolist() == ledger["status"].tolist()


def test_find_that_matches_nothing_returns_no_ids(tmp_path, no_wait):
    session = FakeSession(default=FakeResponse(200, {"movie_results": []}))
    envelope, _ = find_by_external_id(
        session, "https://x", tmp_path, no_wait, "tt0000000", timeout=10,
    )
    assert movie_ids_from_find(envelope) == []


def test_find_on_a_404_returns_no_ids(tmp_path, no_wait):
    session = FakeSession(default=FakeResponse(404))
    envelope, _ = find_by_external_id(
        session, "https://x", tmp_path, no_wait, "tt0000000", timeout=10,
    )
    assert envelope["payload"] is None
    assert movie_ids_from_find(envelope) == []

# ==========================================================================
# Shaping: nested JSON into one table per grain
# ==========================================================================

def film(
    tmdb_id: int = 550,
    title: str = "Fight Club",
    collection: dict | None = None,
    cast: list | None = None,
    crew: list | None = None,
    genres: list | None = None,
    **overrides,
) -> dict:
    """A payload shaped like TMDb's, including the awkward parts."""
    payload = {
        "id": tmdb_id,
        "imdb_id": f"tt{tmdb_id:07d}",
        "title": title,
        "original_title": title,
        "release_date": "1999-10-15",
        "status": "Released",
        "budget": 63_000_000,
        "revenue": 100_853_753,
        "runtime": 139,
        "vote_average": 8.4,
        "vote_count": 27_000,
        "popularity": 61.4,
        "adult": False,
        "video": False,
        "original_language": "en",
        "belongs_to_collection": collection,
        "genres": genres if genres is not None else [{"id": 18, "name": "Drama"}],
        "credits": {
            "cast": cast if cast is not None else [
                {"id": 819, "name": "Edward Norton", "character": "The Narrator",
                 "order": 0, "gender": 2, "known_for_department": "Acting",
                 "popularity": 20.1, "adult": False},
            ],
            "crew": crew if crew is not None else [
                {"id": 7467, "name": "David Fincher", "job": "Director",
                 "department": "Directing", "gender": 2, "popularity": 9.9,
                 "adult": False},
            ],
        },
    }
    payload.update(overrides)
    return payload


IRON_MAN = {"id": 131292, "name": "Iron Man Collection",
            "poster_path": "/x.jpg", "backdrop_path": "/y.jpg"}


# --------------------------------------------------------------------------
# films — one row per film
# --------------------------------------------------------------------------

def test_films_is_one_row_per_film():
    films = build_films([film(550), film(155), film(603)])
    assert len(films) == 3
    assert films["tmdb_id"].is_unique
    assert films["tmdb_id"].tolist() == [155, 550, 603]   # sorted, deterministic


def test_no_column_is_called_id_or_name():
    """The collision that makes a later merge invent id_x and id_y."""
    films = build_films([film(550, collection=IRON_MAN)])
    cast = build_cast([film(550)])
    crew = build_crew([film(550)])
    genres = build_genres([film(550)])

    for table in (films, cast, crew, genres):
        assert "id" not in table.columns
        assert "name" not in table.columns
        assert not any("." in column for column in table.columns)


def test_the_collection_is_flattened_to_two_plain_columns():
    films = build_films([film(1726, collection=IRON_MAN), film(550)])
    by_id = films.set_index("tmdb_id")

    assert by_id.loc[1726, "collection_id"] == 131292
    assert by_id.loc[1726, "collection_name"] == "Iron Man Collection"
    assert pd.isna(by_id.loc[550, "collection_id"])
    assert pd.isna(by_id.loc[550, "collection_name"])


def test_ids_and_money_stay_integers():
    """A film with no runtime must not give every film a decimal point."""
    films = build_films([film(550), film(155, runtime=None, budget=None)])

    assert str(films["tmdb_id"].dtype) == "Int64"
    assert str(films["budget"].dtype) == "Int64"
    assert str(films["runtime"].dtype) == "Int64"
    assert str(films["collection_id"].dtype) == "Int64"
    assert films.loc[films["tmdb_id"] == 550, "budget"].item() == 63_000_000


def test_a_field_tmdb_stops_sending_becomes_an_empty_column():
    """Not a KeyError three stages later."""
    payload = film(550)
    del payload["runtime"]
    films = build_films([payload])

    # release_year is derived here rather than fetched (M4), so it is
    # one column beyond the fields read straight from the payload.
    assert list(films.columns) == FILM_COLUMNS + ["release_year"]
    assert pd.isna(films["runtime"].item())


def test_no_payloads_gives_an_empty_table_not_an_empty_frame():
    films = build_films([])
    # release_year is derived here rather than fetched (M4), so it is
    # one column beyond the fields read straight from the payload.
    assert list(films.columns) == FILM_COLUMNS + ["release_year"]
    assert len(films) == 0
    assert films["budget"].sum() == 0      # would be a KeyError on a bare frame


# --------------------------------------------------------------------------
# cast and crew — one row per credit
# --------------------------------------------------------------------------

def test_cast_is_one_row_per_film_per_member():
    payload = film(550, cast=[
        {"id": 819, "name": "Edward Norton", "character": "Narrator", "order": 0},
        {"id": 287, "name": "Brad Pitt", "character": "Tyler Durden", "order": 1},
    ])
    cast = build_cast([payload, film(155, cast=[
        {"id": 3894, "name": "Christian Bale", "character": "Bruce Wayne", "order": 0},
    ])])

    assert len(cast) == 3
    assert list(cast.columns) == CAST_COLUMNS
    assert cast.loc[cast["person_id"] == 287, "billing_order"].item() == 1
    assert sorted(cast["tmdb_id"].unique()) == [155, 550]


def test_billing_order_zero_is_the_lead_and_survives_as_zero():
    """A falsy value that must not be confused with missing."""
    cast = build_cast([film(550)])
    assert cast["billing_order"].item() == 0
    assert cast["billing_order"].notna().all()


def test_crew_keeps_one_row_per_credit_not_per_person():
    """A writer-director is two credits. Collapsing here would lose a fact."""
    payload = film(550, crew=[
        {"id": 7467, "name": "David Fincher", "job": "Director", "department": "Directing"},
        {"id": 7467, "name": "David Fincher", "job": "Producer", "department": "Production"},
    ])
    crew = build_crew([payload])

    assert len(crew) == 2
    assert list(crew.columns) == CREW_COLUMNS
    assert len(crew.drop_duplicates(["tmdb_id", "person_id"])) == 1
    assert set(crew["job"]) == {"Director", "Producer"}


def test_a_film_with_no_cast_keeps_its_row_in_films():
    """The failure that silently shrinks the film count."""
    payloads = [film(550), film(155, cast=[], crew=[])]
    films, cast, crew = build_films(payloads), build_cast(payloads), build_crew(payloads)

    assert len(films) == 2
    assert set(cast["tmdb_id"]) == {550}
    assert 155 in set(films["tmdb_id"])


def test_a_missing_credits_block_does_not_crash_the_stage():
    """json_normalize with record_path raises here; this must not."""
    payload = film(155)
    del payload["credits"]
    cast = build_cast([film(550), payload])

    assert len(cast) == 1
    assert cast["tmdb_id"].item() == 550


def test_an_absent_cast_field_becomes_na_not_a_crash():
    cast = build_cast([film(550, cast=[{"id": 819, "name": "Edward Norton"}])])
    assert cast["person_id"].item() == 819
    assert pd.isna(cast["character"].item())
    assert pd.isna(cast["billing_order"].item())


# --------------------------------------------------------------------------
# genres
# --------------------------------------------------------------------------

def test_genres_is_one_row_per_film_per_genre():
    genres = build_genres([
        film(550, genres=[{"id": 18, "name": "Drama"}, {"id": 53, "name": "Thriller"}]),
        film(155, genres=[{"id": 28, "name": "Action"}]),
    ])
    assert len(genres) == 3
    assert str(genres["genre_id"].dtype) == "Int64"
    assert set(genres.loc[genres["tmdb_id"] == 550, "genre_name"]) == {"Drama", "Thriller"}


def test_a_film_with_no_genres_is_absent_from_genres_but_not_from_films():
    payloads = [film(550), film(155, genres=[])]
    assert len(build_genres(payloads)) == 1
    assert len(build_films(payloads)) == 2


# --------------------------------------------------------------------------
# grain assertions
# --------------------------------------------------------------------------

def test_a_duplicated_film_row_is_a_hard_failure():
    """It would inflate every median and total, undetectably."""
    films = build_films([film(550), film(550)])
    with pytest.raises(AssertionError, match="more than one row"):
        assert_grains(films, build_cast([]), build_crew([]), build_genres([]))


def test_a_child_row_for_an_unknown_film_is_a_hard_failure():
    films = build_films([film(550)])
    cast = build_cast([film(999)])
    with pytest.raises(AssertionError, match="references films not in films"):
        assert_grains(films, cast, build_crew([]), build_genres([]))


def test_a_film_count_that_disagrees_with_the_fetch_is_a_hard_failure():
    films = build_films([film(550), film(155)])
    with pytest.raises(AssertionError, match="for 3 successful fetches"):
        assert_grains(films, build_cast([]), build_crew([]), build_genres([]),
                      expected_films=3)


def test_a_collection_name_without_an_id_is_a_hard_failure():
    """The franchise split rests entirely on this field."""
    films = build_films([film(550)])
    films.loc[0, "collection_name"] = "Orphan Collection"
    with pytest.raises(AssertionError, match="collection name with no collection id"):
        assert_grains(films, build_cast([]), build_crew([]), build_genres([]))


def test_a_film_with_no_cast_is_reported_as_a_note_not_a_crash():
    payloads = [film(550), film(155, cast=[])]
    notes = assert_grains(
        build_films(payloads), build_cast(payloads), build_crew(payloads),
        build_genres(payloads),
    )
    assert any("no cast rows" in note and "155" in note for note in notes)


def test_a_person_in_two_jobs_is_reported_as_expected_not_wrong():
    payload = film(550, crew=[
        {"id": 7467, "name": "David Fincher", "job": "Director", "department": "Directing"},
        {"id": 7467, "name": "David Fincher", "job": "Producer", "department": "Production"},
    ])
    notes = assert_grains(
        build_films([payload]), build_cast([payload]), build_crew([payload]),
        build_genres([payload]),
    )
    assert any("more than one job" in note for note in notes)


def test_clean_tables_produce_no_notes():
    payloads = [film(550), film(155)]
    notes = assert_grains(
        build_films(payloads), build_cast(payloads), build_crew(payloads),
        build_genres(payloads), expected_films=2,
    )
    assert notes == []


# --------------------------------------------------------------------------
# the franchise split — three categories, because the data has three
# --------------------------------------------------------------------------

def test_a_collection_with_two_films_on_the_list_is_a_franchise():
    films = add_franchise_flags(
        build_films([film(1726, collection=IRON_MAN), film(10138, collection=IRON_MAN)]),
        min_members_on_list=2,
    )
    assert set(films["franchise_status"]) == {"franchise"}
    assert films["collection_members_on_list"].tolist() == [2, 2]


def test_a_lone_member_of_a_collection_is_neither():
    """Not a bundle anyone can buy; also not a standalone film."""
    films = add_franchise_flags(
        build_films([film(1726, collection=IRON_MAN), film(550)]),
        min_members_on_list=2,
    )
    by_id = films.set_index("tmdb_id")

    assert by_id.loc[1726, "franchise_status"] == "lone_collection_member"
    assert by_id.loc[550, "franchise_status"] == "standalone"
    assert pd.isna(by_id.loc[550, "collection_members_on_list"])


def test_the_threshold_is_a_setting_so_the_alternative_stays_runnable():
    films = build_films([film(1726, collection=IRON_MAN), film(550)])

    strict = add_franchise_flags(films, min_members_on_list=2)
    loose = add_franchise_flags(films, min_members_on_list=1)

    assert strict.set_index("tmdb_id").loc[1726, "franchise_status"] == "lone_collection_member"
    assert loose.set_index("tmdb_id").loc[1726, "franchise_status"] == "franchise"
    assert loose.set_index("tmdb_id").loc[550, "franchise_status"] == "standalone"


def test_every_film_gets_exactly_one_status():
    films = add_franchise_flags(
        build_films([
            film(1726, collection=IRON_MAN), film(10138, collection=IRON_MAN),
            film(155, collection={"id": 263, "name": "Batman Collection"}),
            film(550),
        ]),
        min_members_on_list=2,
    )
    assert films["franchise_status"].notna().all()
    assert int(films["franchise_status"].value_counts().sum()) == len(films)
    assert set(films["franchise_status"]) <= {
        "franchise", "lone_collection_member", "standalone",
    }


# --------------------------------------------------------------------------
# reading the cache
# --------------------------------------------------------------------------

def _envelope(tmp_path, tmdb_id, status=200, payload=None, requested=None):
    path = tmp_path / f"{tmdb_id}__details_credits.json"
    path.write_text(json.dumps({
        "requested_id": requested if requested is not None else tmdb_id,
        "id_namespace": "tmdb",
        "endpoint": "details_credits",
        "http_status": status,
        "fetched_at": "2026-11-19T00:00:00+00:00",
        "payload": payload,
    }), encoding="utf-8")
    return path


def test_a_404_envelope_is_skipped_not_read_as_a_film(tmp_path):
    _envelope(tmp_path, 550, payload=film(550))
    _envelope(tmp_path, 999, status=404, payload=None)

    payloads, notes = load_payloads(tmp_path)
    assert len(payloads) == 1
    assert payloads[0]["id"] == 550
    assert any("held no film" in note for note in notes)


def test_a_redirected_id_is_reported(tmp_path):
    """Two of our ids being the same film is a finding, not a detail."""
    _envelope(tmp_path, 550, payload=film(999, title="Merged Entry"), requested=550)
    payloads, notes = load_payloads(tmp_path)

    assert len(payloads) == 1
    assert any("merged or redirected" in note for note in notes)


def test_a_clean_cache_reads_with_no_notes(tmp_path):
    _envelope(tmp_path, 550, payload=film(550))
    _envelope(tmp_path, 155, payload=film(155))
    payloads, notes = load_payloads(tmp_path)

    assert len(payloads) == 2
    assert notes == []


# --------------------------------------------------------------------------
# release_year: derived here, not in the join
# --------------------------------------------------------------------------
# The window boundary is a year, and the year is a property of the film rather
# than of any merge. Deriving it here is what lets the validate stage run on
# this table before a single credit is joined onto it.

def test_release_year_is_an_integer_not_a_string():
    films = build_films([film(550, release_date="1999-10-15")])

    assert str(films["release_year"].dtype) == "Int64"
    assert films["release_year"].item() == 1999


def test_a_missing_release_date_gives_a_missing_year_not_a_crash():
    """NA, never 0.

    A film with no parseable date must fall out of a *bounded* window and stay
    in the unbounded one. A year of 0 would be a real lower bound and would put
    it in both, silently (M4).
    """
    films = build_films([film(550, release_date="")])

    assert pd.isna(films["release_year"].item())
