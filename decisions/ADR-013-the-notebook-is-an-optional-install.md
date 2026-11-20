# ADR-013: Make the notebook an optional install, separate from the pipeline's requirements

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Data team

## Context

The clean-clone test failed. Installing the requirements built nothing at all, because the notebook
package pulls in a dependency chain that ends at a library with no prebuilt version for this Python
and which cannot be compiled here (S-05).

An earlier check had passed, which is why this was not caught sooner: resolving the notebook package
*on its own* selects an older version that predates the problematic dependency. Resolved alongside
everything else, pip picks a newer one.

This decides whether the project installs at all, which makes it the most expensive thing on this
list to get wrong.

## Decision

The notebook moves to its own optional requirements file. The pipeline does not need it, and
produces every artefact and every report without it.

## Alternatives considered

### Alternative A: Pin the notebook's dependencies to versions that avoid the problem

- **How it would work:** Pin two transitive packages to older releases that predate the offending
  dependency.
- **Why it is attractive:** One install command still does everything, and the notebook stays a
  first-class part of the project.
- **Why rejected:** It pins packages pip does not want to the versions I need, which breaks again
  the next time anything else in the chain moves. I would be maintaining someone else's dependency
  graph.

### Alternative B: Drop the notebook entirely

- **How it would work:** Delete it, and let the generated reports carry the narrative.
- **Why it is attractive:** One less thing to install, test and explain, and the reports genuinely
  do cover the analysis.
- **Why rejected:** The notebook is the narrative walkthrough, which is part of the deliverable
  shape (Q11). Deleting a deliverable to fix an install is the wrong trade.

## Consequences

- **What this buys:** Installing the pipeline takes 78 seconds, uses prebuilt packages only, and
  pulls 10 packages instead of about 100. Verified end to end in a fresh clone: install, import with
  no path fiddling, the whole test suite passing, and the missing-credential path printing
  instructions rather than a stack trace.
- **What this costs:** The notebook is a second command, and that command may still fail on this
  Python. The optional file says so plainly, and says the pipeline is unaffected.
- **What it costs the client if I am wrong:** A reader who wants the notebook and hits the wall gets
  nothing from it. That is a documented inconvenience for one optional artefact, against the
  alternative, which was a repository nobody could install.
- **What would make me revisit this:** The missing library shipping a prebuilt version for the
  Python in use. Re-confirmed on 2026-11-19 that it still does not, and that a dry run of the
  install *succeeds* while the real install fails — so checking it needs a real install, not a
  resolution check.

## What this survives

The split survives. The reason for it may not: it exists because of one library's build situation on
one Python version, and that will change. What should survive regardless is the principle that a
viewer's dependencies cannot be allowed to stop the analysis installing.

A related inconsistency has since been closed: the pinned numerical libraries need Python 3.12 or
newer, while the README and project metadata claimed 3.10. Both now say 3.12 (S-09).
