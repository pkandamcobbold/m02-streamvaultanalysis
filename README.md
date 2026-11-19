# StreamVault back-catalog analysis

Which older films are worth licensing: franchise bundles, or standalone hits? This
project pulls public data on the candidate titles, checks it for problems, and
produces a recommendation with a shortlist to negotiate from — the same way every
time, so it can be re-run each quarter without anyone having to remember how.

> **Status: in progress — stages 1 to 7 of 10 work.** `python run_pipeline.py`
> loads the candidate list, fetches every film from TMDb, flattens and joins
> the results into one analysis-ready table of 112 films, profiles it for
> faults, applies the cleaning rules, and produces the KPI tables for both
> time windows — including the shortlist and the check on whether the answer
> changes after 2000. The timing, spot-check and memo stages are not built
> yet, so `reports/memo.md` and `spotcheck.md` do not exist. The stages that turn those into a recommendation are not
> built yet, so `reports/memo.md`, `spotcheck.md` and the KPI tables listed
> below do not exist. The project plan, the source brief and the full build
> runbook are in [`docs/`](docs/). This note goes away when the clean-clone
> test passes.

---

## Setup

You need Python 3.10 or newer and a free account on themoviedb.org.

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

Git Bash or macOS/Linux:

```bash
source .venv/Scripts/activate
```

```bash
pip install -r requirements.txt
```

**3. Get your own access token**

The data comes from The Movie Database, which asks each person to use their own
free credential rather than a shared one.

1. Create an account at <https://www.themoviedb.org/> and verify the email — the
   API page stays locked until you do.
2. Profile icon → **Settings** → **API** in the left sidebar.
3. Request a key: choose **Developer**, accept the terms, fill the short form.
   Approval is instant.
4. Copy the **API Read Access Token (v4 auth)** — the long value starting `eyJ`.
   Not the shorter 32-character key below it.

**4. Put the token where the project can find it**

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder with your token. No quotes, no spaces
around the `=`. That file is ignored by git and never leaves your machine.

---

## Run

```bash
python run_pipeline.py
```

**The first run fetches the data** — about half a minute for the current list of
117 ids, and it needs an internet connection. Every response is saved to
`data/raw/`, so **every run after that reads from disk**: the second run takes
about two seconds and makes no API calls at all. That is deliberate — a re-run
during a meeting does not depend on the network, it does not need the token, and
it does not hammer a service other people are sharing.

If a run is interrupted, just start it again. It picks up where it stopped —
including when it was interrupted *while writing* a file, which used to leave a
half-written response that broke every later run.

To refresh the data deliberately — a new quarter, say:

```bash
python run_pipeline.py --force
```

---

## Where the output goes

| Location | What's in it |
|----------|--------------|
| `reports/memo.md` | **Start here.** One page: the recommendation, the shortlist, what we couldn't verify. |
| `reports/data_diagnosis.md` | Every problem found in the source data, ranked by how much it affects the answer. |
| `reports/decision_log.md` | Every judgement call, why it was made, and what it costs if it's wrong. |
| `reports/spotcheck.md` | A live re-check of a sample of titles against the source, to catch our own errors. |
| `data/processed/id_ledger.csv` | Every title on the candidate list and what happened to it. Nothing disappears silently. |
| `data/processed/run_timings.csv` | How long each stage took, every time it has been run. Appended to, never overwritten. |
| `data/processed/join_report.csv` | Every merge: rows in, rows out, what matched. Proof that no join quietly multiplied or dropped a film. |
| `data/processed/id_accounting.csv` | Every title on the list and whether it reached the analysis. The table the memo's "112 of 127" sentence is read off. |
| `data/processed/profile.csv` | Every column: how much is present, how much is zero, and the shape of the distribution. |
| `data/processed/flags.csv` | Every value worth a second look, each with a verdict (is it an error or a real extreme?) and a reason. |
| `data/processed/exclusions.csv` | Every film left out of a metric, why, and the setting responsible — so any exclusion can be traced to a switch you can flip. |
| `data/processed/sensitivity.csv` | The headline comparison recomputed under each alternative setting. Read this to see whether the answer depends on a judgement call. |
| `data/processed/kpi_all_years.csv`, `kpi_modern.csv` | Franchise against standalone, one file per time window, with the film count beside every statistic. |
| `data/processed/kpi_flip_check.csv` | Whether the answer changes between the two windows, measure by measure. |
| `data/processed/shortlist_franchises.csv`, `shortlist_standalones.csv` | The picks, plus the runners-up they beat — so "why this one" has something to be compared against. |
| `data/processed/` | The KPI tables, timings and exclusions behind the memo. |
| `data/raw/` | Untouched copies of what the API returned, each stamped with when it was fetched. |

---

## Changing how it works

Every threshold, window and limit is in [`config/settings.toml`](config/settings.toml),
with a comment explaining what it does. Change values there — not in the code.

The ones most likely to need changing:

| Setting | Why you'd change it |
|---------|---------------------|
| `input.expected_id_count` | The candidate list grows. Next year it's expected to be ~500. |
| `windows.modern.min_year` | The "recent films only" cutoff, currently 2000. |
| `performance.hit_roi_threshold` | What counts as a hit. The answer is sensitive to this — see the decision log. |
| `talent.min_films_for_reliable` | How many films someone needs before we'll call them a reliable signal. |
| `shortlist.n_franchises` / `n_standalones` | How many names you want to negotiate from. |

---

## When it doesn't work

**"No TMDb token found"** — step 4 of Setup hasn't been done, or `.env` has the
placeholder text still in it. The message tells you exactly where to paste the
token.

**It hangs, or says it can't reach the server** — no internet, or the API is
down. If `data/raw/` already has files in it from a previous run, the analysis
can still run on those; the memo will carry the older as-of date, which is why
that date is printed on it.

**"RECONCILIATION NOTE: the brief says 127 titles, the file has N"** — not a
failure. The candidate list has changed size. Update `input.expected_id_count`
in the settings file to the new number, and read the diagnosis report to see
what the difference was.

**A number in the memo looks wrong** — check `reports/spotcheck.md` first; it
compares a sample of our figures against the live source and classifies any
differences. Then `data/processed/id_ledger.csv`, which accounts for every
title on the list.

---

## How it's built

For anyone picking this up to change it:

- [`docs/00_project_plan.md`](docs/00_project_plan.md) — the problem, the claims being
  tested, and the judgement calls. The *why*.
- [`docs/01_brief_and_guide.md`](docs/01_brief_and_guide.md) — the original brief,
  verbatim, so the work can be audited against what was asked.
- [`docs/02_build_runbook.md`](docs/02_build_runbook.md) — the build order, stage by
  stage, including every manual setup step. The *how*.

Logic lives in `src/streamvault/`, one module per pipeline stage.
`notebooks/analysis.ipynb` tells the story by calling those modules — it holds no
analysis of its own, so the numbers can never depend on which cells someone ran.

```bash
python -m pytest
```

Runs the tests, which cover the parts that don't need live data: parsing the
candidate list, the fetcher's caching and retry behaviour, the cleaning rules,
and the join assertions.

They do **not** prove that a fresh clone works. Pytest is configured to find the
code in `src/` whether or not `pip install -r requirements.txt` succeeded, so a
green suite says nothing about whether `python run_pipeline.py` runs for someone
who has just cloned the repo. Only actually cloning it into a new folder and
running it proves that, which is why that check is a step of its own in the
runbook rather than something the tests can be trusted to cover.
