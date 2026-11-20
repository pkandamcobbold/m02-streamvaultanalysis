# ADR-009: Cleaning adds columns; a film is excluded from a metric, never from the analysis

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Data team

## Context

Some films fail some checks. The question is what "cleaning" then means.

A film with no usable budget cannot go into a return figure. But it is still a real film, with a
real audience rating, a real director and a real place in a franchise. Dropping it from the analysis
because one field is unusable throws away four things to fix one.

This decision governs every number in the project, which is why it is written down even though its
measured effect this quarter is zero.

## Decision

I keep every row and add columns saying what each film is eligible for. Whether a film is usable in
the money figures, what its money quality is, whether its rating has enough votes behind it — all
columns, not filters. The stage asserts that cleaning did not change the row count.

The return figure exists exactly where the film is eligible and is missing everywhere else, so
nothing downstream can average a ratio that was never valid.

## Alternatives considered

### Alternative A: Drop the failing rows and analyse what is left

- **How it would work:** Filter out films with unusable fields before computing anything.
- **Why it is attractive:** It is the obvious reading of "clean the data", and every figure
  afterwards is computed on rows that are known good. No flags to respect.
- **Why rejected:** Each metric would quietly carry a different denominator. The memo says "112
  films", and halfway down the page that would stop being true without anything saying so.

### Alternative B: Fill in the missing values

- **How it would work:** Estimate a budget for the films that lack one — from the median, from
  similar films, from the revenue.
- **Why it is attractive:** It keeps every film in every metric, so the denominators stay honest
  and nothing is lost.
- **Why rejected:** An estimated budget flows into the return figure and becomes indistinguishable
  from a measured one. Kwame would be making a $14M decision partly on numbers I invented, with no
  way to tell which.

## Consequences

- **What this buys:** Denominators that stay true, and exclusions that are traceable. "This film was
  dropped" becomes "this film was dropped by this setting, which you can change" — an exclusion
  nobody can trace to a switch is indistinguishable from a bug.
- **What this costs:** Vigilance. Every aggregation has to respect the flags, and a reader filtering
  the table themselves could compute a figure over films that were never eligible. Mitigated by
  making the return *missing* rather than zero, so that mistake fails or returns nothing instead of
  silently averaging.
- **What it costs the client if I am wrong:** Nothing measurable this quarter — no film is excluded
  from anything, because no film has an unusable budget or box-office figure. What it prevents is
  the point.
- **What would make me revisit this:** A quarter where films genuinely do fail the money checks.
  The flags would start excluding rows, and at that point the sensitivity table rather than this
  record becomes the evidence that the choice is safe.

## What this survives

This is the decision I would most expect to be tested next year. A messier list means real
exclusions, and the design only proves its worth when the flags start firing. The thing that has to
survive is the discipline, not the code: every new aggregation has to respect the eligibility
columns, and nothing in the language enforces that.
