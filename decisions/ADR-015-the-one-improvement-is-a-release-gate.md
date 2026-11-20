# ADR-015: Add a release gate that refuses to publish a memo nobody should act on

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Data team

## Context

Everything else in this project protects the analysis from being wrong. Nothing protected Adjoa from
the analysis being wrong *and looking fine*.

She reruns this every quarter, on her own laptop, sometimes live in the meeting. And the pipeline is
deliberately built to carry on rather than stop (ADR-004, ADR-009) — so a truncated input list, or a
money column half missing, would still produce a confident one-page recommendation with nothing on
it to say otherwise.

This is the improvement beyond the brief.

## Decision

Four checks run before the memo is written. If any fails, **no memo and no shortlist are produced**:
the run stops and prints which check failed, in language that says what to do next, including the
one setting that overrides it.

The checks are: every row of the source file accounted for; enough films left to compare the two
groups; money data complete enough to rank on; and the live re-check has not changed the answer.

## Alternatives considered

### Alternative A: A sensitivity panel

- **How it would work:** One table showing whether the recommendation survives each judgement call
  being flipped.
- **Why it is attractive:** It directly arms Kwame against the challenge he is going to get in the
  room, which is a real need.
- **Why rejected:** Already built, at the validate stage. And it assumes the run was sound in the
  first place — it tells you whether your assumptions matter, not whether your input was intact.

### Alternative B: A run-over-run diff

- **How it would work:** Each quarter, show Adjoa what changed since last time: new titles, revised
  figures, shortlist movements.
- **Why it is attractive:** It serves the quarterly rerun better than anything else on this list,
  and it is the thing she would actually use most.
- **Why rejected:** It needs two quarters of history to say anything. Next quarter, not this one.

### Alternative C: A bundle dead-weight score

- **How it would work:** For each franchise, the share of its films below the standalone median — a
  negotiating number.
- **Why it is attractive:** It is immediately usable at the table: "you are asking us to pay for
  three weak films."
- **Why rejected:** It is a refinement of the answer rather than a protection against the answer
  being wrong. Valuable, and not the gap.

## Consequences

- **What this buys:** The only check in the project whose failure mode is "the board was misled"
  rather than "a stage crashed". The assertions throughout the pipeline protect each step from the
  one before; this protects the client-facing output from the whole pipeline.
- **What this costs:** It can block a run Adjoa believes is fine. Handled two ways: the checks are
  blunt, so each one failing makes the memo actively misleading rather than merely imperfect, and
  the failure message names the setting that overrides it — so skipping the gate is a decision
  somebody makes and can be asked about, rather than something that happens silently.
- **What it costs the client if I am wrong:** A quarter where Adjoa cannot publish and has to
  override the gate under time pressure. Against that: a quarter where she presents a confident
  number built on 40 films instead of 112, and nobody in the room can tell.
- **What would make me revisit this:** The gate blocking a run that turns out to have been sound, or
  the minimum film count ceasing to be a meaningful floor as the list grows.

## What this survives

Three of the four checks are proportions or reconciliations, so they need no re-tuning as the list
grows. The minimum film count is an absolute floor and should be raised if the standalone group stays
as thin as it is now (F-04).

The design constraint that survives is the count: four. A gate with twenty conditions is one that
somebody permanently disables the first time it fires over something cosmetic, and then it protects
nothing at all.
