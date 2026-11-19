# Data diagnosis

> Problems found in the source data, how each was detected, what it does to the
> recommendation, ranked by risk. Risk ranking is provisional until the KPIs exist
> (stage 7) — a problem's rank is the size of its effect on the answer, and that
> cannot be known before there is an answer to move.
>
> **Status: all ten stages complete, and the clean-clone test passes.** F1–F5
> are from the candidate list itself,
> before any API call. F6 is from the acquisition. F7–F8 are from the flattened
> tables, F9 from the join, F10–F12 from the profile, F13 from the cleaning
> sensitivity runs, F14–F16 from the KPI tables, F17 from the time budget,
> F18 from the live spot-check, F19 from the clean-clone test. Findings that need distributions rather than counts — implausible
> money, unreliable ratings, real extremes versus errors — follow after stage 5.
>
> **Risk order as it stands: F12, F14, F7, F10, F11, then F15, F16, then F3,
> F6, F9, then F1, F2, F4, F8, F13.** F14 is ranked second because the obvious
> statistic reverses the recommendation. The top four are not data faults at all - they are limits on
> what this list can answer, and they outrank every fault found in it. F12 is
> first because it makes one of the team's two central claims untestable. F3,
> F6, F9 and F11 share a shape: the obvious handling is wrong in a way that
> leaves no trace in the output.
>
> Data as of **2026-11-19** (the `fetched_at` stamp on every envelope in
> `data/raw/`; the pipeline reads that date rather than today's, so a memo
> produced from cache cannot overstate how fresh its numbers are).

---

## The candidate list: full account

Detected by reading the file before parsing it (`Get-Content`, `Select-String`), then
confirmed by the stage-1 ledger, which holds one row per source row and never drops one.

| | Count |
|---|---|
| Lines in `id_list.csv` | 128 |
| Header row (`tmdb_id`, line 1) | 1 |
| **Data rows** | **127** |
| → **films fetched and available to the analysis** | **112** |
| → duplicate rows (same TMDb id as an earlier row) | 6 |
| → ids TMDb returns 404 for (F6) | 5 |
| → placeholders and a blank row (F2, F4) | 3 |
| → the same film under an IMDb id (F3) | 1 |

**127 = 112 + 6 + 5 + 3 + 1.** The counts reconcile exactly at every stage, and
the brief's figure of 127 matches the file's data-row count, so nothing went
missing between the brief and the file. Every line of this table is reproducible
from `data/processed/id_ledger.csv`, which carries one row per source row and a
reason on each row that did not make it.

**What the gap costs Kwame.** 15 of 127 rows (11.8%) carry no film the analysis can
use, but they are not 15 lost titles:

- **7 are not losses at all.** The 6 duplicates and the 1 IMDb id are films
  already in the 112. Removing them *prevents* double-counting rather than
  costing anything — and in the IMDb id's case prevents triple-counting a
  franchise film (F3).
- **8 are genuine losses**: 5 dead ids, 2 placeholders, 1 blank row.

So he is deciding on **112 titles instead of 120** — a 6.7% reduction. On the
evidence in F6 the 5 dead ids were probably never back-catalog films, which would
make the real loss 3 rows out of 115. What cannot be shown either way is whether
the 8 lost rows resemble the 112 that remain: there is no information left about
what they were. That limit belongs in the memo, and it is the honest version of
"no reason to think the missing titles are unlike the rest".

---

## F1 — Six duplicate rows · risk: **low** (resolved, no effect)

**Detected:** `ledger["tmdb_id"].duplicated(keep="first")` after parsing; visible before
parsing as repeated values in a sorted pass over the file.

**Rows:** 6 of 127.

| Duplicate at row | First occurrence | id |
|---|---|---|
| 43 | 40 | 603 |
| 60 | 27 | 278 |
| 90 | 55 | 1891 |
| 91 | 2 | 155 |
| 94 | 80 | 550 |
| 102 | 8 | 680 |

**Effect on the recommendation:** none, now. First occurrence kept, later ones flagged
`duplicate` in the ledger and never fetched. Had they been left in, each affected film
would have entered every KPI twice — inflating its weight in medians, hit rates and any
talent aggregate, and double-counting its revenue. The brief's "three sources merged over
four years" is exactly this, and it is the single most likely way an unexamined pipeline
would have produced a confidently wrong answer.

**Cost if wrong:** nil. Deduplication on an exact integer id is not a judgement call.

---

## F2 — Two placeholder values · risk: **low**

**Detected:** `Select-String -NotMatch "^[0-9]+$"`, then classified against a sentinel list.

**Rows:** 2 of 127 — row 30 is `-1`, row 111 is `N/A`.

**Why these are findings and not nulls:** both are *real values*. Neither would ever
appear in a null count, and `-1` would survive a naive `int()` conversion and be fetched
as if it were an id. They are a human's way of writing "I don't know", recorded in a
column that has no way to say so.

**Effect on the recommendation:** two fewer candidate titles. No measurable effect unless
those two films would have reached the shortlist, which cannot be known.

**Cost if wrong:** nil to correctness. These cannot be recovered — there is no id to
recover. They stay in the ledger as `invalid_id` so the count still reconciles.

---

## F3 — One IMDb id in a TMDb column · risk: **medium** (resolved; the hypothesis held)

**Detected:** `Select-String -NotMatch "^[0-9]+$"` — row 95 holds `tt0468569`.

**What it is:** an IMDb identifier, not a TMDb one. Wrong namespace, so it cannot be
fetched from `/movie/{id}`. TMDb's `/find/{external_id}` endpoint can resolve it.

**Why this is the interesting one.** The obvious fix — resolve it and add the film back —
is wrong here. It was resolved live at stage 2:

```
GET /find/tt0468569?external_source=imdb_id
  -> 155  'The Dark Knight'  2008-07-16
```

TMDb id **155** is **already on the candidate list twice**: row 2 (kept) and row 91
(flagged as one of F1's duplicates). So resolving row 95 would have added a **third**
copy of a film already counted, not recovered a lost one — turning a 2-row duplicate
into a 3-row one, in a franchise, which is precisely where a duplicate does most
damage to the franchise-versus-standalone comparison. The response is cached at
`data/raw/find_imdb_id__tt0468569.json`, so the identification is checkable rather
than asserted.

**Resolution:** the row carries status `duplicate_other_namespace` and a reason
naming the row it duplicates. It is excluded from the analysis and still accounted
for in the reconciliation.

**This is now a procedure, not a one-off.** `resolve_foreign_ids` in
`src/streamvault/fetch.py` handles all three outcomes, so next quarter's file gets
the same treatment without anyone remembering this paragraph:

| `/find` returns | What happens | Why |
|---|---|---|
| nothing | row stays `invalid_id` | nothing was lost that could have been recovered |
| an id already on the list | `duplicate_other_namespace`, excluded | recovering it would count one film twice |
| an id not on the list | recovered, queued, **flagged for the spot-check** | a genuine recovery, but its provenance is unlike every other row |

**Effect on the recommendation:** nil, which is the point. The pool is 112 films
either way; the wrong call would have put three copies of one franchise film into
every KPI.

**Cost if wrong:** this is the one row where the obvious action and the correct action
differ, which is why it is ranked above F1 and F2 despite affecting a single row. If
the identification had been wrong, one title would be missing from 112 — a 0.9%
reduction, and much the smaller of the two errors. Recorded as DR-05.

---

## F4 — One blank row · risk: **low**

**Detected:** `(Select-String "^$" id_list.csv).Count` → 1, at row 69.

**A note on detection.** The obvious check misses this. `grep -nv "^[0-9]*$"` reports
blank lines as *fine*, because `[0-9]*` matches zero or more digits and therefore matches
an empty line. `[0-9]+` is required. The row was found by a separate blank-line count, not
by the non-numeric check — a reminder that a check returning nothing is indistinguishable
from clean data until the check itself is tested.

**Effect on the recommendation:** none beyond one fewer candidate. Read with
`skip_blank_lines=False` so the row is counted rather than silently skipped; without that,
the file would have appeared to have 126 data rows and the reconciliation against 127
would have failed for the wrong reason.

---

## F5 — File-format characteristics · risk: **none** (handled)

**Detected:** `file` / `Format-Hex` on the raw bytes.

- **CRLF line endings.** Handled by `read_csv`'s universal newlines. Worth recording
  because hand-written shell checks are *not* immune: a `grep "^[0-9]+$"` against a CRLF
  file can fail on the trailing `\r`.
- **No byte-order mark.** Checked and absent. `encoding="utf-8-sig"` is used regardless,
  so a BOM in next quarter's file would not break the first id.
- **One column, as the brief states.** Verified; an extra column would be recorded in the
  ledger's attributes.

---

## F6 — Five ids TMDb has no film for · risk: **medium**

**Detected:** stage 2. Five of the 117 fetched ids returned HTTP 404. Recorded in
`data/processed/fetch_log.csv` and as `not_found_404` on the ledger; each 404
response is cached like any other, so reruns do not ask again.

**Rows:** 5 of 127.

| Source row | id |
|---|---|
| 18 | 8471293 |
| 35 | 9412887 |
| 73 | 8471294 |
| 93 | 9412888 |
| 99 | 7733901 |

**They are not random, and the pattern is unusually clean.** The five do *not*
cluster by position in the file — rows 18, 35, 73, 93, 99 are spread through it. They
cluster perfectly by id:

| | Smallest | Largest |
|---|---|---|
| The 112 ids that resolved | 11 | **301,528** |
| The 5 dead ids | **7,733,901** | 9,412,888 |

There is **no overlap at all**: not one working id exceeds 1,000,000, and the gap
between the two groups is a factor of 25. Two of the five are consecutive pairs —
`8471293`/`8471294` and `9412887`/`9412888`.

**What that means.** TMDb issues ids sequentially as entries are created, so an id in
the 7–9 million range belongs to an entry created far more recently than any genuine
back-catalog film's entry would have been. Consecutive pairs are what you get when
several entries are created in one sitting. The likeliest story is entries added to
TMDb, referenced by whichever of the three sources contributed these rows, and later
removed by TMDb moderation — ids are never reissued, so they 404 permanently.

**Effect on the recommendation:** 112 films analysed instead of 117. On this evidence
the five were probably never back-catalog films, which makes their loss *less* likely
to distort the franchise-versus-standalone comparison than a random loss of five
would be.

**The honest limit.** "Probably never films" is an inference from the id range, not a
check. Because a deleted entry leaves no title, no year and no collection, it is
**not possible** to test whether these five fall unevenly on pre-2000 films or on
franchises — the two splits the whole analysis turns on. This is the one gap in the
diagnosis that cannot be closed with more work, and it is stated in the memo rather
than smoothed over. Recorded as DR-06.

**Cost if wrong:** if all five were in fact pre-2000 standalones, the standalone side
of the comparison is thinner than it looks by five films. Five of 112 is 4.5%, enough
to move a median in a small group, which is why the stage-7 KPI tables report group
sizes beside every figure rather than percentages alone.

**At 500 titles:** re-run the same id-range check. It took one line and is the
cheapest bias test in the project.

---

## F7 — The standalone group is 16 films · risk: **high**

**Detected:** stage 3, by counting collection membership rather than assuming it.
This is not a data fault. Every value is correct. It is a property of the candidate
list that limits what the analysis can honestly conclude, and on current evidence it
is the largest risk to the recommendation — larger than every fault in F1–F6
combined.

**The split.** 96 of 112 films belong to a TMDb collection, but belonging to a
collection is not the same as being a bundle Kwame can buy. A collection with one
film on our list is not a bundle anyone is selling:

| Category | Films | Collections | What it means |
|---|---|---|---|
| **franchise** | **87** | 23 | in a collection with ≥2 of its films on our list — a real bundle |
| **lone_collection_member** | **9** | 9 | belongs to a franchise, but only one film of it is on offer |
| **standalone** | **16** | — | no collection at all |

And in Yaw's window the standalone group nearly halves again:

| Window | Films | franchise | lone member | standalone |
|---|---|---|---|---|
| All years (1966–2019) | 112 | 87 | 9 | **16** |
| 2000 onward | 71 | 59 | 4 | **8** |

**Why this is ranked above every data-quality finding.** The brief's central question
is franchise versus standalone. Answering it means comparing a group of 87 against a
group of **16** — and post-2000, 59 against **8**. A median over 8 films moves
materially if one film is added or removed, so the comparison Yaw cares about rests
on the least stable number in the project. Nothing in the cleaning or the KPI code
can fix that; only a larger candidate list could.

**What it does to the recommendation.** Three consequences, all of which belong in
the memo rather than in a footnote:

1. **Every statistic must be reported with its group size beside it.** A median with
   n=8 under it invites the right amount of scepticism; the same median alone does
   not. (This is why T7 asks for counts beside every statistic — now there is a
   concrete reason, not a convention.)
2. **The franchise-versus-standalone verdict will be directional, not precise.** "On
   this list, franchises show a higher floor" is supportable. "Franchises outperform
   standalones by X%" is not, with n=8 on one side.
3. **The list itself is evidence about the sourcing.** 78% of the candidates are
   franchise films. Whoever assembled it across three sources was already leaning
   toward bundles, which means the list cannot be used to argue that bundles are more
   available in the market — that would be reasoning from the selection back to the
   population.

**Cost if wrong:** nil to correctness; this is a limitation, not an error. The cost of
*not stating it* is a board making a $14M decision on a comparison whose weaker side
is eight films, believing it to be as solid as the 112-film headline suggests.

**At 500 titles:** re-check first. If the proportions hold, the standalone group grows
to roughly 70 and the comparison becomes properly stable — which is itself worth
telling Kwame, because it means the method improves with the next list rather than
needing to be rebuilt.

---

## F8 — The money fields are complete, which was not expected · risk: **none** (good news, verified)

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
were wrong (F4's `[0-9]*`, and the `Bearer` grep in the runbook). So: the counts above
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

## Stage 3 output: the four tables and their grains

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

## F9 — TMDb returns co-directors in inconsistent order · risk: **medium** (resolved)

**Detected:** stage 4, when collapsing the crew table to one row per film.

9 of 112 films have more than one credited director, and the order TMDb returns them
in is not stable across films:

| Film | Order returned |
|---|---|
| *The Matrix* (603) | Lana Wachowski, Lilly Wachowski |
| *The Matrix Reloaded* (604) | Lana Wachowski, Lilly Wachowski |
| *The Matrix Revolutions* (605) | **Lilly** Wachowski, **Lana** Wachowski |
| *Avengers: Infinity War* (299536) | Joe Russo, Anthony Russo |
| *Avengers: Endgame* (299534) | **Anthony** Russo, **Joe** Russo |

The other four are genuine co-directions (*Shrek*, *Shrek 2* with three directors,
*The Lion King*, *Pirates: Dead Men Tell No Tales*).

**Why it is a finding and not a quirk.** The obvious collapse — one director per
film, take the first row — produces an attribution that is arbitrary *and
inconsistent*, and the damage is not to a label but to who exists in the analysis:

| Collapse rule | Directors with ≥3 films (`talent.min_films_for_reliable`) |
|---|---|
| first row per film | **11** of 61 |
| both credited (chosen) | **13** of 66 |

The two that vanish are **Lana and Lilly Wachowski**: their 3-film partnership splits
into one film each, neither clears the threshold, and they are not reported as
unreliable — they are not reported at all. A talent recommendation would be made from
a list that silently lost one of its most consistent directing teams.

**Effect on the recommendation:** none, now. The film-level label is the sorted
partnership, identical across all three Matrix films, and per-director statistics come
from `directors.csv` at one row per film per director, where a shared film counts for
each of them. Recorded as DR-11.

**Cost if wrong:** crediting both directors counts a shared film's performance twice at
the person level, which must be disclosed whenever a co-director is named —
`n_directors` makes that possible. That is the better error: the alternative deletes
people from the analysis without saying so.

---

## Stage 4 output: the join, proven rather than assumed

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

## F10 - Pre- and post-2000 money are not the same unit, risk: **high**

**Detected:** stage 5, by computing the two windows side by side instead of pooling
them. Nothing is wrong with any value.

| Era | Films | Median budget | Median revenue | Median ROI |
|---|---|---|---|---|
| pre-2000 | 41 | $30,000,000 | $321,365,567 | **9.54** |
| 2000 onward | 71 | $150,000,000 | $738,599,701 | **4.92** |

Read naively, that table says pre-2000 films are **twice as profitable**. It does not
say that. Budget and revenue are **nominal** - the dollars of the year each film was
made - and the two columns inflate at different rates: median budget is 5.0x higher
post-2000 while median revenue is only 2.3x higher. A 1977 budget and a 2019 budget
are not the same unit, so their ratio to revenue is not comparable either.

There is a second, less obvious half. **An old film's revenue keeps accruing.** *Star
Wars* was re-released in 1978, 1981 and 1997, and TMDb reports lifetime revenue. So
the numerator includes decades of income earned in later, larger dollars while the
denominator is frozen at 1977 production cost. The older the film, the more its ROI is
flattered.

**What this does to the recommendation.** It is the strongest available answer to
**Yaw's claim (CL5)** that pre-2000 numbers cannot be trusted: he is right, and for a
reason more specific than "old data is bad" - the figures are accurate but not
*commensurable*. Any sentence of the form "older films return more" is measuring
inflation and re-release history, not licensing value.

**Decision (DR-12): compare within a window, never across one.** The brief already
asks for both windows; this is why that structure matters rather than being a
formality. No inflation adjustment is applied - it would need an external CPI series
the brief does not provide, and would still not fix the re-release problem.

**Cost if wrong:** if the effect is smaller than argued, the analysis loses nothing,
since both windows are reported either way. If it were ignored, the memo could tell
Kwame that the cheapest films to license are also the most profitable, which is partly
an artefact of measuring 1970s costs against 2020s receipts.

---

## F11 - Every extreme is pre-2000, so clipping outliers is not neutral, risk: **high** (methodological)

**Detected:** stage 5. Eight films have an ROI above 20x. **All eight are pre-2000:**

| Film | Year | ROI |
|---|---|---|
| Star Wars | 1977 | 70.5x |
| Jaws | 1975 | 67.2x |
| The Godfather | 1972 | 40.8x |
| The Good, the Bad and the Ugly | 1966 | 32.4x |
| The Empire Strikes Back | 1980 | 29.9x |
| Pulp Fiction | 1994 | 26.7x |
| Raiders of the Lost Ark | 1981 | above 20x |
| Back to the Future | 1985 | above 20x |

Years 1966 to 1994. Not one film from 2000 onward appears.

**Why this is a finding and not a list.** The routine move at this point is to
winsorise or drop the outliers to stop them dragging the averages. Here that move
would delete **8 of 41 pre-2000 films (20%) and 0 of 71 modern films (0%)**. An
"outlier treatment" applied to one era and not the other is not a cleaning step - it
is a thumb on the scale of the exact comparison Yaw is worried about, and it would
make pre-2000 films look systematically worse while appearing to be neutral hygiene.

**It is also the wrong films to delete.** A 70x return on a cheap 1977 film *is* the
back-catalog licensing case. Removing it to tidy a distribution removes the finding and
leaves a smoother table.

**Decision (DR-15): flag, classify, never clip.** All eight are recorded in
`data/processed/flags.csv` with the verdict `real_extreme` and a reason, they stay in
every metric, and stage 7 reports medians (resistant to them) alongside the counts.
They are forced into the stage-9 spot-check, because a figure this influential should
be verified against the live source rather than trusted.

**Cost if wrong:** if any of the eight is actually a bad figure, it inflates the
pre-2000 picture - which is why they are spot-checked by name instead of being assumed
correct. The reverse error, clipping them, is both larger and invisible.

---

## F12 - The list contains no film that lost money, risk: **high** (selection bias)

**Detected:** stage 5.

| | |
|---|---|
| Lowest ROI on the list | **1.13x** (*The Shawshank Redemption*, 1994) |
| Films with ROI below 1.0 (a theatrical loss) | **0** of 112 |
| Films with ROI below 1.5 | 2 |
| Films with ROI below 2.0 | 6 |

**Not one of the 112 candidate titles lost money at the box office.** Whoever
assembled this list across three sources selected successes - entirely reasonable for
an acquisition shortlist, and ruinous for one of the questions being asked of it.

**What it does to CL1.** The claim is that *"franchise bundles are the safer buy - a
higher floor and less spread."* A floor is a statement about what happens when things
go badly. On this list **nothing goes badly**, so the floor cannot be measured:
comparing the worst franchise film against the worst standalone film compares 1.86x
against 1.13x, both of which made money. The honest finding is that **CL1's central
argument is untestable on this data**, and no amount of analysis fixes it - only a
candidate list that includes failures would.

**What can still be said.** The *spread* of returns is measurable, and so is the
relative position of the two groups. "Franchise films on this list cluster more
tightly" is supportable. "Franchise films protect you from a flop" is not supportable
from this list at all.

**Knock-on effect on the hit rate.** With `hit_roi_threshold = 2.5`, **92% of the list
counts as a hit** - the metric barely discriminates, which is a direct symptom of the
same bias. Rather than fitting the threshold to make the numbers look interesting
(reasoning backwards from the answer), 2.5 is kept on its industry break-even
justification and stage 7 reports all three definitions - `roi >= 2.5` (92%),
`above_median` (50% by construction), `top_quartile` (ROI at or above 8.85) - with the
disagreement between them shown rather than hidden. See DR-14.

**Cost if wrong:** nil to correctness. The cost of not stating it is a board hearing
"franchises are the safer buy, and the data supports it" when the data contains no
instance of either option being unsafe.

---

## F13 - The direction of the answer is robust; its size is not, risk: **medium**

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
to treat (F8). That is reported as dormant rather than quietly left in place: a
setting that appears to be doing cleaning work while having no effect is a trap for
whoever reads this next quarter.

**Cost if wrong:** low. Every row of this table is reproducible from
`data/processed/sensitivity.csv` by flipping the named setting, so a sceptical reader
does not have to take the range on trust.

---

## F14 - The mean and the median disagree about who wins, risk: **high** (methodological)

**Detected:** stage 7, by reporting both and looking.

| Group | Films | **Mean** ROI | **Median** ROI | Lower quartile | Max | IQR |
|---|---|---|---|---|---|---|
| franchise | 87 | **7.94** | **5.53** | 3.91 | 70.5 | 4.39 |
| standalone | 25 | **10.48** | **5.00** | 2.64 | 67.2 | 11.71 |

**On the mean, standalones win. On the median, franchises win.** The choice of
statistic reverses the recommendation.

**Why.** The eight extreme-ROI films (F11) are not spread evenly: **3 of the 25
standalone films are extremes (12%) against 5 of 87 franchise films (5.7%)** - more
than twice the concentration, in the group one third the size. *Jaws* at 67x, *The
Good, the Bad and the Ugly* at 32x and *Pulp Fiction* at 27x drag the standalone mean
above the franchise mean while the typical standalone film sits *below* the typical
franchise film. The standalone IQR of 11.71 against 4.39 is the same fact seen from
another angle.

**What this does to the recommendation.** It is the reason the memo reports medians.
A mean-based analysis of this list - the obvious first thing anyone would compute -
would tell Kwame to buy standalone hits, on the strength of three films from the
1960s, 70s and 90s whose returns no current acquisition can replicate. The median
answers the question he actually asked, which is what a *typical* film in each group
returns.

**Cost if wrong:** this is a reporting choice, not an estimate, so there is nothing to
be wrong about - both statistics are in `kpi_all_years.csv` and a reader can see the
disagreement. The cost of not stating it is that the single most consequential number
in the analysis looks like a neutral default.

---

## F15 - The franchise spread advantage does not survive into Yaw's window, risk: **medium**

**Detected:** stage 7's flip check, which tests every measure rather than just the
median.

| Measure | Better is | All years | 2000 onward | Flips? |
|---|---|---|---|---|
| median ROI | higher | franchise | franchise | no |
| floor (lower quartile) | higher | franchise | franchise | no |
| hit rate | higher | franchise | franchise | no |
| **spread (IQR)** | **lower** | **franchise** | **standalone** | **yes** |

Across all years, franchise films are markedly tighter: IQR 4.39 against 11.71. In the
modern window the two groups are **2.47 against 2.297** - and standalone is nominally
the tighter one.

**Read carefully, because the arithmetic overstates this.** The margin is **0.17 ROI
points** on a standalone group of **12 films**. That is well inside what one film
entering or leaving would move. The defensible statement is that **the franchise
spread advantage disappears after 2000**, not that standalones become the safer buy.

**Why it still matters.** CL1 is specifically a claim about safety - floor and spread.
The floor half holds in both windows. The spread half, which is the stronger version
of the claim, is an all-years effect that does not reproduce in the window Yaw cares
about. And the all-years figure is itself inflated by F11: the standalone IQR of 11.71
is wide *because* three of its 25 films are pre-2000 extremes.

**Effect on the recommendation:** the direction is unchanged - franchises lead on
three of four measures in both windows - but the "less spread" argument should not be
made for modern titles. Flagged by the pipeline at every run, loudly, as the brief
asks.

**Cost if wrong:** low either way. Both windows are reported; the flip is stated with
its margin and its n, so a reader can discount it themselves.

---

## F16 - Two-thirds of the "weak middle entries" effect is the era confound, risk: **medium**

**Detected:** stage 7, by running the position analysis inside one era instead of over
the pooled list.

Pooled across all years, the pattern is striking and monotonic:

| Position | Films | Median ROI | Median revenue | Median rating |
|---|---|---|---|---|
| first | 22 | **7.76** | $454m | 7.87 |
| middle | 41 | **5.41** | $661m | 7.34 |
| last | 22 | **4.44** | $770m | 7.08 |

A 43% decline in ROI from opener to final entry - which looks like strong support for
the team's "we overpay for weak middle entries".

**But position correlates with era.** First entries have a median release year of
**2000** and are 50% pre-2000; last entries have a median year of **2008.5** and are
only 14% pre-2000. So the opener bonus is partly just F10: older films with nominal
budgets and lifetime revenue. Inside the modern window:

| Position | Films | Median ROI |
|---|---|---|
| first | 11 | **5.30** |
| middle | 27 | **5.05** |
| last | 19 | **4.55** |

The decline survives but shrinks from 43% to **14%** - roughly **two-thirds of the
apparent effect was the era**.

**And the culprit is not the middle.** Within one era, middle entries (5.05) sit
*above* last entries (4.55) and almost level with openers. The team's claim is
directionally right that later entries return less, and **wrong about which entries
are the weak ones**. Meanwhile revenue *rises* with position - a later entry earns
more and costs disproportionately more, which is why anyone looking at revenue alone
would conclude the opposite.

**Effect on the recommendation:** a bundle's later entries are worth less per dollar,
by about 14% from first to last within an era, not the 43% the pooled figure suggests.
That is a negotiating point, not a reason to avoid bundles.

**Cost if wrong:** the modern-window figures rest on 11, 27 and 19 films, so the 14%
is itself approximate; the pre-2000 breakdown has only 3 "last" entries and is not
reported as a finding for that reason. What is robust is the *direction* and the fact
that the pooled number is inflated.

---

## F17 - The first scaling measurement was wrong, and said so clearly, risk: **none** (caught)

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
check produced a confident wrong answer: `grep "^[0-9]*$"` on blank lines (F4), the
`Bearer` grep on cached films, and now a fitted exponent. The pattern is always the
same - the output looked plausible, so nothing prompted a second look. The projected
seconds looked fine; only the exponents gave it away.

**Effect on the recommendation:** none. The budget numbers in the memo come from the
corrected measurement, and both the fitted and the all-linear projections are
reported so the conclusion does not rest on the fit.

---

## F18 - The live re-check found no material difference, risk: **none** (verified)

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

## F19 - A clean clone could not install, and the earlier check had missed it, risk: **high** (fixed)

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
after `grep "^[0-9]*$"` on blank lines (F4), the `Bearer` grep on cached films, and a
fitted scaling exponent that came out negative (F17). The pattern has not varied: the
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

## The claim register: what has been tested so far

The claims in `docs/00_project_plan.md` Part 4 are what the team believes. Findings
are only worth anything once they are attached to one, so this is the running score.
Every row says which stage settles it, so nothing sits in "pending" by accident.

| | Claim | Status | What the evidence says |
|---|---|---|---|
| **CL6** | "The list has 127 titles" *(implicit)* | **Answered — false as meant, true as a row count** | The file holds exactly 127 data rows, so nobody miscounted. But 127 ≠ 127 *usable films*: 6 rows duplicate an earlier id, 1 is the same film under an IMDb id, 5 ids no longer exist on TMDb, 3 are placeholders or blank. The analysis runs on **112**. Anyone quoting "127 titles" to the board would be quoting a row count as a film count. (F1–F6) |
| **CL7** | "TMDb data is accurate enough to decide on" *(implicit)* | **Answered: yes, for this decision, with one stated limit** | Complete (112 of 117 ids resolve, all carry credits, no zero or missing money — F8), plausible (every extreme checked and classified; no impossible value — F11), and **faithful**: 15 films re-fetched live across four slices match on every material field, the only movement being one vote (F18). The limit: this tests our reading of the source, not the source's correctness, and is a weak test of drift because the cache was hours old. |
| **CL1** | "Franchise bundles are the safer buy" | **Answered: supported on the median and the floor, not on spread after 2000** | Franchise films lead on median ROI (5.53 v 5.00), lower quartile (3.91 v 2.64) and hit rate (95% v 80%) across all years, and on all three again in the modern window - in all six cleaning variants (F13). Two caveats: the *mean* reverses it (F14), and the spread advantage does not survive into the modern window (F15). The "no film ever fails" half remains untestable (F12). |
| **CL2** | "We overpay for weak middle entries" | **Answered: half right, and wrong about which half** | Later entries do return less: within one era, first 5.30, middle 5.05, last 4.55. But **middle entries are not the weak ones** - last entries are, and middles sit almost level with openers. And the pooled figure (7.76 / 5.41 / 4.44) overstates the effect roughly threefold, because openers are disproportionately pre-2000 films with inflated ROI (F16). 22 collections, 85 films. |
| **CL3** | "Cherry-picking standalone hits beats bundles" | **Answered on the numbers, with a large caveat** | The top standalones beat the top bundles per film: *Jaws* 67x, *The Good, the Bad and the Ugly* 32x, *Pulp Fiction* 27x against Star Wars' bundle ROI of 10.8. But **all three are pre-2000**, so the comparison is exactly the one F10 says is unsafe, and 2 of the 5 shortlisted "standalones" are lone collection members rather than true standalones (DR-20). Per *typical* film the claim fails: median standalone 5.00 against median franchise 5.53. |
| **CL4** | "Talent is a reliable lever" | **Answered: supported, for directors, with 13 names** | 13 directors have ≥3 films; 7 of them sit above the overall median ROI, led by Spielberg (8 films, median 13.25, hit rate 100%), Zemeckis (4, 10.32) and Cameron (3, 9.91). 19 lead actors clear the same bar. The lever is real but modest in reach: 13 of 66 directors, and every figure is reported with its film count because a 3-film record and an 8-film record are not the same evidence. Note F9: two of the 13 (the Wachowskis) exist only because co-directed films count for both. |
| **CL5** | "Pre-2000 numbers can't be trusted" *(Yaw)* | **Substantially answered - and he is right** | Not because the figures are wrong, but because they are not commensurable: nominal money inflates 5x on budgets against 2.3x on revenue, and old films keep accruing re-release revenue against a frozen budget (F10). Pre-2000 ROI is therefore flattered by construction. Compounding it: every extreme on the list is pre-2000, so routine outlier clipping would delete 20% of his window and none of the modern one (F11). Remaining limits: 8 standalone films post-2000 (F7), and the 5 dead ids have no year so F6's loss cannot be tested for era bias. |
| **CL8** | "The trilogy failed / the passed bundle was a miss" | Out of scope by design | Note only. The method should be able to score any bundle; proving Kwame's history is not this project's job. |

---

## Still to assess (requires stage 3 onward)

- Merged/redirected TMDb entries: two different ids returning the same film
- ~~Disguised nulls in the money fields: `budget == 0`, `revenue == 0`~~ — checked at
  stage 3, none found (F8)
- Implausible money values (a budget of `5`, reported in millions by mistake)
- ~~Non-feature entries: `adult`, `status != "Released"`~~ — checked at stage 3, none
  found (F8). Very short runtimes still to check as a distribution, not a flag
- ~~Films with no director or no cast~~ — checked at stage 3: all 112 have both
- Rating reliability: high `vote_average` on a handful of votes
- Whether any of the above falls unevenly on franchise vs standalone, or pre- vs
  post-2000 — which is what turns a tidiness problem into a risk to the recommendation
