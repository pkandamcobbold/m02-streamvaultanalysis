# ADR-008: Read every saved table back with its types declared, never inferred

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Paapa Andam-Cobbold

## Context

Also from an audit rather than from a failure.

The ledger file holds the id `155`. Read it back without saying what the types are and you get
`155.0`, because the same column holds blanks for the rows that have no id, and a column with a
blank in it cannot be whole numbers.

The first stage of the pipeline goes to real trouble to make sure `550` never becomes `550.0` — that
is the difference between fetching a film and getting a "not found". It writes a correct file. Then
the guarantee leaks the moment anything reads that file back.

Nothing had broken yet only because nothing read the saved tables back yet. The later stages, the
notebook and the spot-check all do.

## Decision

Every saved table gets a loader that declares its types, and every reader uses it. No stage, no
notebook cell and no test reads a pipeline table with types left to be guessed.

## Alternatives considered

### Alternative A: Rely on whoever reads it to declare the types

- **How it would work:** Document the types and leave it to the caller.
- **Why it is attractive:** No extra code, and anyone competent would do it correctly.
- **Why rejected:** The failure is silent and surfaces stages away from its cause. An id with a
  stray `.0` fails against the API, so the symptom is a fetching problem and the cause is a file
  read. That is an hour of debugging in the wrong module.

### Alternative B: Save the tables in a format that carries its own types

- **How it would work:** Use Parquet instead of CSV. The types travel with the data and the problem
  disappears.
- **Why it is attractive:** Technically the right answer. It removes the failure mode rather than
  guarding against it, and it is smaller and faster.
- **Why rejected:** Adjoa and Yaw have to be able to open these files and read them. A format that
  needs code to inspect would make the evidence unavailable to the people the evidence is for.

## Consequences

- **What this buys:** A guarantee that holds across the file boundary rather than only inside the
  stage that made it. The round trip is tested, including a test asserting that the *naive* read
  still produces the wrong type — so if a future library release fixes this, the test fails and
  tells us, rather than leaving redundant loaders in place for years.
- **What this costs:** Every new saved table owes the project a loader. A small standing cost, and
  one that is easy to forget.
- **What it costs the client if I am wrong:** This is the fault class that costs the most and shows
  the least. A number computed on ids that silently lost precision looks exactly like a correct
  number. Nothing downstream could detect it.
- **What would make me revisit this:** A library release that makes the plain read return the type
  that was written. The test for that is already in place and will fail, which is the signal.

## What this survives

All of it, and the exposure grows: every quarter adds artefacts and readers. The reason it is worth
a record rather than a comment is that the guard looks redundant until the day it is not.
