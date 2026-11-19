# ADR-032: Five stage modules in a flat `pipeline/` package, with the rationale in the ADRs

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team, with the module reviewer

## Context
The analysis was built as ten stage modules under `src/streamvault/`, following the ten stages the
lab guide names, with the reasoning for each choice written as long comments and docstrings inside
the code. The reference structure for this module is a flat `pipeline/` package of five ETL stages,
a thin orchestrator, and the "why" versioned alongside the code as numbered decision records.

## Decision
Regroup into five stage modules in a flat `pipeline/` package, and move the inline rationale into
`docs/adr/`:

| Stage | Absorbs | Job |
|---|---|---|
| `extract.py` | the id ledger, the TMDb fetch | Read the source with declared types; cache, retry, account for every id |
| `validate.py` | profiling, flagging, cleaning | Defect against legitimate, with a reason on every row |
| `transform.py` | flattening, the join, the KPIs | Shape the nested JSON, prove the join, build the mart |
| `checks.py` | the release gate, the live spot-check, the time budget | Gates that must pass before anything is published |
| `load.py` | the generated memo and reports, and the ledger's final state | Write the client-facing output |

Stage timings move into the orchestrator's run log. `pipeline/config.py` loads `settings.toml` and
holds the column and dtype constants, plus the few constants more than one stage needs.

Each stage keeps writing its **own evidence** artefact — the profile, the flags, the join report —
beside the assertion that produced it, rather than handing it to `load`. An assertion and the table
that proves it belong together; routing them through a later stage would separate a claim from its
evidence. `load` writes what leaves the building: the memo, the improvement note, and the ledger.

## Alternatives considered
- **Keep ten modules and adopt only the conventions** — the ten-stage numbering in the brief and the
  reports would keep reading straight onto the code, but the layout would not match the structure
  this module teaches.
- **Make each stage a sub-package** holding the old modules — preserves module size, and is not the
  flat layout the reference structure specifies.

## Consequences
- The layout matches the reference structure: five stages, one file each, plus config.
- Five modules absorbing twelve would be very large files if the comments moved with them. They do
  not: the rationale moves to the ADRs, which is where this structure keeps it, and the modules keep
  only what a reader needs to follow the code.
- The ten-stage numbering in the brief and the pipeline guide no longer maps one-to-one onto a
  filename. `docs/findings.md` and this index carry the mapping instead.
- Tests regroup to one file per stage module, with the builders two stages share in
  `tests/conftest.py`. 298 tests pass, and the full run reproduces the previous numbers exactly:
  87 franchise films against 25 standalones, median return 5.526 against 5.000, the same single flip
  on spread.
- **Two behaviour changes fell out of the regrouping**, both deliberate and both verified:
  - `release_year` is derived when the films table is shaped rather than during the join. The window
    boundary is a year and the year is a property of the film, so this is where it belonged — and it
    is what lets `validate` run on the films table before any credit is merged onto it, which is
    what keeps the five stages a single pass.
  - The profile therefore describes the **films** table, so it no longer covers the eight columns
    the join adds (the director and genre labels, the billed lead). Nothing goes unreported: the
    join's own assertions already name every film with no director, no billed lead or no genre. The
    profile is a profile of the source fields, which is what a data profile is for.
- The time budget's boundary now runs *through* a stage rather than between two: shaping the cached
  payloads is inside it, the acquisition is not. So `extract` records three sub-timings
  (`extract.read_ids`, `extract.acquire`, `extract.shape`) and ADR-023's boundary is unchanged in
  substance.

## Revisit when
A sixth concern appears that fits none of the five stages. Adding it as a stage is a new ADR, not a
quiet sixth file.
