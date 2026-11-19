"""Stage 8 — the time budget, and a projection to 500 titles that is measured.

The brief asks for a time budget with the boundary stated, and a projection to
next year's roughly 500 titles. The easy version of the projection is to
multiply by 500/112 and move on. That assumes every stage scales linearly in
films, and at least one does not: stage 3 flattens **credit rows**, of which
there are 223 per film on this list, and stage 7 aggregates groups whose number
grows with the catalog rather than with its size.

So the projection here is **measured**. The analysis stages are re-run over
subsets of the real data at several sizes, and a scaling exponent is fitted per
stage from the observed times:

    seconds ~= a * films ** k

`k` near 1 means linear, below 1 means fixed costs dominate at this size, above
1 means it degrades as the list grows — and only the third kind threatens the
budget. The exponents are reported beside the projection, because a projected
number with no indication of how it was obtained is a guess with a decimal
point.

**The boundary**, stated once and carried into the memo: the budget covers
**stages 3 to 7** — flatten, join, profile, clean, KPIs — with a **warm cache**,
on **one machine, single-threaded**. It **excludes acquisition** (stage 2),
which is network-bound and cached, so including it would measure TMDb's latency
and Adjoa's wifi rather than this code. Stage 1 is included for completeness
and costs 0.02s. Acquisition is projected separately and reported beside the
budget, never inside it.
"""
from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np
import pandas as pd

# Stages inside the budget. Acquisition is deliberately not here; see DR-22.
ANALYSIS_STAGES = ("3_flatten", "4_join", "5_profile", "6_clean", "7_kpis")
ACQUISITION_STAGE = "2_acquire"
INGEST_STAGE = "1_ingest"

BUDGET_COLUMNS = ["stage", "seconds", "share_of_analysis", "in_budget", "note"]
SCALING_COLUMNS = ["films", "stage", "seconds"]
PROJECTION_COLUMNS = [
    "stage", "measured_films", "measured_seconds", "exponent_k", "scaling",
    "fit_quality", "projected_films", "projected_seconds",
]


# ---------------------------------------------------------------------------
# The budget for the run we just did
# ---------------------------------------------------------------------------

def time_budget(timings: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """Per-stage seconds for the most recent run, with the boundary applied.

    Reads the durable timings artefact rather than re-timing anything, so the
    budget describes the run that produced the numbers in the memo.
    """
    if timings.empty:
        return pd.DataFrame(columns=BUDGET_COLUMNS)

    latest = timings.loc[timings["run_at"] == timings["run_at"].max()].copy()
    analysis_total = float(
        latest.loc[latest["stage"].isin(ANALYSIS_STAGES), "seconds"].sum()
    )

    rows: list[dict[str, Any]] = []
    for row in latest.itertuples(index=False):
        in_budget = row.stage in ANALYSIS_STAGES
        if row.stage == ACQUISITION_STAGE:
            note = ("excluded: network-bound and cached, so timing it measures "
                    "TMDb and the connection, not this code")
        elif row.stage == INGEST_STAGE:
            note = "outside the stated boundary, reported for completeness"
        else:
            note = ""
        rows.append({
            "stage": row.stage,
            "seconds": round(float(row.seconds), 3),
            "share_of_analysis": round(float(row.seconds) / analysis_total, 3)
            if in_budget and analysis_total else pd.NA,
            "in_budget": in_budget,
            "note": note,
        })

    budget = pd.DataFrame(rows, columns=BUDGET_COLUMNS)
    budget.attrs["analysis_seconds"] = round(analysis_total, 3)
    budget.attrs["limit_seconds"] = float(settings["budget"]["analysis_seconds_limit"])
    budget.attrs["within_limit"] = analysis_total <= budget.attrs["limit_seconds"]
    acquisition = latest.loc[latest["stage"] == ACQUISITION_STAGE, "seconds"]
    budget.attrs["acquisition_seconds"] = round(float(acquisition.iloc[0]), 3) \
        if len(acquisition) else pd.NA
    return budget


# ---------------------------------------------------------------------------
# Measured scaling
# ---------------------------------------------------------------------------

def measure_scaling(
    settings: Any,
    payloads: list[dict[str, Any]],
    ledger: pd.DataFrame,
    fractions: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0),
    repeats: int = 3,
    warmup: bool = True,
) -> pd.DataFrame:
    """Re-run stages 3-7 over subsets of the real data and time each one.

    Subsets of the *actual* payloads, not synthetic rows: a generated film with
    three cast members would make stage 3 look linear in films when it is
    really linear in credit rows, and that is the distinction the projection
    turns on.

    Two details that the first version of this got wrong, with a measurable
    consequence:

    * **A discarded warm-up pass runs first.** Without it, the smallest sample
      pays pandas' one-off costs — first-call import and allocator warm-up —
      and comes out *slower* than the largest. The fitted exponents were
      negative, which would have projected these stages getting faster as the
      catalog grows.
    * **Each size is timed `repeats` times and the minimum is kept.** Noise on
      a 0.1s measurement only ever adds time, never removes it, so the minimum
      is the least contaminated estimate of the real cost. A mean would carry
      every scheduling hiccup into the projection.
    """
    from . import clean as clean_module
    from . import flatten as flatten_module
    from . import join as join_module
    from . import kpis as kpis_module
    from . import profile as profile_module

    def one_pass(sample: list[dict[str, Any]]) -> dict[str, float]:
        timed: dict[str, float] = {}
        started = time.perf_counter()
        films = flatten_module.build_films(sample)
        cast = flatten_module.build_cast(sample)
        crew = flatten_module.build_crew(sample)
        genres = flatten_module.build_genres(sample)
        films = flatten_module.add_franchise_flags(
            films, int(settings["franchise"]["min_members_on_list"])
        )
        timed["3_flatten"] = time.perf_counter() - started

        started = time.perf_counter()
        analysis, _ = join_module.build_analysis_table(films, cast, crew, genres)
        directors = join_module.directors_long(crew)
        timed["4_join"] = time.perf_counter() - started

        started = time.perf_counter()
        profile_module.profile_table(analysis)
        profile_module.find_flags(analysis, settings)
        profile_module.era_comparability(analysis)
        timed["5_profile"] = time.perf_counter() - started

        started = time.perf_counter()
        cleaned = clean_module.clean(analysis, settings)
        clean_module.build_exclusions(cleaned, settings)
        clean_module.sensitivity_table(analysis, settings)
        timed["6_clean"] = time.perf_counter() - started

        started = time.perf_counter()
        strict = kpis_module.by_window(cleaned, settings, kpis_module.GROUP_STRICT)
        kpis_module.flip_check(strict, kpis_module.GROUP_STRICT)
        bundles = kpis_module.bundle_table(cleaned, settings)
        kpis_module.position_within_franchise(cleaned)
        kpis_module.talent_table(directors, cleaned, settings, "director")
        kpis_module.shortlist(cleaned, bundles, settings)
        timed["7_kpis"] = time.perf_counter() - started
        return timed

    rows: list[dict[str, Any]] = []
    total = len(payloads)

    if warmup and payloads:
        one_pass(payloads)          # discarded: pays the one-off costs

    for fraction in fractions:
        count = max(4, int(round(total * fraction)))
        if count > total:
            continue
        sample = payloads[:count]

        best: dict[str, float] = {}
        for _ in range(max(1, repeats)):
            for stage, seconds in one_pass(sample).items():
                best[stage] = min(best.get(stage, float("inf")), seconds)

        for stage, seconds in best.items():
            rows.append({"films": count, "stage": stage, "seconds": round(seconds, 4)})

    return pd.DataFrame(rows, columns=SCALING_COLUMNS)


def fit_exponent(films: pd.Series, seconds: pd.Series) -> float:
    """Fit k in seconds = a * films ** k, by least squares on the logs.

    Returns 1.0 when there is too little signal to fit — two points, or times
    at the clock's resolution. Defaulting to linear is the honest fallback: it
    is the assumption a reader would make anyway, and pretending to have
    measured an exponent from noise would be worse than admitting the default.
    """
    films = pd.to_numeric(films, errors="coerce")
    seconds = pd.to_numeric(seconds, errors="coerce")
    usable = films.notna() & seconds.notna() & (films > 0) & (seconds > 1e-4)
    if int(usable.sum()) < 3:
        return 1.0
    slope, _ = np.polyfit(
        np.log(films[usable].to_numpy(dtype=float)),
        np.log(seconds[usable].to_numpy(dtype=float)),
        1,
    )
    return float(slope)


def describe_scaling(k: float) -> str:
    """Plain words for an exponent, because `k=0.87` tells Adjoa nothing."""
    if k < 0.8:
        return "sub-linear (fixed costs dominate at this size)"
    if k <= 1.2:
        return "roughly linear"
    if k <= 1.6:
        return "worse than linear"
    return "degrades sharply as the list grows"


def project(
    scaling: pd.DataFrame, settings: Any, measured_total: int
) -> pd.DataFrame:
    """Project each analysis stage to the target catalog size, per measured k."""
    target = int(settings["budget"]["projection_target_titles"])
    rows: list[dict[str, Any]] = []

    for stage in ANALYSIS_STAGES:
        points = scaling.loc[scaling["stage"] == stage]
        if points.empty:
            continue
        fitted = fit_exponent(points["films"], points["seconds"])

        # A negative exponent says the stage gets faster as the data grows,
        # which is not a thing. It means the measurement was contaminated
        # despite the warm-up, so fall back to linear and label it: assuming
        # linear over-estimates the time, which is the safe direction for a
        # budget, and a projection built on an impossible exponent is worse
        # than one built on a stated assumption.
        if fitted < 0:
            k, quality = 1.0, "assumed linear (measured exponent was negative)"
        else:
            k, quality = fitted, "measured"

        largest = points.loc[points["films"].idxmax()]
        base_films = float(largest["films"])
        base_seconds = float(largest["seconds"])
        projected = base_seconds * (target / base_films) ** k

        rows.append({
            "stage": stage,
            "measured_films": int(base_films),
            "measured_seconds": round(base_seconds, 3),
            "exponent_k": round(k, 2),
            "scaling": describe_scaling(k),
            "fit_quality": quality,
            "projected_films": target,
            "projected_seconds": round(projected, 2),
        })

    projection = pd.DataFrame(rows, columns=PROJECTION_COLUMNS)
    projection.attrs["projected_total"] = round(
        float(projection["projected_seconds"].sum()), 2
    ) if not projection.empty else 0.0

    # A second total, assuming every stage is linear. The fitted exponents for
    # the small stages are sub-linear because fixed costs dominate at 112
    # films — and that will stop being true somewhere between here and 500, so
    # extrapolating a k of 0.15 five-fold is optimistic. Reporting the
    # all-linear figure beside the fitted one means the conclusion can be shown
    # to hold under either, rather than resting on the fit being right.
    if not projection.empty:
        ratio = target / float(projection["measured_films"].max())
        projection.attrs["conservative_linear_total"] = round(
            float(projection["measured_seconds"].sum()) * ratio, 2
        )
    else:
        projection.attrs["conservative_linear_total"] = 0.0
    projection.attrs["limit_seconds"] = float(
        settings["budget"]["analysis_seconds_limit"]
    )
    projection.attrs["measured_total_films"] = measured_total
    projection.attrs["target_films"] = target
    return projection


def project_acquisition(timings: pd.DataFrame, settings: Any) -> dict[str, Any]:
    """Acquisition, projected separately and never folded into the budget.

    Uses the slowest recorded acquisition — the cold-cache run — because that
    is the one a new machine or a new quarter will experience. Projecting from
    a cached run would promise 2 seconds and deliver 90.
    """
    target = int(settings["budget"]["projection_target_titles"])
    cold = timings.loc[
        (timings["stage"] == ACQUISITION_STAGE) & (timings["api_calls"] > 0)
    ]
    if cold.empty:
        return {"measured": pd.NA, "calls": pd.NA, "projected_seconds": pd.NA,
                "basis": "no cold-cache run recorded yet"}

    slowest = cold.loc[cold["seconds"].idxmax()]
    per_call = float(slowest["seconds"]) / max(1, int(slowest["api_calls"]))
    return {
        "measured": round(float(slowest["seconds"]), 2),
        "calls": int(slowest["api_calls"]),
        "projected_seconds": round(per_call * target, 1),
        "basis": (
            f"{per_call:.3f}s per call on the cold-cache run, times {target} films; "
            "one call per film because api.append_credits is true"
        ),
    }


# ---------------------------------------------------------------------------
# Assertions and reporting
# ---------------------------------------------------------------------------

def assert_budget(budget: pd.DataFrame, projection: pd.DataFrame) -> list[str]:
    """Hard-assert the boundary is coherent; report whether the limits hold."""
    notes: list[str] = []
    if budget.empty:
        return ["NOTE: no timings recorded yet, so there is no budget to report."]

    assert budget["stage"].is_unique, "a stage appears twice in the budget"
    in_budget = budget.loc[budget["in_budget"]]
    assert not in_budget.empty, "the budget covers no stages"
    assert ACQUISITION_STAGE not in set(in_budget["stage"]), (
        "acquisition is inside the budget, which the stated boundary excludes"
    )
    shares = in_budget["share_of_analysis"].dropna().astype(float).sum()
    assert abs(shares - 1.0) < 0.01, (
        f"stage shares sum to {shares:.3f}, not 1.0 — the boundary is inconsistent"
    )

    measured = budget.attrs["analysis_seconds"]
    limit = budget.attrs["limit_seconds"]
    if budget.attrs["within_limit"]:
        notes.append(
            f"Analysis (stages 3-7, warm cache, acquisition excluded): "
            f"{measured}s against a {limit}s limit."
        )
    else:
        notes.append(
            f"OVER BUDGET: analysis took {measured}s against a {limit}s limit. "
            "The limit is a target in settings, not a law — but the memo should "
            "say so rather than leave a reader to notice."
        )

    if not projection.empty:
        projected = projection.attrs["projected_total"]
        target = projection.attrs["target_films"]
        conservative = projection.attrs.get("conservative_linear_total")
        if projected <= limit:
            notes.append(
                f"Projected to {target} titles: {projected}s, still inside the "
                f"{limit}s limit. Projection is from measured per-stage exponents, "
                "not from multiplying by the ratio of film counts."
            )
            if conservative is not None:
                verdict = "also inside" if conservative <= limit else "OVER"
                notes.append(
                    f"Assuming instead that every stage is linear — which is "
                    f"pessimistic for the stages whose fixed costs dominate today — "
                    f"gives {conservative}s, {verdict} the limit. The conclusion "
                    "does not depend on the fit being right."
                )
        else:
            notes.append(
                f"PROJECTION OVER BUDGET: {target} titles projects to {projected}s "
                f"against a {limit}s limit. The stages to look at first are the "
                "ones below with an exponent above 1."
            )
        worst = projection.loc[projection["exponent_k"].idxmax()]
        if float(worst["exponent_k"]) > 1.2:
            notes.append(
                f"NOTE: {worst['stage']} scales {worst['scaling']} (k="
                f"{worst['exponent_k']}). It is the stage that will hurt first as "
                "the catalog grows, whatever the totals say today."
            )
    return notes


def run(
    settings: Any,
    timings_frame: pd.DataFrame,
    payloads: list[dict[str, Any]],
    ledger: pd.DataFrame,
) -> dict[str, Any]:
    """Stage 8 entry point."""
    budget = time_budget(timings_frame, settings)
    scaling = measure_scaling(settings, payloads, ledger)
    projection = project(scaling, settings, measured_total=len(payloads))
    acquisition = project_acquisition(timings_frame, settings)

    for note in assert_budget(budget, projection):
        print(f"[stage 8] {note}")

    if not pd.isna(acquisition["projected_seconds"]):
        print(
            f"[stage 8] Acquisition, reported beside the budget and not inside it: "
            f"{acquisition['measured']}s for {acquisition['calls']} calls, "
            f"projecting to {acquisition['projected_seconds']}s at "
            f"{settings['budget']['projection_target_titles']} titles."
        )

    processed = settings.path(settings["paths"]["processed_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    budget.to_csv(processed / "time_budget.csv", index=False)
    scaling.to_csv(processed / "scaling_measurements.csv", index=False)
    projection.to_csv(processed / "projection.csv", index=False)
    pd.DataFrame([acquisition]).to_csv(
        processed / "projection_acquisition.csv", index=False
    )

    return {
        "budget": budget,
        "scaling": scaling,
        "projection": projection,
        "acquisition": acquisition,
    }
