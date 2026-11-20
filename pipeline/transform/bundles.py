"""What Kwame actually buys: bundles, position in a franchise, and the shortlist.

A per-film median answers a question nobody is asking. A **bundle** is the unit
of purchase, so it gets its own table: its value is its total, its risk is its
weakest entry, and both sit beside the count of how many of its films are even
on offer.

**Position within a franchise** tests the other half of the team's argument — that
the weak middle entries are what StreamVault overpays for. Read inside one era,
because position is confounded with age and era inflates returns: pooled, the
decline from opener to final entry is 43%; within one era it is 14%, and middle
entries sit *above* last entries, so the team's specific belief is not
supported even though the general direction is (M7).

**The shortlist** ranks by a rule simple enough to say out loud, having first
required that the thing is actually buyable, and carries the runners-up — "why
it made the cut" means nothing without what did not — and each pick's franchise
status, because calling *Jaws* a standalone without qualification is a sentence
a board member could reasonably object to (M12).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.transform.kpis import GROUP_STRICT, _p25


POSITION_FIRST = "first"


POSITION_MIDDLE = "middle"


POSITION_LAST = "last"


# ---------------------------------------------------------------------------
# Inside a franchise: are the middle entries the weak ones?
# ---------------------------------------------------------------------------


def _franchises_born_in(scope: pd.DataFrame, min_year: int) -> pd.Index:
    """The collections whose earliest entry falls in the window.

    A franchise is in or out whole. Admitting a 1977 franchise on the strength
    of its 2015 sequel is what makes an opener cell and a final-entry cell hold
    different franchises, and that is the confound these windows exist to
    remove.
    """
    earliest = scope.groupby("collection_id")["release_year"].min()
    return earliest.loc[earliest.notna() & (earliest >= min_year)].index


def position_within_franchise(
    cleaned: pd.DataFrame,
    min_entries: int = 3,
    window_min_year: int | None = None,
) -> pd.DataFrame:
    """CL2: compare first, middle and last entries inside each collection.

    `min_entries=3` because a two-film collection has no middle, and including
    it would put its second film in the "last" bucket and silently change what
    "last" means. Ranked by release date, which is the order a viewer met them
    in and the order a bundle is built in.

    `window_min_year` keeps the franchises whose **opener** falls in the window
    and ranks those whole, which is the only reading of "hold age still" that
    survives being said out loud (S-07). The two obvious alternatives both
    break the comparison:

    * Filter the films to the window and then rank. A franchise straddling the
      boundary is re-ranked, so its third film is counted as an opener — a
      fresh distortion in the one comparison built to remove one.
    * Rank first and filter after. Positions stay true, but the opener cell
      then holds only franchises that began in the window while the final cell
      also holds old franchises' last entries, so the cells are different
      franchises and the gap between them is partly a gap between sets.

    Keeping whole franchises costs sample — a franchise that began in 1977 is
    out of the window entirely, however modern its later entries — and buys
    the one thing the claim needs: every cell holds the same franchises.
    """
    scope = cleaned.loc[
        cleaned["collection_id"].notna() & cleaned["in_money_metrics"].fillna(False)
    ].copy()
    if scope.empty:
        return pd.DataFrame(columns=["position", "films", "collections",
                                     "median_roi", "floor_roi", "median_revenue"])

    if window_min_year is not None:
        scope = scope.loc[
            scope["collection_id"].isin(_franchises_born_in(scope, window_min_year))].copy()
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


def paired_position_ratio(
    cleaned: pd.DataFrame,
    min_entries: int = 3,
    window_min_year: int | None = None,
) -> pd.DataFrame:
    """Each franchise as its own control: its final entry's return over its opener's.

    The first/middle/last table compares cells of films, so a cell's figure
    moves when the mix of franchises in it moves. This one never compares
    across franchises at all — every number is one collection's last entry
    against its own opener, so cast, genre, audience and studio cancel out.
    It is the version to quote when someone asks whether the effect is real
    rather than how big it is.

    A median ratio above 1 means later instalments return *more*. The share
    below 1 is the honest companion: a median of 1.27 on 11 franchises with 4
    of them declining is a tendency, not a law, and the table says so.
    """
    scope = cleaned.loc[
        cleaned["collection_id"].notna() & cleaned["in_money_metrics"].fillna(False)
    ].copy()
    columns = ["basis", "franchises", "median_last_over_first",
               "share_declining", "median_opener_year"]
    if scope.empty:
        return pd.DataFrame(columns=columns)

    if window_min_year is not None:
        scope = scope.loc[
            scope["collection_id"].isin(_franchises_born_in(scope, window_min_year))].copy()

    scope = scope.loc[
        scope.groupby("collection_id")["tmdb_id"].transform("size") >= min_entries]
    if scope.empty:
        return pd.DataFrame(columns=columns)

    ordered = scope.sort_values(["collection_id", "release_date"])
    by_collection = ordered.groupby("collection_id")
    paired = pd.DataFrame({
        "first_roi": by_collection["roi"].first().astype("float64"),
        "last_roi": by_collection["roi"].last().astype("float64"),
        "opener_year": by_collection["release_year"].first().astype("Float64"),
    })
    # An opener at or below zero return cannot carry a ratio, so it is dropped
    # rather than quietly producing an infinity.
    paired = paired.loc[paired["first_roi"] > 0]
    if paired.empty:
        return pd.DataFrame(columns=columns)

    ratios = paired["last_roi"] / paired["first_roi"]
    basis = ("franchises that began in or after "
             f"{window_min_year}" if window_min_year is not None else "all franchises")
    return pd.DataFrame([{
        "basis": basis,
        "franchises": int(len(ratios)),
        "median_last_over_first": round(float(ratios.median()), 3),
        "share_declining": round(float((ratios < 1).mean()), 3),
        "median_opener_year": int(paired["opener_year"].median()),
    }], columns=columns)

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
