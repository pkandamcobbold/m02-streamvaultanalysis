# ADR-024: Measure the 500-title projection per stage rather than multiplying the total

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
The obvious projection is measured time times 500/112. That assumes every stage scales linearly in
films, and at least one plainly does not: shaping the nested JSON processes **credit rows**, of which
this list has 223 per film, while the small stages are dominated by fixed costs at this size.

## Decision
Fit a scaling exponent per stage from re-runs over subsets of the **actual** payloads, and report
the exponent beside the projection. Run a discarded warm-up pass first, time each size several times
and keep the minimum.

## Alternatives considered
- **Multiply by the ratio of film counts** — assumes the thing the measurement exists to test.
- **Generate a synthetic 500-film dataset and run it** — a synthetic film carries a made-up cast
  size, which would make the shaping stage look linear in films when it is linear in credit rows:
  the exact distinction the projection turns on.

## Consequences
- Fitted projection **3.6s** at 500 titles; all-linear assumption **4.5s**; limit 10s. Both are
  reported, so the conclusion holds whether or not the fit is right.
- That matters because the sub-linear exponents — around 0.05 to 0.1 for joining, profiling and
  cleaning — are extrapolated five-fold beyond the measured range, and fixed costs will stop
  dominating somewhere before 500.
- Shaping is the stage to watch: 64% of the budget today, and the only one that measures as linear.
- The fit rests on four sample sizes and sub-second timings, which are noisy: exponents move by a few
  tenths between runs. That is why the all-linear bound is published beside it, and why the
  conclusion is stated as "comfortably inside the limit under either assumption" rather than as a
  point estimate.
- The first attempt produced negative exponents, which would have projected the stages getting
  faster as the catalog grows, and was quoted nowhere because the exponents were read (F17). A
  negative fit now falls back to linear and says so in the artefact.

## Revisit when
Any stage's fitted exponent exceeds 1.2, or the measured range reaches a size where fixed costs no
longer dominate — at which point the extrapolation is no longer five-fold and the fit can be trusted
further.
