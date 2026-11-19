# ADR-007: Record a 404 as a permanent answer, and ask what the dead ids have in common

**Status:** Accepted · **Date:** 2026-11-18 · **Deciders:** Data team

## Context
5 of the 117 fetched ids returned 404: `8471293, 9412887, 8471294, 9412888, 7733901`, at source
rows 18, 35, 73, 93 and 99. They do not cluster by position in the file. They cluster perfectly by
id: every one of the 112 ids that resolved is **at most 301,528**, and every dead id is **at least
7,733,901** — no overlap at all, a gap of 25 times. Two pairs are consecutive
(`8471293`/`8471294`, `9412887`/`9412888`).

## Decision
Exclude 404 from the retry status list, cache the 404 envelope like any other response, and record
the id on the ledger as `not_found_404`. Report the id-range pattern as a finding rather than as a
count.

## Alternatives considered
- **Retry them**, on the theory that the fetch was at fault — slower, and rude to a shared service
  for an answer that will not change.
- **Recover them by title search** — there is no title to search for; a deleted TMDb entry leaves
  nothing behind.

## Consequences
- 112 films analysed instead of 117.
- TMDb ids are issued sequentially, so an id in the 7 to 9 million range belongs to an entry created
  far more recently than any genuine back-catalog film's, and the consecutive pairs suggest entries
  created back-to-back and later removed by moderation. These five were therefore almost certainly
  never back-catalog films, which makes the 5 lost rows **less** likely to bias the
  franchise-versus-standalone comparison than a random loss of 5 would be.
- The honest limit, carried into the memo: because nothing is known about what these entries *were*,
  it cannot be tested whether the loss falls unevenly on pre-2000 films or on franchises.
  "Unlikely" is not "checked".

## Revisit when
Next quarter's run. Re-run the id-range test: dead ids inside the live range would mean genuine
back-catalog titles are being lost, which is a different finding with a different cost.
