# Data diagnosis

> Problems found in the source data, how each was detected, what it does to the
> recommendation, ranked by risk. Risk ranking is provisional until the KPIs exist
> (stage 7) — a problem's rank is the size of its effect on the answer, and that
> cannot be known before there is an answer to move.
>
> **Status: stages 1–2 complete.** F1–F5 are from the candidate list itself,
> before any API call. F6 is from the acquisition. Findings from the *contents*
> of the fetched data — disguised nulls, implausible money, non-features —
> follow after stage 5.
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

## The claim register: what has been tested so far

The claims in `docs/00_project_plan.md` Part 4 are what the team believes. Findings
are only worth anything once they are attached to one, so this is the running score.
Every row says which stage settles it, so nothing sits in "pending" by accident.

| | Claim | Status | What the evidence says |
|---|---|---|---|
| **CL6** | "The list has 127 titles" *(implicit)* | **Answered — false as meant, true as a row count** | The file holds exactly 127 data rows, so nobody miscounted. But 127 ≠ 127 *usable films*: 6 rows duplicate an earlier id, 1 is the same film under an IMDb id, 5 ids no longer exist on TMDb, 3 are placeholders or blank. The analysis runs on **112**. Anyone quoting "127 titles" to the board would be quoting a row count as a film count. (F1–F6) |
| **CL7** | "TMDb data is accurate enough to decide on" *(implicit)* | Partly answered | What has been checked is *availability*, not accuracy: 112 of 117 ids resolve, and all 112 returned a credits block. Whether the money fields are plausible is stage 5; whether our figures match the live source is the stage-9 spot-check. |
| **CL1** | "Franchise bundles are the safer buy" | Pending — stage 7 | Nothing yet. Note for later: F3 would have put a third copy of one franchise film into every KPI, which is the direction that would have *flattered* this claim. |
| **CL2** | "We overpay for weak middle entries" | Pending — stage 7 | Needs collection membership and release order, which arrive at stage 3. |
| **CL3** | "Cherry-picking standalone hits beats bundles" | Pending — stage 7 | — |
| **CL4** | "Talent is a reliable lever" | Pending — stage 7 | Precondition met: credits are present for all 112 films, so no-one is excluded for want of data. Cast counts 9–177. |
| **CL5** | "Pre-2000 numbers can't be trusted" *(Yaw)* | Pending — stage 7, both windows | Nothing yet, and F6 is an honest obstacle: the 5 dead ids have no year, so the diagnosis cannot say whether the losses fall unevenly on pre-2000 films. |
| **CL8** | "The trilogy failed / the passed bundle was a miss" | Out of scope by design | Note only. The method should be able to score any bundle; proving Kwame's history is not this project's job. |

---

## Still to assess (requires stage 3 onward)

- Merged/redirected TMDb entries: two different ids returning the same film
- Disguised nulls in the money fields: `budget == 0`, `revenue == 0`
- Implausible money values (a budget of `5`, reported in millions by mistake)
- Non-feature entries: `adult`, `status != "Released"`, very short runtimes
- Films with no director or no cast
- Rating reliability: high `vote_average` on a handful of votes
- Whether any of the above falls unevenly on franchise vs standalone, or pre- vs
  post-2000 — which is what turns a tidiness problem into a risk to the recommendation
