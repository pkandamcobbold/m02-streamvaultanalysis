# ADR-026: Four stratified slices for the spot-check, not a random sample

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team (slices not named in the brief — see Q10)

## Context
The brief asks for a spot-check sampled across four slices without naming them, and the budget is 3
films per slice. A simple random sample of 12 from 112 would, with high probability, contain **none**
of the eight extreme-return films that drive the analysis and none of the shortlisted titles the memo
names.

## Decision
Stratify: put the budget where an error would hurt, and keep one unbiased slice as a control. The
four slices are **shortlisted** (an error here is an error in the answer), **flagged_extreme** (the
eight films from F11, *all* of them, because sampling the risky rows is not a check), **pre_2000**
(the distrusted window, where money is least comparable — ADR-013), and **random_control** (without
it the check only looks where problems are expected). The sample is seeded, so a reviewer re-running
it sees the same films and can tell a fixed fault from a new draw.

## Alternatives considered
- **A random sample** — unbiased, and would mostly check films nobody cares about.
- **Check only the influential rows** — cannot detect a fault that is uniform across the list.

## Consequences
- 15 films rather than the 12 the plan estimated, because taking all eight flagged films costs more
  than sampling three. Coverage is 13% of the list and 100% of the rows the recommendation leans on.
- The checks stage hard-fails if the control slice is ever missing, unless the pool was small enough
  to be sampled entirely.
- A stratified sample cannot support a statement about the error rate of the list *as a whole*; the
  control slice is three films, which is too few to estimate anything. So the report claims fidelity
  on the rows checked and does not extrapolate a rate. The alternative is an unbiased estimate of a
  number nobody asked for, computed by not checking the films that matter.

## Revisit when
The list grows enough that 3 films per slice is a smaller share than it is now, or a material
difference is found in the control slice — which would mean the fault is not where the strata expect.
