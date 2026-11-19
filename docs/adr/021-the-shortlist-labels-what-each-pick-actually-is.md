# ADR-021: The shortlist carries each pick's franchise status on the row

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
Under the default grouping, lone collection members count as standalone (ADR-010). The top five
"standalone" picks therefore include **Jaws** and **The Lion King**, both of which belong to a TMDb
collection whose other films are not on the candidate list.

## Decision
Keep them and carry `franchise_status` on every row of the shortlist, so the memo can name what each
pick is.

## Alternatives considered
- **Present them as standalones** — which the grouping says they are. Loses because calling *Jaws* a
  standalone without qualification is a sentence a board member could reasonably object to.
- **Drop them from the standalone shortlist** — chooses from 16 films rather than 25, making an
  already thin group (F7) thinner and excluding two of its strongest candidates for a reason that
  has nothing to do with whether they can be bought.

## Consequences
- 2 of 5 selected standalones are lone collection members. The shortlist table carries the status
  and the memo names it: a single film Kwame can license on its own is exactly what the standalone
  side of the brief means.
- The three true standalones among the picks are *The Good, the Bad and the Ugly*, *Pulp Fiction*
  and *Schindler's List*.
- Costs one column.

## Revisit when
Lone collection members make up most of the standalone shortlist. At that point the grouping, not
the label, is what needs revisiting.
