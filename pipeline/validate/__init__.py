"""Stage 2 — validate: profile the films, then classify what looks wrong.

One stage, two jobs, one module each (ADR-018):

    profile.py  every column's completeness and shape; every suspect value
                flagged with a verdict and a reason
    clean.py    the cleaning rules, as flags rather than deletions, every one
                reading its threshold from settings so the alternative is
                runnable

Runs on the **films** table, before any credit is joined onto it: every rule
here reads film-level fields, and validating before the join is what keeps the
five stages a single pass.

Callers import the stage, not its parts: `validate.find_flags`,
`validate.clean` and `validate.validate` all work.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.validate.clean import (
    EXCLUSION_COLUMNS,
    MONEY_MISSING,
    MONEY_TOO_SMALL,
    MONEY_USABLE,
    MONEY_ZERO_AS_MISSING,
    MONEY_ZERO_AS_REAL,
    SENSITIVITY_COLUMNS,
    add_franchise_groupings,
    add_hit_flags,
    add_money_quality,
    add_rating_reliability,
    assert_clean,
    build_exclusions,
    classify_money,
    clean,
    clean_films,
    sensitivity_table,
    update_ledger,
)
from pipeline.validate.profile import (
    FLAG_COLUMNS,
    PROFILE_COLUMNS,
    VERDICT_CHECK,
    VERDICT_ERROR,
    VERDICT_REAL,
    VERDICT_UNRELIABLE,
    assert_profile,
    duplicate_titles,
    era_comparability,
    find_flags,
    profile_films,
    profile_table,
    summarise_flags,
)


# ---------------------------------------------------------------------------
# The stage entry point
# ---------------------------------------------------------------------------

def validate(
    settings: Any, films: pd.DataFrame, ledger: pd.DataFrame
) -> dict[str, Any]:
    """Profile the films, classify every fault, then apply the cleaning rules.

    Runs on the **films** table, before any credit is joined onto it: every
    rule here reads film-level fields, and validating before the join keeps the
    pipeline a single pass through the five stages (ADR-017).

    Returns the cleaned table plus all the evidence: the profile, the flags
    with a verdict on each, the era-comparability note, the exclusions with the
    setting responsible for each, and the sensitivity runs.
    """
    profiled = profile_films(settings, films)
    cleaned = clean_films(settings, films, ledger)
    return {**profiled, **cleaned}
