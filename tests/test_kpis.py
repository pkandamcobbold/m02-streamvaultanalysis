"""Stage 7 tests.

Every number here will be quoted to a board. The failures that matter are the
ones that produce a defensible-looking figure: a group whose count does not
match the window, a flip that goes unnoticed because only one measure was
checked, a talent table that hides how few films a name rests on.

The spread measure has a direction convention that is easy to get backwards -
for `iqr_roi`, *lower* is better, because a tighter group is the safer buy -
so there is a test for that alone.
"""
from __future__ import annotations

import pandas as pd
import pytest

from streamvault.clean import clean
from streamvault.config import Settings
from streamvault.kpis import (
    GROUP_LOOSE,
    GROUP_STRICT,
    announce_flip,
    assert_kpis,
    bundle_table,
    by_window,
    compare_groups,
    flip_check,
    gap_to_best_entry,
    leads_as_credits,
    position_within_franchise,
    shortlist,
    talent_table,
)


@pytest.fixture
def settings(tmp_path):
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


def film(tmdb_id, roi_revenue, year, status="standalone", collection=None,
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


def cleaned_frame(rows, settings):
    frame = pd.DataFrame(rows)
    for column in ("tmdb_id", "budget", "revenue", "release_year", "collection_id",
                   "lead_person_id", "vote_count"):
        frame[column] = frame[column].astype("Int64")
    return clean(frame, settings)


# --------------------------------------------------------------------------
# Counts beside every statistic
# --------------------------------------------------------------------------

def test_every_statistic_comes_with_its_count(settings):
    frame = cleaned_frame([
        film(1, 6.0, 1999, "franchise", 10), film(2, 4.0, 2005, "franchise", 10),
        film(3, 3.0, 2010, "standalone"),
    ], settings)
    table = compare_groups(frame, GROUP_STRICT)

    assert "films" in table.columns
    assert table["films"].notna().all()
    assert int(table["films"].sum()) == 3


def test_the_groups_partition_the_window_exactly(settings):
    frame = cleaned_frame([
        film(1, 6.0, 1999, "franchise", 10), film(2, 4.0, 2005, "standalone"),
        film(3, 3.0, 2010, "lone_collection_member", 11),
    ], settings)
    tables = by_window(frame, settings, GROUP_STRICT)
    notes = assert_kpis(tables, frame, GROUP_STRICT)

    assert int(tables["all_years"]["films"].sum()) == 3
    assert any("only" in note and "films" in note for note in notes)


def test_a_group_count_that_disagrees_with_the_window_is_a_hard_failure(settings):
    frame = cleaned_frame([film(1, 6.0, 1999, "franchise", 10)], settings)
    tables = by_window(frame, settings, GROUP_STRICT)
    tables["all_years"].loc[0, "films"] = 99
    with pytest.raises(AssertionError, match="in money metrics"):
        assert_kpis(tables, frame, GROUP_STRICT)


def test_a_film_out_of_money_metrics_is_out_of_the_kpis(settings):
    frame = cleaned_frame([
        film(1, 6.0, 1999, "franchise", 10),
        film(2, 0, 2005, "franchise", 10, revenue=0, budget=0),
    ], settings)
    table = compare_groups(frame, GROUP_STRICT)
    assert int(table["films"].sum()) == 1


# --------------------------------------------------------------------------
# Both windows, one function
# --------------------------------------------------------------------------

def test_the_window_is_a_parameter_and_the_two_windows_differ(settings):
    frame = cleaned_frame([
        film(1, 20.0, 1977, "franchise", 10), film(2, 3.0, 2010, "franchise", 10),
        film(3, 2.0, 2015, "standalone"),
    ], settings)
    tables = by_window(frame, settings, GROUP_STRICT)

    assert set(tables) == {"all_years", "modern"}
    assert int(tables["all_years"]["films"].sum()) == 3
    assert int(tables["modern"]["films"].sum()) == 2


def test_min_year_filters_on_release_year_not_on_a_string(settings):
    frame = cleaned_frame([
        film(1, 5.0, 1999, "standalone"), film(2, 5.0, 2000, "standalone"),
    ], settings)
    assert int(compare_groups(frame, GROUP_STRICT, min_year=2000)["films"].sum()) == 1


def test_a_film_with_no_release_year_is_excluded_from_a_bounded_window(settings):
    """It cannot be placed, and guessing would put it in one window silently."""
    frame = cleaned_frame([
        film(1, 5.0, 2010, "standalone"),
        film(2, 5.0, 1999, "standalone", release_year=None, release_date=None),
    ], settings)
    assert int(compare_groups(frame, GROUP_STRICT, min_year=2000)["films"].sum()) == 1
    assert int(compare_groups(frame, GROUP_STRICT, min_year=None)["films"].sum()) == 2


# --------------------------------------------------------------------------
# The flip check
# --------------------------------------------------------------------------

def test_a_flip_on_the_median_is_detected(settings):
    """Franchise ahead across all years, behind in the modern window."""
    frame = cleaned_frame([
        film(1, 30.0, 1980, "franchise", 10), film(2, 25.0, 1985, "franchise", 10),
        film(3, 2.0, 2010, "franchise", 10), film(4, 2.0, 2012, "franchise", 10),
        film(5, 4.0, 1990, "standalone"), film(6, 9.0, 2011, "standalone"),
        film(7, 8.0, 2013, "standalone"),
    ], settings)
    flips = flip_check(by_window(frame, settings, GROUP_STRICT), GROUP_STRICT)
    median_row = flips.loc[flips["measure"] == "median_roi"].iloc[0]

    assert median_row["flipped"]
    assert median_row["winner_all_years"] == "franchise"
    assert median_row["winner_modern"] == "standalone"


def test_for_spread_the_lower_number_wins(settings):
    """A tighter group is the safer buy, so iqr must not be read like a median."""
    frame = cleaned_frame([
        film(1, 5.0, 2001, "franchise", 10), film(2, 5.5, 2002, "franchise", 10),
        film(3, 6.0, 2003, "franchise", 10),
        film(4, 1.5, 2004, "standalone"), film(5, 9.0, 2005, "standalone"),
        film(6, 20.0, 2006, "standalone"),
    ], settings)
    tables = by_window(frame, settings, GROUP_STRICT)
    flips = flip_check(tables, GROUP_STRICT)
    spread = flips.loc[flips["measure"] == "iqr_roi"].iloc[0]

    assert spread["better_is"] == "lower"
    assert spread["winner_all_years"] == "franchise"


def test_every_measure_is_checked_not_just_the_median(settings):
    frame = cleaned_frame([
        film(1, 6.0, 2001, "franchise", 10), film(2, 3.0, 2002, "standalone"),
    ], settings)
    flips = flip_check(by_window(frame, settings, GROUP_STRICT), GROUP_STRICT)
    assert set(flips["measure"]) == {"median_roi", "floor_roi", "hit_rate_roi", "iqr_roi"}


def test_a_flip_is_announced_loudly_and_a_hold_is_stated_plainly():
    flipped = pd.DataFrame({"measure": ["iqr_roi"], "flipped": [True]})
    held = pd.DataFrame({"measure": ["median_roi"], "flipped": [False]})

    assert any("FLIPS BETWEEN WINDOWS" in line for line in announce_flip(flipped))
    assert any("iqr_roi" in line for line in announce_flip(flipped))
    assert any("No measure flips" in line for line in announce_flip(held))


# --------------------------------------------------------------------------
# Position within a franchise
# --------------------------------------------------------------------------

def test_position_is_ranked_by_release_date(settings):
    frame = cleaned_frame([
        film(1, 9.0, 1999, "franchise", 10, release_date="1999-05-01"),
        film(2, 5.0, 2002, "franchise", 10, release_date="2002-05-01"),
        film(3, 3.0, 2005, "franchise", 10, release_date="2005-05-01"),
    ], settings)
    table = position_within_franchise(frame).set_index("position")

    assert table.loc["first", "median_roi"] == 9.0
    assert table.loc["middle", "median_roi"] == 5.0
    assert table.loc["last", "median_roi"] == 3.0


def test_a_two_film_collection_has_no_middle_and_is_excluded(settings):
    """Including it would put its second film in 'last' and change what last means."""
    frame = cleaned_frame([
        film(1, 9.0, 1999, "franchise", 10), film(2, 3.0, 2002, "franchise", 10),
        film(3, 8.0, 1998, "franchise", 11, release_date="1998-01-01"),
        film(4, 5.0, 2001, "franchise", 11, release_date="2001-01-01"),
        film(5, 2.0, 2004, "franchise", 11, release_date="2004-01-01"),
    ], settings)
    table = position_within_franchise(frame, min_entries=3)
    assert int(table["films"].sum()) == 3
    assert table["collections"].max() == 1


def test_position_table_is_ordered_first_middle_last(settings):
    frame = cleaned_frame([
        film(i, 5.0, 2000 + i, "franchise", 10, release_date=f"{2000+i}-01-01")
        for i in range(1, 4)
    ], settings)
    assert position_within_franchise(frame)["position"].tolist() == [
        "first", "middle", "last"
    ]


def test_no_collections_gives_an_empty_table_not_a_crash(settings):
    frame = cleaned_frame([film(1, 5.0, 2000, "standalone")], settings)
    assert position_within_franchise(frame).empty


# --------------------------------------------------------------------------
# Bundle economics
# --------------------------------------------------------------------------

def test_a_bundle_is_buyable_only_with_enough_films_on_the_list(settings):
    frame = cleaned_frame([
        film(1, 6.0, 2001, "franchise", 10), film(2, 4.0, 2002, "franchise", 10),
        film(3, 9.0, 2003, "lone_collection_member", 11),
    ], settings)
    table = bundle_table(frame, settings).set_index("collection_name")

    assert bool(table.loc["Collection 10", "is_buyable_bundle"]) is True
    assert bool(table.loc["Collection 11", "is_buyable_bundle"]) is False


def test_bundle_roi_uses_totals_not_an_average_of_ratios(settings):
    """A bundle is bought whole, so its return is total revenue over total budget."""
    frame = cleaned_frame([
        film(1, 10.0, 2001, "franchise", 10), film(2, 2.0, 2002, "franchise", 10),
    ], settings)
    row = bundle_table(frame, settings).iloc[0]

    assert row["bundle_roi"] == 6.0              # 120m revenue / 20m budget
    assert row["median_roi"] == 6.0
    assert row["floor_roi"] == 2.0


def test_the_concentration_number_shows_what_carries_a_bundle(settings):
    """Question 6: one film at 90% of revenue is a different buy from four equal ones."""
    frame = cleaned_frame([
        film(1, 1.0, 2001, "franchise", 10, revenue=900_000_000),
        film(2, 1.0, 2002, "franchise", 10, revenue=50_000_000),
        film(3, 1.0, 2003, "franchise", 10, revenue=50_000_000),
    ], settings)
    row = gap_to_best_entry(frame).iloc[0]
    assert row["best_share_of_revenue"] == 0.9


# --------------------------------------------------------------------------
# Talent
# --------------------------------------------------------------------------

def directors_frame(rows):
    """rows of (tmdb_id, person_id, person_name)"""
    return pd.DataFrame({
        "tmdb_id": pd.array([r[0] for r in rows], dtype="Int64"),
        "person_id": pd.array([r[1] for r in rows], dtype="Int64"),
        "person_name": [r[2] for r in rows],
    })


def test_the_film_count_is_always_visible_even_below_the_minimum(settings):
    """A 3-film record and an 8-film record are not the same evidence."""
    frame = cleaned_frame([
        film(1, 9.0, 2001, "standalone"), film(2, 8.0, 2002, "standalone"),
        film(3, 7.0, 2003, "standalone"),
    ], settings)
    credits = directors_frame([
        (1, 500, "Prolific"), (2, 500, "Prolific"), (3, 500, "Prolific"),
        (1, 501, "One Film"),
    ])
    table = talent_table(credits, frame, settings, "director").set_index("person_name")

    assert table.loc["One Film", "films"] == 1
    assert bool(table.loc["One Film", "meets_min_films"]) is False
    assert bool(table.loc["Prolific", "meets_min_films"]) is True
    assert "One Film" in table.index, "a thin record was hidden rather than labelled"


def test_a_co_directed_film_counts_for_both_directors(settings):
    frame = cleaned_frame([film(1, 5.0, 2001, "standalone")], settings)
    credits = directors_frame([(1, 500, "Lana"), (1, 501, "Lilly")])
    table = talent_table(credits, frame, settings, "director")

    assert table["films"].tolist() == [1, 1]
    assert set(table["person_name"]) == {"Lana", "Lilly"}


def test_above_overall_median_is_measured_against_the_whole_pool(settings):
    frame = cleaned_frame([
        film(1, 10.0, 2001, "standalone"), film(2, 2.0, 2002, "standalone"),
        film(3, 2.0, 2003, "standalone"),
    ], settings)
    credits = directors_frame([(1, 500, "Good"), (2, 501, "Weak"), (3, 501, "Weak")])
    table = talent_table(credits, frame, settings, "director").set_index("person_name")

    assert bool(table.loc["Good", "above_overall_median"]) is True
    assert bool(table.loc["Weak", "above_overall_median"]) is False


def test_leads_are_reshaped_to_the_same_shape_as_directors(settings):
    frame = cleaned_frame([film(1, 5.0, 2001, "standalone")], settings)
    credits = leads_as_credits(frame)

    assert list(credits.columns) == ["tmdb_id", "person_id", "person_name"]
    assert talent_table(credits, frame, settings, "lead_actor")["role"].item() == "lead_actor"


def test_a_credit_for_a_film_out_of_money_metrics_is_dropped_not_counted(settings):
    frame = cleaned_frame([
        film(1, 5.0, 2001, "standalone"),
        film(2, 0, 2002, "standalone", revenue=0, budget=0),
    ], settings)
    credits = directors_frame([(1, 500, "Director"), (2, 500, "Director")])
    assert talent_table(credits, frame, settings, "director")["films"].item() == 1


# --------------------------------------------------------------------------
# The shortlist
# --------------------------------------------------------------------------

def test_the_shortlist_marks_selections_and_keeps_runners_up(settings):
    frame = cleaned_frame([
        film(1, 9.0, 2001, "franchise", 10), film(2, 8.0, 2002, "franchise", 10),
        film(3, 7.0, 2003, "franchise", 11), film(4, 6.0, 2004, "franchise", 11),
        film(5, 5.0, 2005, "franchise", 12), film(6, 4.0, 2006, "franchise", 12),
        film(7, 12.0, 2007, "standalone"), film(8, 11.0, 2008, "standalone"),
        film(9, 10.0, 2009, "standalone"),
    ], settings)
    picks = shortlist(frame, bundle_table(frame, settings), settings)

    assert int(picks["franchises"]["selected"].sum()) == 2
    assert len(picks["franchises"]) == 3
    assert int(picks["standalones"]["selected"].sum()) == 2
    assert len(picks["standalones"]) == 3


def test_an_unbuyable_bundle_cannot_be_shortlisted(settings):
    """A collection with one film on offer is not a bundle, whatever its ROI."""
    frame = cleaned_frame([
        film(1, 99.0, 2001, "lone_collection_member", 11),
        film(2, 6.0, 2002, "franchise", 10), film(3, 5.0, 2003, "franchise", 10),
    ], settings)
    picks = shortlist(frame, bundle_table(frame, settings), settings)
    assert "Collection 11" not in set(picks["franchises"]["collection_name"])


def test_the_shortlist_shows_the_franchise_status_it_selected_on(settings):
    """3 of the real 5 "standalone" picks are lone collection members - label it."""
    frame = cleaned_frame([
        film(1, 9.0, 2001, "lone_collection_member", 11),
        film(2, 8.0, 2002, "standalone"),
    ], settings)
    picks = shortlist(frame, bundle_table(frame, settings), settings)
    assert "franchise_status" in picks["standalones"].columns
    assert set(picks["standalones"]["franchise_status"]) == {
        "lone_collection_member", "standalone"
    }


def test_the_shortlist_carries_the_numbers_that_justify_each_pick(settings):
    frame = cleaned_frame([
        film(1, 6.0, 2001, "franchise", 10), film(2, 4.0, 2002, "franchise", 10),
        film(3, 9.0, 2003, "standalone"),
    ], settings)
    picks = shortlist(frame, bundle_table(frame, settings), settings)

    assert {"median_roi", "floor_roi", "best_roi", "films_on_list"} <= set(
        picks["franchises"].columns
    )
    assert {"roi", "revenue", "vote_count", "rating_reliable"} <= set(
        picks["standalones"].columns
    )


# --------------------------------------------------------------------------
# The loose grouping runs through the same code
# --------------------------------------------------------------------------

def test_the_alternative_grouping_uses_the_same_function(settings):
    frame = cleaned_frame([
        film(1, 6.0, 2001, "franchise", 10),
        film(2, 9.0, 2002, "lone_collection_member", 11),
        film(3, 3.0, 2003, "standalone"),
    ], settings)
    strict = compare_groups(frame, GROUP_STRICT)
    loose = compare_groups(frame, GROUP_LOOSE)

    assert strict.set_index(GROUP_STRICT).loc["standalone", "films"] == 2
    assert loose.set_index(GROUP_LOOSE).loc["franchise", "films"] == 2
    assert list(strict.columns)[1:] == list(loose.columns)[1:]
