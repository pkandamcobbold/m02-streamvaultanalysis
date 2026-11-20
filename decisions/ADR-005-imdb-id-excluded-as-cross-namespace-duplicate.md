# ADR-005: Resolve the foreign identifier, then exclude it as a duplicate

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Data team

## Context

Row 95 of the candidate list holds `tt0468569`. That is an identifier from a different film
catalogue, sitting in a column that is supposed to hold TMDb ids.

I looked it up rather than guessing. It resolves to *The Dark Knight*, released July 2008 — and that
film is **already on the candidate list twice**, at rows 2 and 91.

## Decision

I wrote the resolution as a procedure with three outcomes, rather than as a one-off fix, because
next quarter's list comes from the same three desks.

A row that resolves to nothing stays unusable. A row that resolves to a film already on the list is
recorded as a duplicate in a second identifier system and excluded. A row that resolves to a film
*not* otherwise on the list is recovered, fetched, and forced into the spot-check sample — its
provenance is unlike every other row, so it deserves checking.

This row took the middle path.

## Alternatives considered

### Alternative A: Drop the row as unparseable

- **How it would work:** Classify it as a bad value, like the placeholders and the blank row, and
  move on.
- **Why it is attractive:** It is consistent with how every other unusable value is handled, and it
  costs no API call.
- **Why rejected:** It never asks what the row was. It would have reached the right outcome — the
  film is excluded either way — for the wrong reason, and it would have hidden the fact that this
  film is on the list three times.

### Alternative B: Resolve it and add the film

- **How it would work:** Look it up, find a valid film, fetch it, include it.
- **Why it is attractive:** This is the obvious fix, and it is what "recover what you can" would
  suggest. It also looks like diligence: a row nobody else would have salvaged.
- **Why rejected:** It would have put **three copies of one film** into every figure. Worse, *The
  Dark Knight* is a series entry, so all three copies would land on the series side of the central
  comparison — inflating the series typical return, the series hit rate, and any talent figure
  touching Nolan or Bale.

## Consequences

- **What this buys:** The analysed pool is unchanged at 112 films, and the central comparison is not
  quietly weighted toward one group. This is the one place in this data where the obvious action and
  the correct action differ, which is the whole reason it is written down.
- **What this costs:** One API call to a lookup endpoint, and a branch of logic that will do nothing
  at all in a quarter where the list is clean.
- **What it costs the client if I am wrong:** If the identification were wrong, one title would be
  missing from a pool of 112 — a 0.9% reduction. It is not wrong: the response is cached and names
  the film and its release date. Against the alternative error, which triples a film's weight in the
  comparison the whole decision rests on, this is the smaller mistake by a wide margin.
- **What would make me revisit this:** A future list carrying foreign identifiers in volume. One row
  is a judgement call; thirty is a problem with how the list is assembled, and belongs in the data
  contract as something to escalate.

## What this survives

The procedure survives; this particular row does not recur. At 500 titles the chance of a foreign
identifier rises and so does the chance that one resolves to a film genuinely not on the list — the
third outcome, which has never yet fired. It is implemented and tested anyway, which is the point of
writing it as a procedure.
