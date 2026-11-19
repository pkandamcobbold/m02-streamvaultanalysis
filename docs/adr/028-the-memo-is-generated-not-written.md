# ADR-028: The memo is generated from the measured results, not written by hand

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
The memo is the one artefact a non-programmer reads, and the one most likely to drift: a figure gets
revised in the analysis and the sentence quoting it does not.

## Decision
Generate the whole document, with the judgement encoded as rules over the measured results. The
recommendation follows from stated conditions: franchise leads on median, floor and hit rate in both
windows, therefore recommend franchise-first; the spread advantage does not survive after 2000,
therefore say so; a headline measure flips, therefore the flip becomes the first line instead of the
recommendation.

## Alternatives considered
- **Write it by hand from the final numbers** — the drift this record exists to prevent.
- **Generate the figures and hand-write the prose around them** — the prose then carries claims the
  rerun cannot falsify.

## Consequences
- Re-running the pipeline republishes the memo, so it cannot quote a figure the data no longer
  supports.
- The caveats are not optional either: tests assert that the mean-reversal disclosure (F14), the thin
  standalone group (F7), the era problem (F10), the absence of any failure on the list (F12) and the
  missing licensing prices all appear, and that no dollar price is ever named. An edit that quietly
  drops a caveat fails the suite.
- Generated prose is less fluent than written prose, and a rule-based recommendation cannot exercise
  judgement the rules do not encode. Mitigated by keeping the rules few and the conditions explicit,
  and by the fact that a human still chooses what the rules are.
- **Open item:** three quantitative claims in the generated memo are hard-coded English rather than
  computed — "three exceptional films from the 1960s, 70s and 90s", "roughly a seventh less than an
  opener" (see ADR-022) and "nearly four in five candidates". Each is true of this quarter and could
  be false next quarter while the pipeline reports success, which is exactly the drift this record
  claims to prevent.

## Revisit when
The open item above is closed by computing those three figures, or a quarter arrives where one of
them is wrong — whichever comes first.
