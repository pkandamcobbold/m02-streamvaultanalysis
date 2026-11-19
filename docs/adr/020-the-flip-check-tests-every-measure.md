# ADR-020: The flip check tests every measure, not just the median

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
The brief asks whether the recommendation changes in the post-2000 window. The planned check
compared one number per window. But the claim being tested — that franchise bundles are the *safer*
buy — is a claim about three measures: the floor, the spread and the hit rate. Checking only the
median would have reported "no flip" while one half of the claim had in fact reversed.

## Decision
Check each measure and report them separately. Four measures, each with its own direction
convention — and the interquartile range is explicitly marked "lower is better", because a tighter
group is the safer buy and reading it like a median inverts the answer.

## Alternatives considered
- **One check on the median** — would have missed the one flip that exists.
- **A single composite score combining them** — needs weights nobody has a basis to choose, and
  would hide exactly the disagreement worth reporting.

## Consequences
- It found one. Franchise films lead on median, floor and hit rate in both windows, and the
  **spread advantage flips** (F15): interquartile range 4.39 against 11.71 across all years, 2.47
  against 2.297 after 2000.
- Four measures mean four chances to see a flip that is really noise, and this one is: a 0.17 margin
  on 12 films. Mitigated by reporting the margin and the count beside the flip rather than only the
  verdict, so the finding reads "the advantage disappears" and not "standalones are now safer".
- A flip on a headline measure moves to the memo's first line; a flip on spread gets its own
  paragraph.

## Revisit when
A flip appears on median, floor or hit rate. That is a different memo, and the rule that promotes it
to the first line is already in place.
