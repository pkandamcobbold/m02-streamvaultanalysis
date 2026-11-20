# Architecture Decision Records

One file per decision, in the house format: context, decision, alternatives with a reason each was
rejected, consequences including what it costs the client if I am wrong, and what the decision
survives. The template is in [`../docs/templates.md`](../docs/templates.md).

Seven records. Each one holds a theme rather than a single switch, because the decisions within a
theme were taken together and reading them apart made them look smaller than they are.

## These are not the brief's "Decision notes"

**These records are about how the system is built**, and they serve two of the rubric's criteria
rather than the reasoning one: acquisition that accounts for every id *without abusing a shared
API* ([001](ADR-001-how-we-call-the-api.md), and the rate limiting and retry policy behind it), and
an analysis that *runs top to bottom from a clean clone*
([002](ADR-002-the-cache-is-disposable-evidence.md),
[007](ADR-007-dont-claim-a-capability-we-lack.md) — which exists because a clean clone could not
install).

**The brief's Decision notes deliverable is
[`../reports/decision_notes.md`](../reports/decision_notes.md).** The test it sets is: *can you say
what the recommendation looks like under the rejected alternative?* Most records here cannot — the
recommendation is identical whichever way the credential is sent — so they are not decision notes,
and filing them as such would bury the ones that are.

**[ADR-003](ADR-003-account-for-every-id.md) is the exception, and it is indexed from the
deliverable as well as from here.** It holds the four decisions that do pass that test — the brief's
title count, the foreign identifier, the dead ids, and cleaning as flags — and they are kept
together because they are one argument: every row of the input gets a verdict and a reason, and
nothing leaves the count silently. Under the rejected alternatives you get, in order: a pipeline
that stops for being correct about a new list size; three copies of one franchise film in every
figure; five rows written off without asking what they were; and a different denominator for every
metric.

Kwame Boateng was unavailable before the board review, so most of the business judgements were mine
to make. Where a decision should have been the client's, the record says so and
[`../docs/questions.md`](../docs/questions.md) carries the question I would have asked.

| ADR | Decision | Stage |
| --- | --- | --- |
| [001](ADR-001-how-we-call-the-api.md) | Call the API once per film, and never put the credential in a URL | Extract |
| [002](ADR-002-the-cache-is-disposable-evidence.md) | The cache is disposable evidence: not committed, written atomically, never overwritten by the live check | Extract, Checks |
| [003](ADR-003-account-for-every-id.md) | Account for every id: reconcile claims, never crash on them, and exclude from a metric rather than from the analysis | Extract, Validate |
| [004](ADR-004-declared-types-on-every-read.md) | Read every saved table back with its types declared, never inferred | Whole pipeline |
| [005](ADR-005-measure-the-pipeline-dont-extrapolate-it.md) | State the timing boundary, and measure how each stage scales rather than multiplying the total | Checks |
| [006](ADR-006-nothing-reaches-the-client-unchecked.md) | Generate the memo from the measured results, and gate its publication | Checks, Load |
| [007](ADR-007-dont-claim-a-capability-we-lack.md) | Do not claim a capability the project does not have: an optional notebook, and settings that work or refuse to load | Whole project |

**If you read three of these**, read
[006](ADR-006-nothing-reaches-the-client-unchecked.md) — the one addition beyond the brief, and the
only check whose failure mode is "the board was misled";
[003](ADR-003-account-for-every-id.md), which governs every number in the project and is where the
one place the obvious action and the correct action differ is written down; and
[004](ADR-004-declared-types-on-every-read.md), the fault class that costs the most and shows the
least.

## About the numbering

**These have now been renumbered twice, and the second time broke a commitment made here.**

The first renumber, on 2026-11-19, followed the analytical records moving out to the decision notes.
That left thirteen gaps in a run of thirty-three, and a sequence with more holes than records is
worse than one renumber done early, before anything outside the repository had quoted a number.
This file then said, in as many words, that it was *"a deliberate exception and it is the only
one"*, and that from then on numbers would never be reused or renumbered.

The second renumber, on 2026-11-20, merged sixteen records into these seven and renumbered them
1–7. That is the same exception a second time, and the rule it broke was mine. The reason is not
that the rule was wrong — it is the right rule — but that sixteen records averaging 570 words each
had become a list to be navigated rather than a set of decisions to be read, and the themes within
them were not separable: three records about the cache, four about accounting for a row. Merging
them meant renumbering, and doing it now was still cheaper than doing it after the submission was
marked.

What it cost: every citation in the code, the tests and the other documents had to be rewritten, and
any number quoted in a commit message before 2026-11-20 now points at the wrong record. The table
below is the only way to resolve those.

| Old | New | What it became |
| --- | --- | --- |
| 001, 003 | [001](ADR-001-how-we-call-the-api.md) | How we call the API |
| 002, 007, 012 | [002](ADR-002-the-cache-is-disposable-evidence.md) | The cache |
| 004, 005, 006, 009 | [003](ADR-003-account-for-every-id.md) | Accounting for every id |
| 008 | [004](ADR-004-declared-types-on-every-read.md) | Declared types on read — carried forward alone |
| 010, 011 | [005](ADR-005-measure-the-pipeline-dont-extrapolate-it.md) | Measuring the pipeline |
| 014, 015 | [006](ADR-006-nothing-reaches-the-client-unchecked.md) | What reaches the client |
| 013, 016 | [007](ADR-007-dont-claim-a-capability-we-lack.md) | Capabilities we do not claim |
| 017, 018, 019 | — | Withdrawn 2026-11-20, before this merge; see below |

Three records were withdrawn on 2026-11-20, separately from the merge: 017 (regrouping the pipeline
into five stages), 018 (a stage with more than one job becomes a package) and 019 (putting the memo
in the house template). They documented reorganising this repository rather than decisions about the
client's problem, and none of them answered the question an ADR exists to answer — *why is the
system like this?* — except by recounting what it used to be like.

Nothing was lost in either operation. The conventions those three described are stated as current
fact in the project README under "Layout and conventions". The memo's subject-line judgement is in
[006](ADR-006-nothing-reaches-the-client-unchecked.md), which owns the memo. The one-page shortfall
is in [`../docs/self_audit.md`](../docs/self_audit.md) as S-10, because it is a defect in a
deliverable rather than a decision. Every alternative, consequence and survival note from the
sixteen merged records is carried into the seven: 8,833 words against 9,096, and the difference is
sixteen headers.

**From here the numbers are stable, and this time there is no exception left to spend.** Never
reused, never renumbered, gaps left where a record is withdrawn. A number in a commit message or a
review note has to keep pointing at the same decision — and the honest reading of this section is
that the project said that once already and then did it again, so the next person has grounds to
check rather than trust.

New decision? Copy the ADR section of [`../docs/templates.md`](../docs/templates.md) and take the
next number — 008. Never edit an accepted record to change its decision: write a new one that
supersedes it.
