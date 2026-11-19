# Source material (reference copy)

> Reproduced so the repo is self-contained and the analysis can be audited against
> what was actually asked. Do not edit; if the brief is revised, add a dated note at
> the bottom rather than rewriting history.

---

## Part A — The lab brief

### Instructions

A client hands you a list of films under consideration for licensing and a decision worth $14M. Nobody hands you the data: you pull it yourself from a live public API, and it isn't clean.

The work is not "compute these numbers." It's deciding what the numbers should be, finding what's wrong with the source, and defending both to someone whose job depends on the answer.

### Background

StreamVault is a streaming service that licenses older films from studios alongside its own productions, the back catalog. Studios sell two ways: a franchise arrives as a bundle (take all six Space Raider films or none), while standalone hits are priced one at a time.

Candidate list: 127 titles this year, assembled over about four years from three sources: Adjoa's evaluation tracker, a spreadsheet inherited from Kwame's predecessor, and a batch a studio's licensing desk emailed over. Nobody has gone through it properly.

Next year's list is expected to be closer to 500 titles.

Kwame's analyst, Adjoa, will re-run this analysis every quarter, on her own laptop, sometimes live in a meeting.

Yaw in Finance distrusts anything released before 2000 (inflation, currency reporting, how box office used to be reported) and will say so in the room.

### Problem statement

Kwame Boateng, VP of Content Acquisition, has $14M to commit at the board's licensing review on 31 October, and no evidence to commit it with. His team argues constantly about how to spend it: half think franchise bundles are the safer buy, built-in audience, people binge the series, the marketing writes itself; the other half think StreamVault overpays for the weak middle entries and would do better cherry-picking standalone hits. Nobody brings numbers.

The stakes are personal. Two years ago Kwame championed a trilogy bundle on instinct; it underperformed, and the board remembers. Last quarter StreamVault passed on a five-film bundle that a competitor picked up and is now promoting; he doesn't know whether that was a bullet dodged or a miss. He's been told, politely, that without evidence this cycle the money moves to originals.

He wants:

- A recommendation he can defend in the room: franchise bundles or standalone hits, with the reasoning behind it.
- A shortlist to negotiate from: his three strongest franchise targets and five strongest standalones, each with the reason it made the cut.
- A read on which directors and lead actors reliably signal a title worth licensing; his negotiators use talent as a lever.
- A one-paragraph deal note on the single strongest franchise candidate: what to pay for it relative to everything else, and the one number that most drove your view.
- To be told plainly what you couldn't verify, and what that costs him. He'd rather hear it from you in October than from Finance in November.

### Resources given

`id_list.csv`: the candidate list, one column of TMDb movie ids, nothing else. You fetch everything yourself, live, from the public TMDb API: movie details (`GET /movie/{id}`) and credits (`GET /movie/{id}/credits`) for every title you use, both returned as nested JSON. Register your own free TMDb key. The data will contain problems this brief doesn't name; not everything that looks wrong is wrong.

### Constraints

- Present the franchise-versus-standalone comparison both ways, all years and 2000-onward, and if the recommendation changes between them, say so loudly rather than footnoting it.
- The solution has to scale: next year's list is expected to be closer to 500 titles, and Adjoa will run it herself, on her own laptop, without you. It shouldn't mean starting over.
- Kwame has no view on how you do any of this; the approach is yours to choose.
- Kwame is not available for follow-up questions before the review. Where the brief doesn't settle something, decide it, and say what you decided.

### Deliverables

- **Data diagnosis**: every problem found, how you detected it, and what it does to Kwame's recommendation, ranked by risk. A full account of the candidate list itself: how many titles made your final analysis, where the rest went, and what that gap costs him.
- **Working analysis**: runs top to bottom from a clean clone, no manual edits, and answers both time windows.
- **Decision notes**: every judgement call you made where the brief left something open: what you assumed, why, and what it costs him if you're wrong. State what survives when Adjoa reruns this next year against 500 titles without you.
- **Client memo**: one page, business language, no tool names or jargon. His recommendation, his shortlist, the two-window comparison, the deal note, and what you couldn't stand behind.
- **One improvement beyond the brief**: justified in terms of what it's worth to Kwame or Adjoa.

### Rubric

| Criterion | What's assessed | What "good" looks like | Weight |
|-----------|-----------------|------------------------|--------|
| Analyze | Data diagnosis | Finds the problems that actually move the recommendation, quantifies their effect, and ranks them by risk. Not a flat list of everything untidy, or a fix applied to nothing broken. | 20% |
| Apply | Acquisition | Pulls the full list without crashing or losing track of anything, without abusing a shared API; every id is accounted for and totals reconcile against what you were given. | 20% |
| Apply / Create | Analysis | Nested responses turned into a sound analytical shape, the join proven not to drop or duplicate a film, results computed without looping over rows, and inside the client's time budget, measured. | 20% |
| Evaluate | Reasoning | Every judgement call named, decided, and defended, with what it costs if you're wrong; rejected alternatives are real, and you can say what the recommendation looks like under them. | 20% |
| Evaluate / Create | What reaches the client | A memo Kwame could act on without a follow-up meeting, with the caveats a negotiator needs, plus one improvement beyond the brief that genuinely helps him or Adjoa, reasoned in terms of their problem. | 20% |

---

## Part B — The pipeline guide

### The pipeline, stage by stage

| Stage | What you do | Built from |
|-------|-------------|------------|
| 1. Load the id list | Read 127 ids with an explicit dtype; assert count and uniqueness; record the number you must reconcile against later. | Topics 1 and 5 |
| 2. Fetch details and credits | Session with timeout and retry policy; cache every raw response with a timestamp; record every id that 404s instead of crashing. | Topics 6 and 7 |
| 3. Flatten to tables | One table per grain, each stated in a comment: one row per film, one row per film per cast member. Rename generated columns once. | Topic 8 |
| 4. Join | Merge with `validate=` and `indicator=True`; assert the row count; use the indicator to account for every id. | Topic 9 |
| 5. Profile and diagnose | Run your profile function; list every fault including the disguised ones; separate real extremes from errors. | Topics 11 and 12 |
| 6. Clean, with a record per decision | Each decision parameterised so the metric can be computed both ways; each one written up in five parts and ranked by risk. | Topic 10 and its continuation |
| 7. Compute KPIs, both windows | Grouped, named aggregations with counts beside every statistic; all years and 2000 onward; say loudly if the recommendation flips. | Topics 4 and 13 |
| 8. Meet the budget | No row loops; time per stage with the acquisition excluded and the boundary stated; project the runtime to 500 titles. | Topics 3, 5 and 14 |
| 9. Spot-check against the API | Sample by the four slices; re-fetch live; classify every discrepancy; report whether any moves the recommendation. | Topic 7, second continuation |
| 10. Write the memo | Business language, no tool names, the recommendation, what would change it, and the as-of date of the data. | Everything above, plus Module 1 |

Two things about that order. It is not the order in which you will work — you will discover a fault at stage 5 and go back to stage 3 — but it must be the order in which your final code runs, top to bottom, from a clean clone, with no manual steps. And every stage produces something you keep: a count, an assertion, a decision record, a timing. Those artefacts are most of the lab's deliverables. They are cheaper to produce as you go than to reconstruct at the end from memory.

### What makes this lab hard, and it is not the pandas

The techniques in this book are learnable in a fortnight. What the lab actually tests is judgement under a silent brief. Kwame is unavailable, so where the brief does not settle something you decide and state what you decided. The data contains problems nobody has listed, and not everything that looks wrong is wrong. The comparison must be presented both ways and you must say loudly if the recommendation changes between them. Yaw in Finance distrusts anything before 2000 and will say so in the room. Adjoa must be able to re-run the whole thing next year on 500 titles without you.

Notice how many of those are not code problems. The analysis is the easy half, and a correct number that nobody trusts is worth nothing.

### Self-assessment against the five objectives

| Objective | You should be able to do this now | This is lab work |
|-----------|-----------------------------------|------------------|
| 1. Series and DataFrame operations fluently, end to end. | All of it. Construct, index by label and position, filter with masks, derive columns without mutating. | Sustaining it across a pipeline long enough that you stop remembering what each frame contains. |
| 2. Analyse data-quality faults and evaluate each cleaning decision by its analytical impact. | Detection: nulls, disguised nulls, duplicates of three kinds, mis-typed columns, outliers. Plus the five-part decision record as a method. | The evaluation half. Deciding whether a zero revenue is a gap or a flop, computing what your choice does to the recommendation, and defending it with nobody to ask. |
| 3. Parse nested JSON columns and merge disparate datasets on a shared key. | All of it. `json_normalize` with `record_path` and `meta`, a hand-written fallback, and a join you can prove with `validate=` and `indicator=`. | Choosing the grain for a question nobody has phrased precisely, and living with that choice through the whole analysis. |
| 4. Vectorised operations on grouped data, and KPIs within a hard performance budget. | The technique in full: grouping, named aggregation, vectorised alternatives to `apply`, and timing two implementations. | The budget. Meeting a stated limit, defining what the measurement covers, and designing for 500 titles rather than optimising after the fact. |
| 5. Evaluate pipeline output against a live external API spot-check and resolve discrepancies. | The calling half: reliable requests, retries, backoff, caching with timestamps. Plus the spot-check method. | Most of it, and this is the largest gap in the module. No resource teaches reconciliation. Finding a real discrepancy in your own output, classifying it and deciding what it means happens for the first time in the lab. |
