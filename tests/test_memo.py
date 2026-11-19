"""Stage 10 tests.

The memo is the only artefact a non-programmer reads, so the failures that
matter are different in kind. A wrong number is bad; **a number stated with
more confidence than the data supports is worse**, because nobody downstream
can tell.

So these tests check that the caveats cannot be dropped, that the jargon stays
out, that a flip reaches the first line rather than a footnote, and that the
gate refuses to publish rather than publishing with a warning nobody reads.
"""
from __future__ import annotations

import pandas as pd
import pytest

from streamvault.config import Settings
from streamvault.kpis import GROUP_STRICT
from streamvault.memo import (
    GateFailed,
    build_improvement,
    build_memo,
    enforce,
    gate,
    gather,
    money,
    multiple,
    share,
)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        raw={
            "paths": {"processed_dir": "data/processed", "reports_dir": "reports"},
            "gate": {
                "enabled": True, "max_unaccounted_rows": 0,
                "min_films_for_a_recommendation": 40,
                "max_missing_money_share": 0.20,
                "block_if_spotcheck_moves": True,
            },
        },
        root=tmp_path,
    )


def flat(text: str) -> str:
    """Collapse whitespace before asserting on prose.

    The memo is hard-wrapped for reading, so a sentence routinely spans two
    lines. Asserting the raw string would make every test a test of where the
    line breaks fall, and it would fail the next time a sentence is reworded by
    a word. These assertions are about what the memo says.
    """
    return " ".join(text.split())


def window_table(franchise_median=5.5, standalone_median=5.0, franchise_n=87,
                 standalone_n=25, franchise_floor=3.9, standalone_floor=2.6,
                 franchise_iqr=4.4, standalone_iqr=11.7):
    return pd.DataFrame({
        GROUP_STRICT: ["franchise", "standalone"],
        "films": [franchise_n, standalone_n],
        "median_roi": [franchise_median, standalone_median],
        "floor_roi": [franchise_floor, standalone_floor],
        "iqr_roi": [franchise_iqr, standalone_iqr],
        "hit_rate_roi": [0.954, 0.80],
        "median_revenue": [618_638_999, 291_465_000],
        "median_rating": [7.5, 7.9],
    })


def flip_table(spread_flipped=True, headline_flipped=False):
    return pd.DataFrame({
        "measure": ["median_roi", "floor_roi", "hit_rate_roi", "iqr_roi"],
        "better_is": ["higher", "higher", "higher", "lower"],
        "winner_all_years": ["franchise"] * 4,
        "winner_modern": [
            "standalone" if headline_flipped else "franchise",
            "franchise", "franchise",
            "standalone" if spread_flipped else "franchise",
        ],
        "flipped": [headline_flipped, False, False, spread_flipped],
    })


def accounting_table():
    return pd.DataFrame({
        "status": ["fetched", "duplicate", "not_found_404", "invalid_id",
                   "duplicate_other_namespace"],
        "source_rows": [112, 6, 5, 3, 1],
        "reached_analysis": pd.array([112, 0, 0, 0, 0], dtype="Int64"),
    })


def ledger_table(data_rows=127):
    return pd.DataFrame({
        "status": ["header_row"] + ["fetched"] * data_rows,
        "tmdb_id": pd.array([None] + list(range(1, data_rows + 1)), dtype="Int64"),
    })


def make_facts(settings, **overrides):
    inputs = {
        "accounting": accounting_table(),
        "ledger": ledger_table(),
        "cleaned": pd.DataFrame({
            "tmdb_id": pd.array(range(1, 113), dtype="Int64"),
            "in_money_metrics": pd.array([True] * 112, dtype="boolean"),
        }),
        "windows": {"all_years": window_table(),
                    "modern": window_table(franchise_n=59, standalone_n=12,
                                           franchise_iqr=2.47,
                                           standalone_iqr=2.30)},
        "flips": flip_table(),
        "bundles": pd.DataFrame(),
        "gaps": pd.DataFrame({
            "collection_name": ["Star Wars Collection"],
            "entries_on_list": [6], "best_roi": [70.5], "median_roi": [13.4],
            "worst_roi": [5.4], "best_to_median": [5.26],
            "best_share_of_revenue": [0.236],
        }),
        "positions": pd.DataFrame({
            "position": ["first", "middle", "last"],
            "films": [22, 41, 22], "median_roi": [7.76, 5.41, 4.44],
        }),
        "talent": pd.DataFrame(),
        "shortlist": {
            "franchises": pd.DataFrame({
                "collection_name": ["Star Wars Collection", "Runner Up Collection"],
                "films_on_list": [6, 3], "median_roi": [13.4, 8.3],
                "floor_roi": [5.4, 6.1], "best_roi": [70.5, 20.6],
                "bundle_roi": [10.8, 9.8], "median_rating": [7.69, 7.78],
                "first_year": [1977, 1985], "last_year": [2019, 1990],
                "selected": [True, False],
            }),
            "standalones": pd.DataFrame({
                "tmdb_id": pd.array([578, 429], dtype="Int64"),
                "title": ["Jaws", "The Good, the Bad and the Ugly"],
                "release_year": pd.array([1975, 1966], dtype="Int64"),
                "roi": [67.2, 32.4], "revenue": [470_653_000, 38_900_000],
                "budget": [7_000_000, 1_200_000],
                "vote_average": [7.7, 8.5], "vote_count": pd.array([12000, 8000],
                                                                   dtype="Int64"),
                "rating_reliable": [True, True],
                "franchise_status": ["lone_collection_member", "standalone"],
                "selected": [True, True],
            }),
        },
        "fetch_log": pd.DataFrame({
            "fetched_at": ["2026-11-19T13:00:00+00:00"] * 112,
        }),
        "spotcheck_movement": {"moved": False, "note": "nothing to substitute"},
        "spotcheck_films": 15,
        "eras": pd.DataFrame(),
    }
    inputs.update(overrides)
    return gather(settings, **inputs)


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------

def test_the_gate_passes_a_sound_run(settings):
    results = gate(settings, make_facts(settings))
    assert results["passed"].all()
    enforce(results, settings)              # must not raise


def test_too_few_films_blocks_the_memo(settings):
    facts = make_facts(settings)
    facts["films_analysed"] = 12
    results = gate(settings, facts)

    assert not results["passed"].all()
    with pytest.raises(GateFailed, match="enough films to compare"):
        enforce(results, settings)


def test_too_much_missing_money_blocks_the_memo(settings):
    facts = make_facts(settings)
    facts["missing_money_share"] = 0.5
    with pytest.raises(GateFailed, match="money data complete enough"):
        enforce(gate(settings, facts), settings)


def test_a_spotcheck_that_moves_the_answer_blocks_the_memo(settings):
    """The whole point: a human must look before this reaches a board."""
    facts = make_facts(settings)
    facts["spotcheck_moved"] = True
    with pytest.raises(GateFailed, match="live re-check"):
        enforce(gate(settings, facts), settings)


def test_the_accounting_cross_check_is_not_a_tautology(settings):
    """It compares two independently built tables, so it can actually fail."""
    facts = make_facts(settings, ledger=ledger_table(data_rows=120))
    assert facts["unaccounted_rows"] == 7
    with pytest.raises(GateFailed, match="every source row accounted for"):
        enforce(gate(settings, facts), settings)


def test_the_failure_message_says_what_to_do(settings):
    facts = make_facts(settings)
    facts["films_analysed"] = 5
    try:
        enforce(gate(settings, facts), settings)
    except GateFailed as error:
        message = str(error)
    assert "Nothing is wrong with your computer" in message
    assert "gate.enabled = false" in message
    assert "data_diagnosis.md" in message


def test_the_gate_can_be_turned_off_deliberately(settings):
    """Skipping it should be a decision somebody can be asked about."""
    facts = make_facts(settings)
    facts["films_analysed"] = 5
    settings.raw["gate"]["enabled"] = False
    enforce(gate(settings, facts), settings)        # must not raise


# --------------------------------------------------------------------------
# Plain language
# --------------------------------------------------------------------------

def test_money_is_readable_aloud():
    assert money(470_653_000) == "$471m"
    assert money(2_942_649_778) == "$2.94bn"
    assert money(None) == "no figure"


def test_returns_are_never_written_as_an_acronym():
    assert multiple(5.526) == "5.5 times"
    assert share(0.954) == "95%"


def test_the_memo_contains_no_tool_names_or_jargon(settings):
    memo = build_memo(make_facts(settings), settings)
    lowered = memo.lower()
    for banned in ("roi", "pandas", "dataframe", "null", "nan", "api", "tmdb",
                   "dtype", "csv", "quartile", "iqr", "median"):
        assert banned not in lowered, f"jargon leaked into the memo: {banned!r}"


# --------------------------------------------------------------------------
# What the memo must say
# --------------------------------------------------------------------------

def test_the_recommendation_is_the_first_line(settings):
    memo = build_memo(make_facts(settings), settings)
    body = flat([line for line in memo.splitlines() if line.strip()][1])
    assert "Buy franchise bundles first" in body


def test_a_headline_flip_replaces_the_recommendation_rather_than_footnoting_it(settings):
    """The brief says loudly. A flip is the most useful thing to tell him."""
    facts = make_facts(settings, flips=flip_table(headline_flipped=True))
    memo = build_memo(facts, settings)
    first = flat([line for line in memo.splitlines() if line.strip()][1])

    assert "changes depending on how far back you look" in first
    assert "Buy franchise bundles first" not in memo


def test_the_spread_flip_is_reported_with_its_group_size(settings):
    memo = flat(build_memo(make_facts(settings), settings))
    assert "that advantage disappears" in memo
    assert "rests on only 12 one-off films" in memo
    assert "would not say one-offs have become *safer*" in memo


def test_the_mean_reversal_is_disclosed_unprompted(settings):
    """It reverses the recommendation; hiding it would be the worst omission."""
    memo = flat(build_memo(make_facts(settings), settings))
    assert "if you compare *averages* instead of typical films, one-offs come out ahead" in memo
    assert "three exceptional films" in memo


def test_no_dollar_price_is_ever_named(settings):
    memo = flat(build_memo(make_facts(settings), settings))
    assert "cannot tell you what to pay" in memo
    assert "anyone who gives you a dollar figure from this data is guessing" in memo


def test_every_limitation_the_analysis_found_is_listed(settings):
    memo = flat(build_memo(make_facts(settings), settings))
    for limitation in (
        "how these films behave on a streaming service",   # box office is a proxy
        "Nothing on this list ever lost money",            # F12, selection bias
        "The one-off group is thin",                       # F7, group size
        "Old and new money are not the same money",        # F10, era effects
        "already filtered toward series films",            # F7, list composition
        "We have no licensing prices",
    ):
        assert limitation in memo, f"missing limitation: {limitation!r}"


def test_the_as_of_date_is_the_data_not_the_day_it_was_written(settings):
    memo = flat(build_memo(make_facts(settings), settings))
    assert "data as it stood on 2026-11-19" in memo
    assert "do not update on their own" in memo


def test_a_cache_spanning_days_reports_a_range(settings):
    facts = make_facts(settings, fetch_log=pd.DataFrame({
        "fetched_at": ["2026-11-18T10:00:00+00:00", "2026-11-19T10:00:00+00:00"],
    }))
    assert "2026-11-18 to 2026-11-19" in flat(build_memo(facts, settings))


def test_the_title_count_reconciles_in_the_memo_itself(settings):
    memo = flat(build_memo(make_facts(settings), settings))
    assert "127 titles received" in memo
    assert "112 analysed" in memo
    assert "15 set aside" in memo


def test_a_lone_collection_member_is_labelled_in_the_shortlist(settings):
    """Presenting Jaws as a one-off without qualification invites an objection."""
    memo = flat(build_memo(make_facts(settings), settings))
    assert "Jaws" in memo
    assert "only this one" in memo


def test_the_runners_up_are_named(settings):
    memo = flat(build_memo(make_facts(settings), settings))
    assert "Runner Up Collection" in memo
    assert "substitute rather than stretch" in memo


def test_the_deal_note_is_relative_and_names_the_driving_number(settings):
    memo = flat(build_memo(make_facts(settings), settings))
    assert "24%" in memo or "23%" in memo      # concentration of the top bundle
    assert "concentration of any series we looked at" in memo
    assert "higher price per film" in memo


def test_the_position_finding_corrects_the_teams_belief(settings):
    memo = flat(build_memo(make_facts(settings), settings))
    assert "middle" in memo
    assert "not supported" in memo


# --------------------------------------------------------------------------
# The improvement write-up
# --------------------------------------------------------------------------

def test_the_improvement_is_justified_in_the_clients_terms(settings):
    facts = make_facts(settings)
    text = flat(build_improvement(facts, gate(settings, facts)))

    assert "Adjoa" in text and "sometimes live in the meeting" in text
    assert "Why not the alternatives" in text
    assert "What survives at 500 titles" in text
    assert "What it costs" in text


def test_the_improvement_lists_every_gate_check(settings):
    facts = make_facts(settings)
    results = gate(settings, facts)
    text = build_improvement(facts, results)
    for check in results["check"]:
        assert check in text
