# ADR-023: Acquisition sits outside the time budget and is reported beside it

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team (no budget stated in the brief — see Q8)

## Context
A cold run spends **20.3s** fetching and **1.9s** analysing. Folding them together makes the
analysis look twelve times slower than it is, and the combined figure would move with TMDb's latency
and Adjoa's wifi rather than with this code. The brief asks for a budget with the boundary stated but
names no number.

## Decision
The budget covers the analysis stages only, with the boundary stated in one place and carried into
the memo: **shaping, joining, profiling, cleaning and KPIs; warm cache; one machine; single-threaded;
acquisition excluded.** Acquisition is measured and reported immediately beside it. The limit is set
at 10s in settings, as ours to choose and stated as such. The checks stage hard-fails if acquisition
ever appears inside the budget, and verifies the per-stage shares sum to 1.

## Alternatives considered
- **One total**, which is what a user experiences — not decomposable, and dominated by the network.
- **Analysis only, acquisition excluded and unmentioned** — the dishonest option: quietly excluding
  the expensive part.

## Consequences
- The budget reads **1.9s against a 10s limit**, of which shaping the nested JSON is 64%.
- Acquisition is projected separately from the **cold-cache** run — 0.173s per call, so **86.6s at
  500 titles** — because projecting from a cached run would promise 2 seconds and deliver ninety.
- A reader who wants "how long until I see the memo on a fresh machine" needs both numbers added,
  roughly 107s at 500 titles. Giving them separately with the boundary named is what makes that
  addition possible.

## Revisit when
The analysis stages approach the stated limit, or someone quotes a single blended figure in a
report — which would mean the boundary stopped being carried.
