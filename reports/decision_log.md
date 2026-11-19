# Decision log

> **Superseded.** Every record here is now one file in [`../docs/adr/`](../docs/adr/README.md),
> rewritten to the ADR template (context, decision, alternatives, consequences, revisit when).
> DR-00 maps to ADR-001 and so on in order; the unnumbered loop record is ADR-031.
> This file is kept only until the migration is reviewed, and may be deleted.


> Every judgement call, in five parts: what we saw, what the real alternatives
> were, what we chose, what each option does to the numbers, and what it costs
> Kwame if the call was wrong.
>
> Where part 4 cannot carry numbers yet, it says so and names the stage that
> will fill it. A decision record with an invented impact figure is worse than
> one that admits the measurement is still to come.
>
> **Status: all ten stages complete.** DR-00 to DR-29 below. DR-07 and DR-08 came
> out of an audit of stages 1–2 rather than from building them, and are kept
> because both were judgement calls with real alternatives. Cleaning and KPI
> DR-07, DR-08, DR-26 and DR-29 came out of auditing the work rather than
> building it, and are kept because each was a judgement call with real
> alternatives.

---

### DR-00: v4 bearer token, not a v3 API key — Risk rank: n/a (hygiene)

1. **Observation** — TMDb offers two credentials: a 32-character v3 key, normally
   passed as `?api_key=...` in the URL, and a v4 bearer token sent in an
   `Authorization` header. A key in a URL ends up in shell history, exception
   messages, server logs and any cached `request_path` we write to disk.
2. **Options** — (a) v3 key in the query string, which is what most tutorials
   show; (b) v4 bearer token in a header.
3. **Decision** — (b). The token is read from `.env`, which is gitignored, and
   is attached once to a `requests.Session` header.
4. **Impact** — none on any number. The guarantee is testable rather than
   asserted: `test_token_never_reaches_the_url_or_the_cache_file` checks that
   no request URL and no cached envelope contains the token, the string
   `Bearer`, or `api_key`.
5. **Cost if wrong** — a leaked credential in a graded repository that is
   cloned and re-run by someone else. Unrecoverable once pushed; revoking is
   the only remedy. At 500 titles this matters more, not less, because the
   pipeline is run by more people.

---

### DR-01: the raw cache is not committed — Risk rank: n/a (hygiene)

1. **Observation** — stage 2 writes one JSON envelope per film to `data/raw/`.
   For 117 films that is a few MB; at 500 it is several times that, and it
   changes every time anyone re-fetches.
2. **Options** — (a) commit the cache so a clean clone needs no API call;
   (b) gitignore it and let a clean clone fetch for itself.
3. **Decision** — (b). `data/raw/*` is ignored, with `.gitkeep` negated so the
   folder survives the clone. The pattern is `data/raw/*` and not `data/raw/`
   because a pattern ending in `/` excludes the directory, git never descends
   into it, and the negation for `.gitkeep` is then never evaluated.
4. **Impact** — none on any number. A clean clone takes ~26s of fetching
   before the analysis runs, measured.
5. **Cost if wrong** — if committed, the repository carries a snapshot that
   silently ages and a reviewer cannot tell whether the memo's as-of date
   describes the data or the commit. The envelope's `fetched_at` is the
   defence either way.

---

### DR-02: one API call per film, not two — Risk rank: n/a (acquisition)

1. **Observation** — the brief names two endpoints, `/movie/{id}` and
   `/movie/{id}/credits`. TMDb also accepts
   `?append_to_response=credits`, which returns both in one response.
   117 films is 234 calls the briefed way, 117 the appended way; next year's
   ~500 titles is 1,000 against 500.
2. **Options** — (a) two calls per film, literally as briefed; (b) one call
   with `append_to_response`; (c) one call, with no way back.
3. **Decision** — (b), with (a) kept runnable behind `api.append_credits` in
   `config/settings.toml`. The rejected alternative is a flag, not a
   paragraph: it can be run and timed.
4. **Impact** — **measured from an empty cache: 117 calls for 117 films in
   20.3s.** A second run: **0 calls, 2.3s.** Both rows are in
   `data/processed/run_timings.csv`, which is appended to on every run rather
   than overwritten — a figure quoted in a report and held nowhere else is a
   memory, not a measurement. The briefed two-call path would issue 234 calls
   for the same data. Content is identical: all 112 films that returned 200
   came back with a credits block, cast counts 9 to 177, none empty.
   (An earlier note here said 114 calls in 26.4s; that run started with three
   films and the `/find` response already cached from the smoke test, so it
   measured neither path cleanly. Superseded by the figures above.)
5. **Cost if wrong** — if the appended credits block were ever truncated or
   absent, the talent analysis would quietly narrow. Guarded two ways: the
   fetch log carries `has_credits` per film and `assert_fetch` reports any 200
   without credits; and the cache filename differs between the two modes
   (`550__details_credits.json` vs `550__details.json`), so switching the flag
   can never serve a cached response that lacks what was asked for. At 500
   titles, scaling the measured 20.3s linearly, the appended path is roughly
   87s against ~174s. Stage 8 replaces that arithmetic with a measured
   projection; it is quoted here only to show the order of the difference.

---

### DR-03: `550.0` is recovered as `550` — Risk rank: low

1. **Observation** — the id column is read as text, so a value that passed
   through a float column upstream arrives as `550.0`. None appears in this
   quarter's file; the branch exists because the fault is one keystroke away
   and next quarter's file comes from the same three desks.
2. **Options** — (a) treat it as unparseable and drop the row; (b) recover it
   as the integer; (c) recover it only if the integer round-trips exactly.
3. **Decision** — (b) restricted to `^\d+\.0+$`, which is (c) by construction:
   only a fractional part of zeros is recovered, and the reason string records
   the recovery on that row of the ledger.
4. **Impact** — zero rows affected this quarter.
5. **Cost if wrong** — a recovered id is self-verifying: TMDb either 404s or
   returns a film whose title does not fit a back-catalog list, and either way
   the row is visible in the fetch log. A value like `550.7` is *not*
   recovered, because there is no honest way to choose between 550 and 551.

---

### DR-04: the brief's "127 titles" is a claim, not an assertion — Risk rank: low

1. **Observation** — the brief says 127 candidate titles. The file holds 128
   lines: one header and 127 data rows. They agree this quarter.
2. **Options** — (a) `assert data_rows == 127`, failing loudly on any
   difference; (b) report a mismatch as a finding and carry on, reconciling
   against what the file actually holds.
3. **Decision** — (b). `input.expected_id_count` lives in settings, and a
   mismatch prints a `RECONCILIATION NOTE` and is recorded in the diagnosis.
4. **Impact** — no mismatch this quarter, so no note was raised.
5. **Cost if wrong** — this is the decision that decides whether Adjoa's run
   works next year. The list is expected to reach ~500 titles; a hard assert
   would crash her pipeline for being *correct* about the new size, during a
   quarter when nobody remembers where the 127 came from. The risk of the soft
   check is the opposite one — a shrinking list going unnoticed — which the
   printed note and the diagnosis report exist to prevent. Both behaviours are
   pinned by tests (`test_count_mismatch_is_a_note_not_a_crash` and
   `test_matching_count_produces_no_note`).

---

### DR-05: the IMDb id in row 95 is excluded, not recovered — Risk rank: medium

1. **Observation** — row 95 holds `tt0468569`, an IMDb identifier in a column
   of TMDb ids. Detected by `Select-String -NotMatch "^[0-9]+$"` before
   parsing. One row of 127. **Resolved live** at stage 2 via
   `/find/tt0468569?external_source=imdb_id` → TMDb **155, *The Dark Knight*
   (2008-07-16)**. TMDb 155 is already on the candidate list **twice**, at
   source rows 2 and 91.
2. **Options** — (a) drop the row as unparseable, never asking what it was;
   (b) resolve it and add the film, the obvious fix; (c) resolve it, discover
   it is already present, and exclude it as a duplicate in a second id
   namespace.
3. **Decision** — (c), implemented as `resolve_foreign_ids` so it is a
   procedure rather than a thing someone remembers. The row carries status
   `duplicate_other_namespace` and a reason naming the row it duplicates.
4. **Impact** — the candidate pool is unchanged at 112 analysed films either
   way, but option (b) would have put **three copies of one film** into every
   KPI. *The Dark Knight* belongs to a franchise, so the triple weight would
   have landed squarely on the franchise side of the central comparison —
   inflating the franchise median, the franchise hit rate and any talent
   aggregate touching Nolan or Bale. This is the single place in the data
   where the obvious action and the correct action differ.
5. **Cost if wrong** — if the identification were wrong (it is not: the live
   response is cached at
   `data/raw/find_imdb_id__tt0468569.json` and names the film and its release
   date), one title would be missing from a pool of 112, a 0.9% reduction.
   That is the smaller error by a wide margin. The code handles the other
   outcome too: an IMDb id resolving to a film *not* otherwise on the list is
   recovered, queued for fetching and flagged for the spot-check, because its
   provenance is unlike every other row.

---

### DR-06: a 404 is a finding, and these five are not random — Risk rank: medium

1. **Observation** — 5 of the 117 fetched ids returned 404:
   `8471293, 9412887, 8471294, 9412888, 7733901`, at source rows 18, 35, 73,
   93 and 99. They do **not** cluster by position in the file. They cluster
   perfectly by id: every one of the 112 ids that resolved is **≤ 301,528**,
   and every dead id is **≥ 7,733,901**. Not one live id exceeds 1,000,000, so
   there is no overlap at all — a gap of 25× between the two groups. Two pairs
   are consecutive (`8471293`/`8471294`, `9412887`/`9412888`).
2. **Options** — (a) retry them, on the theory that the fetch was at fault;
   (b) try to recover them by title search; (c) record them as permanently
   unavailable and ask what they have in common.
3. **Decision** — (c). 404 is deliberately excluded from the retry
   `status_forcelist`: a missing film is an answer, and retrying it five times
   is both slower and rude to a shared service. The 404 is cached like any
   other response, so reruns do not ask again.
4. **Impact** — 112 films analysed instead of 117. TMDb ids are issued
   sequentially, so an id in the 7–9 million range belongs to an entry created
   far more recently than any genuine back-catalog film's entry, and the two
   consecutive pairs suggest entries created back-to-back and later removed by
   TMDb moderation. These five ids were therefore almost certainly never
   back-catalog films at all — which means the 5 lost rows are **less likely**
   to bias the franchise-versus-standalone comparison than a random loss of 5
   would be.
5. **Cost if wrong** — unrecoverable either way: a deleted TMDb entry leaves
   no id to resolve and no title to search for, and ids are never reissued, so
   these five will 404 forever. The honest limit, which belongs in the memo:
   because nothing is known about what these five entries *were*, it is not
   possible to test whether the loss falls unevenly on pre-2000 films or on
   franchises. The id-range evidence makes a back-catalog film unlikely, but
   "unlikely" is not "checked". At 500 titles this check must be re-run, and
   the same id-range test is the cheapest way to do it.

---

### DR-07: a cache write is atomic, and a corrupt entry is a miss — Risk rank: low (robustness)

1. **Observation** — found by auditing stage 2, not by it failing. `write_text`
   is not atomic, so a run interrupted mid-write leaves a truncated JSON file.
   Reproduced by truncating one cache file: the next run raised
   `JSONDecodeError` naming neither the film nor the remedy, **and every run
   after it did the same**, because nothing ever rewrote the bad file. The
   README told Adjoa "if a run is interrupted, just start it again" — true for
   a *missing* file, false for a half-written one.
2. **Options** — (a) leave it: the window is milliseconds wide; (b) write to a
   temp file and `os.replace`, and treat an unreadable entry as a cache miss;
   (c) checksum every entry on read.
3. **Decision** — (b). `os.replace` is atomic on Windows and POSIX, so a
   reader sees the whole old file or the whole new one. An unreadable entry is
   deleted, refetched, and reported as a note.
4. **Impact** — none on any number. The failure it prevents is total, not
   partial: the pipeline stops working until someone deletes a file by hand,
   and the traceback does not say which one.
5. **Cost if wrong** — (c) would also catch bit-rot, which `os.replace`
   does not. Not worth it: a corrupt payload that is still valid JSON would be
   caught by the stage-9 spot-check against the live API. At 500 titles the
   interruption window is four times longer, so this matters more, not less.

---

### DR-08: artefacts are read back with explicit dtypes — Risk rank: medium (latent)

1. **Observation** — also from the audit. `id_ledger.csv` holds `155`, but
   `pd.read_csv` on it returns `tmdb_id` as **float64**, because the column
   also holds blanks for rows with no id. Stage 1 spends 250 lines and 28
   tests ensuring `550` never becomes `550.0`, writes a correct file, and then
   the guarantee leaks at the file boundary. Nothing had broken yet only
   because nothing read the artefacts back yet; stages 3-10, the notebook and
   the spot-check all will.
2. **Options** — (a) rely on whoever reads it passing dtypes; (b) provide
   `load_ledger` / `load_fetch_log` / `timings.load` with explicit dtype maps
   and use them everywhere; (c) store artefacts as Parquet, which carries its
   own dtypes.
3. **Decision** — (b). (c) is technically better and wrong for this project:
   Adjoa and Yaw must be able to open these files in Excel and read them.
4. **Impact** — none on the current numbers; prevents a silent one later. The
   round trip is tested, including a test asserting that the *naive* read does
   return float64 — so if a future pandas fixes this, the test says so rather
   than leaving a redundant loader in place for years.
5. **Cost if wrong** — if a stage reads an artefact with a plain `read_csv`,
   every id gains `.0`, the API 404s on all of them, and the symptom appears
   stages away from the cause. That is the exact bug stage 1 was built to
   prevent, which is what makes it worth a decision record rather than a
   commit message.

---

### DR-09: three franchise categories, not two — Risk rank: **high** (this is the central split)

1. **Observation** — 96 of 112 films belong to a TMDb collection, but 9 of those
   are the *only* film of their collection on the candidate list. A collection
   with one film on offer is not a bundle anyone can sell. So the data has
   three groups, not the two the brief names: 87 franchise, 9 lone collection
   members, 16 true standalones (F7).
2. **Options** — (a) franchise = `belongs_to_collection is not null`, giving
   96 vs 16; (b) franchise = in a collection with ≥2 films on our list, and
   fold the 9 lone members into standalone, giving 87 vs 25; (c) keep all
   three categories and decide at the KPI stage, with the threshold in
   settings.
3. **Decision** — (c). `franchise.min_members_on_list = 2` controls it, and the
   9 lone members carry their own label so they can be moved either way
   without recomputing anything. Option (a) is the tempting one and it is
   wrong: it would count a film as a "bundle" when there is no bundle to buy.
4. **Impact** — directly changes the central comparison's group sizes:

   | Definition | Franchise | Standalone |
   |---|---|---|
   | (a) any collection | 96 | 16 |
   | (b) ≥2 on list, lone members → standalone | 87 | 25 |
   | (c) three groups *(chosen)* | 87 | 16, plus 9 reported separately |

   Stage 7 reports the headline comparison under (c) and a sensitivity row
   under (b), because moving 9 films out of a 16-film group changes it by 56%.
   No KPI numbers exist yet, so the impact cannot be given in performance
   terms until stage 7 — flagged there rather than guessed here.
5. **Cost if wrong** — if the 9 lone members really are franchise films that
   Kwame could buy individually, excluding them understates the franchise
   group by 10% and overstates nothing. If they are treated as standalones
   instead, a 16-film group becomes 25 and its median is pulled by films whose
   performance may owe everything to a franchise the list does not contain.
   The second error is worse, which is why the default is (c). At 500 titles
   the lone-member group should shrink proportionally — if it does not, the
   list is being assembled by picking single entries out of franchises, which
   is itself worth telling Kwame.

---

### DR-10: the crew grain is one row per credit, not per person — Risk rank: medium

1. **Observation** — 914 of 24,932 crew rows are the same person in more than
   one job on the same film: a writer-director, a producer-director. And 9 of
   112 films have more than one person credited as Director.
2. **Options** — (a) deduplicate to one row per person per film at stage 3,
   losing the jobs; (b) keep one row per credit and resolve the director
   question explicitly at stage 4; (c) keep credits and add a derived
   "primary director" column here.
3. **Decision** — (b). Stage 3 changes shape and nothing else — no filtering,
   no cleaning, no derived judgements — so that every judgement lives in one
   place with a record. The exception is the franchise label (DR-09), which is
   in `add_franchise_flags` and named as derived.
4. **Impact** — none yet by construction. It determines what stage 4 must
   handle: with 9 multi-director films, a naive merge would silently pick
   whichever row comes first and produce a director attribution that is
   arbitrary but looks authoritative.
5. **Cost if wrong** — (a) would have been the silent error. Deduplicating a
   writer-director to one row makes any count of *credits* wrong, while a
   count of *people* needs the deduplication — so both numbers have to be
   derivable from the same table, and only the per-credit grain allows that.
   A note is printed at every run so the 914 figure is never a surprise.

---

### DR-11: a co-directed film is credited to both directors — Risk rank: medium

1. **Observation** — 9 of 112 films have more than one credited director, and
   **TMDb returns co-directors in no fixed order**: `/movie/603` (*The Matrix*)
   lists Lana then Lilly Wachowski, `/movie/605` (*The Matrix Revolutions*)
   lists Lilly then Lana. The same is true of the Russo brothers on *Infinity
   War* and *Endgame*. Collapsing with `.first()` therefore credits the same
   partnership to different people on different films.
2. **Options** — (a) `.first()` — one director per film, whichever row arrives
   first; (b) pick the first *alphabetically* as "the" director; (c) a sorted
   partnership label on the film table, plus a long table at one row per film
   per director, so a shared film counts for each of them.
3. **Decision** — (c). The film-level `director_names` is the sorted
   partnership ("Lana Wachowski & Lilly Wachowski"), identical on all three
   Matrix films; `n_directors` marks the 9; and every per-director statistic
   is computed from `directors.csv`, never from the label.
4. **Impact** — **measured, and it decides who exists in the talent analysis.**
   With `talent.min_films_for_reliable = 3`:

   | Collapse rule | Directors clearing 3 films |
   |---|---|
   | (a) `.first()` | **11** of 61 |
   | (c) both credited *(chosen)* | **13** of 66 |

   The two lost under (a) are **Lana Wachowski and Lilly Wachowski** — a
   3-film partnership split into one film each, so neither clears the
   threshold and a consistent directing team disappears from the analysis
   entirely. Under (a) they are not reported as unreliable; they are not
   reported at all.
5. **Cost if wrong** — (c) credits each director with the full performance of
   a film they shared, so a partnership's record is counted twice at the
   person level. That is the right error to make: the alternative silently
   deletes people, and CL4 ("talent is a reliable lever") cannot be tested
   against a list that lost two of its most consistent names. Any
   recommendation naming a co-director must say the films were shared, which
   `n_directors` makes possible. A per-film statistic is unaffected either
   way — only the per-person view changes.

---

### DR-12: money is compared within a window, never across one - Risk rank: **high**

1. **Observation** - budget and revenue are nominal. Median budget is 5.0x
   higher post-2000, median revenue only 2.3x higher, so median ROI appears to
   halve across the boundary (9.54 pre-2000 against 4.92 after). And an old
   film's revenue is lifetime revenue: *Star Wars* was re-released in 1978,
   1981 and 1997, so its numerator accumulates later, larger dollars against a
   1977 denominator (F10).
2. **Options** - (a) pool all years and report one set of figures; (b) adjust
   to constant dollars with an external CPI series; (c) report each window
   separately and never compare a level across the boundary; (d) use only
   rank-based measures, which are scale-free.
3. **Decision** - (c), with (d) alongside it in stage 7 (medians and quartile
   positions rather than dollar levels). (b) was rejected: it needs data the
   brief does not provide, it would add a dependency to a pipeline that must
   run from a clean clone, and **it would not fix the problem** - deflating a
   lifetime revenue figure by the release-year CPI is still wrong, because the
   revenue was not all earned in the release year.
4. **Impact** - this is why the two windows exist. Pooled, the 41 pre-2000
   films would raise the apparent return of the whole catalog and, because 20 of
   those 41 are franchise entries from Star Wars, Indiana Jones and The
   Godfather, would specifically flatter the franchise side. Reported
   separately, each window is internally comparable. No cross-window ratio
   appears anywhere in the memo.
5. **Cost if wrong** - if inflation and re-release effects are weaker than
   argued, nothing is lost: both windows are reported regardless, and the
   reader can compare them while being told why that comparison is unsafe. The
   opposite error produces a confident sentence ("the cheapest films to license
   return the most") that is substantially an artefact of measuring 1970s costs
   against 2020s receipts. At 500 titles the effect grows, because a longer
   back catalog spans more eras.

---

### DR-13: TMDb popularity is never used as a performance measure - Risk rank: medium

1. **Observation** - `popularity` ranges from 0.46 to 85.70 on this list, and
   the top three are *Avengers: Endgame* (2019), *Interstellar* (2014) and
   *The Dark Knight* (2008). It is a rolling engagement score recomputed daily
   from recent page views, votes and watchlist adds.
2. **Options** - (a) use it as a demand proxy, which is tempting since
   licensing value is about future viewing; (b) use it only as a tie-breaker;
   (c) exclude it from every metric and keep it in the tables as fetched.
3. **Decision** - (c), with `profile.use_popularity_as_performance = false` in
   settings so the choice is visible rather than implied by its absence.
4. **Impact** - two reasons, and the second is the one that matters. It is
   **recency-biased**: a 2019 blockbuster outscores a 1966 classic by two
   orders of magnitude, so using it would rank exactly against the back catalog
   this project exists to evaluate. And it is **not reproducible**: the cached
   value is a snapshot, so re-running the analysis next month from the same
   cache would give a different answer from a fresh fetch, and neither would be
   wrong. Every other field used here (budget, revenue, runtime, votes) is
   fixed once a film is released.
5. **Cost if wrong** - current audience interest is genuinely relevant to a
   licensing decision and this discards it. Accepted, and stated in the memo as
   a limitation: the analysis measures historical performance, not present
   demand. A demand signal would need a source whose values do not move under
   the analysis, and that is a different project.

---

### DR-14: the hit threshold stays at break-even, and all three definitions are reported - Risk rank: medium

1. **Observation** - `hit_roi_threshold` was set to 2.5 at the planning stage
   as a box-office break-even rule of thumb and marked TO SET AFTER PROFILING.
   The profile shows **92% of the list clears it**, because the list contains
   no film that lost money (F12). The hit rate therefore barely discriminates
   between any two groups.

   | ROI threshold | Share of the list that counts as a hit |
   |---|---|
   | 2.0 | 95% |
   | **2.5** | **92%** |
   | 4.0 | 71% |
   | 5.0 | 59% |
   | 8.0 | 31% |

2. **Options** - (a) keep 2.5 and report the hit rate as-is; (b) raise the
   threshold until the metric separates the groups; (c) keep 2.5 for its
   external justification and report `above_median` and `top_quartile`
   alongside it, showing where the three disagree.
3. **Decision** - (c). (b) is the trap: choosing a threshold because it makes
   the numbers interesting is fitting the measure to the desired answer, and
   any figure chosen that way cannot survive the question "why 5.0?".
   2.5 keeps an answer to that question - it is roughly where a theatrical
   release breaks even after the exhibitor split and P&A - and
   `report_all_hit_definitions = true` makes the fragility visible instead of
   hiding it behind one number.
4. **Impact** - the hit rate is demoted from a headline metric to one of three,
   and the memo leads with medians and spread instead. `min_budget_for_roi`
   stays at 1,000,000 and is **inactive this quarter**: the smallest budget on
   the list is 1,200,000, so no film is excluded for ROI instability. It is kept
   as a guard for a future list containing a genuinely small film.
5. **Cost if wrong** - if 2.5 is too low for this catalog, the hit rate is
   uninformative - which is exactly what is being reported, so the reader is
   not misled. If it were tuned instead, the recommendation would rest on a
   threshold chosen after seeing its effect, and a sceptical board member
   asking "what happens at 4.0?" would get a different answer from the one
   presented.

---

### DR-15: extremes are flagged and classified, never clipped - Risk rank: **high**

1. **Observation** - eight films have an ROI above 20x, topping out at 70.5x
   (*Star Wars*). **All eight are pre-2000**, from 1966 to 1994 (F11).
2. **Options** - (a) winsorise at a percentile; (b) drop them as implausible;
   (c) keep every value and flag it with a verdict and a reason.
3. **Decision** - (c). Each flag carries one of four verdicts - `error`,
   `real_extreme`, `unreliable`, `check` - and a sentence saying why. All eight
   are `real_extreme`.
4. **Impact** - (a) or (b) would delete **8 of 41 pre-2000 films (20%) and 0 of
   71 modern films**. An outlier treatment that only ever fires on one era is
   not hygiene; it is a thumb on the scale of the comparison Yaw is already
   sceptical about, and it would make his window look worse while looking like
   routine cleaning. It would also delete the most informative rows on the
   list: a 70x return on a cheap 1977 film is the back-catalog case, not noise.
   Instead, stage 7 reports medians, which are resistant to extremes without
   removing them, with counts beside every figure.
5. **Cost if wrong** - if one of the eight is a bad figure, it inflates the
   pre-2000 picture. That is why all eight are forced into the stage-9
   spot-check by name rather than trusted: `spotcheck.always_include_flagged`
   exists for this. The reverse error is larger and leaves no trace - a clipped
   value looks exactly like a value that was never there.

---

### DR-16: cleaning adds flags, and exclusion is per metric - Risk rank: **high** (it governs every number)

1. **Observation** - some films will fail some checks. The question is what
   "cleaning" then means. A film with no usable budget cannot enter an ROI
   figure, but it is still a real film with a real rating, a real director and
   a real franchise status.
2. **Options** - (a) drop failing rows and analyse what is left; (b) impute the
   missing values; (c) keep every row and add columns saying what each film is
   eligible for.
3. **Decision** - (c). `in_money_metrics`, `money_quality` and
   `rating_reliable` are columns, not filters, and `assert_clean` hard-asserts
   that cleaning did not change the row count. ROI exists exactly where
   `in_money_metrics` is true and is NA everywhere else, so nothing downstream
   can average a ratio that was never valid.
4. **Impact** - no film is excluded from anything this quarter, so the measured
   impact is zero. The impact it *prevents* is the one that matters: under (a),
   each metric would quietly carry a different denominator and the memo's "112
   films" would stop being true halfway down the page. Under (b), an imputed
   budget would flow into ROI and be indistinguishable from a measured one.
5. **Cost if wrong** - (c) costs vigilance: every aggregation must respect the
   flags, and a reader who filters the table themselves could compute a figure
   over films that were never eligible. Mitigated by making ROI NA rather than
   zero, which makes the mistake raise or return NA rather than silently
   averaging. At 500 titles, with a messier list, this is the decision that
   keeps the accounting honest.

---

### DR-17: a relative measure is recomputed inside every window - Risk rank: medium

1. **Observation** - two of the three hit definitions are relative:
   `above_median` and `top_quartile` are defined against a pool. The analysis
   reports two windows (all years, and 2000 onward). Computing the flags once
   over all 112 films and reusing them for the 71 modern films compares those
   films against a median set partly by 1970s films - whose ROI is inflated by
   inflation and re-release revenue (F10).
2. **Options** - (a) compute once over everything and reuse, which is cheaper
   and reads as consistent; (b) recompute within each window; (c) drop the
   relative definitions and keep only the absolute threshold.
3. **Decision** - (b). `add_hit_flags` takes a frame and computes within it,
   and stage 7 calls it again for each window. (c) was rejected because the
   absolute threshold on its own is nearly useless here - 92% of the list
   clears it (F12).
4. **Impact** - on this data, computing pool-wide instead of per window moves
   films across the "above median" line in the modern window, and in one
   direction only: modern films are judged against a bar raised by older ones.
   A test pins the behaviour with a four-film case where the two methods
   disagree, because the bug produces no error and nothing in the output would
   show it.
5. **Cost if wrong** - the two methods answer different questions, and (b)
   answers the one the brief asks ("does the answer change in the modern
   window?"). If a reader wants "above the all-years median" for a modern film,
   that figure is still available by computing it on the full table - the
   choice is explicit rather than inherited.

---

### DR-18: medians and quartiles, not means and standard deviations - Risk rank: **high** (it decides the answer)

1. **Observation** - computed both ways, the two statistics disagree about the
   recommendation. Mean ROI: standalone **10.48**, franchise 7.94. Median ROI:
   franchise **5.53**, standalone 5.00. The eight extreme-ROI films (F11) are
   concentrated in the smaller group - 3 of 25 standalone films against 5 of 87
   franchise films - so the standalone mean is pulled above the franchise mean
   while the typical standalone film sits below the typical franchise film.
2. **Options** - (a) report means, the conventional default; (b) report means
   with the extremes winsorised; (c) report medians and quartiles, with the
   mean shown beside them so the disagreement is visible.
3. **Decision** - (c). Spread is the interquartile range rather than the
   standard deviation, for the same reason: an SD inflated by a 70x return says
   nothing about the typical gap between a good and a bad film in the group.
   (b) was rejected under DR-15 - clipping here would delete 20% of the
   pre-2000 films and none of the modern ones.
4. **Impact** - **it reverses the recommendation.** Under (a) the memo would
   advise buying standalone hits, on the strength of *Jaws*, *The Good, the Bad
   and the Ugly* and *Pulp Fiction* - three films from 1975, 1966 and 1994
   whose returns no current acquisition can replicate. Under (c) it advises
   franchise bundles. Both figures are published in `kpi_all_years.csv`.
5. **Cost if wrong** - the median discards information about upside, and upside
   is part of an acquisition case: a buyer who wants one spectacular title
   rather than a reliable slate is served better by the mean. That reader is
   given `max_roi` and the full shortlist rather than being argued with. What
   the median protects against is the opposite error, and it is the likelier
   one: taking a 1970s outlier as evidence about a 2027 licensing deal.

---

### DR-19: the flip check tests every measure, not just the median - Risk rank: medium

1. **Observation** - the brief asks whether the recommendation changes in the
   post-2000 window. The planned check compared one number per window. But CL1
   is a claim about *safety*, which is three measures: the floor, the spread
   and the hit rate. Checking only the median would have reported "no flip"
   while one of the claim's two halves had in fact reversed.
2. **Options** - (a) one check on the median; (b) check each measure and report
   them separately; (c) a single composite score combining them.
3. **Decision** - (b). Four measures, each with its own direction convention -
   and `iqr_roi` is explicitly marked `better_is: lower`, because a tighter
   group is the safer buy and reading it like a median inverts the answer.
   (c) was rejected: a composite would need weights nobody has a basis to
   choose, and would hide exactly the disagreement worth reporting.
4. **Impact** - it found one. Franchise films lead on median, floor and hit
   rate in both windows, and the **spread advantage flips** (F15): IQR 4.39 v
   11.71 across all years, 2.47 v 2.297 after 2000. Under (a) this would not
   have been reported at all.
5. **Cost if wrong** - four measures mean four chances to see a flip that is
   really noise, and this one is: a 0.17 margin on 12 films. Mitigated by
   reporting the margin and the n beside the flip rather than only the verdict,
   so the finding is stated as "the advantage disappears" and not "standalones
   are now safer".

---

### DR-20: the shortlist labels what each pick actually is - Risk rank: medium

1. **Observation** - under the default grouping, lone collection members count
   as standalone (DR-09). The top five "standalone" picks therefore include
   **Jaws** and **The Lion King**, both of which belong to a TMDb collection
   whose other films are not on our list.
2. **Options** - (a) present them as standalones, which the grouping says they
   are; (b) drop them from the standalone shortlist; (c) keep them and carry
   `franchise_status` on every row of the shortlist.
3. **Decision** - (c). They are legitimate picks - a single film Kwame can
   license on its own is exactly what the standalone side of the brief means -
   but calling *Jaws* a standalone without qualification is a sentence a board
   member could reasonably object to.
4. **Impact** - 2 of 5 selected standalones are lone collection members. The
   shortlist table carries the status, and the memo names it. The three true
   standalones among the picks are *The Good, the Bad and the Ugly*, *Pulp
   Fiction* and *Schindler's List*.
5. **Cost if wrong** - under (b) the standalone shortlist would be chosen from
   16 films rather than 25, making an already thin group (F7) thinner and
   excluding two of its strongest candidates for a reason that has nothing to
   do with whether they can be bought. Carrying the label costs a column.

---

### DR-21: the position-within-franchise analysis is read inside one era - Risk rank: medium

1. **Observation** - pooled across all years, ROI falls monotonically with
   position: first 7.76, middle 5.41, last 4.44. But first entries have a
   median release year of 2000 and are 50% pre-2000, while last entries median
   2008.5 and are 14% pre-2000. Position is confounded with era, and era
   inflates ROI (F10).
2. **Options** - (a) report the pooled figures, which support the team's claim
   most strongly; (b) report within-era figures only; (c) report both and name
   the confound.
3. **Decision** - (c), with the within-era figures as the ones quoted in the
   recommendation.
4. **Impact** - the decline shrinks from **43% to 14%** from opener to final
   entry, so roughly two-thirds of the apparent effect was the era. And the
   ranking changes: within one era, middle entries (5.05) sit *above* last
   entries (4.55), so the team's specific claim about *middle* entries is not
   supported even though the general direction is (F16).
5. **Cost if wrong** - the within-era groups are 11, 27 and 19 films, so the
   14% is approximate and is given as such. The pre-2000 breakdown has only
   three "last" entries and is deliberately not reported as a finding. Had (a)
   been reported alone, the team would have been told they were right and by
   three times the real margin - the most flattering and least useful outcome.

---

### DR-22: acquisition sits outside the time budget, and is reported beside it - Risk rank: low

1. **Observation** - a cold run spends **20.3s** fetching and **1.9s**
   analysing. Folding them together makes the analysis look twelve times
   slower than it is, and the combined figure would move with TMDb's latency
   and Adjoa's wifi rather than with this code.
2. **Options** - (a) one total, which is what a user experiences; (b) analysis
   only, acquisition excluded and unmentioned; (c) analysis as the budget,
   acquisition measured and reported immediately beside it.
3. **Decision** - (c). The boundary is stated in one place and carried into the
   memo: **stages 3-7, warm cache, one machine, single-threaded; acquisition
   excluded.** Stage 1 is reported too, outside the boundary, for
   completeness. `assert_budget` hard-fails if acquisition ever appears inside
   the budget, and checks the stage shares sum to 1.
4. **Impact** - the budget reads **1.9s against a 10s limit**, of which
   `3_flatten` is 64%. Acquisition is projected separately from the
   **cold-cache** run - 0.173s per call, so **86.6s at 500 titles** - because
   projecting from a cached run would promise 2 seconds and deliver ninety.
5. **Cost if wrong** - a reader who wants "how long until I see the memo on a
   fresh machine" needs both numbers added, roughly 107s at 500 titles. Giving
   them separately with the boundary named is what makes that addition
   possible; one blended figure would not be decomposable. (b) would have been
   the dishonest option: quietly excluding the expensive part.

---

### DR-23: the 500-title projection is measured, not multiplied - Risk rank: medium

1. **Observation** - the obvious projection is `measured x 500/112`. That
   assumes every stage scales linearly in films, and at least one plainly does
   not: stage 3 flattens **credit rows**, of which this list has 223 per film,
   while the small stages are dominated by fixed costs at this size.
2. **Options** - (a) multiply by the ratio of film counts; (b) fit a scaling
   exponent per stage from re-runs over subsets of the real data; (c) generate
   a synthetic 500-film dataset and run it.
3. **Decision** - (b), using subsets of the **actual** payloads. (c) was
   rejected because a synthetic film would carry a made-up cast size, which
   would make stage 3 look linear in films when it is linear in credit rows -
   the exact distinction the projection turns on.
4. **Impact** - fitted projection **3.6s** at 500 titles; all-linear
   assumption **4.5s**; limit 10s. Both are reported, so the conclusion holds
   whether or not the fit is right - which matters because the sub-linear
   exponents (k around 0.05 to 0.1 for join, profile and clean) are
   extrapolated five-fold beyond the measured range, and fixed costs will stop
   dominating somewhere before 500. `3_flatten` is the stage to watch: it is
   64% of the budget today and the only one that measures as linear.
5. **Cost if wrong** - the fit rests on four sample sizes and sub-second
   timings, which are noisy: exponents move by a few tenths between runs. That
   is why the all-linear bound is published beside it and why the conclusion
   is stated as "comfortably inside the limit under either assumption" rather
   than as a point estimate. F17 records the first attempt, which produced
   negative exponents and would have been quoted had the exponents not been
   read.

---

### DR-24: the spot-check re-fetches into a separate cache - Risk rank: medium

1. **Observation** - the check needs live values, which means a forced
   refetch. The obvious place to put them is `data/raw/`, where every other
   response lives.
2. **Options** - (a) force the refetch into `data/raw/`; (b) hold the live
   payloads in memory only; (c) write them to a separate
   `data/raw_spotcheck/`.
3. **Decision** - (c). Forcing into `data/raw/` would overwrite the
   `fetched_at` stamps the memo's as-of date rests on, and - worse - **would
   make any discrepancy disappear the moment it was found**: the next pipeline
   run would read the new values, recompute, and agree with itself. The check
   would be self-erasing. (b) was rejected because the live payloads are
   evidence: a reviewer should be able to see the response the check compared
   against, not just the verdict.
4. **Impact** - none on the numbers; it is what makes the check repeatable.
   `data/raw_spotcheck/*` is gitignored alongside `data/raw/*` for the same
   reasons (DR-01).
5. **Cost if wrong** - a second cache directory to explain, and a few MB on
   disk. Against that: the alternative is a check that cannot fail twice.

---

### DR-25: four stratified slices, not a random sample - Risk rank: medium (settles Q14)

1. **Observation** - the brief asks for a spot-check "sampled across four
   slices" without naming them, and the budget is 3 films per slice. A simple
   random sample of 12 from 112 would, with high probability, contain **none**
   of the eight extreme-ROI films that drive the analysis and none of the
   shortlisted titles the memo names.
2. **Options** - (a) a random sample, which is unbiased and would mostly check
   films nobody cares about; (b) check only the influential rows, which cannot
   detect a fault that is uniform across the list; (c) stratify: put the budget
   where an error would hurt, and keep one unbiased slice as a control.
3. **Decision** - (c), with the four slices chosen to match the findings:
   **shortlisted** (an error here is an error in the answer),
   **flagged_extreme** (the eight films from F11, *all* of them, because
   sampling the risky rows is not a check), **pre_2000** (Yaw's window, where
   money is least comparable - F10), and **random_control** (without it the
   check only looks where problems are expected). The sample is seeded, so a
   reviewer re-running it sees the same films and can tell a fixed fault from
   a new draw.
4. **Impact** - 15 films rather than the 12 the plan estimated, because taking
   all eight flagged films costs more than sampling three. Coverage 13% of the
   list, and 100% of the rows the recommendation leans on. `assert_spotcheck`
   hard-fails if the control slice is ever missing, unless the pool was small
   enough to be sampled entirely.
5. **Cost if wrong** - a stratified sample cannot support a statement about
   the error rate of the list *as a whole*; the control slice is three films,
   which is too few to estimate anything. So the report claims fidelity on the
   rows checked and does not extrapolate a rate. That is the honest trade: the
   alternative is an unbiased estimate of a number nobody asked for, computed
   by not checking the films that matter.

---

### DR-26: the notebook is an optional install - Risk rank: **high** (it decides whether the project installs at all)

1. **Observation** - the clean-clone test failed: `pip install -r
   requirements.txt` built nothing, because `jupyter` transitively requires
   PyYAML, which has no Python 3.15 wheel (F19). The audit's earlier check had
   passed because it resolved `jupyter` **alone**, where pip selects an older
   jupyterlab that predates the dependency.
2. **Options** - (a) pin jupyterlab and jupyter-server to the older versions
   that avoid `jupyter-events`; (b) drop the notebook from the project
   entirely; (c) move `jupyter` to an optional `requirements-notebook.txt` that
   the pipeline does not need.
3. **Decision** - (c). (a) would pin two transitive packages to versions pip
   does not want, which breaks again the next time anything else moves. (b)
   would discard the notebook narrative, which Q15 settled as part of the
   deliverable.
4. **Impact** - `pip install -r requirements.txt` now completes in **78
   seconds, wheels only**, and installs 10 packages instead of about 100. The
   notebook is one extra command, and `requirements-notebook.txt` says plainly
   that it may fail on Python 3.15 and that the pipeline is unaffected if it
   does. Verified end to end in a fresh clone: install, import with no
   `PYTHONPATH`, 286 tests passing, and the no-token path giving instructions
   rather than a traceback.
5. **Cost if wrong** - a reader who wants the notebook has to run a second
   command and may hit the PyYAML wall on this Python version. That is a
   documented inconvenience for one optional artefact. The alternative was a
   repository that could not be installed at all, which is the only failure in
   this project that would have made every other part of it worthless.

---

### DR-27: the memo is generated, not written - Risk rank: medium

1. **Observation** - the memo is the one artefact a non-programmer reads, and
   the one most likely to drift: a figure gets revised in the analysis and the
   sentence quoting it does not.
2. **Options** - (a) write it by hand from the final numbers; (b) generate the
   figures and hand-write the prose around them; (c) generate the whole
   document, with the judgement encoded as rules over the measured results.
3. **Decision** - (c). The recommendation follows from stated conditions -
   franchise leads on median, floor and hit rate in both windows, therefore
   recommend franchise-first; the spread advantage does not survive after 2000,
   therefore say so; a headline measure flips, therefore the flip becomes the
   first line instead of the recommendation. Change the data and the memo
   changes with it.
4. **Impact** - the memo cannot quote a figure the data no longer supports,
   and re-running the pipeline republishes it. The caveats are not optional
   either: tests assert that the mean-reversal disclosure (F14), the thin
   standalone group (F7), the era problem (F10), the absence of any failure on
   the list (F12) and the missing licensing prices all appear, and that no
   dollar price is ever named. A future edit that quietly drops a caveat fails
   the suite.
5. **Cost if wrong** - generated prose is less fluent than written prose, and
   a rule-based recommendation cannot exercise judgement the rules do not
   encode. Mitigated by keeping the rules few and the conditions explicit, and
   by the fact that a human still chooses what the rules are. The failure this
   avoids is worse than stiff prose: a memo that reads beautifully and quotes
   last week's number.

---

### DR-28: the one improvement is a release gate - Risk rank: n/a (the improvement)

1. **Observation** - everything in this project protects the analysis from
   being wrong. Nothing protected Adjoa from the analysis being wrong *and
   looking fine*. She reruns it quarterly, on a laptop, sometimes live in the
   meeting, and the pipeline is deliberately built to carry on rather than
   crash (DR-04, DR-16) - so a truncated input list or a half-missing money
   column would still produce a confident one-page recommendation.
2. **Options** - a sensitivity panel (already built at stage 6); a
   run-over-run diff (needs two quarters of history to be worth anything); a
   bundle dead-weight score (a better answer, not a protection against a wrong
   one); or a release gate.
3. **Decision** - the gate. Four checks run before the memo is written, and
   if any fails **no memo and no shortlist are produced** - the run stops and
   prints what failed in language that says what to do next, including the one
   setting that overrides it.
4. **Impact** - it is the only check in the project whose failure mode is "the
   board was misled" rather than "a stage crashed". The assertions throughout
   the pipeline protect each step from the one before; this protects the
   client-facing output from the whole pipeline. Justified in the client's
   terms in `reports/improvement.md`.
5. **Cost if wrong** - it can block a run Adjoa believes is sound. Handled by
   keeping the checks blunt - each one, failing, makes the memo actively
   misleading rather than merely imperfect - and by naming
   `gate.enabled = false` in the failure message, so skipping it is a decision
   somebody makes and can be asked about rather than something that happens
   silently. A gate with twenty conditions is one that gets permanently
   disabled the first time it fires over something cosmetic.

---

### DR-29: a settings key must be live, or refuse to load - Risk rank: medium

1. **Observation** - an audit found five keys in `settings.toml` that no code
   read (F20). Two of them were cited in decision records as the mechanism
   that made a judgement reversible: DR-13 credited
   `use_popularity_as_performance` with making a choice visible, and DR-14
   credited `report_all_hit_definitions` with exposing the fragility of the hit
   rate. Both behaviours were real and both were hardcoded.
2. **Options** - (a) delete the inert keys; (b) wire each one up; (c) wire up
   what is implementable and make the rest fail loudly at load.
3. **Decision** - (c). `hit_definition`, `report_all_hit_definitions`,
   `lead_actor_billing_order` and `sensitivity_top_n_billed` are now read and
   change behaviour. `use_popularity_as_performance` cannot be implemented
   without contradicting DR-13, so `validate_settings` **refuses to load** a
   configuration that sets it true, with a message that explains why and names
   the record. A setting that cannot work is better as an error than as a
   decoration.
4. **Impact** - every key in the file is now read by code, asserted by a test.
   One wiring produced a finding that had been unreachable: the top-3-billed
   talent view takes the reliable names from 19 to 44, with 25 visible only
   when the net is widened. A "rejected alternative kept runnable" that nothing
   ran was not an alternative at all.
5. **Cost if wrong** - `validate_settings` can refuse a configuration somebody
   deliberately wants. That is the intent, and the message says what to do; the
   alternative is a switch that looks live, is read by nobody, and is quoted in
   a decision record as evidence of flexibility. At 500 titles this matters
   more: the person flipping a setting next year will not be the person who
   wrote the comment next to it.

---

### DR: fetching uses a loop, and that is not a breach of "no row loops"

Worth stating because it looks like an oversight otherwise. The requirement
forbids looping over DataFrame rows to compute statistics — stage 7's job.
Stage 2 is sequential I/O against a rate-limited service: a loop is the
correct shape, and vectorisation is meaningless when each step is a network
round trip. No stage from 3 onward loops over rows to produce a number.
