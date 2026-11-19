# ADR-002: Do not commit the raw API cache

**Status:** Accepted · **Date:** 2026-11-18 · **Deciders:** Data team

## Context
Extraction writes one JSON envelope per film to `data/raw/`. For 117 films that is a few MB; at the
~500 titles expected next year it is several times that, and it changes every time anyone
re-fetches. TMDb's terms also discourage redistributing bulk responses.

## Decision
Gitignore `data/raw/*` with `.gitkeep` negated so the folder survives a clone. The pattern is
`data/raw/*`, not `data/raw/`: a pattern ending in a slash excludes the directory itself, git never
descends into it, and the negation for `.gitkeep` is then never evaluated.

## Alternatives considered
- **Commit the cache** so a clean clone needs no API call. Loses because the repository would carry
  a snapshot that silently ages, and a reviewer could not tell whether the memo's as-of date
  describes the data or the commit.

## Consequences
- No effect on any number. A clean clone costs about 26s of fetching before the analysis runs,
  measured.
- A clean-clone run needs a token and a connection once; every run after that is offline.
- `data/raw_spotcheck/*` is ignored on the same terms (ADR-025).

## Revisit when
The raw payloads become small and stable enough that committing them would make the analysis
reproducible without a credential, or TMDb's terms change to require it.
