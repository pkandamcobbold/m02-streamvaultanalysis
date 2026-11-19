# ADR-019: Report medians and quartiles, with the mean shown beside them

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
Computed both ways, the two statistics disagree about the recommendation. Mean return: standalone
**10.48**, franchise 7.94. Median return: franchise **5.53**, standalone 5.00. The eight
extreme-return films (F11) are concentrated in the smaller group — 3 of 25 standalone films against
5 of 87 franchise films — so the standalone mean is pulled above the franchise mean while the typical
standalone film sits below the typical franchise film. This decision decides the answer.

## Decision
Report medians and quartiles, with the mean shown beside them so the disagreement is visible. Spread
is the interquartile range rather than the standard deviation, for the same reason: a standard
deviation inflated by a 70 times return says nothing about the typical gap between a good and a bad
film in the group.

## Alternatives considered
- **Report means**, the conventional default — would advise buying standalone hits on the strength of
  three films from 1975, 1966 and 1994.
- **Report means with the extremes winsorised** — rejected under ADR-016: clipping would delete 20%
  of the pre-2000 films and none of the modern ones.

## Consequences
- **It reverses the recommendation.** Under means the memo would recommend standalone hits, on the
  strength of *Jaws*, *The Good, the Bad and the Ugly* and *Pulp Fiction* — returns no current
  acquisition can replicate. Under medians it recommends franchise bundles. Both figures are
  published in the KPI table, and the memo discloses the reversal rather than footnoting it.
- The median discards information about upside, and upside is part of an acquisition case: a buyer
  who wants one spectacular title rather than a reliable slate is served better by the mean. That
  reader is given the maximum and the full shortlist rather than being argued with.
- What the median protects against is the likelier error: taking a 1970s outlier as evidence about a
  2027 licensing deal.

## Revisit when
The gap between the two statistics closes, or a future list's extremes are spread evenly across the
groups — at which point the mean stops being the misleading one.
