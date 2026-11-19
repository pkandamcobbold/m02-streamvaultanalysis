# ADR-017: Cleaning adds flags; exclusion is per metric, never a dropped row

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team (Kwame unavailable — see Q4)

## Context
Some films fail some checks. The question is what "cleaning" then means. A film with no usable
budget cannot enter a return figure, but it is still a real film with a real rating, a real director
and a real franchise status. This decision governs every number in the project.

## Decision
Keep every row and add columns saying what each film is eligible for. `in_money_metrics`,
`money_quality` and `rating_reliable` are columns, not filters, and the stage hard-asserts that
cleaning did not change the row count. Return exists exactly where `in_money_metrics` is true and is
missing everywhere else, so nothing downstream can average a ratio that was never valid.

## Alternatives considered
- **Drop failing rows and analyse what is left** — each metric would quietly carry a different
  denominator, and the memo's "112 films" would stop being true halfway down the page.
- **Impute the missing values** — an imputed budget flows into the return figure and is
  indistinguishable from a measured one.

## Consequences
- No film is excluded from anything this quarter, so the measured impact is zero. The impact it
  *prevents* is the point.
- Every exclusion is traceable to the setting responsible, so "this film was dropped" becomes "this
  film was dropped by `performance.treat_zero_money_as_missing`, which you can flip". An exclusion
  nobody can trace to a switch is indistinguishable from a bug.
- It costs vigilance: every aggregation must respect the flags, and a reader who filters the table
  themselves could compute a figure over films that were never eligible. Mitigated by making the
  return missing rather than zero, so the mistake raises or returns missing rather than silently
  averaging.

## Revisit when
A quarter arrives where films genuinely do fail the money checks. The flags then start excluding
rows, and the sensitivity table — not this record — becomes the evidence that the choice is safe.
