# ADR-029: The one improvement beyond the brief is a release gate

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team (threshold choices — see Q15)

## Context
Everything else in this project protects the analysis from being wrong. Nothing protected Adjoa from
the analysis being wrong *and looking fine*. She reruns it quarterly, on a laptop, sometimes live in
the meeting, and the pipeline is deliberately built to carry on rather than crash (ADR-005,
ADR-017) — so a truncated input list or a half-missing money column would still produce a confident
one-page recommendation.

## Decision
Four checks run before the memo is written, and if any fails **no memo and no shortlist are
produced**: the run stops and prints what failed, in language that says what to do next, including
the one setting that overrides it. The checks are: every source row accounted for; enough films to
compare groups; money data complete enough to decide on; and the live re-check does not change the
answer.

## Alternatives considered
- **A sensitivity panel** — already built, and it assumes the run was sound in the first place.
- **A run-over-run diff** — genuinely useful for the quarterly rerun, and it needs two quarters of
  history to be worth anything.
- **A bundle dead-weight score** — a good negotiating number, and a refinement of the answer rather
  than a protection against the answer being wrong.

## Consequences
- It is the only check in the project whose failure mode is "the board was misled" rather than "a
  stage crashed". The assertions throughout the pipeline protect each step from the one before; this
  protects the client-facing output from the whole pipeline.
- It can block a run Adjoa believes is sound. Handled by keeping the checks blunt — each one,
  failing, makes the memo actively misleading rather than merely imperfect — and by naming
  `gate.enabled = false` in the failure message, so skipping it is a decision somebody makes and can
  be asked about rather than something that happens silently.
- A gate with twenty conditions is one that gets permanently disabled the first time it fires over
  something cosmetic. Four is the whole design.
- All four are proportions or reconciliations, so none needs re-tuning as the list grows, except
  `gate.min_films_for_a_recommendation`, which is an absolute floor.

## Revisit when
The gate blocks a run that turns out to have been fine, or `min_films_for_a_recommendation` stops
being a meaningful floor at 500 titles.
