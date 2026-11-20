"""Tests for the transform stage: the proven join and the KPI tables.

The join tests are about silence. A merge against a non-unique key multiplies
rows and nothing raises; a co-directed film collapsed with `.first()` credits
an arbitrary person and looks authoritative. The KPI tests are about honesty:
every statistic carries its count, the window is a parameter rather than
copy-paste, and a flip is reported on every measure, not just the median.
"""
from __future__ import annotations

import pytest

import pandas as pd

from pipeline.config import Settings
from pipeline.transform import (
    GROUP_LOOSE,
    GROUP_STRICT,
    account_for_every_id,
    announce_flip,
    assert_join,
    assert_kpis,
    build_analysis_table,
    bundle_table,
    by_window,
    collapse_directors,
    collapse_genres,
    collapse_leads,
    compare_groups,
    directors_long,
    flip_check,
    gap_to_best_entry,
    leads_as_credits,
    position_within_franchise,
    shortlist,
    talent_table,
)
from pipeline.validate import clean

# ==========================================================================
# What was tests/test_join.py — the join half of this stage
# ==========================================================================

def films_frame_join(*ids: int) -> pd.DataFrame:
    return pd.DataFrame({
        "tmdb_id": pd.array(ids, dtype="Int64"),
        "title": [f"Film {i}" for i in ids],
        "release_date": ["1999-10-15"] * len(ids),
        "budget": pd.array([1_000_000] * len(ids), dtype="Int64"),
        "revenue": pd.array([5_000_000] * len(ids), dtype="Int64"),
    })


def crew_frame_join(rows: list[tuple]) -> pd.DataFrame:
    """rows of (tmdb_id, person_id, person_name, job)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "person_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "person_name": [r[2] for r in rows],
        "job": [r[3] for r in rows],
        "department": ["Directing" if r[3] == "Director" else "Other" for r in rows],
    })


def cast_frame_join(rows: list[tuple]) -> pd.DataFrame:
    """rows of (tmdb_id, person_id, person_name, billing_order)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "person_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "person_name": [r[2] for r in rows],
        "character": [f"Role {r[1]}" for r in rows],
        "billing_order": pd.array([r[3] for r in rows], dtype="Int64"),
    })


def genres_frame_join(rows: list[tuple]) -> pd.DataFrame:
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

WACHOWSKI_CREW = crew_frame_join([
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
    crew = crew_frame_join([
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
    crew = crew_frame_join([
        (550, 7467, "David Fincher", "Director"),
        (550, 7467, "David Fincher", "Producer"),
        (550, 999, "Someone Else", "Writer"),
    ])
    collapsed = collapse_directors(crew)
    assert collapsed["director_names"].item() == "David Fincher"
    assert collapsed["n_directors"].item() == 1


def test_a_director_credited_twice_on_one_film_counts_once():
    crew = crew_frame_join([
        (550, 7467, "David Fincher", "Director"),
        (550, 7467, "David Fincher", "Director"),
    ])
    assert collapse_directors(crew)["n_directors"].item() == 1
    assert len(directors_long(crew)) == 1


# --------------------------------------------------------------------------
# leads and genres
# --------------------------------------------------------------------------

def test_the_lead_is_billing_order_zero():
    cast = cast_frame_join([
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
    cast = cast_frame_join([
        (550, 2, "Zoe Zed", 0),
        (550, 1, "Alice Ay", 0),
    ])
    first = collapse_leads(cast)["lead_name"].item()
    reversed_input = collapse_leads(cast.iloc[::-1].reset_index(drop=True))
    assert first == "Alice Ay"
    assert reversed_input["lead_name"].item() == first


def test_genres_become_a_sorted_label_and_a_count():
    genres = genres_frame_join([
        (550, 53, "Thriller"), (550, 18, "Drama"), (155, 28, "Action"),
    ])
    collapsed = collapse_genres(genres).set_index("tmdb_id")

    assert collapsed.loc[550, "genre_names"] == "Drama|Thriller"
    assert collapsed.loc[550, "n_genres"] == 2
    assert collapsed.loc[155, "n_genres"] == 1


def test_genre_order_from_tmdb_does_not_change_the_label():
    """There is no "primary genre" here, deliberately — so order cannot matter."""
    a = genres_frame_join([(550, 53, "Thriller"), (550, 18, "Drama")])
    b = genres_frame_join([(550, 18, "Drama"), (550, 53, "Thriller")])
    assert collapse_genres(a)["genre_names"].item() == collapse_genres(b)["genre_names"].item()


# --------------------------------------------------------------------------
# the join itself
# --------------------------------------------------------------------------

def test_the_join_never_changes_the_film_count():
    films = films_frame_join(550, 155, 603)
    analysis, report = build_analysis_table(
        films,
        cast_frame_join([(550, 819, "Edward Norton", 0), (155, 3894, "Christian Bale", 0),
                    (603, 6384, "Keanu Reeves", 0)]),
        WACHOWSKI_CREW,
        genres_frame_join([(550, 18, "Drama"), (155, 28, "Action"), (603, 28, "Action")]),
    )
    assert len(analysis) == 3
    assert analysis["tmdb_id"].is_unique
    assert (report["result_rows"] == 3).all()
    assert (report["left_rows"] == 3).all()


def test_a_duplicated_key_on_the_right_is_a_hard_failure():
    """validate="one_to_one" is the proof. Without it the rows multiply."""
    films = films_frame_join(550)
    bad_cast = cast_frame_join([(550, 819, "Edward Norton", 0), (550, 287, "Brad Pitt", 0)])

    # collapse_leads deduplicates, so force the fault to prove the guard works.
    import pipeline.transform as join_module
    duplicated = bad_cast.rename(columns={
        "person_id": "lead_person_id", "person_name": "lead_name",
        "character": "lead_character",
    })[["tmdb_id", "lead_person_id", "lead_name", "lead_character"]]

    report: list = []
    with pytest.raises(Exception):
        join_module._merge_proven(films, duplicated, "leads", report)


def test_a_film_with_no_director_keeps_its_row():
    """An inner join would delete it, and the deletion would be invisible."""
    films = films_frame_join(550, 155)
    analysis, report = build_analysis_table(
        films,
        cast_frame_join([(550, 819, "Edward Norton", 0), (155, 1, "Someone", 0)]),
        crew_frame_join([(550, 7467, "David Fincher", "Director")]),
        genres_frame_join([(550, 18, "Drama"), (155, 28, "Action")]),
    )
    assert len(analysis) == 2
    assert pd.isna(analysis.set_index("tmdb_id").loc[155, "director_names"])

    directors_row = report.loc[report["merge"] == "directors"].iloc[0]
    assert directors_row["matched"] == 1
    assert directors_row["left_only"] == 1


def test_the_join_report_records_every_merge():
    films = films_frame_join(550)
    _, report = build_analysis_table(
        films,
        cast_frame_join([(550, 819, "Edward Norton", 0)]),
        crew_frame_join([(550, 7467, "David Fincher", "Director")]),
        genres_frame_join([(550, 18, "Drama")]),
    )
    assert report["merge"].tolist() == ["directors", "leads", "genres"]
    assert (report["right_only"] == 0).all()
    assert (report["matched"] == 1).all()


def test_no_indicator_column_survives_the_join():
    """Left in place it would collide with the next merge's indicator."""
    analysis, _ = build_analysis_table(
        films_frame_join(550),
        cast_frame_join([(550, 819, "Edward Norton", 0)]),
        crew_frame_join([(550, 7467, "David Fincher", "Director")]),
        genres_frame_join([(550, 18, "Drama")]),
    )
    assert not [column for column in analysis.columns if column.startswith("_merge")]






# --------------------------------------------------------------------------
# accounting for every id, start to finish
# --------------------------------------------------------------------------

def test_every_fetched_film_reaches_the_analysis():
    films = films_frame_join(550, 155)
    ledger = ledger_frame([550, 155], other=[("duplicate", 550), ("invalid_id", None)])
    analysis, _ = build_analysis_table(
        films, cast_frame_join([(550, 1, "A", 0), (155, 2, "B", 0)]),
        crew_frame_join([(550, 7467, "D", "Director"), (155, 7468, "E", "Director")]),
        genres_frame_join([(550, 18, "Drama"), (155, 28, "Action")]),
    )
    accounting = account_for_every_id(ledger, analysis)
    by_status = accounting.set_index("status")

    assert by_status.loc["fetched", "reached_analysis"] == 2
    assert by_status.loc["duplicate", "reached_analysis"] == 0
    assert by_status.loc["invalid_id", "reached_analysis"] == 0
    assert int(accounting["source_rows"].sum()) == 4      # data rows, not the header


def test_a_duplicate_row_does_not_count_as_reaching_the_analysis():
    """Its id is in the analysis once, via the row that was kept, not twice."""
    films = films_frame_join(550)
    ledger = ledger_frame([550], other=[("duplicate", 550)])
    analysis, _ = build_analysis_table(
        films, cast_frame_join([(550, 1, "A", 0)]),
        crew_frame_join([(550, 7467, "D", "Director")]), genres_frame_join([(550, 18, "Drama")]),
    )
    accounting = account_for_every_id(ledger, analysis)
    assert int(accounting["reached_analysis"].sum()) == 1


def test_a_fetched_film_missing_from_the_analysis_is_a_hard_failure():
    films = films_frame_join(550)
    ledger = ledger_frame([550, 155])
    analysis, _ = build_analysis_table(
        films, cast_frame_join([(550, 1, "A", 0)]),
        crew_frame_join([(550, 7467, "D", "Director")]), genres_frame_join([(550, 18, "Drama")]),
    )
    accounting = account_for_every_id(ledger, analysis)
    with pytest.raises(AssertionError, match="missing from the analysis"):
        assert_join(analysis, films, ledger, accounting)


def test_a_clean_join_produces_no_notes():
    films = films_frame_join(550, 155)
    ledger = ledger_frame([550, 155])
    analysis, _ = build_analysis_table(
        films, cast_frame_join([(550, 1, "A", 0), (155, 2, "B", 0)]),
        crew_frame_join([(550, 7467, "D", "Director"), (155, 7468, "E", "Director")]),
        genres_frame_join([(550, 18, "Drama"), (155, 28, "Action")]),
    )
    accounting = account_for_every_id(ledger, analysis)
    assert assert_join(analysis, films, ledger, accounting) == []


def test_co_directed_films_are_reported_as_a_note():
    films = films_frame_join(603, 605)
    ledger = ledger_frame([603, 605])
    analysis, _ = build_analysis_table(
        films, cast_frame_join([(603, 1, "A", 0), (605, 2, "B", 0)]),
        WACHOWSKI_CREW, genres_frame_join([(603, 28, "Action"), (605, 28, "Action")]),
    )
    notes = assert_join(analysis, films, ledger, account_for_every_id(ledger, analysis))
    assert any("more than one credited director" in note for note in notes)

# ==========================================================================
# What was tests/test_kpis.py — the kpis half of this stage
# ==========================================================================

@pytest.fixture
def settings_kpis(tmp_path):
    return Settings(
        raw={
            "paths": {"processed_dir": "data/processed", "interim_dir": "data/interim"},
            "performance": {
                "treat_zero_money_as_missing": True,
                "min_budget_for_roi": 1_000_000,
                "hit_roi_threshold": 2.5,
                "hit_definition": "roi",
                "report_all_hit_definitions": True,
            },
            "profile": {"min_votes_for_reliable_rating": 1000},
            "franchise": {"min_members_on_list": 2},
            "talent": {"min_films_for_reliable": 3, "lead_actor_billing_order": 0,
                       "sensitivity_top_n_billed": 3},
            "shortlist": {"n_franchises": 2, "n_standalones": 2, "show_runners_up": 1},
            "windows": {
                "all_years": {"label": "All years"},
                "modern": {"label": "2000 onward", "min_year": 2000},
            },
        },
        root=tmp_path,
    )


def film_kpis(tmdb_id, roi_revenue, year, status="standalone", collection=None,
         release_date=None, **extra):
    """One film with a chosen ROI: budget fixed at 10m so revenue sets the ratio."""
    row = {
        "tmdb_id": tmdb_id,
        "title": f"Film {tmdb_id}",
        "budget": 10_000_000,
        "revenue": int(roi_revenue * 10_000_000),
        "release_year": year,
        "release_date": release_date or f"{year}-06-01",
        "vote_average": 7.5,
        "vote_count": 20_000,
        "franchise_status": status,
        "collection_id": collection,
        "collection_name": f"Collection {collection}" if collection else None,
        "lead_person_id": 100 + tmdb_id,
        "lead_name": f"Lead {tmdb_id}",
    }
    row.update(extra)
    return row


def cleaned_frame_kpis(rows, settings_kpis):
    frame = pd.DataFrame(rows)
    for column in ("tmdb_id", "budget", "revenue", "release_year", "collection_id",
                   "lead_person_id", "vote_count"):
        frame[column] = frame[column].astype("Int64")
    return clean(frame, settings_kpis)


# --------------------------------------------------------------------------
# Counts beside every statistic
# --------------------------------------------------------------------------

def test_every_statistic_comes_with_its_count(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 6.0, 1999, "franchise", 10), film_kpis(2, 4.0, 2005, "franchise", 10),
        film_kpis(3, 3.0, 2010, "standalone"),
    ], settings_kpis)
    table = compare_groups(frame, GROUP_STRICT)

    assert "films" in table.columns
    assert table["films"].notna().all()
    assert int(table["films"].sum()) == 3


def test_the_groups_partition_the_window_exactly(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 6.0, 1999, "franchise", 10), film_kpis(2, 4.0, 2005, "standalone"),
        film_kpis(3, 3.0, 2010, "lone_collection_member", 11),
    ], settings_kpis)
    tables = by_window(frame, settings_kpis, GROUP_STRICT)
    notes = assert_kpis(tables, frame, GROUP_STRICT)

    assert int(tables["all_years"]["films"].sum()) == 3
    assert any("only" in note and "films" in note for note in notes)


def test_a_group_count_that_disagrees_with_the_window_is_a_hard_failure(settings_kpis):
    frame = cleaned_frame_kpis([film_kpis(1, 6.0, 1999, "franchise", 10)], settings_kpis)
    tables = by_window(frame, settings_kpis, GROUP_STRICT)
    tables["all_years"].loc[0, "films"] = 99
    with pytest.raises(AssertionError, match="in money metrics"):
        assert_kpis(tables, frame, GROUP_STRICT)


def test_a_film_out_of_money_metrics_is_out_of_the_kpis(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 6.0, 1999, "franchise", 10),
        film_kpis(2, 0, 2005, "franchise", 10, revenue=0, budget=0),
    ], settings_kpis)
    table = compare_groups(frame, GROUP_STRICT)
    assert int(table["films"].sum()) == 1


# --------------------------------------------------------------------------
# Both windows, one function
# --------------------------------------------------------------------------

def test_the_window_is_a_parameter_and_the_two_windows_differ(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 20.0, 1977, "franchise", 10), film_kpis(2, 3.0, 2010, "franchise", 10),
        film_kpis(3, 2.0, 2015, "standalone"),
    ], settings_kpis)
    tables = by_window(frame, settings_kpis, GROUP_STRICT)

    assert set(tables) == {"all_years", "modern"}
    assert int(tables["all_years"]["films"].sum()) == 3
    assert int(tables["modern"]["films"].sum()) == 2


def test_min_year_filters_on_release_year_not_on_a_string(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 5.0, 1999, "standalone"), film_kpis(2, 5.0, 2000, "standalone"),
    ], settings_kpis)
    assert int(compare_groups(frame, GROUP_STRICT, min_year=2000)["films"].sum()) == 1


def test_a_film_with_no_release_year_is_excluded_from_a_bounded_window(settings_kpis):
    """It cannot be placed, and guessing would put it in one window silently."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 5.0, 2010, "standalone"),
        film_kpis(2, 5.0, 1999, "standalone", release_year=None, release_date=None),
    ], settings_kpis)
    assert int(compare_groups(frame, GROUP_STRICT, min_year=2000)["films"].sum()) == 1
    assert int(compare_groups(frame, GROUP_STRICT, min_year=None)["films"].sum()) == 2


# --------------------------------------------------------------------------
# The flip check
# --------------------------------------------------------------------------

def test_a_flip_on_the_median_is_detected(settings_kpis):
    """Franchise ahead across all years, behind in the modern window."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 30.0, 1980, "franchise", 10), film_kpis(2, 25.0, 1985, "franchise", 10),
        film_kpis(3, 2.0, 2010, "franchise", 10), film_kpis(4, 2.0, 2012, "franchise", 10),
        film_kpis(5, 4.0, 1990, "standalone"), film_kpis(6, 9.0, 2011, "standalone"),
        film_kpis(7, 8.0, 2013, "standalone"),
    ], settings_kpis)
    flips = flip_check(by_window(frame, settings_kpis, GROUP_STRICT), GROUP_STRICT)
    median_row = flips.loc[flips["measure"] == "median_roi"].iloc[0]

    assert median_row["flipped"]
    assert median_row["winner_all_years"] == "franchise"
    assert median_row["winner_modern"] == "standalone"


def test_for_spread_the_lower_number_wins(settings_kpis):
    """A tighter group is the safer buy, so iqr must not be read like a median."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 5.0, 2001, "franchise", 10), film_kpis(2, 5.5, 2002, "franchise", 10),
        film_kpis(3, 6.0, 2003, "franchise", 10),
        film_kpis(4, 1.5, 2004, "standalone"), film_kpis(5, 9.0, 2005, "standalone"),
        film_kpis(6, 20.0, 2006, "standalone"),
    ], settings_kpis)
    tables = by_window(frame, settings_kpis, GROUP_STRICT)
    flips = flip_check(tables, GROUP_STRICT)
    spread = flips.loc[flips["measure"] == "iqr_roi"].iloc[0]

    assert spread["better_is"] == "lower"
    assert spread["winner_all_years"] == "franchise"


def test_every_measure_is_checked_not_just_the_median(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 6.0, 2001, "franchise", 10), film_kpis(2, 3.0, 2002, "standalone"),
    ], settings_kpis)
    flips = flip_check(by_window(frame, settings_kpis, GROUP_STRICT), GROUP_STRICT)
    assert set(flips["measure"]) == {
        "median_roi", "floor_roi", "hit_rate_primary", "iqr_roi",
    }


def test_a_flip_is_announced_loudly_and_a_hold_is_stated_plainly():
    flipped = pd.DataFrame({"measure": ["iqr_roi"], "flipped": [True]})
    held = pd.DataFrame({"measure": ["median_roi"], "flipped": [False]})

    assert any("FLIPS BETWEEN WINDOWS" in line for line in announce_flip(flipped))
    assert any("iqr_roi" in line for line in announce_flip(flipped))
    assert any("No measure flips" in line for line in announce_flip(held))


# --------------------------------------------------------------------------
# Position within a franchise
# --------------------------------------------------------------------------

def test_position_is_ranked_by_release_date(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 9.0, 1999, "franchise", 10, release_date="1999-05-01"),
        film_kpis(2, 5.0, 2002, "franchise", 10, release_date="2002-05-01"),
        film_kpis(3, 3.0, 2005, "franchise", 10, release_date="2005-05-01"),
    ], settings_kpis)
    table = position_within_franchise(frame).set_index("position")

    assert table.loc["first", "median_roi"] == 9.0
    assert table.loc["middle", "median_roi"] == 5.0
    assert table.loc["last", "median_roi"] == 3.0


def test_a_two_film_collection_has_no_middle_and_is_excluded(settings_kpis):
    """Including it would put its second film in 'last' and change what last means."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 9.0, 1999, "franchise", 10), film_kpis(2, 3.0, 2002, "franchise", 10),
        film_kpis(3, 8.0, 1998, "franchise", 11, release_date="1998-01-01"),
        film_kpis(4, 5.0, 2001, "franchise", 11, release_date="2001-01-01"),
        film_kpis(5, 2.0, 2004, "franchise", 11, release_date="2004-01-01"),
    ], settings_kpis)
    table = position_within_franchise(frame, min_entries=3)
    assert int(table["films"].sum()) == 3
    assert table["collections"].max() == 1


def test_position_table_is_ordered_first_middle_last(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(i, 5.0, 2000 + i, "franchise", 10, release_date=f"{2000+i}-01-01")
        for i in range(1, 4)
    ], settings_kpis)
    assert position_within_franchise(frame)["position"].tolist() == [
        "first", "middle", "last"
    ]


def test_no_collections_gives_an_empty_table_not_a_crash(settings_kpis):
    frame = cleaned_frame_kpis([film_kpis(1, 5.0, 2000, "standalone")], settings_kpis)
    assert position_within_franchise(frame).empty


# --------------------------------------------------------------------------
# Bundle economics
# --------------------------------------------------------------------------

def test_a_bundle_is_buyable_only_with_enough_films_on_the_list(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 6.0, 2001, "franchise", 10), film_kpis(2, 4.0, 2002, "franchise", 10),
        film_kpis(3, 9.0, 2003, "lone_collection_member", 11),
    ], settings_kpis)
    table = bundle_table(frame, settings_kpis).set_index("collection_name")

    assert bool(table.loc["Collection 10", "is_buyable_bundle"]) is True
    assert bool(table.loc["Collection 11", "is_buyable_bundle"]) is False


def test_bundle_roi_uses_totals_not_an_average_of_ratios(settings_kpis):
    """A bundle is bought whole, so its return is total revenue over total budget."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 10.0, 2001, "franchise", 10), film_kpis(2, 2.0, 2002, "franchise", 10),
    ], settings_kpis)
    row = bundle_table(frame, settings_kpis).iloc[0]

    assert row["bundle_roi"] == 6.0              # 120m revenue / 20m budget
    assert row["median_roi"] == 6.0
    assert row["floor_roi"] == 2.0


def test_the_concentration_number_shows_what_carries_a_bundle(settings_kpis):
    """Question 6: one film at 90% of revenue is a different buy from four equal ones."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 1.0, 2001, "franchise", 10, revenue=900_000_000),
        film_kpis(2, 1.0, 2002, "franchise", 10, revenue=50_000_000),
        film_kpis(3, 1.0, 2003, "franchise", 10, revenue=50_000_000),
    ], settings_kpis)
    row = gap_to_best_entry(frame).iloc[0]
    assert row["best_share_of_revenue"] == 0.9


# --------------------------------------------------------------------------
# Talent
# --------------------------------------------------------------------------

def directors_frame_kpis(rows):
    """rows of (tmdb_id, person_id, person_name)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "person_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "person_name": [r[2] for r in rows],
    })


def test_the_film_count_is_always_visible_even_below_the_minimum(settings_kpis):
    """A 3-film record and an 8-film record are not the same evidence."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 9.0, 2001, "standalone"), film_kpis(2, 8.0, 2002, "standalone"),
        film_kpis(3, 7.0, 2003, "standalone"),
    ], settings_kpis)
    credits = directors_frame_kpis([
        (1, 500, "Prolific"), (2, 500, "Prolific"), (3, 500, "Prolific"),
        (1, 501, "One Film"),
    ])
    table = talent_table(credits, frame, settings_kpis, "director").set_index("person_name")

    assert table.loc["One Film", "films"] == 1
    assert bool(table.loc["One Film", "meets_min_films"]) is False
    assert bool(table.loc["Prolific", "meets_min_films"]) is True
    assert "One Film" in table.index, "a thin record was hidden rather than labelled"


def test_a_co_directed_film_counts_for_both_directors(settings_kpis):
    frame = cleaned_frame_kpis([film_kpis(1, 5.0, 2001, "standalone")], settings_kpis)
    credits = directors_frame_kpis([(1, 500, "Lana"), (1, 501, "Lilly")])
    table = talent_table(credits, frame, settings_kpis, "director")

    assert table["films"].tolist() == [1, 1]
    assert set(table["person_name"]) == {"Lana", "Lilly"}


def test_above_overall_median_is_measured_against_the_whole_pool(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 10.0, 2001, "standalone"), film_kpis(2, 2.0, 2002, "standalone"),
        film_kpis(3, 2.0, 2003, "standalone"),
    ], settings_kpis)
    credits = directors_frame_kpis([(1, 500, "Good"), (2, 501, "Weak"), (3, 501, "Weak")])
    table = talent_table(credits, frame, settings_kpis, "director").set_index("person_name")

    assert bool(table.loc["Good", "above_overall_median"]) is True
    assert bool(table.loc["Weak", "above_overall_median"]) is False


def test_leads_are_reshaped_to_the_same_shape_as_directors(settings_kpis):
    frame = cleaned_frame_kpis([film_kpis(1, 5.0, 2001, "standalone")], settings_kpis)
    credits = leads_as_credits(frame)

    assert list(credits.columns) == ["tmdb_id", "person_id", "person_name"]
    assert talent_table(credits, frame, settings_kpis, "lead_actor")["role"].item() == "lead_actor"


def test_a_credit_for_a_film_out_of_money_metrics_is_dropped_not_counted(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 5.0, 2001, "standalone"),
        film_kpis(2, 0, 2002, "standalone", revenue=0, budget=0),
    ], settings_kpis)
    credits = directors_frame_kpis([(1, 500, "Director"), (2, 500, "Director")])
    assert talent_table(credits, frame, settings_kpis, "director")["films"].item() == 1


# --------------------------------------------------------------------------
# The shortlist
# --------------------------------------------------------------------------

def test_the_shortlist_marks_selections_and_keeps_runners_up(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 9.0, 2001, "franchise", 10), film_kpis(2, 8.0, 2002, "franchise", 10),
        film_kpis(3, 7.0, 2003, "franchise", 11), film_kpis(4, 6.0, 2004, "franchise", 11),
        film_kpis(5, 5.0, 2005, "franchise", 12), film_kpis(6, 4.0, 2006, "franchise", 12),
        film_kpis(7, 12.0, 2007, "standalone"), film_kpis(8, 11.0, 2008, "standalone"),
        film_kpis(9, 10.0, 2009, "standalone"),
    ], settings_kpis)
    picks = shortlist(frame, bundle_table(frame, settings_kpis), settings_kpis)

    assert int(picks["franchises"]["selected"].sum()) == 2
    assert len(picks["franchises"]) == 3
    assert int(picks["standalones"]["selected"].sum()) == 2
    assert len(picks["standalones"]) == 3


def test_an_unbuyable_bundle_cannot_be_shortlisted(settings_kpis):
    """A collection with one film on offer is not a bundle, whatever its ROI."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 99.0, 2001, "lone_collection_member", 11),
        film_kpis(2, 6.0, 2002, "franchise", 10), film_kpis(3, 5.0, 2003, "franchise", 10),
    ], settings_kpis)
    picks = shortlist(frame, bundle_table(frame, settings_kpis), settings_kpis)
    assert "Collection 11" not in set(picks["franchises"]["collection_name"])


def test_the_shortlist_shows_the_franchise_status_it_selected_on(settings_kpis):
    """3 of the real 5 "standalone" picks are lone collection members - label it."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 9.0, 2001, "lone_collection_member", 11),
        film_kpis(2, 8.0, 2002, "standalone"),
    ], settings_kpis)
    picks = shortlist(frame, bundle_table(frame, settings_kpis), settings_kpis)
    assert "franchise_status" in picks["standalones"].columns
    assert set(picks["standalones"]["franchise_status"]) == {
        "lone_collection_member", "standalone"
    }


def test_the_shortlist_carries_the_numbers_that_justify_each_pick(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 6.0, 2001, "franchise", 10), film_kpis(2, 4.0, 2002, "franchise", 10),
        film_kpis(3, 9.0, 2003, "standalone"),
    ], settings_kpis)
    picks = shortlist(frame, bundle_table(frame, settings_kpis), settings_kpis)

    assert {"median_roi", "floor_roi", "best_roi", "films_on_list"} <= set(
        picks["franchises"].columns
    )
    assert {"roi", "revenue", "vote_count", "rating_reliable"} <= set(
        picks["standalones"].columns
    )


# --------------------------------------------------------------------------
# The loose grouping runs through the same code
# --------------------------------------------------------------------------

def test_the_alternative_grouping_uses_the_same_function(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 6.0, 2001, "franchise", 10),
        film_kpis(2, 9.0, 2002, "lone_collection_member", 11),
        film_kpis(3, 3.0, 2003, "standalone"),
    ], settings_kpis)
    strict = compare_groups(frame, GROUP_STRICT)
    loose = compare_groups(frame, GROUP_LOOSE)

    assert strict.set_index(GROUP_STRICT).loc["standalone", "films"] == 2
    assert loose.set_index(GROUP_LOOSE).loc["franchise", "films"] == 2
    assert list(strict.columns)[1:] == list(loose.columns)[1:]


# --------------------------------------------------------------------------
# Settings that were inert until an audit found them
# --------------------------------------------------------------------------

def films_frame_kpis(*ids):
    return pd.DataFrame({
        "tmdb_id": pd.array(ids, dtype="Int64"),
        "title": [f"Film {i}" for i in ids],
        "release_date": ["2001-06-01"] * len(ids),
        "release_year": pd.array([2001] * len(ids), dtype="Int64"),
        "budget": pd.array([10_000_000] * len(ids), dtype="Int64"),
        "revenue": pd.array([60_000_000] * len(ids), dtype="Int64"),
        "vote_average": [7.5] * len(ids),
        "vote_count": pd.array([20_000] * len(ids), dtype="Int64"),
        "franchise_status": ["franchise"] * len(ids),
        "collection_id": pd.array([10] * len(ids), dtype="Int64"),
        "collection_name": ["Collection 10"] * len(ids),
    })


def cast_frame_kpis(rows):
    """rows of (tmdb_id, person_id, person_name, billing_order)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "person_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "person_name": [r[2] for r in rows],
        "character": [f"Role {r[1]}" for r in rows],
        "billing_order": pd.array([r[3] for r in rows], dtype="Int64"),
    })


def crew_frame_kpis(rows):
    """rows of (tmdb_id, person_id, person_name, job)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "person_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "person_name": [r[2] for r in rows],
        "job": [r[3] for r in rows],
        "department": ["Directing"] * len(rows),
    })


def genres_frame_kpis(rows):
    """rows of (tmdb_id, genre_id, genre_name)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "genre_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "genre_name": [r[2] for r in rows],
    })

def test_hit_definition_selects_the_primary_hit_rate(settings_kpis):
    """The setting offered three choices and selected none of them."""
    from pipeline.transform import primary_hit_column

    frame = cleaned_frame_kpis([
        film_kpis(1, 9.0, 2001, "franchise", 10), film_kpis(2, 2.0, 2002, "standalone"),
    ], settings_kpis)

    assert primary_hit_column(settings_kpis) == "hit_rate_roi"
    table = compare_groups(frame, GROUP_STRICT, settings=settings_kpis)
    assert table["hit_rate_primary"].tolist() == table["hit_rate_roi"].tolist()

    settings_kpis.raw["performance"]["hit_definition"] = "top_quartile"
    table = compare_groups(frame, GROUP_STRICT, settings=settings_kpis)
    assert table["hit_rate_primary"].tolist() == table["hit_rate_top_quartile"].tolist()


def test_an_unknown_hit_definition_is_rejected(settings_kpis):
    from pipeline.transform import primary_hit_column

    settings_kpis.raw["performance"]["hit_definition"] = "vibes"
    with pytest.raises(ValueError, match="expected one of"):
        primary_hit_column(settings_kpis)


def test_report_all_hit_definitions_false_drops_the_alternatives(settings_kpis):
    """It claimed to control this and controlled nothing."""
    frame = cleaned_frame_kpis([
        film_kpis(1, 9.0, 2001, "franchise", 10), film_kpis(2, 2.0, 2002, "standalone"),
    ], settings_kpis)

    both = compare_groups(frame, GROUP_STRICT, settings=settings_kpis)
    assert {"hit_rate_roi", "hit_rate_above_median", "hit_rate_top_quartile"} <= set(
        both.columns
    )

    settings_kpis.raw["performance"]["report_all_hit_definitions"] = False
    one = compare_groups(frame, GROUP_STRICT, settings=settings_kpis)
    assert "hit_rate_roi" in one.columns
    assert "hit_rate_above_median" not in one.columns
    assert "hit_rate_top_quartile" not in one.columns
    assert "hit_rate_primary" in one.columns


def test_the_flip_check_follows_the_primary_hit_rate(settings_kpis):
    frame = cleaned_frame_kpis([
        film_kpis(1, 9.0, 1999, "franchise", 10), film_kpis(2, 4.0, 2005, "franchise", 10),
        film_kpis(3, 3.0, 2006, "standalone"),
    ], settings_kpis)
    flips = flip_check(by_window(frame, settings_kpis, GROUP_STRICT), GROUP_STRICT)
    assert "hit_rate_primary" in set(flips["measure"])


def test_the_lead_billing_order_comes_from_settings(settings_kpis):
    """A hardcoded constant meant changing the setting did nothing."""
    cast = cast_frame_kpis([
        (1, 500, "Billed First", 0), (1, 501, "Billed Second", 1),
    ])
    films = films_frame_kpis(1)
    crew = crew_frame_kpis([(1, 900, "Director", "Director")])
    genres = genres_frame_kpis([(1, 18, "Drama")])

    analysis, _ = build_analysis_table(films, cast, crew, genres, settings_kpis)
    assert analysis["lead_name"].item() == "Billed First"

    settings_kpis.raw["talent"]["lead_actor_billing_order"] = 1
    analysis, _ = build_analysis_table(films, cast, crew, genres, settings_kpis)
    assert analysis["lead_name"].item() == "Billed Second"


def test_billed_as_credits_takes_the_top_n_only():
    from pipeline.transform import billed_as_credits

    cast = cast_frame_kpis([
        (1, 500, "First", 0), (1, 501, "Second", 1), (1, 502, "Third", 2),
        (1, 503, "Fourth", 3),
    ])
    assert set(billed_as_credits(cast, 3)["person_id"]) == {500, 501, 502}
    assert set(billed_as_credits(cast, 1)["person_id"]) == {500}


def test_the_talent_sensitivity_shows_who_only_appears_when_widened(settings_kpis):
    """Promised in settings since the planning stage; nothing read it until now."""
    from pipeline.transform import talent_sensitivity

    # The lead columns on `cleaned` must agree with the cast table, or the
    # lead-only view sees a different person per film and the comparison is
    # between two fixtures rather than two definitions.
    frame = cleaned_frame_kpis([
        film_kpis(i, 6.0, 2000 + i, "standalone",
             lead_person_id=500, lead_name="Always Lead")
        for i in range(1, 4)
    ], settings_kpis)
    cast = cast_frame_kpis(
        [(i, 500, "Always Lead", 0) for i in range(1, 4)]
        + [(i, 501, "Always Second", 1) for i in range(1, 4)]
    )
    widened = talent_sensitivity(cast, frame, settings_kpis)
    by_name = widened.set_index("person_name")

    assert bool(by_name.loc["Always Lead", "appears_only_when_widened"]) is False
    assert bool(by_name.loc["Always Second", "appears_only_when_widened"]) is True
    assert by_name.loc["Always Second", "films_top_3"] == 3
    assert pd.isna(by_name.loc["Always Second", "films_as_lead"])


def test_the_sensitivity_keeps_only_names_reliable_under_one_view(settings_kpis):
    from pipeline.transform import talent_sensitivity

    frame = cleaned_frame_kpis([
        film_kpis(i, 6.0, 2000 + i, "standalone",
             lead_person_id=500, lead_name="Reliable")
        for i in range(1, 4)
    ], settings_kpis)
    cast = cast_frame_kpis(
        [(i, 500, "Reliable", 0) for i in range(1, 4)]
        + [(1, 502, "One Film Only", 1)]
    )
    widened = talent_sensitivity(cast, frame, settings_kpis)
    assert set(widened["person_name"]) == {"Reliable"}

# ==========================================================================
# F-02: how much of the gap survives resampling
# ==========================================================================

@pytest.fixture
def settings_uncertainty(settings_kpis):
    """The KPI settings plus a small, seeded resample count, so tests are quick."""
    settings_kpis.raw["uncertainty"] = {
        "bootstrap_samples": 400,
        "cluster_bootstrap_samples": 200,
        "random_seed": 7,
    }
    return settings_kpis


def uncertainty_frame(franchise_rois, standalone_rois, settings, collections=None):
    """Two groups with chosen returns. `collections` assigns franchise films to collections."""
    collections = collections or [10] * len(franchise_rois)
    rows = [
        film_kpis(i + 1, roi, 2005, "franchise", collections[i])
        for i, roi in enumerate(franchise_rois)
    ] + [
        film_kpis(100 + i, roi, 2005, "standalone")
        for i, roi in enumerate(standalone_rois)
    ]
    return cleaned_frame_kpis(rows, settings)


def test_the_published_figure_is_the_statistic_on_the_real_data(settings_uncertainty):
    """The interval is around a figure, and the figure has to be the true one."""
    from pipeline.transform import GROUP_STRICT, bootstrap_comparison

    frame = uncertainty_frame([10.0, 11.0, 12.0, 13.0], [1.0, 2.0, 3.0, 4.0],
                              settings_uncertainty)
    money = frame.loc[frame["in_money_metrics"].fillna(False)]
    expected = float(
        money.loc[money[GROUP_STRICT] == "franchise", "roi"].astype("float64").median())

    table = bootstrap_comparison(frame, settings_uncertainty).set_index("measure")
    assert table.loc["typical return", "franchise"] == pytest.approx(expected, abs=0.001)
    assert table.loc["typical return", "gap"] == pytest.approx(
        table.loc["typical return", "franchise"] - table.loc["typical return", "standalone"],
        abs=0.001)


def test_the_same_seed_gives_the_same_interval(settings_uncertainty):
    """A reviewer re-running this must be able to tell a real change from a new draw."""
    from pipeline.transform import bootstrap_comparison

    frame = uncertainty_frame([10.0, 11.0, 12.0, 13.0], [1.0, 2.0, 3.0, 4.0],
                              settings_uncertainty)
    first = bootstrap_comparison(frame, settings_uncertainty)
    second = bootstrap_comparison(frame, settings_uncertainty)
    pd.testing.assert_frame_equal(first, second)


def test_a_wide_gap_excludes_zero_and_an_absent_one_does_not(settings_uncertainty):
    """The whole point: the interval has to be able to say no."""
    from pipeline.transform import bootstrap_comparison

    separated = bootstrap_comparison(
        uncertainty_frame([20.0, 21.0, 22.0, 23.0], [1.0, 1.1, 1.2, 1.3],
                          settings_uncertainty),
        settings_uncertainty).set_index("measure")
    identical = bootstrap_comparison(
        uncertainty_frame([3.0, 4.0, 5.0, 6.0], [3.0, 4.0, 5.0, 6.0],
                          settings_uncertainty),
        settings_uncertainty).set_index("measure")

    assert bool(separated.loc["typical return", "excludes_zero"]) is True
    assert bool(identical.loc["typical return", "excludes_zero"]) is False
    assert identical.loc["typical return", "gap"] == pytest.approx(0.0, abs=0.001)


def test_for_spread_the_tighter_group_is_the_one_ahead(settings_uncertainty):
    """`better_is: lower` — without the flip, a tighter franchise reads as losing."""
    from pipeline.transform import bootstrap_comparison

    table = bootstrap_comparison(
        uncertainty_frame([5.0, 5.1, 5.2, 5.3], [1.0, 2.0, 20.0, 40.0],
                          settings_uncertainty),
        settings_uncertainty).set_index("measure")

    assert table.loc["spread", "better_is"] == "lower"
    assert table.loc["spread", "gap"] < 0            # franchise spread is smaller
    assert table.loc["spread", "share_franchise_ahead"] > 0.5   # and that is ahead


def test_a_group_too_thin_to_resample_returns_the_empty_table(settings_uncertainty):
    """Publishing must not crash on a thin group, and must not invent an interval."""
    from pipeline.transform import UNCERTAINTY_COLUMNS, bootstrap_comparison

    table = bootstrap_comparison(
        uncertainty_frame([5.0, 6.0, 7.0], [4.0], settings_uncertainty),
        settings_uncertainty)
    assert table.empty
    assert list(table.columns) == UNCERTAINTY_COLUMNS


def test_one_franchise_cannot_be_resampled_as_franchises(settings_uncertainty):
    """87 films from one collection is one observation, and the table says so."""
    from pipeline.transform import cluster_bootstrap

    frame = uncertainty_frame([10.0, 11.0, 12.0, 13.0], [1.0, 2.0, 3.0, 4.0],
                              settings_uncertainty, collections=[10, 10, 10, 10])
    assert cluster_bootstrap(frame, settings_uncertainty).empty


def test_resampling_whole_franchises_never_narrows_the_interval(settings_uncertainty):
    """Sequels are not independent, so the per-film interval is the flattering one."""
    from pipeline.transform import bootstrap_comparison, cluster_bootstrap

    # Two collections, one high-returning and one low: exactly the case where
    # treating the films as independent overstates the evidence.
    frame = uncertainty_frame([20.0, 21.0, 22.0, 1.0, 1.1, 1.2],
                              [3.0, 4.0, 5.0, 6.0], settings_uncertainty,
                              collections=[10, 10, 10, 11, 11, 11])
    per_film = bootstrap_comparison(frame, settings_uncertainty).set_index("measure")
    per_franchise = cluster_bootstrap(frame, settings_uncertainty).set_index("measure")

    assert per_franchise.loc["typical return", "franchise"] == pytest.approx(
        per_film.loc["typical return", "franchise"], abs=0.001)
    assert "2 whole franchises" in per_franchise.loc["typical return", "basis"]
    width = lambda t: t.loc["typical return", "ci_high"] - t.loc["typical return", "ci_low"]
    assert width(per_franchise) >= width(per_film)


def test_only_the_measures_whose_interval_excludes_zero_may_be_led_with(
        settings_uncertainty):
    from pipeline.transform import bootstrap_comparison, measures_that_survive

    table = bootstrap_comparison(
        uncertainty_frame([20.0, 21.0, 22.0, 23.0], [1.0, 1.1, 1.2, 1.3],
                          settings_uncertainty),
        settings_uncertainty)
    survive = measures_that_survive(table)
    excluding = set(table.loc[table["excludes_zero"], "measure"])
    assert set(survive) == excluding
    assert measures_that_survive(table.iloc[0:0]) == []


def test_a_measure_lost_to_clustering_is_announced(settings_uncertainty):
    """A finding that only holds while sequels count as independent must be said aloud."""
    from pipeline.transform import announce_uncertainty

    per_film = pd.DataFrame({"measure": ["typical return"], "excludes_zero": [True]})
    per_franchise = pd.DataFrame({"measure": ["typical return"], "excludes_zero": [False]})
    said = " ".join(announce_uncertainty(per_film, per_franchise))
    assert "typical return" in said
    assert "not independent" in said

    held = " ".join(announce_uncertainty(per_film, per_film))
    assert "does not rest on" in held


def test_no_intervals_at_all_is_reported_rather_than_passed_over(settings_uncertainty):
    from pipeline.transform import announce_uncertainty

    said = announce_uncertainty(pd.DataFrame(), pd.DataFrame())
    assert len(said) == 1 and "too few films" in said[0]


# ==========================================================================
# S-07: reading position inside an era without breaking the comparison
# ==========================================================================

def franchise_frame_positions(rows, settings):
    """rows of (collection_id, release_year, roi) — one film each."""
    return cleaned_frame_kpis([
        film_kpis(i + 1, roi, year, "franchise", collection,
                  release_date=f"{year}-06-01")
        for i, (collection, year, roi) in enumerate(rows)
    ], settings)


def test_the_window_keeps_or_drops_a_franchise_whole(settings_kpis):
    """The fix for S-07: a franchise that began in 1990 is out, sequels and all.

    Admitting it on the strength of its modern entries is what put different
    franchises in the opener cell and the final cell, and the gap between
    those cells is then partly a gap between sets.
    """
    from pipeline.transform import position_within_franchise

    frame = franchise_frame_positions([
        # Began pre-2000 with two modern sequels: out of the window entirely.
        (10, 1990, 9.0), (10, 2004, 4.0), (10, 2008, 3.0),
        # Began in 2001: in.
        (11, 2001, 5.0), (11, 2005, 6.0), (11, 2009, 7.0),
    ], settings_kpis)

    pooled = position_within_franchise(frame)
    modern = position_within_franchise(frame, window_min_year=2000)

    assert set(pooled["collections"]) == {2}
    assert set(modern["collections"]) == {1}
    # Every cell holds the same franchise, so the comparison is like for like.
    assert list(modern["films"]) == [1, 1, 1]
    # And the figures are that franchise's own, not the old franchise's sequels.
    assert float(modern.set_index("position").loc["first", "median_roi"]) == 5.0
    assert float(modern.set_index("position").loc["last", "median_roi"]) == 7.0


def test_the_window_never_relabels_a_sequel_as_an_opener(settings_kpis):
    """Filtering the films first would make the 2004 entry an opener. It must not."""
    from pipeline.transform import position_within_franchise

    frame = franchise_frame_positions([
        (10, 1990, 9.0), (10, 2004, 4.0), (10, 2008, 3.0),
    ], settings_kpis)

    modern = position_within_franchise(frame, window_min_year=2000)
    assert modern.empty
    # The straddling franchise is still read in full when no window is asked for.
    assert not position_within_franchise(frame).empty


def test_a_window_with_no_franchise_born_in_it_returns_the_empty_table(settings_kpis):
    from pipeline.transform import position_within_franchise

    frame = franchise_frame_positions([
        (10, 1990, 9.0), (10, 1994, 4.0), (10, 1998, 3.0),
    ], settings_kpis)
    table = position_within_franchise(frame, window_min_year=2000)
    assert table.empty
    assert "median_roi" in table.columns


def test_the_paired_check_reads_each_franchise_against_itself(settings_kpis):
    """The statistic that cannot be moved by which franchise lands in which cell."""
    from pipeline.transform import paired_position_ratio

    frame = franchise_frame_positions([
        (10, 2001, 2.0), (10, 2004, 3.0), (10, 2007, 4.0),   # last / first = 2.0
        (11, 2002, 8.0), (11, 2005, 7.0), (11, 2008, 4.0),   # last / first = 0.5
        (12, 2003, 5.0), (12, 2006, 6.0), (12, 2009, 5.0),   # last / first = 1.0
    ], settings_kpis)

    row = paired_position_ratio(frame, window_min_year=2000).iloc[0]
    assert int(row["franchises"]) == 3
    assert float(row["median_last_over_first"]) == pytest.approx(1.0, abs=0.001)
    assert float(row["share_declining"]) == pytest.approx(1 / 3, abs=0.001)
    assert int(row["median_opener_year"]) == 2002
    assert "2000" in row["basis"]


def test_the_paired_check_skips_a_franchise_whose_opener_cannot_carry_a_ratio(
        settings_kpis):
    """A zero-return opener would otherwise produce an infinity and a silent lie."""
    from pipeline.transform import paired_position_ratio

    frame = franchise_frame_positions([
        (10, 2001, 0.0), (10, 2004, 3.0), (10, 2007, 4.0),
        (11, 2002, 4.0), (11, 2005, 7.0), (11, 2008, 8.0),
    ], settings_kpis)

    row = paired_position_ratio(frame, window_min_year=2000).iloc[0]
    assert int(row["franchises"]) == 1
    assert float(row["median_last_over_first"]) == pytest.approx(2.0, abs=0.001)


def test_a_two_film_franchise_has_no_middle_and_is_left_out_of_both(settings_kpis):
    from pipeline.transform import paired_position_ratio, position_within_franchise

    frame = franchise_frame_positions([
        (10, 2001, 2.0), (10, 2004, 3.0),
    ], settings_kpis)
    assert position_within_franchise(frame, window_min_year=2000).empty
    assert paired_position_ratio(frame, window_min_year=2000).empty
