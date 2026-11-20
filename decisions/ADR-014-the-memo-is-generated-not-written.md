# ADR-014: Generate the memo from the measured results rather than writing it

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Paapa Andam-Cobbold

## Context

The memo is the one artefact a non-programmer reads, and the one most likely to go stale. A figure
gets revised in the analysis, and the sentence quoting it does not.

That drift is silent and it is the worst possible place for it: a document going in front of a board
with a number that nothing in the pipeline still supports.

## Decision

The whole document is generated, with the judgement encoded as rules over the measured results. Not
just the figures — the conclusions too.

Series films lead on typical return, the weaker end and the hit rate in both windows, therefore
recommend franchise-first. The consistency advantage does not survive after 2000, therefore say so
rather than footnote it. If a headline measure ever flips between the windows, the flip replaces the
recommendation as the first line. Change the data and the rules produce a different memo.

## Alternatives considered

### Alternative A: Write it by hand from the final numbers

- **How it would work:** Read the artefacts, write a page.
- **Why it is attractive:** Far better prose. A person can weigh things a rule cannot, and the memo
  is a persuasive document as much as a factual one.
- **Why rejected:** It is exactly the drift this record exists to prevent. Next quarter the numbers
  change and the sentences do not, and nothing catches it.

### Alternative B: Generate the figures and hand-write the prose around them

- **How it would work:** Template the document with computed values substituted in.
- **Why it is attractive:** It gets most of the protection with most of the fluency, and it is what
  most reporting does.
- **Why rejected:** The prose then carries claims a rerun cannot falsify. "Series films are the
  safer buy" would survive a quarter in which they were not.

## Consequences

- **What this buys:** Re-running the pipeline republishes the memo, so it cannot quote a figure the
  data no longer supports. The caveats are not optional either: tests assert that the
  mean-reversal disclosure (F-03), the thin standalone group (F-04), the era problem (F-05), the absence
  of any failure on the list (F-01) and the missing licensing prices all appear, and that no dollar
  figure is ever named. An edit that quietly drops a caveat fails the test suite.
- **What this costs:** Generated prose is stiffer than written prose, and a rule-based
  recommendation cannot exercise judgement the rules do not encode. Mitigated by keeping the rules
  few and explicit, and by the fact that a human still chooses what the rules are.
- **What it costs the client if I am wrong:** A memo that reads beautifully and quotes last
  quarter's number. There is no mechanism that would catch that, which is why this is a rule rather
  than a habit.
- **What would make me revisit this:** The open item below being closed, or a quarter where one of
  the remaining hard-coded claims turns out to be false — whichever comes first. One of the three
  already did turn out to be false, which is why the item is still open rather than accepted.

**Open item.** Two quantitative claims in the generated memo are hard-coded English rather than
computed: "three exceptional films from the 1960s, 70s and 90s" and "nearly four in five
candidates". Each is true this quarter and could be false next quarter while the pipeline reports
success — which is precisely the drift this record claims to prevent. Tracked as S-08.

There were three. The position figure was computed on 2026-11-20, and the exercise justified this
record outright: the prose said later instalments return about a seventh less, and the computed
answer under the only reading that compares like with like is that they return *more* (M7, F-08).
The memo had been carrying a discount argument that the data does not support, and no test could
have caught it while the sentence was English.

**The recommendation lives in the memo's subject line.** The house template fixes the section
order — found, built, recommend, could not stand behind — so the recommendation cannot be the body's
first line and still obey it. A subject line is where a memo puts its conclusion anyway, and it is
the first thing read, so both constraints hold at once. The rule above survives intact: a flip
between the two windows rewrites the subject rather than being footnoted.

## What this survives

The mechanism survives and gets more valuable every quarter, because the gap between when a figure
was written and when it is read keeps growing. The open item is the part that does not survive: left
alone, those three sentences will eventually be wrong and confident at the same time.
