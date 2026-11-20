"""Tests for the load stage: the generated memo and the improvement note.

The memo is the only artefact a non-programmer reads, so the failures that
matter are different in kind. A wrong number is bad; **a number stated with
more confidence than the data supports is worse**, because nobody downstream
can tell.

So these tests check that the caveats cannot be dropped, that the jargon stays
out, and that a flip reaches the first line rather than a footnote. A future
edit that quietly removes a limitation fails the suite (ADR-014).
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


def subject_line(memo: str) -> str:
    """The memo's Subject line, which is where the recommendation lives.

    The house template fixes the section order — found, built, recommend, could
    not stand behind — so the recommendation cannot be the body's first line and
    still obey it. It goes in the subject instead, which is the first thing read
    and what a memo's subject is for (ADR-014).
    """
    for line in memo.splitlines():
        if line.startswith("**Subject:**"):
            return flat(line)
    raise AssertionError("the memo has no Subject line")


def test_the_recommendation_is_in_the_subject_line(memo_settings):
    memo = build_memo(make_facts(memo_settings), memo_settings)
    assert "Buy franchise bundles first" in subject_line(memo)


def test_a_headline_flip_replaces_the_recommendation_rather_than_footnoting_it(memo_settings):
    """The brief says loudly. A flip is the most useful thing to tell him."""
    facts = make_facts(memo_settings, flips=flip_table(headline_flipped=True))
    memo = build_memo(facts, memo_settings)

    assert "changes depending on how far back you look" in subject_line(memo)
    assert "Buy franchise bundles first" not in memo


def test_the_spread_flip_is_reported_with_its_group_size(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "that advantage disappears" in memo
    assert "rests on only 12 standalone films" in memo
    assert "would not say standalones have become *safer*" in memo


def test_the_mean_reversal_is_disclosed_unprompted(memo_settings):
    """It reverses the recommendation; hiding it would be the worst omission."""
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "if you compare *averages* instead of typical films, standalones come out ahead" in memo
    assert "three exceptional films" in memo


def test_no_dollar_price_is_ever_named(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "cannot tell you what to pay" in memo
    assert "anyone who gives you a dollar figure from this data is guessing" in memo


def test_every_limitation_the_analysis_found_is_listed(memo_settings):
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    for limitation in (
        "how these films behave on a streaming service",   # box office is a proxy
        "Nothing on this list ever lost money",            # F-01, selection bias
        "The standalone group is thin",                    # F-04, group size
        "Old and new money are not the same money",        # F-05, era effects
        "already filtered toward franchise films",         # F-04, list composition
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
    """Presenting Jaws as a standalone without qualification invites an objection."""
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
    assert "concentration of any franchise we looked at" in memo
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

# --------------------------------------------------------------------------
# "How solid is that lead?" — the interval, beside the claim it qualifies
# --------------------------------------------------------------------------

def uncertainty_table(rows):
    """rows of (measure, gap, ci_low, ci_high, share_ahead, excludes_zero)."""
    return pd.DataFrame({
        "measure": [r[0] for r in rows],
        "better_is": ["higher"] * len(rows),
        "franchise": [5.5] * len(rows),
        "standalone": [5.0] * len(rows),
        "gap": [r[1] for r in rows],
        "ci_low": [r[2] for r in rows],
        "ci_high": [r[3] for r in rows],
        "share_franchise_ahead": [r[4] for r in rows],
        "excludes_zero": [r[5] for r in rows],
        "basis": ["a test"] * len(rows),
    })


NOTHING_SETTLED = [
    ("typical return", 0.53, -6.24, 3.18, 0.785, False),
    ("weaker end", 1.27, -0.63, 2.61, 0.938, False),
    ("share clearing break-even", 0.15, -0.001, 0.32, 0.974, False),
    ("spread", -7.33, -17.72, 1.92, 0.886, False),
]


def test_the_memo_states_the_interval_where_it_makes_the_claim(memo_settings):
    """It was in the limitations, which is where a reader goes last."""
    facts = make_facts(
        memo_settings,
        uncertainty_by_franchise=uncertainty_table(NOTHING_SETTLED))
    memo = flat(build_memo(facts, memo_settings))

    found = memo.split("## What I found")[1].split("##")[0]
    assert "-6.2 to +3.2" in found
    assert "78% to 97%" in found
    assert "no single measure's lead is large enough" in found


def test_the_memo_names_the_measure_that_does_settle_it(memo_settings):
    """The sentence must not keep saying "nothing holds" once something does."""
    settled = list(NOTHING_SETTLED)
    settled[1] = ("weaker end", 1.27, 0.40, 2.61, 0.991, True)
    facts = make_facts(memo_settings,
                       uncertainty_by_franchise=uncertainty_table(settled))
    memo = flat(build_memo(facts, memo_settings))

    assert "the gap on weaker end is large enough" in memo
    assert "no single measure's lead is large enough" not in memo


def test_the_memo_quotes_the_franchise_resample_not_the_flattering_one(memo_settings):
    """Per film the gap looks established; per franchise it does not. Quote the latter."""
    per_film = list(NOTHING_SETTLED)
    per_film[0] = ("typical return", 0.53, 0.10, 3.08, 0.999, True)

    facts = make_facts(
        memo_settings,
        uncertainty=uncertainty_table(per_film),
        uncertainty_by_franchise=uncertainty_table(NOTHING_SETTLED))
    memo = flat(build_memo(facts, memo_settings))

    assert "no single measure's lead is large enough" in memo
    assert "+0.1 to +3.1" not in memo        # the per-film interval
    assert "-6.2 to +3.2" in memo            # the cluster interval


def test_with_only_a_per_film_resample_that_one_is_used(memo_settings):
    """A thin group can leave the cluster table empty; the memo still says something."""
    facts = make_facts(memo_settings, uncertainty=uncertainty_table(NOTHING_SETTLED))
    assert "-6.2 to +3.2" in flat(build_memo(facts, memo_settings))


def test_without_any_resample_the_memo_still_builds_and_claims_nothing(memo_settings):
    """No interval is better than an invented one, and the memo must not crash."""
    memo = flat(build_memo(make_facts(memo_settings), memo_settings))
    assert "How solid is that lead?" not in memo
    assert "## What I found" in memo


def test_the_measure_count_is_spelled_not_printed_as_a_digit(memo_settings):
    facts = make_facts(
        memo_settings,
        uncertainty_by_franchise=uncertainty_table(NOTHING_SETTLED))
    memo = flat(build_memo(facts, memo_settings))
    assert "all four measures" in memo
    assert "all 4 measures" not in memo
