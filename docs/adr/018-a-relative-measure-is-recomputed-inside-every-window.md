# ADR-018: Recompute every relative measure inside the window it is reported for

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
Two of the three hit definitions are relative: `above_median` and `top_quartile` are defined against
a pool. The analysis reports two windows, all years and 2000 onward. Computing the flags once over
all 112 films and reusing them for the 71 modern films compares those films against a median set
partly by 1970s films, whose returns are inflated by inflation and re-release revenue (F10).

## Decision
The function that adds hit flags takes a frame and computes within it, and the KPI stage calls it
again for each window.

## Alternatives considered
- **Compute once over everything and reuse** — cheaper, and reads as consistency. Loses because it
  answers a question nobody asked, and nothing in the output would reveal it.
- **Drop the relative definitions and keep only the absolute threshold** — the absolute threshold on
  its own is nearly useless here: 92% of the list clears it (ADR-015).

## Consequences
- On this data, computing pool-wide instead of per window moves films across the "above median" line
  in the modern window, and in one direction only: modern films judged against a bar raised by older
  ones.
- A test pins the behaviour with a four-film case where the two methods disagree, because the bug
  produces no error and nothing in the output would show it.
- A reader who does want "above the all-years median" for a modern film can still compute it on the
  full table. The choice is explicit rather than inherited.

## Revisit when
A third window is added. The same rule applies, and the test should gain a case for it rather than
the code gaining a special case.
