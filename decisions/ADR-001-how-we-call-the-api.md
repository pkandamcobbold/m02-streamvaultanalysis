# ADR-001: Call the API once per film, and never put the credential in a URL

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Paapa Andam-Cobbold
- **Merged from:** ADR-001 (bearer token in a header) and ADR-003 (one call per film), 2026-11-20

## Context

Two questions about how this pipeline talks to TMDb, both settled at the same time and both with no
effect on the recommendation.

**The credential.** TMDb issues two kinds. The older one is a 32-character key that you normally
pass as `?api_key=...` in the address. The newer one is a bearer token you send in a header. A key
in an address does not stay in the address: it reaches shell history, exception messages, server
logs, and the request path this pipeline writes into every cached response. This repository is
graded, cloned and re-run by other people, so a leaked credential is not theoretical.

**The number of calls.** The brief names two endpoints, one for a film's details and one for its
credits. TMDb will return both in a single response if you ask. For 117 films that is 234 calls the
briefed way against 117 the other way; next year's 500 titles makes it 1,000 against 500. This is a
free service other people share.

## Decision

**Authenticate with a bearer token in a header.** It is read from `.env`, which is gitignored, and
attached once to the session headers. No credential appears in a URL, a log line, or a cached file.

**Request details and credits together, in one call per film.** The two-call path stays in the code
behind a setting, so the alternative I rejected is something you can run and time rather than
something I asserted was slower.

## Alternatives considered

### Alternative A: The older key in the query string

- **How it would work:** Append `?api_key=...` to every request. This is what most tutorials show,
  and it is slightly less setup for whoever runs it next.
- **Why it is attractive:** Nothing to configure beyond pasting a shorter string, and every example
  on the internet matches.
- **Why rejected:** The credential ends up in four places this pipeline also writes to disk or
  prints. I would be relying on nobody ever pasting a log line into a chat window.

### Alternative B: Two calls per film, exactly as briefed

- **How it would work:** Call the details endpoint, then the credits endpoint, for every film.
- **Why it is attractive:** It is literally what the brief describes, which matters when the brief
  is also the marking scheme. It also degrades more gracefully: if the credits call fails you still
  have the details.
- **Why rejected:** It doubles the load on a shared service for identical content. I kept it
  runnable rather than discarding it, so the comparison is a measurement.

### Alternative C: One call, with the two-call path deleted

- **How it would work:** As decided, but remove the setting and the second code path.
- **Why it is attractive:** Less code, one path to test, no dead branch to maintain.
- **Why rejected:** It removes the ability to demonstrate the comparison this decision rests on. A
  rejected alternative nobody can run is an opinion.

## Consequences

- **What this buys:** A credential that cannot leak through the pipeline's own output, tested rather
  than claimed — one test checks that no request address and no cached file contains the token, the
  word `Bearer`, or the string `api_key`. And measured from an empty cache, 117 calls for 117 films
  in 20.3 seconds, where the second run makes no calls at all and takes 2.3 seconds. At 500 titles
  that is roughly 87 seconds against 174. The content is identical: all 112 films that returned
  successfully came back with their credits, cast lists running from 9 to 177 names, none empty.
- **What this costs:** Anyone running this needs their own token, so the setup instructions are a
  step longer and there is no shared credential to inherit. Plus a setting that has to keep working
  and a second code path the tests have to cover. Both modes are tested.
- **What it costs the client if I am wrong:** A leaked credential in a repository other people
  clone is unrecoverable once pushed — revoking it is the only remedy — and the exposure grows with
  the number of people running the pipeline. Separately, if an appended credits block were ever
  truncated, the talent analysis would quietly narrow and nothing would look broken. Two guards
  against that: the fetch log records whether credits arrived for every film, and the two modes
  write to different filenames, so flipping the setting can never serve a cached response that
  lacks what was asked for.
- **What would make me revisit this:** TMDb deprecating bearer authentication; a cached file ever
  being found to carry a header; a film returning successfully but without credits; or TMDb
  rate-limiting combined responses differently from plain ones.

## What this survives

Both halves survive intact, and both matter more at 500 titles than at 127. The credential decision
gets more important as the project is handed on: next year more people run it, on more machines, and
the person pasting an error message into an email will not be the person who chose the credential.
The one-call decision scales best of anything here — it halves the acquisition time and halves the
load on someone else's service — and the guard that makes it safe, different filenames per mode,
does not depend on the list's size at all.
