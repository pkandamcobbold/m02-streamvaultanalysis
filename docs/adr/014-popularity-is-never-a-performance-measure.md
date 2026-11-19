# ADR-014: TMDb `popularity` is never used as a performance measure

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
`popularity` ranges from 0.46 to 85.70 on this list, and the top three are *Avengers: Endgame*
(2019), *Interstellar* (2014) and *The Dark Knight* (2008). It is a rolling engagement score
recomputed daily from recent page views, votes and watchlist adds.

## Decision
Exclude it from every metric and keep it in the tables as fetched.
`profile.use_popularity_as_performance = false` makes the choice visible rather than implied by its
absence — and setting it true refuses to load, because there is no code path for it (ADR-030).

## Alternatives considered
- **Use it as a demand proxy** — tempting, since licensing value is about future viewing. Loses on
  both counts below.
- **Use it only as a tie-breaker** — a tie-breaker that is recency-biased still decides which of two
  equal films is recommended, by the wrong criterion.

## Consequences
- Two reasons, and the second is the one that matters. It is **recency-biased**: a 2019 blockbuster
  outscores a 1966 classic by two orders of magnitude, so using it would rank against the back
  catalog this project exists to evaluate. And it is **not reproducible**: the cached value is a
  snapshot, so re-running the analysis next month from the same cache would give a different answer
  from a fresh fetch, and neither would be wrong. Every other field used here — budget, revenue,
  runtime, votes — is fixed once a film is released.
- Current audience interest is genuinely relevant to a licensing decision, and this discards it.
  Accepted, and stated in the memo as a limitation: the analysis measures historical performance,
  not present demand.

## Revisit when
A demand signal becomes available from a source whose values do not move under the analysis. That
is a different project, not a settings change.
