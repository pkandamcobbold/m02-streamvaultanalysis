# ADR-010: Three franchise categories, not two, with the threshold in settings

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team (Kwame unavailable — see Q2)

## Context
96 of 112 films belong to a TMDb collection, but 9 of those are the *only* film of their collection
on the candidate list. A collection with one film on offer is not a bundle anyone can sell. So the
data has three groups, not the two the brief names: 87 franchise, 9 lone collection members, 16 true
standalones (F7). This is the split the entire analysis rests on.

## Decision
Keep all three categories and decide the grouping at the KPI stage.
`franchise.min_members_on_list = 2` controls it, and the 9 lone members carry their own label so
they can be moved either way without recomputing anything.

## Alternatives considered
- **Franchise = belongs to any collection**, giving 96 against 16. The tempting option, and wrong:
  it counts a film as a bundle when there is no bundle to buy.
- **Franchise = at least 2 on the list, lone members folded into standalone**, giving 87 against 25.
  Defensible, and kept as the reported sensitivity rather than as the hidden default.

## Consequences
- Directly changes the central comparison's group sizes:

  | Definition | Franchise | Standalone |
  |---|---|---|
  | Any collection | 96 | 16 |
  | At least 2 on list, lone members to standalone | 87 | 25 |
  | Three groups *(chosen)* | 87 | 16, plus 9 reported separately |

- The headline is reported with lone members as standalone and a sensitivity row the other way,
  because moving 9 films out of a 16-film group changes it by 56%.
- If the 9 lone members really are franchise films Kwame could buy individually, excluding them
  understates the franchise group by 10% and overstates nothing. Treated as standalones instead, a
  16-film group becomes 25 and its median is pulled by films whose performance may owe everything
  to a franchise the list does not contain. The second error is worse, which is why the default
  keeps them visible.

## Revisit when
At 500 titles the lone-member group should shrink proportionally. If it does not, the list is being
assembled by picking single entries out of franchises, which is itself worth telling Kwame.
