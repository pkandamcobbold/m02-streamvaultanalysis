# Data diagnosis

> Problems found in the source data, how each was detected, what it does to the
> recommendation, ranked by risk. Risk ranking is provisional until the KPIs exist
> (stage 7) — a problem's rank is the size of its effect on the answer, and that
> cannot be known before there is an answer to move.
>
> **Status: stage 1 complete.** Findings F1–F5 below are from the candidate list
> itself, before any API call. Findings from the fetched data follow after stage 5.

---

## The candidate list: full account

Detected by reading the file before parsing it (`Get-Content`, `Select-String`), then
confirmed by the stage-1 ledger, which holds one row per source row and never drops one.

| | Count |
|---|---|
| Lines in `id_list.csv` | 128 |
| Header row (`tmdb_id`, line 1) | 1 |
| **Data rows** | **127** |
| → unique, valid ids queued for fetching | **117** |
| → duplicate rows (same id as an earlier row) | 6 |
| → unusable values | 4 |

**127 = 117 + 6 + 4.** The counts reconcile exactly, and the brief's figure of 127
matches the file's data-row count, so nothing has gone missing between the brief and
the file. Reproduce with `data/processed/id_ledger.csv`.

**What the gap costs Kwame:** 10 of 127 rows (7.9%) carry no usable id, but only 4 are
genuine losses — the other 6 are the same films listed twice, so no title is lost to
them. Whether the 4 are losses at all depends on F3 below. Worst case he is deciding on
117 titles instead of 120, a 2.5% reduction in the candidate pool, with no reason yet to
think the missing titles are unlike the rest. This is the smallest of the risks here.

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

## F3 — One IMDb id in a TMDb column · risk: **medium**, pending verification

**Detected:** `Select-String -NotMatch "^[0-9]+$"` — row 95 holds `tt0468569`.

**What it is:** an IMDb identifier, not a TMDb one. Wrong namespace, so it cannot be
fetched from `/movie/{id}`. TMDb's `/find/{external_id}` endpoint can resolve it.

**Why this is the interesting one.** The obvious fix — resolve it and add the film back —
may be wrong. `tt0468569` is believed to be *The Dark Knight*, and TMDb id **155**, also
*The Dark Knight*, is **already on the list twice**: row 2 (kept) and row 91 (flagged as
F1's duplicate). If that identification is right, resolving this row would add a **third**
copy of a film already counted, not recover a lost one — turning a 2-row duplicate into a
3-row one, in a franchise, which is precisely where a duplicate does most damage to the
franchise-versus-standalone comparison.

**Not yet verified.** This requires a live call, which has not been made. To resolve at
stage 2:

1. `GET /find/tt0468569?external_source=imdb_id` → read the returned TMDb id.
2. If it is 155, record as a **cross-namespace duplicate** and leave the row excluded.
3. If it is anything else, resolve it and add the film, flagging it for the stage-9
   spot-check since its provenance is unlike every other row.

**Effect on the recommendation:** if 2 is the case, excluding it is correct and the effect
is nil. If 3 is the case, one title returns. Either way the ledger accounts for the row.

**Cost if wrong:** this is the one row where the obvious action and the correct action may
differ, which is why it is ranked above F1 and F2 despite affecting a single row. Treating
it as a recoverable id without checking would silently triple-weight one franchise film.

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

## Still to assess (requires stage 2 onward)

- 404s: which ids are dead, and whether they cluster by source batch or era
- Merged/redirected TMDb entries: two different ids returning the same film
- Disguised nulls in the money fields: `budget == 0`, `revenue == 0`
- Implausible money values (a budget of `5`, reported in millions by mistake)
- Non-feature entries: `adult`, `status != "Released"`, very short runtimes
- Films with no director or no cast
- Rating reliability: high `vote_average` on a handful of votes
- Whether any of the above falls unevenly on franchise vs standalone, or pre- vs
  post-2000 — which is what turns a tidiness problem into a risk to the recommendation
