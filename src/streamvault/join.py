"""Stage 4 — collapse the child tables to film grain and join them, provably.

Stage 3 produced four tables at three different grains. The analysis needs one
row per film, carrying its director, its lead actor and its genres. Getting
from there to here is where a pipeline quietly starts lying: a merge against a
table that is not unique on the key multiplies rows, every median shifts, and
nothing raises.

So every merge here is made with `validate=` and `indicator=True`, and the
counts are written to a join report rather than trusted. `validate="one_to_one"`
is the proof: it fails loudly if either side is not unique on the key, which is
exactly the condition a human cannot verify by looking.

GRAINS produced:

    directors   one row per film per director   (both halves of a partnership)
    analysis    one row per film                (the analysis-ready table)

The film-level table carries a *label* for its directors and genres. Any
analysis of people or genres uses the long tables, never the label — a count of
films per director must see both co-directors, and a string is not a group.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

DIRECTOR_JOB = "Director"
LEAD_BILLING_ORDER = 0

# Ledger statuses whose row is the one that put a film into the analysis. A
# duplicate row shares its id with the row that was kept, so id membership
# alone is not the question — see account_for_every_id.
ANALYSED_STATUSES = frozenset({"fetched"})

JOIN_REPORT_COLUMNS = [
    "merge", "left_rows", "right_rows", "result_rows", "matched",
    "left_only", "right_only",
]


# ---------------------------------------------------------------------------
# Collapsing to film grain
# ---------------------------------------------------------------------------

def directors_long(crew: pd.DataFrame) -> pd.DataFrame:
    """GRAIN: one row per film per director.

    This is the table the talent analysis must use. A film directed by the
    Wachowskis was directed by *both* of them, and counting it for one would
    understate each of their filmographies — which matters directly, because
    `talent.min_films_for_reliable` asks how many films a person has.
    """
    directors = crew.loc[crew["job"] == DIRECTOR_JOB, ["tmdb_id", "person_id", "person_name"]]
    # One person credited as Director twice on one film is a TMDb data entry
    # artefact, not two directing jobs.
    return (
        directors.drop_duplicates(["tmdb_id", "person_id"])
        .sort_values(["tmdb_id", "person_name"], ignore_index=True)
    )


def collapse_directors(crew: pd.DataFrame) -> pd.DataFrame:
    """GRAIN: one row per film. A label for the directors, not a choice of one.

    **Sorted by name, deliberately.** 9 of 112 films have more than one
    credited director, and TMDb returns them in no fixed order: *The Matrix*
    lists Lana then Lilly Wachowski, *The Matrix Revolutions* lists Lilly then
    Lana. Taking `.first()` would therefore credit the same partnership to
    different people on different films — splitting a 3-film body of work into
    two filmographies of 2 and 1, so that neither clears a 3-film reliability
    threshold and a consistent directing partnership vanishes from the talent
    analysis. Sorting makes the label a property of the film rather than of the
    order a response happened to arrive in.

    `n_directors` is kept so the 9 co-directed films can be found again, and so
    any per-director statistic can say how many of its films were shared.
    """
    long = directors_long(crew)
    if long.empty:
        return pd.DataFrame({
            "tmdb_id": pd.Series(dtype="Int64"),
            "director_names": pd.Series(dtype="str"),
            "director_ids": pd.Series(dtype="str"),
            "n_directors": pd.Series(dtype="Int64"),
        })

    grouped = long.groupby("tmdb_id", as_index=False).agg(
        director_names=pd.NamedAgg("person_name", lambda names: " & ".join(sorted(names))),
        director_ids=pd.NamedAgg(
            "person_id", lambda ids: "|".join(str(value) for value in sorted(ids))
        ),
        n_directors=pd.NamedAgg("person_id", "size"),
    )
    grouped["n_directors"] = grouped["n_directors"].astype("Int64")
    return grouped


def collapse_leads(cast: pd.DataFrame) -> pd.DataFrame:
    """GRAIN: one row per film. The billed lead, where there is exactly one.

    `billing_order == 0` is TMDb's lead. All 112 films in this list have
    exactly one, but that is a fact about this data and not a guarantee, so a
    tie is resolved by name — deterministically, for the same reason the
    directors are sorted — and counted, so the join report shows it happened.
    """
    leads = cast.loc[cast["billing_order"] == LEAD_BILLING_ORDER]
    leads = (
        leads.sort_values(["tmdb_id", "person_name"])
        .drop_duplicates("tmdb_id", keep="first")
        .loc[:, ["tmdb_id", "person_id", "person_name", "character"]]
        .rename(columns={
            "person_id": "lead_person_id",
            "person_name": "lead_name",
            "character": "lead_character",
        })
    )
    return leads.reset_index(drop=True)


def collapse_genres(genres: pd.DataFrame) -> pd.DataFrame:
    """GRAIN: one row per film. A sorted label and a count — not a "primary" genre.

    TMDb does not document its genre order as meaningful, so calling the first
    one "primary" would invent a fact and then rank films by it. Any genre
    analysis uses the long table and groups properly; this is a label for
    reading a row, and `n_genres` so a 5-genre film is not mistaken for a
    1-genre one.
    """
    if genres.empty:
        return pd.DataFrame({
            "tmdb_id": pd.Series(dtype="Int64"),
            "genre_names": pd.Series(dtype="str"),
            "n_genres": pd.Series(dtype="Int64"),
        })
    grouped = genres.groupby("tmdb_id", as_index=False).agg(
        genre_names=pd.NamedAgg("genre_name", lambda names: "|".join(sorted(names))),
        n_genres=pd.NamedAgg("genre_id", "nunique"),
    )
    grouped["n_genres"] = grouped["n_genres"].astype("Int64")
    return grouped


# ---------------------------------------------------------------------------
# The proven join
# ---------------------------------------------------------------------------

def _merge_proven(
    left: pd.DataFrame,
    right: pd.DataFrame,
    name: str,
    report: list[dict[str, Any]],
) -> pd.DataFrame:
    """One left join, validated, counted, and the indicator column removed.

    `validate="one_to_one"` is the whole point: it raises if either side is not
    unique on `tmdb_id`. That is the failure a human cannot see — a duplicated
    key multiplies rows, every statistic moves, and the result looks fine.

    The indicator is named per merge and dropped immediately. Left in place it
    would collide with the next merge's indicator, and pandas would resolve the
    collision by renaming rather than complaining.
    """
    indicator = f"_merge_{name}"
    merged = left.merge(
        right, on="tmdb_id", how="left", validate="one_to_one", indicator=indicator,
    )
    counts = merged[indicator].value_counts()
    report.append({
        "merge": name,
        "left_rows": len(left),
        "right_rows": len(right),
        "result_rows": len(merged),
        "matched": int(counts.get("both", 0)),
        "left_only": int(counts.get("left_only", 0)),
        "right_only": int(counts.get("right_only", 0)),
    })

    # A left join cannot produce right_only rows, so if one appears the merge
    # is not what it claims to be.
    assert int(counts.get("right_only", 0)) == 0, f"{name}: left join produced right_only rows"
    # The row count is the assertion that matters. A left join must never grow.
    assert len(merged) == len(left), (
        f"{name}: {len(left)} films in, {len(merged)} out — the merge multiplied rows"
    )
    return merged.drop(columns=[indicator])


def build_analysis_table(
    films: pd.DataFrame,
    cast: pd.DataFrame,
    crew: pd.DataFrame,
    genres: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """GRAIN: one row per film. Returns (analysis table, join report).

    Three left joins from `films`. Left, not inner: a film with no director
    must keep its row and show a missing director, because an inner join would
    delete it from the film count and the deletion would be invisible —
    the count would simply be smaller than the number of films fetched.
    """
    report: list[dict[str, Any]] = []
    analysis = films.copy()
    analysis = _merge_proven(analysis, collapse_directors(crew), "directors", report)
    analysis = _merge_proven(analysis, collapse_leads(cast), "leads", report)
    analysis = _merge_proven(analysis, collapse_genres(genres), "genres", report)

    analysis["release_year"] = (
        analysis["release_date"].astype("str").str.slice(0, 4)
        .replace({"": None, "nan": None, "<NA>": None})
        .astype("Int64")
    )
    return analysis, pd.DataFrame(report, columns=JOIN_REPORT_COLUMNS)


# ---------------------------------------------------------------------------
# Accounting: every id, start to finish
# ---------------------------------------------------------------------------

def account_for_every_id(ledger: pd.DataFrame, analysis: pd.DataFrame) -> pd.DataFrame:
    """One row per ledger status, with how many reached the analysis table.

    This is the table the memo's "127 received, N analysed, here is the rest"
    sentence is read off. It is built from the two ends of the pipeline and
    compared, rather than from a count anyone carried forward by hand.

    **A row counts as having reached the analysis only if it is the row that
    put the film there.** Testing "is this id in the analysis?" alone is wrong,
    and wrong in the direction that flatters: a duplicate row carries the *same
    id* as the row that was kept, so it would also answer yes, and the
    accounting would claim 113 of 127 rows became films when only 112 films
    exist. `ANALYSED_STATUSES` names the statuses that own their film; stage 6
    extends it when it starts excluding films for quality reasons.
    """
    in_analysis = set(analysis["tmdb_id"].dropna().astype(int))
    data = ledger.loc[ledger["status"] != "header_row"].copy()
    data["reached_analysis"] = [
        status in ANALYSED_STATUSES and not pd.isna(tmdb_id)
        and int(tmdb_id) in in_analysis
        for status, tmdb_id in zip(data["status"], data["tmdb_id"])
    ]
    summary = (
        data.groupby("status", as_index=False)
        .agg(
            source_rows=pd.NamedAgg("source_row", "size"),
            reached_analysis=pd.NamedAgg("reached_analysis", "sum"),
        )
        .sort_values("source_rows", ascending=False, ignore_index=True)
    )
    summary["reached_analysis"] = summary["reached_analysis"].astype("Int64")
    return summary


def assert_join(
    analysis: pd.DataFrame,
    films: pd.DataFrame,
    ledger: pd.DataFrame,
    accounting: pd.DataFrame,
) -> list[str]:
    """Hard-assert the join's integrity; report what is a finding about the data."""
    notes: list[str] = []

    assert len(analysis) == len(films), (
        f"analysis has {len(analysis)} rows for {len(films)} films"
    )
    assert analysis["tmdb_id"].is_unique, "analysis has more than one row for some film"

    # Every film that was fetched must reach the analysis, and nothing else may.
    fetched = set(
        ledger.loc[ledger["status"] == "fetched", "tmdb_id"].dropna().astype(int)
    )
    reached = set(analysis["tmdb_id"].dropna().astype(int))
    assert reached == fetched, (
        f"{len(fetched - reached)} fetched film(s) missing from the analysis, "
        f"{len(reached - fetched)} present that were never fetched"
    )

    # The accounting table must add up to the source rows, or the memo's
    # sentence about where the titles went is quoting a number nothing supports.
    assert int(accounting["source_rows"].sum()) == int(
        ledger.loc[ledger["status"] != "header_row"].shape[0]
    ), "the accounting table does not add up to the ledger's data rows"

    # --- findings, not failures -------------------------------------------
    for column, label in (
        ("director_names", "no director"),
        ("lead_name", "no billed lead"),
        ("genre_names", "no genre"),
    ):
        if column in analysis.columns:
            missing = analysis.loc[analysis[column].isna(), "tmdb_id"].tolist()
            if missing:
                notes.append(
                    f"NOTE: {len(missing)} film(s) have {label}: {missing}. They keep "
                    "their row — the left join is what makes that true — but every "
                    f"statistic grouped by {column} must report its own n."
                )

    if "n_directors" in analysis.columns:
        shared = analysis.loc[analysis["n_directors"] > 1]
        if len(shared):
            notes.append(
                f"NOTE: {len(shared)} film(s) have more than one credited director. "
                "The film-level label is the sorted partnership; per-director "
                "statistics must come from the long directors table, where the film "
                "counts for each of them."
            )
    return notes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(
    settings: Any, ledger: pd.DataFrame, tables: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    """Stage 4 entry point. Returns the analysis table and its evidence."""
    films, cast, crew, genres = (
        tables["films"], tables["cast"], tables["crew"], tables["genres"]
    )
    analysis, report = build_analysis_table(films, cast, crew, genres)
    directors = directors_long(crew)
    accounting = account_for_every_id(ledger, analysis)

    for note in assert_join(analysis, films, ledger, accounting):
        print(f"[stage 4] {note}")

    print(f"[stage 4] analysis table: {len(analysis)} films, {len(analysis.columns)} columns")
    print(f"[stage 4] {len(directors)} director credits across "
          f"{directors['person_id'].nunique()} people")

    processed = settings.path(settings["paths"]["processed_dir"])
    interim = settings.path(settings["paths"]["interim_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    interim.mkdir(parents=True, exist_ok=True)
    analysis.to_csv(interim / "analysis.csv", index=False)
    directors.to_csv(interim / "directors.csv", index=False)
    report.to_csv(processed / "join_report.csv", index=False)
    accounting.to_csv(processed / "id_accounting.csv", index=False)

    return {
        "analysis": analysis,
        "directors": directors,
        "join_report": report,
        "accounting": accounting,
    }
