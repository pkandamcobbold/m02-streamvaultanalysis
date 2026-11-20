"""Stage 3 — transform: prove the join, then answer each of Kwame's questions.

One stage, four jobs, one module each (ADR-018):

    join.py      collapse the credit tables to film grain and merge, with every
                 merge validated, counted and written to a join report
    kpis.py      the central comparison: franchise against standalone, in both
                 windows, with counts beside every statistic and a flip check
    bundles.py   what Kwame actually buys: the bundle as a unit, position
                 within a series, and the shortlist drawn from both
    talent.py    which directors and leads reliably signal a title worth buying

The split follows the brief's questions rather than the code's convenience: the
recommendation, the shortlist, the talent lever and the deal note are four
things a reader asks about separately, and now they are four files.

Callers import the stage, not its parts: `transform.compare_groups`,
`transform.GROUP_STRICT` and `transform.transform` all work.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.transform.bundles import (
    POSITION_FIRST,
    POSITION_LAST,
    POSITION_MIDDLE,
    bundle_table,
    gap_to_best_entry,
    position_within_franchise,
    shortlist,
)
from pipeline.transform.join import (
    DIRECTOR_JOB,
    JOIN_REPORT_COLUMNS,
    LEAD_BILLING_ORDER,
    account_for_every_id,
    assert_join,
    build_analysis_table,
    collapse_directors,
    collapse_genres,
    collapse_leads,
    directors_long,
    join_tables,
)
from pipeline.transform.kpis import (
    GROUP_LOOSE,
    GROUP_STRICT,
    HIT_RATE_COLUMNS,
    announce_flip,
    assert_kpis,
    by_window,
    compare_groups,
    flip_check,
    primary_hit_column,
)
from pipeline.transform.talent import (
    billed_as_credits,
    leads_as_credits,
    talent_sensitivity,
    talent_table,
)


# ---------------------------------------------------------------------------
# The stage entry point
# ---------------------------------------------------------------------------

def measure(
    settings: Any,
    cleaned: pd.DataFrame,
    directors: pd.DataFrame,
    cast: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Compute every KPI table. Every KPI table, both windows, plus the flip check."""
    strict = by_window(cleaned, settings, GROUP_STRICT)
    loose = by_window(cleaned, settings, GROUP_LOOSE)
    flips = flip_check(strict, GROUP_STRICT)

    for note in assert_kpis(strict, cleaned, GROUP_STRICT):
        print(f"[transform] {note}")
    for line in announce_flip(flips):
        print(f"[transform] {line}")

    bundles = bundle_table(cleaned, settings)
    positions = position_within_franchise(cleaned)
    gaps = gap_to_best_entry(cleaned)
    director_talent = talent_table(directors, cleaned, settings, "director")
    lead_talent = talent_table(leads_as_credits(cleaned), cleaned, settings, "lead_actor")
    picks = shortlist(cleaned, bundles, settings)
    widened = (
        talent_sensitivity(cast, cleaned, settings)
        if cast is not None else pd.DataFrame()
    )

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
    if not widened.empty:
        widened.to_csv(processed / "kpi_talent_sensitivity.csv", index=False)
        added = int(widened["appears_only_when_widened"].sum())
        print(
            f"[transform] talent sensitivity (top-"
            f"{settings['talent']['sensitivity_top_n_billed']} billed vs leads only): "
            f"{len(widened)} reliable name(s), {added} of them visible only when "
            "the net is widened"
        )

    print(f"[transform] {len(bundles)} collections, "
          f"{int(bundles['is_buyable_bundle'].sum())} of them buyable bundles")
    print(f"[transform] {int(director_talent['meets_min_films'].sum())} directors and "
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
        "talent_sensitivity": widened,
        "shortlist": picks,
    }


def transform(
    settings: Any,
    ledger: pd.DataFrame,
    cleaned: pd.DataFrame,
    cast: pd.DataFrame,
    crew: pd.DataFrame,
    genres: pd.DataFrame,
) -> dict[str, Any]:
    """Join the cleaned films to their credits, then compute every KPI table.

    The films arriving here already carry their cleaning flags, so the join is
    the last thing that changes the table's shape and the KPIs are computed on
    a table whose eligibility columns are already decided.
    """
    joined = join_tables(
        settings, ledger,
        {"films": cleaned, "cast": cast, "crew": crew, "genres": genres},
    )
    measured = measure(settings, joined["analysis"], joined["directors"], cast)
    return {**joined, **measured}
