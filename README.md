# StreamVault back-catalog licensing analysis

Which older films are worth licensing: franchise bundles, or standalone hits? The candidate list is
127 TMDb ids and nothing else. This pipeline pulls the film data itself from a live public API,
accounts for every id it was given, checks the data for problems, and produces a recommendation with
a shortlist to negotiate from — the same way every time, so it can be re-run each quarter without
anyone having to remember how.

```text
 data/input/id_list.csv ──┐
 TMDb API /movie/{id} ────┤
                          ▼
   EXTRACT ──► VALIDATE ──► TRANSFORM ──► CHECKS ──► LOAD ──► reports/memo.md
   extract.py  validate.py  transform.py  checks.py  load.py
   └──────────── run in order, timed, logged, by run_pipeline.py ────────────┘
```

---

## Setup

You need **Python 3.15** and a free account on themoviedb.org.

3.15 is the version this was built and verified on, and the one the pins in
`requirements.txt` target. `pyproject.toml` declares `>=3.12` because nothing in the code needs
3.13+ syntax, but 3.12 and 3.13 have never been run — treat them as expected to work rather than
known to. If you are on an older Python and something fails at install, that is the likely cause
before anything in this repository is.

**1. Get the code**

```bash
git clone https://github.com/pkandamcobbold/m02-streamvaultanalysis.git
```

**2. Create an isolated environment and install everything**

```bash
python -m venv .venv
```

Activate it. PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

Git Bash on Windows:

```bash
source .venv/Scripts/activate
```

macOS or Linux:

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

That is everything the analysis needs: ten packages, about a minute. If you also want to open
[`explore/analysis.ipynb`](explore/analysis.ipynb) — a guided tour of the whole analysis, which
computes nothing of its own — there is one more command. It is separate on purpose, because a
notebook viewer's dependencies should not be able to stop the analysis installing (ADR-013):

```bash
pip install -r requirements-notebook.txt
```

**3. Get your own access token**

The data comes from The Movie Database, which asks each person to use their own free credential
rather than a shared one.

1. Create an account at <https://www.themoviedb.org/> and verify the email — the API page stays
   locked until you do.
2. Profile icon → **Settings** → **API** in the left sidebar.
3. Request a key: choose **Developer**, accept the terms, fill the short form. Approval is instant.
4. Copy the **API Read Access Token (v4 auth)** — the long value starting `eyJ`. Not the shorter
   32-character key below it.

**4. Put the token where the project can find it**

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder with your token. No quotes, no spaces around the `=`. That
file is ignored by git and never leaves your machine (ADR-001).

---

## Run

```bash
python run_pipeline.py
```

**The first run fetches the data** — about half a minute for the 117 unique ids the 127-title list
resolves to, and it needs an internet connection. Every response is saved to `data/raw/`, so **every run after that
reads from disk**: the second run takes about two seconds and makes no API calls at all. That is
deliberate — a re-run during a meeting does not depend on the network, it does not need the token,
and it does not hammer a service other people are sharing.

If a run is interrupted, just start it again. It picks up where it stopped — including when it was
interrupted *while writing* a file, which used to leave a half-written response that broke every
later run (ADR-007).

Other ways to run it:

```bash
python run_pipeline.py --force
```

```bash
python run_pipeline.py --no-spotcheck
```

```bash
python -m pytest
```

`--force` refreshes the data deliberately, for a new quarter. `--no-spotcheck` skips the one stage
that must reach the network. The tests cover everything that does not need live data.

**Exit codes.** `0` succeeded. `1` could not start — usually no token, and the message says what to
do. `2` means the **release gate blocked publication**: the analysis ran and its results should not
go in front of a board without someone looking first. That is not a crash; see ADR-015.

---

## Layout

| Path | What it holds | Why it is separate |
| --- | --- | --- |
| `pipeline/` | Production code: one package per stage, plus `config.py` and `load.py`. Each package holds one module per job, and its `__init__.py` holds the stage's entry point | This is what runs every quarter. Nothing else lives here |
| `run_pipeline.py` | The orchestrator | The one command, and the only thing that times and records a run |
| `tests/` | Tests on tiny hand-made data, one file per stage module | Prove the code is right before it touches a 127-title list |
| `decisions/` | Architecture Decision Records, one file per decision, in the house format | How the system is built, and why. Versioned with the code |
| `docs/templates.md` | The house templates the deliverables are written to | Copied in so the repo is self-contained and the format can be audited |
| `reports/decision_notes.md` | The brief's Decision notes deliverable: every judgement call where the brief left something open, ranked by risk | Separate from the ADRs because these are the calls that move the recommendation |
| `docs/self_audit.md` | What we checked without finding anything (S-01 to S-03), and the seven defects in this project rather than the data (S-04 to S-10) | Out of the diagnosis so that eleven ranked findings are not diluted by ten that are not about the data |
| `docs/questions.md` | Questions for the client, and what we did when nobody answered | Business decisions belong to the business |
| `docs/data_contract.md` | What we agree to receive, and what happens if it is broken | Both sides know the rules |
| `explore/` | The investigation notebook: the narrative, importing the pipeline | Understanding the data is separate from production code |
| `reports/` | What reaches the client: the memo, the data diagnosis, the improvement, the spot-check | Three of the four are generated, so they cannot drift from the numbers |
| `reports/data_diagnosis.md` | The eleven problems that move the recommendation, numbered in risk order, plus the account of all 127 titles | The deliverable the brief asks for, beside the memo it supports |
| `config/settings.toml` | Every threshold, window and limit | Adjoa changes a value here, never in the code |
| `data/input/` | The candidate list, as given | Committed, never edited |
| `data/raw/`, `data/interim/` | Cached API responses and the shaped tables | Rebuilt from code, so never committed (ADR-002) |
| `data/processed/` | The ledger, the KPI tables, the timings, the run log | Committed: this is the evidence |

The five stages, and what each one is responsible for:

| Stage | Does | Leaves behind |
| --- | --- | --- |
| `extract` | Reads the id list as text, fetches details and credits with a timeout, retries and a rate limit, caches every response with a timestamp, shapes the nested JSON into one table per grain | `id_ledger.csv`, `fetch_log.csv`, `films/cast/crew/genres.csv` |
| `validate` | Profiles every column, flags every value worth a look with a verdict and a reason, applies the cleaning rules as flags rather than deletions | `profile.csv`, `flags.csv`, `exclusions.csv`, `sensitivity.csv` |
| `transform` | Collapses to film grain, proves every merge with `validate=` and an indicator, computes the KPIs for both time windows | `join_report.csv`, `id_accounting.csv`, `kpi_*.csv`, `shortlist_*.csv` |
| `checks` | The release gate, the live spot-check against TMDb, the time budget and the 500-title projection | `gate.csv`, `spotcheck.csv`, `time_budget.csv`, `projection.csv` |
| `load` | Writes the memo and the improvement note, and the ledger's final state | `reports/memo.md`, `reports/improvement.md` |

---

## The brief's five deliverables, and where each one is

If you are marking this against the brief, these five files are the deliverables. Everything else in
the repository is working material that supports them.

| The brief asks for | It is here |
|---|---|
| **Data diagnosis** — every problem found, how detected, what it does to the recommendation, ranked by risk, plus a full account of the candidate list | [`reports/data_diagnosis.md`](reports/data_diagnosis.md) |
| **Working analysis** — runs top to bottom from a clean clone, no manual edits, both time windows | `python run_pipeline.py`, the code in [`pipeline/`](pipeline), and [`explore/analysis.ipynb`](explore/analysis.ipynb) as the narrative |
| **Decision notes** — every judgement call where the brief left something open, what it costs if I am wrong, and what survives at 500 titles | [`reports/decision_notes.md`](reports/decision_notes.md) |
| **Client memo** — one page, business language, no jargon | [`reports/memo.md`](reports/memo.md) |
| **One improvement beyond the brief** — justified in the client's terms | [`reports/improvement.md`](reports/improvement.md), and the gate itself in `pipeline/checks/gate.py` |

Two supporting records sit beside them. [`decisions/`](decisions/README.md) holds the Architecture
Decision Records — how the system is built, which is a different question from the decision notes
and is marked under acquisition and the clean-clone requirement rather than under reasoning.
[`docs/self_audit.md`](docs/self_audit.md) holds what we checked without finding anything, and the
defects in this project rather than in the data.

---

## Layout and conventions

Three conventions govern how the code and the documents are arranged. They are stated here as the
current shape rather than argued for in decision records, because none of them changes a number:

- **Five stages, one package each.** `run_pipeline.py` calls extract, validate, transform, checks
  and load, in that order, once. A stage that does more than one job is a package with one module
  per job and an `__init__.py` holding the stage's entry point, so a stage stays one importable
  thing however many files are behind it.
- **Decisions live beside the code, in two places.** `decisions/` holds the Architecture Decision
  Records — how the system is built. `reports/decision_notes.md` holds the brief's Decision notes —
  the judgement calls that move the recommendation. The split is explained at the top of each.
- **The client-facing documents follow the house templates** in
  [`docs/templates.md`](docs/templates.md). In the memo that puts the recommendation in the subject
  line, because the template fixes the section order and a subject line is where a memo puts its
  conclusion.

---

## Where to start reading

| Location | What's in it |
|----------|--------------|
| [`reports/memo.md`](reports/memo.md) | **Start here.** One page: the recommendation, the shortlist, what we couldn't verify. Written for the room, not for engineers. |
| [`reports/data_diagnosis.md`](reports/data_diagnosis.md) | The eleven problems that move the recommendation, **numbered in risk order**, each traced to the code and test that handles it, plus the full account of where all 127 titles went. |
| [`decisions/`](decisions/README.md) | How the system is built: 18 decisions, one file each, with what we gave up and what would change our mind. |
| [`reports/decision_notes.md`](reports/decision_notes.md) | The analysis judgements: what counts as a franchise, why medians not means, how the era problem is handled. **Read M1, M4, M5, M6** if you read four. |
| [`docs/self_audit.md`](docs/self_audit.md) | What we checked and did not find (S-01–S-03), and the seven defects in this project rather than the data (S-04–S-10), three still open. |
| [`reports/improvement.md`](reports/improvement.md) | The one addition beyond the brief — a release gate — and why that one. |
| [`reports/spotcheck.md`](reports/spotcheck.md) | A live re-check of a stratified sample against the source, to catch our own errors. |
| [`data/processed/id_ledger.csv`](data/processed/id_ledger.csv) | Every title on the candidate list and what happened to it. Nothing disappears silently. |
| `data/processed/run_log.jsonl` | One JSON record per run: counts, timings, whether the gate passed. Appended to, never overwritten. |
| `data/processed/run_timings.csv` | How long each stage took, every time it has been run. What the time budget is computed from. |
| `data/processed/join_report.csv` | Every merge: rows in, rows out, what matched. Proof that no join quietly multiplied or dropped a film. |
| `data/processed/sensitivity.csv` | The headline comparison recomputed under each alternative setting. Read this to see whether the answer depends on a judgement call. |
| `data/processed/kpi_flip_check.csv` | Whether the answer changes between the two time windows, measure by measure. |
| `data/processed/kpi_uncertainty.csv` | How much of the headline gap survives resampling, measure by measure — with `kpi_uncertainty_by_franchise.csv`, which resamples whole franchises instead of individual films. Read this before quoting the gap. |
| `data/processed/kpi_position_paired.csv` | Each franchise's final entry against its own opener. The version of the position question that no change in the mix of franchises can move. |

---

## Changing how it works

Every threshold, window and limit is in [`config/settings.toml`](config/settings.toml), with a
comment explaining what it does. Change values there — not in the code. A key that cannot change
behaviour refuses to load rather than sitting there looking live (ADR-016).

| Setting | Why you'd change it |
|---------|---------------------|
| `input.expected_id_count` | The candidate list grows. Next year it's expected to be ~500. |
| `windows.modern.min_year` | The "recent films only" cutoff, currently 2000. |
| `performance.hit_roi_threshold` | What counts as a hit. 92% of this list clears it, which is itself a finding — see M9. |
| `talent.min_films_for_reliable` | How many films someone needs before we'll call them a reliable signal. |
| `shortlist.n_franchises` / `n_standalones` | How many names you want to negotiate from. |
| `gate.*` | What the release gate refuses to publish past. |

---

## When it doesn't work

**"No TMDb token found"** — step 4 of Setup hasn't been done, or `.env` still has the placeholder in
it. The message tells you exactly where to paste the token.

**It hangs, or says it can't reach the server** — no internet, or the API is down. If `data/raw/`
already has files from a previous run, the analysis still runs on those; the memo will carry the
older as-of date, which is why that date is printed on it.

**"RECONCILIATION NOTE: the brief says 127 titles, the file has N"** — not a failure. The candidate
list has changed size. Update `input.expected_id_count` and read the findings log to see what the
difference was (ADR-004).

**"The memo was not written, because these checks failed"** — not a crash. The analysis ran, and its
results should not go in front of a board without someone looking first: the title count did not
reconcile, or too few films survived, or too much of the money data is missing, or the live re-check
changed the answer. The message names which. Read [`reports/data_diagnosis.md`](reports/data_diagnosis.md), then either
fix the input or — if you have decided the run is sound anyway — set `gate.enabled = false` in
`config/settings.toml`, run again, and say in the meeting that you did.

**A number in the memo looks wrong** — check [`reports/spotcheck.md`](reports/spotcheck.md) first; it
compares a sample of our figures against the live source and classifies any differences. Then
`data/processed/id_ledger.csv`, which accounts for every title on the list.

---

## How it's built

For anyone picking this up to change it:

- [`decisions/README.md`](decisions/README.md) — how the system is built, in order, one file each.
  **Read this before changing any rule**; each one says what it would take to change its mind.
- [`reports/decision_notes.md`](reports/decision_notes.md) — what the numbers mean, M1 to M14. **Read this before
  changing any statistic**: M6 is the one where the conventional choice reverses the answer.
- [`reports/data_diagnosis.md`](reports/data_diagnosis.md) — what is actually wrong with the data, and
  where each finding is handled. Eleven findings, numbered in risk order.
- [`docs/self_audit.md`](docs/self_audit.md) — what we checked without finding anything, and what we
  got wrong ourselves. **Read S-07 to S-09 before a review**: those three are still open.
- [`docs/data_contract.md`](docs/data_contract.md) — what the pipeline relies on from the candidate
  list and from TMDb, and what it does when a rule is broken.
- [`docs/01_brief_and_guide.md`](docs/01_brief_and_guide.md) — the original brief, verbatim, so the
  work can be audited against what was asked.
- [`docs/archive/`](docs/archive) — the original planning document and build runbook, **superseded**.
  Both were written against an earlier ten-stage layout with the code in `src/streamvault/`, so
  their stage numbers and file paths no longer match the repository. Archived rather than deleted
  because they record why decisions were taken at the time; each carries a banner saying so. The
  current shape is the five stages below.

```bash
python -m pytest
```

298 tests, covering everything that does not need live data: parsing the candidate list, the
fetcher's caching and retry behaviour, the grain assertions, the join proofs, the cleaning rules,
the KPI definitions, the gate, and the memo's caveats.

They do **not** prove that a fresh clone works. Pytest is configured to find the code whether or not
`pip install -r requirements.txt` succeeded, so a green suite says nothing about whether
`python run_pipeline.py` runs for someone who has just cloned the repo. Only actually cloning it into
a new folder and running it proves that — which is how finding S-05 was caught, and why that check is
a step of its own rather than something the tests can be trusted to cover.
