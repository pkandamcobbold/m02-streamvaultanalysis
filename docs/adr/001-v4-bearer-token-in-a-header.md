# ADR-001: Authenticate with a v4 bearer token in a header, never a v3 key in the URL

**Status:** Accepted · **Date:** 2026-11-18 · **Deciders:** Data team

## Context
TMDb issues two credentials: a 32-character v3 key, normally passed as `?api_key=...` in the
query string, and a v4 bearer token sent in an `Authorization` header. A key in a URL reaches
shell history, exception messages, server logs, and any cached `request_path` written to disk.
This repository is graded, cloned and re-run by other people.

## Decision
Read a v4 bearer token from `.env` (gitignored) and attach it once to the `requests.Session`
headers. No credential ever appears in a URL, a log line, or a cache envelope.

## Alternatives considered
- **v3 key in the query string** — what most tutorials show. Loses because the credential ends up
  in four places this pipeline also writes to disk or prints.

## Consequences
- No effect on any number.
- The guarantee is tested rather than asserted: `test_token_never_reaches_the_url_or_the_cache_file`
  checks that no request URL and no cached envelope contains the token, the string `Bearer`, or
  `api_key`.
- Anyone running this needs their own token; there is no shared credential to inherit.

## Revisit when
TMDb deprecates v4 bearer auth, or a cached envelope is ever found to carry a header.
