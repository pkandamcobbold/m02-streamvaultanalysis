# ADR-015: Keep the hit threshold at break-even, and report all three hit definitions

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team (Kwame unavailable — see Q3)

## Context
`hit_roi_threshold` was set to 2.5 at the planning stage as a box-office break-even rule of thumb
and marked "to set after profiling". The profile shows **92% of the list clears it**, because the
list contains no film that lost money (F12). The hit rate therefore barely discriminates between any
two groups.

| Return threshold | Share of the list counting as a hit |
|---|---|
| 2.0 | 95% |
| **2.5** | **92%** |
| 4.0 | 71% |
| 5.0 | 59% |
| 8.0 | 31% |

## Decision
Keep 2.5 for its external justification and report `above_median` and `top_quartile` alongside it,
showing where the three disagree. `report_all_hit_definitions = true` makes the fragility visible
instead of hiding it behind one number; `hit_definition` selects which one the reports lead with.

## Alternatives considered
- **Keep 2.5 and report the hit rate as the headline** — a metric that 92% of the list clears cannot
  carry a recommendation.
- **Raise the threshold until the metric separates the groups** — the trap. Choosing a threshold
  because it makes the numbers interesting is fitting the measure to the desired answer, and any
  figure chosen that way cannot survive the question "why 5.0?".

## Consequences
- The hit rate is demoted from a headline metric to one of three, and the memo leads with medians
  and spread instead.
- 2.5 keeps an answer to "why that number?" — roughly where a theatrical release breaks even after
  the exhibitor split and prints-and-advertising.
- `min_budget_for_roi` stays at 1,000,000 and is **inactive this quarter**: the smallest budget on
  the list is 1,200,000, so no film is excluded for return instability. It is kept as a guard for a
  future list containing a genuinely small film.
- If 2.5 is too low for this catalog, the hit rate is uninformative — which is exactly what is
  reported, so the reader is not misled.

## Revisit when
A future list contains films that lost money. The hit rate then starts discriminating, and the
threshold deserves re-examination against that distribution rather than against a rule of thumb.
