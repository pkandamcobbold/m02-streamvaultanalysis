# ADR-016: Flag and classify extremes, never clip them

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
Eight films have a return above 20 times budget, topping out at 70.5 times (*Star Wars*). **All
eight are pre-2000**, from 1966 to 1994 (F11).

## Decision
Keep every value and flag it with a verdict and a sentence saying why. Four verdicts: `error`,
`real_extreme`, `unreliable`, `check`. All eight extremes are `real_extreme` and stay in every
metric.

## Alternatives considered
- **Winsorise at a percentile** — fires only on one era, so it is not hygiene.
- **Drop them as implausible** — deletes the most informative rows on the list.

## Consequences
- Either rejected option would delete **8 of 41 pre-2000 films (20%) and 0 of 71 modern films**. An
  outlier treatment that only ever fires on one era is a thumb on the scale of the comparison
  Finance is already sceptical about, and it would make their window look worse while looking like
  routine cleaning.
- It would also delete the back-catalog case itself: a 70 times return on a cheap 1977 film is the
  evidence, not noise.
- Instead, the reports use medians, which resist extremes without removing them, with counts beside
  every figure.
- If one of the eight is a bad figure, it inflates the pre-2000 picture. That is why all eight are
  forced into the live spot-check by name rather than trusted;
  `spotcheck.always_include_flagged` exists for this. The reverse error is larger and leaves no
  trace: a clipped value looks exactly like a value that was never there.

## Revisit when
The spot-check returns a material difference on any of the eight, or a future list has extremes in
both eras — at which point clipping stops being era-selective and the argument changes.
