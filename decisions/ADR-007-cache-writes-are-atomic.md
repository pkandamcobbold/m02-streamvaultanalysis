# ADR-007: Write cached responses atomically, and treat an unreadable one as missing

- **Status:** Accepted
- **Date:** 2026-11-18
- **Decision owner:** Data team

## Context

I found this by auditing the fetching code, not by it failing.

Writing a file is not instantaneous, so a run interrupted halfway through a write leaves a truncated
file behind. I reproduced it by truncating one cached response: the next run failed with a decoding
error that named neither the film nor the fix, **and so did every run after it**, because nothing
ever rewrote the bad file.

The README told Adjoa that if a run is interrupted she should just start it again. That was true for
a *missing* file and false for a half-written one — which is the case an interruption actually
produces.

## Decision

I write to a temporary file in the same folder, then move it into place in a single operation that
the operating system guarantees is all-or-nothing. A reader sees either the whole old file or the
whole new one, never half of either.

If a cached file still cannot be read, it is treated as missing: deleted, fetched again, and
reported as a note.

## Alternatives considered

### Alternative A: Leave it

- **How it would work:** Accept the risk. The window is a few milliseconds wide per film.
- **Why it is attractive:** It is a genuinely unlikely event, and the code is simpler without the
  temporary file and its cleanup.
- **Why rejected:** The failure it produces is permanent rather than occasional, and it sits on
  exactly the recovery path the documentation calls safe. An unlikely event that breaks the project
  until someone deletes a file by hand is worse than a frequent one that recovers itself.

### Alternative B: Checksum every cached response on read

- **How it would work:** Store a hash with each file and verify it before use.
- **Why it is attractive:** It catches corruption that the atomic write does not — a file damaged
  on disk after it was written correctly.
- **Why rejected:** Too much machinery for the risk. A payload corrupted into something that is
  still valid JSON would be caught by the live spot-check (M13), which compares cached values
  against the source.

## Consequences

- **What this buys:** The documented recovery instruction becomes true. An interrupted run leaves
  nothing behind that breaks the next one, including when the interruption is a keyboard interrupt —
  the temporary file is cleaned up in that case too, so the cache listing stays accurate.
- **What this costs:** A few lines of file handling, and a process id in the temporary filename so
  two runs cannot collide on it.
- **What it costs the client if I am wrong:** Nothing on any number. The failure prevented is total
  rather than partial: the pipeline stops working, and the error message does not say which file to
  delete. Adjoa would be stuck before a meeting with no way to diagnose it.
- **What would make me revisit this:** Corrupt entries reported on runs that were *not* interrupted.
  That points at the disk rather than at the writer, and it is the case the checksum alternative
  would cover.

## What this survives

It matters more as the list grows, not less. At 500 titles the fetch takes four times as long, so
the window in which an interruption can land is four times wider. Nothing about the fix depends on
the list's size.
