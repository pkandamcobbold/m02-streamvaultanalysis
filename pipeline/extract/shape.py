"""Shaping: the cached envelopes become one table per grain.

Four tables, and the grain of each is stated in its builder and asserted at the
end. The grain is not decoration: by Thursday there will be six frames in scope
and nobody remembers which one has one row per film. Every bug that produces a
plausible-but-wrong number downstream is a grain mistake — a sum over `cast`
counts a film once per actor.

    films     one row per film
    cast      one row per film per cast member
    crew      one row per film per crew credit
    genres    one row per film per genre

Nothing is dropped, filtered or cleaned here. A film with a budget of zero or a
runtime of nothing survives intact and is dealt with by the validate stage,
where the decision is recorded. The only job here is shape — plus the two
derived columns named as derived: the franchise label (M1) and the release
year (M4).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


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
    # every bounded window (M4).
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
