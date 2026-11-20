# ADR-002: The cache is disposable evidence — not committed, written atomically, never overwritten by the live check

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Paapa Andam-Cobbold
- **Merged from:** ADR-002 (not committed), ADR-007 (atomic writes) and ADR-012 (separate
  spot-check cache), 2026-11-20

## Context

Three decisions about the cached API responses, which turn out to be one decision seen from three
angles: the cache is **evidence of what the source said and when**, and it is **rebuildable**. Every
choice below follows from holding both of those at once.

**Whether to commit it.** The pipeline saves one file per film to `data/raw/`, holding exactly what
the API returned. For 117 films that is a few megabytes; at the 500 titles expected next year it is
several times that, and it changes every time anyone refreshes the data. TMDb's terms also
discourage redistributing responses in bulk.

**How to write it.** Found by auditing the fetching code, not by it failing. Writing a file is not
instantaneous, so a run interrupted halfway through a write leaves a truncated file behind. I
reproduced it by truncating one cached response: the next run failed with a decoding error that
named neither the film nor the fix, **and so did every run after it**, because nothing ever rewrote
the bad file. The README told Adjoa that if a run is interrupted she should just start it again.
That was true for a *missing* file and false for a half-written one — which is the case an
interruption actually produces.

**Where the live check writes.** The spot-check compares what the analysis used against what the
source says now, so it has to fetch fresh copies. The obvious place to put them is the folder where
every other response already lives.

## Decision

**The contents of `data/raw/` are gitignored, but the folder itself is kept**, so a clean clone has
somewhere to put the data it fetches. The pattern is `data/raw/*` rather than `data/raw/`: a pattern
ending in a slash excludes the directory, git then never looks inside it, and the exception that
keeps the folder alive is never reached. This is the kind of detail that looks like a typo and is
not.

**Every cached response is written atomically** — to a temporary file in the same folder, then moved
into place in a single operation the operating system guarantees is all-or-nothing. A reader sees
either the whole old file or the whole new one, never half of either. If a cached file still cannot
be read, it is treated as missing: deleted, fetched again, and reported as a note.

**The live spot-check writes to its own folder**, ignored by git on the same terms.

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

### Alternative B: Leave the write non-atomic

- **How it would work:** Accept the risk. The window is a few milliseconds wide per film.
- **Why it is attractive:** It is a genuinely unlikely event, and the code is simpler without the
  temporary file and its cleanup.
- **Why rejected:** The failure it produces is permanent rather than occasional, and it sits on
  exactly the recovery path the documentation calls safe. An unlikely event that breaks the project
  until someone deletes a file by hand is worse than a frequent one that recovers itself.

### Alternative C: Checksum every cached response on read

- **How it would work:** Store a hash with each file and verify it before use.
- **Why it is attractive:** It catches corruption that the atomic write does not — a file damaged
  on disk after it was written correctly.
- **Why rejected:** Too much machinery for the risk. A payload corrupted into something that is
  still valid JSON would be caught by the live spot-check (M13), which compares cached values
  against the source.

### Alternative D: Let the spot-check fetch over the top of the analysis cache

- **How it would work:** Force a refresh of the sampled films in place.
- **Why it is attractive:** One cache to explain, no duplication, and the pipeline would then be
  running on the freshest available data.
- **Why rejected:** Two reasons, and the second is serious. It would overwrite the timestamps the
  memo's as-of date rests on. And it would make any discrepancy **disappear the moment it was
  found**: the next run would read the new values, recompute, and agree with itself. The check would
  erase its own evidence, so it could never fail twice.

### Alternative E: Hold the live responses in memory and discard them

- **How it would work:** Fetch, compare, report, throw away.
- **Why it is attractive:** Nothing extra on disk and nothing extra to explain.
- **Why rejected:** The responses are the evidence. A reviewer should be able to see what the check
  compared against, not just the verdict it reached.

## Consequences

- **What this buys:** The as-of date in the memo always means what it says, because it comes from
  the timestamp inside each cached response rather than from the repository's history. The
  documented recovery instruction becomes true: an interrupted run leaves nothing behind that breaks
  the next one, including when the interruption is a keyboard interrupt — the temporary file is
  cleaned up in that case too, so the cache listing stays accurate. And the live check is repeatable,
  with its evidence surviving it.
- **What this costs:** A clean clone needs a credential and a connection once, and about 26 seconds
  of fetching before the analysis runs; every run after that works offline. Plus a few lines of file
  handling, a process id in the temporary filename so two runs cannot collide on it, a second cache
  folder to explain, and a few megabytes on disk.
- **What it costs the client if I am wrong:** Adjoa clones the project in a meeting with no network
  and cannot run it at all — mitigated by the fact that she would be running her own copy, which
  already has the data. The atomic write prevents a failure that is total rather than partial: the
  pipeline stops working and the error does not say which file to delete, leaving her stuck before a
  meeting with no way to diagnose it. And the separate spot-check cache prevents a check that
  silently stops being able to detect the thing it exists to detect.
- **What would make me revisit this:** The payloads becoming small and stable enough that committing
  them would make the analysis reproducible without a credential, or TMDb's terms changing to
  require it. Corrupt entries reported on runs that were *not* interrupted, which points at the disk
  rather than at the writer and is the case the checksum alternative would cover. Or the two caches
  drifting far enough apart that comparing them stops being meaningful — which would mean the
  analysis cache is older than the quarter it is being used for, and the fix is to refresh it rather
  than to merge the folders.

## What this survives

All of it, and every part of the argument strengthens with size. At 500 titles the cache is five
times larger while the reason not to commit it is unchanged. The fetch takes four times as long, so
the window in which an interruption can land is four times wider, and nothing about the atomic write
depends on the list's size. And the more quarters this runs, the more valuable it is that a
discrepancy found in October is still visible in January.
