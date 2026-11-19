# ADR-012: A co-directed film counts for both directors, and the film-level label is sorted

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team (Kwame unavailable — see Q6)

## Context
9 of 112 films have more than one credited director, and **TMDb returns co-directors in no fixed
order**: `/movie/603` (*The Matrix*) lists Lana then Lilly Wachowski, `/movie/605` (*The Matrix
Revolutions*) lists Lilly then Lana. The same is true of the Russo brothers on *Infinity War* and
*Endgame*. Taking the first row therefore credits the same partnership to different people on
different films.

## Decision
Carry a sorted partnership label on the film table (`director_names`, identical on all three Matrix
films), plus `n_directors` to mark the 9, plus a long table at one row per film per director. Every
per-director statistic is computed from the long table, never from the label.

## Alternatives considered
- **Take the first row** — one director per film, whichever arrives first. Loses because the
  attribution is arbitrary and looks authoritative.
- **Take the first alphabetically as "the" director** — deterministic, and still discards a real
  co-director's filmography.

## Consequences
- **Measured, and it decides who exists in the talent analysis.** With
  `talent.min_films_for_reliable = 3`:

  | Collapse rule | Directors clearing 3 films |
  |---|---|
  | First row | **11** of 61 |
  | Both credited *(chosen)* | **13** of 66 |

- The two lost under the first-row rule are **Lana and Lilly Wachowski** — a 3-film partnership
  split into one film each, so neither clears the threshold and a consistent directing team
  disappears entirely. They would not be reported as unreliable; they would not be reported at all.
- The chosen rule credits each director with the full performance of a film they shared, so a
  partnership's record is counted twice at the person level. That is the right error to make: the
  alternative silently deletes people, and the claim that talent is a reliable lever cannot be
  tested against a list that lost two of its most consistent names.
- Any recommendation naming a co-director must say the films were shared, which `n_directors` makes
  possible. Per-film statistics are unaffected either way.

## Revisit when
A shortlist recommends a co-director without the shared-film caveat, or a partnership's doubled
weight changes which names clear the reliability threshold.
