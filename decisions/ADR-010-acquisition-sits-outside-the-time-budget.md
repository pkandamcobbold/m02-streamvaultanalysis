# ADR-010: Keep fetching outside the time budget, and report it immediately beside it

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Paapa Andam-Cobbold

## Context

A run from an empty cache spends 20.3 seconds fetching and 1.9 seconds analysing.

Report those as one number and the analysis looks twelve times slower than it is. Worse, the
combined figure would move with TMDb's response times and Adjoa's wifi rather than with anything I
wrote, so it would measure the wrong thing and change for reasons nobody could act on.

The brief asks for a time budget with the boundary stated. It does not name a number, so the number
is mine to choose and to say I chose.

## Decision

The budget covers the analysis only: shaping, validating and transforming, with the data already
cached, on one machine, single-threaded. Fetching is excluded, and measured and reported directly
beside it so nothing is hidden.

The limit is 10 seconds, set in the settings file and stated as ours rather than the client's. The
checks stage refuses to run if fetching ever appears inside the budget, and verifies that the
per-stage shares add up.

## Alternatives considered

### Alternative A: One total, the way a user experiences it

- **How it would work:** Time the whole run, from launch to memo, and report that.
- **Why it is attractive:** It is the number Adjoa actually waits for, and it needs no explanation
  or boundary.
- **Why rejected:** It cannot be broken down. If it got worse, nothing in it would say whether the
  cause was my code or the network, so nobody could act on it.

### Alternative B: Analysis only, with fetching excluded and unmentioned

- **How it would work:** Report 1.9 seconds against the limit and say nothing about the other 20.
- **Why it is attractive:** It is the flattering number, and the boundary statement makes it
  technically defensible.
- **Why rejected:** It quietly excludes the expensive part. A reader who later discovered the full
  run takes half a minute would be right to distrust everything else in the report.

## Consequences

- **What this buys:** A measurement that means something. The budget reads 1.9 seconds against a
  10-second limit, and shaping the nested responses is 64% of it — so if the budget is ever at risk,
  the artefact already says which stage to look at.
- **What this costs:** Two numbers to explain instead of one, and a boundary that has to be restated
  wherever either figure appears.
- **What it costs the client if I am wrong:** Someone asks how long it takes on a fresh machine and
  gets the wrong answer. They need both numbers added — roughly 107 seconds at 500 titles — and
  giving them separately with the boundary named is exactly what makes that addition possible.
- **What would make me revisit this:** The analysis stages approaching the limit, or anyone quoting
  a single blended figure in a report, which would mean the boundary had stopped being carried.

## What this survives

The boundary survives. The figures do not: fetching is projected separately from the *cold* run —
0.173 seconds per call, so about 87 seconds at 500 titles — because projecting from a cached run
would promise two seconds and deliver ninety. That distinction is the thing to keep when the list
grows.
