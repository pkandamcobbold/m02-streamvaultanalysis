# ADR-011: Measure how each stage scales rather than multiplying the total

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Paapa Andam-Cobbold

## Context

The brief asks how long this will take at around 500 titles. The obvious answer is the measured time
times 500 over 112.

That assumes every stage gets slower in proportion to the number of films, and at least one plainly
does not. Shaping the responses processes **credit rows**, and this list averages 223 of them per
film. The smaller stages are the opposite problem: at 112 films they are dominated by fixed costs
that will not grow at all.

## Decision

I re-run the analysis stages over subsets of the real data at four sizes, fit how each one actually
scales, and report that exponent beside the projection. A discarded warm-up pass runs first, each
size is timed several times, and I keep the fastest.

## Alternatives considered

### Alternative A: Multiply by the ratio of film counts

- **How it would work:** 1.9 seconds times 500 over 112, which is about 8.5 seconds.
- **Why it is attractive:** One line of arithmetic, no measurement machinery, and a figure anyone
  can check.
- **Why rejected:** It assumes the exact thing the measurement exists to test. It would also be
  pessimistic here, which hides the real risk: if one stage scaled *worse* than linearly, this
  method would never show it.

### Alternative B: Generate a synthetic 500-film dataset and run it

- **How it would work:** Fabricate 500 films with plausible fields and time the real pipeline on
  them.
- **Why it is attractive:** It is a direct measurement at the target size rather than an
  extrapolation, which is strictly better evidence when it works.
- **Why rejected:** A fabricated film carries a made-up cast size. That would make the shaping stage
  look proportional to the number of films, when it is really proportional to the number of credit
  rows — the exact distinction the projection turns on.

## Consequences

- **What this buys:** A projection of 3.6 seconds at 500 titles, with an all-linear figure of 4.5
  seconds published beside it, against a 10-second limit. The conclusion holds either way, which
  matters because the sub-linear exponents are being stretched five-fold beyond the range I
  measured. It also names the stage to watch: shaping is 64% of the budget and the only one that
  measures as genuinely proportional.
- **What this costs:** The measurement re-runs the analysis stages twelve times, which is why the
  checks stage excludes its own timing from the budget it computes.
- **What it costs the client if I am wrong:** The fit rests on four sample sizes and sub-second
  timings, which are noisy — exponents move by a few tenths between runs. That is why the
  conservative bound is published alongside and the conclusion is phrased as "comfortably inside the
  limit under either assumption" rather than as a point estimate.
- **What would make me revisit this:** Any stage fitting an exponent above 1.2, or the measured
  range reaching a size where fixed costs no longer dominate — at which point the extrapolation is
  no longer five-fold and the fit can be trusted further.

## What this survives

The method survives; the numbers need re-running. The first attempt fitted *negative* exponents,
which would have projected the pipeline getting faster as the catalogue grew, and was quoted nowhere
because I read the exponents instead of just the total (S-04). A negative fit now falls back to
linear and says so in the artefact, so the same mistake cannot be published silently next year.
