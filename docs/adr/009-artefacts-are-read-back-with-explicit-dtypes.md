# ADR-009: Every artefact is read back with explicit dtypes, never by inference

**Status:** Accepted · **Date:** 2026-11-18 · **Deciders:** Data team

## Context
Also from an audit. `id_ledger.csv` holds `155`, but a plain `read_csv` on it returns `tmdb_id` as
**float64**, because the column also holds blanks for the rows that have no id. Extraction spends
considerable effort ensuring `550` never becomes `550.0`, writes a correct file, and then the
guarantee leaks at the file boundary. Nothing had broken yet only because nothing read the
artefacts back yet; the later stages, the notebook and the spot-check all do.

## Decision
Every artefact gets a loader with an explicit dtype map — the ledger, the fetch log, the run
timings — and every reader uses it. No stage, notebook cell or test calls a bare `read_csv` on a
pipeline artefact.

## Alternatives considered
- **Rely on whoever reads it passing dtypes** — the failure is silent and appears stages away from
  the cause.
- **Store artefacts as Parquet**, which carries its own dtypes. Technically better and wrong for
  this project: Adjoa and Yaw must be able to open these files in Excel and read them.

## Consequences
- No effect on the current numbers; prevents a silent one later.
- The round trip is tested, including a test asserting that the *naive* read does return float64 —
  so if a future pandas fixes this, the test says so rather than leaving a redundant loader in
  place for years.
- Every new artefact now owes the project a loader, which is a small standing cost.

## Revisit when
A pandas release makes the naive read return the written dtype. The test for that is already in
place and will fail, which is the signal.
