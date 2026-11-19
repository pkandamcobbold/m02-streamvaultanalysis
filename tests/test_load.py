"""Tests for the load stage: the generated memo and the improvement note.

The memo is the only artefact a non-programmer reads, so the failures that
matter are different in kind. A wrong number is bad; **a number stated with
more confidence than the data supports is worse**, because nobody downstream
can tell.

So these tests check that the caveats cannot be dropped, that the jargon stays
out, and that a flip reaches the first line rather than a footnote. A future
edit that quietly removes a limitation fails the suite (ADR-028).
"""
from __future__ import annotations

import pandas as pd

from pipeline.checks import gate
from pipeline.load import build_improvement, build_memo
from tests.conftest import flat, flip_table, make_facts, window_table


def test_the_memo_contains_no_tool_names_or_jargon(memo_settings):
    memo = build_memo(make_facts(memo_settings), memo_settings)
    lowered = memo.lower()
    for banned in ("roi", "pandas", "dataframe", "null", "nan", "api", "tmdb",
                   "dtype", "csv", "quartile", "iqr", "median"):
        assert banned not in lowered, f"jargon leaked into the memo: {banned!r}"


def test_the_recommendation_is_the_first_line(memo_settings):
    memo = build_memo(make_facts(memo_settings), memo_settings)
    body = flat([line for line in memo.splitlines() if line.strip()][1])
    assert "Buy franchise bundles first" in body


def test_a_headline_flip_replaces_the_recommendation_rather_than_footnoting_it(memo_settings):
    """The brief says loudly. A flip is the most useful thing to tell him."""
    facts = make_facts(memo_settings, flips=flip_table(headline_flipped=True))
    memo = build_memo(facts, memo_settings)
    first = flat([line for line in memo.splitlines() if line.strip()][1])

    assert "changes depending on how far back you look" in first
    assert "Buy franchise bundles first" not in memo


def test_the_spread_flip_is_reported_with_its_group_size(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "that advantage disappears" in memo
    assert "rests on only 12 one-off films" in memo
    assert "would not say one-offs have become *safer*" in memo


def test_the_mean_reversal_is_disclosed_unprompted(memo_settings):
    """It reverses the recommendation; hiding it would be the worst omission."""
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "if you compare *averages* instead of typical films, one-offs come out ahead" in memo
    assert "three exceptional films" in memo


def test_no_dollar_price_is_ever_named(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "cannot tell you what to pay" in memo
    assert "anyone who gives you a dollar figure from this data is guessing" in memo


def test_every_limitation_the_analysis_found_is_listed(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    for limitation in (
        "how these films behave on a streaming service",   # box office is a proxy
        "Nothing on this list ever lost money",            # F12, selection bias
        "The one-off group is thin",                       # F7, group size
        "Old and new money are not the same money",        # F10, era effects
        "already filtered toward series films",            # F7, list composition
        "We have no licensing prices",
    ):
        assert limitation in memo, f"missing limitation: {limitation!r}"


def test_the_as_of_date_is_the_data_not_the_day_it_was_written(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "data as it stood on 2026-11-19" in memo
    assert "do not update on their own" in memo


def test_a_cache_spanning_days_reports_a_range(memo_settings):
    facts = make_facts(memo_settings, fetch_log=pd.DataFrame({
        "fetched_at": ["2026-11-18T10:00:00+00:00", "2026-11-19T10:00:00+00:00"],
    }))
    assert "2026-11-18 to 2026-11-19" in flat(build_memo(facts, memo_settings))


def test_the_title_count_reconciles_in_the_memo_itself(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "127 titles received" in memo
    assert "112 analysed" in memo
    assert "15 set aside" in memo


def test_a_lone_collection_member_is_labelled_in_the_shortlist(memo_settings):
    """Presenting Jaws as a one-off without qualification invites an objection."""
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "Jaws" in memo
    assert "only this one" in memo


def test_the_runners_up_are_named(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "Runner Up Collection" in memo
    assert "substitute rather than stretch" in memo


def test_the_deal_note_is_relative_and_names_the_driving_number(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "24%" in memo or "23%" in memo      # concentration of the top bundle
    assert "concentration of any series we looked at" in memo
    assert "higher price per film" in memo


def test_the_position_finding_corrects_the_teams_belief(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "middle" in memo
    assert "not supported" in memo


def test_the_improvement_is_justified_in_the_clients_terms(memo_settings):
    facts = make_facts(memo_settings)
    text = flat(build_improvement(facts, gate(memo_settings, facts)))

    assert "Adjoa" in text and "sometimes live in the meeting" in text
    assert "Why not the alternatives" in text
    assert "What survives at 500 titles" in text
    assert "What it costs" in text


def test_the_improvement_lists_every_gate_check(memo_settings):
    facts = make_facts(memo_settings)
    results = gate(memo_settings, facts)
    text = build_improvement(facts, results)
    for check in results["check"]:
        assert check in text
