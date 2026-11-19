# Data diagnosis

> Problems found in the source data, how each was detected, what it does to the
> recommendation, ranked by risk. Risk ranking is provisional until the KPIs exist
> (stage 7) — a problem's rank is the size of its effect on the answer, and that
> cannot be known before there is an answer to move.
>
> **Status: stages 1–4 complete.** F1–F5 are from the candidate list itself,
> before any API call. F6 is from the acquisition. F7–F8 are from the flattened
> tables, F9 from the join. Findings that need distributions rather than counts — implausible
> money, unreliable ratings, real extremes versus errors — follow after stage 5.
>
> **Risk order as it stands: F7, then F3, F6 and F9, then F1, F2, F4.** F7 is
> ranked first because it is the only one that limits what the analysis can
> conclude rather than how many films it runs on. F9 is ranked with F3 and F6
> because all three are cases where the obvious handling is wrong in a way that
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

## The claim register: what has been tested so far

The claims in `docs/00_project_plan.md` Part 4 are what the team believes. Findings
are only worth anything once they are attached to one, so this is the running score.
Every row says which stage settles it, so nothing sits in "pending" by accident.

| | Claim | Status | What the evidence says |
|---|---|---|---|
| **CL6** | "The list has 127 titles" *(implicit)* | **Answered — false as meant, true as a row count** | The file holds exactly 127 data rows, so nobody miscounted. But 127 ≠ 127 *usable films*: 6 rows duplicate an earlier id, 1 is the same film under an IMDb id, 5 ids no longer exist on TMDb, 3 are placeholders or blank. The analysis runs on **112**. Anyone quoting "127 titles" to the board would be quoting a row count as a film count. (F1–F6) |
| **CL7** | "TMDb data is accurate enough to decide on" *(implicit)* | Partly answered, so far favourably | Completeness is established: 112 of 117 ids resolve, all 112 carry credits, and **no** film has a zero budget, zero revenue, missing runtime or missing release date (F8) — the disguised-null fault this was most likely to fail on is simply absent. Still open: whether present values are *plausible* (stage 5) and whether they match the live source (stage 9). |
| **CL1** | "Franchise bundles are the safer buy" | Pending — stage 7, **and already constrained** | The groups are now sized: 87 franchise films against 16 standalone, 59 against 8 post-2000 (F7). Whatever stage 7 finds, this claim can be answered directionally and not precisely. Note too that F3 would have put a third copy of one franchise film into every KPI — the direction that would have *flattered* this claim. |
| **CL2** | "We overpay for weak middle entries" | Pending — stage 7 | Precondition now met: 23 collections carry ≥2 films on the list, sized 2 to 8 (Harry Potter 8, Star Wars 6, Pirates 5, Mission: Impossible 5). Position-within-series is computable from `release_date`, which is present for all 112 films. |
| **CL3** | "Cherry-picking standalone hits beats bundles" | Pending — stage 7 | Weakly answerable at best: "the top standalones" would be chosen from a pool of 16, and `shortlist.n_standalones = 5` means picking the top 5 of 16. That is cherry-picking from a thin list, and the claim's own logic makes the thinness matter. |
| **CL4** | "Talent is a reliable lever" | Pending — stage 7, **pool now known** | 66 directors across 122 director credits, of whom **13 have ≥3 films** on the list (Spielberg 8, Nolan 7, Jackson 6, then ten more) — so the claim is testable, on 13 names and not on one or two. Every film has a billed lead and at least one director. Note F9: two of those 13 exist only because co-directed films are credited to both directors. |
| **CL5** | "Pre-2000 numbers can't be trusted" *(Yaw)* | Pending — stage 7, both windows | Both windows are viable: 41 films pre-2000, 71 from 2000 on, spanning 1966–2019. But Yaw's window is where F7 bites hardest — 8 standalone films — so the honest answer may be that his concern cannot be *settled* either way on this list. Two obstacles are already known: the 5 dead ids have no year, so F6's loss cannot be tested for era bias. |
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
