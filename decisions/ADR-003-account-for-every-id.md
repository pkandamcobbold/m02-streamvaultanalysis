# ADR-003: Account for every id — reconcile claims, never crash on them, and exclude from a metric rather than from the analysis

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Paapa Andam-Cobbold
- **Merged from:** ADR-004 (the brief's count is a claim), ADR-005 (the foreign identifier),
  ADR-006 (a 404 is a finding) and ADR-009 (cleaning adds flags), 2026-11-20

> **These four are the ADRs that pass the Decision-notes test** — for each one you can say what the
> recommendation looks like under the rejected alternative. They are indexed from
> [`../reports/decision_notes.md`](../reports/decision_notes.md) as well as from the ADR list, and
> they are kept together here because they are one argument: **every row of the input gets a verdict
> and a reason, and nothing leaves the count silently.**

## Context

Four places where a row could have disappeared without anyone noticing.

**The brief's count.** It says 127 candidate titles. The file has 128 lines: a header and 127 rows.
They agree, this quarter. Next year's list is expected to be around 500 titles, and Adjoa will be
running the pipeline herself, sometimes live in a meeting, without me there to explain why it
stopped.

**A foreign identifier.** Row 95 holds `tt0468569` — an identifier from a different film catalogue,
in a column that is supposed to hold TMDb ids. I looked it up rather than guessing. It resolves to
*The Dark Knight*, released July 2008, and that film is **already on the candidate list twice**, at
rows 2 and 91.

**Five ids that do not exist.** `8471293`, `9412887`, `8471294`, `9412888` and `7733901`, at rows
18, 35, 73, 93 and 99. They do not cluster by position. They cluster perfectly by id: every one of
the 112 ids that worked is **301,528 or below**, every dead id is **7,733,901 or above**. No overlap
at all — a gap of twenty-five fold — and two of the five are consecutive pairs.

**Films that fail a check.** A film with no usable budget cannot go into a return figure. But it is
still a real film, with a real audience rating, a real director and a real place in a franchise.
Dropping it because one field is unusable throws away four things to fix one.

## Decision

**The expected count lives in the settings file.** If the file disagrees with it, the pipeline
prints a note, records it as a finding, and carries on — reconciling against what the file actually
holds rather than against what the brief claimed.

**Foreign identifiers are resolved by a procedure with three outcomes**, not a one-off fix, because
next quarter's list comes from the same three desks. A row that resolves to nothing stays unusable.
A row that resolves to a film already on the list is recorded as a duplicate in a second identifier
system and excluded. A row that resolves to a film *not* otherwise on the list is recovered,
fetched, and forced into the spot-check sample — its provenance is unlike every other row, so it
deserves checking. Row 95 took the middle path.

**A "not found" is an answer**, so it is recorded and the run moves on: the id goes on the ledger
with its reason, the response is cached like any other so reruns do not ask again, and it is
deliberately excluded from the retry policy. Then the *pattern* is treated as a finding rather than
a count, because five dead ids is a sentence and five dead ids that all sit above seven million is
evidence.

**Cleaning adds columns rather than removing rows.** Whether a film is usable in the money figures,
what its money quality is, whether its rating has enough votes behind it — all columns, not filters.
The stage asserts that cleaning did not change the row count. The return figure exists exactly where
the film is eligible and is missing everywhere else, so nothing downstream can average a ratio that
was never valid.

## Alternatives considered

### Alternative A: Assert the count is exactly 127

- **How it would work:** Check the row count on startup and stop the run if it differs.
- **Why it is attractive:** It catches a truncated file immediately, which is a real failure mode
  when a list is assembled by hand from three sources. It is also the kind of check that reads as
  rigorous.
- **Why rejected:** It would stop Adjoa's run for being *correct* about a new list size, in a
  quarter when nobody remembers where 127 came from. The failure would look like a bug in the
  pipeline rather than a change in the input, and she would be debugging it in front of the board.

### Alternative B: Drop the foreign identifier as unparseable

- **How it would work:** Classify it as a bad value, like the placeholders and the blank row, and
  move on.
- **Why it is attractive:** It is consistent with how every other unusable value is handled, and it
  costs no API call.
- **Why rejected:** It never asks what the row was. It would have reached the right outcome — the
  film is excluded either way — for the wrong reason, and it would have hidden the fact that this
  film is on the list three times.

### Alternative C: Resolve the foreign identifier and add the film

- **How it would work:** Look it up, find a valid film, fetch it, include it.
- **Why it is attractive:** This is the obvious fix, and it is what "recover what you can" would
  suggest. It also looks like diligence: a row nobody else would have salvaged.
- **Why rejected:** It would have put **three copies of one film** into every figure. Worse, *The
  Dark Knight* is a franchise entry, so all three copies would land on the franchise side of the
  central comparison — inflating the franchise median return, the franchise hit rate, and any talent
  figure touching Nolan or Bale.

### Alternative D: Retry the dead ids

- **How it would work:** Put "not found" in the retry list alongside the server errors and the rate
  limits, on the theory that the fetch might have been at fault.
- **Why it is attractive:** It is the defensive default, and it costs nothing to type.
- **Why rejected:** It is slower and it is rude to a shared service, for an answer that will not
  change. A missing film is not a transient failure.

### Alternative E: Recover the dead ids by searching for the titles

- **How it would work:** Search the catalogue by name and match the results back to the list.
- **Why it is attractive:** It would recover real titles rather than writing off five rows, and
  recovering data generally beats losing it.
- **Why rejected:** There is no title to search for. The list is ids and nothing else, and a deleted
  entry leaves nothing behind to search with.

### Alternative F: Drop the failing rows and analyse what is left

- **How it would work:** Filter out films with unusable fields before computing anything.
- **Why it is attractive:** It is the obvious reading of "clean the data", and every figure
  afterwards is computed on rows that are known good. No flags to respect.
- **Why rejected:** Each metric would quietly carry a different denominator. The memo says "112
  films", and halfway down the page that would stop being true without anything saying so.

### Alternative G: Fill in the missing values

- **How it would work:** Estimate a budget for the films that lack one — from the median, from
  similar films, from the revenue.
- **Why it is attractive:** It keeps every film in every metric, so the denominators stay honest
  and nothing is lost.
- **Why rejected:** An estimated budget flows into the return figure and becomes indistinguishable
  from a measured one. Kwame would be making a $14M decision partly on numbers I invented, with no
  way to tell which.

## Consequences

- **What this buys:** A pipeline that keeps working when the input legitimately changes, which it is
  expected to do substantially within a year. An analysed pool unchanged at 112 films, with the
  central comparison not quietly weighted toward one group — the foreign identifier is the one place
  in this data where the obvious action and the correct action differ, which is the whole reason it
  is written down. A reason recorded for each of the five dead ids and an explanation of what they
  probably were: ids are issued in order, so something in the 7-to-9 million range was created far
  more recently than any genuine back-catalogue film's entry would have been, and the consecutive
  pairs suggest entries created one after another and later removed. On that evidence those five
  were probably never back-catalogue films, which makes losing them **less** damaging to the
  comparison than losing five random titles. And denominators that stay true, with exclusions that
  are traceable: "this film was dropped" becomes "this film was dropped by this setting, which you
  can change", because an exclusion nobody can trace to a switch is indistinguishable from a bug.
- **What this costs:** The opposite risk on the count — a list that silently shrinks would not stop
  the run, so it has to be caught by someone reading the note; both behaviours are pinned by tests,
  so neither can be lost by accident. One API call to a lookup endpoint and a branch of logic that
  does nothing in a clean quarter. Five fewer candidates and an inference I cannot prove. And
  vigilance: every aggregation has to respect the eligibility flags, and a reader filtering the
  table themselves could compute a figure over films that were never eligible — mitigated by making
  the return *missing* rather than zero, so that mistake fails or returns nothing instead of
  silently averaging.
- **What it costs the client if I am wrong:** A quarter's recommendation computed on a truncated
  list, with the note printed and nobody reading it — which is why the release gate also checks that
  every row of the source file is accounted for (ADR-006): a printed note is advisory, and the gate
  is not. If the foreign identifier were misidentified, one title would be missing from a pool of
  112, a 0.9% reduction; it is not misidentified, the response is cached and names the film and its
  release date, and against the alternative error — tripling a film's weight in the comparison the
  whole decision rests on — this is the smaller mistake by a wide margin. If the five dead ids were
  real back-catalogue titles, the loss might fall unevenly on older films or on franchises and I
  would have no way to know; because nothing is left to identify them, that cannot be tested in
  either direction, so "probably never back-catalogue films" is an inference from the id range, not
  a check, and the memo says so. On the flags: nothing measurable this quarter, because no film has
  an unusable budget or box-office figure. What it prevents is the point.
- **What would make me revisit this:** A run reporting a count mismatch that nobody acts on — that
  means the note is not loud enough and the check belongs entirely to the gate. A future list
  carrying foreign identifiers in volume: one row is a judgement call, thirty is a problem with how
  the list is assembled and belongs in the data contract as something to escalate. Dead ids
  appearing *inside* the live range, which would mean genuine titles are being lost — a different
  finding with a different cost. And a quarter where films genuinely do fail the money checks: the
  flags would start excluding rows, and at that point the sensitivity table rather than this record
  becomes the evidence that the choice is safe.

## What this survives

The count check is one of the few decisions made specifically *for* the 500-title run rather than
despite it; the number it checks against is a setting, so the only maintenance is editing one line
when the list grows. The foreign-identifier procedure survives while that particular row does not
recur — at 500 titles the chance of a foreign identifier rises, and so does the chance one resolves
to a film genuinely not on the list, the third outcome that has never yet fired and is implemented
and tested anyway. The dead-id handling survives unchanged, while the inference needs re-testing
every quarter: the id-range comparison is two numbers and is the cheapest way to do it. The flags
are the decision I would most expect to be tested next year — a messier list means real exclusions,
and the design only proves its worth when the flags start firing. What has to survive there is the
discipline, not the code: every new aggregation has to respect the eligibility columns, and nothing
in the language enforces that.
