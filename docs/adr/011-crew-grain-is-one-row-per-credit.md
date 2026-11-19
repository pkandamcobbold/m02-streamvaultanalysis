# ADR-011: The crew table is one row per credit, not per person

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
914 of 24,932 crew rows are the same person in more than one job on the same film: a
writer-director, a producer-director. And 9 of 112 films have more than one person credited as
Director.

## Decision
Keep one row per credit, and resolve the director question explicitly when collapsing to film
grain. Shaping the nested JSON changes shape and nothing else — no filtering, no cleaning, no
derived judgements — so every judgement lives in one place with a record. The one exception is the
franchise label (ADR-010), which is named as derived.

## Alternatives considered
- **Deduplicate to one row per person per film** — loses the jobs, and makes any count of *credits*
  wrong while a count of *people* needs the deduplication. Both numbers have to be derivable from
  the same table.
- **Add a derived "primary director" column at this stage** — puts a judgement in the stage whose
  only job is shape.

## Consequences
- No effect on any number by construction. It determines what the join must handle: with 9
  multi-director films, a naive merge would silently pick whichever row comes first and produce a
  director attribution that is arbitrary but looks authoritative.
- A note is printed at every run, so the 914 figure is never a surprise.
- Any aggregation over this table has to state whether it is counting credits or people.

## Revisit when
A later question needs crew roles beyond Director. The grain already supports it; the note should
then name the roles in use.
