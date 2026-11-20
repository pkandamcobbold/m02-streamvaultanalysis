"""Tests for the checks stage: the gate, the spot-check, and the time budget.

These are the tests of the things that are supposed to stop the run. So each
one asserts a refusal: the gate blocks rather than publishing with a warning
nobody reads, the budget hard-fails if acquisition is folded inside its stated
boundary, and the spot-check samples every flagged extreme rather than a sample
of them, because a check that avoids the risky rows is not a check.
"""
from __future__ import annotations

import pytest

import numpy as np
import pandas as pd

from tests.conftest import ledger_table, make_facts

from pipeline.checks import (
    GateFailed,
    enforce,
    gate,
    ACQUISITION_STAGE,
    ANALYSIS_STAGES,
    KNOWN_SLICES,
    VERDICT_DRIFT,
    VERDICT_GONE,
    VERDICT_IDENTICAL,
    VERDICT_MATERIAL,
    assert_budget,
    assert_spotcheck,
    build_sample,
    compare_film,
    describe_scaling,
    fit_exponent,
    project,
    project_acquisition,
    run_comparison,
    shortlisted_film_ids,
    summarise,
    time_budget,
    would_it_move_the_recommendation,
)
from pipeline.config import Settings

# ==========================================================================
# The time budget and the 500-title projection
# ==========================================================================

@pytest.fixture
def settings_budget(tmp_path):
    return Settings(
        raw={
            "paths": {"processed_dir": "data/processed"},
            "budget": {"analysis_seconds_limit": 10, "projection_target_titles": 500},
            "franchise": {"min_members_on_list": 2},
        },
        root=tmp_path,
    )


def timings_frame(rows, run_at="2026-11-19T12:00:00+00:00"):
    """rows of (stage, seconds) or (stage, seconds, api_calls)."""
    frame = pd.DataFrame([
        {
            "run_at": row[0] if isinstance(row[0], str) and row[0].startswith("20")
            else run_at,
            "stage": row[-3] if len(row) == 4 else row[0],
            "seconds": row[-2] if len(row) == 4 else row[1],
            "api_calls": row[-1] if len(row) >= 3 else 0,
            "cache_hits": 0, "rows": 0, "note": "",
        }
        for row in rows
    ])
    frame["api_calls"] = frame["api_calls"].astype("Int64")
    return frame


# --------------------------------------------------------------------------
# The boundary
# --------------------------------------------------------------------------

def test_acquisition_is_outside_the_budget(settings_budget):
    """Including it would measure TMDb's latency, not this code."""
    budget = time_budget(timings_frame([
        ("extract.read_ids", 0.02), (ACQUISITION_STAGE, 20.3, 117),
        ("extract.shape", 1.0), ("validate", 0.1),
        ("transform", 0.2),
    ]), settings_budget)
    by_stage = budget.set_index("stage")

    assert bool(by_stage.loc[ACQUISITION_STAGE, "in_budget"]) is False
    assert budget.attrs["analysis_seconds"] == 1.3
    assert "network-bound" in by_stage.loc[ACQUISITION_STAGE, "note"]


def test_ingest_is_reported_but_outside_the_stated_boundary(settings_budget):
    budget = time_budget(timings_frame([
        ("extract.read_ids", 0.02), ("extract.shape", 1.0), ("validate", 0.1), ("transform", 0.2),
    ]), settings_budget)
    row = budget.set_index("stage").loc["extract.read_ids"]

    assert bool(row["in_budget"]) is False
    assert "completeness" in row["note"]
    assert "extract.read_ids" in set(budget["stage"]), "it was dropped rather than labelled"


def test_the_stage_shares_sum_to_one(settings_budget):
    budget = time_budget(timings_frame([
        ("extract.shape", 1.0), ("validate", 0.25),
        ("transform", 1.0),
    ]), settings_budget)
    shares = budget["share_of_analysis"].dropna().astype(float)

    # Shares are rounded to 3dp for reading, so they sum to 1.0 only within
    # rounding error. The production assertion allows 0.01 for this reason;
    # demanding exactness here would be a test of float formatting, not of the
    # boundary.
    assert abs(shares.sum() - 1.0) < 0.01
    assert len(shares) == len(ANALYSIS_STAGES)
    assert assert_budget(budget, pd.DataFrame()) is not None


def test_an_incoherent_boundary_is_a_hard_failure(settings_budget):
    budget = time_budget(timings_frame([
        ("extract.shape", 1.0), ]), settings_budget)
    budget.loc[0, "share_of_analysis"] = 0.9      # no longer sums to 1
    with pytest.raises(AssertionError, match="boundary is inconsistent"):
        assert_budget(budget, pd.DataFrame())


def test_acquisition_inside_the_budget_is_a_hard_failure(settings_budget):
    budget = time_budget(timings_frame([
        ("extract.shape", 1.0), (ACQUISITION_STAGE, 20.0, 117),
    ]), settings_budget)
    budget.loc[budget["stage"] == ACQUISITION_STAGE, "in_budget"] = True
    with pytest.raises(AssertionError, match="acquisition is inside the budget"):
        assert_budget(budget, pd.DataFrame())


def test_only_the_most_recent_run_is_budgeted(settings_budget):
    """A budget averaged over history describes no run that ever happened."""
    old = timings_frame([("extract.shape", 9.0)], run_at="2026-11-18T12:00:00+00:00")
    new = timings_frame([("extract.shape", 1.0)], run_at="2026-11-19T12:00:00+00:00")
    budget = time_budget(pd.concat([old, new], ignore_index=True), settings_budget)

    assert len(budget) == 1
    assert budget.attrs["analysis_seconds"] == 1.0


# --------------------------------------------------------------------------
# The fitted exponent
# --------------------------------------------------------------------------

def test_the_fit_recovers_a_known_linear_law():
    films = pd.Series([25, 50, 75, 100])
    seconds = films * 0.01                       # exactly linear
    assert fit_exponent(films, seconds) == pytest.approx(1.0, abs=0.01)


def test_the_fit_recovers_a_known_quadratic_law():
    films = pd.Series([25, 50, 75, 100])
    seconds = (films.astype(float) ** 2) * 1e-4
    assert fit_exponent(films, seconds) == pytest.approx(2.0, abs=0.01)


def test_the_fit_recovers_a_sub_linear_law():
    films = pd.Series([25, 50, 75, 100])
    seconds = np.sqrt(films.astype(float)) * 0.01
    assert fit_exponent(films, seconds) == pytest.approx(0.5, abs=0.01)


def test_too_few_points_falls_back_to_linear_rather_than_fitting_noise():
    """Defaulting to linear openly beats inventing an exponent from two dots."""
    assert fit_exponent(pd.Series([50, 100]), pd.Series([0.5, 1.0])) == 1.0


def test_times_at_the_clock_resolution_fall_back_to_linear():
    films = pd.Series([25, 50, 75, 100])
    seconds = pd.Series([0.00001, 0.00002, 0.00001, 0.00002])
    assert fit_exponent(films, seconds) == 1.0


def test_the_exponent_is_described_in_words():
    assert "sub-linear" in describe_scaling(0.5)
    assert "roughly linear" in describe_scaling(1.0)
    assert "worse than linear" in describe_scaling(1.4)
    assert "sharply" in describe_scaling(2.0)


# --------------------------------------------------------------------------
# The projection
# --------------------------------------------------------------------------

def scaling_frame(stage, films, seconds):
    return pd.DataFrame({
        "films": films, "stage": [stage] * len(films), "seconds": seconds,
    })


def test_a_linear_stage_projects_by_the_ratio_of_film_counts(settings_budget):
    scaling = scaling_frame("extract.shape", [25, 50, 75, 100], [0.25, 0.5, 0.75, 1.0])
    row = project(scaling, settings_budget, measured_total=100).iloc[0]

    assert row["exponent_k"] == pytest.approx(1.0, abs=0.01)
    assert row["projected_seconds"] == pytest.approx(5.0, rel=0.02)   # 500/100 * 1.0


def test_a_quadratic_stage_projects_far_worse_than_the_ratio(settings_budget):
    """The whole reason for measuring instead of multiplying."""
    films = [25, 50, 75, 100]
    seconds = [(f ** 2) * 1e-4 for f in films]
    row = project(scaling_frame("transform", films, seconds), settings_budget,
                  measured_total=100).iloc[0]

    assert row["exponent_k"] == pytest.approx(2.0, abs=0.02)
    naive = row["measured_seconds"] * 5
    assert row["projected_seconds"] > naive * 4


def test_an_impossible_exponent_falls_back_to_linear_and_says_so(settings_budget):
    """A stage cannot get faster as the data grows. If the fit says it does,
    the measurement was contaminated — so assume linear, which over-estimates
    the time, and label the row rather than publishing the impossible number.
    """
    films = [25, 50, 75, 100]
    seconds = [0.40, 0.30, 0.20, 0.10]          # faster with more data
    row = project(scaling_frame("transform", films, seconds), settings_budget,
                  measured_total=100).iloc[0]

    assert row["exponent_k"] == 1.0
    assert "assumed linear" in row["fit_quality"]
    assert row["projected_seconds"] == pytest.approx(0.5, rel=0.02)


def test_a_sound_fit_is_labelled_as_measured(settings_budget):
    scaling = scaling_frame("extract.shape", [25, 50, 75, 100], [0.25, 0.5, 0.75, 1.0])
    assert project(scaling, settings_budget, measured_total=100).iloc[0]["fit_quality"] == "measured"


def test_the_projection_is_fitted_from_the_largest_measured_point(settings_budget):
    scaling = scaling_frame("validate", [25, 50, 75, 100], [0.25, 0.5, 0.75, 1.0])
    row = project(scaling, settings_budget, measured_total=100).iloc[0]
    assert row["measured_films"] == 100
    assert row["measured_seconds"] == 1.0


def test_a_stage_with_no_measurements_is_skipped_not_guessed(settings_budget):
    scaling = scaling_frame("extract.shape", [50, 100], [0.5, 1.0])
    projection = project(scaling, settings_budget, measured_total=100)
    assert projection["stage"].tolist() == ["extract.shape"]
    assert set(projection["stage"]) < set(ANALYSIS_STAGES)


def test_a_projection_over_the_limit_is_reported_loudly(settings_budget):
    films = [25, 50, 75, 100]
    scaling = pd.concat([
        scaling_frame(stage, films, [f * 0.05 for f in films])
        for stage in ANALYSIS_STAGES
    ], ignore_index=True)
    projection = project(scaling, settings_budget, measured_total=100)
    budget = time_budget(timings_frame([("extract.shape", 1.0)]), settings_budget)

    assert projection.attrs["projected_total"] > 10
    notes = assert_budget(budget, projection)
    assert any("PROJECTION OVER BUDGET" in note for note in notes)


def test_a_projection_within_the_limit_says_how_it_was_obtained(settings_budget):
    films = [25, 50, 75, 100]
    scaling = pd.concat([
        scaling_frame(stage, films, [f * 0.0001 for f in films])
        for stage in ANALYSIS_STAGES
    ], ignore_index=True)
    projection = project(scaling, settings_budget, measured_total=100)
    notes = assert_budget(time_budget(timings_frame([("extract.shape", 0.01)]), settings_budget),
                          projection)

    assert any("measured per-stage exponents" in note for note in notes)
    assert any("not from multiplying" in note for note in notes)


def test_a_conservative_all_linear_total_is_reported_beside_the_fit(settings_budget):
    """A sub-linear k extrapolated five-fold is optimistic; show both."""
    films = [25, 50, 75, 100]
    scaling = pd.concat([
        scaling_frame(stage, films, [0.1 + f * 1e-5 for f in films])  # near-flat
        for stage in ANALYSIS_STAGES
    ], ignore_index=True)
    projection = project(scaling, settings_budget, measured_total=100)

    fitted = projection.attrs["projected_total"]
    conservative = projection.attrs["conservative_linear_total"]
    assert conservative > fitted, "the linear assumption should be the harsher one"
    # Written in terms of the boundary rather than a literal count, so it does
    # not rot the next time a stage joins or leaves the boundary.
    assert conservative == pytest.approx(
        0.101 * len(ANALYSIS_STAGES) * 5, rel=0.05
    )

    notes = assert_budget(time_budget(timings_frame([("extract.shape", 0.1)]), settings_budget),
                          projection)
    assert any("does not depend on the fit being right" in note for note in notes)


def test_the_worst_scaling_stage_is_named(settings_budget):
    films = [25, 50, 75, 100]
    scaling = pd.concat([
        scaling_frame("extract.shape", films, [(f ** 2) * 1e-6 for f in films]),
        scaling_frame("validate", films, [f * 1e-4 for f in films]),
    ], ignore_index=True)
    projection = project(scaling, settings_budget, measured_total=100)
    notes = assert_budget(time_budget(timings_frame([("extract.shape", 0.01)]), settings_budget),
                          projection)

    assert any("extract.shape" in note and "hurt first" in note for note in notes)


# --------------------------------------------------------------------------
# Acquisition, projected separately
# --------------------------------------------------------------------------

def test_acquisition_is_projected_from_the_cold_run_not_the_cached_one(settings_budget):
    """A cached run would promise 2 seconds and deliver ninety."""
    timings = pd.concat([
        timings_frame([(ACQUISITION_STAGE, 20.0, 117)],
                      run_at="2026-11-19T10:00:00+00:00"),
        timings_frame([(ACQUISITION_STAGE, 0.4, 0)],
                      run_at="2026-11-19T11:00:00+00:00"),
    ], ignore_index=True)
    result = project_acquisition(timings, settings_budget)

    assert result["measured"] == 20.0
    assert result["calls"] == 117
    assert result["projected_seconds"] == pytest.approx(85.5, rel=0.02)
    assert "per call" in result["basis"]


def test_with_no_cold_run_the_projection_says_so_rather_than_inventing_one(settings_budget):
    timings = timings_frame([(ACQUISITION_STAGE, 0.4, 0)])
    result = project_acquisition(timings, settings_budget)

    assert pd.isna(result["projected_seconds"])
    assert "no cold-cache run" in result["basis"]


def test_no_timings_at_all_is_reported_not_crashed(settings_budget):
    empty = pd.DataFrame(columns=["run_at", "stage", "seconds", "api_calls"])
    budget = time_budget(empty, settings_budget)
    assert budget.empty
    assert any("no timings recorded" in note
               for note in assert_budget(budget, pd.DataFrame()))


def test_every_out_of_budget_stage_says_why(settings_budget):
    """A stage excluded from a judgement must say so; one simply absent from
    the table looks like a stage that never ran. Before an audit, stages 9 and
    10 were missing from the budget entirely because stage 8 ran before them.
    """
    budget = time_budget(timings_frame([
        ("extract.read_ids", 0.02), (ACQUISITION_STAGE, 20.3, 117),
        ("extract.shape", 1.0), ("validate", 0.1),
        ("transform", 0.2),
        ("checks", 1.5), ("__spotcheck", 5.0), ("load", 0.02),
    ]), settings_budget)
    out = budget.loc[~budget["in_budget"]].set_index("stage")

    assert (out["note"].str.len() > 0).all(), "an excluded stage gives no reason"
    assert "count them twice" in out.loc["checks", "note"]
    assert "network-bound by design" in out.loc["__spotcheck", "note"]
    assert "writes the reports" in out.loc["load", "note"]
    assert budget.attrs["analysis_seconds"] == 1.3      # the shaping, validate and transform stages only

# ==========================================================================
# The live spot-check against the source
# ==========================================================================

@pytest.fixture
def settings_spotcheck(tmp_path):
    return Settings(
        raw={
            "paths": {"processed_dir": "data/processed", "raw_dir": "data/raw"},
            "spotcheck": {"films_per_slice": 3, "random_seed": 20251031,
                          "always_include_flagged": True},
            "performance": {
                "treat_zero_money_as_missing": True, "min_budget_for_roi": 1_000_000,
                "hit_roi_threshold": 2.5, "hit_definition": "roi",
                "report_all_hit_definitions": True,
            },
            "profile": {"min_votes_for_reliable_rating": 1000},
            "franchise": {"min_members_on_list": 2},
        },
        root=tmp_path,
    )


def cleaned_frame_spotcheck(rows):
    default = {
        "title": "A Film", "budget": 10_000_000, "revenue": 50_000_000,
        "runtime": 120, "release_date": "1999-06-01", "release_year": 1999,
        "vote_average": 7.5, "vote_count": 20_000, "popularity": 12.3,
        "collection_id": None, "collection_name": None,
        "franchise_status": "standalone", "franchise_group_strict": "standalone",
        "franchise_group_loose": "standalone", "in_money_metrics": True,
        "roi": 5.0, "money_quality": "usable", "rating_reliable": True,
        "is_hit_roi": True, "is_hit_above_median": True, "is_hit_top_quartile": False,
    }
    frame = pd.DataFrame([{**default, **row} for row in rows])
    for column in ("tmdb_id", "budget", "revenue", "runtime", "vote_count",
                   "release_year", "collection_id"):
        frame[column] = frame[column].astype("Int64")
    frame["in_money_metrics"] = frame["in_money_metrics"].astype("boolean")
    frame["roi"] = frame["roi"].astype("Float64")
    return frame


def flags_frame(ids):
    return pd.DataFrame({
        "tmdb_id": pd.array(ids, dtype="Int64"),
        "title": [f"Film {i}" for i in ids],
        "flag": ["roi_extreme"] * len(ids),
        "verdict": ["real_extreme"] * len(ids),
        "why": ["70x"] * len(ids),
    })


def payload(tmdb_id=1, **overrides):
    base = {
        "id": tmdb_id, "title": "A Film", "budget": 10_000_000,
        "revenue": 50_000_000, "runtime": 120, "release_date": "1999-06-01",
        "vote_average": 7.5, "vote_count": 20_000, "popularity": 12.3,
        "belongs_to_collection": None,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# The sample must not avoid the rows that matter
# --------------------------------------------------------------------------

def test_every_flagged_extreme_is_sampled_not_a_sample_of_them(settings_spotcheck):
    """A random 12 of 112 would usually miss all eight. That is the failure."""
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": i} for i in range(1, 30)])
    flagged = [1, 2, 3, 4, 5, 6, 7, 8]
    sample = build_sample(cleaned, flags_frame(flagged), set(), settings_spotcheck)

    picked = set(sample.loc[sample["slice"] == "flagged_extreme", "tmdb_id"])
    assert picked == set(flagged), "the risky rows were sampled rather than all taken"


def test_turning_off_always_include_flagged_samples_instead(tmp_path):
    raw = {
        "paths": {"processed_dir": "p", "raw_dir": "r"},
        "spotcheck": {"films_per_slice": 3, "random_seed": 1,
                      "always_include_flagged": False},
    }
    settings_spotcheck = Settings(raw=raw, root=tmp_path)
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": i} for i in range(1, 30)])
    sample = build_sample(cleaned, flags_frame([1, 2, 3, 4, 5, 6, 7, 8]), set(),
                          settings_spotcheck)
    assert len(sample.loc[sample["slice"] == "flagged_extreme"]) == 3


def test_the_shortlisted_films_are_sampled_first(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": i} for i in range(1, 30)])
    sample = build_sample(cleaned, pd.DataFrame(), {11, 12}, settings_spotcheck)
    shortlisted = set(sample.loc[sample["slice"] == "shortlisted", "tmdb_id"])
    assert shortlisted == {11, 12}


def test_there_is_always_an_unbiased_control_slice(settings_spotcheck):
    """Without it, the check only looks where problems are expected."""
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": i} for i in range(1, 30)])
    sample = build_sample(cleaned, flags_frame([1, 2]), {5}, settings_spotcheck)

    assert "random_control" in set(sample["slice"])
    assert set(sample["slice"]) <= KNOWN_SLICES


def test_no_film_is_sampled_twice_across_slices(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck([
        {"tmdb_id": i, "release_year": 1980} for i in range(1, 12)
    ])
    sample = build_sample(cleaned, flags_frame([1, 2]), {1, 3}, settings_spotcheck)
    assert sample["tmdb_id"].is_unique


def test_the_sample_is_the_same_every_run(settings_spotcheck):
    """A sample that changes per run cannot be argued about."""
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": i} for i in range(1, 40)])
    first = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)
    second = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)
    assert first["tmdb_id"].tolist() == second["tmdb_id"].tolist()


def test_every_sampled_film_records_why_it_was_chosen(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": i} for i in range(1, 20)])
    sample = build_sample(cleaned, flags_frame([1]), {2}, settings_spotcheck)
    assert (sample["why_this_slice"].str.len() > 0).all()


def test_the_pre_2000_slice_only_takes_pre_2000_films(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck(
        [{"tmdb_id": i, "release_year": 1980} for i in range(1, 6)]
        + [{"tmdb_id": i, "release_year": 2015} for i in range(6, 12)]
    )
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)
    picked = sample.loc[sample["slice"] == "pre_2000", "tmdb_id"]
    assert set(picked) <= {1, 2, 3, 4, 5}


def test_shortlisted_ids_include_each_bundles_member_films():
    cleaned = cleaned_frame_spotcheck([
        {"tmdb_id": 1, "collection_name": "Star Wars Collection"},
        {"tmdb_id": 2, "collection_name": "Star Wars Collection"},
        {"tmdb_id": 3, "collection_name": "Other Collection"},
        {"tmdb_id": 9},
    ])
    shortlist = {
        "franchises": pd.DataFrame({
            "collection_name": ["Star Wars Collection", "Other Collection"],
            "selected": [True, False],
        }),
        "standalones": pd.DataFrame({
            "tmdb_id": pd.array([9], dtype="Int64"), "selected": [True],
        }),
    }
    assert shortlisted_film_ids(shortlist, cleaned) == {1, 2, 9}


# --------------------------------------------------------------------------
# Classification: drift is not the same as a discrepancy
# --------------------------------------------------------------------------

def test_an_unchanged_film_is_identical_on_every_field():
    analysed = cleaned_frame_spotcheck([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1), "random_control")
    assert {row["verdict"] for row in rows} == {VERDICT_IDENTICAL}


def test_a_changed_budget_is_material():
    analysed = cleaned_frame_spotcheck([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1, budget=99_000_000), "shortlisted")
    budget = next(row for row in rows if row["field"] == "budget")

    assert budget["verdict"] == VERDICT_MATERIAL
    assert "feeds ROI" in budget["note"]
    assert budget["analysed_value"] == 10_000_000
    assert budget["live_value"] == 99_000_000


def test_a_changed_popularity_is_drift_not_a_discrepancy():
    analysed = cleaned_frame_spotcheck([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1, popularity=80.0), "random_control")
    popularity = next(row for row in rows if row["field"] == "popularity")

    assert popularity["verdict"] == VERDICT_DRIFT
    assert "recomputed daily" in popularity["note"]


def test_a_rising_vote_count_is_drift():
    analysed = cleaned_frame_spotcheck([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1, vote_count=20_500), "pre_2000")
    votes = next(row for row in rows if row["field"] == "vote_count")
    assert votes["verdict"] == VERDICT_DRIFT


def test_a_changed_collection_is_material_because_it_moves_the_split():
    analysed = cleaned_frame_spotcheck([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(
        analysed, payload(1, belongs_to_collection={"id": 999, "name": "New"}),
        "shortlisted",
    )
    collection = next(row for row in rows if row["field"] == "collection_id")

    assert collection["verdict"] == VERDICT_MATERIAL
    assert "franchise / standalone split" in collection["note"]


def test_a_changed_release_date_is_material_because_it_moves_the_window():
    analysed = cleaned_frame_spotcheck([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1, release_date="2005-01-01"), "pre_2000")
    date = next(row for row in rows if row["field"] == "release_date")

    assert date["verdict"] == VERDICT_MATERIAL
    assert "time window" in date["note"]


def test_a_film_that_has_vanished_is_its_own_verdict():
    analysed = cleaned_frame_spotcheck([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, None, "shortlisted")

    assert len(rows) == 1
    assert rows[0]["verdict"] == VERDICT_GONE
    assert "no longer returns" in rows[0]["note"]


def test_the_comparison_covers_every_sampled_film(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)
    comparison = run_comparison(sample, cleaned, {1: payload(1), 2: payload(2)})

    assert set(comparison["tmdb_id"]) == {1, 2}
    assert comparison["field"].nunique() == 9


# --------------------------------------------------------------------------
# Does it move the recommendation?
# --------------------------------------------------------------------------

def test_with_no_material_difference_the_recommendation_is_unchanged(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck([
        {"tmdb_id": 1, "franchise_group_strict": "franchise", "roi": 6.0},
        {"tmdb_id": 2, "roi": 3.0},
    ])
    comparison = run_comparison(
        build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck), cleaned,
        {1: payload(1), 2: payload(2)},
    )
    movement = would_it_move_the_recommendation(comparison, cleaned, settings_spotcheck)

    assert movement["moved"] is False
    assert movement["substitutions"] == 0
    assert "by construction" in movement["note"]


def test_a_material_money_difference_is_substituted_and_recomputed(settings_spotcheck):
    """The only honest way to answer "does it move the answer" is to try it."""
    cleaned = cleaned_frame_spotcheck([
        {"tmdb_id": 1, "franchise_group_strict": "franchise",
         "revenue": 60_000_000, "roi": 6.0},
        {"tmdb_id": 2, "franchise_group_strict": "standalone",
         "revenue": 50_000_000, "roi": 5.0},
    ])
    comparison = pd.DataFrame([{
        "tmdb_id": 1, "title": "A Film", "slice": "shortlisted", "field": "revenue",
        "analysed_value": 60_000_000, "live_value": 10_000_000,
        "verdict": VERDICT_MATERIAL, "note": "material: feeds ROI directly",
    }])
    movement = would_it_move_the_recommendation(comparison, cleaned, settings_spotcheck)

    assert movement["substitutions"] == 1
    assert movement["winner_before"] == "franchise"
    assert movement["winner_after"] == "standalone"
    assert movement["moved"] is True


def test_drift_is_never_substituted(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck([
        {"tmdb_id": 1, "franchise_group_strict": "franchise", "roi": 6.0},
        {"tmdb_id": 2, "roi": 3.0},
    ])
    comparison = pd.DataFrame([{
        "tmdb_id": 1, "title": "A Film", "slice": "shortlisted",
        "field": "popularity", "analysed_value": 12.3, "live_value": 80.0,
        "verdict": VERDICT_DRIFT, "note": "expected",
    }])
    assert would_it_move_the_recommendation(comparison, cleaned, settings_spotcheck)[
        "substitutions"] == 0


# --------------------------------------------------------------------------
# Assertions and the summary
# --------------------------------------------------------------------------

def test_a_clean_spotcheck_says_what_it_verified(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": i} for i in range(1, 8)])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)
    comparison = run_comparison(
        sample, cleaned, {int(i): payload(int(i)) for i in sample["tmdb_id"]}
    )
    notes = assert_spotcheck(sample, comparison, settings_spotcheck)

    assert any("No material difference" in note for note in notes)
    assert any("slices" in note for note in notes)


def test_a_material_difference_is_reported_with_the_field(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)
    comparison = run_comparison(
        sample, cleaned, {1: payload(1, budget=1_000_000), 2: payload(2)}
    )
    notes = assert_spotcheck(sample, comparison, settings_spotcheck)
    assert any("changes an answer" in note and "budget" in note for note in notes)


def test_an_empty_sample_is_a_hard_failure(settings_spotcheck):
    with pytest.raises(AssertionError, match="sampled no films"):
        assert_spotcheck(pd.DataFrame(columns=["tmdb_id", "slice", "why_this_slice"]),
                         pd.DataFrame(), settings_spotcheck)


def test_a_pool_small_enough_to_be_fully_sampled_needs_no_control(settings_spotcheck):
    """Total coverage is the one case where a missing control slice is fine."""
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)

    assert len(sample) == 2
    assert "random_control" not in set(sample["slice"])
    assert_spotcheck(sample, pd.DataFrame(), settings_spotcheck)      # must not raise


def test_a_sample_with_no_control_slice_is_a_hard_failure(settings_spotcheck):
    sample = pd.DataFrame({
        "tmdb_id": pd.array([1], dtype="Int64"), "title": ["A"],
        "slice": ["shortlisted"], "why_this_slice": ["named in the memo"],
    })
    with pytest.raises(AssertionError, match="no unbiased control slice"):
        assert_spotcheck(sample, pd.DataFrame(), settings_spotcheck)


def test_the_report_is_generated_and_states_what_it_does_not_establish(
    settings_spotcheck, tmp_path
):
    """A generated report cannot drift from the check it describes."""
    from pipeline.checks import write_report

    cleaned = cleaned_frame_spotcheck([{"tmdb_id": i} for i in range(1, 8)])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)
    comparison = run_comparison(
        sample, cleaned, {int(i): payload(int(i)) for i in sample["tmdb_id"]}
    )
    movement = would_it_move_the_recommendation(comparison, cleaned, settings_spotcheck)

    path = tmp_path / "spotcheck.md"
    write_report(path, sample, comparison, summarise(comparison), movement, settings_spotcheck)
    text = path.read_text(encoding="utf-8")

    assert "does not establish" in text
    assert "weak test of *drift over time*" in text
    assert "No material difference" in text
    assert "random_control" in text
    assert "data/raw_spotcheck/" in text
    for field in ("budget", "revenue", "popularity"):
        assert f"`{field}`" in text


def test_the_report_leads_with_a_material_difference_when_there_is_one(
    settings_spotcheck, tmp_path
):
    from pipeline.checks import write_report

    cleaned = cleaned_frame_spotcheck([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)
    comparison = run_comparison(
        sample, cleaned, {1: payload(1, budget=42), 2: payload(2)}
    )
    movement = would_it_move_the_recommendation(comparison, cleaned, settings_spotcheck)

    path = tmp_path / "spotcheck.md"
    write_report(path, sample, comparison, summarise(comparison), movement, settings_spotcheck)
    text = path.read_text(encoding="utf-8")

    assert "differ materially" in text
    assert "Material differences" in text
    assert "42" in text


def test_the_summary_groups_by_slice_and_verdict(settings_spotcheck):
    cleaned = cleaned_frame_spotcheck([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings_spotcheck)
    comparison = run_comparison(
        sample, cleaned, {1: payload(1, budget=5), 2: payload(2)}
    )
    summary = summarise(comparison)

    assert {"slice", "verdict", "fields", "films"} == set(summary.columns)
    assert VERDICT_MATERIAL in set(summary["verdict"])

# ==========================================================================
# The release gate (ADR-015)
# ==========================================================================

def test_the_gate_passes_a_sound_run(memo_settings):
    results = gate(memo_settings, make_facts(memo_settings))
    assert results["passed"].all()
    enforce(results, memo_settings)              # must not raise


def test_too_few_films_blocks_the_memo(memo_settings):
    facts = make_facts(memo_settings)
    facts["films_analysed"] = 12
    results = gate(memo_settings, facts)

    assert not results["passed"].all()
    with pytest.raises(GateFailed, match="enough films to compare"):
        enforce(results, memo_settings)


def test_too_much_missing_money_blocks_the_memo(memo_settings):
    facts = make_facts(memo_settings)
    facts["missing_money_share"] = 0.5
    with pytest.raises(GateFailed, match="money data complete enough"):
        enforce(gate(memo_settings, facts), memo_settings)


def test_a_spotcheck_that_moves_the_answer_blocks_the_memo(memo_settings):
    """The whole point: a human must look before this reaches a board."""
    facts = make_facts(memo_settings)
    facts["spotcheck_moved"] = True
    with pytest.raises(GateFailed, match="live re-check"):
        enforce(gate(memo_settings, facts), memo_settings)


def test_the_accounting_cross_check_is_not_a_tautology(memo_settings):
    """It compares two independently built tables, so it can actually fail."""
    facts = make_facts(memo_settings, ledger=ledger_table(data_rows=120))
    assert facts["unaccounted_rows"] == 7
    with pytest.raises(GateFailed, match="every source row accounted for"):
        enforce(gate(memo_settings, facts), memo_settings)


def test_the_failure_message_says_what_to_do(memo_settings):
    facts = make_facts(memo_settings)
    facts["films_analysed"] = 5
    try:
        enforce(gate(memo_settings, facts), memo_settings)
    except GateFailed as error:
        message = str(error)
    assert "Nothing is wrong with your computer" in message
    assert "gate.enabled = false" in message
    assert "data_diagnosis.md" in message


def test_the_gate_can_be_turned_off_deliberately(memo_settings):
    """Skipping it should be a decision somebody can be asked about."""
    facts = make_facts(memo_settings)
    facts["films_analysed"] = 5
    memo_settings.raw["gate"]["enabled"] = False
    enforce(gate(memo_settings, facts), memo_settings)        # must not raise


def test_a_skipped_spotcheck_is_not_a_pass_and_not_a_failure(memo_settings):
    """The defect this replaced: --no-spotcheck left `spotcheck_moved` as None,
    `bool(None)` was False, and the gate reported the live re-check as *passed*
    when it had never run. It did not crash, which was worse — the run log
    recorded an unearned pass.
    """
    facts = make_facts(memo_settings)
    facts["spotcheck_moved"] = None
    results = gate(memo_settings, facts)
    row = results.loc[results["check"].str.contains("re-check")].iloc[0]

    assert row["status"] == "not_checked"
    assert bool(row["passed"]) is False, "a check that never ran must not read as passed"
    assert "did not run" in row["detail"]

    # ...and it must not block publication either.
    enforce(results, memo_settings)


def test_a_spotcheck_that_moved_the_answer_still_blocks(memo_settings):
    facts = make_facts(memo_settings)
    facts["spotcheck_moved"] = True
    results = gate(memo_settings, facts)
    row = results.loc[results["check"].str.contains("re-check")].iloc[0]

    assert row["status"] == "fail"
    with pytest.raises(GateFailed, match="re-check"):
        enforce(results, memo_settings)


def test_only_a_failure_blocks_never_a_skip(memo_settings):
    """`~passed` would have blocked on a skip, making --no-spotcheck unusable."""
    facts = make_facts(memo_settings)
    facts["spotcheck_moved"] = None
    results = gate(memo_settings, facts)

    assert (~results["passed"]).any(), "the skipped row is not marked passed"
    assert (results["status"] == "fail").sum() == 0
    enforce(results, memo_settings)        # must not raise


def test_every_gate_row_carries_one_of_the_three_statuses(memo_settings):
    for moved in (False, True, None):
        facts = make_facts(memo_settings)
        facts["spotcheck_moved"] = moved
        results = gate(memo_settings, facts)
        assert set(results["status"]) <= {"pass", "fail", "not_checked"}
        # `passed` is derived from `status`, never set independently.
        assert (results["passed"] == (results["status"] == "pass")).all()
