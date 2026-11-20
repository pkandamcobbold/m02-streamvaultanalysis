"""Acquisition: cached, retried, rate-limited TMDb calls.

One JSON file per (id, endpoint) in `data/raw/`, each wrapped in an envelope
recording the HTTP status, the request path and when it was fetched. The
envelope is what makes the memo's as-of date defensible, and what lets the
spot-check compare today's live values against what the analysis actually used.

Three properties this module exists to guarantee: **cache first**, so a second
run costs nothing and needs no network; **resumable**, so a run that dies at
film 80 restarts at 81 with no state beyond the files themselves; and **nothing
is lost**, because a 404 is an answer recorded in three places rather than an
exception.

See ADR-001 (the token), ADR-002 (the uncommitted cache), ADR-003 (one call per
film), ADR-005 (foreign ids), ADR-006 (404s), ADR-007 (atomic writes) and
and the note on row loops at the end of reports/decision_notes.md, for why a loop is
correct here.
"""
from __future__ import annotations

import json
import os
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
from pipeline.extract.ids import (
    IMDB_ID_RE,
    STATUS_INVALID,
    STATUS_PARSED,
    normalise_cell,
)


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
    """Resolve a foreign id to a TMDb one. This is F-09's resolution procedure.

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

    This is F-09's procedure, written as code rather than left to whoever runs
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
