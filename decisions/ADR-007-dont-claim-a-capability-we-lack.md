# ADR-007: Do not claim a capability the project does not have — an optional notebook, and settings that work or refuse to load

- **Status:** Accepted
- **Date:** 2026-11-19
- **Decision owner:** Paapa Andam-Cobbold
- **Merged from:** ADR-013 (the notebook is an optional install) and ADR-016 (a setting must be live
  or refuse to load), 2026-11-20

## Context

Two failures of the same kind, found within a day of each other: the project asserting something
about itself that was not true. One was an install that could not work; the other was a set of
switches that did nothing.

**The install.** The clean-clone test failed. Installing the requirements built nothing at all,
because the notebook package pulls in a dependency chain that ends at a library with no prebuilt
version for this Python and which cannot be compiled here (S-05). An earlier check had passed, which
is why this was not caught sooner: resolving the notebook package *on its own* selects an older
version that predates the problematic dependency. Resolved alongside everything else, pip picks a
newer one. This decides whether the project installs at all, which makes it the most expensive thing
here to get wrong.

**The switches.** An audit found five keys in the settings file that no code read (S-06). That would
be untidy on its own. What made it serious is that two of them were cited *in decision records* as
the mechanism that made a judgement reversible. One record credited a setting with making a choice
visible; another credited a setting with exposing how fragile the hit rate is. Both behaviours were
real. Both were hardcoded, and the settings had nothing to do with them. So the project was claiming
a flexibility it did not have, in writing, in the documents meant to be most trustworthy.

## Decision

**The notebook moves to its own optional requirements file.** The pipeline does not need it, and
produces every artefact and every report without it.

**Every settings key either changes behaviour or refuses to load.** Four keys now genuinely change
behaviour. The fifth — using the catalogue's popularity score as a performance measure — cannot be
implemented without contradicting M8, so the settings validation **refuses to load** a configuration
that turns it on, with a message explaining why and naming the record. A setting that cannot work is
better as an error than as decoration.

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

### Alternative C: Delete the inert settings keys

- **How it would work:** Remove them from the settings file and from the records that cite them.
- **Why it is attractive:** Simplest possible fix, and the file gets shorter.
- **Why rejected:** It loses the switch for the four that *can* work, and it leaves two decision
  records citing a mechanism that no longer exists anywhere. The honest version of that fix is to
  rewrite the records to admit the behaviour is fixed — at which point I have removed a capability
  rather than gained one.

### Alternative D: Wire all five settings up

- **How it would work:** Implement every switch, including the popularity one.
- **Why it is attractive:** Every key does what it looks like it does, with no special cases and no
  validation to explain.
- **Why rejected:** Implementing the popularity switch means reversing a decision this project
  argues is correct, for the sake of consistency in a settings file. That is the tail wagging the
  dog.

## Consequences

- **What this buys:** Installing the pipeline takes 78 seconds, uses prebuilt packages only, and
  pulls 10 packages instead of about 100 — verified end to end in a fresh clone: install, import
  with no path fiddling, the whole test suite passing, and the missing-credential path printing
  instructions rather than a stack trace. And every key in the settings file is now read by code,
  with a test asserting it. One of those wirings produced a finding that had been unreachable:
  widening the talent view from billed leads to the top three billed takes the reliable names from
  19 to 44, with 25 visible only when the net is widened. A "rejected alternative kept runnable"
  that nothing ran was not an alternative at all.
- **What this costs:** The notebook is a second command, and that command may still fail on this
  Python; the optional file says so plainly, and says the pipeline is unaffected. And the settings
  can now refuse a configuration somebody deliberately wants — that is the intent, and the message
  says what to do about it.
- **What it costs the client if I am wrong:** A reader who wants the notebook and hits the wall gets
  nothing from it, which is a documented inconvenience for one optional artefact against the
  alternative of a repository nobody could install. The settings failure is worse in kind: someone
  trusts a decision record that says a choice is reversible, flips the setting, sees no change, and
  concludes the analysis is unreliable — reasonably. That is a loss of trust in the documents, which
  is harder to recover than a wrong number.
- **What would make me revisit this:** The missing library shipping a prebuilt version for the
  Python in use — re-confirmed on 2026-11-19 that it still does not, and that a dry run of the
  install *succeeds* while the real install fails, so checking it needs a real install rather than a
  resolution check. Nothing about the settings rule: it applies to every new key, each of which owes
  the project either a code path or a validation error, and a test proving which.

## What this survives

The install split survives; the reason for it may not. It exists because of one library's build
situation on one Python version, and that will change. What should survive regardless is the
principle that a viewer's dependencies cannot be allowed to stop the analysis installing. A related
inconsistency has since been closed: the pinned numerical libraries need Python 3.12 or newer, while
the README and project metadata claimed 3.10 (S-09).

The settings rule gets more important as the project is handed on. The person flipping a setting next
year will not be the person who wrote the comment beside it, and they will have no way to tell a live
switch from a decorative one except by trusting what the file says.
