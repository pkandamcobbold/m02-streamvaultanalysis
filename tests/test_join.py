"""Stage 4 tests.

A merge is the most dangerous operation in the pipeline, because the way it
fails is by succeeding. Join against a table that is not unique on the key and
the rows multiply, every median moves, and nothing raises — the result is a
table of the wrong length full of plausible numbers.

So these tests are mostly about row counts and determinism. The headline case
is real: TMDb returns the Wachowskis in one order for *The Matrix* and the
other for *The Matrix Revolutions*, and a `.first()` collapse would credit the
same partnership to different people on different films.
"""
from __future__ import annotations

import pandas as pd
import pytest

from streamvault.join import (
    account_for_every_id,
    assert_join,
    build_analysis_table,
    collapse_directors,
    collapse_genres,
    collapse_leads,
    directors_long,
)


def films_frame(*ids: int) -> pd.DataFrame:
    return pd.DataFrame({
        "tmdb_id": pd.array(ids, dtype="Int64"),
        "title": [f"Film {i}" for i in ids],
        "release_date": ["1999-10-15"] * len(ids),
        "budget": pd.array([1_000_000] * len(ids), dtype="Int64"),
        "revenue": pd.array([5_000_000] * len(ids), dtype="Int64"),
    })


def crew_frame(rows: list[tuple]) -> pd.DataFrame:
    """rows of (tmdb_id, person_id, person_name, job)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "person_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "person_name": [r[2] for r in rows],
        "job": [r[3] for r in rows],
        "department": ["Directing" if r[3] == "Director" else "Other" for r in rows],
    })


def cast_frame(rows: list[tuple]) -> pd.DataFrame:
    """rows of (tmdb_id, person_id, person_name, billing_order)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "person_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "person_name": [r[2] for r in rows],
        "character": [f"Role {r[1]}" for r in rows],
        "billing_order": pd.array([r[3] for r in rows], dtype="Int64"),
    })


def genres_frame(rows: list[tuple]) -> pd.DataFrame:
    """rows of (tmdb_id, genre_id, genre_name)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "genre_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "genre_name": [r[2] for r in rows],
    })


def ledger_frame(fetched: list[int], other: list[tuple] = ()) -> pd.DataFrame:
    """A minimal ledger: fetched ids plus (status, tmdb_id_or_None) extras."""
    rows = [{"source_row": 1, "status": "header_row", "tmdb_id": None}]
    row_number = 2
    for tmdb_id in fetched:
        rows.append({"source_row": row_number, "status": "fetched", "tmdb_id": tmdb_id})
        row_number += 1
    for status, tmdb_id in other:
        rows.append({"source_row": row_number, "status": status, "tmdb_id": tmdb_id})
        row_number += 1
    frame = pd.DataFrame(rows)
    frame["tmdb_id"] = frame["tmdb_id"].astype("Int64")
    return frame


# --------------------------------------------------------------------------
# The Wachowski case — determinism, and why it matters
# --------------------------------------------------------------------------

WACHOWSKI_CREW = crew_frame([
    # The order TMDb actually returns, which differs between these two films.
    (603, 9339, "Lana Wachowski", "Director"),
    (603, 9340, "Lilly Wachowski", "Director"),
    (605, 9340, "Lilly Wachowski", "Director"),
    (605, 9339, "Lana Wachowski", "Director"),
])


def test_a_partnership_gets_the_same_label_whatever_order_tmdb_returns():
    """`.first()` would credit Lana for one film and Lilly for the other."""
    collapsed = collapse_directors(WACHOWSKI_CREW).set_index("tmdb_id")

    assert collapsed.loc[603, "director_names"] == "Lana Wachowski & Lilly Wachowski"
    assert collapsed.loc[605, "director_names"] == collapsed.loc[603, "director_names"]
    assert collapsed.loc[603, "director_ids"] == collapsed.loc[605, "director_ids"]
    assert collapsed.loc[603, "n_directors"] == 2


def test_a_co_directed_film_counts_for_both_directors():
    """The reason the long table exists: min_films_for_reliable asks how many."""
    long = directors_long(WACHOWSKI_CREW)
    per_person = long.groupby("person_name").size().to_dict()

    assert per_person == {"Lana Wachowski": 2, "Lilly Wachowski": 2}
    assert len(long) == 4


def test_the_naive_collapse_would_have_split_the_filmography():
    """Pins what the decision avoids, so nobody 'simplifies' it back.

    Taking the first row per film gives Lana one film and Lilly one film.
    Sorted, both have two. With a 3-film reliability threshold, the difference
    is a partnership appearing in the talent analysis or vanishing from it.
    """
    naive = (
        WACHOWSKI_CREW.loc[WACHOWSKI_CREW["job"] == "Director"]
        .groupby("tmdb_id", as_index=False).first()
    )
    assert naive["person_name"].tolist() == ["Lana Wachowski", "Lilly Wachowski"]

    sorted_long = directors_long(WACHOWSKI_CREW)
    assert sorted_long.groupby("person_id").size().min() == 2


def test_three_directors_are_all_kept():
    crew = crew_frame([
        (809, 1, "Andrew Adamson", "Director"),
        (809, 2, "Kelly Asbury", "Director"),
        (809, 3, "Conrad Vernon", "Director"),
    ])
    collapsed = collapse_directors(crew)
    assert collapsed["n_directors"].item() == 3
    assert collapsed["director_names"].item() == (
        "Andrew Adamson & Conrad Vernon & Kelly Asbury"
    )


def test_only_directors_are_treated_as_directors():
    crew = crew_frame([
        (550, 7467, "David Fincher", "Director"),
        (550, 7467, "David Fincher", "Producer"),
        (550, 999, "Someone Else", "Writer"),
    ])
    collapsed = collapse_directors(crew)
    assert collapsed["director_names"].item() == "David Fincher"
    assert collapsed["n_directors"].item() == 1


def test_a_director_credited_twice_on_one_film_counts_once():
    crew = crew_frame([
        (550, 7467, "David Fincher", "Director"),
        (550, 7467, "David Fincher", "Director"),
    ])
    assert collapse_directors(crew)["n_directors"].item() == 1
    assert len(directors_long(crew)) == 1


# --------------------------------------------------------------------------
# leads and genres
# --------------------------------------------------------------------------

def test_the_lead_is_billing_order_zero():
    cast = cast_frame([
        (550, 819, "Edward Norton", 0),
        (550, 287, "Brad Pitt", 1),
        (550, 1, "Someone", 2),
    ])
    leads = collapse_leads(cast)
    assert len(leads) == 1
    assert leads["lead_name"].item() == "Edward Norton"
    assert leads["lead_person_id"].item() == 819


def test_a_tie_for_the_lead_is_resolved_deterministically():
    """No film in this list has one, but determinism must not depend on that."""
    cast = cast_frame([
        (550, 2, "Zoe Zed", 0),
        (550, 1, "Alice Ay", 0),
    ])
    first = collapse_leads(cast)["lead_name"].item()
    reversed_input = collapse_leads(cast.iloc[::-1].reset_index(drop=True))
    assert first == "Alice Ay"
    assert reversed_input["lead_name"].item() == first


def test_genres_become_a_sorted_label_and_a_count():
    genres = genres_frame([
        (550, 53, "Thriller"), (550, 18, "Drama"), (155, 28, "Action"),
    ])
    collapsed = collapse_genres(genres).set_index("tmdb_id")

    assert collapsed.loc[550, "genre_names"] == "Drama|Thriller"
    assert collapsed.loc[550, "n_genres"] == 2
    assert collapsed.loc[155, "n_genres"] == 1


def test_genre_order_from_tmdb_does_not_change_the_label():
    """There is no "primary genre" here, deliberately — so order cannot matter."""
    a = genres_frame([(550, 53, "Thriller"), (550, 18, "Drama")])
    b = genres_frame([(550, 18, "Drama"), (550, 53, "Thriller")])
    assert collapse_genres(a)["genre_names"].item() == collapse_genres(b)["genre_names"].item()


# --------------------------------------------------------------------------
# the join itself
# --------------------------------------------------------------------------

def test_the_join_never_changes_the_film_count():
    films = films_frame(550, 155, 603)
    analysis, report = build_analysis_table(
        films,
        cast_frame([(550, 819, "Edward Norton", 0), (155, 3894, "Christian Bale", 0),
                    (603, 6384, "Keanu Reeves", 0)]),
        WACHOWSKI_CREW,
        genres_frame([(550, 18, "Drama"), (155, 28, "Action"), (603, 28, "Action")]),
    )
    assert len(analysis) == 3
    assert analysis["tmdb_id"].is_unique
    assert (report["result_rows"] == 3).all()
    assert (report["left_rows"] == 3).all()


def test_a_duplicated_key_on_the_right_is_a_hard_failure():
    """validate="one_to_one" is the proof. Without it the rows multiply."""
    films = films_frame(550)
    bad_cast = cast_frame([(550, 819, "Edward Norton", 0), (550, 287, "Brad Pitt", 0)])

    # collapse_leads deduplicates, so force the fault to prove the guard works.
    import streamvault.join as join_module
    duplicated = bad_cast.rename(columns={
        "person_id": "lead_person_id", "person_name": "lead_name",
        "character": "lead_character",
    })[["tmdb_id", "lead_person_id", "lead_name", "lead_character"]]

    report: list = []
    with pytest.raises(Exception):
        join_module._merge_proven(films, duplicated, "leads", report)


def test_a_film_with_no_director_keeps_its_row():
    """An inner join would delete it, and the deletion would be invisible."""
    films = films_frame(550, 155)
    analysis, report = build_analysis_table(
        films,
        cast_frame([(550, 819, "Edward Norton", 0), (155, 1, "Someone", 0)]),
        crew_frame([(550, 7467, "David Fincher", "Director")]),
        genres_frame([(550, 18, "Drama"), (155, 28, "Action")]),
    )
    assert len(analysis) == 2
    assert pd.isna(analysis.set_index("tmdb_id").loc[155, "director_names"])

    directors_row = report.loc[report["merge"] == "directors"].iloc[0]
    assert directors_row["matched"] == 1
    assert directors_row["left_only"] == 1


def test_the_join_report_records_every_merge():
    films = films_frame(550)
    _, report = build_analysis_table(
        films,
        cast_frame([(550, 819, "Edward Norton", 0)]),
        crew_frame([(550, 7467, "David Fincher", "Director")]),
        genres_frame([(550, 18, "Drama")]),
    )
    assert report["merge"].tolist() == ["directors", "leads", "genres"]
    assert (report["right_only"] == 0).all()
    assert (report["matched"] == 1).all()


def test_no_indicator_column_survives_the_join():
    """Left in place it would collide with the next merge's indicator."""
    analysis, _ = build_analysis_table(
        films_frame(550),
        cast_frame([(550, 819, "Edward Norton", 0)]),
        crew_frame([(550, 7467, "David Fincher", "Director")]),
        genres_frame([(550, 18, "Drama")]),
    )
    assert not [column for column in analysis.columns if column.startswith("_merge")]


def test_release_year_is_an_integer_not_a_string():
    analysis, _ = build_analysis_table(
        films_frame(550), cast_frame([(550, 819, "Edward Norton", 0)]),
        crew_frame([(550, 7467, "David Fincher", "Director")]),
        genres_frame([(550, 18, "Drama")]),
    )
    assert str(analysis["release_year"].dtype) == "Int64"
    assert analysis["release_year"].item() == 1999


def test_a_missing_release_date_gives_a_missing_year_not_a_crash():
    films = films_frame(550)
    films.loc[0, "release_date"] = None
    analysis, _ = build_analysis_table(
        films, cast_frame([(550, 819, "Edward Norton", 0)]),
        crew_frame([(550, 7467, "David Fincher", "Director")]),
        genres_frame([(550, 18, "Drama")]),
    )
    assert pd.isna(analysis["release_year"].item())


# --------------------------------------------------------------------------
# accounting for every id, start to finish
# --------------------------------------------------------------------------

def test_every_fetched_film_reaches_the_analysis():
    films = films_frame(550, 155)
    ledger = ledger_frame([550, 155], other=[("duplicate", 550), ("invalid_id", None)])
    analysis, _ = build_analysis_table(
        films, cast_frame([(550, 1, "A", 0), (155, 2, "B", 0)]),
        crew_frame([(550, 7467, "D", "Director"), (155, 7468, "E", "Director")]),
        genres_frame([(550, 18, "Drama"), (155, 28, "Action")]),
    )
    accounting = account_for_every_id(ledger, analysis)
    by_status = accounting.set_index("status")

    assert by_status.loc["fetched", "reached_analysis"] == 2
    assert by_status.loc["duplicate", "reached_analysis"] == 0
    assert by_status.loc["invalid_id", "reached_analysis"] == 0
    assert int(accounting["source_rows"].sum()) == 4      # data rows, not the header


def test_a_duplicate_row_does_not_count_as_reaching_the_analysis():
    """Its id is in the analysis once, via the row that was kept, not twice."""
    films = films_frame(550)
    ledger = ledger_frame([550], other=[("duplicate", 550)])
    analysis, _ = build_analysis_table(
        films, cast_frame([(550, 1, "A", 0)]),
        crew_frame([(550, 7467, "D", "Director")]), genres_frame([(550, 18, "Drama")]),
    )
    accounting = account_for_every_id(ledger, analysis)
    assert int(accounting["reached_analysis"].sum()) == 1


def test_a_fetched_film_missing_from_the_analysis_is_a_hard_failure():
    films = films_frame(550)
    ledger = ledger_frame([550, 155])
    analysis, _ = build_analysis_table(
        films, cast_frame([(550, 1, "A", 0)]),
        crew_frame([(550, 7467, "D", "Director")]), genres_frame([(550, 18, "Drama")]),
    )
    accounting = account_for_every_id(ledger, analysis)
    with pytest.raises(AssertionError, match="missing from the analysis"):
        assert_join(analysis, films, ledger, accounting)


def test_a_clean_join_produces_no_notes():
    films = films_frame(550, 155)
    ledger = ledger_frame([550, 155])
    analysis, _ = build_analysis_table(
        films, cast_frame([(550, 1, "A", 0), (155, 2, "B", 0)]),
        crew_frame([(550, 7467, "D", "Director"), (155, 7468, "E", "Director")]),
        genres_frame([(550, 18, "Drama"), (155, 28, "Action")]),
    )
    accounting = account_for_every_id(ledger, analysis)
    assert assert_join(analysis, films, ledger, accounting) == []


def test_co_directed_films_are_reported_as_a_note():
    films = films_frame(603, 605)
    ledger = ledger_frame([603, 605])
    analysis, _ = build_analysis_table(
        films, cast_frame([(603, 1, "A", 0), (605, 2, "B", 0)]),
        WACHOWSKI_CREW, genres_frame([(603, 28, "Action"), (605, 28, "Action")]),
    )
    notes = assert_join(analysis, films, ledger, account_for_every_id(ledger, analysis))
    assert any("more than one credited director" in note for note in notes)
