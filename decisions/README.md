# Architecture Decision Records

One file per decision, in the house format: context, decision, alternatives with a reason each was
rejected, consequences including what it costs the client if I am wrong, and what the decision
survives. The template is in [`../docs/templates.md`](../docs/templates.md).

## These are not the brief's "Decision notes"

**These records are about how the system is built**, and they serve two of the rubric's criteria
rather than the reasoning one: acquisition that accounts for every id *without abusing a shared
API* (ADR-003, and the rate limiting and retry policy behind it), and an analysis that *runs top to
bottom from a clean clone* (ADR-002, ADR-013 — which exists because a clean clone could not
install).

**The brief's Decision notes deliverable is
[`../reports/decision_notes.md`](../reports/decision_notes.md).** The test it sets is: *can you say
what the recommendation looks like under the rejected alternative?* Most records here cannot — the
recommendation is identical whichever way the credential is sent — so they are not decision notes,
and filing them as such would bury the thirteen that are.

Four records here do pass that test and are indexed in the deliverable as well as listed below:
[005](ADR-005-imdb-id-excluded-as-cross-namespace-duplicate.md) (the alternative puts three copies
of one film on the franchise side of the central comparison),
[009](ADR-009-cleaning-adds-flags-and-exclusion-is-per-metric.md) (the alternative gives every
metric a different denominator), [004](ADR-004-the-briefs-title-count-is-a-claim.md) and
[006](ADR-006-a-404-is-a-finding.md). They are written up here in full rather than duplicated there.

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

**If you read four of these**, read [015](ADR-015-the-one-improvement-is-a-release-gate.md) — the
one addition beyond the brief, and the only check whose failure mode is "the board was misled";
[009](ADR-009-cleaning-adds-flags-and-exclusion-is-per-metric.md), which governs every number in the
project; [008](ADR-008-artefacts-are-read-back-with-explicit-dtypes.md), the fault class that costs
the most and shows the least; and
[014](ADR-014-the-memo-is-generated-not-written.md), on why the client-facing document cannot quote
a figure the data no longer supports.

## About the numbering

These were renumbered once, on 2026-11-19, straight after the analytical records moved out to the
decision notes. That left thirteen gaps in a run of thirty-three, and a sequence with more holes
than records is worse than one renumber done early, before anything outside the repository had
quoted a number. It was a deliberate exception and it is the only one.

**Three records were then withdrawn**, on 2026-11-20: 017 (regrouping the pipeline into five
stages), 018 (a stage with more than one job becomes a package) and 019 (putting the memo in the
house template). They documented reorganising this repository rather than decisions about the
client's problem, and none of them answered the question an ADR exists to answer — *why is the
system like this?* — except by recounting what it used to be like.

Nothing was lost. The conventions they described are stated as current fact in the project README
under "Layout and conventions". The memo's subject-line judgement moved to
[014](ADR-014-the-memo-is-generated-not-written.md), which already owns the memo. The one-page
shortfall moved to [`../docs/self_audit.md`](../docs/self_audit.md) as S-10, because it is a defect
in a deliverable rather than a decision, and that file is where this project's own defects live.

**From here the numbers are stable**: never reused, never renumbered, gaps left where a record is
withdrawn. A number in a commit message or a review note has to keep pointing at the same decision.

New decision? Copy the ADR section of [`../docs/templates.md`](../docs/templates.md) and take the
next number — 020. Never edit an accepted record to change its decision: write a new one that
supersedes it.
