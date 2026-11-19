# ADR-004: Recover `550.0` as `550`, but only when the fractional part is zeros

**Status:** Accepted · **Date:** 2026-11-18 · **Deciders:** Data team

## Context
The id column is read as text, so a value that passed through a float column upstream arrives as
`550.0`. None appears in this quarter's file. The branch exists because the fault is one keystroke
away and next quarter's file comes from the same three desks.

## Decision
Recover values matching a digits-dot-zeros pattern as the integer, and record the recovery in the
`reason` column of that ledger row. Anything else fails classification and stays unusable.

## Alternatives considered
- **Treat it as unparseable and drop the row** — loses a recoverable title to a formatting accident.
- **Recover any float-like value** — loses because there is no honest way to choose between `550.7`
  as 550 or as 551.

## Consequences
- Zero rows affected this quarter.
- A recovered id is self-verifying: TMDb either 404s or returns a film whose title does not fit a
  back-catalog list, and either way the row is visible in the fetch log.

## Revisit when
A future list contains float-formatted ids in volume. That would mean a source desk has changed how
it exports, and the contract in `docs/data_contract.md` needs a rule rather than a recovery branch.
