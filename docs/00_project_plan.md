# StreamVault Back-Catalog Analysis — Project Plan & Study Guide

> Status: planning only. No code yet.
> Purpose: understand the problem, list every requirement, decide what to test, and agree the order of work before writing anything.

> **Addendum, 18 Nov.** The brief and pipeline guide have since been checked against this
> plan and saved verbatim in [01_brief_and_guide.md](01_brief_and_guide.md). The plan holds —
> nothing in the source material contradicts it. Three things are now settled, superseding
> Part 10 where they differ:
>
> - **Q15 (deliverable shape)** — both: logic in `src/streamvault/`, `notebooks/analysis.ipynb`
>   as the narrative that imports it, `run_pipeline.py` as the one command.
> - **Q13 (`id_list.csv`)** — given with the lab; download it to `data/input/id_list.csv`,
>   never edit it, commit it.
> - **J15 (one request or two)** — `append_to_response=credits`, with the two-call path kept
>   behind a settings flag so the rejected alternative is runnable, not hypothetical.
>
> - **Q16 (as-of date)** — settled at stage 2, since the data now exists and the question
>   stopped being hypothetical. The memo's as-of date is the **`fetched_at` stamp carried in
>   the cached envelopes**, not the date the memo is written. The two differ as soon as a run
>   reads from cache — which is the normal case, and the case where quoting today's date
>   would overstate how fresh the numbers are. Currently 2026-11-19.
>
> - **Q12 (time budget)** — settled at stage 8. The boundary is stages 3–7, warm cache,
>   one machine, single-threaded, acquisition excluded and reported beside it. Measured
>   1.9s against the 10s limit in settings; projected 3.6s at 500 titles (4.5s if every
>   stage is assumed linear). See DR-22 and DR-23.
> - **Q14 (the four slices)** — settled at stage 9: `shortlisted`, `flagged_extreme`
>   (all eight, not a sample), `pre_2000`, and `random_control`. Stratified rather than
>   random, because a random 12 of 112 would miss every film the recommendation leans
>   on. See DR-25.
>
> - **The "one improvement beyond the brief"** — settled at stage 10: it is code, a
>   release gate that refuses to publish a memo when the accounting does not
>   reconcile, the groups are too thin, too much money data is missing, or a live
>   re-check moved the answer. Chosen over a sensitivity panel (already built), a
>   run-over-run diff (needs two quarters of history) and a bundle dead-weight score
>   (a better answer rather than a protection against a wrong one). Justified in the
>   client's terms in `reports/improvement.md`. See DR-28.
>
> Nothing is now open. Every question in Part 10 has been settled and recorded.
>
> The step-by-step build order, including every manual setup task, is in
> [02_build_runbook.md](02_build_runbook.md). This file stays the *why*; that one is the *how*.

---

## Part 0 — How a data engineer starts a project (the habits)

Before touching an API or a DataFrame, answer five questions in writing. If you can't, you aren't ready to code.

| # | Question | Our answer (draft) |
|---|----------|--------------------|
| 1 | **What decision does this data serve?** | Where Kwame puts $14M: franchise bundles vs standalone hits, and which titles to negotiate on. |
| 2 | **Who uses the output, and how?** | Kwame (memo, in a board room), negotiators (shortlist, talent levers), Yaw/Finance (will attack pre-2000 numbers), Adjoa (re-runs it every quarter, alone, sometimes live). |
| 3 | **What does "good" look like?** | A recommendation that survives Yaw's challenge, a pipeline Adjoa can run on 500 titles without help, and a ledger where every one of the 127 ids is accounted for. |
| 4 | **What could make us wrong?** | Dirty source data, a bad definition (what is a "franchise"? what is "performance"?), a join that drops or duplicates films, era bias, small samples. |
| 5 | **What can't we know from this data?** | Licensing prices, streaming viewership, what the competitor paid. TMDb gives box-office and audience ratings — a *proxy* for streaming value, not the thing itself. Say this in the memo. |

**Habit: separate claims from facts.** Everything the team "knows" is a claim until the data tests it. We keep a *claim register* (Part 2).

**Habit: never delete, always flag.** Every row that leaves the analysis goes to an exclusions table with a reason code. Nothing disappears silently. The raw API responses are kept exactly as received.

**Habit: write the decision when you make it.** Decision records are cheap at the time and impossible to reconstruct a week later.

---

## Part 1 — Requirements, drawn out of the brief

Every line in the brief that creates work, with where it ends up. Use this as a checklist at the end.

### 1A. Business questions (what Kwame asked for)

| ID | Requirement | Deliverable |
|----|-------------|-------------|
| B1 | Recommend franchise bundles **or** standalone hits, with reasoning | Memo, analysis |
| B2 | Shortlist: **3** franchise targets, **5** standalones, each with *why it made the cut* | Memo, analysis |
| B3 | Which **directors** and **lead actors** reliably signal a title worth licensing | Memo, analysis |
| B4 | One-paragraph **deal note** on the strongest franchise: what to pay *relative to everything else*, and *the one number* that drove the view | Memo |
| B5 | Plainly state what couldn't be verified and **what that costs him** | Memo, diagnosis |

### 1B. Constraints

| ID | Constraint | What it means in practice |
|----|-----------|---------------------------|
| C1 | Compare **both windows**: all years and 2000-onward | Every KPI is computed twice by a parameter, not by copy-paste. |
| C2 | If the recommendation **flips** between windows, say so **loudly** | Automatic check in the code that prints/flags a flip; top of the memo if it happens. |
| C3 | Must **scale to ~500 titles** | Vectorised, no row loops, cached fetching, runtime measured and projected. |
| C4 | **Adjoa runs it alone**, on her laptop, sometimes live | One command, clear README, readable errors, cached data so a meeting rerun doesn't hit the API. |
| C5 | Runs **top to bottom from a clean clone, no manual edits** | No hard-coded paths, no "run cell 7 first", key read from environment. |
| C6 | Kwame **unavailable** — decide and state | Decision log. |
| C7 | Fetch **live** from TMDb: `/movie/{id}` and `/movie/{id}/credits` | Fetch module. |
| C8 | **Don't abuse a shared API** | Rate limiting, retries with backoff, cache — never fetch the same id twice without reason. |
| C9 | **Yaw distrusts pre-2000** | The 2000+ window answers him; the decision log explains what we did about inflation. |
| C10 | **API keys never committed** (your rule) | `.env` + `.gitignore` before the first commit. |

### 1C. Deliverables (what gets graded)

| ID | Deliverable | Must contain |
|----|-------------|--------------|
| D1 | **Data diagnosis** | Every problem, how detected, effect on the recommendation, **ranked by risk**; full account of the 127: how many analysed, where the rest went, what the gap costs. |
| D2 | **Working analysis** | Runs clean-clone → results, both windows. |
| D3 | **Decision notes** | Every judgement call: assumption, why, cost if wrong; rejected alternatives; what survives at 500 titles. |
| D4 | **Client memo** | One page, business language, no tool names/jargon: recommendation, shortlist, two-window comparison, deal note, what you couldn't stand behind, as-of date. |
| D5 | **One improvement beyond the brief** | Justified in terms of value to Kwame or Adjoa. |

### 1D. Technical requirements (from the pipeline guide & rubric)

| ID | Requirement | Proof we keep |
|----|-------------|---------------|
| T1 | Load ids with **explicit dtype**; assert count and uniqueness; record the reconciliation number | Assertion + logged count |
| T2 | Session with **timeout + retry policy**; cache each raw response **with a timestamp**; record 404s instead of crashing | Cache folder, fetch log, failures table |
| T3 | Flatten nested JSON into **one table per grain**, grain stated in a comment; rename generated columns once | `films`, `cast`, `crew`, `genres`, … tables |
| T4 | Join with `validate=` and `indicator=True`; assert row count; account for every id | Join report |
| T5 | **Profile** function; find disguised faults; separate real extremes from errors | Profile output, diagnosis |
| T6 | Cleaning **parameterised** so each metric can be computed both ways; each decision written in **five parts**, ranked by risk | Decision log + sensitivity table |
| T7 | **Named aggregations** with **counts beside every statistic**, both windows | KPI tables |
| T8 | **No row loops**; time each stage **excluding acquisition**, boundary stated; **project to 500** | Timing table |
| T9 | **Spot-check** vs live API, sampled across **four slices**; classify every discrepancy; say if any moves the recommendation | Spot-check report |
| T10 | Memo with **as-of date** of the data | Memo |

### 1E. Rubric weights (where the marks are)

All five criteria are 20%. Note what each rewards:
- **Analyze** — problems that *move the recommendation*, quantified and ranked. *Not* a flat list of untidiness, *not* fixes applied to nothing broken.
- **Apply (acquisition)** — every id accounted for, totals reconcile, polite to the API.
- **Apply/Create (analysis)** — sound table shapes, join *proven*, vectorised, timed against the budget.
- **Evaluate (reasoning)** — every call named, defended, costed; you can say what the answer would be under the rejected alternative.
- **Evaluate/Create (client)** — Kwame could act without a follow-up meeting.

---

## Part 2 — The claim register (what we are testing)

A claim test turns an opinion into: *a hypothesis → a metric → a threshold → what would prove it wrong.* Write these down **before** you look at results, so you can't move the goalposts.

| ID | Claim (who holds it) | Testable form | Metric(s) | What would refute it |
|----|---------------------|---------------|-----------|----------------------|
| CL1 | "Franchise bundles are the safer buy" (half the team) | Franchise films have a *higher floor* and *less spread* than standalones | Hit rate, median and lower quartile of performance, share of flops | Franchise lower quartile ≤ standalone lower quartile, or flop share similar |
| CL2 | "We overpay for weak middle entries" (other half) | Within a franchise, entries that are not the first/best perform materially worse | Performance by position in series (1st, middle, last); gap between best and median entry per bundle | Middle entries perform about as well as the opener |
| CL3 | "Cherry-picking standalone hits beats bundles" | The top-N standalones beat the average *per-film* value of a bundle | Compare top standalones vs bundle average (bundle priced as a whole) | Bundle average ≥ top-standalone average |
| CL4 | "Talent is a reliable lever" (negotiators) | Some directors / lead actors have consistently above-median films, with enough films to trust | Per-person film count, median performance, hit rate, spread | No person with ≥ N films beats the overall median consistently |
| CL5 | "Pre-2000 numbers can't be trusted" (Yaw) | The recommendation depends on pre-2000 films | Same KPIs in both windows | Recommendation is the same in both windows → Yaw's concern doesn't change the answer (still state it) |
| CL6 | "The list has 127 titles" (implicit) | 127 unique, valid, fetchable ids | Count, duplicates, 404s, non-films | Anything other than 127 clean ids |
| CL7 | "TMDb data is accurate enough to decide on" (implicit) | Spot-check matches; money fields are plausible | Discrepancy rate in spot-check; share of disguised nulls | High missing/implausible share in the fields that drive the answer |
| CL8 | "The trilogy failed / the passed bundle was a miss" (Kwame's history) | Out of scope to prove, but our method should be able to score any bundle | — | Note only; don't overclaim |

**Teaching point — selection bias.** Sequels only get made when the first film succeeded. So franchises will *look* safer partly because the failures never got sequels. Name this in the decision notes; it's exactly the kind of reasoning the "Evaluate" criterion rewards.

---

## Part 3 — Definitions we must decide (judgement calls)

The brief is silent on all of these. Each becomes a decision record. Draft positions below — we confirm them after profiling.

| # | Question | Options | Draft choice & why | Cost if wrong |
|---|----------|---------|---------------------|---------------|
| J1 | **What is a "franchise" film?** | (a) TMDb `belongs_to_collection` not null; (b) ≥2 films of the same collection on *our list*; (c) manual | (a) as base, but record how many collection members are on the list vs exist | Collections with 1 film on our list aren't really "bundles" to buy |
| J2 | **What is a "bundle"?** | Only films from the collection that are on our list, or the whole collection | Films on our list (that's what's under consideration); flag incomplete bundles | Pricing the bundle on a subset that misses the weak entries |
| J3 | **What is "performance"?** | Revenue; ROI = revenue / budget; profit; rating (`vote_average`); popularity; `vote_count` (audience size) | Primary: revenue-based ROI/multiple **and** an audience measure; never a single metric. Report both. | ROI explodes on tiny budgets; revenue favours big-budget era; ratings ignore reach |
| J4 | **What counts as a "hit"?** | Absolute threshold, above median, top quartile, ROI > 2–3× | e.g. ROI ≥ 2.5× (rough box-office break-even rule of thumb) — decide after profiling | Threshold drives hit rate directly → run a sensitivity check |
| J5 | **Zero budget / zero revenue** | Missing (disguised null) or real flop | Treat 0 as **missing**, not a flop; keep the film, exclude it only from money metrics | If some are real flops, we flatter whichever group has more zeros |
| J6 | **Inflation for pre-2000** | Adjust with CPI; don't adjust and use ratios; drop pre-2000 | Prefer **ratios** (ROI) which are inflation-neutral within a film, plus the 2000+ window | Revenue totals across eras are not comparable |
| J7 | **Lead actor** | `order == 0`; top 3 billed | `order == 0` as "lead"; top-3 as a sensitivity check | Ensemble films mis-credited |
| J8 | **Director** | `crew.job == 'Director'` (can be several) | All directors, credited per film — watch for join duplication | Double-counting co-directed films |
| J9 | **"Reliable" talent** | Minimum film count | e.g. ≥ 3 films on the list, report count beside every number | Small-sample "stars" misleading negotiators |
| J10 | **Window boundary** | `release_date` year ≥ 2000 | Year from parsed release date; films with missing date flagged | Missing dates silently fall out of one window |
| J11 | **Unreleased / non-film entries** | Keep or exclude | Exclude from KPIs (no box office possible), keep in ledger | — |
| J12 | **How the ranking works (shortlist)** | Single metric vs composite | Simple, explainable rule; show the runner-ups | A composite nobody can explain won't survive the room |
| J13 | **Time budget** | Not stated in what we were given | Ask; if no answer, set one (e.g. analysis stages < 10 s on a laptop, acquisition excluded) and state it | — |
| J14 | **Cache: commit or not** | Commit raw responses vs fetch on clone | Don't commit raw cache (size, licence terms); clean clone fetches once, then reruns use cache | Clean-clone run needs a key and internet |
| J15 | **One request or two per film** | Two endpoints as briefed; or `append_to_response=credits` | Decide; `append_to_response` halves calls (scales better to 500) — document it | Must still prove credits came back for every film |

---

## Part 4 — What to look for in the data (detection, not answers)

The brief warns: *problems it doesn't name*, and *not everything that looks wrong is wrong*. Here is a checklist of where to look. You'll find out which ones are real.

### In the id list (before any API call)
- Dtype: are ids read as integers, or did something turn them into floats (`550.0`) or strings with spaces?
- Exact duplicates. Count before and after.
- Ids that aren't TMDb ids at all (e.g. IMDb-style `tt…`), blanks, header rows mid-file, stray characters.
- **Three sources merged over four years** → expect overlap and formatting drift.

### From the API
- **404s** — deleted or wrong ids. Record, don't crash.
- **Redirects / merged entries** — two different ids that return the *same* film (a duplicate you only see after fetching — compare returned `id`, `imdb_id`, title+year).
- Entries that are not feature films (TV, short, `adult`, `video`).
- `status` other than `Released`.

### In the fields (disguised problems)
- `budget = 0`, `revenue = 0` — the classic **disguised null**.
- Implausibly tiny values (e.g. budget `5` — reported in millions by mistake).
- Revenue < budget: could be a real flop (*don't fix*) or an error.
- `release_date` as empty string `""` rather than null.
- `runtime = 0` or null.
- `vote_average` high with `vote_count` of 3 → unreliable, not an error.
- Huge outliers (a $2bn film) — usually **real**. Real extremes stay; errors get flagged.

### In credits
- Films with **no director** or **no cast**.
- **Multiple directors** → one-to-many join → silent duplication of the film's revenue.
- Same person in cast twice (multiple roles).

### For each problem, record:
1. How you detected it (the check).
2. How many rows.
3. Which group it affects (franchise or standalone? pre or post 2000?) — **this is what makes it risky**.
4. What it does to the recommendation (compute both ways).
5. Risk rank.

> **Key idea for the "Analyze" marks:** a problem matters in proportion to how much it moves the answer. 40 zero-budget films spread evenly is lower risk than 8 that are all in franchises.

---

## Part 5 — Never losing a film: the id ledger

One table, one row per id from the original file, with a final status. This is how you prove reconciliation.

| column | meaning |
|--------|---------|
| `source_row` | position in `id_list.csv` |
| `raw_value` | exactly as read |
| `tmdb_id` | parsed id (or null) |
| `status` | `analysed` / `duplicate` / `invalid_id` / `not_found_404` / `not_released` / `excluded_<reason>` |
| `reason` | text |
| `in_money_metrics` | bool — film kept but excluded from ROI because of missing money fields |

**Reconciliation rule:** `count(ledger) == 127` and the status counts add to 127. Assert it in code. The memo says: "127 received → X analysed → Y removed for these reasons."

---

## Part 6 — Proposed directory structure

```
m02-streamvaultanalysis/
├── README.md                 # what it is, how to run, how to set the key
├── .gitignore                # .env, data/raw/, data/interim/, __pycache__, .venv
├── .env.example              # TMDB_API_KEY=your_key_here   (committed, no real value)
├── requirements.txt          # pinned versions
├── config/
│   └── settings.toml         # windows, thresholds, min film counts, rate limit — the knobs
├── data/
│   ├── input/id_list.csv     # given input, committed, never edited
│   ├── raw/                  # cached API JSON + fetched_at (gitignored)
│   ├── interim/              # flattened tables (gitignored, regenerable)
│   └── processed/            # final tables, ledger, KPIs
├── src/streamvault/
│   ├── config.py             # load settings + env key
│   ├── ingest.py             # stage 1: load & validate ids
│   ├── fetch.py              # stage 2: session, retry, cache, 404 log
│   ├── flatten.py            # stage 3: one table per grain
│   ├── join.py               # stage 4: validated merges
│   ├── profile.py            # stage 5: profiling function
│   ├── clean.py              # stage 6: parameterised cleaning rules + flags
│   ├── kpis.py               # stage 7: grouped aggregations, both windows
│   ├── timing.py             # stage 8: stage timer
│   └── spotcheck.py          # stage 9: live re-fetch & compare
├── notebooks/
│   └── analysis.ipynb        # the narrative; calls src/, runs top to bottom
├── tests/                    # small tests for parsers, join assertions, cleaning rules
├── reports/
│   ├── data_diagnosis.md     # D1
│   ├── decision_log.md       # D3
│   ├── claims.md             # claim register + verdicts
│   ├── memo.md               # D4
│   └── improvement.md        # D5
├── docs/
│   └── 00_project_plan.md    # this file
└── run_pipeline.py           # one command: python run_pipeline.py
```

Why this shape: input/raw/interim/processed is the standard data lifecycle (you can always rebuild later layers from earlier ones); code in `src/` is reusable and testable; the notebook *tells the story* but doesn't hide logic; `config/` means Adjoa changes a threshold without editing code.

---

## Part 7 — Secrets and API etiquette

**Secrets**
1. Create `.gitignore` with `.env` in it **before** the first commit.
2. Commit `.env.example` with a placeholder only.
3. Read the key with `os.getenv` (via `python-dotenv`); if missing, stop with a clear message telling Adjoa how to set it.
4. Never print or log the key. Don't store request URLs with `api_key=` in the cache metadata. (TMDb's v4 *bearer token* in a header avoids keys in URLs entirely — worth considering.)
5. Before each commit: `git status` and look. Optionally a pre-commit secret scan.

**Being polite to a shared API**
- One `requests.Session` (connection reuse).
- `timeout=` on every call.
- Retry with exponential backoff on 429 and 5xx; honour `Retry-After`. Do **not** retry 404 — record it.
- A small delay / rate cap between calls.
- **Cache first:** if the file is in `data/raw/`, don't call. Save JSON + `fetched_at` + HTTP status.
- **Resumable:** if it dies at film 80, rerun picks up at 81.

---

## Part 8 — The pipeline, stage by stage (what each produces)

| Stage | Do | Keep (artefact) |
|-------|----|-----------------|
| 1 Load ids | Explicit dtype, assert count/uniqueness | Count = 127 recorded; duplicates logged |
| 2 Fetch | Session, retry, cache, 404 log | Raw cache; fetch log with status per id |
| 3 Flatten | `films` (1 row/film), `cast` (1 row/film/person), `crew` directors (1 row/film/director), `genres` etc. | Grain stated in comments; row counts |
| 4 Join | `validate="one_to_one"` / `"one_to_many"`, `indicator=True` | Join report: `both / left_only / right_only` counts |
| 5 Profile | Nulls, disguised nulls, dtypes, ranges, duplicates, outliers | Profile table; candidate fault list |
| 6 Clean | Flags not deletions; each rule a parameter | Decision records; exclusions table |
| 7 KPIs | Named aggs, counts beside stats, both windows, flip check | KPI tables; flip flag |
| 8 Budget | Time each stage, acquisition excluded | Timing table; 500-title projection |
| 9 Spot-check | Sample from 4 slices (franchise/standalone × pre/post-2000), live re-fetch, classify differences | Spot-check report |
| 10 Memo | Business language, as-of date | One page |

**Order of working ≠ order of running.** You'll find a fault at stage 5 and go back to stage 3. That's normal. The *final* code must still run 1 → 10 in one go.

---

## Part 9 — The five-part decision record (template)

Use this for every cleaning rule and every judgement call:

```
### DR-xx: <short title>                         Risk rank: <n>
1. Observation   — what we saw, how detected, how many rows, which groups
2. Options       — at least two real alternatives
3. Decision      — what we chose
4. Impact        — the KPI / recommendation computed under each option (numbers)
5. Cost if wrong — what Kwame loses if this was the wrong call; what survives at 500 titles
```

---

## Part 10 — Questions to answer (open questions list)

### Questions the analysis must answer (for Kwame)
1. Across all years, do franchise films outperform standalones — on median, floor, hit rate?
2. Same question, 2000-onward. Does the answer flip?
3. Inside franchises, how much weaker are middle entries than the best entry?
4. Which 3 franchises and 5 standalones rank highest, and why each?
5. Which directors / lead actors with enough films are consistently above median?
6. For the top franchise: what is its value relative to the rest, and what single number drives that?
7. How many of the 127 made it into the analysis, and what do the missing ones cost?
8. What can't be verified (no licensing price, no streaming data, missing money fields, era effects)?

### Questions to settle ourselves (Kwame is unavailable — decide and record)
9. Definitions J1–J15 above.
10. What hit-rate threshold, and how sensitive is the answer to it?
11. Is a 1-film "collection" on our list a franchise for buying purposes?

### Questions to check with your instructor/reviewer (genuinely ambiguous)
12. Is there a stated **time budget** for the analysis stages? (The guide mentions "the client's time budget" but the brief text we have doesn't give a number.)
13. Where is `id_list.csv`? (Not yet in the repo.)
14. What are the "four slices" for the spot-check — is franchise/standalone × pre/post-2000 correct?
15. Is a notebook, scripts, or both expected for the "working analysis"?
16. Dates: the board review is 31 October; what as-of date should the memo carry?

---

## Part 11 — "Improvement beyond the brief" — candidates

Pick one later; judge by value to Kwame or Adjoa:
- **Run-over-run diff report** — each quarter, show Adjoa what changed vs last run (new ids, TMDb revisions, shortlist changes). Directly serves the quarterly rerun.
- **Data-quality gate** — the pipeline stops with a readable message if reconciliation fails or missing-money share exceeds a threshold. Protects Adjoa in a live meeting.
- **Sensitivity panel** — one table showing whether the recommendation survives each judgement call flipped. Arms Kwame against Yaw.
- **Bundle "dead weight" score** — share of a bundle's films below the standalone median; a negotiation number ("you're asking us to pay for 3 weak films").

---

## Part 12 — Order of work (suggested sessions)

1. **Setup** — repo structure, `.gitignore`, `.env.example`, venv, requirements, README stub. Get a TMDb key. First commit (no secrets).
2. **Ingest + fetch** — load ids, assert, build cached fetcher, pull everything once. Produce ledger v1.
3. **Explore raw JSON by hand** — open 3–4 responses, note nested fields. Write grains.
4. **Flatten + join** — tables, validated joins, join report.
5. **Profile + diagnose** — fault list, ranked. Go back to stage 3 if needed.
6. **Decide + clean** — decision records, parameterised rules, exclusions table.
7. **KPIs, both windows** — flip check; claim verdicts.
8. **Timing + spot-check.**
9. **Write** — diagnosis, decision log, memo, improvement.
10. **Clean-clone test** — fresh clone into a new folder, set key, run one command. If it fails, it isn't done.

### Learning checkpoints (explain these back in your own words)
- Why is `budget == 0` a disguised null and not a flop? When might it be a flop?
- Why does `validate="one_to_many"` matter when joining directors?
- Why is ROI dangerous on small budgets, and what do you do about it?
- Why might franchises look safer than they are (selection bias)?
- What does "acquisition excluded from the time budget" mean, and why exclude it?
