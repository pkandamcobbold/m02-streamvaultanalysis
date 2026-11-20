# Data contract: the candidate list and the TMDb API

What this pipeline agrees to receive, written from what we **observed**, not just from what the
brief said. Every rule says what the pipeline does when it is broken, and where.

**Parties:** the acquisition team (sends the candidate list) and the data team (receives it);
The Movie Database (serves the film data) and the data team (consumes it) ·
**Version:** 1.0 · **As of:** 2026-11-19

**Changes.** The candidate list is assembled by three desks — Adjoa's evaluation tracker, a
spreadsheet inherited from Kwame's predecessor, and a batch emailed by a studio's licensing desk.
Nobody owns the combined file, which is why this contract is written from observation. Any change
to its shape should reach the data team before the file does; in practice it will not, so every
rule below is enforced in code rather than assumed. For TMDb there is no negotiable contract at
all: it is a public API that can change without telling us, so the rules below say what we rely on
and what breaks if it moves.

---

## Part 1 — The candidate list

### Delivery

| Rule | If it is broken | Where |
| --- | --- | --- |
| One file at `data/input/id_list.csv`, committed and never edited | The run stops with the path it looked for | `pipeline/extract/` |
| CSV, UTF-8, one column of TMDb movie ids | A second column is read as a finding and ignored; only the first is used | `pipeline/extract/` |
| One header row | A header value appearing anywhere in the file is classified as `header_row` and excluded from the reconciliation base, not counted as data | `pipeline/extract/` |
| The row count matches `input.expected_id_count` in settings | A reconciliation note is printed and recorded; the run continues against what the file holds. **Not** an assertion — next year's list is expected to be ~500 titles (ADR-003) | `pipeline/extract/` |
| The file is valid UTF-8 | Falls back to latin-1 and records the fallback as a finding, because mangled characters are a fact about the source | `pipeline/extract/` |

### Values

The file is read as **text with no type inference**. `dtype=str`, `na_filter=False`,
`keep_default_na=False`: a blank stays blank and never becomes a null that forces the column to
float, which is how `550` becomes `550.0` and 404s three stages later (ADR-004).

| Rule | Seen in the data | If a row breaks it | Where |
| --- | --- | --- | --- |
| Every value is a positive integer TMDb movie id | 121 of 127 rows | — | `pipeline/extract/` |
| Every id appears once | 6 rows repeat an earlier id | First occurrence kept; later ones get status `duplicate` and a reason naming the row they repeat. Never fetched | `pipeline/extract/` |
| No placeholders | `-1` at row 30, `N/A` at row 111 | Status `invalid_id`, reason names the placeholder. Checked **before** the digits pattern, so a bare `0` is reported as a placeholder rather than fetched as an id | `pipeline/extract/` |
| No blank rows | 1 blank row | Status `invalid_id`, reason "blank row". Counted, never dropped | `pipeline/extract/` |
| Ids are TMDb ids, not another namespace | 1 IMDb id, `tt0468569`, at row 95 (F-09) | Resolved live via `/find`. If it resolves to an id already on the list: status `duplicate_other_namespace`, excluded, because recovering it would count one film three times. If it resolves to an id *not* on the list: recovered, fetched, and forced into the spot-check (ADR-003) | `pipeline/extract/` |
| No float-formatted ids | None this quarter | A digits-dot-zeros value is recovered as the integer and the recovery is recorded. Anything else stays unusable: there is no honest way to choose between `550.7` as 550 or 551. The branch exists because the fault is one keystroke away and next quarter's file comes from the same three desks | `pipeline/extract/ids.py` |
| No invisible characters | Byte-order mark, CRLF endings, a quoted value, a non-breaking space | Normalised at read; recorded as a characteristic of the file | `pipeline/extract/` |

**Every row is accounted for, always.** `data/processed/id_ledger.csv` carries one row per source
row, forever, with a status and a reason. Rows are never dropped from it. The status counts must sum
to the data-row count exactly, and that is asserted before a single API call is spent.

---

## Part 2 — The TMDb API

### Delivery

| Rule | If it is broken | Where |
| --- | --- | --- |
| `GET /movie/{id}?append_to_response=credits` returns details and credits in one response | `api.append_credits = false` runs the two-call path the brief names, against a different cache filename so a cached response can never lack what was asked for (ADR-001) | `pipeline/extract/` |
| Every call carries a timeout | Hard-asserted by a test; a call without one would hang Adjoa's run with no message | `pipeline/extract/` |
| 429 and 5xx are transient | Retried 5 times with exponential backoff, honouring `Retry-After` | `pipeline/extract/` |
| 404 is permanent | **Not** retried. Recorded on the ledger as `not_found_404` and cached like any other response, so reruns do not ask again (ADR-003) | `pipeline/extract/` |
| Anything else after retries | Status `fetch_failed`, reported as a note naming the ids. Not evidence of anything; rerun before relying on the counts | `pipeline/extract/` |
| Calls are paced at `api.min_seconds_between_calls` | A floor on the gap between calls, measured on a monotonic clock so a clock adjustment cannot release a burst | `pipeline/extract/` |
| The credential never appears in a URL | A v4 bearer token in a header. Asserted by a test over every request URL and every cached envelope (ADR-001) | `pipeline/extract/` |

### Fields we rely on

Every cached response is wrapped in an envelope recording the HTTP status, the request path and
`fetched_at` in UTC. The envelope is what makes the memo's as-of date defensible.

| Field | Type | Rule we rely on | Seen in the data | If it breaks | Where |
| --- | --- | --- | --- | --- | --- |
| `id` | whole number | Matches the id we requested | All 112 match | A mismatch is reported as a merged or redirected entry, and checked against the rest of the list | `pipeline/transform/` |
| `title` | text | Always present | As expected | Identifies the film in the memo; a change is a **material** spot-check difference | `pipeline/checks/` |
| `budget` | whole dollars | Present and non-zero for a released feature | **All 112 non-zero** (S-01) — the classic disguised null is absent | Zero or missing: the film leaves the money metrics with a reason, and stays in every other metric (ADR-003). Below `profile.min_plausible_budget`: flagged as a figure probably entered in millions | `pipeline/validate/` |
| `revenue` | whole dollars | Present and non-zero for a released feature | All 112 non-zero (S-01). 8 films return more than 20× budget, all pre-2000 (F-06) | Same as budget. An extreme is **flagged with a verdict, never clipped** — clipping would delete 20% of the pre-2000 films and none of the modern ones (M5) | `pipeline/validate/` |
| `release_date` | `YYYY-MM-DD` | Parses to a year | All 112 parse | A film with no parseable year falls out of any bounded window. `windows.all_years` deliberately has **no** lower bound rather than a bound of 0, so such a film is not silently excluded from both | `pipeline/transform/` |
| `belongs_to_collection` | object or null | Null, or an object with an `id` and a `name` | 96 of 112 belong to a collection; 9 are the only member of theirs on the list (F-04) | A name with no id is a **hard failure**: the franchise split is the whole analysis. Decides the franchise/standalone split, so a change is a material spot-check difference | `pipeline/transform/` |
| `runtime` | minutes | A plausible feature length | All within range | Outside `profile.min_feature_runtime` to `max_plausible_runtime`: flagged as `check`, nothing excluded on a check | `pipeline/validate/` |
| `vote_average` | decimal | Real, but only meaningful with enough votes | — | Below `profile.min_votes_for_reliable_rating` votes: the film is kept and `rating_reliable` is false, so it cannot order a shortlist | `pipeline/validate/` |
| `vote_count` | whole number | Rises over time | — | Expected to drift; a change is **not** a discrepancy | `pipeline/checks/` |
| `credits.cast[]` | list | One entry per cast member, with `order` where 0 is the lead | All 112 carry a credits block; cast counts 9 to 177, none empty | A 200 without credits is reported by name: the talent analysis cannot see those films. An **empty** cast list is a fact, not an absence, and the film must survive the joins | `pipeline/extract/`, `pipeline/transform/` |
| `credits.crew[]` | list | One entry per credit, not per person | 914 of 24,932 rows are one person in two jobs on one film; 9 films have co-directors returned in **no fixed order** (F-11) | Grain is one row per credit. Co-directors get a sorted partnership label and both are credited in the long table (M2, M3) | `pipeline/transform/` |
| `genres[]` | list | One entry per genre | — | Order is **not** documented as meaningful, so no genre is called "primary". A film with no genres keeps its row | `pipeline/transform/` |

### Fields we deliberately do not rely on

| Field | Why not |
| --- | --- |
| `popularity` | Recomputed daily from recent activity and heavily recency-biased: 85.7 for a 2019 blockbuster against 0.46 for a 1966 classic. Using it would rank against the back catalog this project exists to evaluate, and would make the analysis irreproducible from the same cache a month later. Kept in the tables as fetched, excluded from every metric, and setting `profile.use_popularity_as_performance = true` **refuses to load** (M8, ADR-007) |
| `adult`, `video` | Read and available; no rule depends on them this quarter |
| `dispatched_at`-style extras | Any field TMDb adds is ignored. Any field it stops sending becomes an empty column rather than a crash three stages later |

---

## Part 3 — Each run as a whole

| Rule | If it is broken | Where |
| --- | --- | --- |
| Every source row ends up with exactly one status, and the statuses sum to the data-row count | The run stops. This is the arithmetic the memo's "127 received, 112 analysed" sentence is read off | `pipeline/extract/` |
| Every film fetched reaches the analysis table, and nothing else does | The run stops | `pipeline/transform/` |
| No merge changes the row count. Each is made with `validate=` and an indicator, and counted into a join report | The run stops. A duplicated key multiplies rows, every statistic moves, and the result looks fine | `pipeline/transform/` |
| Cleaning adds columns and never removes a row | The run stops | `pipeline/validate/` |
| A return figure exists exactly where the film is in the money metrics, and nowhere else | The run stops, so nothing downstream can average a ratio that was never valid | `pipeline/validate/` |
| Every statistic is reported with its count | Asserted per window; a group appearing twice or without a count stops the run | `pipeline/transform/` |
| At most `gate.max_unaccounted_rows` source rows unaccounted for (0) | **No memo and no shortlist are published.** The run stops and names the check | `pipeline/checks/` |
| At least `gate.min_films_for_a_recommendation` films analysed (40) | Same. Below this the groups are too thin to rank, and the honest output is a description | `pipeline/checks/` |
| At most `gate.max_missing_money_share` of films without usable money (20%) | Same. Above that, a ranking by return is a ranking of whichever films happened to have figures | `pipeline/checks/` |
| A live re-check does not change the recommendation | Same, while `gate.block_if_spotcheck_moves` is true | `pipeline/checks/` |
| The analysis stages finish inside `budget.analysis_seconds_limit` (10s, warm cache, acquisition excluded) | Reported loudly, not blocked: the limit is a target we set, not a rule anyone gave us (ADR-005) | `pipeline/checks/` |

The gate can be turned off with `gate.enabled = false`. That is deliberate: skipping it should be a
decision somebody makes and can be asked about in the meeting, not something that happens by
accident (ADR-006).
