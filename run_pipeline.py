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

from streamvault import fetch, timings
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

    print()
    print("-" * 72)
    print("Every source row, accounted for:")
    print(reconciliation_summary(ledger).to_string(index=False))
    print("-" * 72)
    print(f"Artefacts written to {processed}/")
    print("  id_ledger.csv    — one row per source row, with a reason on each")
    print("  fetch_log.csv    — one row per id fetched, with HTTP status and timing")
    print("  run_timings.csv  — appended: how long each stage took, every run")
    print()
    print("Stages 3-10 are not built yet. See docs/02_build_runbook.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
