# ADR-013: Compare money within a time window, never across one

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team (Finance challenge expected — see Q5)

## Context
Budget and revenue are nominal. Median budget is 5.0 times higher post-2000, median revenue only
2.3 times higher, so median return appears to halve across the boundary: 9.54 pre-2000 against 4.92
after. And an old film's revenue is lifetime revenue: *Star Wars* was re-released in 1978, 1981 and
1997, so its numerator accumulates later, larger dollars against a 1977 denominator (F10).

## Decision
Report each window separately and never compare a level across the boundary, alongside rank-based
measures — medians and quartile positions rather than dollar levels — which are scale-free. No
cross-window ratio appears anywhere in the memo.

## Alternatives considered
- **Pool all years and report one set of figures** — the 41 pre-2000 films would raise the apparent
  return of the whole catalog and, because 20 of those 41 are franchise entries from Star Wars,
  Indiana Jones and The Godfather, would specifically flatter the franchise side.
- **Adjust to constant dollars with an external CPI series** — needs data the brief does not
  provide, adds a dependency to a pipeline that must run from a clean clone, and **would not fix
  the problem**: deflating a lifetime revenue figure by the release-year CPI is still wrong, because
  the revenue was not all earned in the release year.

## Consequences
- This is why the two windows exist at all. Each window is internally comparable.
- If inflation and re-release effects are weaker than argued, nothing is lost: both windows are
  reported regardless, and the reader can compare them while being told why that comparison is
  unsafe.
- The opposite error produces a confident sentence — "the cheapest films to license return the
  most" — that is substantially an artefact of measuring 1970s costs against 2020s receipts.

## Revisit when
The candidate list spans more eras, which it will as the back catalog grows. The effect gets larger,
not smaller, at 500 titles.
