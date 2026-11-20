"""Cleaning as flags, parameterised so every metric runs both ways.

Three rules govern this module.

**1. Nothing is deleted. Exclusion is a column, and it is per metric.** A film
with no usable budget is excluded from the return figures and still counts in
the film count, the rating analysis and the franchise split. A single global
"clean" table would force one answer to "is this film in?", when the honest
answer is "in for some things, out for others" — and would quietly shrink the
denominators the memo quotes (ADR-009).

**2. Every rule reads its threshold from settings.** Not for configurability's
own sake, but so the rejected alternative is *runnable*:
`treat_zero_money_as_missing` can be flipped and the whole analysis recomputed,
which is what makes the sensitivity table a measurement rather than an argument.

**3. A relative measure is recomputed inside every window it is reported for.**
"Above median" means above the median *of the pool being discussed*. Computing
it once over all 112 films and then reporting it for the post-2000 subset would
silently compare modern films against a median set partly by 1970s films.
`add_hit_flags` therefore takes a frame and computes within it, and the KPI
stage calls it again per window. A test pins this, because the bug it prevents
is invisible in the output (M10).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.config import ANALYSED_STATUSES


# ===========================================================================
# Cleaning as flags, every choice runnable both ways
# (was src/streamvault/clean.py)
# ===========================================================================

MONEY_USABLE = "usable"


MONEY_ZERO_AS_MISSING = "zero_treated_as_missing"


MONEY_ZERO_AS_REAL = "zero_treated_as_real"


MONEY_MISSING = "missing"


MONEY_TOO_SMALL = "too_small_for_stable_roi"


EXCLUSION_COLUMNS = ["tmdb_id", "title", "metric", "reason", "setting"]


SENSITIVITY_COLUMNS = [
    "parameter", "value", "films_in_money_metrics", "franchise_n", "franchise_median_roi",
    "standalone_n", "standalone_median_roi", "franchise_ahead", "gap",
]


# ---------------------------------------------------------------------------
# Money quality — which films may enter a money metric, and why
# ---------------------------------------------------------------------------

def classify_money(
    budget: Any, revenue: Any, treat_zero_as_missing: bool, min_budget: int
) -> str:
    """One film's money quality. The order of these checks is the judgement.

    A zero is checked before the plausibility floor, because what a zero *is*
    depends on a setting: with `treat_zero_money_as_missing = true` it is a
    disguised null; with it false it is a real figure of nothing, and a film
    that genuinely made no money is a different claim about the world.
    """
    if pd.isna(budget) or pd.isna(revenue):
        return MONEY_MISSING

    budget, revenue = int(budget), int(revenue)

    if budget == 0 or revenue == 0:
        return MONEY_ZERO_AS_MISSING if treat_zero_as_missing else MONEY_ZERO_AS_REAL

    if budget < min_budget:
        # ROI on a tiny budget is unstable: a rounding error in the denominator
        # moves it by multiples. The film is real; the ratio is not reportable.
        return MONEY_TOO_SMALL

    return MONEY_USABLE


def add_money_quality(frame: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """Add `money_quality`, `roi` and `in_money_metrics`."""
    performance = settings["performance"]
    treat_zero_as_missing = bool(performance["treat_zero_money_as_missing"])
    min_budget = int(performance["min_budget_for_roi"])

    frame = frame.copy()
    frame["money_quality"] = [
        classify_money(budget, revenue, treat_zero_as_missing, min_budget)
        for budget, revenue in zip(frame["budget"], frame["revenue"])
    ]
    frame["in_money_metrics"] = (frame["money_quality"] == MONEY_USABLE).astype("boolean")

    # ROI only where it means something. Computed as a float on purpose: it is
    # a ratio, not a count, and NA where the film is out of money metrics so
    # nothing downstream can average a figure that was never valid.
    usable = frame["in_money_metrics"].fillna(False)
    frame["roi"] = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    frame.loc[usable, "roi"] = (
        frame.loc[usable, "revenue"].astype("Float64")
        / frame.loc[usable, "budget"].astype("Float64")
    )
    return frame


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------

def add_rating_reliability(frame: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """Flag ratings thin enough that ranking on them would be noise.

    The film stays. A 9.1 on 40 votes is a real average of real votes — it is
    just not evidence about a film's reception, so it must not order a
    shortlist. Keeping the film and refusing to rank on it is a different
    decision from dropping the film, and only the first one is honest about
    what is known.
    """
    minimum = int(settings["profile"]["min_votes_for_reliable_rating"])
    frame = frame.copy()
    frame["rating_reliable"] = (
        frame["vote_count"].fillna(0).astype("int64") >= minimum
    ).astype("boolean")
    return frame


# ---------------------------------------------------------------------------
# Hit definitions — one absolute, two relative
# ---------------------------------------------------------------------------

def add_hit_flags(frame: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """Add the three hit flags, computed **within the frame given**.

    `is_hit_roi` is absolute and so travels safely between windows.
    `is_hit_above_median` and `is_hit_top_quartile` do not: they are defined
    against a pool, so they must be recomputed for every window they are
    reported in. Inheriting them from the full table would compare post-2000
    films against a median partly set by 1970s films — a comparison nobody
    chose and nothing in the output would reveal.
    """
    threshold = float(settings["performance"]["hit_roi_threshold"])
    frame = frame.copy()
    roi = frame["roi"] if "roi" in frame.columns else pd.Series(pd.NA, index=frame.index)
    usable = roi.notna()

    frame["is_hit_roi"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    frame["is_hit_above_median"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    frame["is_hit_top_quartile"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")

    if not usable.any():
        return frame

    values = roi.loc[usable].astype("float64")
    frame.loc[usable, "is_hit_roi"] = values >= threshold
    frame.loc[usable, "is_hit_above_median"] = values >= values.median()
    frame.loc[usable, "is_hit_top_quartile"] = values >= values.quantile(0.75)
    return frame


# ---------------------------------------------------------------------------
# The franchise split, both ways
# ---------------------------------------------------------------------------

def add_franchise_groupings(frame: pd.DataFrame) -> pd.DataFrame:
    """Two columns for the two defensible ways to treat lone collection members.

    M1 kept three categories. The comparison the brief asks for has two
    sides, so somebody has to decide where the 9 lone members go, and both
    answers are arguable: they are franchise films, but not ones Kwame can buy
    as a bundle. Having both columns means stage 7 can report the headline one
    way and the sensitivity the other, instead of the choice being buried.
    """
    frame = frame.copy()
    status = frame["franchise_status"]
    frame["franchise_group_strict"] = status.map({
        "franchise": "franchise",
        "lone_collection_member": "standalone",
        "standalone": "standalone",
    })
    frame["franchise_group_loose"] = status.map({
        "franchise": "franchise",
        "lone_collection_member": "franchise",
        "standalone": "standalone",
    })
    return frame


# ---------------------------------------------------------------------------
# Exclusions: who is out of what, and on whose authority
# ---------------------------------------------------------------------------

def build_exclusions(frame: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """One row per (film, metric) it is excluded from, naming the setting.

    Naming the setting matters: it turns "this film was dropped" into "this
    film was dropped by `performance.treat_zero_money_as_missing`, which you
    can flip". An exclusion nobody can trace to a switch is indistinguishable
    from a bug.
    """
    rows: list[dict[str, Any]] = []
    for film in frame.itertuples(index=False):
        if film.money_quality != MONEY_USABLE:
            rows.append({
                "tmdb_id": film.tmdb_id,
                "title": film.title,
                "metric": "money (roi, revenue, budget)",
                "reason": {
                    MONEY_MISSING: "no budget or revenue figure at all",
                    MONEY_ZERO_AS_MISSING: "a zero figure, treated as a disguised null",
                    MONEY_ZERO_AS_REAL: "a zero figure, kept as real — ROI undefined",
                    MONEY_TOO_SMALL: (
                        f"budget below {int(settings['performance']['min_budget_for_roi']):,}; "
                        "ROI on a budget this small is unstable"
                    ),
                }[film.money_quality],
                "setting": "performance.treat_zero_money_as_missing / min_budget_for_roi",
            })
        if not bool(film.rating_reliable):
            rows.append({
                "tmdb_id": film.tmdb_id,
                "title": film.title,
                "metric": "rating (ranking only)",
                "reason": (
                    f"{int(film.vote_count) if not pd.isna(film.vote_count) else 0:,} votes, "
                    f"below {int(settings['profile']['min_votes_for_reliable_rating']):,}; "
                    "the film is kept, but must not be ranked on its average"
                ),
                "setting": "profile.min_votes_for_reliable_rating",
            })

    exclusions = pd.DataFrame(rows, columns=EXCLUSION_COLUMNS)
    if not exclusions.empty:
        exclusions["tmdb_id"] = exclusions["tmdb_id"].astype("Int64")
    return exclusions


# ---------------------------------------------------------------------------
# The sensitivity table — the point of parameterising anything
# ---------------------------------------------------------------------------

def _compare(frame: pd.DataFrame, group_column: str) -> dict[str, Any]:
    """Median ROI either side of one franchise definition."""
    usable = frame.loc[frame["roi"].notna()]
    franchise = usable.loc[usable[group_column] == "franchise", "roi"].astype("float64")
    standalone = usable.loc[usable[group_column] == "standalone", "roi"].astype("float64")
    franchise_median = franchise.median() if len(franchise) else float("nan")
    standalone_median = standalone.median() if len(standalone) else float("nan")
    return {
        "films_in_money_metrics": int(len(usable)),
        "franchise_n": int(len(franchise)),
        "franchise_median_roi": round(franchise_median, 3) if len(franchise) else pd.NA,
        "standalone_n": int(len(standalone)),
        "standalone_median_roi": round(standalone_median, 3) if len(standalone) else pd.NA,
        "franchise_ahead": bool(franchise_median > standalone_median)
        if len(franchise) and len(standalone) else pd.NA,
        "gap": round(franchise_median - standalone_median, 3)
        if len(franchise) and len(standalone) else pd.NA,
    }


def sensitivity_table(analysis: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """Recompute the headline comparison under every cleaning choice.

    This is the table that answers "does your answer depend on your
    assumptions?" with numbers rather than reassurance. Each row re-runs the
    cleaning under one setting and reports the comparison, so a reader can see
    for themselves whether the direction survives.

    `franchise_ahead` is the column to read first: if it is the same in every
    row, the recommendation does not rest on any of these choices.
    """
    rows: list[dict[str, Any]] = []

    for treat_zero, label in ((True, "true (default)"), (False, "false")):
        variant = dict(settings.raw)
        variant["performance"] = {**settings["performance"],
                                  "treat_zero_money_as_missing": treat_zero}
        local = type(settings)(raw=variant, root=settings.root)
        frame = add_hit_flags(add_money_quality(analysis, local), local)
        frame = add_franchise_groupings(frame)
        rows.append({
            "parameter": "performance.treat_zero_money_as_missing",
            "value": label,
            **_compare(frame, "franchise_group_strict"),
        })

    prepared = add_franchise_groupings(
        add_hit_flags(add_money_quality(analysis, settings), settings)
    )
    for column, label in (
        ("franchise_group_strict", "2 — lone members are standalone (default)"),
        ("franchise_group_loose", "1 — lone members are franchise"),
    ):
        rows.append({
            "parameter": "franchise.min_members_on_list",
            "value": label,
            **_compare(prepared, column),
        })

    for minimum, label in ((1_000_000, "1,000,000 (default)"), (10_000_000, "10,000,000")):
        variant = dict(settings.raw)
        variant["performance"] = {**settings["performance"], "min_budget_for_roi": minimum}
        local = type(settings)(raw=variant, root=settings.root)
        frame = add_franchise_groupings(
            add_hit_flags(add_money_quality(analysis, local), local)
        )
        rows.append({
            "parameter": "performance.min_budget_for_roi",
            "value": label,
            **_compare(frame, "franchise_group_strict"),
        })

    return pd.DataFrame(rows, columns=SENSITIVITY_COLUMNS)


# ---------------------------------------------------------------------------
# Back to the ledger
# ---------------------------------------------------------------------------

def update_ledger(ledger: pd.DataFrame, cleaned: pd.DataFrame) -> pd.DataFrame:
    """Fill `in_money_metrics`, the column stage 1 reserved and left as NA.

    Stage 1 created that column empty with the comment "decided at stage 6, not
    here". This is stage 6. The ledger is the one table that accounts for every
    source row from the file to the final metric, and leaving the column empty
    would mean the accounting stops one step short of the numbers in the memo.

    **Only a row that owns its film is flagged.** A duplicate row carries the
    same id as the row that was kept, so mapping by id alone marks all six
    duplicates `True` and the ledger then claims 118 rows entered the money
    metrics when 112 films did. This is the identical mistake stage 4's
    accounting made, caught there by a test; `ANALYSED_STATUSES` is imported
    rather than redefined so there is one answer to "which row owns the film?".
    """
    ledger = ledger.copy()
    flags = dict(zip(cleaned["tmdb_id"].astype("Int64"), cleaned["in_money_metrics"]))
    ledger["in_money_metrics"] = [
        flags.get(tmdb_id, pd.NA)
        if status in ANALYSED_STATUSES and not pd.isna(tmdb_id)
        else pd.NA
        for status, tmdb_id in zip(ledger["status"], ledger["tmdb_id"])
    ]
    ledger["in_money_metrics"] = ledger["in_money_metrics"].astype("boolean")
    return ledger


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def assert_clean(
    cleaned: pd.DataFrame, analysis: pd.DataFrame, exclusions: pd.DataFrame
) -> list[str]:
    """Hard-assert that cleaning changed no row count; report what it excluded."""
    notes: list[str] = []

    # The whole design in one assertion: cleaning adds columns, never removes
    # rows. If this fails, the film count in the memo no longer matches the
    # accounting table built at stage 4.
    assert len(cleaned) == len(analysis), (
        f"cleaning changed the row count: {len(analysis)} in, {len(cleaned)} out"
    )
    assert cleaned["tmdb_id"].is_unique, "cleaning broke the one-row-per-film grain"

    # Every film must land in exactly one money_quality class.
    assert cleaned["money_quality"].notna().all(), "a film has no money_quality"

    # ROI exists exactly where the film is in money metrics, and nowhere else.
    usable = cleaned["in_money_metrics"].fillna(False)
    assert cleaned.loc[usable, "roi"].notna().all(), (
        "a film in money metrics has no ROI"
    )
    assert cleaned.loc[~usable, "roi"].isna().all(), (
        "a film excluded from money metrics has an ROI, which nothing may average"
    )

    if not exclusions.empty:
        assert (exclusions["setting"].str.len() > 0).all(), (
            "an exclusion does not name the setting that caused it"
        )

    excluded_money = int((~usable).sum())
    if excluded_money:
        notes.append(
            f"{excluded_money} film(s) are excluded from money metrics; each is "
            "listed in exclusions.csv with the setting responsible."
        )
    else:
        notes.append(
            f"All {len(cleaned)} films are in the money metrics: no zero, missing or "
            "implausibly small figure to exclude. "
            "`performance.treat_zero_money_as_missing` is therefore dormant this "
            "quarter — it changes nothing, and the decision log says so rather than "
            "claiming it cleaned anything."
        )

    thin = int((~cleaned["rating_reliable"].fillna(False)).sum())
    if thin:
        notes.append(
            f"{thin} film(s) have too few votes to rank on their rating. They stay "
            "in every other metric."
        )
    return notes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def clean(analysis: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """Apply every rule, in order. Adds columns; never removes a row."""
    frame = add_money_quality(analysis, settings)
    frame = add_rating_reliability(frame, settings)
    frame = add_hit_flags(frame, settings)
    return add_franchise_groupings(frame)


def clean_films(
    settings: Any, analysis: pd.DataFrame, ledger: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """Apply the cleaning rules."""
    cleaned = clean(analysis, settings)
    exclusions = build_exclusions(cleaned, settings)
    sensitivity = sensitivity_table(analysis, settings)
    ledger = update_ledger(ledger, cleaned)

    for note in assert_clean(cleaned, analysis, exclusions):
        print(f"[validate] {note}")

    print(f"[validate] money quality: {cleaned['money_quality'].value_counts().to_dict()}")
    hits = {
        column.replace("is_hit_", ""): int(cleaned[column].fillna(False).sum())
        for column in ("is_hit_roi", "is_hit_above_median", "is_hit_top_quartile")
    }
    print(f"[validate] hits by definition (of {len(cleaned)} films): {hits}")

    processed = settings.path(settings["paths"]["processed_dir"])
    interim = settings.path(settings["paths"]["interim_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    interim.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(interim / "cleaned.csv", index=False)
    exclusions.to_csv(processed / "exclusions.csv", index=False)
    sensitivity.to_csv(processed / "sensitivity.csv", index=False)

    return {
        "cleaned": cleaned,
        "exclusions": exclusions,
        "sensitivity": sensitivity,
        "ledger": ledger,
    }
