"""Run the StreamVault back-catalog analysis, end to end, from a clean clone.

Examples:
    python run_pipeline.py                  # read the cache where it exists
    python run_pipeline.py --force          # re-fetch everything from TMDb
    python run_pipeline.py --no-spotcheck   # skip the one stage that needs the network

The runner executes extract -> validate -> transform -> checks -> load, in that
order, once. It holds no analysis: it calls the stage modules, times each one,
and writes a structured record of the run. A missing token is reported as an
instruction rather than a traceback, because it is the one failure a first-time
reader is most likely to hit.

Two things this file owns that the stages do not:

* **The run log.** One JSON object per run appended to
  `data/processed/run_log.jsonl`, plus one row per stage in
  `run_timings.csv`, which is what the checks stage computes the time budget
  and the 500-title projection from. Appended to, never overwritten: a figure
  quoted in a report and held nowhere else is a memory, not a measurement.
* **The failure contract.** A blocked gate exits 2, not 1, and says so. The
  analysis ran; its output should not be published. See ADR-029.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline import checks, extract, load, transform, validate
from pipeline.config import TIMING_COLUMNS, MissingTokenError, load_settings

log = logging.getLogger("pipeline")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_timing(
    path: Path,
    stage: str,
    seconds: float,
    run_at: str | None = None,
    api_calls: int = 0,
    cache_hits: int = 0,
    rows: int = 0,
    note: str = "",
) -> None:
    """Append one stage's timing. Creates the file and header if absent.

    Appended with the csv module rather than a DataFrame write, because a
    read-modify-write of the whole file would lose every earlier run if the
    process died halfway, and the history is the only reason this file exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIMING_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow({
            "run_at": run_at or _utc_now(),
            "stage": stage,
            "seconds": round(float(seconds), 3),
            "api_calls": int(api_calls),
            "cache_hits": int(cache_hits),
            "rows": int(rows),
            "note": note,
        })


def record_run(path: Path, entry: dict[str, Any]) -> None:
    """Append one structured JSON record of the whole run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def run_once(settings: Any, run_at: str, force: bool, spotcheck: bool) -> dict[str, Any]:
    """Run all five stages and return the run's metadata."""
    processed = settings.path(settings["paths"]["processed_dir"])
    timings_path = processed / "run_timings.csv"
    seconds: dict[str, float] = {}

    def step(name: str, function, *args, **kwargs):
        started = time.monotonic()
        result = function(*args, **kwargs)
        seconds[name] = round(time.monotonic() - started, 3)
        return result

    # --- extract ----------------------------------------------------------
    log.info("extract: the candidate list, the fetch, and the four tables")
    extracted = extract.extract(settings, force=force)
    ledger, fetch_log = extracted["ledger"], extracted["log"]
    for stage, elapsed in extracted["timings"].items():
        seconds[stage] = round(elapsed, 3)
        record_timing(
            timings_path, stage, elapsed, run_at,
            api_calls=fetch_log.attrs["calls_made"] if stage == "extract.acquire" else 0,
            cache_hits=int(fetch_log["from_cache"].sum()) if stage == "extract.acquire" else 0,
            rows=len(extracted["films"]) if stage == "extract.shape" else len(ledger),
            note=(f"append_credits={fetch_log.attrs['append_credits']}"
                  + (", forced refetch" if force else ""))
            if stage == "extract.acquire" else "",
        )
    log.info(
        "extracted %d films, %d cast rows, %d crew rows",
        len(extracted["films"]), len(extracted["cast"]), len(extracted["crew"]),
    )

    # --- validate ---------------------------------------------------------
    log.info("validate: profile, classify every fault, apply the cleaning flags")
    validated = step("validate", validate.validate, settings, extracted["films"], ledger)
    ledger = validated["ledger"]
    record_timing(
        timings_path, "validate", seconds["validate"], run_at,
        rows=len(validated["cleaned"]),
        note=f"{len(validated['flags'])} flags, {len(validated['exclusions'])} exclusions, "
             f"{len(validated['sensitivity'])} sensitivity runs",
    )
    print()
    print("Money either side of the window boundary — nominal, so not one unit:")
    print(validated["era_comparability"].to_string(index=False))
    print()
    print("Sensitivity — the same comparison under each cleaning choice:")
    print(validated["sensitivity"].to_string(index=False))

    # --- transform --------------------------------------------------------
    log.info("transform: the proven join, then every KPI table, both windows")
    transformed = step(
        "transform", transform.transform, settings, ledger, validated["cleaned"],
        extracted["cast"], extracted["crew"], extracted["genres"],
    )
    record_timing(
        timings_path, "transform", seconds["transform"], run_at,
        rows=len(transformed["analysis"]),
        note=f"{len(transformed['join_report'])} validated merges, "
             f"{len(transformed['bundles'])} bundles",
    )
    print()
    print("Join report — every merge, counted:")
    print(transformed["join_report"].to_string(index=False))
    for window, table in transformed["windows_strict"].items():
        print()
        print(f"Franchise vs standalone — {window}:")
        print(table[[
            transform.GROUP_STRICT, "films", "median_roi", "floor_roi", "iqr_roi",
            "hit_rate_roi", "median_revenue",
        ]].to_string(index=False))
    print()
    print("Does the answer change between windows?")
    print(transformed["flips"].to_string(index=False))
    print()
    print("Inside a franchise, by position:")
    print(transformed["positions"].to_string(index=False))

    # --- checks -----------------------------------------------------------
    checked = None
    if spotcheck:
        log.info("checks: re-fetch a stratified sample live and classify every difference")
        try:
            checked = step(
                "checks.spotcheck", checks.spot_check, settings, transformed["analysis"],
                validated["flags"], transformed["shortlist"],
            )
            record_timing(
                timings_path, "checks.spotcheck", seconds["checks.spotcheck"], run_at,
                rows=len(checked["sample"]), api_calls=len(checked["sample"]),
                note=f"{checked['sample']['slice'].nunique()} slices, "
                     f"moved={checked['movement']['moved']}",
            )
            print()
            print("Differences by slice:")
            print(checked["summary"].to_string(index=False))
        except MissingTokenError as error:
            # The only stage that always needs the network: it exists to compare
            # against the live source, so there is no cached answer to fall back on.
            log.warning("spot-check skipped, it must reach TMDb:\n%s", error)
    else:
        log.info("checks: spot-check skipped by --no-spotcheck")

    log.info("checks: the release gate, then the time budget")
    payloads, _ = extract.load_payloads(settings.path(settings["paths"]["raw_dir"]))
    gated = step(
        "checks", checks.check_before_load,
        settings,
        timings_path,
        payloads,
        checked["movement"] if checked else None,
        len(checked["sample"]) if checked else 0,
        accounting=transformed["accounting"],
        ledger=ledger,
        cleaned=transformed["analysis"],
        windows=transformed["windows_strict"],
        flips=transformed["flips"],
        bundles=transformed["bundles"],
        gaps=transformed["bundle_gaps"],
        positions=transformed["positions"],
        talent=transformed["talent_directors"],
        shortlist=transformed["shortlist"],
        fetch_log=fetch_log,
        eras=validated["era_comparability"],
    )
    record_timing(
        timings_path, "checks", seconds["checks"], run_at,
        rows=len(gated["gate"]),
        note="gate passed; measures the analysis stages by re-running them",
    )
    print()
    print("Where the time goes (shaping, validate, transform; acquisition excluded):")
    print(gated["budget"]["budget"].to_string(index=False))
    print()
    print("Projected to 500 titles, from measured per-stage scaling:")
    print(gated["budget"]["projection"][[
        "stage", "measured_seconds", "exponent_k", "scaling", "fit_quality",
        "projected_seconds",
    ]].to_string(index=False))

    # --- load -------------------------------------------------------------
    log.info("load: the memo and the improvement note")
    written = step("load", load.load, settings, gated["facts"], gated["gate"], ledger)
    record_timing(
        timings_path, "load", seconds["load"], run_at,
        rows=len(written["memo"].splitlines()), note="memo and improvement written",
    )

    print()
    print("-" * 72)
    print("Every source row, accounted for:")
    print(extract.reconciliation_summary(ledger).to_string(index=False))
    print()
    print("...and how many of each reached the analysis table:")
    print(transformed["accounting"].to_string(index=False))
    print("-" * 72)

    return {
        "ids_in_file": int(ledger.attrs["data_rows"]),
        "films_analysed": int(gated["facts"]["films_analysed"]),
        "unaccounted_rows": int(gated["facts"]["unaccounted_rows"]),
        "api_calls": int(fetch_log.attrs["calls_made"]),
        "cache_hits": int(fetch_log["from_cache"].sum()),
        "spotcheck_films": int(len(checked["sample"])) if checked else 0,
        "spotcheck_moved": bool(checked["movement"]["moved"]) if checked else None,
        "gate_passed": bool(gated["gate"]["passed"].all()),
        "analysis_seconds": gated["budget"]["budget"].attrs["analysis_seconds"],
        "projected_seconds_at_500": gated["budget"]["projection"].attrs["projected_total"],
        "as_of": gated["facts"]["as_of_last"],
        "seconds": seconds,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="ignore the cache and re-fetch every film from TMDb",
    )
    parser.add_argument(
        "--no-spotcheck", action="store_true",
        help="skip the live re-check, the one stage that needs the network",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    settings = load_settings()
    processed = settings.path(settings["paths"]["processed_dir"])
    run_id = uuid.uuid4().hex[:8]
    # One run_at for every stage of this run, so the timing rows group cleanly.
    run_at = _utc_now()
    started = run_at

    try:
        result = run_once(settings, run_at, force=args.force, spotcheck=not args.no_spotcheck)
    except MissingTokenError as error:
        # An instruction, not a traceback. The fix is four lines long.
        print(f"\n{error}", file=sys.stderr)
        return 1
    except checks.GateFailed as error:
        # Not a crash. The analysis ran; its output should not be published.
        print(f"\n{error}\n", file=sys.stderr)
        record_run(processed / "run_log.jsonl", {
            "run_id": run_id, "run_at": run_at, "started": started,
            "finished": _utc_now(), "status": "blocked_by_gate",
            "error": str(error).splitlines()[0],
        })
        return 2

    record_run(processed / "run_log.jsonl", {
        "run_id": run_id, "run_at": run_at, "started": started,
        "finished": _utc_now(), "status": "success", **result,
    })

    reports = settings.path(settings["paths"]["reports_dir"])
    print(f"Artefacts written to {processed}/ — ledger, fetch log, timings, join report,")
    print("  accounting, profile, flags, exclusions, sensitivity, KPI tables, shortlists,")
    print("  gate, time budget, projection, spot-check, and run_log.jsonl")
    print(f"Reports written to {reports}/")
    print("  memo.md          — START HERE: one page, for the room")
    print("  improvement.md   — the one addition beyond the brief, and why this one")
    print("  spotcheck.md     — the live re-check, generated so it cannot drift")
    print()
    print("The reasoning behind every decision is in docs/adr/, one file per decision.")
    print("What was found in the data, and where each finding is handled: docs/findings.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
