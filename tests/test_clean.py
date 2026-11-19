"""Stage 6 tests.

Cleaning is where an analysis usually starts lying, and it does it by being
helpful: dropping the awkward rows, filling the gaps, smoothing the extremes.
Every test here is a guard against a helpful change that loses information.

The one to read first is
`test_a_relative_hit_flag_must_be_recomputed_inside_each_window`. It pins a
bug that produces no error, no warning and no visible symptom — comparing
post-2000 films against a median partly set by 1970s films.
"""
from __future__ import annotations

import pandas as pd
import pytest

from streamvault.clean import (
    MONEY_MISSING,
    MONEY_TOO_SMALL,
    MONEY_USABLE,
    MONEY_ZERO_AS_MISSING,
    MONEY_ZERO_AS_REAL,
    add_franchise_groupings,
    add_hit_flags,
    add_money_quality,
    add_rating_reliability,
    assert_clean,
    build_exclusions,
    classify_money,
    clean,
    sensitivity_table,
    update_ledger,
)
from streamvault.config import Settings


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
def settings(tmp_path):
    return make_settings(tmp_path)


def analysis_frame(rows: list[dict]) -> pd.DataFrame:
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

def test_cleaning_adds_columns_and_never_removes_a_row(settings):
    analysis = analysis_frame([
        {"tmdb_id": 1}, {"tmdb_id": 2, "budget": 0},
        {"tmdb_id": 3, "budget": None, "revenue": None},
        {"tmdb_id": 4, "vote_count": 12},
    ])
    cleaned = clean(analysis, settings)

    assert len(cleaned) == 4
    assert set(analysis["tmdb_id"]) == set(cleaned["tmdb_id"])
    assert set(analysis.columns) <= set(cleaned.columns)


def test_a_film_excluded_from_money_is_still_in_every_other_metric(settings):
    """Exclusion is per metric. A global filter would shrink the film count."""
    cleaned = clean(analysis_frame([
        {"tmdb_id": 1, "budget": 0, "vote_count": 27_000},
    ]), settings)
    row = cleaned.iloc[0]

    assert row["in_money_metrics"] is False or row["in_money_metrics"] == False
    assert pd.isna(row["roi"])
    assert bool(row["rating_reliable"]) is True
    assert row["franchise_group_strict"] == "standalone"


def test_roi_exists_exactly_where_the_film_is_in_money_metrics(settings):
    analysis = analysis_frame([
        {"tmdb_id": 1}, {"tmdb_id": 2, "budget": 0},
        {"tmdb_id": 3, "revenue": None},
    ])
    cleaned = clean(analysis, settings)
    assert assert_clean(cleaned, analysis, build_exclusions(cleaned, settings))

    usable = cleaned["in_money_metrics"].fillna(False)
    assert cleaned.loc[usable, "roi"].notna().all()
    assert cleaned.loc[~usable, "roi"].isna().all()


def test_an_roi_on_an_excluded_film_is_a_hard_failure(settings):
    """Nothing downstream may average a ratio that was never valid."""
    analysis = analysis_frame([{"budget": 0}])
    cleaned = clean(analysis, settings)
    cleaned.loc[0, "roi"] = 99.0
    with pytest.raises(AssertionError, match="has an ROI"):
        assert_clean(cleaned, analysis, build_exclusions(cleaned, settings))


# --------------------------------------------------------------------------
# The invisible bug
# --------------------------------------------------------------------------

def test_a_relative_hit_flag_must_be_recomputed_inside_each_window(settings):
    """Inheriting "above median" across windows compares against the wrong pool.

    Four films: two old with high ROI, two modern with lower ROI. Computed over
    all four, neither modern film is above the median. Computed within the
    modern window, one of them is — and that is the correct answer to "is this
    an above-median performer for its era?".
    """
    analysis = analysis_frame([
        {"tmdb_id": 1, "release_year": 1977, "budget": 1_000_000, "revenue": 70_000_000},
        {"tmdb_id": 2, "release_year": 1980, "budget": 1_000_000, "revenue": 50_000_000},
        {"tmdb_id": 3, "release_year": 2010, "budget": 1_000_000, "revenue": 4_000_000},
        {"tmdb_id": 4, "release_year": 2015, "budget": 1_000_000, "revenue": 2_000_000},
    ])
    everything = add_hit_flags(add_money_quality(analysis, settings), settings)
    inherited = everything.loc[everything["release_year"] >= 2000, "is_hit_above_median"]
    assert inherited.tolist() == [False, False], "pool-wide flags favour the old films"

    modern = everything.loc[everything["release_year"] >= 2000].copy()
    recomputed = add_hit_flags(modern, settings)["is_hit_above_median"]
    assert recomputed.tolist() == [True, False], "recomputing uses the right pool"


def test_the_absolute_hit_flag_is_safe_to_carry_between_windows(settings):
    """is_hit_roi depends on no pool, which is why it is the one that travels."""
    analysis = analysis_frame([
        {"tmdb_id": 1, "release_year": 1977, "budget": 1_000_000, "revenue": 70_000_000},
        {"tmdb_id": 2, "release_year": 2015, "budget": 1_000_000, "revenue": 2_000_000},
    ])
    everything = add_hit_flags(add_money_quality(analysis, settings), settings)
    modern = add_hit_flags(
        everything.loc[everything["release_year"] >= 2000].copy(), settings
    )
    assert everything.loc[1, "is_hit_roi"] == modern["is_hit_roi"].item()


def test_the_three_hit_definitions_can_disagree(settings):
    """Which is the point of reporting all three."""
    analysis = analysis_frame([
        {"tmdb_id": i, "budget": 1_000_000, "revenue": revenue}
        for i, revenue in enumerate([2_000_000, 3_000_000, 10_000_000, 90_000_000], 1)
    ])
    cleaned = clean(analysis, settings)

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


def test_every_film_gets_exactly_one_money_class(settings):
    cleaned = add_money_quality(analysis_frame([
        {"tmdb_id": 1}, {"tmdb_id": 2, "budget": 0}, {"tmdb_id": 3, "budget": None},
        {"tmdb_id": 4, "budget": 50_000},
    ]), settings)
    assert cleaned["money_quality"].notna().all()
    assert int(cleaned["money_quality"].value_counts().sum()) == 4


# --------------------------------------------------------------------------
# Ratings
# --------------------------------------------------------------------------

def test_a_thin_rating_keeps_the_film_and_loses_the_ranking(settings):
    cleaned = add_rating_reliability(analysis_frame([
        {"tmdb_id": 1, "vote_count": 40}, {"tmdb_id": 2, "vote_count": 27_000},
    ]), settings)

    assert cleaned["rating_reliable"].tolist() == [False, True]
    assert len(cleaned) == 2
    assert cleaned["vote_average"].notna().all(), "the rating itself was not removed"


def test_a_missing_vote_count_is_not_reliable(settings):
    cleaned = add_rating_reliability(
        analysis_frame([{"vote_count": None}]), settings
    )
    assert bool(cleaned["rating_reliable"].item()) is False


# --------------------------------------------------------------------------
# The franchise split, both ways
# --------------------------------------------------------------------------

def test_lone_members_move_between_the_two_groupings():
    frame = add_franchise_groupings(analysis_frame([
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
    frame = add_franchise_groupings(analysis_frame([
        {"tmdb_id": 1, "franchise_status": "franchise"},
        {"tmdb_id": 2, "franchise_status": "lone_collection_member"},
    ]))
    for column in ("franchise_group_strict", "franchise_group_loose"):
        assert frame[column].notna().all()
        assert set(frame[column]) <= {"franchise", "standalone"}


# --------------------------------------------------------------------------
# Exclusions name the setting responsible
# --------------------------------------------------------------------------

def test_every_exclusion_names_the_setting_that_caused_it(settings):
    """An exclusion nobody can trace to a switch looks like a bug."""
    cleaned = clean(analysis_frame([
        {"tmdb_id": 1, "budget": 0}, {"tmdb_id": 2, "vote_count": 12},
    ]), settings)
    exclusions = build_exclusions(cleaned, settings)

    assert len(exclusions) == 2
    assert (exclusions["setting"].str.len() > 0).all()
    assert (exclusions["reason"].str.len() > 0).all()
    assert set(exclusions["metric"]) == {
        "money (roi, revenue, budget)", "rating (ranking only)"
    }


def test_a_clean_frame_excludes_nobody(settings):
    cleaned = clean(analysis_frame([{"tmdb_id": 1}, {"tmdb_id": 2}]), settings)
    assert build_exclusions(cleaned, settings).empty


def test_a_dormant_rule_is_reported_as_dormant(settings):
    """A setting that silently does nothing is worse than one documented as idle."""
    analysis = analysis_frame([{"tmdb_id": 1}, {"tmdb_id": 2}])
    cleaned = clean(analysis, settings)
    notes = assert_clean(cleaned, analysis, build_exclusions(cleaned, settings))
    assert any("dormant" in note for note in notes)


# --------------------------------------------------------------------------
# The sensitivity table
# --------------------------------------------------------------------------

def test_the_sensitivity_table_runs_every_choice_both_ways(settings):
    analysis = analysis_frame([
        {"tmdb_id": 1, "franchise_status": "franchise", "revenue": 60_000_000},
        {"tmdb_id": 2, "franchise_status": "franchise", "revenue": 40_000_000},
        {"tmdb_id": 3, "franchise_status": "lone_collection_member", "revenue": 90_000_000},
        {"tmdb_id": 4, "franchise_status": "standalone", "revenue": 20_000_000},
        {"tmdb_id": 5, "franchise_status": "standalone", "revenue": 30_000_000},
    ])
    table = sensitivity_table(analysis, settings)

    assert set(table["parameter"]) == {
        "performance.treat_zero_money_as_missing",
        "franchise.min_members_on_list",
        "performance.min_budget_for_roi",
    }
    assert len(table) == 6
    assert table["franchise_n"].notna().all()


def test_moving_the_lone_members_changes_the_groups_it_compares(settings):
    analysis = analysis_frame([
        {"tmdb_id": 1, "franchise_status": "franchise", "revenue": 60_000_000},
        {"tmdb_id": 2, "franchise_status": "lone_collection_member", "revenue": 90_000_000},
        {"tmdb_id": 3, "franchise_status": "standalone", "revenue": 20_000_000},
    ])
    table = sensitivity_table(analysis, settings)
    rows = table.loc[table["parameter"] == "franchise.min_members_on_list"]

    strict = rows.loc[rows["value"].str.startswith("2")].iloc[0]
    loose = rows.loc[rows["value"].str.startswith("1")].iloc[0]
    assert strict["franchise_n"] == 1 and strict["standalone_n"] == 2
    assert loose["franchise_n"] == 2 and loose["standalone_n"] == 1


def test_the_sensitivity_table_reports_whether_the_direction_holds(settings):
    analysis = analysis_frame([
        {"tmdb_id": 1, "franchise_status": "franchise", "revenue": 90_000_000},
        {"tmdb_id": 2, "franchise_status": "standalone", "revenue": 20_000_000},
    ])
    table = sensitivity_table(analysis, settings)
    assert "franchise_ahead" in table.columns
    assert table["franchise_ahead"].dropna().all()


# --------------------------------------------------------------------------
# Back to the ledger
# --------------------------------------------------------------------------

def test_the_ledger_column_reserved_at_stage_one_gets_filled(settings):
    """Stage 1 created it empty with "decided at stage 6". This is stage 6."""
    ledger = pd.DataFrame({
        "source_row": [1, 2, 3, 4],
        "tmdb_id": pd.array([None, 550, 155, None], dtype="Int64"),
        "status": ["header_row", "fetched", "fetched", "invalid_id"],
        "in_money_metrics": pd.array([None] * 4, dtype="boolean"),
    })
    cleaned = clean(analysis_frame([
        {"tmdb_id": 550}, {"tmdb_id": 155, "budget": 0},
    ]), settings)
    updated = update_ledger(ledger, cleaned)

    by_row = updated.set_index("source_row")
    assert by_row.loc[2, "in_money_metrics"] == True       # noqa: E712
    assert by_row.loc[3, "in_money_metrics"] == False      # noqa: E712
    assert pd.isna(by_row.loc[1, "in_money_metrics"])      # the header row
    assert pd.isna(by_row.loc[4, "in_money_metrics"])      # never had an id
    assert str(updated["in_money_metrics"].dtype) == "boolean"


def test_a_duplicate_row_is_not_flagged_as_entering_the_money_metrics(settings):
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
    updated = update_ledger(ledger, clean(analysis_frame([{"tmdb_id": 550}]), settings))
    by_row = updated.set_index("source_row")

    assert by_row.loc[2, "in_money_metrics"] == True       # noqa: E712
    assert pd.isna(by_row.loc[3, "in_money_metrics"]), "the duplicate was counted too"
    assert int(updated["in_money_metrics"].fillna(False).sum()) == 1


def test_updating_the_ledger_does_not_lose_a_row(settings):
    ledger = pd.DataFrame({
        "source_row": [1, 2],
        "tmdb_id": pd.array([None, 550], dtype="Int64"),
        "status": ["header_row", "fetched"],
        "in_money_metrics": pd.array([None, None], dtype="boolean"),
    })
    updated = update_ledger(ledger, clean(analysis_frame([{"tmdb_id": 550}]), settings))
    assert len(updated) == len(ledger)
