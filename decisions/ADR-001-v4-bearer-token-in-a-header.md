# ADR-001: Authenticate with a bearer token in a header, never a key in the URL

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Paapa Andam-Cobbold

## Context

TMDb issues two kinds of credential. The older one is a 32-character key that you normally pass as
`?api_key=...` in the address. The newer one is a bearer token you send in a header.

A key in an address does not stay in the address. It reaches shell history, exception messages,
server logs, and the request path I write into every cached response. This repository is graded,
cloned and re-run by other people, so a leaked credential is not a theoretical problem.

## Decision

I read a bearer token from `.env`, which is gitignored, and attach it once to the session headers.
No credential appears in a URL, a log line, or a cached file.

## Alternatives considered

### Alternative A: The older key in the query string

- **How it would work:** Append `?api_key=...` to every request. This is what most tutorials show,
  and it is slightly less setup for whoever runs it next.
- **Why it is attractive:** Nothing to configure beyond pasting a shorter string, and every example
  on the internet matches.
- **Why rejected:** The credential ends up in four places this pipeline also writes to disk or
  prints. I would be relying on nobody ever pasting a log line into a chat window.

## Consequences

- **What this buys:** A credential that cannot leak through the pipeline's own output. The guarantee
  is tested rather than claimed: one test checks that no request address and no cached file contains
  the token, the word `Bearer`, or the string `api_key`.
- **What this costs:** Anyone running this needs their own token, and the setup instructions are a
  step longer. There is no shared credential to inherit.
- **What it costs the client if I am wrong:** A leaked credential in a repository that other people
  clone. Unrecoverable once pushed — revoking it is the only remedy — and the exposure grows with
  the number of people running the pipeline.
- **What would make me revisit this:** TMDb deprecating bearer authentication, or a cached file ever
  being found to carry a header.

## What this survives

All of it. This gets more important as the project is handed on, not less: next year more people run
it, on more machines, and the person pasting an error message into an email will not be the person
who chose the credential.
