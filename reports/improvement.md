# The one improvement: a release gate

## What it is

Four checks that run before the memo is written. If any fails, **no memo and no
shortlist are produced** — the pipeline stops and prints what failed, in
language that says what to do next.

| Check | What it refuses to publish past |
|---|---|
| every source row accounted for | 0 row(s) unaccounted for, limit 0. |
| enough films to compare groups | 112 films analysed, minimum 40. |
| money data complete enough to decide on | 0% of films have no usable budget or box office, limit 20%. |
| live re-check does not change the answer | the live re-check leaves the recommendation unchanged. |

It is in `src/streamvault/memo.py` as `gate()`, configured under `[gate]` in
`config/settings.toml`, and it can be turned off deliberately —
`gate.enabled = false` — which is the point: skipping it should be a decision
somebody makes and can be asked about, not a thing that happens by accident.

## Why this one, for this client

Adjoa reruns this every quarter, on her laptop, **sometimes live in the
meeting**. Everything else in this project protects the analysis from being
wrong. Nothing protected her from the analysis being wrong *and looking fine*.

That is the specific failure this addresses: a run where the candidate list
arrived truncated, or half the box-office figures were missing, or a title was
double-counted — and the pipeline, which is built to carry on rather than
crash, produces a confident one-page recommendation anyway. She presents it.
Yaw asks how many titles it covers. Nobody in the room can tell that the
number is built on 40 films instead of 112.

A gate is worth more than another assertion because of *where* it sits. The
assertions throughout the pipeline protect each step from the one before. This
protects the **client-facing output** from the whole pipeline, and it is the
only check whose failure mode is "the board was misled" rather than "a stage
crashed".

## Why not the alternatives

- **A sensitivity panel** showing whether the answer survives each judgement
  call — already built, at stage 6. It answers Yaw before he asks, which is
  valuable, but it assumes the run was sound in the first place.
- **A run-over-run diff** of what changed since last quarter. Genuinely useful
  for the quarterly rerun, and it needs two quarters of history to be worth
  anything. Next quarter, not this one.
- **A bundle dead-weight score** — the share of a set's films below the
  one-off median. A good negotiating number, and it is a refinement of the
  answer rather than a protection against the answer being wrong.

## What it costs

Four checks, about sixty lines, and the risk that it blocks a run Adjoa
believes is fine. That risk is handled by the message naming the one-line
setting that overrides it, and by keeping the checks blunt: each one, if it
fails, makes the memo actively misleading rather than merely imperfect. A gate
with twenty conditions is a gate somebody permanently disables the first time
it blocks a run for something cosmetic.

## What survives at 500 titles

All four checks are proportions or reconciliations, so none of them needs
re-tuning as the list grows — except
`gate.min_films_for_a_recommendation`, which is an absolute floor and should be
raised if the standalone group stays as thin as it is now.
