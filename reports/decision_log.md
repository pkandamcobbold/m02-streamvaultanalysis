# Decision log

> Every judgement call, in five parts: what we saw, what the real alternatives
> were, what we chose, what each option does to the numbers, and what it costs
> Kwame if the call was wrong.
>
> Where part 4 cannot carry numbers yet, it says so and names the stage that
> will fill it. A decision record with an invented impact figure is worse than
> one that admits the measurement is still to come.
>
> **Status: stages 1–4 complete.** DR-00 to DR-11 below. DR-07 and DR-08 came
> out of an audit of stages 1–2 rather than from building them, and are kept
> because both were judgement calls with real alternatives. Cleaning and KPI
> decisions (DR-12 onward) arrive with stages 6 and 7.

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

### DR: fetching uses a loop, and that is not a breach of "no row loops"

Worth stating because it looks like an oversight otherwise. The requirement
forbids looping over DataFrame rows to compute statistics — stage 7's job.
Stage 2 is sequential I/O against a rate-limited service: a loop is the
correct shape, and vectorisation is meaningless when each step is a network
round trip. No stage from 3 onward loops over rows to produce a number.
