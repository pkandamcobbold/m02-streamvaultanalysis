"""The central comparison: franchise against standalone, in both windows.

Three rules, each of which is a way of not misleading the reader.

**1. Counts beside every statistic.** A median with no `n` under it is not a
finding. It matters more here than usual: the standalone group is 25 films, and
12 of them post-2000, so a figure quoted without its denominator invites
exactly the wrong amount of confidence.

**2. The window is a parameter, never copy-pasted code.** One function called
twice. Two blocks that look alike are how the windows silently diverge when
somebody edits one of them.

**3. Statistics chosen for the question actually asked.** The team's claim is
that franchises are the *safer* buy. Safety is a claim about the **floor** and
the **spread**, not the average, so the lower quartile and the interquartile
range carry more weight here than the mean — and the mean is reported beside
them only so the disagreement is visible, because it reverses the answer
(M6).

The flip check tests every measure rather than just the median, because the
recommendation can hold on the median and flip on the spread, and that is a
different conversation (M11). Nothing here loops over rows to produce a
number: every figure comes from a named aggregation over a group. See the note
on row loops at the end of docs/method.md.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.validate import add_hit_flags


# ===========================================================================
# The KPI tables: both windows, counts beside every statistic
# (was src/streamvault/kpis.py)
# ===========================================================================

GROUP_STRICT = "franchise_group_strict"


GROUP_LOOSE = "franchise_group_loose"


# `performance.hit_definition` names one of these. All three are computed at
# stage 6; this decides which one the reports treat as *the* hit rate, and
# `report_all_hit_definitions` decides whether the other two travel with it.
#
# Both settings were inert until an audit found them: the code reported all
# three unconditionally while M9 credited a setting with that behaviour.
# A switch nothing reads is worse than no switch, because the decision record
# claims it can be flipped.
HIT_RATE_COLUMNS = {
    "roi": "hit_rate_roi",
    "above_median": "hit_rate_above_median",
    "top_quartile": "hit_rate_top_quartile",
}


# ---------------------------------------------------------------------------
# The core comparison
# ---------------------------------------------------------------------------

def _p25(series: pd.Series) -> float:
    return series.quantile(0.25)


def _p75(series: pd.Series) -> float:
    return series.quantile(0.75)


def primary_hit_column(settings: Any) -> str:
    """The hit-rate column `performance.hit_definition` selects."""
    definition = str(settings["performance"]["hit_definition"])
    if definition not in HIT_RATE_COLUMNS:
        raise ValueError(
            f"performance.hit_definition is {definition!r}; expected one of "
            f"{sorted(HIT_RATE_COLUMNS)}"
        )
    return HIT_RATE_COLUMNS[definition]


def compare_groups(
    films: pd.DataFrame,
    group_column: str = GROUP_STRICT,
    min_year: int | None = None,
    settings: Any = None,
) -> pd.DataFrame:
    """Franchise against standalone for one window. `min_year=None` is all years.

    Named aggregation throughout, counts beside every statistic, no row loops.

    `floor_roi` is the lower quartile rather than the minimum: a single worst
    film is an anecdote, and on this list the minimum is 1.13x for everyone
    (F-01). The quartile is what "higher floor" can actually be measured as.
    """
    scope = films if min_year is None else films.loc[
        films["release_year"].notna() & (films["release_year"] >= min_year)
    ]
    money = scope.loc[scope["in_money_metrics"].fillna(False)]

    if money.empty:
        return pd.DataFrame(columns=[
            group_column, "films", "median_roi", "floor_roi", "upper_roi",
            "iqr_roi", "mean_roi", "min_roi", "max_roi", "hit_rate_roi",
            "hits_roi", "hit_rate_above_median", "hit_rate_top_quartile",
            "median_revenue", "median_budget", "median_rating", "median_votes",
        ])

    table = money.groupby(group_column, as_index=False).agg(
        films=pd.NamedAgg("tmdb_id", "size"),
        median_roi=pd.NamedAgg("roi", "median"),
        floor_roi=pd.NamedAgg("roi", _p25),
        upper_roi=pd.NamedAgg("roi", _p75),
        mean_roi=pd.NamedAgg("roi", "mean"),
        min_roi=pd.NamedAgg("roi", "min"),
        max_roi=pd.NamedAgg("roi", "max"),
        hits_roi=pd.NamedAgg("is_hit_roi", "sum"),
        hit_rate_roi=pd.NamedAgg("is_hit_roi", "mean"),
        hit_rate_above_median=pd.NamedAgg("is_hit_above_median", "mean"),
        hit_rate_top_quartile=pd.NamedAgg("is_hit_top_quartile", "mean"),
        median_revenue=pd.NamedAgg("revenue", "median"),
        median_budget=pd.NamedAgg("budget", "median"),
        median_rating=pd.NamedAgg("vote_average", "median"),
        median_votes=pd.NamedAgg("vote_count", "median"),
    )
    # Spread as the interquartile range, not the standard deviation: a few real
    # 70x returns (F-06) inflate an SD without telling you anything about the
    # typical gap between a good and a bad film in the group.
    table["iqr_roi"] = table["upper_roi"] - table["floor_roi"]

    if settings is not None:
        primary = primary_hit_column(settings)
        table["hit_rate_primary"] = table[primary]
        table.attrs["hit_definition"] = settings["performance"]["hit_definition"]
        if not bool(settings["performance"]["report_all_hit_definitions"]):
            # Drop the alternatives the reader asked not to see. Kept as a
            # setting rather than hard-coded because F-01 is the reason all
            # three are normally shown: on a list with no failures in it, no
            # single definition is defensible alone.
            table = table.drop(columns=[
                column for column in HIT_RATE_COLUMNS.values() if column != primary
            ])
    return table.round(3)


def by_window(
    cleaned: pd.DataFrame, settings: Any, group_column: str = GROUP_STRICT
) -> dict[str, pd.DataFrame]:
    """One comparison per configured window, each computed in its own pool.

    The relative hit flags are recomputed inside each window before the
    comparison, which is the whole of M10: inherited flags would measure
    modern films against a median partly set by 1970s films.
    """
    tables: dict[str, pd.DataFrame] = {}
    for name, window in settings.windows.items():
        min_year = window["min_year"]
        scope = cleaned if min_year is None else cleaned.loc[
            cleaned["release_year"].notna() & (cleaned["release_year"] >= min_year)
        ]
        rescoped = add_hit_flags(scope.copy(), settings)
        tables[name] = compare_groups(
            rescoped, group_column, min_year=None, settings=settings
        )
    return tables


def flip_check(tables: dict[str, pd.DataFrame], group_column: str = GROUP_STRICT) -> pd.DataFrame:
    """Does the winner change between windows, and on which measure?

    Richer than a single boolean on purpose. The recommendation can hold on the
    median and flip on the floor, and that is a different conversation with
    Kwame than "it flips" or "it holds" — so every measure is checked and
    reported separately.
    """
    # Check the hit rate the reports actually lead with. With a non-default
    # hit_definition, `hit_rate_roi` may not even be in the table.
    sample = next(iter(tables.values()), pd.DataFrame())
    hit_column = (
        "hit_rate_primary" if "hit_rate_primary" in sample.columns else "hit_rate_roi"
    )
    measures = ["median_roi", "floor_roi", hit_column, "iqr_roi"]
    rows: list[dict[str, Any]] = []

    for measure in measures:
        winners: dict[str, Any] = {}
        for window, table in tables.items():
            if table.empty or measure not in table.columns:
                winners[window] = pd.NA
                continue
            # For spread, lower is better: a tighter group is the safer buy.
            index = table[measure].idxmin() if measure == "iqr_roi" \
                else table[measure].idxmax()
            winners[window] = table.loc[index, group_column]

        distinct = {value for value in winners.values() if not pd.isna(value)}
        rows.append({
            "measure": measure,
            "better_is": "lower" if measure == "iqr_roi" else "higher",
            **{f"winner_{window}": value for window, value in winners.items()},
            "flipped": len(distinct) > 1,
        })

    return pd.DataFrame(rows)


def announce_flip(flips: pd.DataFrame) -> list[str]:
    """Say it loudly if any measure flips. The brief asks for loudly."""
    notes: list[str] = []
    flipped = flips.loc[flips["flipped"]]
    if len(flipped):
        notes.append("=" * 70)
        notes.append(
            "RECOMMENDATION FLIPS BETWEEN WINDOWS on: "
            + ", ".join(flipped["measure"].tolist())
        )
        notes.append("This belongs in the memo's first paragraph, not a footnote.")
        notes.append("=" * 70)
    else:
        notes.append(
            "No measure flips between windows: the same group leads on median, "
            "floor, hit rate and spread in both. Yaw's objection changes the "
            "size of the answer (F-05), not its direction."
        )
    return notes


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def assert_kpis(
    tables: dict[str, pd.DataFrame], cleaned: pd.DataFrame, group_column: str = GROUP_STRICT
) -> list[str]:
    """Hard-assert the tables describe the films we think they do."""
    notes: list[str] = []
    eligible = int(cleaned["in_money_metrics"].fillna(False).sum())

    for window, table in tables.items():
        if table.empty:
            notes.append(f"NOTE: the {window} window has no films in money metrics.")
            continue

        # Counts beside every statistic is not decoration: it is the assertion
        # that the groups partition the window exactly.
        assert "films" in table.columns, f"{window}: no count column"
        assert table["films"].notna().all(), f"{window}: a group has no count"
        assert table[group_column].is_unique, f"{window}: a group appears twice"

        if window == "all_years":
            assert int(table["films"].sum()) == eligible, (
                f"all_years groups hold {int(table['films'].sum())} films, "
                f"but {eligible} are in money metrics"
            )

        thin = table.loc[table["films"] < 10]
        for row in thin.itertuples(index=False):
            notes.append(
                f"NOTE: in the {window} window, {getattr(row, group_column)} has only "
                f"{int(row.films)} films. Every statistic for that group is reported "
                "with its n for this reason; a median over this many films moves "
                "materially if one film enters or leaves."
            )
    return notes
