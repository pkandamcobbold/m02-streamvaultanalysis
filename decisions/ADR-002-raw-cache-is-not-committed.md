# ADR-002: Do not commit the raw API responses

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Paapa Andam-Cobbold

## Context

The pipeline saves one file per film to `data/raw/`, holding exactly what the API returned. For 117
films that is a few megabytes. At the 500 titles expected next year it is several times that, and it
changes every time anyone refreshes the data. TMDb's terms also discourage redistributing responses
in bulk.

## Decision

I gitignore the contents of `data/raw/` but keep the folder itself, so a clean clone has somewhere
to put the data it fetches.

The pattern is `data/raw/*` rather than `data/raw/`. A pattern ending in a slash excludes the
directory, git then never looks inside it, and the exception that keeps the folder alive is never
reached. This is the kind of detail that looks like a typo and is not.

## Alternatives considered

### Alternative A: Commit the cached responses

- **How it would work:** Check the fetched files into the repository, so a clean clone needs no
  credential and no network to reproduce the analysis.
- **Why it is attractive:** It makes the project genuinely self-contained. Anyone could clone it and
  get the same numbers with no account and no internet, which is a real benefit for a graded piece
  of work.
- **Why rejected:** The repository would carry a snapshot that silently ages. A reviewer reading the
  memo's as-of date could not tell whether it describes the data or the last commit, and that date
  is the whole basis for knowing how fresh the figures are.

## Consequences

- **What this buys:** The as-of date in the memo always means what it says, because it comes from
  the timestamp inside each cached response rather than from the repository's history.
- **What this costs:** A clean clone needs a credential and a connection once, and about 26 seconds
  of fetching before the analysis runs. Every run after that works offline.
- **What it costs the client if I am wrong:** Adjoa clones the project in a meeting with no network
  and cannot run it at all. Mitigated by the fact that she would be running her own copy, which
  already has the data.
- **What would make me revisit this:** The payloads becoming small and stable enough that
  committing them would make the analysis reproducible without a credential, or TMDb's terms
  changing to require it.

## What this survives

All of it, and the argument strengthens at 500 titles: the cache gets five times larger while the
reason to commit it stays the same. The spot-check's separate cache is ignored on the same terms
(ADR-012).
