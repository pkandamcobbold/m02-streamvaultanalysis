# ADR-016: A setting must change behaviour, or refuse to load

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Paapa Andam-Cobbold

## Context

An audit found five keys in the settings file that no code read (S-06).

That would be untidy on its own. What made it serious is that two of them were cited *in decision
records* as the mechanism that made a judgement reversible. One record credited a setting with
making a choice visible; another credited a setting with exposing how fragile the hit rate is. Both
behaviours were real. Both were hardcoded, and the settings had nothing to do with them.

So the project was claiming a flexibility it did not have, in writing, in the documents meant to be
most trustworthy.

## Decision

Wire up what can be implemented, and make the rest fail loudly when the settings load.

Four keys now genuinely change behaviour. The fifth — using the catalogue's popularity score as a
performance measure — cannot be implemented without contradicting M8, so the settings validation
**refuses to load** a configuration that turns it on, with a message explaining why and naming the
record. A setting that cannot work is better as an error than as decoration.

## Alternatives considered

### Alternative A: Delete the inert keys

- **How it would work:** Remove them from the settings file and from the records that cite them.
- **Why it is attractive:** Simplest possible fix, and the file gets shorter.
- **Why rejected:** It loses the switch for the four that *can* work, and it leaves two decision
  records citing a mechanism that no longer exists anywhere. The honest version of that fix is to
  rewrite the records to admit the behaviour is fixed — at which point I have removed a capability
  rather than gained one.

### Alternative B: Wire all five up

- **How it would work:** Implement every switch, including the popularity one.
- **Why it is attractive:** Every key does what it looks like it does, with no special cases and no
  validation to explain.
- **Why rejected:** Implementing the popularity switch means reversing a decision this project
  argues is correct, for the sake of consistency in a settings file. That is the tail wagging the
  dog.

## Consequences

- **What this buys:** Every key in the file is now read by code, and a test asserts it. One of the
  wirings also produced a finding that had been unreachable: widening the talent view from billed
  leads to the top three billed takes the reliable names from 19 to 44, with 25 visible only when
  the net is widened. A "rejected alternative kept runnable" that nothing ran was not an alternative
  at all.
- **What this costs:** The settings can now refuse a configuration somebody deliberately wants. That
  is the intent, and the message says what to do about it.
- **What it costs the client if I am wrong:** Someone trusts a decision record that says a choice is
  reversible, flips the setting, sees no change, and concludes the analysis is unreliable — reasonably.
  That is a loss of trust in the documents, which is harder to recover than a wrong number.
- **What would make me revisit this:** Nothing about the rule. It applies to every new key: each one
  owes the project either a code path or a validation error, and a test proving which.

## What this survives

This gets more important as the project is handed on. The person flipping a setting next year will
not be the person who wrote the comment beside it, and they will have no way to tell a live switch
from a decorative one except by trusting what the file says.
