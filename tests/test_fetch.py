"""Stage 2 tests.

No test here touches the network. A test that needs the live API is not a
test, it is a monitor: it fails when TMDb has an outage, which tells you
nothing about this code. The session is faked, which lets us assert the thing
that actually matters and cannot be observed from outside — *how many calls
were made, and to what*.

The faults these guard against are the expensive-and-silent kind: the token
leaking into a URL or a cached file, the cache serving a response that lacks
the credits the caller asked for, a 404 being retried five times, counts
turning into floats, and a row quietly vanishing between the ledger and the
fetch log.
"""
from __future__ import annotations

import json
import time

import pandas as pd
import pytest

from streamvault.config import Settings
from streamvault.fetch import (
    ENDPOINT_CREDITS,
    ENDPOINT_DETAILS,
    ENDPOINT_DETAILS_CREDITS,
    STATUS_CROSS_NAMESPACE_DUPLICATE,
    STATUS_FETCHED,
    STATUS_NOT_FOUND,
    RateLimiter,
    apply_to_ledger,
    assert_fetch,
    build_session,
    cache_path,
    context_from_settings,
    fetch_all,
    fetch_film,
    fetch_one,
    find_by_external_id,
    load_fetch_log,
    movie_ids_from_find,
    request_path_for,
    resolve_foreign_ids,
    save_fetch_log,
)
from streamvault.ingest import build_ledger

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
    """The v4-token decision (DR-00) is only worth anything if this holds."""
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
# F3: the IMDb id in row 95
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
