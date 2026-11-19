"""Profiling, and separating real extremes from errors.

Two jobs, and the second one is the hard one.

**Profile** every column: how much is present, how much is zero, and the shape
of the distribution. Zeros are counted separately from nulls, because a zero
budget is TMDb's way of saying "unknown" and would never appear in a null
count. Percentiles rather than mean and standard deviation, because money is
heavily skewed and an SD on a skewed distribution invites exactly the "anything
beyond 3 sigma is an error" reasoning this module exists to refuse.

**Separate real extremes from errors.** *Star Wars* returned 70 times its
budget. That is not an outlier to be clipped — it is the single most relevant
data point on the list, because the whole question is whether old films are
worth licensing. So the rule is **flag with a reason, classify, never delete**,
and every flag carries a verdict:

    error            the value cannot be right (a budget of 5, a zero)
    real_extreme     unusual and true — stays in every metric
    unreliable       true but too thin to carry weight (a rating on 40 votes)
    check            needs a human to look; nothing is excluded on a check

Nothing here excludes a film. `clean.py` acts on the verdicts, so the decision
to drop a film from a metric is always traceable to a sentence, never to a
quantile. See ADR-016.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


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
