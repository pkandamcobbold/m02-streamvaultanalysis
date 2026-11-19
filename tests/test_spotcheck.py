"""Stage 9 tests.

A spot-check can fail in two directions and both look like success.

It can **avoid the risky rows** — a random sample of 12 from 112 will usually
miss all eight extreme-ROI films, report "no discrepancies" and have checked
nothing that mattered. So the sampling is stratified and tested.

And it can **wave a real difference through** as drift, because `popularity`
moving is normal and it is tempting to treat all movement the same way. So the
field classification is decided in advance and tested per field.

No test here touches the network: the live payloads are passed in.
"""
from __future__ import annotations

import pandas as pd
import pytest

from streamvault.config import Settings
from streamvault.spotcheck import (
    KNOWN_SLICES,
    VERDICT_DRIFT,
    VERDICT_GONE,
    VERDICT_IDENTICAL,
    VERDICT_MATERIAL,
    assert_spotcheck,
    build_sample,
    compare_film,
    run_comparison,
    shortlisted_film_ids,
    summarise,
    would_it_move_the_recommendation,
)


@pytest.fixture
def settings(tmp_path):
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


def cleaned_frame(rows):
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

def test_every_flagged_extreme_is_sampled_not_a_sample_of_them(settings):
    """A random 12 of 112 would usually miss all eight. That is the failure."""
    cleaned = cleaned_frame([{"tmdb_id": i} for i in range(1, 30)])
    flagged = [1, 2, 3, 4, 5, 6, 7, 8]
    sample = build_sample(cleaned, flags_frame(flagged), set(), settings)

    picked = set(sample.loc[sample["slice"] == "flagged_extreme", "tmdb_id"])
    assert picked == set(flagged), "the risky rows were sampled rather than all taken"


def test_turning_off_always_include_flagged_samples_instead(tmp_path):
    raw = {
        "paths": {"processed_dir": "p", "raw_dir": "r"},
        "spotcheck": {"films_per_slice": 3, "random_seed": 1,
                      "always_include_flagged": False},
    }
    settings = Settings(raw=raw, root=tmp_path)
    cleaned = cleaned_frame([{"tmdb_id": i} for i in range(1, 30)])
    sample = build_sample(cleaned, flags_frame([1, 2, 3, 4, 5, 6, 7, 8]), set(),
                          settings)
    assert len(sample.loc[sample["slice"] == "flagged_extreme"]) == 3


def test_the_shortlisted_films_are_sampled_first(settings):
    cleaned = cleaned_frame([{"tmdb_id": i} for i in range(1, 30)])
    sample = build_sample(cleaned, pd.DataFrame(), {11, 12}, settings)
    shortlisted = set(sample.loc[sample["slice"] == "shortlisted", "tmdb_id"])
    assert shortlisted == {11, 12}


def test_there_is_always_an_unbiased_control_slice(settings):
    """Without it, the check only looks where problems are expected."""
    cleaned = cleaned_frame([{"tmdb_id": i} for i in range(1, 30)])
    sample = build_sample(cleaned, flags_frame([1, 2]), {5}, settings)

    assert "random_control" in set(sample["slice"])
    assert set(sample["slice"]) <= KNOWN_SLICES


def test_no_film_is_sampled_twice_across_slices(settings):
    cleaned = cleaned_frame([
        {"tmdb_id": i, "release_year": 1980} for i in range(1, 12)
    ])
    sample = build_sample(cleaned, flags_frame([1, 2]), {1, 3}, settings)
    assert sample["tmdb_id"].is_unique


def test_the_sample_is_the_same_every_run(settings):
    """A sample that changes per run cannot be argued about."""
    cleaned = cleaned_frame([{"tmdb_id": i} for i in range(1, 40)])
    first = build_sample(cleaned, pd.DataFrame(), set(), settings)
    second = build_sample(cleaned, pd.DataFrame(), set(), settings)
    assert first["tmdb_id"].tolist() == second["tmdb_id"].tolist()


def test_every_sampled_film_records_why_it_was_chosen(settings):
    cleaned = cleaned_frame([{"tmdb_id": i} for i in range(1, 20)])
    sample = build_sample(cleaned, flags_frame([1]), {2}, settings)
    assert (sample["why_this_slice"].str.len() > 0).all()


def test_the_pre_2000_slice_only_takes_pre_2000_films(settings):
    cleaned = cleaned_frame(
        [{"tmdb_id": i, "release_year": 1980} for i in range(1, 6)]
        + [{"tmdb_id": i, "release_year": 2015} for i in range(6, 12)]
    )
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings)
    picked = sample.loc[sample["slice"] == "pre_2000", "tmdb_id"]
    assert set(picked) <= {1, 2, 3, 4, 5}


def test_shortlisted_ids_include_each_bundles_member_films():
    cleaned = cleaned_frame([
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
    analysed = cleaned_frame([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1), "random_control")
    assert {row["verdict"] for row in rows} == {VERDICT_IDENTICAL}


def test_a_changed_budget_is_material():
    analysed = cleaned_frame([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1, budget=99_000_000), "shortlisted")
    budget = next(row for row in rows if row["field"] == "budget")

    assert budget["verdict"] == VERDICT_MATERIAL
    assert "feeds ROI" in budget["note"]
    assert budget["analysed_value"] == 10_000_000
    assert budget["live_value"] == 99_000_000


def test_a_changed_popularity_is_drift_not_a_discrepancy():
    analysed = cleaned_frame([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1, popularity=80.0), "random_control")
    popularity = next(row for row in rows if row["field"] == "popularity")

    assert popularity["verdict"] == VERDICT_DRIFT
    assert "recomputed daily" in popularity["note"]


def test_a_rising_vote_count_is_drift():
    analysed = cleaned_frame([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1, vote_count=20_500), "pre_2000")
    votes = next(row for row in rows if row["field"] == "vote_count")
    assert votes["verdict"] == VERDICT_DRIFT


def test_a_changed_collection_is_material_because_it_moves_the_split():
    analysed = cleaned_frame([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(
        analysed, payload(1, belongs_to_collection={"id": 999, "name": "New"}),
        "shortlisted",
    )
    collection = next(row for row in rows if row["field"] == "collection_id")

    assert collection["verdict"] == VERDICT_MATERIAL
    assert "franchise / standalone split" in collection["note"]


def test_a_changed_release_date_is_material_because_it_moves_the_window():
    analysed = cleaned_frame([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, payload(1, release_date="2005-01-01"), "pre_2000")
    date = next(row for row in rows if row["field"] == "release_date")

    assert date["verdict"] == VERDICT_MATERIAL
    assert "time window" in date["note"]


def test_a_film_that_has_vanished_is_its_own_verdict():
    analysed = cleaned_frame([{"tmdb_id": 1}]).iloc[0]
    rows = compare_film(analysed, None, "shortlisted")

    assert len(rows) == 1
    assert rows[0]["verdict"] == VERDICT_GONE
    assert "no longer returns" in rows[0]["note"]


def test_the_comparison_covers_every_sampled_film(settings):
    cleaned = cleaned_frame([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings)
    comparison = run_comparison(sample, cleaned, {1: payload(1), 2: payload(2)})

    assert set(comparison["tmdb_id"]) == {1, 2}
    assert comparison["field"].nunique() == 9


# --------------------------------------------------------------------------
# Does it move the recommendation?
# --------------------------------------------------------------------------

def test_with_no_material_difference_the_recommendation_is_unchanged(settings):
    cleaned = cleaned_frame([
        {"tmdb_id": 1, "franchise_group_strict": "franchise", "roi": 6.0},
        {"tmdb_id": 2, "roi": 3.0},
    ])
    comparison = run_comparison(
        build_sample(cleaned, pd.DataFrame(), set(), settings), cleaned,
        {1: payload(1), 2: payload(2)},
    )
    movement = would_it_move_the_recommendation(comparison, cleaned, settings)

    assert movement["moved"] is False
    assert movement["substitutions"] == 0
    assert "by construction" in movement["note"]


def test_a_material_money_difference_is_substituted_and_recomputed(settings):
    """The only honest way to answer "does it move the answer" is to try it."""
    cleaned = cleaned_frame([
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
    movement = would_it_move_the_recommendation(comparison, cleaned, settings)

    assert movement["substitutions"] == 1
    assert movement["winner_before"] == "franchise"
    assert movement["winner_after"] == "standalone"
    assert movement["moved"] is True


def test_drift_is_never_substituted(settings):
    cleaned = cleaned_frame([
        {"tmdb_id": 1, "franchise_group_strict": "franchise", "roi": 6.0},
        {"tmdb_id": 2, "roi": 3.0},
    ])
    comparison = pd.DataFrame([{
        "tmdb_id": 1, "title": "A Film", "slice": "shortlisted",
        "field": "popularity", "analysed_value": 12.3, "live_value": 80.0,
        "verdict": VERDICT_DRIFT, "note": "expected",
    }])
    assert would_it_move_the_recommendation(comparison, cleaned, settings)[
        "substitutions"] == 0


# --------------------------------------------------------------------------
# Assertions and the summary
# --------------------------------------------------------------------------

def test_a_clean_spotcheck_says_what_it_verified(settings):
    cleaned = cleaned_frame([{"tmdb_id": i} for i in range(1, 8)])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings)
    comparison = run_comparison(
        sample, cleaned, {int(i): payload(int(i)) for i in sample["tmdb_id"]}
    )
    notes = assert_spotcheck(sample, comparison, settings)

    assert any("No material difference" in note for note in notes)
    assert any("slices" in note for note in notes)


def test_a_material_difference_is_reported_with_the_field(settings):
    cleaned = cleaned_frame([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings)
    comparison = run_comparison(
        sample, cleaned, {1: payload(1, budget=1_000_000), 2: payload(2)}
    )
    notes = assert_spotcheck(sample, comparison, settings)
    assert any("changes an answer" in note and "budget" in note for note in notes)


def test_an_empty_sample_is_a_hard_failure(settings):
    with pytest.raises(AssertionError, match="sampled no films"):
        assert_spotcheck(pd.DataFrame(columns=["tmdb_id", "slice", "why_this_slice"]),
                         pd.DataFrame(), settings)


def test_a_pool_small_enough_to_be_fully_sampled_needs_no_control(settings):
    """Total coverage is the one case where a missing control slice is fine."""
    cleaned = cleaned_frame([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings)

    assert len(sample) == 2
    assert "random_control" not in set(sample["slice"])
    assert_spotcheck(sample, pd.DataFrame(), settings)      # must not raise


def test_a_sample_with_no_control_slice_is_a_hard_failure(settings):
    sample = pd.DataFrame({
        "tmdb_id": pd.array([1], dtype="Int64"), "title": ["A"],
        "slice": ["shortlisted"], "why_this_slice": ["named in the memo"],
    })
    with pytest.raises(AssertionError, match="no unbiased control slice"):
        assert_spotcheck(sample, pd.DataFrame(), settings)


def test_the_report_is_generated_and_states_what_it_does_not_establish(
    settings, tmp_path
):
    """A generated report cannot drift from the check it describes."""
    from streamvault.spotcheck import write_report

    cleaned = cleaned_frame([{"tmdb_id": i} for i in range(1, 8)])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings)
    comparison = run_comparison(
        sample, cleaned, {int(i): payload(int(i)) for i in sample["tmdb_id"]}
    )
    movement = would_it_move_the_recommendation(comparison, cleaned, settings)

    path = tmp_path / "spotcheck.md"
    write_report(path, sample, comparison, summarise(comparison), movement, settings)
    text = path.read_text(encoding="utf-8")

    assert "does not establish" in text
    assert "weak test of *drift over time*" in text
    assert "No material difference" in text
    assert "random_control" in text
    assert "data/raw_spotcheck/" in text
    for field in ("budget", "revenue", "popularity"):
        assert f"`{field}`" in text


def test_the_report_leads_with_a_material_difference_when_there_is_one(
    settings, tmp_path
):
    from streamvault.spotcheck import write_report

    cleaned = cleaned_frame([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings)
    comparison = run_comparison(
        sample, cleaned, {1: payload(1, budget=42), 2: payload(2)}
    )
    movement = would_it_move_the_recommendation(comparison, cleaned, settings)

    path = tmp_path / "spotcheck.md"
    write_report(path, sample, comparison, summarise(comparison), movement, settings)
    text = path.read_text(encoding="utf-8")

    assert "differ materially" in text
    assert "Material differences" in text
    assert "42" in text


def test_the_summary_groups_by_slice_and_verdict(settings):
    cleaned = cleaned_frame([{"tmdb_id": 1}, {"tmdb_id": 2}])
    sample = build_sample(cleaned, pd.DataFrame(), set(), settings)
    comparison = run_comparison(
        sample, cleaned, {1: payload(1, budget=5), 2: payload(2)}
    )
    summary = summarise(comparison)

    assert {"slice", "verdict", "fields", "films"} == set(summary.columns)
    assert VERDICT_MATERIAL in set(summary["verdict"])
