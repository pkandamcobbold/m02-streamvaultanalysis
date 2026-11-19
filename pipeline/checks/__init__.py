"""Stage 4 — checks: the gates that must pass before anything is published.

Three concerns, one module each. They share only their position in the run:
one refuses to publish, one talks to a live API, and one is a benchmark that
re-executes the other stages. Keeping a benchmark in the same file as a
release gate was the clearest thing wrong with the merged version (ADR-033).

    gate.py       four blunt checks; the one improvement beyond the brief
    spotcheck.py  re-fetch a stratified sample live and classify the differences
    budget.py     the time budget, and a measured projection to 500 titles

Only the gate can stop the run. The spot-check feeds it — a live re-check that
moves the answer is one of the four conditions — and the budget reports rather
than blocks, because the limit is one we set, not one the client gave us.
"""
from __future__ import annotations

from typing import Any

from pipeline.checks.budget import (
    ACQUISITION_STAGE,
    ANALYSIS_STAGES,
    BUDGET_COLUMNS,
    INGEST_STAGE,
    OUT_OF_BUDGET_NOTES,
    PROJECTION_COLUMNS,
    SCALING_COLUMNS,
    assert_budget,
    describe_scaling,
    fit_exponent,
    latest_timing_run,
    load_timings,
    measure_scaling,
    project,
    project_acquisition,
    time_budget,
    time_budget_report,
)
from pipeline.checks.gate import (
    GATE_COLUMNS,
    GateFailed,
    enforce,
    gate,
    gather,
)
from pipeline.checks.spotcheck import (
    COMPARISON_COLUMNS,
    KNOWN_SLICES,
    MATERIAL_FIELDS,
    SAMPLE_COLUMNS,
    VERDICT_DRIFT,
    VERDICT_GONE,
    VERDICT_IDENTICAL,
    VERDICT_MATERIAL,
    VOLATILE_FIELDS,
    assert_spotcheck,
    build_sample,
    compare_film,
    run_comparison,
    shortlisted_film_ids,
    spot_check,
    summarise,
    would_it_move_the_recommendation,
    write_report,
)


# ---------------------------------------------------------------------------
# The stage entry point
# ---------------------------------------------------------------------------

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
