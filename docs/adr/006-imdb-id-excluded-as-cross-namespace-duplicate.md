# ADR-006: Resolve the IMDb id, then exclude it as a duplicate in a second id namespace

**Status:** Accepted · **Date:** 2026-11-18 · **Deciders:** Data team

## Context
Source row 95 holds `tt0468569`, an IMDb identifier in a column of TMDb ids. Resolved live via
`/find/tt0468569?external_source=imdb_id` to TMDb **155, *The Dark Knight* (2008-07-16)**. TMDb 155
is already on the candidate list **twice**, at source rows 2 and 91.

## Decision
Resolve foreign ids as a procedure, not as something someone remembers, then classify the outcome.
A row resolving to an id already on the list gets status `duplicate_other_namespace` and a reason
naming the row it duplicates. A row resolving to an id *not* otherwise on the list is recovered,
queued for fetching, and forced into the spot-check sample, because its provenance is unlike every
other row on the list.

## Alternatives considered
- **Drop the row as unparseable** — never asks what it was, and would have hidden a duplicate.
- **Resolve it and add the film** — the obvious fix, and the wrong one: it would have put three
  copies of one film into every KPI.

## Consequences
- The candidate pool is unchanged at 112 analysed films either way.
- The rejected obvious fix would have landed triple weight on *The Dark Knight*, a franchise film,
  squarely on the franchise side of the central comparison: inflating the franchise median, the
  franchise hit rate, and any talent aggregate touching Nolan or Bale. This is the one place in this
  data where the obvious action and the correct action differ.
- If the identification were wrong — it is not; the live response is cached at
  `data/raw/tt0468569__find_imdb_id.json` and names the film and its release date — one title would
  be missing from a pool of 112, a 0.9% reduction. The smaller error by a wide margin.

## Revisit when
A future list carries IMDb ids in volume. That makes it a contract violation to escalate (see
`docs/data_contract.md`) rather than a one-row judgement.
