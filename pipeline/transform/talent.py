"""Talent: which directors and leads reliably signal a title worth licensing.

The negotiators use talent as a lever, so this has to survive a negotiator
quoting it at a studio. Two things make that possible.

**The film count sits beside every name.** `min_films_for_reliable` filters the
*recommendation*, not the table: a name with 3 films and a name with 8 are not
the same evidence, and hiding the difference is how a shortlist acquires a
spurious star.

**A co-directed film counts for both directors.** The long directors table, not
the film-level label, is what every per-person statistic is computed from —
otherwise a 3-film partnership splits into two filmographies of 2 and 1 and
neither clears the threshold (M3).

The lead-only view is reported beside a top-3-billed view, because a performer
billed second is still a draw: widening the net takes the reliable names from 19
to 44, and 25 of those are invisible to a lead-only view. That is a finding, and
it was unreachable until the setting that controls it was actually wired up
(ADR-016).
"""
from __future__ import annotations

from typing import Any

import pandas as pd


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


def billed_as_credits(cast: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """The top `top_n` billed actors per film, shaped like directors_long.

    The alternative to judging an actor by their lead roles only: a performer
    billed second or third is still a draw, and on a 112-film list the
    lead-only view leaves most of the cast unexamined.
    """
    billed = cast.loc[
        cast["billing_order"].notna() & (cast["billing_order"] < int(top_n)),
        ["tmdb_id", "person_id", "person_name"],
    ]
    return billed.drop_duplicates(["tmdb_id", "person_id"], ignore_index=True)


def talent_sensitivity(
    cast: pd.DataFrame, cleaned: pd.DataFrame, settings: Any
) -> pd.DataFrame:
    """Does the reliable-talent list survive widening from leads to top-N billed?

    `talent.sensitivity_top_n_billed` has existed since the planning stage with
    the comment "re-run the talent analysis on top-3 billed", and until an
    audit found it, nothing read it — a rejected alternative that was supposed
    to stay runnable and never was. This is that run.

    Returns one row per person who clears `min_films_for_reliable` under either
    view, with the film count and median return under each, so a name that
    appears only when the net is widened is visible as such rather than
    arriving unexplained.
    """
    top_n = int(settings["talent"]["sensitivity_top_n_billed"])
    minimum = int(settings["talent"]["min_films_for_reliable"])

    lead_view = talent_table(leads_as_credits(cleaned), cleaned, settings, "lead_actor")
    billed_view = talent_table(
        billed_as_credits(cast, top_n), cleaned, settings, f"top_{top_n}_billed"
    )
    if lead_view.empty and billed_view.empty:
        return pd.DataFrame(columns=["person_id", "person_name", "films_as_lead",
                                     "median_roi_as_lead", f"films_top_{top_n}",
                                     f"median_roi_top_{top_n}", "appears_only_when_widened"])

    keep = ["person_id", "person_name", "films", "median_roi", "meets_min_films"]
    merged = (
        lead_view[keep].rename(columns={
            "films": "films_as_lead", "median_roi": "median_roi_as_lead",
            "meets_min_films": "reliable_as_lead",
        })
        .merge(
            billed_view[keep].rename(columns={
                "films": f"films_top_{top_n}",
                "median_roi": f"median_roi_top_{top_n}",
                "meets_min_films": f"reliable_top_{top_n}",
            }),
            on=["person_id", "person_name"], how="outer",
        )
    )
    for column in ("reliable_as_lead", f"reliable_top_{top_n}"):
        merged[column] = merged[column].fillna(False).astype("boolean")

    merged = merged.loc[
        merged["reliable_as_lead"].fillna(False)
        | merged[f"reliable_top_{top_n}"].fillna(False)
    ].copy()
    merged["appears_only_when_widened"] = (
        ~merged["reliable_as_lead"].fillna(False)
        & merged[f"reliable_top_{top_n}"].fillna(False)
    )
    merged.attrs["min_films_for_reliable"] = minimum
    merged.attrs["top_n"] = top_n
    return merged.sort_values(
        [f"median_roi_top_{top_n}", "median_roi_as_lead"],
        ascending=False, ignore_index=True,
    )
