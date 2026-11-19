"""Stage 2 — validate: profile the films, then classify what looks wrong.

Two jobs, and the second one is the hard one.

**Profile** every column: how much is present, how much is zero, and the shape
of the distribution. Zeros are counted separately from nulls, because a zero
budget is TMDb's way of saying "unknown" and would never appear in a null count.

**Separate real extremes from errors.** *Star Wars* returned 70 times its
budget. That is not an outlier to be clipped — it is the single most relevant
data point on the list, because the whole question is whether old films are
worth licensing. So the rule throughout is **flag with a reason, classify,
never delete**, and every flag carries a verdict:

    error            the value cannot be right (a budget of 5, a zero)
    real_extreme     unusual and true — stays in every metric
    unreliable       true but too thin to carry weight (a rating on 40 votes)
    check            needs a human to look; nothing is excluded on a check

Cleaning then adds columns and never removes a row. Exclusion is **per metric**:
a film with no usable budget leaves the money metrics and stays in the film
count, the rating analysis and the franchise split. Every rule reads its
threshold from settings, so the rejected alternative is runnable and the
sensitivity table is a measurement rather than an argument.

See ADR-013 to ADR-017 for the judgements, and ADR-030 for why a settings key
that changes nothing refuses to load.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.config import ANALYSED_STATUSES


# ===========================================================================
# Profiling, and separating real extremes from errors
# (was src/streamvault/profile.py)
# ===========================================================================

PROFILE_COLUMNS = [
    "column", "dtype", "n", "n_missing", "pct_missing", "n_zero", "n_distinct",
    "min", "p05", "p25", "median", "p75", "p95", "max",
]

FLAG_COLUMNS = ["tmdb_id", "title", "flag", "column", "value", "verdict", "why"]

VERDICT_ERROR = "error"
VERDICT_REAL = "real_extreme"
VERDICT_UNRELIABLE = "unreliable"
VERDICT_CHECK = "check"


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------

def profile_table(frame: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """One row per column: completeness, zeros, and the distribution's shape.

    Percentiles rather than mean and standard deviation. Money is heavily
    skewed — one *Avengers: Endgame* drags a mean far from anything typical —
    and a standard deviation on a skewed distribution invites exactly the
    "anything beyond 3 sigma is an error" reasoning this stage exists to
    refuse.
    """
    columns = columns or list(frame.columns)
    rows: list[dict[str, Any]] = []

    for column in columns:
        if column not in frame.columns:
            continue
        series = frame[column]
        row: dict[str, Any] = {
            "column": column,
            "dtype": str(series.dtype),
            "n": int(series.notna().sum()),
            "n_missing": int(series.isna().sum()),
            "pct_missing": round(100 * series.isna().mean(), 2),
            "n_distinct": int(series.nunique(dropna=True)),
            "n_zero": pd.NA,
            "min": pd.NA, "p05": pd.NA, "p25": pd.NA,
            "median": pd.NA, "p75": pd.NA, "p95": pd.NA, "max": pd.NA,
        }

        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            row["n_zero"] = int((numeric == 0).sum())
            if len(numeric):
                row.update({
                    "min": numeric.min(),
                    "p05": numeric.quantile(0.05),
                    "p25": numeric.quantile(0.25),
                    "median": numeric.median(),
                    "p75": numeric.quantile(0.75),
                    "p95": numeric.quantile(0.95),
                    "max": numeric.max(),
                })
        rows.append(row)

    return pd.DataFrame(rows, columns=PROFILE_COLUMNS)


# ---------------------------------------------------------------------------
# Flagging, with a verdict on each flag
# ---------------------------------------------------------------------------

def _flag(
    rows: list[dict[str, Any]], film: Any, flag: str, column: str,
    value: Any, verdict: str, why: str,
) -> None:
    rows.append({
        "tmdb_id": film.tmdb_id,
        "title": film.title,
        "flag": flag,
        "column": column,
        "value": value,
        "verdict": verdict,
        "why": why,
    })


def find_flags(analysis: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """Every value worth a second look, with a verdict and a reason.

    The verdicts are assigned by rule, and the rules encode the judgement:
    a zero or a sub-$100k budget on a studio film *cannot* be right, while a
    70× return or a flop *can*, so the first is an error and the second is a
    real extreme. Nothing here excludes a film.
    """
    config = settings["profile"]
    min_budget = int(config["min_plausible_budget"])
    min_revenue = int(config["min_plausible_revenue"])
    min_votes = int(config["min_votes_for_reliable_rating"])
    min_runtime = int(config["min_feature_runtime"])
    max_runtime = int(config["max_plausible_runtime"])
    extreme_roi = float(config["extreme_roi"])
    flop_roi = float(config["flop_roi"])

    rows: list[dict[str, Any]] = []
    current_year = pd.Timestamp.now(tz="UTC").year

    for film in analysis.itertuples(index=False):
        budget = None if pd.isna(film.budget) else int(film.budget)
        revenue = None if pd.isna(film.revenue) else int(film.revenue)

        # --- money that cannot be right ----------------------------------
        for column, value in (("budget", budget), ("revenue", revenue)):
            if value is None:
                _flag(rows, film, "money_missing", column, None, VERDICT_ERROR,
                      "no figure at all; the film cannot enter any money metric")
            elif value == 0:
                _flag(rows, film, "money_zero", column, 0, VERDICT_ERROR,
                      "zero is TMDb's 'unknown' and would compute an ROI of 0 or "
                      "infinity; a disguised null, not a figure")
            elif value < (min_budget if column == "budget" else min_revenue):
                _flag(rows, film, "money_implausibly_small", column, value,
                      VERDICT_ERROR,
                      f"{value:,} for a released feature suggests a figure entered "
                      "in millions rather than units")

        # --- money that is extreme but can be true -----------------------
        if budget and revenue:
            roi = revenue / budget
            if roi < flop_roi:
                _flag(rows, film, "revenue_below_budget", "revenue", revenue,
                      VERDICT_REAL,
                      f"ROI {roi:.2f}: a real theatrical loss, and exactly the "
                      "case CL1's 'franchises have a higher floor' claim is about. "
                      "Excluding it would delete the evidence for the claim")
            elif roi > extreme_roi:
                year = None if pd.isna(film.release_year) else int(film.release_year)
                _flag(rows, film, "roi_extreme", "revenue", revenue, VERDICT_REAL,
                      f"ROI {roi:.1f}x" + (
                          f", a {year} film: a low nominal budget against revenue "
                          "accumulated over later re-releases. True, and not "
                          "comparable with a modern film's ROI — see the era "
                          "comparability note" if year and year < 2000 else
                          ", verified against the source at stage 9"
                      ))

        # --- ratings too thin to carry weight ----------------------------
        if not pd.isna(film.vote_count) and int(film.vote_count) < min_votes:
            _flag(rows, film, "rating_on_few_votes", "vote_average",
                  film.vote_average, VERDICT_UNRELIABLE,
                  f"{int(film.vote_count):,} votes: the average is real but thin, "
                  "so it must not be used to rank a shortlist")

        # --- shape checks -------------------------------------------------
        if not pd.isna(film.runtime):
            runtime = int(film.runtime)
            if runtime < min_runtime:
                _flag(rows, film, "runtime_short", "runtime", runtime, VERDICT_CHECK,
                      f"{runtime} minutes: may be a short, a TV cut or a "
                      "mis-entered figure rather than a feature")
            elif runtime > max_runtime:
                _flag(rows, film, "runtime_long", "runtime", runtime, VERDICT_CHECK,
                      f"{runtime} minutes: may be a boxed set or an extended cut "
                      "standing in for the theatrical release")

        if not pd.isna(film.release_year) and int(film.release_year) > current_year:
            _flag(rows, film, "release_in_the_future", "release_year",
                  int(film.release_year), VERDICT_ERROR,
                  "a film that has not been released cannot have back-catalog "
                  "performance; its revenue figure describes nothing")

        if getattr(film, "status", None) is not None and not pd.isna(film.status) \
                and film.status != "Released":
            _flag(rows, film, "not_released", "status", film.status, VERDICT_ERROR,
                  f"status {film.status!r}: not a back-catalog title")

    flags = pd.DataFrame(rows, columns=FLAG_COLUMNS)
    if not flags.empty:
        flags["tmdb_id"] = flags["tmdb_id"].astype("Int64")
    return flags


def duplicate_titles(analysis: pd.DataFrame) -> pd.DataFrame:
    """Films sharing a title and year — two ids for one film, after all the
    deduplication stage 1 and 2 did on ids.

    A merged TMDb entry can be reachable under two ids that both return 200,
    so an id-level deduplication cannot catch it. Returns the suspects; it does
    not decide, because two different films can share a title (a remake).
    """
    keyed = analysis.dropna(subset=["title"]).copy()
    keyed["title_year"] = (
        keyed["title"].astype("str").str.lower().str.strip()
        + "|" + keyed["release_year"].astype("str")
    )
    duplicated = keyed.loc[keyed.duplicated("title_year", keep=False)]
    return duplicated[["tmdb_id", "title", "release_year"]].sort_values(
        ["title", "tmdb_id"], ignore_index=True
    )


# ---------------------------------------------------------------------------
# Cross-era comparability — a confound, not a fault
# ---------------------------------------------------------------------------

def era_comparability(analysis: pd.DataFrame, split_year: int = 2000) -> pd.DataFrame:
    """Money levels either side of the window boundary, so the gap is visible.

    Nothing here is wrong with the data. The point is that budget and revenue
    are **nominal** — the dollars of the year each film was made — and an
    old film's revenue also accumulates decades of re-release income earned in
    later, larger dollars. So a pre-2000 figure and a post-2000 figure are not
    the same unit, and the ratio of their medians is not a finding about
    filmmaking.

    This is computed rather than asserted because it is the strongest available
    answer to Yaw's claim that pre-2000 numbers cannot be trusted: he is right,
    for a specific reason, and the fix is to compare within a window rather
    than across one.
    """
    frame = analysis.dropna(subset=["release_year", "budget", "revenue"]).copy()
    if frame.empty:
        return pd.DataFrame(columns=["era", "films", "median_budget",
                                     "median_revenue", "median_roi"])
    frame["roi"] = frame["revenue"] / frame["budget"]
    frame["era"] = [
        f"pre-{split_year}" if year < split_year else f"{split_year}+"
        for year in frame["release_year"]
    ]
    summary = frame.groupby("era", as_index=False).agg(
        films=pd.NamedAgg("tmdb_id", "size"),
        median_budget=pd.NamedAgg("budget", "median"),
        median_revenue=pd.NamedAgg("revenue", "median"),
        median_roi=pd.NamedAgg("roi", "median"),
    )
    return summary.sort_values("era", ignore_index=True)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def summarise_flags(flags: pd.DataFrame) -> pd.DataFrame:
    """Flags by verdict and type — the table that goes in the diagnosis."""
    if flags.empty:
        return pd.DataFrame(columns=["verdict", "flag", "films"])
    return (
        flags.groupby(["verdict", "flag"], as_index=False)
        .agg(films=pd.NamedAgg("tmdb_id", "nunique"))
        .sort_values(["verdict", "films"], ascending=[True, False], ignore_index=True)
    )


def assert_profile(analysis: pd.DataFrame, flags: pd.DataFrame) -> list[str]:
    """Hard-assert that the profile is about the data we think it is."""
    notes: list[str] = []

    assert analysis["tmdb_id"].is_unique, "the analysis table is not one row per film"
    if not flags.empty:
        unknown = set(flags["verdict"]) - {
            VERDICT_ERROR, VERDICT_REAL, VERDICT_UNRELIABLE, VERDICT_CHECK,
        }
        assert not unknown, f"flags carry unknown verdicts: {sorted(unknown)}"
        assert (flags["why"].str.len() > 0).all(), "a flag has no reason recorded"
        orphans = set(flags["tmdb_id"]) - set(analysis["tmdb_id"])
        assert not orphans, f"flags reference films not in the analysis: {orphans}"

    errors = flags.loc[flags["verdict"] == VERDICT_ERROR] if not flags.empty \
        else flags
    if len(errors):
        notes.append(
            f"{errors['tmdb_id'].nunique()} film(s) carry a value that cannot be "
            f"right ({', '.join(sorted(set(errors['flag'])))}). Stage 6 decides "
            "what to do with each, and records it."
        )
    else:
        notes.append(
            "No film carries an impossible value: no zero or missing money, no "
            "unreleased title, no future release date. The fault this stage most "
            "expected to find is absent, and that is a result, not a skipped check."
        )

    reals = flags.loc[flags["verdict"] == VERDICT_REAL] if not flags.empty else flags
    if len(reals):
        notes.append(
            f"{reals['tmdb_id'].nunique()} film(s) hold a real extreme. These stay "
            "in every metric. Clipping them would remove the most informative "
            "films on the list — a 70x return on a 1977 film is the back-catalog "
            "case, not noise."
        )
    return notes


def profile_films(settings: Any, analysis: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Profile and classify. Produces the profile, the flags and the verdicts."""
    numeric_first = [
        "budget", "revenue", "runtime", "vote_average", "vote_count",
        "popularity", "release_year", "collection_members_on_list",
        "n_directors", "n_genres",
    ]
    columns = numeric_first + [
        column for column in analysis.columns if column not in numeric_first
    ]

    profile = profile_table(analysis, columns)
    flags = find_flags(analysis, settings)
    summary = summarise_flags(flags)
    eras = era_comparability(analysis)
    duplicates = duplicate_titles(analysis)

    for note in assert_profile(analysis, flags):
        print(f"[validate] {note}")

    if len(duplicates):
        print(
            f"[validate] NOTE: {len(duplicates)} film(s) share a title and year, so "
            "two ids may be one film. Id-level deduplication cannot catch a merged "
            f"TMDb entry: {duplicates['title'].tolist()}"
        )

    print(f"[validate] {len(flags)} flag(s) on {flags['tmdb_id'].nunique() if not flags.empty else 0} film(s)")
    if not summary.empty:
        print(summary.to_string(index=False))

    processed = settings.path(settings["paths"]["processed_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    profile.to_csv(processed / "profile.csv", index=False)
    flags.to_csv(processed / "flags.csv", index=False)
    eras.to_csv(processed / "era_comparability.csv", index=False)

    return {
        "profile": profile,
        "flags": flags,
        "flag_summary": summary,
        "era_comparability": eras,
        "duplicate_titles": duplicates,
    }

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

    ADR-010 kept three categories. The comparison the brief asks for has two
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


# ===========================================================================
# The stage entry point
# ===========================================================================

def validate(
    settings: Any, films: pd.DataFrame, ledger: pd.DataFrame
) -> dict[str, Any]:
    """Profile the films, classify every fault, then apply the cleaning rules.

    Runs on the **films** table, before any credit is joined onto it: every
    rule here reads film-level fields, and validating before the join keeps the
    pipeline a single pass through the five stages (ADR-032).

    Returns the cleaned table plus all the evidence: the profile, the flags
    with a verdict on each, the era-comparability note, the exclusions with the
    setting responsible for each, and the sensitivity runs.
    """
    profiled = profile_films(settings, films)
    cleaned = clean_films(settings, films, ledger)
    return {**profiled, **cleaned}
