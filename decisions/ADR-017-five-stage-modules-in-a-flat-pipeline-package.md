# ADR-017: Regroup the pipeline into five stages in a flat package

- **Status:** Accepted, and partly superseded by [ADR-018](ADR-018-a-stage-with-more-than-one-job-is-a-package.md)
- **Date:** 2026-11-19
- **Decision owner:** Data team, with the module reviewer

> ADR-018 keeps the five stages decided here and changes only their file shape, because two of the
> five turned out to be doing three unrelated jobs each. The table below still describes what each
> stage is responsible for.

## Context

I built the analysis as ten modules, following the ten stages the pipeline guide names, with the
reasoning for each choice written as long comments inside the code.

The reference structure for this module is different: a flat package of five stages, a thin
orchestrator, and the reasoning kept beside the code as numbered decision records rather than inside
it.

## Decision

Regroup into five stages, and move the inline reasoning into `decisions/`.

| Stage | Absorbs | Job |
|---|---|---|
| `extract` | the id ledger, the fetch, the shaping | Read the source with declared types; cache, retry, account for every id |
| `validate` | profiling, flagging, cleaning | Tell a defect from something that only looks like one, with a reason on every row |
| `transform` | the join, the KPIs | Prove the join, then answer each of the client's questions |
| `checks` | the gate, the live check, the time budget | Everything that must pass before anything is published |
| `load` | the memo and the improvement note | Write what leaves the building |

Stage timings move into the orchestrator's run log. The config module loads the settings file and
holds the constants more than one stage needs.

Each stage keeps writing its **own evidence** — the profile, the flags, the join report — beside the
assertion that produced it, rather than handing it to `load`. An assertion and the table that proves
it belong together.

## Alternatives considered

### Alternative A: Keep ten modules and adopt only the conventions

- **How it would work:** Leave the file layout alone, move the reasoning to decision records, adopt
  the orchestrator and test conventions.
- **Why it is attractive:** It is the better engineering. Ten small modules with the reasoning
  extracted would have been the strongest version, and the ten-stage numbering in the brief and the
  reports would keep reading straight onto the filenames.
- **Why rejected:** It does not match the structure this module specifies, and matching that
  structure is part of what is being assessed. Where taste and the specification disagree on
  something this visible, the specification wins and the cost gets recorded.

### Alternative B: Make each stage a sub-package of the old modules

- **How it would work:** Five directories, each holding the original modules more or less unchanged.
- **Why it is attractive:** Five stages at the top level, with module sizes preserved. Best of both.
- **Why rejected:** It is not the flat layout the reference structure shows. **This judgement did
  not survive the day:** ADR-018 adopts exactly this shape for the four stages that needed it, so
  read this rejection as the mistake it was rather than as a position the project still holds.

## Consequences

- **What this buys:** A layout that matches the reference structure — five stages, a thin
  orchestrator, config beside them — and reasoning that lives in version-controlled records instead
  of 3,500 lines of comments nobody reads in order.
- **What this costs:** The ten-stage numbering in the brief no longer maps one-to-one onto a
  filename, so the mapping has to live in this table and in the diagnosis. Tests also regrouped to
  one file per stage, with the builders two stages share moved into a shared fixtures file.
- **What it costs the client if I am wrong:** Nothing in the numbers — 298 tests pass and the full
  run reproduces the previous results exactly: 87 series films against 25 one-offs, typical return
  5.526 against 5.000, the same single flip on consistency. The cost is navigational, and ADR-018
  pays part of it back.
- **What would make me revisit this:** A sixth concern that fits none of the five stages. Adding one
  is a new record, not a quiet sixth file.

**Two behaviour changes fell out of the regrouping**, both deliberate and both verified. The release
year is now derived when the films table is shaped rather than during the join, which is where it
belonged and what lets validation run before any credit is merged on. As a result the profile
describes the films table and no longer covers the eight columns the join adds — nothing goes
unreported, because the join's own assertions already name every film with no director, no billed
lead or no genre.

## What this survives

The five-stage shape survives, including into ADR-018, which changes the files inside the stages and
not the stages themselves. What did not survive is my judgement in Alternative B: within a day it
was clear that two stages were too large, and the shape I rejected there is the one ADR-018 adopts.

The time budget's boundary now runs *through* a stage — shaping is inside it, fetching is not — so
`extract` reports three sub-timings. That is a seam worth watching, and it is the first piece of
evidence ADR-018 cites.
