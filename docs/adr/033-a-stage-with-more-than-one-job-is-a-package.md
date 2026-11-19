# ADR-033: A stage with more than one job is a package, not one long file

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team · **Supersedes part of** [ADR-032](032-five-stage-modules-in-a-flat-pipeline-package.md)

## Context
ADR-032 regrouped twelve modules into five, one file per stage, to match the reference structure.
Two of the five then did too much:

| Module | Lines | Jobs in it |
|---|---|---|
| `extract.py` | 1,485 | parsing a text file, HTTP with retries and caching, reshaping nested JSON |
| `checks.py` | 1,221 | a release gate, a live API call, a benchmark that re-executes other stages |

Three specific things were wrong, not just the line counts:

- Those jobs share nothing but their order. `ids` needs `re`; `fetch` needs `requests` and
  `urllib3`; `shape` needs neither. They fail differently and they change for different reasons.
- `checks.py` held a **benchmark** — `measure_scaling` imports `extract`, `transform` and
  `validate` and re-runs them at four sample sizes — in the same file as the gate that decides
  whether a board sees the memo. Finding a benchmark inside a release gate is the clearest signal
  the grouping was wrong.
- The time budget's boundary **runs through** `extract`: shaping is inside it, acquisition is not
  (ADR-023). A required measurement boundary cutting a module in half says the module boundary is
  in the wrong place. It is why `extract` had to report three sub-timings.

The reference structure's own `extract.py` is 96 lines, so five files of 1,200 obeyed the letter of
"one file per stage" while losing the thing that made it worth having.

## Decision
A stage with more than one job becomes a package: one directory, one module per job, and
`__init__.py` holding the stage's docstring, its entry point, and re-exports of the whole public
surface. There are still five stages, named and imported exactly as before.

```text
pipeline/extract/     ids.py (311)  fetch.py (778)  shape.py (427)
pipeline/validate/    profile.py (378)  clean.py (462)
pipeline/transform/   join.py (364)  kpis.py (266)  bundles.py (190)  talent.py (152)
pipeline/checks/      gate.py (187) spotcheck.py (635) budget.py (465)
```

`config.py` and `load.py` stay single files: each does one job.

> **Amended the same day.** As first written, this record split only `extract` and `checks` and said
> `validate` and `transform` would stay single files, on the grounds that each held two closely
> coupled jobs. That was wrong about `transform`, which held four — the join, the central
> comparison, bundle economics and talent — and those are four things a reader asks about
> separately. The decision above is unchanged; its scope now covers all four multi-job stages.

`transform`'s split follows the brief's questions rather than the code's convenience. The
recommendation, the shortlist, the talent lever and the deal note are separate questions from
separate claims, and each is now a file you can open on its own.

## Alternatives considered
- **Leave them as single files** — what ADR-032 chose. Loses on all three counts above; the line
  count is the symptom, not the complaint.
- **Go back to ten flat modules** — the better engineering, and it abandons the five-stage structure
  the module specifies. ADR-032 still holds on that point: five stages is the requirement.
- **Flat files with longer names** (`extract_ids.py`, `extract_fetch.py`) — same decomposition
  without the package, and the stage stops being one importable thing, so the orchestrator's five
  steps become nine imports.

## Consequences
- **The largest module is now 778 lines** (`extract/fetch.py`), down from 1,485, and the median is
  311. Eleven of the fifteen modules are under 500 lines; before this, two files held 2,706 between
  them.
- **Nothing outside the packages changed.** `extract.build_films`, `transform.GROUP_STRICT` and
  `checks.ANALYSIS_STAGES` resolve exactly as before, because each `__init__.py` re-exports the
  stage's whole public surface. The orchestrator, the notebook and all 298 tests were untouched by
  either split and passed first time. That is the test of whether the re-exports are complete.
- The full run reproduces the same numbers: 87 franchise films against 25 standalones, median
  return 5.526 against 5.000, the same single flip on spread, the gate passing on all four checks.
- A new public name added to a submodule has to be added to `__init__.py` as well, or callers
  cannot see it. That is a real standing cost — four `__init__.py` files to keep in step — and it
  is the price of the stage staying one importable thing.
- The five-stage narrative in the orchestrator, the README and ADR-032's mapping table is unchanged.
  `run_pipeline.py` still calls five functions in order.

## Revisit when
A submodule crosses the same line this record was written about: it starts doing a second unrelated
job, or a boundary the brief requires starts running through the middle of it. `extract/fetch.py` at
778 lines is the one to watch — it is a session, a cache, a rate limiter and a resolver, and a case
could already be made for separating the cache from the client.
