# Architecture Decision Records

One file per decision: what we chose, why, what we gave up, and the signal that would make us change
our mind. They are short on purpose. Each one maps to a stage of the pipeline, and the findings log
([`../findings.md`](../findings.md)) names the ADR that settled each finding.

Kwame Boateng was unavailable before the board review, so most of the business judgements here were
ours to make. Where a decision should have been the client's, the record says so and
[`../questions.md`](../questions.md) carries the question we would have asked.

| ADR | Decision | Stage |
| --- | --- | --- |
| [001](001-v4-bearer-token-in-a-header.md) | Authenticate with a v4 bearer token in a header, never a key in the URL | Extract |
| [002](002-raw-cache-is-not-committed.md) | Do not commit the raw API cache | Extract |
| [003](003-one-api-call-per-film.md) | One API call per film, with the two-call path kept runnable | Extract |
| [004](004-float-formatted-ids-are-recovered.md) | Recover `550.0` as `550`, only when the fraction is zeros | Extract |
| [005](005-the-briefs-title-count-is-a-claim.md) | The brief's "127 titles" is a claim to reconcile against, not an assertion | Extract |
| [006](006-imdb-id-excluded-as-cross-namespace-duplicate.md) | Resolve the IMDb id, then exclude it as a cross-namespace duplicate | Extract |
| [007](007-a-404-is-a-finding.md) | A 404 is a permanent answer; ask what the dead ids have in common | Extract |
| [008](008-cache-writes-are-atomic.md) | Cache writes are atomic; an unreadable entry is a cache miss | Extract |
| [009](009-artefacts-are-read-back-with-explicit-dtypes.md) | Every artefact is read back with explicit dtypes | Whole pipeline |
| [010](010-three-franchise-categories-not-two.md) | Three franchise categories, not two, with the threshold in settings | Transform |
| [011](011-crew-grain-is-one-row-per-credit.md) | The crew table is one row per credit, not per person | Transform |
| [012](012-a-co-directed-film-is-credited-to-both-directors.md) | A co-directed film counts for both directors | Transform |
| [013](013-money-is-compared-within-a-window-never-across-one.md) | Compare money within a window, never across one | Transform |
| [014](014-popularity-is-never-a-performance-measure.md) | TMDb `popularity` is never a performance measure | Transform |
| [015](015-the-hit-threshold-stays-at-break-even.md) | Keep the hit threshold at break-even; report all three definitions | Validate |
| [016](016-extremes-are-flagged-and-classified-never-clipped.md) | Flag and classify extremes, never clip them | Validate |
| [017](017-cleaning-adds-flags-and-exclusion-is-per-metric.md) | Cleaning adds flags; exclusion is per metric | Validate |
| [018](018-a-relative-measure-is-recomputed-inside-every-window.md) | Recompute every relative measure inside its own window | Transform |
| [019](019-medians-and-quartiles-not-means-and-standard-deviations.md) | Medians and quartiles, with the mean shown beside them | Transform |
| [020](020-the-flip-check-tests-every-measure.md) | The flip check tests every measure, not just the median | Transform |
| [021](021-the-shortlist-labels-what-each-pick-actually-is.md) | The shortlist carries each pick's franchise status | Transform |
| [022](022-position-within-a-franchise-is-read-inside-one-era.md) | Read the position-in-series effect inside one era | Transform |
| [023](023-acquisition-sits-outside-the-time-budget.md) | Acquisition sits outside the time budget, reported beside it | Checks |
| [024](024-the-500-title-projection-is-measured-not-multiplied.md) | The 500-title projection is measured per stage, not multiplied | Checks |
| [025](025-the-spot-check-re-fetches-into-a-separate-cache.md) | The spot-check re-fetches into a separate cache | Checks |
| [026](026-four-stratified-slices-not-a-random-sample.md) | Four stratified spot-check slices, not a random sample | Checks |
| [027](027-the-notebook-is-an-optional-install.md) | The notebook is an optional install | Whole project |
| [028](028-the-memo-is-generated-not-written.md) | The memo is generated from the measured results | Load |
| [029](029-the-one-improvement-is-a-release-gate.md) | The one improvement beyond the brief is a release gate | Checks |
| [030](030-a-settings-key-must-be-live-or-refuse-to-load.md) | A settings key must change behaviour, or refuse to load | Whole pipeline |
| [031](031-extraction-uses-a-loop-and-the-kpis-do-not.md) | Extraction loops over films; the KPIs never loop over rows | Extract |
| [032](032-five-stage-modules-in-a-flat-pipeline-package.md) | Five stage modules in a flat `pipeline/` package | Whole pipeline |

The ones that decide the answer rather than the plumbing are
**[010](010-three-franchise-categories-not-two.md)** (the central split),
**[013](013-money-is-compared-within-a-window-never-across-one.md)** (era comparability),
**[016](016-extremes-are-flagged-and-classified-never-clipped.md)** and
**[019](019-medians-and-quartiles-not-means-and-standard-deviations.md)** (which reverses the
recommendation), and **[017](017-cleaning-adds-flags-and-exclusion-is-per-metric.md)** (which
governs every number).

Two records carry an **open item** in their consequences:
[022](022-position-within-a-franchise-is-read-inside-one-era.md) (the within-era position figures are
hand-computed, not produced by code) and
[028](028-the-memo-is-generated-not-written.md) (three figures in the generated memo are hard-coded
prose). Both are in `docs/findings.md` as F21 and F22.

New decision? Copy [`template.md`](template.md) and take the next number. Never edit an accepted ADR
to change its decision: write a new one that supersedes it.
