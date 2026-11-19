"""Stage 5 tests.

The thing being tested here is a judgement, not a calculation: whether a value
that looks wrong *is* wrong. So the tests come in pairs — a figure that cannot
be right must be an `error`, and a figure that is merely astonishing must be a
`real_extreme` and survive.

The pair that matters most is Star Wars against a budget of 5. Both are far
outside anything typical. One is the most informative film on the list and the
other is a data entry mistake, and no threshold on its own can tell them apart.
"""
from __future__ import annotations

import pandas as pd
import pytest

from streamvault.config import Settings
from streamvault.profile import (
    VERDICT_CHECK,
    VERDICT_ERROR,
    VERDICT_REAL,
    VERDICT_UNRELIABLE,
    assert_profile,
    duplicate_titles,
    era_comparability,
    find_flags,
    profile_table,
    summarise_flags,
)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        raw={
            "paths": {"processed_dir": "data/processed"},
            "profile": {
                "min_plausible_budget": 100_000,
                "min_plausible_revenue": 100_000,
                "min_votes_for_reliable_rating": 1000,
                "min_feature_runtime": 70,
                "max_plausible_runtime": 300,
                "extreme_roi": 20.0,
                "flop_roi": 1.0,
                "use_popularity_as_performance": False,
            },
        },
        root=tmp_path,
    )


def analysis_frame(rows: list[dict]) -> pd.DataFrame:
    """The columns stage 5 reads, with sensible defaults."""
    default = {
        "tmdb_id": 550, "title": "Fight Club", "status": "Released",
        "budget": 63_000_000, "revenue": 100_853_753, "runtime": 139,
        "vote_average": 8.4, "vote_count": 27_000, "popularity": 61.4,
        "release_year": 1999,
    }
    frame = pd.DataFrame([{**default, **row} for row in rows])
    for column, dtype in (
        ("tmdb_id", "Int64"), ("budget", "Int64"), ("revenue", "Int64"),
        ("runtime", "Int64"), ("vote_count", "Int64"), ("release_year", "Int64"),
    ):
        frame[column] = frame[column].astype(dtype)
    return frame


def verdicts(flags: pd.DataFrame, flag: str) -> list[str]:
    return flags.loc[flags["flag"] == flag, "verdict"].tolist()


# --------------------------------------------------------------------------
# The pair that defines this stage
# --------------------------------------------------------------------------

def test_a_seventy_times_return_is_a_real_extreme_not_an_error(settings):
    """Star Wars: 11m budget, 775m revenue. The most informative row on the list."""
    flags = find_flags(analysis_frame([
        {"tmdb_id": 11, "title": "Star Wars", "release_year": 1977,
         "budget": 11_000_000, "revenue": 775_398_007},
    ]), settings)

    assert verdicts(flags, "roi_extreme") == [VERDICT_REAL]
    assert VERDICT_ERROR not in flags["verdict"].tolist()
    assert "not comparable" in flags.loc[flags["flag"] == "roi_extreme", "why"].item()


def test_a_budget_of_five_is_an_error(settings):
    """Same distance from typical, opposite verdict."""
    flags = find_flags(analysis_frame([
        {"tmdb_id": 999, "title": "Mis-entered", "budget": 5},
    ]), settings)

    assert verdicts(flags, "money_implausibly_small") == [VERDICT_ERROR]
    assert "millions rather than units" in flags["why"].iloc[0]


def test_nothing_is_ever_deleted_by_this_stage(settings):
    """Flags are a separate table. The analysis frame is untouched."""
    analysis = analysis_frame([
        {"tmdb_id": 11, "title": "Star Wars", "budget": 11_000_000,
         "revenue": 775_398_007, "release_year": 1977},
        {"tmdb_id": 999, "title": "Broken", "budget": 0},
    ])
    before = analysis.copy()
    flags = find_flags(analysis, settings)

    assert len(flags) > 0
    pd.testing.assert_frame_equal(analysis, before)


# --------------------------------------------------------------------------
# Money: errors
# --------------------------------------------------------------------------

def test_a_zero_budget_is_an_error_not_a_number(settings):
    flags = find_flags(analysis_frame([{"budget": 0}]), settings)
    assert verdicts(flags, "money_zero") == [VERDICT_ERROR]
    assert "disguised null" in flags.loc[flags["flag"] == "money_zero", "why"].item()


def test_missing_money_is_flagged_separately_from_zero(settings):
    flags = find_flags(analysis_frame([
        {"tmdb_id": 1, "budget": 0}, {"tmdb_id": 2, "budget": None},
    ]), settings)
    assert set(flags["flag"]) >= {"money_zero", "money_missing"}
    assert len(flags.loc[flags["flag"] == "money_missing"]) == 1


def test_both_money_columns_are_checked(settings):
    flags = find_flags(analysis_frame([{"budget": 0, "revenue": 0}]), settings)
    assert set(flags.loc[flags["flag"] == "money_zero", "column"]) == {"budget", "revenue"}


# --------------------------------------------------------------------------
# Money: real extremes
# --------------------------------------------------------------------------

def test_revenue_below_budget_is_real_and_says_why_it_matters(settings):
    """A flop is evidence for CL1's floor argument, not a value to remove."""
    flags = find_flags(analysis_frame([
        {"title": "Lost Money", "budget": 100_000_000, "revenue": 40_000_000},
    ]), settings)

    assert verdicts(flags, "revenue_below_budget") == [VERDICT_REAL]
    assert "CL1" in flags.loc[flags["flag"] == "revenue_below_budget", "why"].item()


def test_an_ordinary_film_raises_no_money_flag(settings):
    """A profile that flags everything flags nothing."""
    flags = find_flags(analysis_frame([{}]), settings)
    assert flags.empty


def test_the_extreme_roi_note_depends_on_the_era(settings):
    """A pre-2000 70x and a modern 70x do not mean the same thing."""
    flags = find_flags(analysis_frame([
        {"tmdb_id": 1, "title": "Old", "release_year": 1977,
         "budget": 1_000_000, "revenue": 100_000_000},
        {"tmdb_id": 2, "title": "New", "release_year": 2015,
         "budget": 1_000_000, "revenue": 100_000_000},
    ]), settings)
    why = dict(zip(flags["tmdb_id"], flags["why"]))

    assert "re-releases" in why[1]
    assert "re-releases" not in why[2]
    assert set(flags["verdict"]) == {VERDICT_REAL}


# --------------------------------------------------------------------------
# Ratings, runtime, status
# --------------------------------------------------------------------------

def test_a_rating_on_few_votes_is_unreliable_not_wrong(settings):
    flags = find_flags(analysis_frame([
        {"vote_average": 9.1, "vote_count": 40},
    ]), settings)

    assert verdicts(flags, "rating_on_few_votes") == [VERDICT_UNRELIABLE]
    assert "must not be used to rank" in flags["why"].iloc[0]


def test_a_well_supported_rating_is_not_flagged(settings):
    flags = find_flags(analysis_frame([{"vote_average": 9.1, "vote_count": 25_000}]),
                       settings)
    assert flags.empty


def test_an_odd_runtime_is_a_check_not_a_verdict(settings):
    """Nothing is excluded on a 'check'. Toy Story is 81 minutes and fine."""
    flags = find_flags(analysis_frame([
        {"tmdb_id": 1, "title": "Short", "runtime": 45},
        {"tmdb_id": 2, "title": "Boxed set?", "runtime": 400},
    ]), settings)

    assert set(flags["verdict"]) == {VERDICT_CHECK}
    assert set(flags["flag"]) == {"runtime_short", "runtime_long"}


def test_an_unreleased_film_is_an_error(settings):
    flags = find_flags(analysis_frame([{"status": "Post Production"}]), settings)
    assert verdicts(flags, "not_released") == [VERDICT_ERROR]


def test_a_future_release_date_is_an_error(settings):
    flags = find_flags(analysis_frame([{"release_year": 2099}]), settings)
    assert verdicts(flags, "release_in_the_future") == [VERDICT_ERROR]


# --------------------------------------------------------------------------
# The profile table
# --------------------------------------------------------------------------

def test_the_profile_counts_zeros_separately_from_nulls():
    """A zero budget would never appear in a null count. That is the whole point."""
    frame = analysis_frame([
        {"tmdb_id": 1, "budget": 0}, {"tmdb_id": 2, "budget": None},
        {"tmdb_id": 3, "budget": 50_000_000},
    ])
    profile = profile_table(frame, ["budget"]).set_index("column")

    assert profile.loc["budget", "n_zero"] == 1
    assert profile.loc["budget", "n_missing"] == 1
    assert profile.loc["budget", "n"] == 2


def test_the_profile_reports_percentiles_not_a_standard_deviation():
    """A sigma rule on skewed money is how a real extreme gets called an error."""
    profile = profile_table(analysis_frame([{}]), ["budget"])
    assert {"p05", "p25", "median", "p75", "p95"} <= set(profile.columns)
    assert "std" not in profile.columns
    assert "mean" not in profile.columns


def test_the_profile_handles_text_columns_without_inventing_statistics():
    profile = profile_table(analysis_frame([{}]), ["title"]).set_index("column")
    assert pd.isna(profile.loc["title", "median"])
    assert profile.loc["title", "n_distinct"] == 1


def test_a_column_that_does_not_exist_is_skipped_not_fatal():
    profile = profile_table(analysis_frame([{}]), ["budget", "nonexistent"])
    assert profile["column"].tolist() == ["budget"]


# --------------------------------------------------------------------------
# Era comparability
# --------------------------------------------------------------------------

def test_era_comparability_separates_the_two_windows():
    frame = analysis_frame([
        {"tmdb_id": 1, "release_year": 1977, "budget": 11_000_000, "revenue": 775_000_000},
        {"tmdb_id": 2, "release_year": 1980, "budget": 18_000_000, "revenue": 538_000_000},
        {"tmdb_id": 3, "release_year": 2015, "budget": 200_000_000, "revenue": 800_000_000},
    ])
    eras = era_comparability(frame).set_index("era")

    assert eras.loc["pre-2000", "films"] == 2
    assert eras.loc["2000+", "films"] == 1
    assert eras.loc["pre-2000", "median_roi"] > eras.loc["2000+", "median_roi"]


def test_era_comparability_on_an_empty_frame_returns_an_empty_table():
    empty = analysis_frame([{}]).iloc[0:0]
    assert era_comparability(empty).empty


# --------------------------------------------------------------------------
# Duplicate titles — what id deduplication cannot catch
# --------------------------------------------------------------------------

def test_two_ids_for_one_title_and_year_are_surfaced():
    frame = analysis_frame([
        {"tmdb_id": 1, "title": "The Thing", "release_year": 1982},
        {"tmdb_id": 2, "title": "the thing ", "release_year": 1982},
        {"tmdb_id": 3, "title": "Other", "release_year": 1982},
    ])
    duplicates = duplicate_titles(frame)
    assert set(duplicates["tmdb_id"]) == {1, 2}


def test_a_remake_is_not_treated_as_a_duplicate():
    """Same title, different year: two different films."""
    frame = analysis_frame([
        {"tmdb_id": 1, "title": "The Thing", "release_year": 1982},
        {"tmdb_id": 2, "title": "The Thing", "release_year": 2011},
    ])
    assert duplicate_titles(frame).empty


# --------------------------------------------------------------------------
# Assertions and the summary
# --------------------------------------------------------------------------

def test_a_clean_profile_says_so_rather_than_staying_silent(settings):
    """A check that found nothing must report that it ran."""
    analysis = analysis_frame([{}])
    notes = assert_profile(analysis, find_flags(analysis, settings))
    assert any("absent, and that is a result" in note for note in notes)


def test_every_flag_must_carry_a_reason(settings):
    analysis = analysis_frame([{"budget": 0}])
    flags = find_flags(analysis, settings)
    flags.loc[0, "why"] = ""
    with pytest.raises(AssertionError, match="no reason recorded"):
        assert_profile(analysis, flags)


def test_a_flag_for_an_unknown_film_is_a_hard_failure(settings):
    analysis = analysis_frame([{"tmdb_id": 550}])
    flags = find_flags(analysis_frame([{"tmdb_id": 999, "budget": 0}]), settings)
    with pytest.raises(AssertionError, match="films not in the analysis"):
        assert_profile(analysis, flags)


def test_the_summary_groups_by_verdict_then_flag(settings):
    flags = find_flags(analysis_frame([
        {"tmdb_id": 1, "budget": 0},
        {"tmdb_id": 2, "budget": 0},
        {"tmdb_id": 3, "vote_count": 10},
    ]), settings)
    summary = summarise_flags(flags)

    assert set(summary["verdict"]) == {VERDICT_ERROR, VERDICT_UNRELIABLE}
    assert summary.loc[summary["flag"] == "money_zero", "films"].item() == 2


def test_an_empty_flag_table_summarises_without_raising():
    assert summarise_flags(pd.DataFrame()).empty
