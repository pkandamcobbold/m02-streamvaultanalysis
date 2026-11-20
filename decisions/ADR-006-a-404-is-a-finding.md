# ADR-006: Record a missing film as a permanent answer, and ask what the dead ids have in common

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Data team

## Context

Five of the 117 ids I tried came back as "not found": `8471293`, `9412887`, `8471294`, `9412888` and
`7733901`, at rows 18, 35, 73, 93 and 99 of the file.

They do not cluster by position. They cluster perfectly by id. Every one of the 112 ids that worked
is **301,528 or below**. Every dead id is **7,733,901 or above**. There is no overlap at all — a gap
of twenty-five fold — and two of the five are consecutive pairs.

## Decision

A "not found" is an answer, so I record it and move on: the id goes on the ledger with its reason,
the response is cached like any other so reruns do not ask again, and it is deliberately excluded
from the retry policy.

Then I treat the pattern as a finding rather than a count, because five dead ids is a sentence and
five dead ids that all sit above seven million is evidence.

## Alternatives considered

### Alternative A: Retry them

- **How it would work:** Put "not found" in the retry list alongside the server errors and the rate
  limits, on the theory that the fetch might have been at fault.
- **Why it is attractive:** It is the defensive default, and it costs nothing to type.
- **Why rejected:** It is slower and it is rude to a shared service, for an answer that will not
  change. A missing film is not a transient failure.

### Alternative B: Recover them by searching for the titles

- **How it would work:** Search the catalogue by name and match the results back to the list.
- **Why it is attractive:** It would recover real titles rather than writing off five rows, and
  recovering data generally beats losing it.
- **Why rejected:** There is no title to search for. The list is ids and nothing else, and a deleted
  entry leaves nothing behind to search with.

## Consequences

- **What this buys:** 112 films analysed instead of 117, with a reason recorded for each of the five
  and an explanation of what they probably were. Ids are issued in order, so something in the
  7-to-9 million range was created far more recently than any genuine back-catalogue film's entry
  would have been, and the consecutive pairs suggest entries created one after another and later
  removed. On that evidence these five were probably never back-catalogue films — which makes
  losing them **less** damaging to the comparison than losing five random titles.
- **What this costs:** Five fewer candidates, and an inference I cannot prove.
- **What it costs the client if I am wrong:** If those five were real back-catalogue titles, the
  loss might fall unevenly on older films or on series, and I would have no way to know. Because
  nothing is left to identify them, that cannot be tested in either direction. "Probably never
  back-catalogue films" is an inference from the id range, not a check, and the memo says so.
- **What would make me revisit this:** Dead ids appearing *inside* the live range. That would mean
  genuine titles are being lost, which is a different finding with a different cost.

## What this survives

The handling survives unchanged. The inference needs re-testing every quarter, and the id-range
comparison is the cheapest way to do it — it is two numbers. At 500 titles I would expect more dead
ids; what matters is whether they still sit in a range that cannot contain an old film.
