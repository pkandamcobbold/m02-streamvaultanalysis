# ADR-006: Generate the memo from the measured results, and gate its publication

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Paapa Andam-Cobbold
- **Merged from:** ADR-014 (the memo is generated) and ADR-015 (the release gate — the improvement
  beyond the brief), 2026-11-20

## Context

Two decisions about the client-facing output, one about how it is produced and one about whether it
is produced at all.

**The memo is the one artefact a non-programmer reads**, and the one most likely to go stale. A
figure gets revised in the analysis, and the sentence quoting it does not. That drift is silent and
it is the worst possible place for it: a document going in front of a board with a number that
nothing in the pipeline still supports.

**And everything else in this project protects the analysis from being wrong.** Nothing protected
Adjoa from the analysis being wrong *and looking fine*. She reruns this every quarter, on her own
laptop, sometimes live in the meeting. The pipeline is deliberately built to carry on rather than
stop (ADR-003) — so a truncated input list, or a money column half missing, would still produce a
confident one-page recommendation with nothing on it to say otherwise. The gate is the improvement
beyond the brief.

## Decision

**The whole memo is generated**, with the judgement encoded as rules over the measured results. Not
just the figures — the conclusions too. Series films lead on typical return, the weaker end and the
hit rate in both windows, therefore recommend franchise-first. The consistency advantage does not
survive after 2000, therefore say so rather than footnote it. If a headline measure ever flips
between the windows, the flip replaces the recommendation as the first line. Change the data and the
rules produce a different memo.

**Four checks run before the memo is written.** If any fails, **no memo and no shortlist are
produced**: the run stops and prints which check failed, in language that says what to do next,
including the one setting that overrides it. The checks are: every row of the source file accounted
for; enough films left to compare the two groups; money data complete enough to rank on; and the
live re-check has not changed the answer.

## Alternatives considered

### Alternative A: Write the memo by hand from the final numbers

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

### Alternative C: A sensitivity panel instead of a gate

- **How it would work:** One table showing whether the recommendation survives each judgement call
  being flipped.
- **Why it is attractive:** It directly arms Kwame against the challenge he is going to get in the
  room, which is a real need.
- **Why rejected:** Already built, at the validate stage. And it assumes the run was sound in the
  first place — it tells you whether your assumptions matter, not whether your input was intact.

### Alternative D: A run-over-run diff instead of a gate

- **How it would work:** Each quarter, show Adjoa what changed since last time: new titles, revised
  figures, shortlist movements.
- **Why it is attractive:** It serves the quarterly rerun better than anything else on this list,
  and it is the thing she would actually use most.
- **Why rejected:** It needs two quarters of history to say anything. Next quarter, not this one.

### Alternative E: A bundle dead-weight score instead of a gate

- **How it would work:** For each franchise, the share of its films below the standalone median — a
  negotiating number.
- **Why it is attractive:** It is immediately usable at the table: "you are asking us to pay for
  three weak films."
- **Why rejected:** It is a refinement of the answer rather than a protection against the answer
  being wrong. Valuable, and not the gap.

## Consequences

- **What this buys:** Re-running the pipeline republishes the memo, so it cannot quote a figure the
  data no longer supports. The caveats are not optional either: tests assert that the mean-reversal
  disclosure (F-03), the thin standalone group (F-04), the era problem (F-05), the absence of any
  failure on the list (F-01) and the missing licensing prices all appear, and that no dollar figure
  is ever named — an edit that quietly drops a caveat fails the test suite. On top of that, the gate
  is the only check in the project whose failure mode is "the board was misled" rather than "a stage
  crashed": the assertions throughout the pipeline protect each step from the one before, and this
  protects the client-facing output from the whole pipeline.
- **What this costs:** Generated prose is stiffer than written prose, and a rule-based
  recommendation cannot exercise judgement the rules do not encode — mitigated by keeping the rules
  few and explicit, and by the fact that a human still chooses what the rules are. The gate can also
  block a run Adjoa believes is fine, handled two ways: the checks are blunt, so each one failing
  makes the memo actively misleading rather than merely imperfect, and the failure message names the
  setting that overrides it, so skipping the gate is a decision somebody makes and can be asked
  about rather than something that happens silently.
- **What it costs the client if I am wrong:** A memo that reads beautifully and quotes last
  quarter's number, with no mechanism that would catch it — which is why the generation is a rule
  rather than a habit. And a quarter where Adjoa cannot publish and has to override the gate under
  time pressure; against that, a quarter where she presents a confident number built on 40 films
  instead of 112 and nobody in the room can tell.
- **What would make me revisit this:** The open item below being closed, or a quarter where one of
  the remaining hard-coded claims turns out to be false — whichever comes first; one of the three
  already did, which is why the item is still open rather than accepted. For the gate: it blocking a
  run that turns out to have been sound, or the minimum film count ceasing to be a meaningful floor
  as the list grows.

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

The generation mechanism survives and gets more valuable every quarter, because the gap between when
a figure was written and when it is read keeps growing. The open item is the part that does not
survive: left alone, those two sentences will eventually be wrong and confident at the same time.

Three of the gate's four checks are proportions or reconciliations, so they need no re-tuning as the
list grows. The minimum film count is an absolute floor and should be raised if the standalone group
stays as thin as it is now (F-04). The design constraint that survives is the count: four. A gate
with twenty conditions is one that somebody permanently disables the first time it fires over
something cosmetic, and then it protects nothing at all.
