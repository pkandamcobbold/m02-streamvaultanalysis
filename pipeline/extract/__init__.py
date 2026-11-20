"""Stage 1 — extract: the candidate list and the film data, as typed tables.

One stage, three jobs, one module each, because they have nothing in common but
their order: parsing a text file, speaking HTTP to a shared service, and
reshaping nested JSON have different dependencies, different failure modes and
different reasons to change, so each gets its own module.

    ids.py      read the candidate list; one ledger row per source row, forever
    fetch.py    details and credits: cached, retried, rate-limited, resumable
    shape.py    the nested responses become one table per grain

GRAINS produced:

    films     one row per film
    cast      one row per film per cast member
    crew      one row per film per crew credit
    genres    one row per film per genre

Callers import the stage, not its parts: `extract.build_films` and
`extract.extract` both work, so nothing outside this package has to know it is
a package rather than a file.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from pipeline.config import Settings
from pipeline.extract.fetch import (
    ENDPOINT_CREDITS,
    ENDPOINT_DETAILS,
    ENDPOINT_DETAILS_CREDITS,
    FETCH_LOG_COLUMNS,
    FETCH_LOG_DTYPES,
    STATUS_CROSS_NAMESPACE_DUPLICATE,
    STATUS_FETCH_FAILED,
    STATUS_FETCHED,
    STATUS_NOT_FOUND,
    FetchContext,
    RateLimiter,
    apply_to_ledger,
    assert_fetch,
    build_session,
    cache_path,
    context_from_settings,
    corrupt_cache_files,
    fetch_all,
    fetch_film,
    fetch_films,
    fetch_one,
    find_by_external_id,
    load_fetch_log,
    movie_ids_from_find,
    request_path_for,
    resolve_foreign_ids,
    save_fetch_log,
)
from pipeline.extract.ids import (
    FLOAT_LIKE_RE,
    HEADER_VALUES,
    IMDB_ID_RE,
    LEDGER_COLUMNS,
    LEDGER_DTYPES,
    SENTINEL_VALUES,
    STATUS_DUPLICATE,
    STATUS_HEADER,
    STATUS_INVALID,
    STATUS_PARSED,
    TMDB_ID_RE,
    assert_ledger,
    build_ledger,
    classify_value,
    load_id_list,
    load_ledger,
    normalise_cell,
    read_raw_rows,
    reconciliation_summary,
    save_ledger,
)
from pipeline.extract.shape import (
    CAST_COLUMNS,
    CAST_DTYPES,
    CREW_COLUMNS,
    CREW_DTYPES,
    FILM_COLUMNS,
    FILM_DTYPES,
    FILM_RENAMES,
    GENRE_COLUMNS,
    GENRE_DTYPES,
    add_franchise_flags,
    assert_grains,
    build_cast,
    build_crew,
    build_films,
    build_genres,
    build_tables,
    load_payloads,
    save_tables,
)


# ---------------------------------------------------------------------------
# The stage entry point
# ---------------------------------------------------------------------------

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
    cached payloads is inside it, and the acquisition is not (ADR-005).
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
