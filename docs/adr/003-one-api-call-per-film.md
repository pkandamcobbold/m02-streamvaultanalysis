# ADR-003: One API call per film using `append_to_response=credits`, with the two-call path kept runnable

**Status:** Accepted · **Date:** 2026-11-18 · **Deciders:** Data team

## Context
The brief names two endpoints, `/movie/{id}` and `/movie/{id}/credits`. TMDb also accepts
`?append_to_response=credits`, returning both in one response. 117 films is 234 calls the briefed
way against 117 appended; next year's ~500 titles is 1,000 against 500, against a shared service.

## Decision
Request details and credits in one call. Keep the two-call path behind `api.append_credits` in
`config/settings.toml`, so the rejected alternative is a flag that can be run and timed rather than
a paragraph.

## Alternatives considered
- **Two calls per film, literally as briefed** — doubles the load on a shared API for identical
  content. Kept runnable rather than discarded.
- **One call with no way back** — loses the ability to measure the comparison this decision claims.

## Consequences
- Measured from an empty cache: **117 calls for 117 films in 20.3s**. A second run: **0 calls,
  2.3s**. Both are in the run log, which is appended to rather than overwritten.
- Content is identical: all 112 films returning 200 came back with a credits block, cast counts 9
  to 177, none empty.
- Two guards against a truncated credits block: the fetch log carries `has_credits` per film, and
  the cache filename differs between modes (`550__details_credits.json` against
  `550__details.json`), so flipping the flag can never serve a cached response lacking what was
  asked for.
- At 500 titles, scaling the measured 20.3s linearly: about 87s appended against about 174s briefed.

## Revisit when
A film returns 200 without a credits block, or TMDb rate-limits appended responses differently from
plain ones.
