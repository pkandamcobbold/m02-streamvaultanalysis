# Architecture Decision Records

One file per decision, in the house format: context, decision, alternatives with a reason each was
rejected, consequences including what it costs the client if I am wrong, and what the decision
survives. The template is in [`../docs/templates.md`](../docs/templates.md).

**These records are about how the system is built.** The judgements about what the numbers *mean* —
what counts as a series, why typical figures rather than averages, how the era problem is handled —
are in [`../docs/method.md`](../docs/method.md) as M1 to M13. They were in this directory and moved
out: thirty-three "architecture decisions" is not a set anyone reads, and the analytical ones
interlock, so they read better as one document than as thirteen files.

Kwame Boateng was unavailable before the board review, so most of the business judgements were mine
to make. Where a decision should have been the client's, the record says so and
[`../docs/questions.md`](../docs/questions.md) carries the question I would have asked.

| ADR | Decision | Stage |
| --- | --- | --- |
| [001](ADR-001-v4-bearer-token-in-a-header.md) | Authenticate with a bearer token in a header, never a key in the URL | Extract |
| [002](ADR-002-raw-cache-is-not-committed.md) | Do not commit the raw API responses | Extract |
| [003](ADR-003-one-api-call-per-film.md) | Fetch each film in one call, and keep the two-call version runnable | Extract |
| [004](ADR-004-the-briefs-title-count-is-a-claim.md) | Treat the brief's title count as a number to reconcile against, not one to crash on | Extract |
| [005](ADR-005-imdb-id-excluded-as-cross-namespace-duplicate.md) | Resolve the foreign identifier, then exclude it as a duplicate | Extract |
| [006](ADR-006-a-404-is-a-finding.md) | Record a missing film as a permanent answer, and ask what the dead ids share | Extract |
| [007](ADR-007-cache-writes-are-atomic.md) | Write cached responses atomically; an unreadable one is missing | Extract |
| [008](ADR-008-artefacts-are-read-back-with-explicit-dtypes.md) | Read every saved table back with its types declared | Whole pipeline |
| [009](ADR-009-cleaning-adds-flags-and-exclusion-is-per-metric.md) | Cleaning adds columns; a film leaves a metric, never the analysis | Validate |
| [010](ADR-010-acquisition-sits-outside-the-time-budget.md) | Keep fetching outside the time budget, and report it beside it | Checks |
| [011](ADR-011-the-500-title-projection-is-measured-not-multiplied.md) | Measure how each stage scales rather than multiplying the total | Checks |
| [012](ADR-012-the-spot-check-re-fetches-into-a-separate-cache.md) | The live check writes to its own cache | Checks |
| [013](ADR-013-the-notebook-is-an-optional-install.md) | Make the notebook an optional install | Whole project |
| [014](ADR-014-the-memo-is-generated-not-written.md) | Generate the memo from the measured results rather than writing it | Load |
| [015](ADR-015-the-one-improvement-is-a-release-gate.md) | Add a release gate that refuses to publish a memo nobody should act on | Checks |
| [016](ADR-016-a-settings-key-must-be-live-or-refuse-to-load.md) | A setting must change behaviour, or refuse to load | Whole pipeline |
| [017](ADR-017-five-stage-modules-in-a-flat-pipeline-package.md) | Regroup the pipeline into five stages in a flat package *(partly superseded by 018)* | Whole pipeline |
| [018](ADR-018-a-stage-with-more-than-one-job-is-a-package.md) | A stage that does more than one job becomes a package | Whole pipeline |

**If you read four of these**, read [015](ADR-015-the-one-improvement-is-a-release-gate.md) — the
one addition beyond the brief, and the only check whose failure mode is "the board was misled";
[009](ADR-009-cleaning-adds-flags-and-exclusion-is-per-metric.md), which governs every number in the
project; [008](ADR-008-artefacts-are-read-back-with-explicit-dtypes.md), the fault class that costs
the most and shows the least; and
[014](ADR-014-the-memo-is-generated-not-written.md), on why the client-facing document cannot quote
a figure the data no longer supports.

## About the numbering

These were renumbered once, on 2026-11-19, straight after the analytical records moved out to
`method.md`. That left thirteen gaps in a run of thirty-three, and a sequence with more holes than
records is worse than one renumber done early, before anything outside the repository had quoted a
number.

It was a deliberate exception and it is the only one. **From here the numbers are stable**: never
reused, never renumbered, gaps left where a record is withdrawn. A number in a commit message or a
review note has to keep pointing at the same decision.

New decision? Copy the ADR section of [`../docs/templates.md`](../docs/templates.md) and take the
next number — 019. Never edit an accepted record to change its decision: write a new one that
supersedes it, as 018 does to 017.
