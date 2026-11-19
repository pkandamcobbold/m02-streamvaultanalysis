"""Stage 1 — extract: the candidate list and the film data, as typed tables.

Three jobs, in the order they run:

1. **Read the candidate list** as text and nothing else, one ledger row per
   source row, forever. Rows are never dropped: a row that cannot be used gets
   a status and a reason. This is how "127 received, 112 analysed, here is the
   rest" is proved rather than remembered.
2. **Fetch details and credits** from TMDb: one session, a timeout on every
   call, retries with backoff, a rate limit, and every response cached in an
   envelope carrying its HTTP status and `fetched_at`. A 404 is an answer, not
   a failure. A second run needs neither token nor network.
3. **Shape the nested responses** into one table per grain — films, cast, crew,
   genres — with the grain asserted. Nothing is filtered or cleaned here; the
   only job is shape.

GRAINS produced:

    films     one row per film
    cast      one row per film per cast member
    crew      one row per film per crew credit
    genres    one row per film per genre

The reasoning behind each choice is in `docs/adr/`: the bearer token (ADR-001),
the uncommitted cache (ADR-002), one call per film (ADR-003), recovered float
ids (ADR-004), the title count as a claim (ADR-005), the IMDb id (ADR-006), the
404s (ADR-007), atomic cache writes (ADR-008), explicit dtypes (ADR-009), the
crew grain (ADR-011), and why a loop is correct here (ADR-031).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pipeline.config import Settings, load_token


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

# ===========================================================================
# Acquisition: cached, retried, rate-limited TMDb calls
# (was src/streamvault/fetch.py)
# ===========================================================================

# ---------------------------------------------------------------------------
# Endpoint names. These are also the cache filename suffixes, which is the
# point: "details" and "details_credits" are different files, so toggling
# api.append_credits can never serve a cached response that lacks the credits
# the caller asked for. Changing what you request changes where it is cached.
# ---------------------------------------------------------------------------
ENDPOINT_DETAILS = "details"
ENDPOINT_CREDITS = "credits"
ENDPOINT_DETAILS_CREDITS = "details_credits"

# Ledger statuses this stage adds. Stage 1's statuses partition the file;
# these partition what happened to the ids stage 1 queued for fetching.
STATUS_FETCHED = "fetched"
STATUS_NOT_FOUND = "not_found_404"
STATUS_FETCH_FAILED = "fetch_failed"
STATUS_CROSS_NAMESPACE_DUPLICATE = "duplicate_other_namespace"

FETCH_LOG_COLUMNS = [
    "tmdb_id", "endpoint", "http_status", "fetched_at", "from_cache",
    "calls_made", "has_credits", "n_cast", "n_crew",
]

# Read the artefact back with these, never with inference. Writing `155` and
# reading back `155.0` is the stage-1 fault reintroduced at the file boundary:
# the CSV is correct, and pandas infers float64 because the column also holds
# the blanks belonging to the ids that 404'd.
FETCH_LOG_DTYPES = {
    "tmdb_id": "Int64",
    "endpoint": "str",
    "http_status": "Int64",
    "fetched_at": "str",
    "calls_made": "Int64",
    "n_cast": "Int64",
    "n_crew": "Int64",
}

# Files whose cached response could not be read this run. Module-level because
# the corruption is found deep in fetch_one, three frames below anything that
# reports; reset at the start of every fetch_all.
_corrupt_cache: list[str] = []


# ---------------------------------------------------------------------------
# Session and pacing
# ---------------------------------------------------------------------------

def build_session(token: str, max_retries: int, backoff_factor: float) -> requests.Session:
    """One Session for the whole run: connection reuse, one retry policy.

    404 is deliberately NOT in status_forcelist. A missing film is an answer,
    not a failure, and retrying it five times is both rude and pointless.

    The token goes in a header. It never appears in a URL, so it cannot end up
    in a log line, an exception message, a cached request_path or a referrer.
    """
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "streamvault-catalog-analysis/0.1",
        }
    )
    retry = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,              # 0.5s, 1s, 2s, 4s, 8s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,            # honour TMDb's Retry-After
        raise_on_status=False,                      # we classify; urllib3 does not
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class RateLimiter:
    """A floor on the gap between calls. Crude, and crude is correct here.

    Measured with time.monotonic, not time.time: a clock adjustment mid-run
    must not produce a negative gap and release a burst of calls.
    """

    def __init__(self, min_interval: float) -> None:
        self.min_interval = float(min_interval)
        self._last: float | None = None

    def wait(self) -> None:
        now = time.monotonic()
        if self._last is not None:
            gap = now - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
        self._last = time.monotonic()


# ---------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------

def cache_path(raw_dir: Path, tmdb_id: int | str, endpoint: str) -> Path:
    """Where one (id, endpoint) response lives. Flat, sorted, greppable."""
    return Path(raw_dir) / f"{tmdb_id}__{endpoint}.json"


def request_path_for(tmdb_id: int | str, endpoint: str) -> str:
    if endpoint in (ENDPOINT_DETAILS, ENDPOINT_DETAILS_CREDITS):
        return f"/movie/{tmdb_id}"
    if endpoint == ENDPOINT_CREDITS:
        return f"/movie/{tmdb_id}/credits"
    raise ValueError(f"unknown endpoint {endpoint!r}")


def _envelope(
    requested_id: int | str,
    id_namespace: str,
    endpoint: str,
    status: int,
    payload: Any,
    request_path: str,
) -> dict[str, Any]:
    """What gets written to disk. Note what is absent: no headers, no token.

    The id field is `requested_id` with a separate `id_namespace`, not
    `tmdb_id`. A `/find` call is made with an IMDb id, so a field named
    `tmdb_id` holding `"tt0468569"` is a field name that lies — and the next
    person to read these envelopes generically will reasonably expect an
    integer there.

    fetched_at is UTC and explicit about it. A naive local timestamp in a file
    that outlives a daylight-saving change is not evidence of anything.
    """
    return {
        "requested_id": requested_id,
        "id_namespace": id_namespace,
        "endpoint": endpoint,
        "request_path": request_path,
        "http_status": int(status),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payload": payload,
    }


def _write_atomic(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then replace in one step.

    A half-written cache file is worse than no cache file: it is found on the
    next run, read, and raises — permanently, because nothing ever rewrites
    it. `path.write_text()` can leave exactly that if the process dies
    mid-write, which is the interruption the README tells Adjoa is safe.

    os.replace is atomic on POSIX and on Windows, so a reader sees either the
    whole old file or the whole new one. The temp file carries the pid so two
    processes writing the same id cannot collide on it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        # Includes KeyboardInterrupt: leaving a stray .tmp behind would make
        # the next run's cache listing wrong.
        tmp.unlink(missing_ok=True)
        raise


def _read_cached(path: Path) -> dict[str, Any] | None:
    """Return the cached envelope, or None if it cannot be used.

    A corrupt entry is a cache miss, not an exception. The old behaviour was
    a JSONDecodeError naming neither the film nor the remedy, on every run
    from then on. The file is deleted and recorded so the fetch reports it as
    a finding and then simply fetches it again.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
        _corrupt_cache.append(path.name)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def corrupt_cache_files() -> list[str]:
    """Cache entries that had to be discarded during the last fetch_all."""
    return list(_corrupt_cache)


def fetch_one(
    session: Any,
    base_url: str,
    raw_dir: Path,
    limiter: RateLimiter,
    tmdb_id: int | str,
    endpoint: str,
    timeout: float,
    params: dict[str, str] | None = None,
    force: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Return (envelope, from_cache) for one (id, endpoint).

    from_cache is returned rather than stored in the envelope on purpose: it
    describes this run, not the response. Writing it to disk would make every
    cached file claim it had been fetched live, forever.
    """
    path = cache_path(raw_dir, tmdb_id, endpoint)
    if path.exists() and not force:
        cached = _read_cached(path)
        if cached is not None:
            return cached, True
        # Corrupt entry: discarded and recorded, so fall through and refetch.

    request_path = request_path_for(tmdb_id, endpoint)
    limiter.wait()
    response = session.get(
        f"{base_url}{request_path}",
        params=params or {},
        timeout=timeout,                 # every call has a timeout. Every one.
    )

    if response.status_code == 200:
        payload: Any = response.json()
    else:
        # 404, or anything that survived the retry policy. Record, don't raise.
        payload = None

    envelope = _envelope(
        tmdb_id, "tmdb", endpoint, response.status_code, payload, request_path
    )
    _write_atomic(path, json.dumps(envelope, ensure_ascii=False, indent=1))
    return envelope, False


def find_by_external_id(
    session: Any,
    base_url: str,
    raw_dir: Path,
    limiter: RateLimiter,
    external_id: str,
    timeout: float,
    source: str = "imdb_id",
    force: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Resolve a foreign id to a TMDb one. This is F3's resolution procedure.

    Row 95 of the candidate list holds an IMDb id in a TMDb column. The
    obvious fix — resolve it and add the film — may be wrong: if it resolves
    to 155, that film is already on the list twice, and resolving it would add
    a third copy inside a franchise, which is precisely where a duplicate does
    most damage to the franchise-versus-standalone comparison.

    So this returns the answer and records it. It does not act on it.
    """
    # Filename reads the same way round as the envelope: id first, then what
    # kind of request it was.
    path = cache_path(raw_dir, external_id, f"find_{source}")
    if path.exists() and not force:
        cached = _read_cached(path)
        if cached is not None:
            return cached, True

    request_path = f"/find/{external_id}"
    limiter.wait()
    response = session.get(
        f"{base_url}{request_path}",
        params={"external_source": source},
        timeout=timeout,
    )
    payload = response.json() if response.status_code == 200 else None
    envelope = _envelope(
        external_id, source, f"find_{source}", response.status_code, payload,
        request_path,
    )
    _write_atomic(path, json.dumps(envelope, ensure_ascii=False, indent=1))
    return envelope, False


def movie_ids_from_find(envelope: dict[str, Any]) -> list[int]:
    """The TMDb movie ids a /find response matched. Usually one, sometimes none."""
    payload = envelope.get("payload") or {}
    return [int(item["id"]) for item in payload.get("movie_results", []) if "id" in item]


# ---------------------------------------------------------------------------
# One film
# ---------------------------------------------------------------------------

def _credit_counts(payload: Any) -> tuple[int | None, int | None]:
    """(n_cast, n_crew) from either a credits payload or an appended one.

    Returns (None, None) when there is no credits block at all, which is a
    different fact from a film with an empty cast list and must not be
    flattened into the same number.
    """
    if not isinstance(payload, dict):
        return None, None
    block = payload.get("credits") if "credits" in payload else payload
    if not isinstance(block, dict):
        return None, None
    cast, crew = block.get("cast"), block.get("crew")
    if cast is None and crew is None:
        return None, None
    return len(cast or []), len(crew or [])


@dataclass
class FetchContext:
    """Everything the fetch functions need, resolved once from settings."""

    base_url: str
    raw_dir: Path
    timeout: float
    limiter: RateLimiter
    append_credits: bool


def fetch_film(
    session: Any, ctx: FetchContext, tmdb_id: int, force: bool = False
) -> dict[str, Any]:
    """Fetch one film and return its fetch-log row.

    Two paths, both live, chosen by api.append_credits:

    * append   — /movie/{id}?append_to_response=credits. One call per film.
    * two-call — /movie/{id} then /movie/{id}/credits. What the brief names.

    The rejected alternative stays runnable, which is what makes the timing
    comparison in the decision log a measurement rather than an estimate.
    """
    if ctx.append_credits:
        envelope, cached = fetch_one(
            session, ctx.base_url, ctx.raw_dir, ctx.limiter, tmdb_id,
            ENDPOINT_DETAILS_CREDITS, ctx.timeout,
            params={"append_to_response": "credits"}, force=force,
        )
        n_cast, n_crew = _credit_counts(envelope["payload"])
        return {
            "tmdb_id": tmdb_id,
            "endpoint": ENDPOINT_DETAILS_CREDITS,
            "http_status": envelope["http_status"],
            "fetched_at": envelope["fetched_at"],
            "from_cache": cached,
            "calls_made": 0 if cached else 1,
            "has_credits": n_cast is not None,
            "n_cast": n_cast,
            "n_crew": n_crew,
        }

    details, details_cached = fetch_one(
        session, ctx.base_url, ctx.raw_dir, ctx.limiter, tmdb_id,
        ENDPOINT_DETAILS, ctx.timeout, force=force,
    )
    calls = 0 if details_cached else 1

    if details["http_status"] != 200:
        # No point asking for the credits of a film that does not exist.
        return {
            "tmdb_id": tmdb_id,
            "endpoint": ENDPOINT_DETAILS,
            "http_status": details["http_status"],
            "fetched_at": details["fetched_at"],
            "from_cache": details_cached,
            "calls_made": calls,
            "has_credits": False,
            "n_cast": None,
            "n_crew": None,
        }

    credits, credits_cached = fetch_one(
        session, ctx.base_url, ctx.raw_dir, ctx.limiter, tmdb_id,
        ENDPOINT_CREDITS, ctx.timeout, force=force,
    )
    n_cast, n_crew = _credit_counts(credits["payload"])
    return {
        "tmdb_id": tmdb_id,
        "endpoint": f"{ENDPOINT_DETAILS}+{ENDPOINT_CREDITS}",
        "http_status": details["http_status"],
        "fetched_at": details["fetched_at"],
        "from_cache": details_cached and credits_cached,
        "calls_made": calls + (0 if credits_cached else 1),
        "has_credits": n_cast is not None and credits["http_status"] == 200,
        "n_cast": n_cast,
        "n_crew": n_crew,
    }


# ---------------------------------------------------------------------------
# All of them
# ---------------------------------------------------------------------------

def context_from_settings(settings: Settings) -> FetchContext:
    api = settings["api"]
    return FetchContext(
        base_url=api["base_url"],
        raw_dir=settings.path(settings["paths"]["raw_dir"]),
        timeout=float(api["timeout_seconds"]),
        limiter=RateLimiter(api["min_seconds_between_calls"]),
        append_credits=bool(api["append_credits"]),
    )


def fetch_all(
    ids: Iterable[int],
    settings: Settings,
    session_factory: Callable[[], Any] | None = None,
    force: bool = False,
    progress: Callable[[str], None] | None = print,
) -> pd.DataFrame:
    """Fetch every id and return the fetch log: one row per id.

    The session is built lazily, on the first cache miss. That is deliberate:
    a fully cached run needs neither a token nor a network, so the analysis can
    be re-run in a meeting on a laptop with no connection — which is the whole
    reason the cache exists. A missing token only becomes an error at the
    moment something actually has to be fetched.
    """
    ctx = context_from_settings(settings)
    api = settings["api"]
    every = int(api.get("progress_every", 25))
    ids = list(ids)
    _corrupt_cache.clear()

    session: Any = None

    def make_session() -> Any:
        if session_factory is not None:
            return session_factory()
        return build_session(
            load_token(), int(api["max_retries"]), float(api["backoff_factor"])
        )

    class LazySession:
        """Stands in for the Session until a call is actually made."""

        def get(self, *args: Any, **kwargs: Any) -> Any:
            nonlocal session
            if session is None:
                session = make_session()
            return session.get(*args, **kwargs)

    lazy = LazySession()
    rows: list[dict[str, Any]] = []
    started = time.monotonic()

    for index, tmdb_id in enumerate(ids, start=1):
        rows.append(fetch_film(lazy, ctx, int(tmdb_id), force=force))
        if progress and every and (index % every == 0 or index == len(ids)):
            live = sum(1 for row in rows if not row["from_cache"])
            progress(
                f"[extract] {index}/{len(ids)} films — {live} fetched, "
                f"{index - live} from cache, {time.monotonic() - started:.1f}s"
            )

    log = pd.DataFrame(rows, columns=FETCH_LOG_COLUMNS)
    # Explicit dtypes, for the same reason stage 1 is explicit: one film with
    # no credits block must not turn every count in the column into a float.
    for column in ("tmdb_id", "http_status", "calls_made", "n_cast", "n_crew"):
        log[column] = log[column].astype("Int64")
    log["from_cache"] = log["from_cache"].astype("boolean")
    log["has_credits"] = log["has_credits"].astype("boolean")

    log.attrs["ids_requested"] = len(ids)
    log.attrs["calls_made"] = int(log["calls_made"].sum())
    log.attrs["seconds"] = round(time.monotonic() - started, 2)
    log.attrs["append_credits"] = ctx.append_credits
    log.attrs["corrupt_cache"] = corrupt_cache_files()
    return log


def load_fetch_log(path: Path) -> pd.DataFrame:
    """Read the fetch log back with explicit dtypes.

    The counterpart to save_fetch_log, and the reason it exists: the CSV holds
    `139`, but `pd.read_csv` without dtypes returns `139.0`, because the column
    also holds the blanks belonging to the five ids that 404'd. Stage 1 exists
    to stop `550` becoming `550.0`; handing the next stage an artefact that
    undoes it at the file boundary would make that work pointless.
    """
    frame = pd.read_csv(path, dtype=FETCH_LOG_DTYPES)
    for column in ("from_cache", "has_credits"):
        frame[column] = frame[column].astype("boolean")
    return frame


def assert_fetch(log: pd.DataFrame, ids: Iterable[int]) -> list[str]:
    """Hard-assert what is logically required; report what is merely a finding."""
    notes: list[str] = []
    ids = [int(value) for value in ids]

    # Logically required: one row per requested id, and no extras. If this
    # fails, every count downstream is quoting a different denominator.
    assert len(log) == len(ids), f"fetch log has {len(log)} rows for {len(ids)} ids"
    assert log["tmdb_id"].is_unique, "fetch log has a duplicate id"
    assert set(log["tmdb_id"]) == set(ids), "fetch log ids differ from the ids requested"
    assert log["http_status"].notna().all(), "a fetch log row has no HTTP status"

    corrupt = log.attrs.get("corrupt_cache") or []
    if corrupt:
        notes.append(
            f"NOTE: {len(corrupt)} cached response(s) could not be read and were "
            f"discarded and refetched: {corrupt}. Usually a run interrupted "
            "mid-write. Harmless, but if it recurs the disk is the suspect."
        )

    missing = log.loc[log["http_status"] == 404, "tmdb_id"].tolist()
    if missing:
        notes.append(
            f"NOTE: {len(missing)} id(s) returned 404 and hold no film: {missing}. "
            "Check whether they cluster by era or by source batch — four dead ids "
            "is a sentence, four dead pre-2000 ids from one batch is a finding."
        )

    other = log.loc[~log["http_status"].isin([200, 404]), "tmdb_id"].tolist()
    if other:
        notes.append(
            f"NOTE: {len(other)} id(s) returned neither 200 nor 404 after retries: "
            f"{other}. These are not evidence of anything; re-run before relying "
            "on the counts."
        )

    # Credits are the whole basis of the talent question. A 200 without them is
    # the failure mode the append_to_response decision has to answer for.
    no_credits = log.loc[
        (log["http_status"] == 200) & (~log["has_credits"].fillna(False)), "tmdb_id"
    ]
    if len(no_credits):
        notes.append(
            f"NOTE: {len(no_credits)} film(s) returned 200 without credits: "
            f"{no_credits.tolist()}. The talent analysis cannot see these."
        )

    empty_cast = log.loc[(log["http_status"] == 200) & (log["n_cast"] == 0), "tmdb_id"]
    if len(empty_cast):
        notes.append(
            f"NOTE: {len(empty_cast)} film(s) have an empty cast list: "
            f"{empty_cast.tolist()}. Real, not an error — they must survive the "
            "stage-4 joins rather than disappearing from the film count."
        )
    return notes


def apply_to_ledger(ledger: pd.DataFrame, log: pd.DataFrame) -> pd.DataFrame:
    """Write what happened to each id back onto the ledger.

    The ledger stays the single place that accounts for every source row. Rows
    that were never queued — duplicates, blanks, placeholders — keep the status
    stage 1 gave them and are not touched here.
    """
    ledger = ledger.copy()
    status_by_id: dict[int, str] = {}
    reason_by_id: dict[int, str] = {}
    for row in log.itertuples(index=False):
        key = int(row.tmdb_id)
        if row.http_status == 200:
            status_by_id[key] = STATUS_FETCHED
            reason_by_id[key] = ""
        elif row.http_status == 404:
            status_by_id[key] = STATUS_NOT_FOUND
            reason_by_id[key] = "TMDb has no film under this id (404)"
        else:
            status_by_id[key] = STATUS_FETCH_FAILED
            reason_by_id[key] = f"HTTP {row.http_status} after retries"

    target = ledger["status"].eq("parsed") & ledger["tmdb_id"].isin(status_by_id)
    ledger.loc[target, "reason"] = ledger.loc[target, "tmdb_id"].map(reason_by_id)
    ledger.loc[target, "status"] = ledger.loc[target, "tmdb_id"].map(status_by_id)
    return ledger


def resolve_foreign_ids(
    ledger: pd.DataFrame,
    settings: Settings,
    session_factory: Callable[[], Any] | None = None,
    force: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """Resolve rows holding an IMDb id, and decide what each one means.

    This is F3's procedure, written as code rather than left to whoever runs
    the pipeline next quarter. Three outcomes, and the middle one is the whole
    reason this is not a one-line fix:

    * **No TMDb match.** The row stays unusable. Nothing was lost that could
      have been recovered.
    * **Resolves to an id already on the list.** A *cross-namespace duplicate*:
      the same film, written in two id systems. Recovering it would add
      another copy of a film already counted — and row 95's id resolves to
      155, a film already on the list twice, inside a franchise, which is
      exactly where a duplicate does most damage to the franchise-versus-
      standalone comparison. So it is excluded, with the reason recorded.
    * **Resolves to an id not on the list.** A genuine recovery. The row
      becomes fetchable, and is flagged for the stage-9 spot-check because its
      provenance is unlike every other row on the list.

    Returns (ledger, findings). Findings are printed and belong in the
    diagnosis report.
    """
    ledger = ledger.copy()
    findings: list[str] = []

    candidates = [
        row for row in ledger.itertuples(index=False)
        if row.status == STATUS_INVALID and IMDB_ID_RE.match(normalise_cell(row.raw_value))
    ]
    if not candidates:
        return ledger, findings

    ctx = context_from_settings(settings)
    api = settings["api"]
    session: Any = None

    known = set(ledger.loc[ledger["tmdb_id"].notna(), "tmdb_id"].astype(int))
    first_row_of = (
        ledger.loc[ledger["tmdb_id"].notna()]
        .drop_duplicates("tmdb_id")
        .set_index("tmdb_id")["source_row"]
    )

    for row in candidates:
        external_id = normalise_cell(row.raw_value)
        if session is None:
            session = (
                session_factory() if session_factory is not None
                else build_session(
                    load_token(), int(api["max_retries"]), float(api["backoff_factor"])
                )
            )
        envelope, _ = find_by_external_id(
            session, ctx.base_url, ctx.raw_dir, ctx.limiter, external_id,
            ctx.timeout, force=force,
        )
        matches = movie_ids_from_find(envelope)
        target = ledger["source_row"] == row.source_row

        if not matches:
            ledger.loc[target, "reason"] = (
                f"IMDb id {external_id!r}: TMDb /find returned no film. "
                "Not recoverable; nothing was lost that could have been."
            )
            findings.append(
                f"source_row {row.source_row}: IMDb id {external_id} resolves to "
                "nothing on TMDb. Row stays unusable."
            )
            continue

        resolved = matches[0]
        if resolved in known:
            at = int(first_row_of[resolved])
            ledger.loc[target, "status"] = STATUS_CROSS_NAMESPACE_DUPLICATE
            ledger.loc[target, "reason"] = (
                f"IMDb id {external_id!r} resolves to TMDb {resolved}, already on "
                f"the list at source_row {at}. Cross-namespace duplicate: "
                "excluded, because recovering it would count one film twice."
            )
            findings.append(
                f"source_row {row.source_row}: IMDb id {external_id} resolves to TMDb "
                f"{resolved}, which is already on the list at source_row {at}. "
                "Excluded as a cross-namespace duplicate — the obvious fix "
                "(recover the film) would have double-counted it."
            )
        else:
            ledger.loc[target, "tmdb_id"] = resolved
            ledger.loc[target, "status"] = STATUS_PARSED
            ledger.loc[target, "reason"] = (
                f"recovered from IMDb id {external_id!r} as TMDb {resolved} via "
                "/find — provenance unlike every other row, so spot-check it"
            )
            known.add(resolved)
            findings.append(
                f"source_row {row.source_row}: IMDb id {external_id} resolves to TMDb "
                f"{resolved}, which is NOT otherwise on the list. Recovered and "
                "queued for fetching; force it into the stage-9 spot-check sample."
            )

    ledger.attrs["unique_ids_to_fetch"] = int((ledger["status"] == STATUS_PARSED).sum())
    return ledger, findings


def save_fetch_log(log: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    log.to_csv(path, index=False)


def fetch_films(
    ledger: pd.DataFrame,
    settings: Settings,
    session_factory: Callable[[], Any] | None = None,
    force: bool = False,
    resolve_foreign: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch every film. Returns (updated ledger, fetch log).

    The ids to fetch are taken from the ledger, not passed in, so there is one
    source of truth for what is being analysed. Foreign ids are resolved first,
    because a recovery changes that list.
    """
    if resolve_foreign:
        ledger, findings = resolve_foreign_ids(
            ledger, settings, session_factory=session_factory, force=force
        )
        for finding in findings:
            print(f"[extract] FINDING {finding}")

    ids = ledger.loc[ledger["status"] == STATUS_PARSED, "tmdb_id"].astype(int).tolist()
    log = fetch_all(ids, settings, session_factory=session_factory, force=force)
    for note in assert_fetch(log, ids):
        print(f"[extract] {note}")
    save_fetch_log(
        log, settings.path(settings["paths"]["processed_dir"]) / "fetch_log.csv"
    )
    print(
        f"[extract] {log.attrs['calls_made']} API call(s) for {len(ids)} films "
        f"in {log.attrs['seconds']}s (append_credits={log.attrs['append_credits']})"
    )
    return apply_to_ledger(ledger, log), log

# ===========================================================================
# Shaping: one table per grain
# (was src/streamvault/flatten.py)
# ===========================================================================

# ---------------------------------------------------------------------------
# Column renames, in one place. The left side is what TMDb/json_normalize
# produces; the right side is what this project calls it, everywhere, forever.
# ---------------------------------------------------------------------------
FILM_RENAMES = {
    "id": "tmdb_id",
    "belongs_to_collection.id": "collection_id",
    "belongs_to_collection.name": "collection_name",
}

FILM_COLUMNS = [
    "tmdb_id", "imdb_id", "title", "original_title", "release_date", "status",
    "budget", "revenue", "runtime", "vote_average", "vote_count", "popularity",
    "adult", "video", "original_language", "collection_id", "collection_name",
]

# Nullable dtypes throughout: a missing runtime must not turn the column into
# float64 and give every film a decimal point. Money is Int64 because TMDb
# reports whole dollars and a budget is not 63000000.0.
FILM_DTYPES = {
    "tmdb_id": "Int64",
    "imdb_id": "str",
    "title": "str",
    "original_title": "str",
    "release_date": "str",
    "status": "str",
    "budget": "Int64",
    "revenue": "Int64",
    "runtime": "Int64",
    "vote_average": "Float64",
    "vote_count": "Int64",
    "popularity": "Float64",
    "adult": "boolean",
    "video": "boolean",
    "original_language": "str",
    "collection_id": "Int64",
    "collection_name": "str",
}

CAST_COLUMNS = [
    "tmdb_id", "person_id", "person_name", "character", "billing_order",
    "gender", "known_for_department",
]
CAST_DTYPES = {
    "tmdb_id": "Int64", "person_id": "Int64", "person_name": "str",
    "character": "str", "billing_order": "Int64", "gender": "Int64",
    "known_for_department": "str",
}

CREW_COLUMNS = [
    "tmdb_id", "person_id", "person_name", "job", "department", "gender",
]
CREW_DTYPES = {
    "tmdb_id": "Int64", "person_id": "Int64", "person_name": "str",
    "job": "str", "department": "str", "gender": "Int64",
}

GENRE_COLUMNS = ["tmdb_id", "genre_id", "genre_name"]
GENRE_DTYPES = {"tmdb_id": "Int64", "genre_id": "Int64", "genre_name": "str"}


# ---------------------------------------------------------------------------
# Reading the cache
# ---------------------------------------------------------------------------

def load_payloads(raw_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Every successful payload in the cache, plus notes on what was skipped.

    Reads `*__details_credits.json` — the append-mode files. A 404 envelope
    carries `payload: null` and is skipped here, not treated as a film with
    missing fields: the ledger already accounts for it as `not_found_404`.
    """
    notes: list[str] = []
    payloads: list[dict[str, Any]] = []
    skipped = 0

    for path in sorted(Path(raw_dir).glob("*__details_credits.json")):
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = envelope.get("payload")
        if envelope.get("http_status") != 200 or payload is None:
            skipped += 1
            continue
        # The envelope's requested_id is what we asked for; payload["id"] is
        # what TMDb returned. They differ if an id redirects to a merged
        # entry, which would mean two of our ids are the same film.
        requested = envelope.get("requested_id")
        if requested is not None and int(requested) != int(payload["id"]):
            notes.append(
                f"NOTE: id {requested} returned film {payload['id']} "
                f"({payload.get('title')!r}) — a merged or redirected TMDb entry. "
                "Check it is not also on the list under its current id."
            )
        payloads.append(payload)

    if skipped:
        notes.append(
            f"{skipped} cached envelope(s) held no film (404s) and were skipped. "
            "They remain accounted for on the ledger."
        )
    return payloads, notes


# ---------------------------------------------------------------------------
# The four tables
# ---------------------------------------------------------------------------

def build_films(payloads: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """GRAIN: one row per film. One row per successful payload, exactly.

    `belongs_to_collection` is a nested object or null, and it is the entire
    franchise-versus-standalone split, so it is flattened here into two plain
    columns and nowhere else. max_level=1 keeps json_normalize out of the
    credits, which have their own tables.
    """
    payloads = list(payloads)
    if not payloads:
        # Same columns as a populated table, release_year included: a shape
        # that changes when the input is empty is a KeyError waiting for a
        # quarter with nothing in it.
        empty = _empty(FILM_COLUMNS, FILM_DTYPES)
        empty["release_year"] = pd.Series(dtype="Int64")
        return empty

    films = pd.json_normalize(payloads, max_level=1)
    films = films.rename(columns=FILM_RENAMES)

    # A field TMDb has not sent (a new one, or one dropped) must appear as an
    # empty column rather than a KeyError three stages later.
    for column in FILM_COLUMNS:
        if column not in films.columns:
            films[column] = pd.NA

    films = films[FILM_COLUMNS].astype(FILM_DTYPES)

    # The window boundary is a year, and the year is a property of the film,
    # not of the join. Derived here so the validate stage can run on this
    # table before any credit is merged onto it. An unparseable date becomes
    # NA rather than 0: a real lower bound would silently exclude it from
    # every bounded window (ADR-013).
    films["release_year"] = (
        films["release_date"].astype("str").str.slice(0, 4)
        .replace({"": None, "nan": None, "<NA>": None})
        .astype("Int64")
    )
    return films.sort_values("tmdb_id", ignore_index=True)


def build_cast(payloads: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """GRAIN: one row per film per cast member.

    `order` is TMDb's billing order: 0 is the lead. Renamed to
    `billing_order` because `order` reads like a verb and because
    `settings.talent.lead_actor_billing_order` has to mean something.
    """
    return _build_credits(payloads, "cast", CAST_COLUMNS, CAST_DTYPES, {
        "id": "person_id", "name": "person_name", "order": "billing_order",
    })


def build_crew(payloads: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """GRAIN: one row per film per crew credit.

    Note *credit*, not person: one person can hold several jobs on one film,
    so this table is not unique on (tmdb_id, person_id). Collapsing it to one
    director per film is stage 4's job, where the choice is recorded.
    """
    return _build_credits(payloads, "crew", CREW_COLUMNS, CREW_DTYPES, {
        "id": "person_id", "name": "person_name",
    })


def _build_credits(
    payloads: Iterable[dict[str, Any]],
    block: str,
    columns: list[str],
    dtypes: dict[str, str],
    renames: dict[str, str],
) -> pd.DataFrame:
    """Shared body for cast and crew: same shape, different fields.

    Built row by row from the payloads rather than with json_normalize's
    record_path. record_path raises on a film whose credits block is absent,
    and the workaround (errors="ignore") hides the difference between "no cast"
    and "no credits fetched" — which stage 2 went to some trouble to keep
    apart. An explicit loop over 112 payloads costs nothing and cannot do that.
    """
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        credits = payload.get("credits") or {}
        for entry in credits.get(block) or []:
            row = {"tmdb_id": payload["id"]}
            for source, target in renames.items():
                row[target] = entry.get(source)
            for column in columns:
                if column not in row:
                    row[column] = entry.get(column)
            rows.append(row)

    if not rows:
        return _empty(columns, dtypes)
    frame = pd.DataFrame(rows)[columns].astype(dtypes)
    return frame


def build_genres(payloads: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """GRAIN: one row per film per genre."""
    rows = [
        {
            "tmdb_id": payload["id"],
            "genre_id": genre.get("id"),
            "genre_name": genre.get("name"),
        }
        for payload in payloads
        for genre in payload.get("genres") or []
    ]
    if not rows:
        return _empty(GENRE_COLUMNS, GENRE_DTYPES)
    return pd.DataFrame(rows)[GENRE_COLUMNS].astype(GENRE_DTYPES)


def _empty(columns: list[str], dtypes: dict[str, str]) -> pd.DataFrame:
    """An empty table with the right columns and dtypes, not an empty frame.

    So that a downstream `films["budget"].sum()` on an empty run returns 0
    rather than raising a KeyError about a column that should always exist.
    """
    return pd.DataFrame({column: pd.Series(dtype=dtypes[column]) for column in columns})


# ---------------------------------------------------------------------------
# Grain assertions
# ---------------------------------------------------------------------------

def assert_grains(
    films: pd.DataFrame,
    cast: pd.DataFrame,
    crew: pd.DataFrame,
    genres: pd.DataFrame,
    expected_films: int | None = None,
) -> list[str]:
    """Hard-assert each table's grain; report what is a finding about the data.

    The grain assertions are hard because a broken grain does not raise — it
    produces a number that looks fine. One duplicated film row inflates every
    median and every total, and nothing downstream can detect it.
    """
    notes: list[str] = []

    # --- grain: films is one row per film ---------------------------------
    assert films["tmdb_id"].is_unique, "films has more than one row for some film"
    assert films["tmdb_id"].notna().all(), "a film row has no id"
    if expected_films is not None:
        assert len(films) == expected_films, (
            f"films has {len(films)} rows for {expected_films} successful fetches"
        )

    # --- grain: every child row belongs to a film we have -----------------
    known = set(films["tmdb_id"])
    for name, table in (("cast", cast), ("crew", crew), ("genres", genres)):
        if table.empty:
            continue
        orphans = set(table["tmdb_id"]) - known
        assert not orphans, f"{name} references films not in films: {sorted(orphans)}"

    # --- cast is unique on (film, person, billing order) ------------------
    if not cast.empty:
        key = ["tmdb_id", "person_id", "billing_order"]
        duplicated = int(cast.duplicated(key).sum())
        if duplicated:
            notes.append(
                f"NOTE: {duplicated} cast row(s) repeat the same person at the same "
                "billing order on the same film. Real on TMDb (a credit entered "
                "twice), but they would double-weight that actor."
            )

    # --- crew is deliberately NOT unique per person ------------------------
    if not crew.empty:
        people = len(crew.drop_duplicates(["tmdb_id", "person_id"]))
        if people != len(crew):
            notes.append(
                f"NOTE: {len(crew) - people} crew row(s) are the same person in more "
                "than one job on one film — a writer-director, say. Expected, and "
                "the reason the crew grain is one row per *credit*. Any count of "
                "people must deduplicate; any count of credits must not."
            )

    # --- the franchise split, which the whole analysis rests on -----------
    bad = films["collection_name"].notna() & films["collection_id"].isna()
    assert not bad.any(), (
        f"{int(bad.sum())} film(s) have a collection name with no collection id"
    )

    # --- films with nothing in a child table ------------------------------
    for name, table in (("cast", cast), ("crew", crew), ("genres", genres)):
        missing = known - (set(table["tmdb_id"]) if not table.empty else set())
        if missing:
            notes.append(
                f"NOTE: {len(missing)} film(s) have no {name} rows: {sorted(missing)}. "
                f"They are still films and must survive the stage-4 joins; a film "
                f"without {name} is a fact, not an absence."
            )
    return notes


# ---------------------------------------------------------------------------
# Franchise membership — the one derived column stage 3 may add
# ---------------------------------------------------------------------------

def add_franchise_flags(films: pd.DataFrame, min_members_on_list: int) -> pd.DataFrame:
    """Label each film franchise / standalone / lone collection member.

    Three categories, not two, because the data has three and flattening them
    to two is a judgement call that belongs in the decision log rather than
    hidden in a boolean:

    * **franchise** — in a collection with at least `min_members_on_list`
      films on our candidate list. A bundle someone could actually buy.
    * **lone_collection_member** — belongs to a collection, but only one of
      its films is on our list. Not a bundle; also not a standalone film. The
      sensitivity run flips these to see whether the answer moves.
    * **standalone** — no collection at all.

    `min_members_on_list` comes from settings so the alternative stays
    runnable. The count is over *our list*, not over the collection's true
    size on TMDb: Kwame can only license what is on offer.
    """
    films = films.copy()
    members = (
        films.loc[films["collection_id"].notna()]
        .groupby("collection_id")["tmdb_id"]
        .transform("size")
    )
    films["collection_members_on_list"] = members.reindex(films.index).astype("Int64")

    films["franchise_status"] = "standalone"
    in_collection = films["collection_id"].notna()
    films.loc[in_collection, "franchise_status"] = "lone_collection_member"
    films.loc[
        in_collection & (films["collection_members_on_list"] >= min_members_on_list),
        "franchise_status",
    ] = "franchise"
    return films


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def save_tables(tables: dict[str, pd.DataFrame], interim_dir: Path) -> None:
    """One CSV per table, named for its grain."""
    interim_dir = Path(interim_dir)
    interim_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(interim_dir / f"{name}.csv", index=False)


def build_tables(settings: Any, expected_films: int | None = None) -> dict[str, pd.DataFrame]:
    """Shape the cached payloads. Returns {name: table}, all four, grains asserted."""
    payloads, notes = load_payloads(settings.path(settings["paths"]["raw_dir"]))
    for note in notes:
        print(f"[extract] {note}")

    films = build_films(payloads)
    cast = build_cast(payloads)
    crew = build_crew(payloads)
    genres = build_genres(payloads)

    for note in assert_grains(films, cast, crew, genres, expected_films):
        print(f"[extract] {note}")

    films = add_franchise_flags(
        films, int(settings["franchise"]["min_members_on_list"])
    )
    split = films["franchise_status"].value_counts().to_dict()
    print(
        f"[extract] {len(films)} films, {len(cast)} cast rows, {len(crew)} crew rows, "
        f"{len(genres)} genre rows"
    )
    print(f"[extract] franchise split: {split}")

    tables = {"films": films, "cast": cast, "crew": crew, "genres": genres}
    save_tables(tables, settings.path(settings["paths"]["interim_dir"]))
    return tables


# ===========================================================================
# The stage entry point
# ===========================================================================

def extract(
    settings: Settings,
    force: bool = False,
    session_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Read the list, fetch every film, shape the responses into four tables.

    Returns the ledger, the fetch log and the four tables. The ledger is the
    single source of truth for what is being analysed, so the ids to fetch are
    taken from it rather than passed in.

    The three parts are timed separately and returned under `timings`, because
    the time budget's boundary runs straight through this stage: shaping the
    cached payloads is inside it, and the acquisition is not (ADR-023).
    """
    timings: dict[str, float] = {}

    started = time.monotonic()
    ledger, ids = load_id_list(
        settings.path(settings["input"]["id_list_path"]),
        settings["input"]["expected_id_count"],
    )
    timings["extract.read_ids"] = time.monotonic() - started
    print(f"[extract] {ledger.attrs['data_rows']} data rows, {len(ids)} ids to fetch")

    started = time.monotonic()
    ledger, log = fetch_films(
        ledger, settings, session_factory=session_factory, force=force
    )
    timings["extract.acquire"] = time.monotonic() - started
    save_ledger(
        ledger,
        settings.path(settings["paths"]["processed_dir"]) / "id_ledger.csv",
    )

    started = time.monotonic()
    films_fetched = int((log["http_status"] == 200).sum())
    tables = build_tables(settings, expected_films=films_fetched)
    timings["extract.shape"] = time.monotonic() - started

    return {"ledger": ledger, "log": log, "timings": timings, **tables}
