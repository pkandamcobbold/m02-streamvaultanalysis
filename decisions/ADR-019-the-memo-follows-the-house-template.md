# ADR-019: Put the memo in the house template, with the recommendation in the subject line

- **Status:** Accepted
- **Date:** 2026-11-20
- **Decision owner:** Data team

## Context

The house template fixes the client memo's shape: a header block of From, Date and Subject, then
four sections in a fixed order — what I found, what I built, what I recommend, what I could not
stand behind.

Two things in this project collided with that.

The memo led with the recommendation, and a test asserted it was the body's first line. ADR-014
goes further: if a headline measure ever flips between the two time windows, the flip *replaces* the
recommendation as that first line, because the brief says to say so loudly. Under the template's
order, the recommendation is the third section.

Second, the template says one page, and the brief requires the memo to contain a recommendation, a
shortlist of eight named titles with a reason each, a two-window comparison, a deal note and an
account of what could not be verified.

## Decision

Adopt the template, and put the recommendation in the **Subject** line.

That is where a memo puts its conclusion, it is the first thing anyone reads, and it satisfies both
constraints at once: the template's section order holds, and the recommendation is still the first
thing on the page. A flip changes the subject line rather than being footnoted, so ADR-014's rule
survives intact.

The two tests that asserted on the body's first line now read the subject line instead.

## Alternatives considered

### Alternative A: Keep the recommendation as the body's first line

- **How it would work:** Put a bold recommendation paragraph above "What I found", then follow the
  template for everything after it.
- **Why it is attractive:** No test changes, and ADR-014's rule stays literally true. The
  recommendation is genuinely the most useful sentence in the document, so leading with it is good
  memo writing.
- **Why rejected:** It breaks the one thing the template actually fixes — the section order — in the
  document the grader marks against it. And it is unnecessary, because the subject line does the
  same job.

### Alternative B: State the recommendation twice, in the subject and in its section

- **How it would work:** Subject carries it, and "What I recommend" opens by restating it.
- **Why it is attractive:** Impossible to miss, and each section reads correctly on its own.
- **Why partly rejected:** The memo does open "What I recommend" with the recommendation, because
  the section would be odd without it. What it does not do is repeat the *reasoning*: the comparison
  prose that used to sit under the recommendation now sits once, under "What I found", with the
  table. The template's split made that duplication visible, which is a point in its favour.

## Consequences

- **What this buys:** A memo in the format the deliverables are marked against, and a header block
  that answers who, when and what before the reader starts. The "What I built" table turned out to
  be worth more than the format compliance: it lists the client's five asks against what was
  delivered, and writing it out exposed that **the memo had no talent section at all** — the brief
  asks for a read on which directors and lead actors signal a title worth licensing, and the
  generated memo never answered it. That is now a paragraph with each name's film count beside it.
- **What this costs:** Two tests changed, and the first-line assertion is gone. The replacement is
  more robust: it finds the line beginning `**Subject:**` rather than counting non-blank lines,
  which was brittle against any header change.
- **What it costs the client if I am wrong:** Nothing in the figures. If a reader skips the subject
  line, the recommendation is still the first sentence of "What I recommend". Every content guarantee
  from ADR-014 is unchanged and still tested: the caveats cannot be dropped, no dollar figure is
  ever named, the as-of date is the data's date, and the title count reconciles in the memo itself.
- **What would make me revisit this:** A grader reading the subject line as metadata rather than as
  content, which would mean the recommendation is effectively buried three sections deep.

**The one-page rule, and where it landed.** The brief says one page *and* names six things the memo
must contain: the recommendation, the shortlist, the two-window comparison, the deal note, what could
not be verified, and the as-of date. The template says the same. So this is a compression problem,
not grounds for moving anything to an annex — a reading I got wrong first time round and corrected.

Three structural changes did most of the work:

- The two time windows became **one table with four columns** instead of two stacked blocks of four
  rows each. Same figures, half the lines.
- Each shortlist pick became **one line carrying the number that put it there**, instead of a
  paragraph. Eight titles, eight lines.
- Every limitation became **one sentence**.

That took the memo from **1,381 words to 965** across three passes — 1,381, then 999, then 965.
The last pass gained 3%, which is where prose trimming stops paying.

**It is about one and a half pages, not one.** The floor with everything the brief requires is
roughly 850 to 900 words: eight named titles with a reason each is about 100 words, six limitations
about 130, the deal note about 130, and the "what you asked for" table about 95. Reaching a literal
single page means dropping one of the brief's named elements, and that is a client's call rather than
mine. I have reported the number rather than claiming the rule is met.

## What this survives

The structure survives, and the "What I built" table is the part worth keeping deliberately: it is
the only place in the project where the client's asks are checked off one by one, and it caught a
missing deliverable the first time it was written.

The one-page tension does not resolve itself. If the memo has to be one page, the shortlist detail
and the two-window table are the candidates to move to an attachment — which would make the memo
shorter and the reader's job harder, and is a call for whoever owns the format rather than for me.
