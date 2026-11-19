"""Tests for the validate stage: profiling, verdicts, and the cleaning flags.

The stage exists to tell a real extreme from an error, and then to exclude a
film from one metric without removing it from the analysis. Both are judgements
that produce no error when they go wrong, so the tests pin the behaviour rather
than the output: nothing is ever deleted, a 70x return survives, a zero does
not, and a relative measure recomputed in the wrong pool is caught.
"""
from __future__ import annotations

import pytest

import pandas as pd

from pipeline.config import Settings
from pipeline.validate import (
    MONEY_MISSING,
    MONEY_TOO_SMALL,
    MONEY_USABLE,
    MONEY_ZERO_AS_MISSING,
    MONEY_ZERO_AS_REAL,
    VERDICT_CHECK,
    VERDICT_ERROR,
    VERDICT_REAL,
    VERDICT_UNRELIABLE,
    add_franchise_groupings,
    add_hit_flags,
    add_money_quality,
    add_rating_reliability,
    assert_clean,
    assert_profile,
    build_exclusions,
    classify_money,
    clean,
    duplicate_titles,
    era_comparability,
    find_flags,
    profile_table,
    sensitivity_table,
    summarise_flags,
    update_ledger,
)

# ==========================================================================
# What was tests/test_profile.py — the profile half of this stage
# ==========================================================================

@pytest.fixture
def settings_profile(tmp_path):
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


def analysis_frame_profile(rows: list[dict]) -> pd.DataFrame:
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

def test_a_seventy_times_return_is_a_real_extreme_not_an_error(settings_profile):
    """Star Wars: 11m budget, 775m revenue. The most informative row on the list."""
    flags = find_flags(analysis_frame_profile([
        {"tmdb_id": 11, "title": "Star Wars", "release_year": 1977,
         "budget": 11_000_000, "revenue": 775_398_007},
    ]), settings_profile)

    assert verdicts(flags, "roi_extreme") == [VERDICT_REAL]
    assert VERDICT_ERROR not in flags["verdict"].tolist()
    assert "not comparable" in flags.loc[flags["flag"] == "roi_extreme", "why"].item()


def test_a_budget_of_five_is_an_error(settings_profile):
    """Same distance from typical, opposite verdict."""
    flags = find_flags(analysis_frame_profile([
        {"tmdb_id": 999, "title": "Mis-entered", "budget": 5},
    ]), settings_profile)

    assert verdicts(flags, "money_implausibly_small") == [VERDICT_ERROR]
    assert "millions rather than units" in flags["why"].iloc[0]


def test_nothing_is_ever_deleted_by_this_stage(settings_profile):
    """Flags are a separate table. The analysis frame is untouched."""
    analysis = analysis_frame_profile([
        {"tmdb_id": 11, "title": "Star Wars", "budget": 11_000_000,
         "revenue": 775_398_007, "release_year": 1977},
        {"tmdb_id": 999, "title": "Broken", "budget": 0},
    ])
    before = analysis.copy()
    flags = find_flags(analysis, settings_profile)

    assert len(flags) > 0
    pd.testing.assert_frame_equal(analysis, before)


# --------------------------------------------------------------------------
# Money: errors
# --------------------------------------------------------------------------

def test_a_zero_budget_is_an_error_not_a_number(settings_profile):
    flags = find_flags(analysis_frame_profile([{"budget": 0}]), settings_profile)
    assert verdicts(flags, "money_zero") == [VERDICT_ERROR]
    assert "disguised null" in flags.loc[flags["flag"] == "money_zero", "why"].item()


def test_missing_money_is_flagged_separately_from_zero(settings_profile):
    flags = find_flags(analysis_frame_profile([
        {"tmdb_id": 1, "budget": 0}, {"tmdb_id": 2, "budget": None},
    ]), settings_profile)
    assert set(flags["flag"]) >= {"money_zero", "money_missing"}
    assert len(flags.loc[flags["flag"] == "money_missing"]) == 1


def test_both_money_columns_are_checked(settings_profile):
    flags = find_flags(analysis_frame_profile([{"budget": 0, "revenue": 0}]), settings_profile)
    assert set(flags.loc[flags["flag"] == "money_zero", "column"]) == {"budget", "revenue"}


# --------------------------------------------------------------------------
# Money: real extremes
# --------------------------------------------------------------------------

def test_revenue_below_budget_is_real_and_says_why_it_matters(settings_profile):
    """A flop is evidence for CL1's floor argument, not a value to remove."""
    flags = find_flags(analysis_frame_profile([
        {"title": "Lost Money", "budget": 100_000_000, "revenue": 40_000_000},
    ]), settings_profile)

    assert verdicts(flags, "revenue_below_budget") == [VERDICT_REAL]
    assert "CL1" in flags.loc[flags["flag"] == "revenue_below_budget", "why"].item()


def test_an_ordinary_film_raises_no_money_flag(settings_profile):
    """A profile that flags everything flags nothing."""
    flags = find_flags(analysis_frame_profile([{}]), settings_profile)
    assert flags.empty


def test_the_extreme_roi_note_depends_on_the_era(settings_profile):
    """A pre-2000 70x and a modern 70x do not mean the same thing."""
    flags = find_flags(analysis_frame_profile([
        {"tmdb_id": 1, "title": "Old", "release_year": 1977,
         "budget": 1_000_000, "revenue": 100_000_000},
        {"tmdb_id": 2, "title": "New", "release_year": 2015,
         "budget": 1_000_000, "revenue": 100_000_000},
    ]), settings_profile)
    why = dict(zip(flags["tmdb_id"], flags["why"]))

    assert "re-releases" in why[1]
    assert "re-releases" not in why[2]
    assert set(flags["verdict"]) == {VERDICT_REAL}


# --------------------------------------------------------------------------
# Ratings, runtime, status
# --------------------------------------------------------------------------

def test_a_rating_on_few_votes_is_unreliable_not_wrong(settings_profile):
    flags = find_flags(analysis_frame_profile([
        {"vote_average": 9.1, "vote_count": 40},
    ]), settings_profile)

    assert verdicts(flags, "rating_on_few_votes") == [VERDICT_UNRELIABLE]
    assert "must not be used to rank" in flags["why"].iloc[0]


def test_a_well_supported_rating_is_not_flagged(settings_profile):
    flags = find_flags(analysis_frame_profile([{"vote_average": 9.1, "vote_count": 25_000}]),
                       settings_profile)
    assert flags.empty


def test_an_odd_runtime_is_a_check_not_a_verdict(settings_profile):
    """Nothing is excluded on a 'check'. Toy Story is 81 minutes and fine."""
    flags = find_flags(analysis_frame_profile([
        {"tmdb_id": 1, "title": "Short", "runtime": 45},
        {"tmdb_id": 2, "title": "Boxed set?", "runtime": 400},
    ]), settings_profile)

    assert set(flags["verdict"]) == {VERDICT_CHECK}
    assert set(flags["flag"]) == {"runtime_short", "runtime_long"}


def test_an_unreleased_film_is_an_error(settings_profile):
    flags = find_flags(analysis_frame_profile([{"status": "Post Production"}]), settings_profile)
    assert verdicts(flags, "not_released") == [VERDICT_ERROR]


def test_a_future_release_date_is_an_error(settings_profile):
    flags = find_flags(analysis_frame_profile([{"release_year": 2099}]), settings_profile)
    assert verdicts(flags, "release_in_the_future") == [VERDICT_ERROR]


# --------------------------------------------------------------------------
# The profile table
# --------------------------------------------------------------------------

def test_the_profile_counts_zeros_separately_from_nulls():
    """A zero budget would never appear in a null count. That is the whole point."""
    frame = analysis_frame_profile([
        {"tmdb_id": 1, "budget": 0}, {"tmdb_id": 2, "budget": None},
        {"tmdb_id": 3, "budget": 50_000_000},
    ])
    profile = profile_table(frame, ["budget"]).set_index("column")

    assert profile.loc["budget", "n_zero"] == 1
    assert profile.loc["budget", "n_missing"] == 1
    assert profile.loc["budget", "n"] == 2


def test_the_profile_reports_percentiles_not_a_standard_deviation():
    """A sigma rule on skewed money is how a real extreme gets called an error."""
    profile = profile_table(analysis_frame_profile([{}]), ["budget"])
    assert {"p05", "p25", "median", "p75", "p95"} <= set(profile.columns)
    assert "std" not in profile.columns
    assert "mean" not in profile.columns


def test_the_profile_handles_text_columns_without_inventing_statistics():
    profile = profile_table(analysis_frame_profile([{}]), ["title"]).set_index("column")
    assert pd.isna(profile.loc["title", "median"])
    assert profile.loc["title", "n_distinct"] == 1


def test_a_column_that_does_not_exist_is_skipped_not_fatal():
    profile = profile_table(analysis_frame_profile([{}]), ["budget", "nonexistent"])
    assert profile["column"].tolist() == ["budget"]


# --------------------------------------------------------------------------
# Era comparability
# --------------------------------------------------------------------------

def test_era_comparability_separates_the_two_windows():
    frame = analysis_frame_profile([
        {"tmdb_id": 1, "release_year": 1977, "budget": 11_000_000, "revenue": 775_000_000},
        {"tmdb_id": 2, "release_year": 1980, "budget": 18_000_000, "revenue": 538_000_000},
        {"tmdb_id": 3, "release_year": 2015, "budget": 200_000_000, "revenue": 800_000_000},
    ])
    eras = era_comparability(frame).set_index("era")

    assert eras.loc["pre-2000", "films"] == 2
    assert eras.loc["2000+", "films"] == 1
    assert eras.loc["pre-2000", "median_roi"] > eras.loc["2000+", "median_roi"]


def test_era_comparability_on_an_empty_frame_returns_an_empty_table():
    empty = analysis_frame_profile([{}]).iloc[0:0]
    assert era_comparability(empty).empty


# --------------------------------------------------------------------------
# Duplicate titles — what id deduplication cannot catch
# --------------------------------------------------------------------------

def test_two_ids_for_one_title_and_year_are_surfaced():
    frame = analysis_frame_profile([
        {"tmdb_id": 1, "title": "The Thing", "release_year": 1982},
        {"tmdb_id": 2, "title": "the thing ", "release_year": 1982},
        {"tmdb_id": 3, "title": "Other", "release_year": 1982},
    ])
    duplicates = duplicate_titles(frame)
    assert set(duplicates["tmdb_id"]) == {1, 2}


def test_a_remake_is_not_treated_as_a_duplicate():
    """Same title, different year: two different films."""
    frame = analysis_frame_profile([
        {"tmdb_id": 1, "title": "The Thing", "release_year": 1982},
        {"tmdb_id": 2, "title": "The Thing", "release_year": 2011},
    ])
    assert duplicate_titles(frame).empty


# --------------------------------------------------------------------------
# Assertions and the summary
# --------------------------------------------------------------------------

def test_a_clean_profile_says_so_rather_than_staying_silent(settings_profile):
    """A check that found nothing must report that it ran."""
    analysis = analysis_frame_profile([{}])
    notes = assert_profile(analysis, find_flags(analysis, settings_profile))
    assert any("absent, and that is a result" in note for note in notes)


def test_every_flag_must_carry_a_reason(settings_profile):
    analysis = analysis_frame_profile([{"budget": 0}])
    flags = find_flags(analysis, settings_profile)
    flags.loc[0, "why"] = ""
    with pytest.raises(AssertionError, match="no reason recorded"):
        assert_profile(analysis, flags)


def test_a_flag_for_an_unknown_film_is_a_hard_failure(settings_profile):
    analysis = analysis_frame_profile([{"tmdb_id": 550}])
    flags = find_flags(analysis_frame_profile([{"tmdb_id": 999, "budget": 0}]), settings_profile)
    with pytest.raises(AssertionError, match="films not in the analysis"):
        assert_profile(analysis, flags)


def test_the_summary_groups_by_verdict_then_flag(settings_profile):
    flags = find_flags(analysis_frame_profile([
        {"tmdb_id": 1, "budget": 0},
        {"tmdb_id": 2, "budget": 0},
        {"tmdb_id": 3, "vote_count": 10},
    ]), settings_profile)
    summary = summarise_flags(flags)

    assert set(summary["verdict"]) == {VERDICT_ERROR, VERDICT_UNRELIABLE}
    assert summary.loc[summary["flag"] == "money_zero", "films"].item() == 2


def test_an_empty_flag_table_summarises_without_raising():
    assert summarise_flags(pd.DataFrame()).empty

# ==========================================================================
# What was tests/test_clean.py — the clean half of this stage
# ==========================================================================

def make_settings(tmp_path, **overrides):
    performance = {
        "treat_zero_money_as_missing": True,
        "min_budget_for_roi": 1_000_000,
        "hit_roi_threshold": 2.5,
        "hit_definition": "roi",
        "report_all_hit_definitions": True,
    }
    performance.update(overrides.pop("performance", {}))
    return Settings(
        raw={
            "paths": {"processed_dir": "data/processed", "interim_dir": "data/interim"},
            "performance": performance,
            "profile": {"min_votes_for_reliable_rating": 1000},
            "franchise": {"min_members_on_list": 2},
            **overrides,
        },
        root=tmp_path,
    )


@pytest.fixture
def settings_clean(tmp_path):
    return make_settings(tmp_path)


def analysis_frame_clean(rows: list[dict]) -> pd.DataFrame:
    default = {
        "tmdb_id": 550, "title": "Fight Club", "budget": 10_000_000,
        "revenue": 50_000_000, "vote_count": 27_000, "vote_average": 8.4,
        "release_year": 1999, "franchise_status": "standalone",
    }
    frame = pd.DataFrame([{**default, **row} for row in rows])
    for column in ("tmdb_id", "budget", "revenue", "vote_count", "release_year"):
        frame[column] = frame[column].astype("Int64")
    return frame


# --------------------------------------------------------------------------
# The rule that holds the whole stage together
# --------------------------------------------------------------------------

def test_cleaning_adds_columns_and_never_removes_a_row(settings_clean):
    analysis = analysis_frame_clean([
        {"tmdb_id": 1}, {"tmdb_id": 2, "budget": 0},
        {"tmdb_id": 3, "budget": None, "revenue": None},
        {"tmdb_id": 4, "vote_count": 12},
    ])
    cleaned = clean(analysis, settings_clean)

    assert len(cleaned) == 4
    assert set(analysis["tmdb_id"]) == set(cleaned["tmdb_id"])
    assert set(analysis.columns) <= set(cleaned.columns)


def test_a_film_excluded_from_money_is_still_in_every_other_metric(settings_clean):
    """Exclusion is per metric. A global filter would shrink the film count."""
    cleaned = clean(analysis_frame_clean([
        {"tmdb_id": 1, "budget": 0, "vote_count": 27_000},
    ]), settings_clean)
    row = cleaned.iloc[0]

    assert row["in_money_metrics"] is False or row["in_money_metrics"] == False
    assert pd.isna(row["roi"])
    assert bool(row["rating_reliable"]) is True
    assert row["franchise_group_strict"] == "standalone"


def test_roi_exists_exactly_where_the_film_is_in_money_metrics(settings_clean):
    analysis = analysis_frame_clean([
        {"tmdb_id": 1}, {"tmdb_id": 2, "budget": 0},
        {"tmdb_id": 3, "revenue": None},
    ])
    cleaned = clean(analysis, settings_clean)
    assert assert_clean(cleaned, analysis, build_exclusions(cleaned, settings_clean))

    usable = cleaned["in_money_metrics"].fillna(False)
    assert cleaned.loc[usable, "roi"].notna().all()
    assert cleaned.loc[~usable, "roi"].isna().all()


def test_an_roi_on_an_excluded_film_is_a_hard_failure(settings_clean):
    """Nothing downstream may average a ratio that was never valid."""
    analysis = analysis_frame_clean([{"budget": 0}])
    cleaned = clean(analysis, settings_clean)
    cleaned.loc[0, "roi"] = 99.0
    with pytest.raises(AssertionError, match="has an ROI"):
        assert_clean(cleaned, analysis, build_exclusions(cleaned, settings_clean))


# --------------------------------------------------------------------------
# The invisible bug
# --------------------------------------------------------------------------

def test_a_relative_hit_flag_must_be_recomputed_inside_each_window(settings_clean):
    """Inheriting "above median" across windows compares against the wrong pool.

    Four films: two old with high ROI, two modern with lower ROI. Computed over
    all four, neither modern film is above the median. Computed within the
    modern window, one of them is — and that is the correct answer to "is this
    an above-median performer for its era?".
    """
    analysis = analysis_frame_clean([
        {"tmdb_id": 1, "release_year": 1977, "budget": 1_000_000, "revenue": 70_000_000},
        {"tmdb_id": 2, "release_year": 1980, "budget": 1_000_000, "revenue": 50_000_000},
        {"tmdb_id": 3, "release_year": 2010, "budget": 1_000_000, "revenue": 4_000_000},
        {"tmdb_id": 4, "release_year": 2015, "budget": 1_000_000, "revenue": 2_000_000},
    ])
    everything = add_hit_flags(add_money_quality(analysis, settings_clean), settings_clean)
    inherited = everything.loc[everything["release_year"] >= 2000, "is_hit_above_median"]
    assert inherited.tolist() == [False, False], "pool-wide flags favour the old films"

    modern = everything.loc[everything["release_year"] >= 2000].copy()
    recomputed = add_hit_flags(modern, settings_clean)["is_hit_above_median"]
    assert recomputed.tolist() == [True, False], "recomputing uses the right pool"


def test_the_absolute_hit_flag_is_safe_to_carry_between_windows(settings_clean):
    """is_hit_roi depends on no pool, which is why it is the one that travels."""
    analysis = analysis_frame_clean([
        {"tmdb_id": 1, "release_year": 1977, "budget": 1_000_000, "revenue": 70_000_000},
        {"tmdb_id": 2, "release_year": 2015, "budget": 1_000_000, "revenue": 2_000_000},
    ])
    everything = add_hit_flags(add_money_quality(analysis, settings_clean), settings_clean)
    modern = add_hit_flags(
        everything.loc[everything["release_year"] >= 2000].copy(), settings_clean
    )
    assert everything.loc[1, "is_hit_roi"] == modern["is_hit_roi"].item()


def test_the_three_hit_definitions_can_disagree(settings_clean):
    """Which is the point of reporting all three."""
    analysis = analysis_frame_clean([
        {"tmdb_id": i, "budget": 1_000_000, "revenue": revenue}
        for i, revenue in enumerate([2_000_000, 3_000_000, 10_000_000, 90_000_000], 1)
    ])
    cleaned = clean(analysis, settings_clean)

    assert cleaned["is_hit_roi"].fillna(False).tolist() == [False, True, True, True]
    assert cleaned["is_hit_top_quartile"].fillna(False).sum() < \
        cleaned["is_hit_roi"].fillna(False).sum()


# --------------------------------------------------------------------------
# Money quality
# --------------------------------------------------------------------------

def test_a_zero_means_what_the_setting_says_it_means():
    """The same figure, two defensible readings, and the setting decides."""
    assert classify_money(0, 5_000_000, True, 1_000_000) == MONEY_ZERO_AS_MISSING
    assert classify_money(0, 5_000_000, False, 1_000_000) == MONEY_ZERO_AS_REAL


def test_missing_is_not_the_same_class_as_zero():
    assert classify_money(None, 5_000_000, True, 1_000_000) == MONEY_MISSING
    assert classify_money(0, 5_000_000, True, 1_000_000) != MONEY_MISSING


def test_a_tiny_budget_is_excluded_as_unstable_not_as_wrong():
    assert classify_money(50_000, 5_000_000, True, 1_000_000) == MONEY_TOO_SMALL
    assert classify_money(2_000_000, 5_000_000, True, 1_000_000) == MONEY_USABLE


def test_every_film_gets_exactly_one_money_class(settings_clean):
    cleaned = add_money_quality(analysis_frame_clean([
        {"tmdb_id": 1}, {"tmdb_id": 2, "budget": 0}, {"tmdb_id": 3, "budget": None},
        {"tmdb_id": 4, "budget": 50_000},
    ]), settings_clean)
    assert cleaned["money_quality"].notna().all()
    assert int(cleaned["money_quality"].value_counts().sum()) == 4


# --------------------------------------------------------------------------
# Ratings
# --------------------------------------------------------------------------

def test_a_thin_rating_keeps_the_film_and_loses_the_ranking(settings_clean):
    cleaned = add_rating_reliability(analysis_frame_clean([
        {"tmdb_id": 1, "vote_count": 40}, {"tmdb_id": 2, "vote_count": 27_000},
    ]), settings_clean)

    assert cleaned["rating_reliable"].tolist() == [False, True]
    assert len(cleaned) == 2
    assert cleaned["vote_average"].notna().all(), "the rating itself was not removed"


def test_a_missing_vote_count_is_not_reliable(settings_clean):
    cleaned = add_rating_reliability(
        analysis_frame_clean([{"vote_count": None}]), settings_clean
    )
    assert bool(cleaned["rating_reliable"].item()) is False


# --------------------------------------------------------------------------
# The franchise split, both ways
# --------------------------------------------------------------------------

def test_lone_members_move_between_the_two_groupings():
    frame = add_franchise_groupings(analysis_frame_clean([
        {"tmdb_id": 1, "franchise_status": "franchise"},
        {"tmdb_id": 2, "franchise_status": "lone_collection_member"},
        {"tmdb_id": 3, "franchise_status": "standalone"},
    ]))
    assert frame["franchise_group_strict"].tolist() == [
        "franchise", "standalone", "standalone"
    ]
    assert frame["franchise_group_loose"].tolist() == [
        "franchise", "franchise", "standalone"
    ]


def test_both_groupings_label_every_film():
    frame = add_franchise_groupings(analysis_frame_clean([
        {"tmdb_id": 1, "franchise_status": "franchise"},
        {"tmdb_id": 2, "franchise_status": "lone_collection_member"},
    ]))
    for column in ("franchise_group_strict", "franchise_group_loose"):
        assert frame[column].notna().all()
        assert set(frame[column]) <= {"franchise", "standalone"}


# --------------------------------------------------------------------------
# Exclusions name the setting responsible
# --------------------------------------------------------------------------

def test_every_exclusion_names_the_setting_that_caused_it(settings_clean):
    """An exclusion nobody can trace to a switch looks like a bug."""
    cleaned = clean(analysis_frame_clean([
        {"tmdb_id": 1, "budget": 0}, {"tmdb_id": 2, "vote_count": 12},
    ]), settings_clean)
    exclusions = build_exclusions(cleaned, settings_clean)

    assert len(exclusions) == 2
    assert (exclusions["setting"].str.len() > 0).all()
    assert (exclusions["reason"].str.len() > 0).all()
    assert set(exclusions["metric"]) == {
        "money (roi, revenue, budget)", "rating (ranking only)"
    }


def test_a_clean_frame_excludes_nobody(settings_clean):
    cleaned = clean(analysis_frame_clean([{"tmdb_id": 1}, {"tmdb_id": 2}]), settings_clean)
    assert build_exclusions(cleaned, settings_clean).empty


def test_a_dormant_rule_is_reported_as_dormant(settings_clean):
    """A setting that silently does nothing is worse than one documented as idle."""
    analysis = analysis_frame_clean([{"tmdb_id": 1}, {"tmdb_id": 2}])
    cleaned = clean(analysis, settings_clean)
    notes = assert_clean(cleaned, analysis, build_exclusions(cleaned, settings_clean))
    assert any("dormant" in note for note in notes)


# --------------------------------------------------------------------------
# The sensitivity table
# --------------------------------------------------------------------------

def test_the_sensitivity_table_runs_every_choice_both_ways(settings_clean):
    analysis = analysis_frame_clean([
        {"tmdb_id": 1, "franchise_status": "franchise", "revenue": 60_000_000},
        {"tmdb_id": 2, "franchise_status": "franchise", "revenue": 40_000_000},
        {"tmdb_id": 3, "franchise_status": "lone_collection_member", "revenue": 90_000_000},
        {"tmdb_id": 4, "franchise_status": "standalone", "revenue": 20_000_000},
        {"tmdb_id": 5, "franchise_status": "standalone", "revenue": 30_000_000},
    ])
    table = sensitivity_table(analysis, settings_clean)

    assert set(table["parameter"]) == {
        "performance.treat_zero_money_as_missing",
        "franchise.min_members_on_list",
        "performance.min_budget_for_roi",
    }
    assert len(table) == 6
    assert table["franchise_n"].notna().all()


def test_moving_the_lone_members_changes_the_groups_it_compares(settings_clean):
    analysis = analysis_frame_clean([
        {"tmdb_id": 1, "franchise_status": "franchise", "revenue": 60_000_000},
        {"tmdb_id": 2, "franchise_status": "lone_collection_member", "revenue": 90_000_000},
        {"tmdb_id": 3, "franchise_status": "standalone", "revenue": 20_000_000},
    ])
    table = sensitivity_table(analysis, settings_clean)
    rows = table.loc[table["parameter"] == "franchise.min_members_on_list"]

    strict = rows.loc[rows["value"].str.startswith("2")].iloc[0]
    loose = rows.loc[rows["value"].str.startswith("1")].iloc[0]
    assert strict["franchise_n"] == 1 and strict["standalone_n"] == 2
    assert loose["franchise_n"] == 2 and loose["standalone_n"] == 1


def test_the_sensitivity_table_reports_whether_the_direction_holds(settings_clean):
    analysis = analysis_frame_clean([
        {"tmdb_id": 1, "franchise_status": "franchise", "revenue": 90_000_000},
        {"tmdb_id": 2, "franchise_status": "standalone", "revenue": 20_000_000},
    ])
    table = sensitivity_table(analysis, settings_clean)
    assert "franchise_ahead" in table.columns
    assert table["franchise_ahead"].dropna().all()


# --------------------------------------------------------------------------
# Back to the ledger
# --------------------------------------------------------------------------

def test_the_ledger_column_reserved_at_stage_one_gets_filled(settings_clean):
    """Stage 1 created it empty with "decided at stage 6". This is stage 6."""
    ledger = pd.DataFrame({
        "source_row": [1, 2, 3, 4],
        "tmdb_id": pd.array([None, 550, 155, None], dtype="Int64"),
        "status": ["header_row", "fetched", "fetched", "invalid_id"],
        "in_money_metrics": pd.array([None] * 4, dtype="boolean"),
    })
    cleaned = clean(analysis_frame_clean([
        {"tmdb_id": 550}, {"tmdb_id": 155, "budget": 0},
    ]), settings_clean)
    updated = update_ledger(ledger, cleaned)

    by_row = updated.set_index("source_row")
    assert by_row.loc[2, "in_money_metrics"] == True       # noqa: E712
    assert by_row.loc[3, "in_money_metrics"] == False      # noqa: E712
    assert pd.isna(by_row.loc[1, "in_money_metrics"])      # the header row
    assert pd.isna(by_row.loc[4, "in_money_metrics"])      # never had an id
    assert str(updated["in_money_metrics"].dtype) == "boolean"


def test_a_duplicate_row_is_not_flagged_as_entering_the_money_metrics(settings_clean):
    """The same bug stage 4's accounting made: a duplicate shares its id.

    Mapping by id alone marks every duplicate True, and the ledger then claims
    more rows entered the money metrics than there are films.
    """
    ledger = pd.DataFrame({
        "source_row": [1, 2, 3],
        "tmdb_id": pd.array([None, 550, 550], dtype="Int64"),
        "status": ["header_row", "fetched", "duplicate"],
        "in_money_metrics": pd.array([None] * 3, dtype="boolean"),
    })
    updated = update_ledger(ledger, clean(analysis_frame_clean([{"tmdb_id": 550}]), settings_clean))
    by_row = updated.set_index("source_row")

    assert by_row.loc[2, "in_money_metrics"] == True       # noqa: E712
    assert pd.isna(by_row.loc[3, "in_money_metrics"]), "the duplicate was counted too"
    assert int(updated["in_money_metrics"].fillna(False).sum()) == 1


def test_updating_the_ledger_does_not_lose_a_row(settings_clean):
    ledger = pd.DataFrame({
        "source_row": [1, 2],
        "tmdb_id": pd.array([None, 550], dtype="Int64"),
        "status": ["header_row", "fetched"],
        "in_money_metrics": pd.array([None, None], dtype="boolean"),
    })
    updated = update_ledger(ledger, clean(analysis_frame_clean([{"tmdb_id": 550}]), settings_clean))
    assert len(updated) == len(ledger)
