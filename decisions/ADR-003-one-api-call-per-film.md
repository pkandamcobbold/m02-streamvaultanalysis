# ADR-003: Fetch each film in one call, and keep the two-call version runnable

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Paapa Andam-Cobbold

## Context

The brief names two endpoints: one for a film's details, one for its credits. TMDb will also return
both in a single response if you ask it to.

For 117 films that is 234 calls the briefed way against 117 the other way. Next year's 500 titles
makes it 1,000 against 500. This is a free service that other people share.

## Decision

I request details and credits together, in one call per film. The two-call path stays in the code
behind a setting, so the alternative I rejected is something you can run and time rather than
something I asserted was slower.

## Alternatives considered

### Alternative A: Two calls per film, exactly as briefed

- **How it would work:** Call the details endpoint, then the credits endpoint, for every film.
- **Why it is attractive:** It is literally what the brief describes, which matters when the brief
  is also the marking scheme. It also degrades more gracefully: if the credits call fails you still
  have the details.
- **Why rejected:** It doubles the load on a shared service for identical content. I kept it
  runnable rather than discarding it, so the comparison is a measurement.

### Alternative B: One call, with the two-call path deleted

- **How it would work:** Same as the decision, but remove the setting and the second code path.
- **Why it is attractive:** Less code, one path to test, no dead branch to maintain.
- **Why rejected:** It removes the ability to demonstrate the comparison this decision rests on. A
  rejected alternative nobody can run is an opinion.

## Consequences

- **What this buys:** Measured from an empty cache, 117 calls for 117 films in 20.3 seconds. A
  second run makes no calls at all and takes 2.3 seconds. At 500 titles that scales to roughly 87
  seconds against 174. The content is identical: all 112 films that returned successfully came back
  with their credits, cast lists running from 9 to 177 names, none empty.
- **What this costs:** A setting that has to keep working, and a second code path that the tests
  have to cover. Both modes are tested.
- **What it costs the client if I am wrong:** If an appended credits block were ever truncated, the
  talent analysis would quietly narrow and nothing would look broken. Two guards against that: the
  fetch log records whether credits arrived for every film, and the two modes write to different
  filenames, so flipping the setting can never serve a cached response that lacks what was asked
  for.
- **What would make me revisit this:** A film returning successfully but without credits, or TMDb
  rate-limiting combined responses differently from plain ones.

## What this survives

This is the decision that scales best. At 500 titles it halves the acquisition time and halves the
load on someone else's service. The guard that makes it safe — different filenames per mode — does
not depend on the list's size at all.
