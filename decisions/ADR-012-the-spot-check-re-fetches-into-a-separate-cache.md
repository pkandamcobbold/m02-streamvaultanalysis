# ADR-012: The live check writes to its own cache, not over the analysis cache

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Data team

## Context

The spot-check compares what the analysis used against what the source says now, so it has to fetch
fresh copies. The obvious place to put them is the folder where every other response already lives.

## Decision

Live responses go to a separate folder, ignored by git on the same terms as the main cache
(ADR-002).

## Alternatives considered

### Alternative A: Fetch over the top of the analysis cache

- **How it would work:** Force a refresh of the sampled films in place.
- **Why it is attractive:** One cache to explain, no duplication, and the pipeline would then be
  running on the freshest available data.
- **Why rejected:** Two reasons, and the second is serious. It would overwrite the timestamps the
  memo's as-of date rests on. And it would make any discrepancy **disappear the moment it was
  found**: the next run would read the new values, recompute, and agree with itself. The check would
  erase its own evidence, so it could never fail twice.

### Alternative B: Hold the live responses in memory and discard them

- **How it would work:** Fetch, compare, report, throw away.
- **Why it is attractive:** Nothing extra on disk and nothing extra to explain.
- **Why rejected:** The responses are the evidence. A reviewer should be able to see what the check
  compared against, not just the verdict it reached.

## Consequences

- **What this buys:** A check that is repeatable and whose evidence survives it. The as-of date
  keeps meaning what it says.
- **What this costs:** A second cache folder to explain, and a few megabytes on disk.
- **What it costs the client if I am wrong:** Nothing on any number. What the alternative would have
  cost is a check that silently stops being able to detect the thing it exists to detect.
- **What would make me revisit this:** The two caches drifting far enough apart that comparing them
  stops being meaningful — which would mean the analysis cache is older than the quarter it is being
  used for, and the fix is to refresh it rather than to merge the folders.

## What this survives

Unchanged at any size. If anything the argument strengthens: the more quarters this runs, the more
valuable it is that a discrepancy found in October is still visible in January.
