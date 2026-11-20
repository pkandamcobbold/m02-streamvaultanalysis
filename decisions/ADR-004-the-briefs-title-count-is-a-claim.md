# ADR-004: Treat the brief's title count as a number to reconcile against, not one to crash on

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Paapa Andam-Cobbold

## Context

The brief says there are 127 candidate titles. The file has 128 lines: a header and 127 rows of
data. They agree, this quarter.

Next year's list is expected to be around 500 titles, and Adjoa will be running the pipeline
herself, sometimes live in a meeting, without me there to explain why it stopped.

## Decision

The expected count lives in the settings file. If the file disagrees with it, the pipeline prints a
note saying so, records it as a finding, and carries on — reconciling against what the file actually
holds rather than against what the brief claimed.

## Alternatives considered

### Alternative A: Assert the count is exactly 127

- **How it would work:** Check the row count on startup and stop the run if it differs.
- **Why it is attractive:** It catches a truncated file immediately, which is a real failure mode
  when a list is assembled by hand from three sources. It is also the kind of check that reads as
  rigorous.
- **Why rejected:** It would stop Adjoa's run for being *correct* about a new list size, in a
  quarter when nobody remembers where 127 came from. The failure would look like a bug in the
  pipeline rather than a change in the input, and she would be debugging it in front of the board.

## Consequences

- **What this buys:** The pipeline keeps working when the input legitimately changes, which it is
  expected to do, substantially, within a year.
- **What this costs:** The opposite risk. A list that silently shrinks would not stop the run, so it
  has to be caught by someone reading the note. Both behaviours are pinned by tests, so neither can
  be lost by accident.
- **What it costs the client if I am wrong:** A quarter's recommendation computed on a truncated
  list, with the note printed and nobody reading it. That is why the release gate also checks that
  every row of the source file is accounted for (ADR-015) — a printed note is advisory, and the gate
  is not.
- **What would make me revisit this:** A run reporting a mismatch that nobody acts on. That means
  the note is not loud enough and the check belongs entirely to the gate.

## What this survives

This is one of the few decisions made specifically *for* the 500-title run rather than despite it.
The number it checks against is a setting, so the only maintenance is editing one line when the list
grows.
