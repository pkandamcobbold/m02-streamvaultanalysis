# ADR-005: Treat the brief's "127 titles" as a claim to reconcile against, not an assertion to crash on

**Status:** Accepted · **Date:** 2026-11-18 · **Deciders:** Data team

## Context
The brief says 127 candidate titles. The file holds 128 lines: one header and 127 data rows. They
agree this quarter. Next year's list is expected to reach about 500 titles, and Adjoa will run the
pipeline herself, sometimes live in a meeting.

## Decision
`input.expected_id_count` lives in settings. A mismatch prints a reconciliation note, is recorded
as a finding, and all reconciliation proceeds against what the file actually holds.

## Alternatives considered
- **Assert the count is exactly 127** — fails loudly on any difference. Loses because it would
  crash Adjoa's run for being *correct* about a new list size, in a quarter when nobody remembers
  where 127 came from.

## Consequences
- No mismatch this quarter, so no note was raised.
- The opposite risk — a shrinking list going unnoticed — is carried by the printed note and the
  findings log rather than by an exception.
- Both behaviours are pinned: `test_count_mismatch_is_a_note_not_a_crash` and
  `test_matching_count_produces_no_note`.

## Revisit when
A run reports a mismatch that nobody acts on. That means the note is not loud enough, and the
release gate (ADR-029) should take the check over.
