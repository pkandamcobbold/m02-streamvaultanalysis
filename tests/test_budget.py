"""Stage 8 tests.

Two things can go wrong here and neither raises. The boundary can quietly
include acquisition, which makes the analysis look twenty times slower than it
is and measures the wifi. And the projection can be a multiplication dressed up
as a measurement.

So the tests check the boundary holds, the shares reconcile, the fitted
exponent recovers a known scaling law, and the fallback to linear happens
openly rather than by fitting noise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from streamvault.budget import (
    ACQUISITION_STAGE,
    ANALYSIS_STAGES,
    assert_budget,
    describe_scaling,
    fit_exponent,
    project,
    project_acquisition,
    time_budget,
)
from streamvault.config import Settings


@pytest.fixture
def settings(tmp_path):
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

def test_acquisition_is_outside_the_budget(settings):
    """Including it would measure TMDb's latency, not this code."""
    budget = time_budget(timings_frame([
        ("1_ingest", 0.02), (ACQUISITION_STAGE, 20.3, 117),
        ("3_flatten", 1.0), ("4_join", 0.1), ("5_profile", 0.1),
        ("6_clean", 0.1), ("7_kpis", 0.2),
    ]), settings)
    by_stage = budget.set_index("stage")

    assert bool(by_stage.loc[ACQUISITION_STAGE, "in_budget"]) is False
    assert budget.attrs["analysis_seconds"] == 1.5
    assert "network-bound" in by_stage.loc[ACQUISITION_STAGE, "note"]


def test_ingest_is_reported_but_outside_the_stated_boundary(settings):
    budget = time_budget(timings_frame([
        ("1_ingest", 0.02), ("3_flatten", 1.0), ("4_join", 0.1),
        ("5_profile", 0.1), ("6_clean", 0.1), ("7_kpis", 0.2),
    ]), settings)
    row = budget.set_index("stage").loc["1_ingest"]

    assert bool(row["in_budget"]) is False
    assert "completeness" in row["note"]
    assert "1_ingest" in set(budget["stage"]), "it was dropped rather than labelled"


def test_the_stage_shares_sum_to_one(settings):
    budget = time_budget(timings_frame([
        ("3_flatten", 1.0), ("4_join", 0.5), ("5_profile", 0.25),
        ("6_clean", 0.25), ("7_kpis", 1.0),
    ]), settings)
    shares = budget["share_of_analysis"].dropna().astype(float)

    # Shares are rounded to 3dp for reading, so they sum to 1.0 only within
    # rounding error. The production assertion allows 0.01 for this reason;
    # demanding exactness here would be a test of float formatting, not of the
    # boundary.
    assert abs(shares.sum() - 1.0) < 0.01
    assert len(shares) == len(ANALYSIS_STAGES)
    assert assert_budget(budget, pd.DataFrame()) is not None


def test_an_incoherent_boundary_is_a_hard_failure(settings):
    budget = time_budget(timings_frame([
        ("3_flatten", 1.0), ("4_join", 1.0),
    ]), settings)
    budget.loc[0, "share_of_analysis"] = 0.9      # no longer sums to 1
    with pytest.raises(AssertionError, match="boundary is inconsistent"):
        assert_budget(budget, pd.DataFrame())


def test_acquisition_inside_the_budget_is_a_hard_failure(settings):
    budget = time_budget(timings_frame([
        ("3_flatten", 1.0), (ACQUISITION_STAGE, 20.0, 117),
    ]), settings)
    budget.loc[budget["stage"] == ACQUISITION_STAGE, "in_budget"] = True
    with pytest.raises(AssertionError, match="acquisition is inside the budget"):
        assert_budget(budget, pd.DataFrame())


def test_only_the_most_recent_run_is_budgeted(settings):
    """A budget averaged over history describes no run that ever happened."""
    old = timings_frame([("3_flatten", 9.0)], run_at="2026-11-18T12:00:00+00:00")
    new = timings_frame([("3_flatten", 1.0)], run_at="2026-11-19T12:00:00+00:00")
    budget = time_budget(pd.concat([old, new], ignore_index=True), settings)

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


def test_a_linear_stage_projects_by_the_ratio_of_film_counts(settings):
    scaling = scaling_frame("3_flatten", [25, 50, 75, 100], [0.25, 0.5, 0.75, 1.0])
    row = project(scaling, settings, measured_total=100).iloc[0]

    assert row["exponent_k"] == pytest.approx(1.0, abs=0.01)
    assert row["projected_seconds"] == pytest.approx(5.0, rel=0.02)   # 500/100 * 1.0


def test_a_quadratic_stage_projects_far_worse_than_the_ratio(settings):
    """The whole reason for measuring instead of multiplying."""
    films = [25, 50, 75, 100]
    seconds = [(f ** 2) * 1e-4 for f in films]
    row = project(scaling_frame("7_kpis", films, seconds), settings,
                  measured_total=100).iloc[0]

    assert row["exponent_k"] == pytest.approx(2.0, abs=0.02)
    naive = row["measured_seconds"] * 5
    assert row["projected_seconds"] > naive * 4


def test_an_impossible_exponent_falls_back_to_linear_and_says_so(settings):
    """A stage cannot get faster as the data grows. If the fit says it does,
    the measurement was contaminated — so assume linear, which over-estimates
    the time, and label the row rather than publishing the impossible number.
    """
    films = [25, 50, 75, 100]
    seconds = [0.40, 0.30, 0.20, 0.10]          # faster with more data
    row = project(scaling_frame("6_clean", films, seconds), settings,
                  measured_total=100).iloc[0]

    assert row["exponent_k"] == 1.0
    assert "assumed linear" in row["fit_quality"]
    assert row["projected_seconds"] == pytest.approx(0.5, rel=0.02)


def test_a_sound_fit_is_labelled_as_measured(settings):
    scaling = scaling_frame("3_flatten", [25, 50, 75, 100], [0.25, 0.5, 0.75, 1.0])
    assert project(scaling, settings, measured_total=100).iloc[0]["fit_quality"] == "measured"


def test_the_projection_is_fitted_from_the_largest_measured_point(settings):
    scaling = scaling_frame("4_join", [25, 50, 75, 100], [0.25, 0.5, 0.75, 1.0])
    row = project(scaling, settings, measured_total=100).iloc[0]
    assert row["measured_films"] == 100
    assert row["measured_seconds"] == 1.0


def test_a_stage_with_no_measurements_is_skipped_not_guessed(settings):
    scaling = scaling_frame("3_flatten", [50, 100], [0.5, 1.0])
    projection = project(scaling, settings, measured_total=100)
    assert projection["stage"].tolist() == ["3_flatten"]
    assert set(projection["stage"]) < set(ANALYSIS_STAGES)


def test_a_projection_over_the_limit_is_reported_loudly(settings):
    films = [25, 50, 75, 100]
    scaling = pd.concat([
        scaling_frame(stage, films, [f * 0.05 for f in films])
        for stage in ANALYSIS_STAGES
    ], ignore_index=True)
    projection = project(scaling, settings, measured_total=100)
    budget = time_budget(timings_frame([("3_flatten", 1.0)]), settings)

    assert projection.attrs["projected_total"] > 10
    notes = assert_budget(budget, projection)
    assert any("PROJECTION OVER BUDGET" in note for note in notes)


def test_a_projection_within_the_limit_says_how_it_was_obtained(settings):
    films = [25, 50, 75, 100]
    scaling = pd.concat([
        scaling_frame(stage, films, [f * 0.0001 for f in films])
        for stage in ANALYSIS_STAGES
    ], ignore_index=True)
    projection = project(scaling, settings, measured_total=100)
    notes = assert_budget(time_budget(timings_frame([("3_flatten", 0.01)]), settings),
                          projection)

    assert any("measured per-stage exponents" in note for note in notes)
    assert any("not from multiplying" in note for note in notes)


def test_a_conservative_all_linear_total_is_reported_beside_the_fit(settings):
    """A sub-linear k extrapolated five-fold is optimistic; show both."""
    films = [25, 50, 75, 100]
    scaling = pd.concat([
        scaling_frame(stage, films, [0.1 + f * 1e-5 for f in films])  # near-flat
        for stage in ANALYSIS_STAGES
    ], ignore_index=True)
    projection = project(scaling, settings, measured_total=100)

    fitted = projection.attrs["projected_total"]
    conservative = projection.attrs["conservative_linear_total"]
    assert conservative > fitted, "the linear assumption should be the harsher one"
    assert conservative == pytest.approx(0.101 * 5 * 5, rel=0.05)

    notes = assert_budget(time_budget(timings_frame([("3_flatten", 0.1)]), settings),
                          projection)
    assert any("does not depend on the fit being right" in note for note in notes)


def test_the_worst_scaling_stage_is_named(settings):
    films = [25, 50, 75, 100]
    scaling = pd.concat([
        scaling_frame("3_flatten", films, [(f ** 2) * 1e-6 for f in films]),
        scaling_frame("4_join", films, [f * 1e-4 for f in films]),
    ], ignore_index=True)
    projection = project(scaling, settings, measured_total=100)
    notes = assert_budget(time_budget(timings_frame([("3_flatten", 0.01)]), settings),
                          projection)

    assert any("3_flatten" in note and "hurt first" in note for note in notes)


# --------------------------------------------------------------------------
# Acquisition, projected separately
# --------------------------------------------------------------------------

def test_acquisition_is_projected_from_the_cold_run_not_the_cached_one(settings):
    """A cached run would promise 2 seconds and deliver ninety."""
    timings = pd.concat([
        timings_frame([(ACQUISITION_STAGE, 20.0, 117)],
                      run_at="2026-11-19T10:00:00+00:00"),
        timings_frame([(ACQUISITION_STAGE, 0.4, 0)],
                      run_at="2026-11-19T11:00:00+00:00"),
    ], ignore_index=True)
    result = project_acquisition(timings, settings)

    assert result["measured"] == 20.0
    assert result["calls"] == 117
    assert result["projected_seconds"] == pytest.approx(85.5, rel=0.02)
    assert "per call" in result["basis"]


def test_with_no_cold_run_the_projection_says_so_rather_than_inventing_one(settings):
    timings = timings_frame([(ACQUISITION_STAGE, 0.4, 0)])
    result = project_acquisition(timings, settings)

    assert pd.isna(result["projected_seconds"])
    assert "no cold-cache run" in result["basis"]


def test_no_timings_at_all_is_reported_not_crashed(settings):
    empty = pd.DataFrame(columns=["run_at", "stage", "seconds", "api_calls"])
    budget = time_budget(empty, settings)
    assert budget.empty
    assert any("no timings recorded" in note
               for note in assert_budget(budget, pd.DataFrame()))
