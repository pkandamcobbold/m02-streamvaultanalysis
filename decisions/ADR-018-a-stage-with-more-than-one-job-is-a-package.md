# ADR-018: A stage that does more than one job becomes a package, not one long file

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Data team
- **Supersedes part of:** [ADR-017](ADR-017-five-stage-modules-in-a-flat-pipeline-package.md)

## Context

ADR-017 regrouped twelve modules into five, one file per stage. Two of the five then did too much.

| Module | Lines | Jobs in it |
|---|---|---|
| `extract.py` | 1,485 | parsing a text file, speaking HTTP with retries and a cache, reshaping nested responses |
| `checks.py` | 1,221 | a release gate, a live API call, a benchmark that re-runs other stages |

Three specific things were wrong, and the line counts are only the symptom.

Those jobs share nothing but their order in the run. Parsing needs a regular-expression library;
fetching needs an HTTP client; reshaping needs neither. They fail differently and they change for
different reasons.

The checks module held a **benchmark** — the thing that re-runs the analysis at four sample sizes to
measure scaling — in the same file as the gate that decides whether a board sees the memo. Finding a
benchmark inside a release gate is the clearest possible signal that the grouping is wrong.

And the time budget's boundary **runs through** the extract stage: shaping is inside the budget,
fetching is not (ADR-010). When a measurement the brief requires cuts a module in half, the module
boundary is in the wrong place. It is why extract had to report three separate sub-timings.

The reference structure's own extract module is 96 lines. Five files of 1,200 obeyed the letter of
"one file per stage" while losing the thing that made the rule worth having.

## Decision

A stage with more than one job becomes a package: one directory, one module per job, and an
`__init__.py` holding the stage's documentation, its entry point, and re-exports of its whole public
surface. There are still five stages, named and imported exactly as before.

```text
pipeline/extract/     ids.py (311)  fetch.py (778)  shape.py (427)
pipeline/validate/    profile.py (378)  clean.py (462)
pipeline/transform/   join.py (364)  kpis.py (266)  bundles.py (190)  talent.py (152)
pipeline/checks/      gate.py (187)  spotcheck.py (635)  budget.py (465)
```

The config and load modules stay single files, because each does one job.

> **Amended the same day.** As first written this record split only `extract` and `checks`, and said
> `validate` and `transform` would stay single files on the grounds that each held two closely
> coupled jobs. That was wrong about `transform`, which held four: the join, the central comparison,
> bundle economics, and talent. Those are four things a reader asks about separately. The decision
> above is unchanged; its scope now covers all four multi-job stages.

The transform split follows the brief's questions rather than the code's convenience. The
recommendation, the shortlist, the talent lever and the deal note come from separate claims, and
each is now a file you can open on its own.

## Alternatives considered

### Alternative A: Leave them as single files

- **How it would work:** Accept ADR-017 as it stood.
- **Why it is attractive:** No churn, no new `__init__.py` files to maintain, and nothing outside
  the modules would need to change.
- **Why rejected:** It loses on all three counts above. The line count is the symptom; the benchmark
  sitting inside the release gate is the complaint.

### Alternative B: Go back to ten flat modules

- **How it would work:** Undo ADR-017's regrouping and keep only its conventions.
- **Why it is attractive:** It is the better engineering, as ADR-017 already conceded.
- **Why rejected:** It abandons the five-stage structure the module specifies. ADR-017 still holds
  on that point.

### Alternative C: Flat files with compound names

- **How it would work:** `extract_ids.py`, `extract_fetch.py`, `extract_shape.py`, and so on.
- **Why it is attractive:** The same decomposition with no packages and no re-export bookkeeping.
- **Why rejected:** The stage stops being one importable thing, so the orchestrator's five steps
  become nine imports and the five-stage narrative survives only in the documentation.

## Consequences

- **What this buys:** The largest module is now 778 lines, down from 1,485, and the median is 311.
  Eleven of the fifteen modules are under 500 lines; before this, two files held 2,706 between them.
  Each file now has one reason to change.
- **What this costs:** A new public name added to a submodule has to be added to its `__init__.py`
  as well, or callers cannot see it. Four files to keep in step, and that is the price of each stage
  staying one importable thing.
- **What it costs the client if I am wrong:** Nothing. **Nothing outside the packages changed** —
  every existing reference resolves as before, because each `__init__.py` re-exports the stage's
  whole public surface. The orchestrator, the notebook and all 298 tests were untouched by either
  split and passed first time, which is the test of whether the re-exports are complete. The full
  run reproduces the same numbers, including the gate passing all four checks.
- **What would make me revisit this:** A submodule starting to do a second unrelated job, or a
  boundary the brief requires starting to run through the middle of one.

## What this survives

The rule survives and is the thing to carry forward: a stage is a package when it has more than one
job, and a file has one reason to change.

The current shape may not. `extract/fetch.py` at 778 lines is the one to watch — it is a session, a
cache, a rate limiter and an identifier resolver, and a case could already be made for separating
the cache from the client. I left it because those four are more coupled than anything I separated
here, and because there is a point where more files stop helping.
