"""Stage 9 — re-fetch a sample live and classify every difference.

The question this stage answers is not "is TMDb right?". It is **"did we read
TMDb correctly, and would the recommendation survive if we had read it
differently?"** Those are answerable; the first is not, from here.

**The four slices** (settling open question Q14). A random sample would spend
most of its budget on films that do not matter and would avoid the ones that
do, so the sample is stratified to put the check where an error would hurt:

1. **shortlisted** — the films and bundles the memo actually names. If these
   are wrong, the recommendation is wrong, and nothing else in the check
   matters as much.
2. **flagged_extreme** — the eight films whose ROI exceeds 20x (F11). They are
   the most influential rows in the analysis and the ones a sceptical reader
   will question first. `spotcheck.always_include_flagged` takes **all** of
   them rather than sampling, because a check that samples the risky rows is
   not a check.
3. **pre_2000** — Yaw's distrusted window, where the money figures are least
   comparable (F10) and the data is oldest.
4. **random_control** — a seeded random draw from everything not already
   picked. Without it, the check only looks where problems are expected, and
   could not detect a fault that is uniform across the list.

**The re-fetch writes to a separate cache.** `data/raw_spotcheck/`, not
`data/raw/`. Forcing a refetch into the analysis cache would overwrite the
`fetched_at` stamps the memo's as-of date rests on, and would make the
discrepancy disappear the moment it was found — the next run would read the new
values and agree with itself.

**What a difference means.** Some fields are expected to move: `popularity` is
recomputed daily and `vote_count` rises continuously, so a change in them is
not a discrepancy. Others cannot move without changing an answer: budget,
revenue, runtime, release date and collection membership feed ROI, the window
split and the franchise split. The classification is by field, decided in
advance, so a material difference cannot be waved through as drift.
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from .clean import clean as clean_frame
from .config import load_token
from .fetch import (
    ENDPOINT_DETAILS_CREDITS,
    RateLimiter,
    build_session,
    fetch_one,
)
from .kpis import GROUP_STRICT, compare_groups

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
                "none of them enters a performance metric (DR-13)."
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
            "discrepancy. None of them enters a performance metric (DR-13).",
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

def run(
    settings: Any,
    cleaned: pd.DataFrame,
    flags: pd.DataFrame,
    shortlist: dict[str, pd.DataFrame],
    session_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Stage 9 entry point. Re-fetches live; writes to a separate cache."""
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
        print(f"[stage 9] {note}")
    print(
        f"[stage 9] {len(sample)} films re-fetched live across "
        f"{sample['slice'].nunique()} slices, seed {sample.attrs['seed']}"
    )
    if movement["moved"]:
        print("[stage 9] " + "=" * 60)
        print("[stage 9] A SPOT-CHECK DIFFERENCE MOVES THE RECOMMENDATION")
        print(f"[stage 9] {movement['winner_before']} -> {movement['winner_after']}")
        print("[stage 9] " + "=" * 60)
    else:
        print(f"[stage 9] Recommendation unchanged: {movement['note']}")

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
