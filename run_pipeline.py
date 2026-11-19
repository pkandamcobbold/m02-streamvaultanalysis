"""Run the whole pipeline, in order, from a clean clone.

    python run_pipeline.py            # read the cache where it exists
    python run_pipeline.py --force    # re-fetch everything from TMDb

This file holds no analysis. It calls the stage modules in order and prints
what each one did, so that "which cells did you run?" is never a question
anyone has to ask about a number in the memo.

Stages implemented so far: 1 (id ledger) and 2 (acquisition). Stages 3-10 are
added below as they are built; the runbook in docs/02_build_runbook.md has the
order and what each one must leave behind.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from streamvault import (
    budget, clean, fetch, flatten, join, kpis, memo, profile, spotcheck, timings,
)
from streamvault.config import MissingTokenError, load_settings
from streamvault.ingest import load_id_list, reconciliation_summary, save_ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="ignore the cache and re-fetch every film from TMDb",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    processed = settings.path(settings["paths"]["processed_dir"])
    timings_path = processed / "run_timings.csv"
    # One run_at for every stage of this run, so the rows group cleanly.
    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # --- Stage 1: the id ledger ------------------------------------------
    print("=" * 72)
    print("Stage 1 — the candidate list")
    print("=" * 72)
    started = time.monotonic()
    ledger, ids = load_id_list(
        settings.path(settings["input"]["id_list_path"]),
        settings["input"]["expected_id_count"],
    )
    timings.record(
        timings_path, "1_ingest", time.monotonic() - started,
        rows=ledger.attrs["data_rows"], run_at=run_at,
        note=f"{len(ids)} ids queued",
    )
    print(f"[stage 1] {ledger.attrs['data_rows']} data rows, {len(ids)} ids to fetch")

    # --- Stage 2: acquisition --------------------------------------------
    print()
    print("=" * 72)
    print("Stage 2 — fetch details and credits")
    print("=" * 72)
    started = time.monotonic()
    try:
        ledger, log = fetch.run(ledger, settings, force=args.force)
    except MissingTokenError as error:
        # An instruction, not a traceback. This is the one failure a first-time
        # reader is most likely to hit, and the fix is four lines long.
        print(f"\n{error}", file=sys.stderr)
        return 1

    # Acquisition is timed separately from everything else, because the time
    # budget in stage 8 excludes it: it is network-bound and cached, so folding
    # it into the analysis time would measure the wrong thing.
    timings.record(
        timings_path, "2_acquire", time.monotonic() - started,
        api_calls=log.attrs["calls_made"],
        cache_hits=int(log["from_cache"].sum()),
        rows=len(log), run_at=run_at,
        note=f"append_credits={log.attrs['append_credits']}"
             + (", forced refetch" if args.force else ""),
    )

    save_ledger(ledger, processed / "id_ledger.csv")

    # --- Stage 3: flatten to tables --------------------------------------
    print()
    print("=" * 72)
    print("Stage 3 — flatten to one table per grain")
    print("=" * 72)
    started = time.monotonic()
    films_fetched = int((log["http_status"] == 200).sum())
    tables = flatten.run(settings, expected_films=films_fetched)
    timings.record(
        timings_path, "3_flatten", time.monotonic() - started,
        rows=len(tables["films"]), run_at=run_at,
        note=f"{len(tables['cast'])} cast, {len(tables['crew'])} crew rows",
    )

    # --- Stage 4: the proven join ----------------------------------------
    print()
    print("=" * 72)
    print("Stage 4 — collapse to film grain and join, with validation")
    print("=" * 72)
    started = time.monotonic()
    joined = join.run(settings, ledger, tables)
    timings.record(
        timings_path, "4_join", time.monotonic() - started,
        rows=len(joined["analysis"]), run_at=run_at,
        note=f"{len(joined['join_report'])} validated merges",
    )
    print()
    print("Join report — every merge, counted:")
    print(joined["join_report"].to_string(index=False))

    # --- Stage 5: profile and diagnose -----------------------------------
    print()
    print("=" * 72)
    print("Stage 5 — profile, and separate real extremes from errors")
    print("=" * 72)
    started = time.monotonic()
    profiled = profile.run(settings, joined["analysis"])
    timings.record(
        timings_path, "5_profile", time.monotonic() - started,
        rows=len(profiled["flags"]), run_at=run_at,
        note=f"{len(profiled['profile'])} columns profiled",
    )
    print()
    print("Money either side of the window boundary — nominal, so not one unit:")
    print(profiled["era_comparability"].to_string(index=False))

    # --- Stage 6: cleaning rules, every one reversible ------------------
    print()
    print("=" * 72)
    print("Stage 6 — cleaning as flags, with every choice runnable both ways")
    print("=" * 72)
    started = time.monotonic()
    cleaned = clean.run(settings, joined["analysis"], ledger)
    ledger = cleaned["ledger"]
    timings.record(
        timings_path, "6_clean", time.monotonic() - started,
        rows=len(cleaned["cleaned"]), run_at=run_at,
        note=f"{len(cleaned['exclusions'])} exclusions, "
             f"{len(cleaned['sensitivity'])} sensitivity runs",
    )
    save_ledger(ledger, processed / "id_ledger.csv")

    print()
    print("Sensitivity — the same comparison under each cleaning choice:")
    print(cleaned["sensitivity"].to_string(index=False))

    # --- Stage 7: the KPI tables -----------------------------------------
    print()
    print("=" * 72)
    print("Stage 7 — KPIs, both windows, counts beside every statistic")
    print("=" * 72)
    started = time.monotonic()
    measured = kpis.run(
        settings, cleaned["cleaned"], joined["directors"], tables["cast"]
    )
    timings.record(
        timings_path, "7_kpis", time.monotonic() - started,
        rows=len(cleaned["cleaned"]), run_at=run_at,
        note=f"{len(measured['windows_strict'])} windows, "
             f"{len(measured['bundles'])} bundles",
    )

    for window, table in measured["windows_strict"].items():
        print()
        print(f"Franchise vs standalone — {window}:")
        print(table[[
            kpis.GROUP_STRICT, "films", "median_roi", "floor_roi", "iqr_roi",
            "hit_rate_roi", "median_revenue",
        ]].to_string(index=False))

    print()
    print("Does the answer change between windows?")
    print(measured["flips"].to_string(index=False))

    print()
    print("Inside a franchise, by position:")
    print(measured["positions"].to_string(index=False))

    # --- Stage 9: the live spot-check ------------------------------------
    print()
    print("=" * 72)
    print("Stage 9 — re-fetch a stratified sample live and classify every difference")
    print("=" * 72)
    started = time.monotonic()
    try:
        checked = spotcheck.run(
            settings, cleaned["cleaned"], profiled["flags"], measured["shortlist"]
        )
        timings.record(
            timings_path, "9_spotcheck", time.monotonic() - started,
            rows=len(checked["sample"]), api_calls=len(checked["sample"]),
            run_at=run_at,
            note=f"{checked['sample']['slice'].nunique()} slices, "
                 f"moved={checked['movement']['moved']}",
        )
        print()
        print("Differences by slice:")
        print(checked["summary"].to_string(index=False))
    except MissingTokenError as error:
        # The only stage that always needs the network: it exists to compare
        # against the live source, so there is no cached answer to fall back on.
        print(f"\nSkipped — the spot-check must reach TMDb:\n{error}", file=sys.stderr)
        checked = None

    # --- Stage 10: the gate, then the memo -------------------------------
    print()
    print("=" * 72)
    print("Stage 10 — the release gate, then the memo")
    print("=" * 72)
    started = time.monotonic()
    try:
        written = memo.run(
            settings,
            accounting=joined["accounting"],
            ledger=ledger,
            cleaned=cleaned["cleaned"],
            windows=measured["windows_strict"],
            flips=measured["flips"],
            bundles=measured["bundles"],
            gaps=measured["bundle_gaps"],
            positions=measured["positions"],
            talent=measured["talent_directors"],
            shortlist=measured["shortlist"],
            fetch_log=log,
            spotcheck_movement=checked["movement"] if checked else None,
            spotcheck_films=len(checked["sample"]) if checked else 0,
            eras=profiled["era_comparability"],
        )
        timings.record(
            timings_path, "10_memo", time.monotonic() - started,
            rows=len(written["memo"].splitlines()), run_at=run_at,
            note="gate passed",
        )
    except memo.GateFailed as error:
        # Not a crash. The analysis ran; its output should not be published.
        print(f"\n{error}\n", file=sys.stderr)
        timings.record(
            timings_path, "10_memo", time.monotonic() - started, run_at=run_at,
            note="gate blocked publication",
        )
        return 2

    # --- Stage 8: the time budget -----------------------------------------
    # Runs last, not eighth. It reads run_timings.csv, so running it in
    # numerical order meant reading a partial file: stages 9 and 10 had not
    # recorded yet and were silently missing from the budget. Found by an
    # audit of the artefact, not by anything failing.
    print()
    print("=" * 72)
    print("Stage 8 — the time budget, measured last so it sees every stage")
    print("=" * 72)
    started = time.monotonic()
    payloads, _ = flatten.load_payloads(settings.path(settings["paths"]["raw_dir"]))
    measured_budget = budget.run(
        settings,
        timings.load(timings_path),
        payloads,
        ledger,
    )
    # Recorded like every other stage, so "time each stage" is literally true —
    # and excluded from the budget it computes, with the reason in the artefact,
    # because it measures the other stages by re-running them and would
    # otherwise count them twice.
    timings.record(
        timings_path, "8_budget", time.monotonic() - started, run_at=run_at,
        rows=len(measured_budget["scaling"]),
        note="measures stages 3-7 by re-running them at four sample sizes",
    )
    print()
    print("Where the time goes (stages 3-7, warm cache, acquisition excluded):")
    print(measured_budget["budget"].to_string(index=False))
    print()
    print("Projected to 500 titles, from measured per-stage scaling:")
    print(measured_budget["projection"][[
        "stage", "measured_seconds", "exponent_k", "scaling", "fit_quality",
        "projected_seconds",
    ]].to_string(index=False))

    print()
    print("-" * 72)
    print("Every source row, accounted for:")
    print(reconciliation_summary(ledger).to_string(index=False))
    print()
    print("...and how many of each reached the analysis table:")
    print(joined["accounting"].to_string(index=False))
    print("-" * 72)
    print(f"Artefacts written to {processed}/")
    print("  id_ledger.csv    — one row per source row, with a reason on each")
    print("  fetch_log.csv    — one row per id fetched, with HTTP status and timing")
    print("  run_timings.csv  — appended: how long each stage took, every run")
    print("  join_report.csv  — every merge: rows in, rows out, what matched")
    print("  id_accounting.csv— every source row, and whether it reached the analysis")
    print("  profile.csv      — every column: completeness, zeros, distribution")
    print("  flags.csv        — every value worth a look, with a verdict and a reason")
    print("  era_comparability.csv — why pre- and post-2000 money is not one unit")
    print("  exclusions.csv   — every film out of a metric, and the setting responsible")
    print("  sensitivity.csv  — the comparison recomputed under each cleaning choice")
    print("  kpi_*.csv        — the comparison per window, bundles, positions, talent")
    print("  kpi_flip_check.csv — whether the answer changes between windows")
    print("  shortlist_*.csv  — the picks and the runners-up they beat")
    print("  time_budget.csv  — where the time went, and what the boundary excludes")
    print("  scaling_measurements.csv, projection.csv — the 500-title projection")
    print("  spotcheck.csv    — every field re-checked live, with a verdict on each")
    print(f"Reports written to {settings.path(settings['paths']['reports_dir'])}/")
    print("  spotcheck.md     — the live re-check, generated so it cannot drift")
    print("  memo.md          — START HERE: one page, for the room")
    print("  improvement.md   — the one addition beyond the brief, and why this one")
    print(f"Tables written to {settings.path(settings['paths']['interim_dir'])}/")
    print("  films.csv, cast.csv, crew.csv, genres.csv — one table per grain")
    print("  analysis.csv     — one row per film, analysis-ready")
    print("  directors.csv    — one row per film per director")
    print()
    print("Every stage is built. The build order and the reasoning behind each")
    print("decision are in docs/02_build_runbook.md and reports/decision_log.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
