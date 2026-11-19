# ADR-008: Write cache entries atomically, and treat an unreadable entry as a cache miss

**Status:** Accepted · **Date:** 2026-11-18 · **Deciders:** Data team

## Context
Found by auditing extraction, not by it failing. A plain `write_text` is not atomic, so a run
interrupted mid-write leaves a truncated JSON file. Reproduced by truncating one cache file: the
next run raised a JSON decode error naming neither the film nor the remedy, **and every run after it
did the same**, because nothing ever rewrote the bad file. The README told Adjoa "if a run is
interrupted, just start it again" — true for a *missing* file, false for a half-written one.

## Decision
Write to a temp file carrying the process id in the same directory, then `os.replace`, which is
atomic on both Windows and POSIX. An unreadable entry is deleted, refetched, and reported as a note.

## Alternatives considered
- **Leave it** — the window is milliseconds wide, but the failure it produces is permanent and sits
  on exactly the path the README calls safe.
- **Checksum every entry on read** — also catches bit-rot, which `os.replace` does not. Not worth
  it: a corrupt payload that is still valid JSON would be caught by the live spot-check (ADR-026).

## Consequences
- No effect on any number. The failure prevented is total, not partial: the pipeline stops working
  until someone deletes a file by hand, and the traceback does not say which one.
- The temp file is cleaned up even on a keyboard interrupt, so an interrupted run leaves no stray
  entries in the cache listing.
- At 500 titles the interruption window is four times longer, so this matters more, not less.

## Revisit when
Corrupt entries are reported on runs that were not interrupted. That points at the disk, not at the
writer.
