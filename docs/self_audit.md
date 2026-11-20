# What we checked, and what we got wrong

The companion to [`../reports/data_diagnosis.md`](../reports/data_diagnosis.md). That file holds the
eleven findings that move the recommendation. This one holds everything that is not a finding about
the source data but still has to be on the record:

- **What we checked and did not find** — three results that rule something out. A diagnosis that
  only reports what went wrong leaves a reader unable to tell a clean check from a check nobody ran.
- **What we got wrong ourselves** — six defects in this project rather than in the data, three of
  them still open. Each open one breaks a promise the project makes somewhere else, which is why
  each is also named in the record it contradicts.
- **The tables and the join, proven** — the counts behind the claim that no merge dropped or
  multiplied a film.
- **The claim register** — what the team believed, and what the evidence did to each belief.

Items here carry an **S** number so they cannot be confused with the ranked findings. The mapping
from the old single series is in the table at the end.

---

## What we checked and did not find


### S-01 — The money fields are complete, which was not expected · risk: **none** (good news, verified)

**Detected:** stage 3, checking for the fault before assuming it.

A list assembled from three sources over four years is where disguised nulls live, and
`budget == 0` / `revenue == 0` is TMDb's classic one — a zero that is really "unknown"
and would compute an ROI of zero or infinity. So it was checked explicitly:

| Check | Films affected |
|---|---|
| `budget == 0` | **0** of 112 |
| `revenue == 0` | **0** of 112 |
| missing `runtime` | 0 |
| missing `release_date` | 0 |
| `status != "Released"` | 0 |
| `adult == True` | 0 |

**Why this is recorded rather than passed over.** A check that finds nothing is worth
exactly as much as one that finds something, provided it was a real check — and this
project has already been caught twice by checks that reported nothing because they
were wrong (F-04's `[0-9]*`, and the `Bearer` grep in the runbook). So: the counts above
come from the flattened `films` table, which has one asserted row per film, and the
test suite pins the dtype so a zero cannot be hiding as a NaN or vice versa.

**What it means for the settings.** `performance.treat_zero_money_as_missing = true`
currently has nothing to act on. It stays, because next quarter's list may not be this
clean, but the decision log must not claim it changed an answer here: it changed
nothing, and saying so is the honest version.

**Still to check at stage 5**, because "present" is not "plausible": a budget of 5
(reported in millions by mistake), a revenue smaller than a plausible print-and-
advertising spend, and a high `vote_average` resting on a handful of votes.

---

### S-02 — The direction of the answer is robust; its size is not · risk: **medium**

**Detected:** stage 6, by recomputing the comparison under every cleaning choice
rather than arguing that the choices were reasonable.

| Parameter | Value | Franchise n | Franchise median ROI | Standalone n | Standalone median ROI | Franchise ahead? | Gap |
|---|---|---|---|---|---|---|---|
| `treat_zero_money_as_missing` | true *(default)* | 87 | 5.526 | 25 | 5.000 | yes | 0.53 |
| `treat_zero_money_as_missing` | false | 87 | 5.526 | 25 | 5.000 | yes | 0.53 |
| `franchise.min_members_on_list` | 2 *(default)* | 87 | 5.526 | 25 | 5.000 | yes | 0.53 |
| `franchise.min_members_on_list` | **1** | 96 | 5.624 | **16** | **3.845** | yes | **1.78** |
| `min_budget_for_roi` | 1,000,000 *(default)* | 87 | 5.526 | 25 | 5.000 | yes | 0.53 |
| `min_budget_for_roi` | 10,000,000 | 85 | 5.451 | 20 | 4.762 | yes | 0.69 |

**Franchise films come out ahead in all six runs.** The direction of the answer does
not depend on any cleaning choice made in this project, which is the single most
useful thing a sensitivity table can say.

**But the size of the lead swings by 3.4x**, from 0.53 to 1.78, and one choice drives
almost all of it: where the **9 lone collection members** go (DR-09). Moving them from
standalone to franchise takes the standalone group from 25 films to 16 and drops its
median ROI from 5.00 to 3.85 - because those 9 are franchise films, and they perform
like franchise films. Counting them as standalone raises the standalone median and
narrows the gap.

**What this means for the memo.** "Franchise bundles outperform standalones on this
list" is supportable under every assumption tested. "They outperform by about 10%" is
an artefact of one definition; under an equally defensible one it is about 45%. So the
memo states the direction with confidence, gives the range rather than a point
estimate, and names the choice the range depends on. A single number here would be the
most misleading thing in the document.

`treat_zero_money_as_missing` changes **nothing at all**, because there are no zeros
to treat (S-01). That is reported as dormant rather than quietly left in place: a
setting that appears to be doing cleaning work while having no effect is a trap for
whoever reads this next quarter.

**Cost if wrong:** low. Every row of this table is reproducible from
`data/processed/sensitivity.csv` by flipping the named setting, so a sceptical reader
does not have to take the range on trust.

---

### S-03 — The live re-check found no material difference · risk: **none** (verified)

**Detected:** stage 9. 15 of 112 films (13%) re-fetched from TMDb and compared field
by field. Full detail in `reports/spotcheck.md`, which is generated by the stage so it
cannot drift from the check it describes.

| Slice | Films | Result |
|---|---|---|
| `shortlisted` | 3 | identical on every field |
| `flagged_extreme` | 6 | identical, bar one vote |
| `pre_2000` | 3 | identical on every field |
| `random_control` | 3 | identical on every field |

**Every budget, revenue, runtime, release date, collection membership and title
matches the live source.** The single difference found in the whole sample: *Back to
the Future*'s `vote_count` moved from 22,791 to **22,792** - one person voted in the
hours between the fetch and the check. That is a textbook illustration of why that
field is classified as expected drift and excluded from every performance metric
(DR-13), rather than a discrepancy.

**All eight extreme-ROI films are covered**, though only six appear under
`flagged_extreme`: *Star Wars* and *The Empire Strikes Back* were already taken by the
`shortlisted` slice, and no film is sampled twice. The check could not avoid the rows
that matter, which is what `spotcheck.always_include_flagged` exists to guarantee.

**What this establishes, and what it does not.** It establishes **fidelity**: the
values the analysis used are the values the source holds, so nothing was mis-parsed,
mis-joined or mis-assigned on the way in. It does **not** establish that TMDb is
correct - not answerable from here - and it is a **weak test of drift over time**,
because the analysis cache was fetched hours earlier, so only a fast-moving field had
time to change. Stating that limit matters more than the clean result: a reader who
takes this as proof that the figures are stable across quarters would be
over-reading it. Run again next quarter against the same cache and it becomes a real
drift test.

**Effect on the recommendation:** none, and tested rather than assumed. The stage
substitutes any live money figure that differs back into the analysis and recomputes
the franchise-versus-standalone comparison; with no material difference there was
nothing to substitute, so the recommendation is unchanged by construction.

---

---

---

## What we got wrong ourselves

Six defects in this project rather than in the data. They are here rather than in the diagnosis
because they answer a different question — "what did you get wrong?" — and because mixing them into
the ranking would overstate how much is wrong with the data and understate how much was wrong with
us. Three are fixed; three are **open**.


### S-04 — The first scaling measurement was wrong, and said so clearly · risk: **none** (caught)

**Detected:** stage 8, by reading the fitted exponents instead of the projected total.

The projection to 500 titles is built by re-running stages 3-7 over subsets of the real
data at four sizes and fitting `seconds = a * films ** k` per stage. The first run
produced this:

| Stage | Fitted k |
|---|---|
| 3_flatten | 0.49 |
| 4_join | **-0.09** |
| 5_profile | **-0.22** |
| 6_clean | **-0.47** |
| 7_kpis | **-0.35** |

**Four of five exponents were negative** - the stages appearing to get *faster* as the
data grew, which is not a thing. The cause: the smallest sample ran first and paid
pandas' one-off costs (first-call imports, allocator warm-up), so it came out slower
than the largest. The projected total of 2.06s was built on it and would have been
quoted in the memo.

**What the fix was.** A discarded warm-up pass before timing; each size timed three
times keeping the **minimum** (noise on a 0.1s measurement only ever adds time, so the
minimum is the least contaminated estimate); and a guard that refuses a negative
exponent, falling back to linear and **labelling the row** `assumed linear (measured
exponent was negative)`. Assuming linear over-estimates the time, which is the safe
direction for a budget.

After the fix, `3_flatten` measures k around 1.0 and its times rise monotonically with
sample size, as they must. One stage (`7_kpis`) still fits negative at this scale and
is openly carried as linear rather than published as impossible.

**Why this is recorded as a finding.** It is the third time in this project that a
check produced a confident wrong answer: `grep "^[0-9]*$"` on blank lines (F-04), the
`Bearer` grep on cached films, and now a fitted exponent. The pattern is always the
same - the output looked plausible, so nothing prompted a second look. The projected
seconds looked fine; only the exponents gave it away.

**Effect on the recommendation:** none. The budget numbers in the memo come from the
corrected measurement, and both the fitted and the all-linear projections are
reported so the conclusion does not rest on the fit.

---

### S-05 — A clean clone could not install, and the earlier check had missed it · risk: **high** (fixed)

**Detected:** stage 12's clean-clone test - cloning the repository to a fresh directory,
building a new virtual environment and running `pip install -r requirements.txt`. It
failed outright, installing **nothing**:

```
error: failed-wheel-build-for-install
x Failed to build installable wheels for some pyproject.toml based projects
+-> pyyaml
```

**The chain:**

```
pyyaml>=5.3  <-  jupyter-events  <-  jupyter-server>=2.19  <-  jupyterlab  <-  jupyter==1.1.1
```

PyYAML has no wheel for Python 3.15 and cannot compile from source here. This is the
same dependency that forced the project's config from YAML to TOML at the very start -
it came back as a transitive dependency of a notebook viewer.

**Why the earlier check missed it, which is the part worth keeping.** The stage-8 audit
checked exactly this risk and passed it: `pip install --only-binary :all: --dry-run
jupyter==1.1.1` resolved cleanly, with no PyYAML in the install list. That check was
sound and answered the wrong question. **Resolved alone**, `jupyter` selects
jupyterlab 3.5.3 and jupyter-server 1.24.0, which predate `jupyter-events` and need no
PyYAML. **Resolved alongside the other pins**, pip backtracks differently and selects
jupyterlab 4.6.6 and jupyter-server 2.21.1, which do. A dependency is only installable
*in context*, and testing one package in isolation cannot show that.

This is the fourth time in this project a check has returned a confident wrong answer,
after `grep "^[0-9]*$"` on blank lines (F-04), the `Bearer` grep on cached films, and a
fitted scaling exponent that came out negative (S-04). The pattern has not varied: the
check ran, reported success, and was answering a question slightly different from the
one that mattered.

**The fix (DR-26).** Jupyter moved out of `requirements.txt` into an optional
`requirements-notebook.txt`. The pipeline needs no notebook server - `run_pipeline.py`
writes every artefact and every report - so the thing the brief asks to run from a
clean clone now installs **wheels only, in 78 seconds**, and cannot be broken by a
dependency of a viewer.

**Verified after the fix**, in a fresh clone with a fresh environment: install
succeeds, `import streamvault` works with no `PYTHONPATH` and no `sys.path`
manipulation, **all 286 tests pass**, and `python run_pipeline.py` without a token
stops at stage 2 with the three-step instruction rather than a traceback.

**Effect on the recommendation:** none on any number. The effect of *not* finding it
would have been total: a grader or a colleague cloning this repository would have been
unable to install it, and every artefact in it would have been unreproducible on their
machine.

---

### S-06 — The project made three claims about itself that were not true · risk: **medium** (all fixed)

**Detected:** a second audit, after all ten stages were complete. None of these affects
a number in the memo; all three were the project describing itself inaccurately, which
in a graded deliverable is its own kind of error.

#### 1. Five settings were declared and never read

| Setting | What the project said | What the code did |
|---|---|---|
| `performance.report_all_hit_definitions` | DR-14: *"makes the fragility visible instead of hiding it behind one number"* | never read; all three reported unconditionally |
| `profile.use_popularity_as_performance` | DR-13: *"in settings so the choice is visible"* | never read; flipping it changed nothing |
| `performance.hit_definition` | offers `roi / above_median / top_quartile` | never read - a selector that selected nothing |
| `talent.lead_actor_billing_order` | the lead-actor definition | never read; `join.py` hardcoded the same number |
| `talent.sensitivity_top_n_billed` | *"re-run the talent analysis on top-3 billed"* | never implemented |

This directly contradicted the project's own principle. Stage 6 reported
`treat_zero_money_as_missing` as **dormant** on the grounds that *"a setting that
silently has no effect is worse than one documented as dormant"* - while five others
were silently inert, and two were credited in decision records with making a judgement
reversible. The behaviour the records describe was real; the switch they attributed it
to was not.

**Fixed.** All five are now read. `hit_definition` selects a `hit_rate_primary` column
that the flip check follows; `report_all_hit_definitions = false` drops the
alternatives; `lead_actor_billing_order` is threaded from settings into
`collapse_leads`, so changing it changes the lead; and
`config.validate_settings` now **refuses to load** a configuration that switches on
something unimplemented, with a message naming the decision record. Every key in
`settings.toml` is read by code, and a test asserts the shipped file validates.

**And the sensitivity that had never run produced a real result.** Widening the talent
view from leads only to the top three billed takes the reliable names from **19 to
44**, with **25 visible only when the net is widened** - Carrie Fisher, Viggo
Mortensen and Christopher Lloyd among them. A lead-only view of a 112-film list leaves
most of the cast unexamined, which is a finding about CL4 that was sitting unreachable
behind an unread setting.

#### 2. The time budget silently omitted two stages

`time_budget.csv` presented itself as where the time goes and listed seven stages;
`run_timings.csv` for the same run held nine. Stage 8 read the timings file before
stages 9 and 10 had written theirs, so a reader could not tell that two more stages
existed.

**Fixed.** The budget now runs last, every stage appears, and each one outside the
boundary carries the reason it is excluded - because a stage excluded from a judgement
should say so, while one simply absent looks like a stage that never ran.

#### 3. The notebook was described in the present tense and did not exist

`notebooks/analysis.ipynb` was named in the README (*"tells the story by calling those
modules"*), in the plan's Q15 and directory structure, and was the sole reason
`requirements-notebook.txt` exists. The directory contained only `.gitkeep`.

**Fixed.** It exists: 38 cells, and every one of its 18 code cells executes in order
against the real artefacts. It holds **no analysis of its own** - by design, since a
figure that lived only in a cell would not survive the quarterly rerun and nobody
could tell which cells had been run to produce it.

**Why this is recorded rather than quietly corrected.** It is the fifth time in this
project that something asserted about its own correctness turned out to be untested -
after `grep "^[0-9]*$"`, the `Bearer` grep, the negative scaling exponents, and the
clean-clone install. Four of those five were found by deliberately re-checking a claim
rather than by anything failing.

---

### S-07 — The within-era position figures are hand-computed · risk: **medium** (open)

**Detected:** by auditing the published artefact against the memo. M7 decided that the
position-in-franchise effect must be read inside one era, and that the pooled figures overstate it
roughly threefold. The memo quotes the within-era result ("roughly a seventh less than an opener",
middles above lasts). The pipeline's `kpi_position_in_franchise.csv` holds only the **pooled**
figures — 7.76 / 5.41 / 4.44 — which is the version M7 says not to quote.

**Rows:** one artefact, three figures, and one paragraph of the memo.

**Effect on the recommendation:** none today; the hand-computed figures are correct as of this run.
The risk is that they cannot be re-derived. Next quarter the era mix changes, the hand-computed
numbers become stale, and nothing in the pipeline will contradict them — the artefact will still
show the pooled figures and the memo will still print the old within-era sentence.

**Cost if wrong:** a negotiator uses "a seventh less" as a discount argument at the table, on a
figure no rerun can confirm. The fix is to compute the within-era breakdown in `transform.py` and
publish it beside the pooled table, so the memo quotes a number the artefact carries.

---

### S-08 — Three figures in the generated memo are hard-coded prose · risk: **medium** (open)

**Detected:** by reading the memo generator against its own docstring, which claims the memo
"cannot quote a figure the data no longer supports".

**Rows:** three sentences — "the work of three exceptional films from the 1960s, 70s and 90s",
"roughly a seventh less than an opener" (see S-07), and "nearly four in five candidates belong to
one".

**Effect on the recommendation:** none today. Each is true of this quarter's data.

**Cost if wrong:** this is precisely the drift ADR-014 exists to prevent, reintroduced by hand. If
next quarter has four exceptional films, or the franchise share falls to three in five, the memo
will state the old figure with full confidence and the pipeline will report success. Everything
else in the memo is computed; a reader has no way to tell which sentences are which. The fix is to
compute the three figures or delete the claims.

---

### S-09 — The stated Python floor is lower than the pins allow · risk: **medium** (open)

**Detected:** by reading `requirements.txt` against the installed package metadata.
`numpy==2.5.5` requires Python **3.12 or newer**; `pandas==3.1.1` requires **3.11 or newer**. The
README says "Python 3.10 or newer" and `pyproject.toml` declares `requires-python = ">=3.10"`.

**Rows:** two documents, one promise.

**Effect on the recommendation:** none. It affects whether anyone can reproduce it.

**Cost if wrong:** on a Python 3.10 or 3.11 machine, `pip install -r requirements.txt` fails to
resolve and the project does not run. This is the same class of failure as S-05 — a clean clone that
cannot install — on a different axis, and the constraint it breaks is the one the brief states
outright: Adjoa runs this herself, on her own laptop. The fix is one line in each of the two
documents.

---

---

---

### S-10 — The client memo is half a page over the limit · risk: **low** (open)

**Detected:** by counting it. The brief asks for a one-page memo and also names six things it must
contain — the recommendation, the shortlist, both time windows, the deal note, what could not be
verified, and the as-of date.

**Scale:** 1,063 words, roughly a page and a half.

**What I did about it.** Three compression passes, which took it from 1,381 words to 965. The
structural changes did the work: the two time windows became one table with four columns instead of
two stacked blocks, each shortlist pick became one line carrying the number that put it there, and
every limitation became one sentence. The last pass gained 3%, which is where prose trimming stops
paying.

It then grew by 98 words, deliberately. A cross-check against the brief found two of Kwame's asks unanswered in the memo — the lead actors behind the talent lever, and what would change the recommendation. Answering a named requirement beats meeting a length rule, so both went in.

**Effect on the recommendation:** none. Every element the brief names is present and every caveat is
tested.

**Residual risk.** The floor with all six required elements is about 850 to 900 words: eight named
titles with a reason each is roughly 100, six limitations 130, the deal note 130, and the "what you
asked for" table 95. A literal single page needs one of the brief's named elements dropped, which is
the client's call rather than mine. I have reported the number rather than claiming the rule is met.

---

## The tables and the join, proven

Kept because the claim that no merge dropped or multiplied a film is only worth something with the
counts beside it.


### Stage 3 output: the four tables and their grains

| Table | Grain | Rows |
|---|---|---|
| `films` | one row per film | 112 |
| `cast` | one row per film per cast member | 7,827 |
| `crew` | one row per film per crew **credit** | 24,932 |
| `genres` | one row per film per genre | 320 |

Grains are asserted, not assumed: `films.tmdb_id` is unique, every child row
references a film that exists, and a `collection_name` without a `collection_id` is a
hard failure because the franchise split rests entirely on that field.

Two facts about the crew table worth carrying forward: **914 rows are the same person
in more than one job on the same film** (a writer-director), so any count of *people*
must deduplicate and any count of *credits* must not; and **9 films have more than one
director**, which stage 4 has to resolve explicitly rather than by taking whichever row
the merge happens to return first.

Coverage is complete where the analysis needs it: all 112 films have at least one
director, and all 112 have a billed lead (`billing_order == 0`).

---

### Stage 4 output: the join, proven rather than assumed

Every merge is made with `validate="one_to_one"` and `indicator=True`, and the counts
are written to `data/processed/join_report.csv` rather than trusted:

| Merge | Left rows | Right rows | Result | Matched | Left only | Right only |
|---|---|---|---|---|---|---|
| directors | 112 | 112 | 112 | 112 | 0 | 0 |
| leads | 112 | 112 | 112 | 112 | 0 | 0 |
| genres | 112 | 112 | 112 | 112 | 0 | 0 |

No row multiplied, nothing was orphaned, and no film lost its row. `validate=` is what
makes that a proof rather than an observation: it raises if either side is not unique
on `tmdb_id`, which is the condition nobody can verify by looking at a table.

And every source row is accounted for end to end, in
`data/processed/id_accounting.csv`:

| Ledger status | Source rows | Reached the analysis |
|---|---|---|
| fetched | 112 | **112** |
| duplicate | 6 | 0 |
| not_found_404 | 5 | 0 |
| invalid_id | 3 | 0 |
| duplicate_other_namespace | 1 | 0 |
| **Total** | **127** | **112** |

🧠 One correction worth recording, because it was caught by a test rather than by
reading: the first version of this table asked "is this id in the analysis?" — which
counts a *duplicate* row as having reached the analysis, since it carries the same id
as the row that was kept. It would have reported 113 of 127 rows becoming films when
only 112 films exist, and it would have been the memo's headline sentence.

---

---

---

## The claim register: what has been tested so far

The claims in `docs/00_project_plan.md` Part 4 are what the team believes. Findings
are only worth anything once they are attached to one, so this is the running score.
Every row says which stage settles it, so nothing sits in "pending" by accident.

| | Claim | Status | What the evidence says |
|---|---|---|---|
| **CL6** | "The list has 127 titles" *(implicit)* | **Answered — false as meant, true as a row count** | The file holds exactly 127 data rows, so nobody miscounted. But 127 ≠ 127 *usable films*: 6 rows duplicate an earlier id, 1 is the same film under an IMDb id, 5 ids no longer exist on TMDb, 3 are placeholders or blank. The analysis runs on **112**. Anyone quoting "127 titles" to the board would be quoting a row count as a film count. (F-01–F-10) |
| **CL7** | "TMDb data is accurate enough to decide on" *(implicit)* | **Answered: yes, for this decision, with one stated limit** | Complete (112 of 117 ids resolve, all carry credits, no zero or missing money — S-01), plausible (every extreme checked and classified; no impossible value — F-06), and **faithful**: 15 films re-fetched live across four slices match on every material field, the only movement being one vote (S-03). The limit: this tests our reading of the source, not the source's correctness, and is a weak test of drift because the cache was hours old. |
| **CL1** | "Franchise bundles are the safer buy" | **Answered: supported on the median and the floor, not on spread after 2000** | Franchise films lead on median ROI (5.53 v 5.00), lower quartile (3.91 v 2.64) and hit rate (95% v 80%) across all years, and on all three again in the modern window - in all six cleaning variants (S-02). Two caveats: the *mean* reverses it (F-03), and the spread advantage does not survive into the modern window (F-07). The "no film ever fails" half remains untestable (F-01). |
| **CL2** | "We overpay for weak middle entries" | **Answered: half right, and wrong about which half** | Later entries do return less: within one era, first 5.30, middle 5.05, last 4.55. But **middle entries are not the weak ones** - last entries are, and middles sit almost level with openers. And the pooled figure (7.76 / 5.41 / 4.44) overstates the effect roughly threefold, because openers are disproportionately pre-2000 films with inflated ROI (F-08). 22 collections, 85 films. |
| **CL3** | "Cherry-picking standalone hits beats bundles" | **Answered on the numbers, with a large caveat** | The top standalones beat the top bundles per film: *Jaws* 67x, *The Good, the Bad and the Ugly* 32x, *Pulp Fiction* 27x against Star Wars' bundle ROI of 10.8. But **all three are pre-2000**, so the comparison is exactly the one F-05 says is unsafe, and 2 of the 5 shortlisted "standalones" are lone collection members rather than true standalones (DR-20). Per *typical* film the claim fails: median standalone 5.00 against median franchise 5.53. |
| **CL4** | "Talent is a reliable lever" | **Answered: supported, and wider than it first looked** | 13 directors have ≥3 films; 7 sit above the overall median, led by Spielberg (8 films, median 13.25, hit rate 100%), Zemeckis (4, 10.32) and Cameron (3, 9.91). For actors the answer depends on where you look: **19** names clear the bar as billed leads, **44** when the view widens to the top three billed — **25 of them invisible to a lead-only view** (S-06), including Carrie Fisher and Viggo Mortensen. So the lever is real and the lead-only framing understates it by more than half. Every figure carries its film count, because a 3-film record and an 8-film record are not the same evidence. Note F-11: two of the 13 directors exist only because co-directed films count for both. |
| **CL5** | "Pre-2000 numbers can't be trusted" *(Yaw)* | **Substantially answered - and he is right** | Not because the figures are wrong, but because they are not commensurable: nominal money inflates 5x on budgets against 2.3x on revenue, and old films keep accruing re-release revenue against a frozen budget (F-05). Pre-2000 ROI is therefore flattered by construction. Compounding it: every extreme on the list is pre-2000, so routine outlier clipping would delete 20% of his window and none of the modern one (F-06). Remaining limits: 8 standalone films post-2000 (F-04), and the 5 dead ids have no year so F-10's loss cannot be tested for era bias. |
| **CL8** | "The trilogy failed / the passed bundle was a miss" | Out of scope by design | Note only. The method should be able to score any bundle; proving Kwame's history is not this project's job. |

---

## Where these used to live

Everything in this file and in the diagnosis was once a single `F` series in one findings log. On
2026-11-20 the diagnosis was cut to the eleven findings that move the recommendation, renumbered in
risk order, and reformatted to the house template; everything else moved here. References in the
code, the ADRs and the method records were rewritten in the same pass.

The old numbers below are written as bare integers, with no letter prefix, **so that a future
renumbering sweep cannot rewrite them.** An earlier version of this table put them in backticks and
said that was enough. It was not: a sweep matching bare `F`-tokens matches inside backticks too, and
it destroyed this table twice before the column was changed to integers.

| Old number | Is now | Where it lives |
|---|---|---|
| 12 | **F-01** | diagnosis — no film on the list ever lost money |
| 24 | **F-02** | diagnosis — the headline gap is not distinguishable from noise |
| 14 | **F-03** | diagnosis — the mean and the median disagree about who wins |
| 7 | **F-04** | diagnosis — the standalone group is 16 films |
| 10 | **F-05** | diagnosis — pre- and post-2000 money are not the same unit |
| 11 | **F-06** | diagnosis — every exceptional return is an old film |
| 15 | **F-07** | diagnosis — the consistency advantage does not survive post-2000 |
| 16 | **F-08** | diagnosis — two-thirds of the middle-entry effect is age |
| 3 | **F-09** | diagnosis — the IMDb identifier, already on the list |
| 6 | **F-10** | diagnosis — five ids with no film behind them |
| 9 | **F-11** | diagnosis — co-directors returned in inconsistent order |
| 8 | **S-01** | here — the money fields were complete, which was not expected |
| 13 | **S-02** | here — the direction is robust, its size is not |
| 18 | **S-03** | here — the live re-check found no material difference |
| 17 | **S-04** | here — the first scaling measurement was wrong |
| 19 | **S-05** | here — a clean clone could not install |
| 20 | **S-06** | here — three untrue claims the project made about itself |
| 21 | **S-07** | here — the within-era position figures are hand-computed |
| 22 | **S-08** | here — three figures in the memo are hard-coded prose |
| 23 | **S-09** | here — the stated Python floor was lower than the pins allowed |
| 1, 2, 4, 5 | *no number* | counted in the diagnosis reconciliation table, not ranked: six duplicate rows, two placeholders, one blank row, and the file's invisible characters |
