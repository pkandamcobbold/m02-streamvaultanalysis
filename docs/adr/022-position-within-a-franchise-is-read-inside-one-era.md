# ADR-022: Read the position-within-franchise effect inside one era, and name the confound

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
Pooled across all years, return falls monotonically with position in a series: first 7.76, middle
5.41, last 4.44. But first entries have a median release year of 2000 and are 50% pre-2000, while
last entries median 2008.5 and are 14% pre-2000. Position is confounded with era, and era inflates
returns (ADR-013). Half the team believes the *middle* entries are the weak ones.

## Decision
Report both the pooled and the within-era figures, name the confound, and quote the within-era
figures in the recommendation.

## Alternatives considered
- **Report the pooled figures** — supports the team's claim most strongly, and by three times the
  real margin. The most flattering and least useful outcome.
- **Report within-era figures only** — hides the size of the confound, which is itself a finding.

## Consequences
- The decline shrinks from **43% to 14%** from opener to final entry, so roughly two-thirds of the
  apparent effect was the era.
- The ranking changes: within one era, middle entries (5.05) sit *above* last entries (4.55), so the
  team's specific claim about middle entries is **not supported** even though the general direction
  is (F16).
- The within-era groups are 11, 27 and 19 films, so the 14% is approximate and is given as such. The
  pre-2000 breakdown has only three "last" entries and is deliberately not reported as a finding.
- **Open item:** the pipeline's position artefact holds the pooled figures only. The within-era
  figures quoted in the memo were computed by hand from the cleaned table and are not yet produced
  by code, so they cannot be re-derived by a rerun. The artefact currently published is the version
  this record says not to quote.

## Revisit when
The open item above is closed by computing the within-era breakdown in the pipeline — at which point
the artefact and the memo quote the same numbers, and a rerun can falsify both.
