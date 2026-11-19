# ADR-030: A settings key must change behaviour, or refuse to load

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
An audit found five keys in `settings.toml` that no code read (F20). Two of them were cited in
decision records as the mechanism that made a judgement reversible: ADR-014 credited
`use_popularity_as_performance` with making a choice visible, and ADR-015 credited
`report_all_hit_definitions` with exposing the fragility of the hit rate. Both behaviours were real
and both were hardcoded.

## Decision
Wire up what is implementable and make the rest fail loudly at load.
`hit_definition`, `report_all_hit_definitions`, `lead_actor_billing_order` and
`sensitivity_top_n_billed` are now read and change behaviour.
`use_popularity_as_performance` cannot be implemented without contradicting ADR-014, so settings
validation **refuses to load** a configuration that sets it true, with a message that explains why
and names the record.

## Alternatives considered
- **Delete the inert keys** — loses the switch, and leaves the decision records citing something
  that no longer exists.
- **Wire every key up** — impossible for the popularity key without reversing a decision this
  project argues is correct.

## Consequences
- Every key in the file is now read by code, asserted by a test.
- One wiring produced a finding that had been unreachable: the top-3-billed talent view takes the
  reliable names from 19 to 44, with 25 visible only when the net is widened. A "rejected
  alternative kept runnable" that nothing ran was not an alternative at all.
- Settings validation can refuse a configuration somebody deliberately wants. That is the intent, and
  the message says what to do.
- At 500 titles this matters more: the person flipping a setting next year will not be the person who
  wrote the comment next to it.

## Revisit when
A new key is added. It owes the project either a code path or a validation error, and a test proving
which.
