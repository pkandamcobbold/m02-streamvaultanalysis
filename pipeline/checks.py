"""Stage 4 — checks: the gates that must pass before anything is published.

Three gates, and only the first can stop the run.

**The release gate** (ADR-029, the one improvement beyond the brief). Four blunt
checks run before the memo is written: every source row accounted for, enough
films to compare groups, money data complete enough to decide on, and a live
re-check that does not change the answer. If any fails, no memo and no shortlist
are produced — the run stops and prints what failed, naming the setting that
overrides it. Adjoa reruns this quarterly and sometimes live; the failure it
protects against is a confident number from a broken run with no way to know.

**The live spot-check** (ADR-025, ADR-026). Re-fetch a stratified sample into a
separate cache and classify every difference by field, decided in advance, so a
material difference cannot be waved through as drift. Then substitute every live
money value found and recompute the comparison, because the only honest way to
answer "does it move the recommendation?" is to move it and look.

**The time budget** (ADR-023, ADR-024). Per-stage seconds for this run against
the stated boundary — the shaping, validate and transform stages, warm cache,
one machine, single-threaded, acquisition excluded and reported beside it — plus
a projection to 500 titles fitted from measured per-stage exponents rather than
from multiplying by the ratio of film counts.
"""
from __future__ import annotations

import textwrap
import time
from typing import Any, Callable

import numpy as np
import pandas as pd

from pipeline import extract, transform, validate
from pipeline.config import Settings, TIMING_DTYPES, load_token, share
from pipeline.extract import (
    ENDPOINT_DETAILS_CREDITS,
    RateLimiter,
    build_session,
    fetch_one,
)
from pipeline.transform import GROUP_STRICT, compare_groups
from pipeline.validate import clean as clean_frame

GATE_COLUMNS = ["check", "passed", "detail"]


class GateFailed(RuntimeError):
    """Raised instead of publishing a memo nobody should act on."""


def load_timings(path) -> pd.DataFrame:
    """Read the per-stage timings back with explicit dtypes, never by inference."""
    frame = pd.read_csv(path, dtype=TIMING_DTYPES)
    frame["note"] = frame["note"].fillna("")
    return frame


def latest_timing_run(path) -> pd.DataFrame:
    """Just the most recent run's rows — what a report should quote."""
    frame = load_timings(path)
    if frame.empty:
        return frame
    return frame.loc[frame["run_at"] == frame["run_at"].max()]


# ===========================================================================
# The time budget and the 500-title projection
# (was src/streamvault/budget.py)
# ===========================================================================

# Stages inside the budget. Acquisition is deliberately not here; see ADR-023.
ANALYSIS_STAGES = ("extract.shape", "validate", "transform")
ACQUISITION_STAGE = "extract.acquire"
INGEST_STAGE = "extract.read_ids"

# Why each stage outside the boundary is outside it. A stage that is excluded
# from a judgement should say so in the artefact; one that is simply absent
# looks like a stage that never ran.
OUT_OF_BUDGET_NOTES = {
    "checks": "this stage measures the others by re-running them, so timing it "
                "inside the budget would count them twice",
    "__spotcheck": "excluded: network-bound by design — it exists to compare "
                   "against the live source, so it cannot run from cache",
    "load": "excluded: writes the reports rather than computing the analysis",
}

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
        elif in_budget:
            note = ""
        else:
            # Every stage outside the boundary says why, so a reader of this
            # artefact can tell that a stage was excluded from a judgement
            # rather than simply absent. Before an audit, stages 9 and 10 were
            # missing from the table altogether and nothing said so.
            note = OUT_OF_BUDGET_NOTES.get(
                row.stage, "outside the stated boundary, reported for completeness"
            )
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
    """Re-run the shaping, validate and transform stages over subsets of the real data and time each one.

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
    def one_pass(sample: list[dict[str, Any]]) -> dict[str, float]:
        timed: dict[str, float] = {}
        started = time.perf_counter()
        films = extract.build_films(sample)
        cast = extract.build_cast(sample)
        crew = extract.build_crew(sample)
        genres = extract.build_genres(sample)
        films = extract.add_franchise_flags(
            films, int(settings["franchise"]["min_members_on_list"])
        )
        timed["extract.shape"] = time.perf_counter() - started

        started = time.perf_counter()
        analysis, _ = transform.build_analysis_table(films, cast, crew, genres)
        directors = transform.directors_long(crew)
        
        started = time.perf_counter()
        validate.profile_table(analysis)
        validate.find_flags(analysis, settings)
        validate.era_comparability(analysis)
        timed["validate"] = time.perf_counter() - started

        started = time.perf_counter()
        cleaned = validate.clean(analysis, settings)
        validate.build_exclusions(cleaned, settings)
        validate.sensitivity_table(analysis, settings)
        
        started = time.perf_counter()
        strict = transform.by_window(cleaned, settings, transform.GROUP_STRICT)
        transform.flip_check(strict, transform.GROUP_STRICT)
        bundles = transform.bundle_table(cleaned, settings)
        transform.position_within_franchise(cleaned)
        transform.talent_table(directors, cleaned, settings, "director")
        transform.shortlist(cleaned, bundles, settings)
        timed["transform"] = time.perf_counter() - started
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
            f"Analysis (shaping, validate and transform; warm cache; acquisition excluded): "
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


def time_budget_report(
    settings: Any,
    timings_frame: pd.DataFrame,
    payloads: list[dict[str, Any]],
    ledger: pd.DataFrame,
) -> dict[str, Any]:
    """Measure the time budget."""
    budget = time_budget(timings_frame, settings)
    scaling = measure_scaling(settings, payloads, ledger)
    projection = project(scaling, settings, measured_total=len(payloads))
    acquisition = project_acquisition(timings_frame, settings)

    for note in assert_budget(budget, projection):
        print(f"[checks] {note}")

    if not pd.isna(acquisition["projected_seconds"]):
        print(
            f"[checks] Acquisition, reported beside the budget and not inside it: "
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

# ===========================================================================
# Re-fetch a stratified sample live and classify every difference
# (was src/streamvault/spotcheck.py)
# ===========================================================================

# Fields where a change would change an answer, and why it would.
MATERIAL_FIELDS = {
    "budget": "feeds ROI directly",
    "revenue": "feeds ROI directly",
    "runtime": "feeds the non-feature check",
    "release_date": "decides which time window the film is in",
    "collection_id": "decides the franchise / standalone split",
    "title": "identifies the film in the memo and the shortlist",
}

# Fields that move on their own. A change here is drift, not a discrepancy.
VOLATILE_FIELDS = {
    "popularity": "recomputed daily by TMDb from recent activity",
    "vote_count": "rises continuously as people vote",
    "vote_average": "moves slightly as vote_count rises",
}

VERDICT_IDENTICAL = "identical"
VERDICT_DRIFT = "expected_drift"
VERDICT_MATERIAL = "material_difference"
VERDICT_GONE = "no_longer_available"

KNOWN_SLICES = frozenset({
    "shortlisted", "flagged_extreme", "pre_2000", "random_control",
})

SAMPLE_COLUMNS = ["tmdb_id", "title", "slice", "why_this_slice"]
COMPARISON_COLUMNS = [
    "tmdb_id", "title", "slice", "field", "analysed_value", "live_value",
    "verdict", "note",
]


# ---------------------------------------------------------------------------
# Choosing the sample
# ---------------------------------------------------------------------------

def build_sample(
    cleaned: pd.DataFrame,
    flags: pd.DataFrame,
    shortlisted_ids: set[int],
    settings: Any,
) -> pd.DataFrame:
    """The stratified sample, seeded so it is the same every run.

    Seeded because a spot-check that samples differently each run cannot be
    argued about: a reviewer who re-runs it and sees different films cannot
    tell a fixed fault from a new draw. `spotcheck.random_seed` is in settings
    so the sample can be deliberately changed and the change recorded.
    """
    config = settings["spotcheck"]
    per_slice = int(config["films_per_slice"])
    seed = int(config["random_seed"])
    take_all_flagged = bool(config["always_include_flagged"])

    picked: list[dict[str, Any]] = []
    used: set[int] = set()

    def add(frame: pd.DataFrame, slice_name: str, why: str, limit: int | None) -> None:
        available = frame.loc[~frame["tmdb_id"].isin(used)]
        if available.empty:
            return
        if limit is None or len(available) <= limit:
            chosen = available
        else:
            chosen = available.sample(n=limit, random_state=seed)
        for row in chosen.itertuples(index=False):
            picked.append({
                "tmdb_id": int(row.tmdb_id),
                "title": row.title,
                "slice": slice_name,
                "why_this_slice": why,
            })
            used.add(int(row.tmdb_id))

    # 1. The films the memo names.
    add(
        cleaned.loc[cleaned["tmdb_id"].isin(shortlisted_ids)],
        "shortlisted",
        "named in the recommendation; an error here is an error in the answer",
        per_slice,
    )

    # 2. Every flagged extreme, not a sample of them.
    flagged_ids = set()
    if not flags.empty:
        flagged_ids = set(
            flags.loc[flags["verdict"] == "real_extreme", "tmdb_id"].dropna().astype(int)
        )
    add(
        cleaned.loc[cleaned["tmdb_id"].isin(flagged_ids)],
        "flagged_extreme",
        "ROI above 20x: the most influential rows in the analysis",
        None if take_all_flagged else per_slice,
    )

    # 3. Yaw's window.
    add(
        cleaned.loc[cleaned["release_year"].notna() & (cleaned["release_year"] < 2000)],
        "pre_2000",
        "the window Finance distrusts, and where money is least comparable",
        per_slice,
    )

    # 4. An unbiased control.
    add(
        cleaned,
        "random_control",
        "seeded random draw from the rest: without it the check only looks "
        "where problems are expected",
        per_slice,
    )

    sample = pd.DataFrame(picked, columns=SAMPLE_COLUMNS)
    if not sample.empty:
        sample["tmdb_id"] = sample["tmdb_id"].astype("Int64")
    sample.attrs["seed"] = seed
    sample.attrs["pool"] = int(len(cleaned))
    return sample


def shortlisted_film_ids(
    shortlist: dict[str, pd.DataFrame], cleaned: pd.DataFrame
) -> set[int]:
    """Every film named by the shortlist, including each bundle's members."""
    ids: set[int] = set()
    standalones = shortlist.get("standalones")
    if standalones is not None and not standalones.empty:
        selected = standalones.loc[standalones["selected"]]
        ids |= set(selected["tmdb_id"].dropna().astype(int))

    franchises = shortlist.get("franchises")
    if franchises is not None and not franchises.empty:
        names = set(franchises.loc[franchises["selected"], "collection_name"])
        members = cleaned.loc[cleaned["collection_name"].isin(names), "tmdb_id"]
        ids |= set(members.dropna().astype(int))
    return ids


# ---------------------------------------------------------------------------
# Comparing
# ---------------------------------------------------------------------------

def _normalise(value: Any) -> Any:
    """Put both sides on the same footing before comparing them.

    Every flavour of missing becomes None. This matters more than it looks: a
    film with no collection holds `pd.NA` in the analysis and `None` from the
    API, and `pd.NA == None` is False — so without this, **every standalone
    film would be reported as a material difference on `collection_id`**, and
    the spot-check would cry wolf on 25 films while saying nothing useful.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):      # not a scalar pandas understands
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 4)
    return value


def compare_film(
    analysed: pd.Series, payload: dict[str, Any] | None, slice_name: str
) -> list[dict[str, Any]]:
    """Every tracked field for one film, with a verdict on each difference."""
    rows: list[dict[str, Any]] = []
    title = analysed.get("title")

    if payload is None:
        return [{
            "tmdb_id": analysed["tmdb_id"], "title": title, "slice": slice_name,
            "field": "(whole film)", "analysed_value": title, "live_value": None,
            "verdict": VERDICT_GONE,
            "note": "TMDb no longer returns this id. The analysis used a value that "
                    "can no longer be verified at source.",
        }]

    live_collection = (payload.get("belongs_to_collection") or {}).get("id")

    for field, reason in {**MATERIAL_FIELDS, **VOLATILE_FIELDS}.items():
        analysed_value = _normalise(analysed.get(field))
        live_value = _normalise(
            live_collection if field == "collection_id" else payload.get(field)
        )

        if analysed_value == live_value:
            verdict, note = VERDICT_IDENTICAL, ""
        elif field in VOLATILE_FIELDS:
            verdict, note = VERDICT_DRIFT, f"expected: {reason}"
        else:
            verdict, note = VERDICT_MATERIAL, f"material: {reason}"

        rows.append({
            "tmdb_id": analysed["tmdb_id"], "title": title, "slice": slice_name,
            "field": field, "analysed_value": analysed_value,
            "live_value": live_value, "verdict": verdict, "note": note,
        })
    return rows


def run_comparison(
    sample: pd.DataFrame, cleaned: pd.DataFrame, live: dict[int, dict[str, Any] | None]
) -> pd.DataFrame:
    """One row per (film, field) in the sample."""
    # drop=False keeps tmdb_id as a column as well as the index, because
    # compare_film reads it off the row.
    indexed = cleaned.set_index("tmdb_id", drop=False)
    rows: list[dict[str, Any]] = []
    for pick in sample.itertuples(index=False):
        tmdb_id = int(pick.tmdb_id)
        if tmdb_id not in indexed.index:
            continue
        rows.extend(
            compare_film(indexed.loc[tmdb_id], live.get(tmdb_id), pick.slice)
        )
    comparison = pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
    if not comparison.empty:
        comparison["tmdb_id"] = comparison["tmdb_id"].astype("Int64")
    return comparison


# ---------------------------------------------------------------------------
# Does any of it move the recommendation?
# ---------------------------------------------------------------------------

def would_it_move_the_recommendation(
    comparison: pd.DataFrame, cleaned: pd.DataFrame, settings: Any
) -> dict[str, Any]:
    """Substitute every live money value found and recompute the comparison.

    The brief asks whether a discrepancy moves the recommendation. The only
    honest way to answer that is to recompute it with the live figures in place
    and look, rather than reasoning about whether a difference seems large.
    """
    before = compare_groups(cleaned, GROUP_STRICT)
    winner_before = (
        before.loc[before["median_roi"].idxmax(), GROUP_STRICT]
        if not before.empty else None
    )

    money = comparison.loc[
        (comparison["verdict"] == VERDICT_MATERIAL)
        & comparison["field"].isin(["budget", "revenue"])
        & comparison["live_value"].notna()
    ]
    if money.empty:
        return {
            "substitutions": 0,
            "winner_before": winner_before,
            "winner_after": winner_before,
            "moved": False,
            "note": "no material money difference to substitute, so the "
                    "recommendation is unchanged by construction",
        }

    patched = cleaned.copy().set_index("tmdb_id")
    for row in money.itertuples(index=False):
        patched.loc[int(row.tmdb_id), row.field] = row.live_value
    patched = clean_frame(patched.reset_index(), settings)

    after = compare_groups(patched, GROUP_STRICT)
    winner_after = (
        after.loc[after["median_roi"].idxmax(), GROUP_STRICT]
        if not after.empty else None
    )
    return {
        "substitutions": int(len(money)),
        "winner_before": winner_before,
        "winner_after": winner_after,
        "moved": bool(winner_before != winner_after),
        "note": f"{len(money)} live money value(s) substituted and the comparison "
                "recomputed",
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def summarise(comparison: pd.DataFrame) -> pd.DataFrame:
    """Discrepancies by slice and verdict — the table the report leads with."""
    if comparison.empty:
        return pd.DataFrame(columns=["slice", "verdict", "fields", "films"])
    return (
        comparison.groupby(["slice", "verdict"], as_index=False)
        .agg(fields=pd.NamedAgg("field", "size"),
             films=pd.NamedAgg("tmdb_id", "nunique"))
        .sort_values(["slice", "verdict"], ignore_index=True)
    )


def assert_spotcheck(
    sample: pd.DataFrame, comparison: pd.DataFrame, settings: Any
) -> list[str]:
    """Hard-assert the check actually checked what it claims; then report."""
    notes: list[str] = []
    config = settings["spotcheck"]

    assert not sample.empty, "the spot-check sampled no films"
    assert sample["tmdb_id"].is_unique, "a film appears twice in the sample"

    slices = set(sample["slice"])
    # The control slice is what stops the check only looking where problems are
    # expected. The one case where its absence is fine is a pool small enough
    # that the earlier slices already took every film — then coverage is total
    # and there is nothing left to control against.
    pool = sample.attrs.get("pool")
    covers_everything = pool is not None and len(sample) >= pool
    assert "random_control" in slices or covers_everything, (
        "no unbiased control slice: the check only looked where problems were expected"
    )
    assert slices <= KNOWN_SLICES, (
        f"the sample contains an unrecognised slice: {sorted(slices - KNOWN_SLICES)}"
    )
    assert (sample["why_this_slice"].str.len() > 0).all(), (
        "a sampled film does not record why it was chosen"
    )

    if not comparison.empty:
        assert set(comparison["verdict"]) <= {
            VERDICT_IDENTICAL, VERDICT_DRIFT, VERDICT_MATERIAL, VERDICT_GONE,
        }, "an unknown verdict reached the comparison"

        material = comparison.loc[comparison["verdict"] == VERDICT_MATERIAL]
        gone = comparison.loc[comparison["verdict"] == VERDICT_GONE]
        drift = comparison.loc[comparison["verdict"] == VERDICT_DRIFT]

        if len(material):
            notes.append(
                f"{material['tmdb_id'].nunique()} film(s) differ from the live source "
                f"on a field that changes an answer: "
                f"{sorted(set(material['field']))}. Each is listed in "
                "spotcheck.csv with both values."
            )
        else:
            notes.append(
                f"No material difference in {sample['tmdb_id'].nunique()} films across "
                f"{len(slices)} slices: every budget, revenue, runtime, release date, "
                "collection and title matches the live source."
            )
        if len(gone):
            notes.append(
                f"{len(gone)} sampled film(s) are no longer returned by TMDb at all."
            )
        if len(drift):
            notes.append(
                f"{drift['tmdb_id'].nunique()} film(s) show expected drift in "
                f"{sorted(set(drift['field']))} — these fields move on their own and "
                "none of them enters a performance metric (ADR-014)."
            )
    return notes


def write_report(
    path: Any,
    sample: pd.DataFrame,
    comparison: pd.DataFrame,
    summary: pd.DataFrame,
    movement: dict[str, Any],
    settings: Any,
    as_of: str | None = None,
) -> None:
    """Write reports/spotcheck.md. Generated, so it cannot drift from the data.

    A hand-written spot-check report is a claim about a check. A generated one
    is the check's own output, and re-running the pipeline rewrites it.
    """
    material = comparison.loc[comparison["verdict"] == VERDICT_MATERIAL] \
        if not comparison.empty else comparison
    drift = comparison.loc[comparison["verdict"] == VERDICT_DRIFT] \
        if not comparison.empty else comparison
    gone = comparison.loc[comparison["verdict"] == VERDICT_GONE] \
        if not comparison.empty else comparison

    lines: list[str] = [
        "# Spot-check against the live source",
        "",
        "> Generated by stage 9. Re-running the pipeline rewrites this file, so it",
        "> cannot drift from the check it describes.",
        "",
        f"**{sample['tmdb_id'].nunique()} of {sample.attrs.get('pool', '?')} films "
        f"re-fetched live**, stratified across {sample['slice'].nunique()} slices, "
        f"seed `{sample.attrs.get('seed')}`.",
        "",
        "## What this check does and does not establish",
        "",
        "It establishes **fidelity**: that the values the analysis used are the values",
        "the source holds — that nothing was mis-parsed, mis-joined or mis-assigned",
        "on the way in.",
        "",
        "It does **not** establish that TMDb is correct, which is not answerable from",
        "here. And it is a weak test of *drift over time*: the analysis cache was",
        "fetched hours before this check, so only a fast-moving field has had time to",
        "change. A check run a quarter from now against the same cache would be a",
        "real drift test; this one is not, and should not be read as one.",
        "",
        "## Verdict",
        "",
    ]

    if material.empty and gone.empty:
        lines += [
            "**No material difference.** Every budget, revenue, runtime, release date,",
            "collection membership and title in the sample matches the live source.",
            "",
        ]
    else:
        lines += [
            f"**{material['tmdb_id'].nunique()} film(s) differ materially** on "
            f"{sorted(set(material['field']))}, and {len(gone)} are no longer "
            "returned by TMDb at all. Each is listed below with both values.",
            "",
        ]

    lines += [
        f"**Does any difference move the recommendation?** "
        f"{'YES' if movement['moved'] else 'No'}. "
        f"{movement['note'][:1].upper()}{movement['note'][1:]}.",
        "",
        "## The four slices, and why each one",
        "",
        "A random sample would spend its budget on films that do not matter and would",
        "usually miss every film that does. So the sample is stratified:",
        "",
        "| Slice | Films | Why this slice |",
        "|---|---|---|",
    ]
    for slice_name, group in sample.groupby("slice", sort=False):
        lines.append(
            f"| `{slice_name}` | {len(group)} | {group['why_this_slice'].iloc[0]} |"
        )

    lines += [
        "",
        "## Films checked",
        "",
        "| TMDb id | Title | Slice |",
        "|---|---|---|",
    ]
    for row in sample.itertuples(index=False):
        lines.append(f"| {row.tmdb_id} | {row.title} | `{row.slice}` |")

    lines += ["", "## Every difference found, classified", ""]
    if not summary.empty:
        lines += ["| Slice | Verdict | Fields | Films |", "|---|---|---|---|"]
        for row in summary.itertuples(index=False):
            lines.append(
                f"| `{row.slice}` | `{row.verdict}` | {row.fields} | {row.films} |"
            )
        lines.append("")

    if not drift.empty:
        lines += [
            "### Expected drift",
            "",
            "These fields move on their own, so a change in them is not a",
            "discrepancy. None of them enters a performance metric (ADR-014).",
            "",
            "| Film | Field | Analysis | Live |",
            "|---|---|---|---|",
        ]
        for row in drift.itertuples(index=False):
            lines.append(
                f"| {row.title} | `{row.field}` | {row.analysed_value} | "
                f"{row.live_value} |"
            )
        lines.append("")

    if not material.empty:
        lines += [
            "### Material differences",
            "",
            "| Film | Field | Analysis | Live | Why it matters |",
            "|---|---|---|---|---|",
        ]
        for row in material.itertuples(index=False):
            lines.append(
                f"| {row.title} | `{row.field}` | {row.analysed_value} | "
                f"{row.live_value} | {row.note} |"
            )
        lines.append("")

    lines += [
        "## How a difference is classified",
        "",
        "Decided per field in advance, so a material change cannot be waved through",
        "as drift once it is inconvenient.",
        "",
        "| Field | Treated as | Because |",
        "|---|---|---|",
    ]
    for field, reason in MATERIAL_FIELDS.items():
        lines.append(f"| `{field}` | material | {reason} |")
    for field, reason in VOLATILE_FIELDS.items():
        lines.append(f"| `{field}` | expected drift | {reason} |")

    lines += [
        "",
        "The re-fetch writes to `data/raw_spotcheck/`, **not** `data/raw/`. Forcing a",
        "refetch into the analysis cache would overwrite the `fetched_at` stamps the",
        "memo's as-of date rests on, and would make any discrepancy vanish on the next",
        "run — the pipeline would read the new values and agree with itself.",
        "",
    ]

    path = __import__("pathlib").Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def spot_check(
    settings: Any,
    cleaned: pd.DataFrame,
    flags: pd.DataFrame,
    shortlist: dict[str, pd.DataFrame],
    session_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Re-check a sample against the live source. Re-fetches live; writes to a separate cache."""
    api = settings["api"]
    sample = build_sample(
        cleaned, flags, shortlisted_film_ids(shortlist, cleaned), settings
    )

    # A separate cache directory, so the analysis cache and its fetched_at
    # stamps are untouched. Forcing into data/raw/ would make a discrepancy
    # vanish on the next run.
    raw_dir = settings.path(settings["paths"]["raw_dir"]).parent / "raw_spotcheck"
    limiter = RateLimiter(api["min_seconds_between_calls"])
    session = (session_factory or (lambda: build_session(
        load_token(), int(api["max_retries"]), float(api["backoff_factor"])
    )))()

    live: dict[int, dict[str, Any] | None] = {}
    for tmdb_id in sample["tmdb_id"].astype(int):
        envelope, _ = fetch_one(
            session, api["base_url"], raw_dir, limiter, int(tmdb_id),
            ENDPOINT_DETAILS_CREDITS, float(api["timeout_seconds"]),
            params={"append_to_response": "credits"}, force=True,
        )
        live[int(tmdb_id)] = envelope["payload"]

    comparison = run_comparison(sample, cleaned, live)
    summary = summarise(comparison)
    movement = would_it_move_the_recommendation(comparison, cleaned, settings)

    for note in assert_spotcheck(sample, comparison, settings):
        print(f"[checks] {note}")
    print(
        f"[checks] {len(sample)} films re-fetched live across "
        f"{sample['slice'].nunique()} slices, seed {sample.attrs['seed']}"
    )
    if movement["moved"]:
        print("[checks] " + "=" * 60)
        print("[checks] A SPOT-CHECK DIFFERENCE MOVES THE RECOMMENDATION")
        print(f"[checks] {movement['winner_before']} -> {movement['winner_after']}")
        print("[checks] " + "=" * 60)
    else:
        print(f"[checks] Recommendation unchanged: {movement['note']}")

    processed = settings.path(settings["paths"]["processed_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    sample.to_csv(processed / "spotcheck_sample.csv", index=False)
    comparison.to_csv(processed / "spotcheck.csv", index=False)
    summary.to_csv(processed / "spotcheck_summary.csv", index=False)
    write_report(
        settings.path(settings["paths"]["reports_dir"]) / "spotcheck.md",
        sample, comparison, summary, movement, settings,
    )

    return {
        "sample": sample,
        "comparison": comparison,
        "summary": summary,
        "movement": movement,
    }

# ===========================================================================
# The release gate — the one improvement beyond the brief (ADR-029)
# (was src/streamvault/memo.py)
# ===========================================================================

def gate(settings: Any, facts: dict[str, Any]) -> pd.DataFrame:
    """Decide whether these results may be published. Returns one row per check.

    Deliberately a small number of blunt checks. A gate with twenty conditions
    is a gate nobody trusts: the first time it blocks a run for something
    cosmetic, somebody adds a flag to skip it, and then it protects nothing.
    Every check here is one that, if it failed, would make the memo actively
    misleading rather than merely imperfect.
    """
    config = settings["gate"]
    rows: list[dict[str, Any]] = []

    unaccounted = int(facts.get("unaccounted_rows", 0))
    limit = int(config["max_unaccounted_rows"])
    rows.append({
        "check": "every source row accounted for",
        "passed": unaccounted <= limit,
        "detail": f"{unaccounted} row(s) unaccounted for, limit {limit}. The memo "
                  "quotes a count of what was analysed and what was dropped; if "
                  "that does not reconcile, the sentence is false.",
    })

    films = int(facts.get("films_analysed", 0))
    minimum = int(config["min_films_for_a_recommendation"])
    rows.append({
        "check": "enough films to compare groups",
        "passed": films >= minimum,
        "detail": f"{films} films analysed, minimum {minimum}. Below this the two "
                  "groups are too thin to rank; the honest output is a description, "
                  "not a recommendation.",
    })

    missing = float(facts.get("missing_money_share", 0.0))
    max_missing = float(config["max_missing_money_share"])
    rows.append({
        "check": "money data complete enough to decide on",
        "passed": missing <= max_missing,
        "detail": f"{share(missing)} of films have no usable budget or box office, "
                  f"limit {share(max_missing)}. Above that, a ranking by return is "
                  "a ranking of whichever films happened to have figures.",
    })

    if bool(config["block_if_spotcheck_moves"]):
        moved = bool(facts.get("spotcheck_moved", False))
        rows.append({
            "check": "live re-check does not change the answer",
            "passed": not moved,
            "detail": "the live re-check moved the recommendation; a human must look "
                      "before this is published" if moved else
                      "the live re-check leaves the recommendation unchanged",
        })

    return pd.DataFrame(rows, columns=GATE_COLUMNS)


def enforce(gate_results: pd.DataFrame, settings: Any) -> None:
    """Raise if any check failed and the gate is enabled."""
    if not bool(settings["gate"]["enabled"]):
        return
    failed = gate_results.loc[~gate_results["passed"]]
    if failed.empty:
        return
    lines = ["The memo was not written, because these checks failed:", ""]
    for row in failed.itertuples(index=False):
        lines.append(f"  * {row.check}")
        lines.append(f"    {row.detail}")
    lines += [
        "",
        "Nothing is wrong with your computer. The analysis produced results that",
        "should not be put in front of a board without someone looking first.",
        "Read docs/findings.md, then either fix the input or, if you have",
        "decided the run is sound anyway, set gate.enabled = false in",
        "config/settings.toml and run again — and say in the meeting that you did.",
    ]
    raise GateFailed("\n".join(lines))


def gather(
    settings: Any,
    accounting: pd.DataFrame,
    ledger: pd.DataFrame,
    cleaned: pd.DataFrame,
    windows: dict[str, pd.DataFrame],
    flips: pd.DataFrame,
    bundles: pd.DataFrame,
    gaps: pd.DataFrame,
    positions: pd.DataFrame,
    talent: pd.DataFrame,
    shortlist: dict[str, pd.DataFrame],
    fetch_log: pd.DataFrame,
    spotcheck_movement: dict[str, Any] | None,
    spotcheck_films: int,
    eras: pd.DataFrame,
) -> dict[str, Any]:
    """Everything the memo quotes, in one dictionary, computed once."""
    source_rows = int(accounting["source_rows"].sum()) if not accounting.empty else 0
    analysed = int(accounting.loc[accounting["status"] == "fetched",
                                  "reached_analysis"].sum()) \
        if not accounting.empty else 0

    # A genuine cross-check between two tables built independently: the ledger
    # has one row per line of the source file, and the accounting table is
    # grouped from it at stage 4. Comparing the accounting total against its
    # own total would be a tautology and would pass whatever went wrong.
    ledger_data_rows = int(
        (ledger["status"] != "header_row").sum()
    ) if "status" in ledger.columns else source_rows
    unaccounted = abs(ledger_data_rows - source_rows)

    dates = fetch_log["fetched_at"].dropna().astype(str).str.slice(0, 10) \
        if "fetched_at" in fetch_log.columns else pd.Series(dtype=str)

    all_years = windows.get("all_years", pd.DataFrame())
    modern = windows.get("modern", pd.DataFrame())

    def group_row(table: pd.DataFrame, group: str) -> pd.Series | None:
        if table.empty or GROUP_STRICT not in table.columns:
            return None
        rows = table.loc[table[GROUP_STRICT] == group]
        return rows.iloc[0] if len(rows) else None

    in_money = cleaned["in_money_metrics"].fillna(False) \
        if "in_money_metrics" in cleaned.columns else pd.Series(dtype=bool)

    return {
        "source_rows": source_rows,
        "films_analysed": analysed,
        "unaccounted_rows": unaccounted,
        "ledger_data_rows": ledger_data_rows,
        "missing_money_share": float(1 - in_money.mean()) if len(in_money) else 0.0,
        "accounting": accounting,
        "as_of_first": dates.min() if len(dates) else None,
        "as_of_last": dates.max() if len(dates) else None,
        "all_years": all_years,
        "modern": modern,
        "franchise_all": group_row(all_years, "franchise"),
        "standalone_all": group_row(all_years, "standalone"),
        "franchise_modern": group_row(modern, "franchise"),
        "standalone_modern": group_row(modern, "standalone"),
        "flips": flips,
        "bundles": bundles,
        "gaps": gaps,
        "positions": positions,
        "talent": talent,
        "shortlist": shortlist,
        "eras": eras,
        "spotcheck_moved": bool(spotcheck_movement["moved"])
        if spotcheck_movement else False,
        "spotcheck_films": int(spotcheck_films),
    }


# ===========================================================================
# The stage entry point
# ===========================================================================

def check_before_load(
    settings: Any,
    timings_path,
    payloads: list[dict[str, Any]],
    spotcheck_movement: dict[str, Any] | None,
    spotcheck_films: int,
    **facts_inputs: Any,
) -> dict[str, Any]:
    """Run the gate, raise if it blocks, and measure the time budget.

    Raises `GateFailed` instead of returning, if any gate check fails while
    `gate.enabled` is true. Nothing downstream writes a client-facing document
    unless this returns.
    """
    facts = gather(
        settings,
        spotcheck_movement=spotcheck_movement,
        spotcheck_films=spotcheck_films,
        **facts_inputs,
    )
    gate_results = gate(settings, facts)

    for row in gate_results.itertuples(index=False):
        mark = "pass" if row.passed else "FAIL"
        print(f"[checks] gate {mark}: {row.check}")

    processed = settings.path(settings["paths"]["processed_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    gate_results.to_csv(processed / "gate.csv", index=False)

    enforce(gate_results, settings)      # raises GateFailed if anything failed

    measured_budget = time_budget_report(
        settings, load_timings(timings_path), payloads, facts["accounting"]
    )
    return {"facts": facts, "gate": gate_results, "budget": measured_budget}
