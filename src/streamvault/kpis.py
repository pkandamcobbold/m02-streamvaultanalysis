"""Stage 7 — the KPI tables. Both windows, counts beside every statistic.

Three rules, each of which is a way of not misleading the reader.

**1. Counts beside every statistic.** A median with no `n` under it is not a
finding. It matters more here than usual: the standalone group is 25 films, and
8 of them post-2000 (F7), so a figure quoted without its denominator invites
exactly the wrong amount of confidence.

**2. The window is a parameter, never copy-pasted code.** One function called
twice. Two blocks that look alike are how the windows silently diverge when
somebody edits one of them.

**3. Statistics chosen for the question actually asked.** Kwame's team claims
franchises are the *safer* buy. Safety is a claim about the **floor** and the
**spread**, not the average, so the lower quartile and the interquartile range
carry more weight here than the mean — and the mean is reported beside them
only so the difference is visible.

Relative hit flags are recomputed inside every window (DR-17). Nothing in this
module loops over rows to produce a number: every figure comes from a named
aggregation over a group.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .clean import add_hit_flags

GROUP_STRICT = "franchise_group_strict"
GROUP_LOOSE = "franchise_group_loose"

POSITION_FIRST = "first"
POSITION_MIDDLE = "middle"
POSITION_LAST = "last"


# ---------------------------------------------------------------------------
# The core comparison
# ---------------------------------------------------------------------------

def _p25(series: pd.Series) -> float:
    return series.quantile(0.25)


def _p75(series: pd.Series) -> float:
    return series.quantile(0.75)


def compare_groups(
    films: pd.DataFrame, group_column: str = GROUP_STRICT, min_year: int | None = None
) -> pd.DataFrame:
    """Franchise against standalone for one window. `min_year=None` is all years.

    Named aggregation throughout, counts beside every statistic, no row loops.

    `floor_roi` is the lower quartile rather than the minimum: a single worst
    film is an anecdote, and on this list the minimum is 1.13x for everyone
    (F12). The quartile is what "higher floor" can actually be measured as.
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
    # 70x returns (F11) inflate an SD without telling you anything about the
    # typical gap between a good and a bad film in the group.
    table["iqr_roi"] = table["upper_roi"] - table["floor_roi"]
    return table.round(3)


def by_window(
    cleaned: pd.DataFrame, settings: Any, group_column: str = GROUP_STRICT
) -> dict[str, pd.DataFrame]:
    """One comparison per configured window, each computed in its own pool.

    The relative hit flags are recomputed inside each window before the
    comparison, which is the whole of DR-17: inherited flags would measure
    modern films against a median partly set by 1970s films.
    """
    tables: dict[str, pd.DataFrame] = {}
    for name, window in settings.windows.items():
        min_year = window["min_year"]
        scope = cleaned if min_year is None else cleaned.loc[
            cleaned["release_year"].notna() & (cleaned["release_year"] >= min_year)
        ]
        rescoped = add_hit_flags(scope.copy(), settings)
        tables[name] = compare_groups(rescoped, group_column, min_year=None)
    return tables


def flip_check(tables: dict[str, pd.DataFrame], group_column: str = GROUP_STRICT) -> pd.DataFrame:
    """Does the winner change between windows, and on which measure?

    Richer than a single boolean on purpose. The recommendation can hold on the
    median and flip on the floor, and that is a different conversation with
    Kwame than "it flips" or "it holds" — so every measure is checked and
    reported separately.
    """
    measures = ["median_roi", "floor_roi", "hit_rate_roi", "iqr_roi"]
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
            "size of the answer (F10), not its direction."
        )
    return notes


# ---------------------------------------------------------------------------
# Inside a franchise: are the middle entries the weak ones?
# ---------------------------------------------------------------------------

def position_within_franchise(cleaned: pd.DataFrame, min_entries: int = 3) -> pd.DataFrame:
    """CL2: compare first, middle and last entries inside each collection.

    `min_entries=3` because a two-film collection has no middle, and including
    it would put its second film in the "last" bucket and silently change what
    "last" means. Ranked by release date, which is the order a viewer met them
    in and the order a bundle is built in.
    """
    scope = cleaned.loc[
        cleaned["collection_id"].notna() & cleaned["in_money_metrics"].fillna(False)
    ].copy()
    if scope.empty:
        return pd.DataFrame(columns=["position", "films", "collections",
                                     "median_roi", "floor_roi", "median_revenue"])

    scope["entries_on_list"] = scope.groupby("collection_id")["tmdb_id"].transform("size")
    scope = scope.loc[scope["entries_on_list"] >= min_entries].copy()
    if scope.empty:
        return pd.DataFrame(columns=["position", "films", "collections",
                                     "median_roi", "floor_roi", "median_revenue"])

    scope["entry_rank"] = (
        scope.groupby("collection_id")["release_date"].rank(method="first").astype("Int64")
    )
    scope["position"] = POSITION_MIDDLE
    scope.loc[scope["entry_rank"] == 1, "position"] = POSITION_FIRST
    scope.loc[scope["entry_rank"] == scope["entries_on_list"], "position"] = POSITION_LAST

    table = scope.groupby("position", as_index=False).agg(
        films=pd.NamedAgg("tmdb_id", "size"),
        collections=pd.NamedAgg("collection_id", "nunique"),
        median_roi=pd.NamedAgg("roi", "median"),
        floor_roi=pd.NamedAgg("roi", _p25),
        median_revenue=pd.NamedAgg("revenue", "median"),
        median_rating=pd.NamedAgg("vote_average", "median"),
    )
    order = {POSITION_FIRST: 0, POSITION_MIDDLE: 1, POSITION_LAST: 2}
    table = table.sort_values("position", key=lambda s: s.map(order), ignore_index=True)
    return table.round(3)


def gap_to_best_entry(cleaned: pd.DataFrame, min_entries: int = 2) -> pd.DataFrame:
    """How far below its collection's best entry does a typical entry sit?

    The other half of CL2. "We overpay for weak middle entries" is a claim
    about the gap *within* a bundle, which a cross-collection median hides: a
    bundle whose films are all mediocre and one whose opener carries it can
    have the same median.
    """
    scope = cleaned.loc[
        cleaned["collection_id"].notna() & cleaned["in_money_metrics"].fillna(False)
    ].copy()
    if scope.empty:
        return pd.DataFrame(columns=["collection_name", "entries_on_list", "best_roi",
                                     "median_roi", "worst_roi", "best_share_of_revenue"])

    scope["entries_on_list"] = scope.groupby("collection_id")["tmdb_id"].transform("size")
    scope = scope.loc[scope["entries_on_list"] >= min_entries]

    table = scope.groupby(["collection_id", "collection_name"], as_index=False).agg(
        entries_on_list=pd.NamedAgg("tmdb_id", "size"),
        best_roi=pd.NamedAgg("roi", "max"),
        median_roi=pd.NamedAgg("roi", "median"),
        worst_roi=pd.NamedAgg("roi", "min"),
        total_revenue=pd.NamedAgg("revenue", "sum"),
        top_film_revenue=pd.NamedAgg("revenue", "max"),
    )
    table["best_to_median"] = (table["best_roi"] / table["median_roi"]).round(2)
    # Question 6: the single number that drives a bundle's value.
    table["best_share_of_revenue"] = (
        table["top_film_revenue"] / table["total_revenue"]
    ).round(3)
    return table.sort_values("median_roi", ascending=False, ignore_index=True).round(3)


# ---------------------------------------------------------------------------
# Bundle economics — the unit of purchase
# ---------------------------------------------------------------------------

def bundle_table(cleaned: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """One row per collection: a bundle is what Kwame actually buys.

    Aggregated to the collection because a per-film median answers a question
    nobody is asking. A bundle's value is its total; its risk is its weakest
    entry — both are here, beside the count of how many of its films are even
    on offer.
    """
    minimum = int(settings["franchise"]["min_members_on_list"])
    scope = cleaned.loc[
        cleaned["collection_id"].notna() & cleaned["in_money_metrics"].fillna(False)
    ]
    if scope.empty:
        return pd.DataFrame(columns=["collection_name", "films_on_list", "median_roi"])

    table = scope.groupby(["collection_id", "collection_name"], as_index=False).agg(
        films_on_list=pd.NamedAgg("tmdb_id", "size"),
        median_roi=pd.NamedAgg("roi", "median"),
        floor_roi=pd.NamedAgg("roi", "min"),
        best_roi=pd.NamedAgg("roi", "max"),
        total_revenue=pd.NamedAgg("revenue", "sum"),
        total_budget=pd.NamedAgg("budget", "sum"),
        median_rating=pd.NamedAgg("vote_average", "median"),
        first_year=pd.NamedAgg("release_year", "min"),
        last_year=pd.NamedAgg("release_year", "max"),
    )
    table["bundle_roi"] = (table["total_revenue"] / table["total_budget"]).round(3)
    table["is_buyable_bundle"] = table["films_on_list"] >= minimum
    return table.sort_values("median_roi", ascending=False, ignore_index=True).round(3)


# ---------------------------------------------------------------------------
# Talent
# ---------------------------------------------------------------------------

def talent_table(
    credits: pd.DataFrame, cleaned: pd.DataFrame, settings: Any, role: str
) -> pd.DataFrame:
    """Per-person performance, with the film count beside every name.

    `min_films_for_reliable` filters the *recommendation*, not the table: the
    count stays visible so a negotiator can see a three-film record for what it
    is. A name with 3 films and a name with 8 are not the same evidence, and
    hiding the difference is how a shortlist acquires a spurious star.
    """
    minimum = int(settings["talent"]["min_films_for_reliable"])
    money = cleaned.loc[cleaned["in_money_metrics"].fillna(False)]
    overall_median = money["roi"].astype("float64").median()

    joined = credits.merge(
        money[["tmdb_id", "roi", "is_hit_roi", "vote_average", "release_year"]],
        on="tmdb_id", how="inner", validate="many_to_one",
    )
    if joined.empty:
        return pd.DataFrame(columns=["person_id", "person_name", "role", "films",
                                     "median_roi", "above_overall_median"])

    table = joined.groupby(["person_id", "person_name"], as_index=False).agg(
        films=pd.NamedAgg("tmdb_id", "nunique"),
        median_roi=pd.NamedAgg("roi", "median"),
        floor_roi=pd.NamedAgg("roi", "min"),
        best_roi=pd.NamedAgg("roi", "max"),
        hit_rate_roi=pd.NamedAgg("is_hit_roi", "mean"),
        median_rating=pd.NamedAgg("vote_average", "median"),
        first_year=pd.NamedAgg("release_year", "min"),
        last_year=pd.NamedAgg("release_year", "max"),
    )
    table["role"] = role
    table["above_overall_median"] = table["median_roi"] > overall_median
    table["meets_min_films"] = table["films"] >= minimum
    return table.sort_values(
        ["meets_min_films", "median_roi"], ascending=[False, False], ignore_index=True
    ).round(3)


def leads_as_credits(cleaned: pd.DataFrame) -> pd.DataFrame:
    """The lead-actor columns, reshaped to the same shape as directors_long."""
    leads = cleaned.loc[cleaned["lead_person_id"].notna(),
                        ["tmdb_id", "lead_person_id", "lead_name"]]
    return leads.rename(columns={"lead_person_id": "person_id", "lead_name": "person_name"})


# ---------------------------------------------------------------------------
# The shortlist
# ---------------------------------------------------------------------------

def shortlist(
    cleaned: pd.DataFrame, bundles: pd.DataFrame, settings: Any
) -> dict[str, pd.DataFrame]:
    """Three franchises and five standalones, by a rule simple enough to say.

    The rule: rank by median ROI within the group, having first required that
    the thing is actually buyable (a bundle needs `min_members_on_list` films
    on offer). Runners-up are included because "why it made the cut" means
    nothing without what did not.
    """
    n_franchises = int(settings["shortlist"]["n_franchises"])
    n_standalones = int(settings["shortlist"]["n_standalones"])
    runners = int(settings["shortlist"]["show_runners_up"])

    buyable = bundles.loc[bundles["is_buyable_bundle"]].copy()
    franchise_columns = ["collection_name", "films_on_list", "median_roi", "floor_roi",
                         "best_roi", "bundle_roi", "total_revenue", "median_rating",
                         "first_year", "last_year"]
    franchises = buyable.head(n_franchises + runners)[franchise_columns].copy()
    franchises["selected"] = [True] * min(n_franchises, len(franchises)) + \
        [False] * max(0, len(franchises) - n_franchises)

    standalones = cleaned.loc[
        (cleaned[GROUP_STRICT] == "standalone")
        & cleaned["in_money_metrics"].fillna(False)
    ].sort_values("roi", ascending=False, ignore_index=True)
    standalone_columns = ["tmdb_id", "title", "release_year", "roi", "revenue",
                          "budget", "vote_average", "vote_count", "rating_reliable",
                          "franchise_status"]
    standalones = standalones.head(n_standalones + runners)[standalone_columns].copy()
    standalones["selected"] = [True] * min(n_standalones, len(standalones)) + \
        [False] * max(0, len(standalones) - n_standalones)

    return {"franchises": franchises.round(3), "standalones": standalones.round(3)}


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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(
    settings: Any, cleaned: pd.DataFrame, directors: pd.DataFrame
) -> dict[str, Any]:
    """Stage 7 entry point. Every KPI table, both windows, plus the flip check."""
    strict = by_window(cleaned, settings, GROUP_STRICT)
    loose = by_window(cleaned, settings, GROUP_LOOSE)
    flips = flip_check(strict, GROUP_STRICT)

    for note in assert_kpis(strict, cleaned, GROUP_STRICT):
        print(f"[stage 7] {note}")
    for line in announce_flip(flips):
        print(f"[stage 7] {line}")

    bundles = bundle_table(cleaned, settings)
    positions = position_within_franchise(cleaned)
    gaps = gap_to_best_entry(cleaned)
    director_talent = talent_table(directors, cleaned, settings, "director")
    lead_talent = talent_table(leads_as_credits(cleaned), cleaned, settings, "lead_actor")
    picks = shortlist(cleaned, bundles, settings)

    processed = settings.path(settings["paths"]["processed_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    for window, table in strict.items():
        table.to_csv(processed / f"kpi_{window}.csv", index=False)
    for window, table in loose.items():
        table.to_csv(processed / f"kpi_{window}_lone_as_franchise.csv", index=False)
    flips.to_csv(processed / "kpi_flip_check.csv", index=False)
    bundles.to_csv(processed / "kpi_bundles.csv", index=False)
    positions.to_csv(processed / "kpi_position_in_franchise.csv", index=False)
    gaps.to_csv(processed / "kpi_bundle_gaps.csv", index=False)
    director_talent.to_csv(processed / "kpi_talent_directors.csv", index=False)
    lead_talent.to_csv(processed / "kpi_talent_leads.csv", index=False)
    picks["franchises"].to_csv(processed / "shortlist_franchises.csv", index=False)
    picks["standalones"].to_csv(processed / "shortlist_standalones.csv", index=False)

    print(f"[stage 7] {len(bundles)} collections, "
          f"{int(bundles['is_buyable_bundle'].sum())} of them buyable bundles")
    print(f"[stage 7] {int(director_talent['meets_min_films'].sum())} directors and "
          f"{int(lead_talent['meets_min_films'].sum())} leads meet the film minimum")

    return {
        "windows_strict": strict,
        "windows_loose": loose,
        "flips": flips,
        "bundles": bundles,
        "positions": positions,
        "bundle_gaps": gaps,
        "talent_directors": director_talent,
        "talent_leads": lead_talent,
        "shortlist": picks,
    }
