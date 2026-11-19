# ADR-031: Extraction loops over films; the KPIs never loop over rows

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
The brief requires results computed without looping over rows. Extraction loops over films, which
looks like an oversight unless it is recorded. The requirement is about computing statistics, not
about sequential I/O.

## Decision
Extraction loops, because it is sequential I/O against a rate-limited service: a loop is the correct
shape, and vectorisation is meaningless when each step is a network round trip. Every figure in the
KPI tables comes from a named aggregation over a group — no row iteration produces a statistic.

## Alternatives considered
- **Concurrent fetching** — faster, and harder to rate-limit politely against a shared API. At 500
  titles the measured 87s is not the bottleneck worth that complexity (ADR-023).
- **Vectorising the per-film classification work** — possible, and it would make the claim below
  literally true rather than true in substance.

## Consequences
- Acquisition is 20.3s cold, 2.3s warm, and excluded from the time budget with the boundary stated
  (ADR-023).
- Every KPI aggregation is vectorised and the measured analysis budget is 1.9s against a 10s limit.
- **Precise statement of what still iterates**, because an earlier version of this record claimed no
  stage past extraction loops over rows, and that was not accurate. Row-wise iteration remains in:
  classifying each cell of the id list; building the flag table; classifying each film's money
  quality, which produces `money_quality` and the return column that feed every number; building the
  exclusions table; and filling the ledger's per-film columns. None computes a statistic, and at 500
  titles each is linear and sub-second — but the honest claim is "no statistic is computed by
  iteration", not "nothing iterates".

## Revisit when
Any of the iterating steps shows up as a measurable share of the time budget, or the money-quality
classification is vectorised — at which point the list above gets shorter.
