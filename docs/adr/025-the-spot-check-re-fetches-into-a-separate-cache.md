# ADR-025: The spot-check re-fetches into a separate cache

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
The live check needs current values, which means a forced refetch. The obvious place to put them is
`data/raw/`, where every other response lives.

## Decision
Write live payloads to a separate `data/raw_spotcheck/`, gitignored on the same terms as
`data/raw/` (ADR-002).

## Alternatives considered
- **Force the refetch into `data/raw/`** — would overwrite the `fetched_at` stamps the memo's as-of
  date rests on and, worse, **would make any discrepancy disappear the moment it was found**: the
  next pipeline run would read the new values, recompute, and agree with itself. The check would be
  self-erasing.
- **Hold the live payloads in memory only** — the payloads are evidence; a reviewer should be able to
  see the response the check compared against, not just the verdict.

## Consequences
- No effect on the numbers; it is what makes the check repeatable.
- A second cache directory to explain, and a few MB on disk.
- Against that: the alternative is a check that cannot fail twice.

## Revisit when
The two caches drift far enough apart that comparing them stops being meaningful — which would mean
the analysis cache is older than the quarter it is being used for.
