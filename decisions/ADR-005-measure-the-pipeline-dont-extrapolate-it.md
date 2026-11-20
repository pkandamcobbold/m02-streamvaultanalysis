# ADR-005: State the timing boundary, and measure how each stage scales rather than multiplying the total

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Paapa Andam-Cobbold
- **Merged from:** ADR-010 (acquisition outside the budget) and ADR-011 (the projection is
  measured), 2026-11-20

## Context

Two decisions about measuring the pipeline: what the budget covers, and how it is projected forward.

**The boundary.** A run from an empty cache spends 20.3 seconds fetching and 1.9 seconds analysing.
Report those as one number and the analysis looks twelve times slower than it is. Worse, the
combined figure would move with TMDb's response times and Adjoa's wifi rather than with anything I
wrote, so it would measure the wrong thing and change for reasons nobody could act on. The brief
asks for a time budget with the boundary stated. It does not name a number, so the number is mine to
choose and to say I chose.

**The projection.** The brief asks how long this will take at around 500 titles. The obvious answer
is the measured time times 500 over 112. That assumes every stage gets slower in proportion to the
number of films, and at least one plainly does not: shaping the responses processes **credit rows**,
and this list averages 223 of them per film. The smaller stages are the opposite problem — at 112
films they are dominated by fixed costs that will not grow at all.

## Decision

**The budget covers the analysis only**: shaping, validating and transforming, with the data already
cached, on one machine, single-threaded. Fetching is excluded, and measured and reported directly
beside it so nothing is hidden. The limit is 10 seconds, set in the settings file and stated as ours
rather than the client's. The checks stage refuses to run if fetching ever appears inside the
budget, and verifies that the per-stage shares add up.

**The projection is measured.** I re-run the analysis stages over subsets of the real data at four
sizes, fit how each one actually scales, and report that exponent beside the projection. A discarded
warm-up pass runs first, each size is timed several times, and I keep the fastest.

## Alternatives considered

### Alternative A: One total, the way a user experiences it

- **How it would work:** Time the whole run, from launch to memo, and report that.
- **Why it is attractive:** It is the number Adjoa actually waits for, and it needs no explanation
  or boundary.
- **Why rejected:** It cannot be broken down. If it got worse, nothing in it would say whether the
  cause was my code or the network, so nobody could act on it.

### Alternative B: Analysis only, with fetching excluded and unmentioned

- **How it would work:** Report 1.9 seconds against the limit and say nothing about the other 20.
- **Why it is attractive:** It is the flattering number, and the boundary statement makes it
  technically defensible.
- **Why rejected:** It quietly excludes the expensive part. A reader who later discovered the full
  run takes half a minute would be right to distrust everything else in the report.

### Alternative C: Multiply by the ratio of film counts

- **How it would work:** 1.9 seconds times 500 over 112, which is about 8.5 seconds.
- **Why it is attractive:** One line of arithmetic, no measurement machinery, and a figure anyone
  can check.
- **Why rejected:** It assumes the exact thing the measurement exists to test. It would also be
  pessimistic here, which hides the real risk: if one stage scaled *worse* than linearly, this
  method would never show it.

### Alternative D: Generate a synthetic 500-film dataset and run it

- **How it would work:** Fabricate 500 films with plausible fields and time the real pipeline on
  them.
- **Why it is attractive:** It is a direct measurement at the target size rather than an
  extrapolation, which is strictly better evidence when it works.
- **Why rejected:** A fabricated film carries a made-up cast size. That would make the shaping stage
  look proportional to the number of films, when it is really proportional to the number of credit
  rows — the exact distinction the projection turns on.

## Consequences

- **What this buys:** A measurement that means something. The budget reads 1.9 seconds against a
  10-second limit, and shaping the nested responses is 64% of it — so if the budget is ever at risk,
  the artefact already says which stage to look at. The projection is 3.6 seconds at 500 titles with
  an all-linear figure of 4.5 seconds published beside it, so the conclusion holds either way, which
  matters because the sub-linear exponents are being stretched five-fold beyond the range I
  measured.
- **What this costs:** Two numbers to explain instead of one, and a boundary that has to be restated
  wherever either figure appears. The measurement also re-runs the analysis stages twelve times,
  which is why the checks stage excludes its own timing from the budget it computes.
- **What it costs the client if I am wrong:** Someone asks how long it takes on a fresh machine and
  gets the wrong answer; they need both numbers added — roughly 107 seconds at 500 titles — and
  giving them separately with the boundary named is exactly what makes that addition possible. On
  the fit: it rests on four sample sizes and sub-second timings, which are noisy, and exponents move
  by a few tenths between runs. That is why the conservative bound is published alongside and the
  conclusion is phrased as "comfortably inside the limit under either assumption" rather than as a
  point estimate.
- **What would make me revisit this:** The analysis stages approaching the limit, or anyone quoting
  a single blended figure in a report, which would mean the boundary had stopped being carried. Any
  stage fitting an exponent above 1.2, or the measured range reaching a size where fixed costs no
  longer dominate — at which point the extrapolation is no longer five-fold and the fit can be
  trusted further.

## What this survives

The boundary survives; the figures do not. Fetching is projected separately from the *cold* run —
0.173 seconds per call, so about 87 seconds at 500 titles — because projecting from a cached run
would promise two seconds and deliver ninety. That distinction is the thing to keep when the list
grows.

The method survives too, and its numbers need re-running. The first attempt fitted *negative*
exponents, which would have projected the pipeline getting faster as the catalogue grew, and was
quoted nowhere because I read the exponents instead of just the total (S-04). A negative fit now
falls back to linear and says so in the artefact, so the same mistake cannot be published silently
next year.
