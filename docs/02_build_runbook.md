# Build runbook — beginning to end

> Companion to [00_project_plan.md](00_project_plan.md) (the *what* and *why*) and
> [01_brief_and_guide.md](01_brief_and_guide.md) (the source material).
> This file is the *how*, in order, including the things only you can do by hand.

## How to read this

Every step is tagged:

- 🧑 **BY HAND** — you do this outside the repo (browser, file explorer, terminal). No code can do it for you.
- 💻 **CODE** — a file to create. Contents given, or specified precisely enough to write.
- ✅ **ARTEFACT** — what the step must leave behind. These *are* the deliverables. If a step produces no artefact you skipped something.
- 🧠 **JUDGEMENT** — a decision the brief doesn't settle. Gets a five-part decision record in `reports/decision_log.md`.

Don't skip the artefact column. The rubric is 40% reasoning and diagnosis; those marks come from artefacts written *while* you work, not from reconstructing your thinking at 11pm the night before.

---

# Phase 0 — Before any code

## Step 0.1 🧑 Check your tooling

```bash
python --version
```

You want 3.10 or newer (the code below uses `int | None` union syntax). Also confirm `git --version` works.

## Step 0.2 🧑 Register a TMDb API key

1. Go to <https://www.themoviedb.org/> and create a free account.
2. Verify the email — the API page stays locked until you do.
3. Profile icon → **Settings** → **API** in the left sidebar.
4. Request a key. Choose **Developer**, accept the terms, and fill the short form (application name: something like "StreamVault licensing analysis"; type: education/personal; URL: your GitHub repo URL is fine; summary: one sentence about analysing back-catalog films).
5. Approval is instant. You now have **two** credentials on that page:
   - **API Key (v3 auth)** — a 32-character hex string. Goes in a URL as `?api_key=...`.
   - **API Read Access Token (v4 auth)** — a long JWT starting `eyJ...`. Goes in an `Authorization: Bearer ...` header.

🧠 **DR-00: which credential to use.** Use the **v4 bearer token**. The key never appears in a URL, so it can't leak into the request paths you store in the cache, into a traceback, or into a log line. Cost if wrong: none — both authenticate the same endpoints. Record it anyway; it's a free decision record that shows you thought about secret handling.

Keep the page open; you'll paste the token in Step 1.6.

## Step 0.3 🧑 Get `id_list.csv` and put it somewhere safe

The brief says it's given. Download it from wherever the course provides it. Then:

- Save it to `data/input/id_list.csv` (you'll create that folder in Step 1.2).
- **Do not open it in Excel.** Excel will happily turn `550` into a number and `0000550` into `550`, and on save it rewrites the file. If it already went through Excel, re-download it.
- **Never edit it.** Not to remove a blank line, not to fix a stray `tt0137523`. Those are findings. Editing the input destroys the only evidence you had of the problem, and the "account for every id" requirement becomes unprovable.
- It gets committed to git. It's the given input, it's tiny, and the clean-clone run needs it.

## Step 0.4 🧑 Look at the file before pandas does

Before you write a line of parsing code, look at the bytes. Two minutes here saves an hour of confusion later.

> ### ⚠️ Which shell are you in?
>
> **These are Bash commands.** `wc`, `head`, `tail` and `grep` do not exist in PowerShell,
> which is the default terminal on Windows — you'll get *"wc is not recognized as the name
> of a cmdlet"*. Either run them in **Git Bash** (installed with Git, so you already have
> it), or use the PowerShell column below.
>
> Being able to read a file in whichever shell is in front of you is not a side quest. This
> is the step where you find out what you're dealing with.

| What you want | Bash / Git Bash | PowerShell |
|---------------|-----------------|------------|
| Count lines | `wc -l FILE` | `(Get-Content FILE).Count` |
| First 5 lines | `head -5 FILE` | `Get-Content FILE -TotalCount 5` |
| Last 5 lines | `tail -5 FILE` | `Get-Content FILE -Tail 5` |
| True line count | `grep -c "" FILE` | `(Get-Content FILE).Count` |
| Line endings | `file FILE` | `(Get-Content FILE -Raw) -match "`r`n"` |
| Byte-order mark | `head -c 3 FILE \| xxd` | `Format-Hex FILE -Count 3` |
| Blank lines | `grep -c "^$" FILE` | `(Select-String "^$" FILE).Count` |
| Lines that aren't ids | `grep -nvE "^[0-9]+$" FILE` | `Select-String -NotMatch "^[0-9]+$" FILE` |

Copy-paste versions for PowerShell, in order:

```bash
(Get-Content data/input/id_list.csv).Count
```

```bash
Get-Content data/input/id_list.csv -TotalCount 5
```

```bash
Get-Content data/input/id_list.csv -Tail 5
```

```bash
Select-String -NotMatch "^[0-9]+$" data/input/id_list.csv
```

### A bug in the obvious check

The last command is the valuable one, and the naive version of it is wrong:

```bash
grep -nv "^[0-9]*$" data/input/id_list.csv      # WRONG — hides blank lines
```

```bash
grep -nvE "^[0-9]+$" data/input/id_list.csv     # right
```

`[0-9]*` means *zero or more* digits, so it matches an **empty line**. Inverted, that means
blank rows are reported as "fine" and vanish from your results. `[0-9]+` means one or more.

One character, and the difference between seeing a missing row and not. That is the whole
lesson of this phase: **the check you write determines what you are able to see**, and a
check that reports nothing is indistinguishable from clean data until you test the check
itself.

### What you're looking for, and why each matters

| Look for | Why it matters |
|----------|----------------|
| A header row | 127 ids + 1 header = 128 lines. Reconcile against *data rows*, not file lines. |
| CRLF line endings | A trailing `\r` makes the value `"550\r"`, which won't match a digits-only pattern. Python's `read_csv` handles this; your hand-written `grep` checks may not. |
| A BOM (`efbb bf`) | The first id becomes `"﻿550"` and *only the first one* fails — a nasty thing to chase. |
| Blank lines | Rows you must account for, or file noise? Either way they're in the ledger. |
| More than one column | The brief says one column. More means the file isn't what you were told. |
| Sentinel values | `-1`, `0`, `N/A`, `TBC`, `#N/A`, `NULL` — a human's way of writing "no data". |
| Wrong namespace | `tt0468569` is an IMDb id, not a TMDb one. |
| Duplicates | Three sources merged over four years. Expect them. |

Write down what you find. It's the first entry in your diagnosis, and it's the honest answer to "how did you detect it": *by looking*.

> **Three sources merged over four years.** That's the brief telling you to expect exactly this: overlap between the sources (duplicates), formatting drift between them (one desk exported from Excel, one typed by hand), and possibly a header row from the middle file surviving into the merge.

---

# Phase 1 — Repo, secrets, environment

Order matters here. `.gitignore` exists **before** the first commit, and `.env` exists only after `.gitignore` names it. Get this backwards once and your key is in git history forever.

## Step 1.1 🧑 Confirm where you are

```bash
git status
```

You should be on `main` with `docs/` untracked and no commits yet.

## Step 1.2 🧑 Create the directory skeleton

```bash
mkdir -p config data/input data/raw data/interim data/processed src/streamvault notebooks tests reports
```

Git won't track empty folders, so leave a marker in the generated ones:

```bash
touch data/raw/.gitkeep data/interim/.gitkeep data/processed/.gitkeep
```

## Step 1.3 💻 `.gitignore` — first file, before anything else

See [`.gitignore`](../.gitignore) in the repo root for the version in use. The part worth understanding:

```gitignore
.env

data/raw/*
!data/raw/.gitkeep
data/interim/*
!data/interim/.gitkeep
```

> **Gotcha, and it bites people.** That must be `data/raw/*`, **not** `data/raw/`.
> A pattern ending in `/` excludes the *directory*, and git does not descend into an
> excluded directory — so the `!data/raw/.gitkeep` negation on the next line is never
> even evaluated, and the folder vanishes from the clone. `data/raw/*` excludes the
> *contents*, which leaves the negation reachable.
>
> Verify rather than assume:
>
> ```bash
> git check-ignore -v data/raw/.gitkeep
> ```
>
> The matching rule it prints should be the `!` line. If it prints the `data/raw` line
> instead, the negation isn't working.

Which folders are committed, and why:

| Folder | Committed? | Why |
|--------|-----------|-----|
| `data/input/` | yes | the given input; the clean-clone run needs it |
| `data/processed/` | yes | the ledger, KPI tables and timings are evidence, not cache |
| `data/raw/` | no | see DR-01 below |
| `data/interim/` | no | regenerable from raw in seconds |

🧠 **DR-01: don't commit the raw cache.** Options were (a) commit `data/raw/` so a clean clone needs no key or internet, (b) gitignore it and let the clean clone fetch once. Chose (b): TMDb's terms cover redistribution of their data, the cache for 500 titles is tens of MB of JSON, and the lab explicitly wants the fetching demonstrated. Cost if wrong: a clean-clone run needs a key and a network, and takes a few minutes the first time. Mitigated by the README saying so plainly. Note `data/processed/` **is** committed — the ledger, KPI tables and reports are evidence, not cache.

## Step 1.4 💻 `.env.example` — committed, placeholder only

```bash
# Copy this file to .env and paste your own token. .env is gitignored.
# Get a token: themoviedb.org -> Settings -> API -> API Read Access Token (v4 auth)
TMDB_BEARER_TOKEN=paste_your_v4_read_access_token_here
```

## Step 1.5 💻 `requirements.txt` and `pyproject.toml`

See [`requirements.txt`](../requirements.txt) and [`pyproject.toml`](../pyproject.toml) in the repo root.

Pinned exactly, not `>=`. Adjoa reruns this in a year; an unpinned pandas major version is how a pipeline that worked in October fails in March.

Two details that matter more than they look:

**`-e .` at the end of `requirements.txt`.** The code lives in `src/streamvault/`, which is not on Python's import path by default. Without this, `import streamvault` fails in `run_pipeline.py`, in the notebook and in the tests, and the usual workaround is a `sys.path.insert(...)` at the top of every entry point — which is exactly the kind of thing that works on your machine and breaks on Adjoa's. Installing the project itself in editable mode fixes it properly, and costs nothing: `pip install -r requirements.txt` already does it.

**`pythonpath = ["src"]` under `[tool.pytest.ini_options]`.** Belt and braces — it lets `python -m pytest` find the package even before the editable install has happened, so a fresh clone can run the tests immediately.

The src layout is worth the small amount of plumbing: it makes it impossible to accidentally import a half-finished module because you happened to be in the right directory, which is a real failure mode in a project you'll be running from three places.

## Step 1.6 🧑 Create the virtual environment and your real `.env`

```bash
python -m venv .venv
```

```bash
.venv\Scripts\Activate.ps1
```

(That's PowerShell. Git Bash: `source .venv/Scripts/activate`.)

```bash
pip install -r requirements.txt
```

Now copy the example and paste your token into the copy:

```bash
cp .env.example .env
```

Open `.env` in your editor and replace the placeholder with the v4 token from Step 0.2. No quotes, no spaces around the `=`, no trailing spaces.

## Step 1.7 🧑 Prove the secret is not tracked — before committing

```bash
git status --short
```

`.env` must **not** appear. If it does, `.gitignore` is wrong or misplaced — fix it before going further.

```bash
git check-ignore -v .env
```

That should print the `.gitignore` line that catches it. Silence means it is *not* ignored. Stop and fix.

## Step 1.8 💻 `config/settings.toml` — every knob Adjoa might turn

See [`config/settings.toml`](../config/settings.toml). The point of the file: Adjoa changes a threshold without editing code, and every number that drives the answer is visible in one place.

Every value in it is a 🧠. Don't invent the thresholds now and pretend they were principled — `hit_roi_threshold` and `min_budget_for_roi` are marked `TO SET AFTER PROFILING` for a reason, and both get a sensitivity row in the decision log once they're set.

Note which settings exist specifically so the *rejected* alternative stays runnable: `api.append_credits`, `performance.treat_zero_money_as_missing`, `franchise.min_members_on_list`, `talent.sensitivity_top_n_billed`. Flip one, re-run, and you can state the recommendation under the alternative instead of merely asserting it would hold. That is the difference between a decision record that earns the Evaluate marks and one that doesn't.

## Step 1.9 💻 `README.md` — write it for Adjoa, now, not later

See [`README.md`](../README.md). Written now rather than at the end, and kept true as the pipeline grows — it carries a visible status note saying `run_pipeline.py` doesn't exist yet, which goes away when the clean-clone test passes. A README that claims something that isn't true yet is worse than no README.

The five things it has to do:

1. What this is, in two sentences, no jargon.
2. **Setup** — clone, venv, install, token. Written so someone who has never used an API can follow it.
3. **Run** — one command, and the fact that the first run fetches (minutes, needs internet) while later runs read the cache (seconds).
4. **Where the outputs go**, with the memo first.
5. **When it doesn't work** — the likeliest messages and what each means.

Keep revising point 5 from the errors you actually hit while building. That section is worth real marks under "Adjoa reruns this next year without you", and it's the one part of a README that can only be written by someone who has already broken the thing.

Two notes on what the README deliberately does *not* say. It never names pandas, a DataFrame or an endpoint, because the person it's for doesn't care. And it frames the cache as *"a re-run during a meeting does not depend on the network, and it does not hammer a service other people are sharing"* — the reason, in her terms, not ours.

## Step 1.10 🧑 First commit

```bash
git add -A && git status --short
```

Read that list before committing. You are looking for `.env`, anything in `data/raw/`, and any file with a token in it.

```bash
git commit -m "Scaffold project: structure, secrets handling, config, requirements"
```

✅ **ARTEFACT** — a repo that a stranger can clone and set up from the README alone, with no secret in history.

---

# Phase 2 — Stage 1: load the id list

This is the step you asked about, so it gets the most detail. Loading a one-column CSV sounds trivial. It is where most of the "every id accounted for" marks are won or lost.

## The principle

**Read as text. Decide types yourself. Never let pandas guess.**

Here's what goes wrong if you don't. `pd.read_csv("id_list.csv")` on a file with one blank row gives you `float64`, because `NaN` can't live in an int column. Your ids become `550.0`, `11.0`, `nan`. Now `str(id)` in a URL produces `/movie/550.0` and every call 404s. You'd spend an hour debugging the fetcher for a bug that happened at read time.

Worse, it can *succeed* and still be wrong: one id read as a float, rounded, becomes a different real film.

So: `dtype=str`, `na_filter=False`, then an explicit classification step where every decision is yours and recorded.

## Step 2.1 💻 `src/streamvault/__init__.py`

```python
"""StreamVault back-catalog licensing analysis."""

__version__ = "0.1.0"
```

## Step 2.2 💻 `src/streamvault/config.py`

```python
"""Configuration: settings.toml plus the secret from the environment.

Loaded once, passed down. No module reads os.environ on its own, and nothing
anywhere prints the token.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS = PROJECT_ROOT / "config" / "settings.toml"


class MissingTokenError(RuntimeError):
    """Raised with instructions, not a traceback, when the token is absent."""


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]
    root: Path

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def path(self, relative: str) -> Path:
        """Resolve a settings path against the project root, never the cwd.

        This is what makes 'runs from a clean clone, no manual edits' true:
        no hard-coded absolute paths, and the pipeline works whatever
        directory you launch it from.
        """
        return self.root / relative


def load_settings(path: Path | None = None) -> Settings:
    settings_path = path or DEFAULT_SETTINGS
    with settings_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return Settings(raw=raw, root=PROJECT_ROOT)


def load_token() -> str:
    """Read the TMDb v4 bearer token from .env or the environment.

    Fails with an instruction Adjoa can act on, not a KeyError.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
    if not token:
        raise MissingTokenError(
            "No TMDb token found.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Get your token: themoviedb.org -> Settings -> API -> "
            "API Read Access Token (v4 auth)\n"
            "  3. Paste it after TMDB_BEARER_TOKEN= in .env\n"
            "See the README section 'Setup'."
        )
    return token
```

Note what this file does *not* do: it never logs the token, never puts it in a dataclass that might get printed in a traceback, and never returns it from anything but the one function that needs it.

## Step 2.3 💻 `src/streamvault/ingest.py` — the loader

```python
"""Stage 1 — load and validate the candidate id list.

GRAIN of the ledger: one row per row of the source file, forever.
Rows are never dropped from the ledger. A row that can't be used gets a
status and a reason. This table is how we prove "every id accounted for".
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# What a TMDb movie id looks like, and what the near-misses look like.
# ---------------------------------------------------------------------------
TMDB_ID_RE = re.compile(r"^\d+$")              # 550
IMDB_ID_RE = re.compile(r"^tt\d+$", re.I)      # tt0137523 — wrong namespace
FLOAT_LIKE_RE = re.compile(r"^\d+\.0+$")       # 550.0 — a dtype accident upstream

# Values that are a header, not data. Three merged sources means a header
# can turn up in the middle of the file.
HEADER_VALUES = {
    "id", "ids", "movie_id", "movie_ids", "tmdb_id", "tmdb id",
    "film_id", "title_id", "movie id",
}

LEDGER_COLUMNS = [
    "source_row", "raw_value", "tmdb_id", "status", "reason", "in_money_metrics",
]


def read_raw_rows(path: Path) -> pd.DataFrame:
    """Read the file as text and nothing else. One row out per row in.

    dtype=str          -> explicit dtype; pandas infers nothing
    na_filter=False    -> "" stays "", never becomes NaN, never forces float64
    header=None        -> we decide what is a header, in classify_value
    skip_blank_lines   -> False: a blank line is a row we must account for
    encoding utf-8-sig -> strips a BOM if one is present
    """
    try:
        frame = pd.read_csv(
            path,
            dtype=str,
            na_filter=False,
            keep_default_na=False,
            header=None,
            skip_blank_lines=False,
            encoding="utf-8-sig",
        )
    except UnicodeDecodeError:
        # A file that went through a Windows-era export may not be UTF-8.
        # Fall back, but record it: it is a finding about the source.
        frame = pd.read_csv(
            path,
            dtype=str,
            na_filter=False,
            keep_default_na=False,
            header=None,
            skip_blank_lines=False,
            encoding="latin-1",
        )
        frame.attrs["encoding_fallback"] = True

    if frame.shape[1] != 1:
        # The brief says one column. More means the file is not what we were
        # told; keep the first column but record the discrepancy loudly.
        frame.attrs["extra_columns"] = frame.shape[1] - 1

    return frame


def classify_value(raw: str) -> tuple[int | None, str, str]:
    """Classify one raw cell. Returns (tmdb_id, status, reason).

    Every branch here is a decision someone could disagree with, which is
    why each one has a reason string that ends up in the ledger.
    """
    text = raw.replace("﻿", "").replace(" ", " ").strip().strip('"').strip("'").strip()

    if text == "":
        return None, "invalid_id", "blank row"

    if text.lower() in HEADER_VALUES:
        return None, "header_row", f"header value {text!r} in the data"

    if IMDB_ID_RE.match(text):
        return None, "invalid_id", f"IMDb id {text!r}, not a TMDb id"

    if FLOAT_LIKE_RE.match(text):
        # 550.0 is almost certainly 550 that passed through a float column
        # somewhere upstream. Recovering it is a judgement call (see DR).
        return int(float(text)), "parsed", f"float-formatted {text!r}, recovered as integer"

    if TMDB_ID_RE.match(text):
        value = int(text)
        if value <= 0:
            return None, "invalid_id", f"non-positive id {text!r}"
        return value, "parsed", ""

    return None, "invalid_id", f"unparseable value {text!r}"


def build_ledger(path: Path, expected_id_count: int) -> pd.DataFrame:
    """Build the id ledger. One row per source row. Nothing is ever dropped."""
    raw = read_raw_rows(path)
    values = raw.iloc[:, 0].astype(str)

    classified = [classify_value(value) for value in values]
    ledger = pd.DataFrame(
        {
            "source_row": range(1, len(values) + 1),   # 1-based: matches a text editor
            "raw_value": values.to_numpy(),
            "tmdb_id": pd.array([item[0] for item in classified], dtype="Int64"),
            "status": [item[1] for item in classified],
            "reason": [item[2] for item in classified],
        },
        columns=["source_row", "raw_value", "tmdb_id", "status", "reason"],
    )
    ledger["in_money_metrics"] = pd.NA   # decided later, at cleaning

    # --- duplicates: keep the first occurrence, flag the rest ---------------
    is_dup = ledger["tmdb_id"].notna() & ledger["tmdb_id"].duplicated(keep="first")
    ledger.loc[is_dup, "status"] = "duplicate"
    first_seen = ledger.loc[ledger["tmdb_id"].notna()].drop_duplicates("tmdb_id")
    row_of_first = dict(zip(first_seen["tmdb_id"], first_seen["source_row"]))
    ledger.loc[is_dup, "reason"] = [
        f"same id as source_row {row_of_first[value]}"
        for value in ledger.loc[is_dup, "tmdb_id"]
    ]

    ledger.attrs["file_rows"] = len(ledger)
    ledger.attrs["header_rows"] = int((ledger["status"] == "header_row").sum())
    ledger.attrs["data_rows"] = ledger.attrs["file_rows"] - ledger.attrs["header_rows"]
    ledger.attrs["expected_id_count"] = expected_id_count
    return ledger


def reconciliation_summary(ledger: pd.DataFrame) -> pd.DataFrame:
    """Status counts. These must always add to the number of data rows."""
    counts = ledger.loc[ledger["status"] != "header_row", "status"].value_counts()
    return counts.rename_axis("status").reset_index(name="rows")


def assert_ledger(ledger: pd.DataFrame) -> None:
    """Assertions that must hold before we spend a single API call."""
    data_rows = ledger.attrs["data_rows"]
    expected = ledger.attrs["expected_id_count"]

    # Uniqueness of what we will actually fetch.
    to_fetch = ledger.loc[ledger["status"] == "parsed", "tmdb_id"]
    assert to_fetch.is_unique, "ids queued for fetching are not unique"

    # The counts must reconcile exactly.
    assert int(reconciliation_summary(ledger)["rows"].sum()) == data_rows, (
        "status counts do not add up to the number of data rows"
    )

    # The brief's number. A mismatch is a FINDING, not a crash: report it and
    # carry on, because the file is the truth and the brief is a claim.
    if data_rows != expected:
        print(
            f"[stage 1] RECONCILIATION NOTE: the brief says {expected} titles, "
            f"the file has {data_rows} data rows. Recorded as a diagnosis finding; "
            f"all reconciliation below is against {data_rows}."
        )


def load_id_list(path: Path, expected_id_count: int) -> tuple[pd.DataFrame, list[int]]:
    """Stage 1 entry point. Returns (ledger, ids to fetch)."""
    ledger = build_ledger(path, expected_id_count)
    assert_ledger(ledger)
    ids = ledger.loc[ledger["status"] == "parsed", "tmdb_id"].astype(int).tolist()
    return ledger, ids
```

### Why the assertion is soft on the count

The pipeline guide says "assert count". But think about what an `assert data_rows == 127` does in Adjoa's live meeting next quarter, when the list is 500 titles: it crashes the pipeline for being *correct*. So:

- **Hard assert** the things that are logically required: ids queued for fetch are unique, status counts reconcile to the row count.
- **Soft check with a loud note** on the brief's 127, because the file is the evidence and the brief is a claim. A mismatch is finding #1 in the diagnosis, which is exactly what the "Analyze" criterion rewards. And `expected_id_count` lives in `settings.toml`, so Adjoa changes it to 500 without touching code.

🧠 **DR-03: recovering `550.0` as `550`.** Options: (a) treat it as invalid and lose the film, (b) recover it. Chose (b) — the float formatting is near-certainly an upstream dtype accident, and the recovered id is verifiable: if it's wrong, TMDb 404s or returns a film whose title doesn't fit the list. Cost if wrong: a silently *different* film enters the analysis. Mitigation: these rows are flagged in the ledger and deliberately included in the Step 9 spot-check sample.

## Step 2.4 💻 `tests/test_ingest.py` — the parser is worth testing

The analysis as a whole can't be unit tested — it depends on live data. The parser can, and it's where a silent error is most expensive.

```python
import pandas as pd

from streamvault.ingest import build_ledger, classify_value


def test_plain_id():
    assert classify_value("550") == (550, "parsed", "")


def test_whitespace_and_quotes():
    assert classify_value('  "550" ')[0] == 550


def test_bom_prefix():
    assert classify_value("﻿550")[0] == 550


def test_float_formatted_id_is_recovered():
    tmdb_id, status, reason = classify_value("550.0")
    assert (tmdb_id, status) == (550, "parsed")
    assert "float" in reason


def test_imdb_id_is_invalid_not_silently_dropped():
    tmdb_id, status, _ = classify_value("tt0137523")
    assert tmdb_id is None and status == "invalid_id"


def test_blank_is_accounted_for():
    assert classify_value("")[1] == "invalid_id"


def test_header_is_detected_anywhere():
    assert classify_value("movie_id")[1] == "header_row"


def test_ledger_never_loses_a_row(tmp_path):
    path = tmp_path / "ids.csv"
    path.write_text("id\n550\n550\n\ntt0137523\n11\n", encoding="utf-8")
    ledger = build_ledger(path, expected_id_count=4)
    assert len(ledger) == 5                      # every source row survives
    assert ledger.attrs["data_rows"] == 4
    assert (ledger["status"] == "duplicate").sum() == 1
    assert ledger.loc[ledger["status"] == "parsed", "tmdb_id"].is_unique
```

Run them:

```bash
python -m pytest tests -q
```

✅ **ARTEFACT** — `data/processed/id_ledger.csv` (one row per source row, with status), the reconciliation summary, and a passing test suite. Commit here.

---

# Phase 3 — Stage 2: fetch, politely and once

## The principle

**Cache first, and never fetch the same id twice without a reason.** Three forces point the same way: TMDb is a shared service, Adjoa reruns this quarterly on a laptop, and you'll run the pipeline fifty times while building. A cache-first fetcher makes all three cheap, and makes the pipeline resumable for free — if it dies at film 80, the rerun starts at 81 because 1–79 are already on disk.

> **Green tests do not mean a clean clone works.** `pyproject.toml` sets
> `pythonpath = ["src"]`, so pytest imports the package whether or not the editable
> install succeeded. Only Phase 12's clean-clone test proves the pipeline runs for
> someone who just cloned the repo; it cannot be skipped on the strength of a green
> suite.

## Step 3.1 💻 `src/streamvault/fetch.py`

The module is in the repo; read it there rather than from a listing in a document
that can drift out of date. What follows is the part you cannot see by reading it:
why it is shaped this way.

**Five things it guarantees, each with a test that would fail if it stopped being true:**

| Guarantee | Why it is not obvious | Test |
|---|---|---|
| The token is in a header, never a URL or a cached file | a key in a query string reaches shell history, logs, exception text and the cached `request_path` | `test_token_never_reaches_the_url_or_the_cache_file` |
| A second run makes zero calls | this is what makes the pipeline resumable *and* runnable offline in a meeting | `test_a_second_run_is_all_cache_and_costs_no_calls` |
| A 404 is cached, recorded, and never retried | a missing film is an answer; retrying it five times is slow and rude to a shared service | `test_404_is_not_retried` |
| Toggling `append_credits` cannot serve the wrong cache | the two modes request different things, so they must write different filenames | `test_toggling_append_does_not_serve_a_credit_less_cache` |
| A missing credits block is not an empty cast list | one means we cannot see the cast; the other means there isn't one. Collapsing them hides a fetch failure as a real fact | `test_no_credits_block_is_distinct_from_an_empty_cast` |
| An interrupted write leaves no half-written file | `write_text` is not atomic; a truncated cache entry breaks *every* later run, not just this one | `test_an_interrupted_write_leaves_no_partial_file` |
| A corrupt cache entry is a miss, not a crash | the old failure was a `JSONDecodeError` naming neither the film nor the fix | `test_a_corrupt_cache_entry_is_refetched_not_raised` |
| The log reads back with the dtypes it was written with | the CSV holds `139`; a plain `read_csv` returns `139.0`, because the column also holds blanks for the ids that 404'd | `test_the_fetch_log_round_trips_without_floating_the_counts` |

**The cache key carries the policy.** `550__details_credits.json` and
`550__details.json` are different files on purpose. If both modes wrote to
`550__details.json`, flipping `api.append_credits` would read a response fetched
under the other policy and the fetcher would report credits it never received. The
filename is the only place that distinction can live, because the cache is checked
before anything knows what the response contains.

**`fetch_one` returns `(envelope, from_cache)`,** not just the envelope.
`from_cache` describes *this run*, not the response — writing it into the JSON
would make every cached file claim forever that it had been fetched live.

**The session is built lazily, on the first cache miss.** So a fully cached run
needs neither a token nor a network, and a missing token only becomes an error at
the moment something actually has to be fetched. That is the difference between
"the analysis re-runs in a meeting" and "the analysis re-runs in a meeting with
wifi".

**`fetched_at` is UTC and says so.** A naive local timestamp in a file that
outlives a clock change is not evidence of anything, and this field is what the
memo's as-of date rests on.

> **"No row loops" does not apply here.** That rule is about stage 7 — don't loop
> over DataFrame rows to compute statistics. Fetching is sequential I/O against a
> rate-limited service; a loop is the right shape. Said explicitly in the decision
> log so it doesn't read as an oversight.

✅ **ARTEFACT** — `data/processed/fetch_log.csv`: one row per id with HTTP status,
`fetched_at`, cache hit, calls made, and whether credits arrived. Integer columns
are `Int64`, for the same reason stage 1 is explicit about dtype: one film with no
credits block must not turn every count in the column into a float.

## Step 3.2 🧠 DR-02: one call per film or two

The brief names two endpoints. TMDb also supports `?append_to_response=credits`, which returns details **and** credits in one response.

- **Two calls**: literally what the brief describes. 127 films = 254 calls; 500 films = 1000 calls.
- **One call with append**: 127 films = 127 calls; 500 = 500. Half the load on a shared API, roughly half the acquisition time, and the same data.

Decision: **append, with the two-call path kept behind the `api.append_credits` flag in settings.** That way the alternative isn't hypothetical — you can run it both ways and show the timing difference, which is what "rejected alternatives are real" means. Cost if wrong: none to correctness, but you must still prove credits came back for every film, so the fetch log carries a `has_credits` column and stage 4 asserts on it.

## Step 3.3 🧑 Smoke-test on three ids before fetching 117

Don't discover an auth problem on call 90. Three ids first:

```bash
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'src'); from streamvault.config import load_settings, load_token; from streamvault import fetch as F; s=load_settings(); ctx=F.context_from_settings(s); sess=F.build_session(load_token(), 5, 0.5); print([F.fetch_film(sess, ctx, i) for i in (550,155,603)])"
```

Checked, and what came back: status 200 for all three, `fetched_at` in the current
hour, credits present, cast counts 75 / 139 / 37.

Then prove the token is not in the files it just wrote — and be careful which
check you use, because the obvious one lies:

```bash
grep -rl "Bearer" data/raw/
```

That printed **three files**, and all three are false positives: `"Medal Bearer"`
and `"Flag Bearer"` are character names in the Star Wars credits. A check that
cries wolf is as useless as one that stays silent — the second time it fires you
stop reading it. Grep for the thing that would actually be wrong:

```bash
grep -rl "Authorization" data/raw/
```

Nothing, which is what it must print. Then check the real token itself, without
printing it:

```bash
.venv/Scripts/python.exe -c "import sys,pathlib; sys.path.insert(0,'src'); from streamvault.config import load_token; t=load_token(); print([str(p) for p in pathlib.Path('data/raw').rglob('*') if p.is_file() and t in p.read_text(encoding='utf-8',errors='ignore')] or 'NONE')"
```

`NONE`. (A test asserts the same guarantee, but against a fake token; this checks
the real one.)

🧠 **The second time this project has been caught by its own check.** The first
was `grep -nv "^[0-9]*$"`, which reported a blank line as fine because `[0-9]*`
matches zero digits (F4). Both failures are the same shape: the check was written
by thinking about what the answer should be, not about what else could produce that
answer. Write the check, then feed it a case you know the answer to.

## Step 3.4 🧑 Settle row 95 with a live `/find` call

This is F3, and it is worth doing before the full fetch because the answer changes
what gets fetched. `resolve_foreign_ids` does it for every IMDb-shaped row it finds,
so it also covers next quarter's file.

**Result:** `tt0468569` → TMDb **155, *The Dark Knight* (2008-07-16)** — already on
the list at rows 2 and 91. The hypothesis in the diagnosis held: resolving it would
have added a *third* copy of one franchise film rather than recovering a lost one.
Row 95 is excluded as `duplicate_other_namespace`. Recorded as DR-05.

🧠 **The lesson worth keeping.** The obvious fix and the correct fix pointed in
opposite directions, and the only thing that separated them was asking what the row
*was* before deciding what to do with it. Nothing in the data looked wrong about
recovering it.

## Step 3.5 🧑 Then the full fetch, once

```bash
.venv/Scripts/python.exe run_pipeline.py
```

**Measured from an empty cache:** 117 API calls for 117 films in **20.3s**, append
mode. A second run: **0 calls, 2.3s**. The briefed two-call path would have issued
234.

Every run appends these to `data/processed/run_timings.csv`, so the figure in the
decision log can be checked against something. `fetch_log.csv` is overwritten each
run, so after one cached re-run it reports 1 call in 0.7s — true of that run, and no
longer evidence for a claim about acquisition cost. A number quoted in a report and
held nowhere else is a memory, not a measurement.

Then read what came back rather than assuming:

```bash
.venv/Scripts/python.exe -c "import pandas as pd; d=pd.read_csv('data/processed/fetch_log.csv'); print(d.http_status.value_counts()); print('credits for every 200:', bool(d[d.http_status==200].has_credits.all()))"
```

✅ **ARTEFACT** — `data/raw/` full of envelopes, `data/processed/fetch_log.csv`, and
an `id_ledger.csv` that now reconciles **127 = 112 fetched + 6 duplicate + 5
not_found_404 + 3 invalid + 1 duplicate_other_namespace**.

## Step 3.6 🧠 DR-06: ask what the 404s have in common

Five ids returned 404. "Five 404s" is a sentence; the finding is in what they share.

Positions in the file — rows 18, 35, 73, 93, 99 — say nothing: they are spread
through it. The ids say everything. Every one of the 112 that resolved is ≤ 301,528;
every dead one is ≥ 7,733,901, with nothing in between and two consecutive pairs.
TMDb issues ids sequentially, so those five belong to entries created long after any
real back-catalog film's entry, and later removed.

```bash
.venv/Scripts/python.exe -c "import pandas as pd; l=pd.read_csv('data/processed/id_ledger.csv'); print(l.groupby(l.status=='not_found_404').tmdb_id.agg(['min','max','count']))"
```

🧠 **What makes this a finding rather than a tidy-up.** It changes the risk
*downward*: a random loss of 5 films could skew the comparison, while five entries
that were probably never back-catalog films cannot skew it much. And it leaves a gap
that cannot be closed — a deleted entry has no year and no collection, so there is
no way to test whether the loss falls unevenly on pre-2000 films or franchises. Say
that in the memo. An unclosable gap stated plainly reads as competence; the same gap
unmentioned reads as an oversight when someone finds it.

---

# Phase 4 — Stage 3: flatten to tables

## The principle

**One table per grain, and the grain written in a comment at the top of the function.** You will have six frames open by Thursday and you will not remember which one has one row per film. The comment is for you, three days from now.

## Step 4.1 💻 `src/streamvault/flatten.py`

Build these, each from the cached envelopes:

| Table | Grain | Key fields |
|-------|-------|-----------|
| `films` | one row per film | `tmdb_id`, `imdb_id`, `title`, `release_date`, `status`, `budget`, `revenue`, `runtime`, `vote_average`, `vote_count`, `popularity`, `adult`, `original_language`, `collection_id`, `collection_name` |
| `cast` | one row per film per cast member | `tmdb_id`, `person_id`, `name`, `character`, `billing_order` |
| `crew` | one row per film per crew credit | `tmdb_id`, `person_id`, `name`, `job`, `department` |
| `genres` | one row per film per genre | `tmdb_id`, `genre_id`, `genre_name` |

Use `pd.json_normalize` with `record_path` and `meta` for the nested lists, e.g.:

```python
cast = pd.json_normalize(
    payloads,                                  # list of credit payloads
    record_path=["cast"],
    meta=["id"],
    meta_prefix="film_",
    errors="ignore",                           # a film with no cast must not crash this
)
```

Three things to get right:

1. **`belongs_to_collection` is a nested object or `null`.** Flatten it to two flat columns on `films` — `collection_id`, `collection_name` — in one place, once. This single field is the entire franchise/standalone split, so it deserves its own assertion: no film may have a `collection_name` without a `collection_id`.
2. **Rename generated columns once, immediately.** `json_normalize` gives you `id`, `film_id`, `belongs_to_collection.name`. Rename at the point of creation, never twice, never downstream. Dots in column names break attribute access and will bite you.
3. **A film with no cast or no crew still exists.** Its absence from `cast` must not remove it from `films`. That's what stage 4's `indicator=True` is for.

✅ **ARTEFACT** — row counts and stated grain per table; the counts go in the diagnosis. `len(films)` must equal the number of ids with HTTP 200.

---

# Phase 5 — Stage 4: the proven join

## The principle

**A join you didn't validate is a guess.** The two failure modes are silent: a left join that drops films (you under-count and never notice), and a one-to-many join that duplicates a film's revenue once per director (you double-count the money and the KPI looks plausible).

## Step 5.1 💻 `src/streamvault/join.py`

```python
# GRAIN: one row per film. Directors collapsed to a list/count first so the
# merge stays one-to-one and a co-directed film's revenue is counted once.
directors = (
    crew.loc[crew["job"] == "Director", ["tmdb_id", "person_id", "name"]]
        .drop_duplicates()                      # same person credited twice
)
director_counts = (
    directors.groupby("tmdb_id", as_index=False)
             .agg(director_count=("person_id", "size"),
                  director_names=("name", lambda names: " | ".join(sorted(names))))
)

films_with_directors = films.merge(
    director_counts,
    on="tmdb_id",
    how="left",                 # a film with no director must survive
    validate="one_to_one",      # proves the right side has one row per film
    indicator=True,             # proves which films had no director at all
)

assert len(films_with_directors) == len(films), "join changed the film count"
join_report = films_with_directors["_merge"].value_counts()
```

The same pattern for the lead actor: filter `cast` to `billing_order == 0`, **then** `drop_duplicates("tmdb_id")`, then merge `one_to_one`. Don't merge the whole cast table into `films` and then aggregate — that's where the revenue duplication happens.

✅ **ARTEFACT** — the join report (`both` / `left_only` / `right_only` counts) for every merge, plus the `left_only` list: those are the films with no director or no cast, which is itself a diagnosis finding.

> **Learning checkpoint.** Why does `validate="one_to_many"` matter for directors? Because without it, a film with two directors produces two rows, and `films["revenue"].sum()` silently counts that film's revenue twice. The number stays plausible — which is exactly why it's dangerous.

---

# Phase 6 — Stage 5: profile and diagnose

## The principle

**Detect first, decide later.** This phase produces no fixes. It produces a list of candidate faults. Deciding which are real and what to do about them is Phase 7, and keeping the two separate is what stops you from "fixing" something that was never broken.

## Step 6.1 💻 `src/streamvault/profile.py`

One `profile(frame)` function, reused on every table. For each column: dtype, non-null count, null count, distinct count, min/max (numeric and dates), and the **disguised-null** counts that `isna()` will never show you:

| Disguised fault | The check | Why it's not a null to pandas |
|-----------------|-----------|-------------------------------|
| `budget == 0` | `(films["budget"] == 0).sum()` | Zero is a valid integer |
| `revenue == 0` | same | ditto |
| `release_date == ""` | `(films["release_date"] == "").sum()` | Empty string is a valid string |
| `runtime == 0` or null | both | a film with no runtime |
| implausibly small money | `films["budget"].between(1, 1000)` | budget of `5` — reported in millions by mistake |
| unreliable rating | `films["vote_count"] < 10` | the rating is real, the sample isn't |
| non-feature entries | `adult`, `status != "Released"`, `runtime < 40` | all valid values |
| merged/duplicate films | duplicate `imdb_id`, or duplicate (title, release year), across *different* `tmdb_id` | two ids, one film — invisible until after the fetch |

## Step 6.2 🧑 The part that earns the Analyze marks

For **every** candidate fault, answer four questions in `reports/data_diagnosis.md`. Three are easy. The third is the one that decides the risk rank:

1. **How did you detect it?** The actual check, as code.
2. **How many rows?**
3. **Which group does it hit?** Franchise or standalone? Pre- or post-2000? **This is the whole game.** 40 zero-budget films spread evenly across both groups barely moves the comparison. Eight zero-budget films that are all franchise entries will flatter or damn franchises depending on which way you treat them, and that *is* the recommendation.
4. **What does it do to the recommendation?** Compute the headline KPI both ways and show the two numbers.

Then rank by the size of the answer to #4. A ranked list of four findings with numbers beats a flat list of twenty without.

```python
# The shape of the check that produces #3 — do this for every fault
films.assign(
    is_franchise=films["collection_id"].notna(),
    era=np.where(films["release_year"] >= 2000, "2000+", "pre-2000"),
    zero_budget=films["budget"].eq(0),
).groupby(["is_franchise", "era"])["zero_budget"].agg(["sum", "size", "mean"])
```

## Step 6.3 🧠 Real extremes stay

A $2bn-revenue film is real. A 1977 film with a $11M budget is real. Do not winsorise, clip or drop them because they're far from the median — you'd be deleting the exact films Kwame is trying to buy. Errors get flagged; extremes stay. Write this down, because "we removed outliers" is the single most common way an analysis of licensing value destroys its own answer.

✅ **ARTEFACT** — `reports/data_diagnosis.md` with a ranked table, and a profile output per table in `data/processed/`.

---

# Phase 7 — Stage 6: clean, with a record per decision

## The principle

**Never delete, always flag. And parameterise, so every metric can be computed both ways.**

A cleaning rule that is a hard-coded `df = df[df.budget > 0]` can only be defended by argument. A rule that's a parameter can be defended by *number*: "under the alternative, franchise median ROI is 1.8× instead of 2.4×, and the recommendation does not change."

## Step 7.1 💻 `src/streamvault/clean.py`

Every rule takes its threshold from settings and adds a **flag column**, never removes a row:

```python
def flag_money_quality(films: pd.DataFrame, treat_zero_as_missing: bool, min_budget: int) -> pd.DataFrame:
    """Add flags. Removes nothing. Every exclusion downstream reads a flag."""
    out = films.copy()
    out["budget_missing"] = out["budget"].eq(0) if treat_zero_as_missing else False
    out["revenue_missing"] = out["revenue"].eq(0) if treat_zero_as_missing else False
    out["budget_implausible"] = out["budget"].between(1, 1000)
    out["roi_unstable"] = out["budget"].lt(min_budget) & ~out["budget_missing"]
    out["in_money_metrics"] = ~(out["budget_missing"] | out["revenue_missing"] | out["budget_implausible"])
    return out
```

Then the exclusions table is derived, not performed: `films.loc[~films["in_money_metrics"]]` with the reason columns. And `in_money_metrics` flows back into the ledger, which is how a film can be *analysed* and still be absent from the ROI numbers — a distinction the memo has to make honestly.

## Step 7.2 🧑 Write the decision records now, not later

Use the five-part template for each. The ones you will certainly need:

| DR | The call | Why it's contested |
|----|----------|--------------------|
| What is a franchise? | `belongs_to_collection` not null, vs ≥2 members on our list | A collection with one film on the list isn't a bundle anyone can buy |
| What is a bundle? | only the films on our list, vs the whole collection | Pricing a six-film bundle on the three good ones you happen to have |
| What is performance? | revenue, ROI, profit, rating, vote_count | ROI explodes on tiny budgets; revenue favours the big-budget era; ratings ignore reach |
| What is a hit? | ROI ≥ 2.5×, vs above median, vs top quartile | The threshold *is* the hit rate. Sensitivity-test it or it's arbitrary |
| Zero money | disguised null vs real flop | Whichever group has more zeros gets flattered |
| Inflation | CPI-adjust, vs use ratios, vs drop pre-2000 | Yaw will ask. Ratios are inflation-neutral *within* a film |
| Lead actor | `billing_order == 0` vs top-3 billed | Ensemble films |
| Reliable talent | minimum film count | A "star" with two films misleads a negotiator |

And the one that has to be in there:

🧠 **DR: selection bias in franchises.** Sequels only get commissioned when the first film succeeded. So franchises will look safer *partly because their failures never became franchises*. You cannot correct for this with the data you have. Name it, quantify what you can (compare first entries only vs all entries), and state in the memo that the franchise advantage is an upper bound. This is the single highest-value paragraph in the decision notes: it's the kind of reasoning the Evaluate criterion exists to reward, and almost nobody writes it.

✅ **ARTEFACT** — `reports/decision_log.md` (five parts each, risk-ranked), `data/processed/exclusions.csv`, and the ledger's `in_money_metrics` column filled in.

---

# Phase 8 — Stage 7: KPIs, both windows

## The principle

**Counts beside every statistic, and the window as a parameter.** A median with no `n` is not a finding. And "both windows" means one function called twice, never two blocks of copy-pasted code — because copy-paste is how the two windows silently diverge.

## Step 8.1 💻 `src/streamvault/kpis.py`

```python
def compare_groups(films: pd.DataFrame, min_year: int | None) -> pd.DataFrame:
    """Franchise vs standalone for one window. min_year=None means all years.

    Named aggregation, counts beside every statistic, no row loops.
    """
    scope = films if min_year is None else films.loc[films["release_year"] >= min_year]
    money = scope.loc[scope["in_money_metrics"]]
    return money.groupby("is_franchise", as_index=False).agg(
        films=("tmdb_id", "size"),
        median_roi=("roi", "median"),
        lower_quartile_roi=("roi", lambda s: s.quantile(0.25)),   # the floor
        mean_roi=("roi", "mean"),
        roi_spread=("roi", "std"),
        hit_rate=("is_hit", "mean"),
        hits=("is_hit", "sum"),
        median_rating=("vote_average", "median"),
        median_votes=("vote_count", "median"),
    )
```

Note which statistics are there and why: Kwame's question is about **risk**, not average. The claim "franchises are the safer buy" is a claim about the *floor* and the *spread*, so the lower quartile and the standard deviation matter more than the mean. A comparison on means alone doesn't answer what he asked.

## Step 8.2 💻 The flip check — make it shout

```python
def flip_check(all_years: pd.DataFrame, modern: pd.DataFrame) -> dict:
    """C2: if the recommendation changes between windows, say so loudly."""
    winner_all = all_years.loc[all_years["median_roi"].idxmax(), "is_franchise"]
    winner_modern = modern.loc[modern["median_roi"].idxmax(), "is_franchise"]
    flipped = bool(winner_all != winner_modern)
    if flipped:
        print("=" * 70)
        print("RECOMMENDATION FLIPS BETWEEN WINDOWS — see the memo's first line")
        print("=" * 70)
    return {"flipped": flipped, "all_years": winner_all, "modern": winner_modern}
```

If it flips, that goes in the memo's **first paragraph**, not a footnote. The brief says "loudly" — and a flip is genuinely the most useful thing you could tell Kwame, because it means Yaw's objection changes the answer and he needs to know before the room does.

## Step 8.3 💻 The rest of the KPI set

- **Position within franchise** — rank entries by release date inside each collection; compare first vs middle vs last. This tests the "weak middle entries" claim, which is half the team's position and nobody has numbers for.
- **Bundle-level economics** — aggregate to the collection, because that's the unit of purchase. A bundle's value is its *total*, and its risk is its weakest entries.
- **Talent** — group `cast` (`billing_order == 0`) and directors by `person_id`; report film count, median performance, hit rate, spread. Filter to `min_films_for_reliable`, but **report the count beside every name** so a negotiator can see a 3-film star for what it is.
- **The shortlist** — 3 franchises, 5 standalones, by a rule simple enough to say out loud. Show the runners-up; "why it made the cut" means something only next to what didn't.

✅ **ARTEFACT** — `data/processed/kpi_*.csv` per window, the flip flag, bundle table, talent table, shortlist with runners-up, and verdicts written into `reports/claims.md` against the claim register in the project plan.

---

# Phase 9 — Stage 8: the time budget

## Step 9.1 💻 `src/streamvault/timing.py`

A context manager that records `time.perf_counter()` per stage into a list, then a table.

## Step 9.2 🧠 State the boundary explicitly

"Acquisition excluded" needs a definition, because a cache hit is a disk read and a cache miss is a network round-trip:

> **The budget covers stages 3–7** (flatten, join, profile, clean, KPIs), measured with the cache already warm. Stage 1 (reading the file) is included as it is trivially fast. Stage 2 (fetch) is excluded whether it hits the network or the cache, since reading 127 JSON files from disk is part of acquisition, not analysis.

Then project to 500 titles and say which stages scale how. Most are linear in films. The ones that aren't: anything grouped by person (scales with cast size, not film count) and any self-join within collections. Measure, then state the projection as a range with the assumption attached.

🧠 **DR: the time budget number.** The brief references a client time budget but gives no figure. Decide one — 10 seconds for the analysis stages on a laptop — and justify it from the use case: Adjoa runs this live in a meeting, so the gap between pressing enter and having an answer must be shorter than the gap in conversation it creates.

✅ **ARTEFACT** — `data/processed/timings.csv`, the stated boundary, the 500-title projection.

---

# Phase 10 — Stage 9: spot-check against the live API

## The principle

**This is the only stage that can tell you your own output is wrong**, and the pipeline guide says plainly that it's the biggest gap in the module. Budget real time for it.

## Step 10.1 💻 `src/streamvault/spotcheck.py`

The **four slices** are franchise/standalone × pre-2000/2000+. Sample `films_per_slice` from each (seeded, so the sample is reproducible), re-fetch live with `force=True` into a separate cache folder, and compare field by field against what the analysis used.

Deliberately include in the sample: a film whose id you recovered from `550.0`, and a film with a disguised null. Those are the rows most likely to be wrong, and a sample that avoids them isn't a check.

## Step 10.2 🧑 Classify every discrepancy

Not "12 fields differed" — every difference gets a class:

| Class | Example | What it means |
|-------|---------|---------------|
| **Our bug** | we flattened the wrong field, or lost precision | fix the code |
| **Source revision** | TMDb's revenue updated since your fetch | legitimate; this is what the as-of date is for |
| **Volatile by nature** | `popularity`, `vote_count`, `vote_average` | expected to drift daily; don't build the recommendation on them |
| **Still unexplained** | can't account for it | say so — an honest unknown beats a confident guess |

Then the question that matters: **does any discrepancy move the recommendation?** Recompute the headline KPI with the live values for the sampled films and show whether the winner changes.

> **Why `popularity` drifting is a finding, not noise.** If a discrepancy shows up in a field your shortlist ranks on, your shortlist isn't stable between Tuesday and Thursday. That's a reason to rank on revenue and ROI rather than popularity — and now you can defend that choice with evidence instead of taste.

✅ **ARTEFACT** — `reports/spotcheck.md`: the sample, the per-field comparison, every discrepancy classified, and a yes/no on whether the recommendation moves.

---

# Phase 11 — Stage 10: what reaches the client

## Step 11.1 💻 `run_pipeline.py` — the one command

```python
"""One command, top to bottom, from a clean clone. python run_pipeline.py"""
```

It calls the stages in order 1 → 10, prints a readable line per stage, writes every artefact, and fails with a message a non-programmer can act on. No notebook needed to produce the numbers.

## Step 11.2 💻 `notebooks/analysis.ipynb` — the narrative

Imports from `src/`, calls the same functions, and shows the story: here's the comparison, here's the flip check, here's the shortlist. **No analytical logic lives only in the notebook.** If a number exists in a cell and nowhere in `src/`, it isn't reproducible and it won't survive Adjoa's rerun.

## Step 11.3 🧑 `reports/memo.md` — one page, for the room

Write it last, and write it for Kwame, who is not a programmer and is going to be challenged live by Yaw. No tool names. No "pandas", no "ROI" without a plain-English gloss, no "null".

Order it the way the room will consume it:

1. **The recommendation**, in one sentence, first line. If it flips between windows, *that* is the first line instead.
2. **Why**, in three sentences with the numbers that matter.
3. **The shortlist** — 3 franchises, 5 standalones, one line each saying why it made the cut.
4. **Both windows**, side by side, with the counts visible.
5. **The deal note** — one paragraph on the strongest franchise: what to pay *relative to everything else*, and the single number that drove the view. Relative, not absolute: you have no licensing prices, so you cannot name a dollar figure, and pretending otherwise is the fastest way to lose the room.
6. **What you couldn't stand behind, and what it costs him.** Missing money fields and how many. No licensing prices. No streaming viewership — TMDb gives box office and audience ratings, which are a *proxy* for streaming value, not the thing itself. Era effects. Selection bias in franchises. The 404s.
7. **As-of date of the data**, and the count: "127 received → X analysed → Y removed, for these reasons."

## Step 11.4 🧑 `reports/improvement.md` — pick one, justify it in their terms

Candidates, strongest first for *this* client:

- **Data-quality gate** — the pipeline refuses to produce a shortlist if reconciliation fails or the missing-money share crosses a threshold, with a readable message. Value: Adjoa is running this live in a meeting. The failure mode you're protecting against is her presenting a confident number from a broken run, in front of the board, with no way to know.
- **Sensitivity panel** — one table showing whether the recommendation survives each judgement call being flipped. Value: it's the answer to Yaw, pre-computed, before he asks.
- **Run-over-run diff** — what changed since last quarter: new ids, revised TMDb figures, shortlist movements. Value: directly serves the quarterly rerun, and catches source revisions automatically.
- **Bundle dead-weight score** — the share of a bundle's films below the standalone median. Value: a negotiating number. "You're asking us to pay for three films that underperform the standalones we could buy instead."

Justify in terms of *their* problem, not the code's elegance. That's what the criterion asks for.

---

# Phase 12 — The clean-clone test

**If this fails, the lab isn't done, whatever state the analysis is in.** 20% of the marks say "runs top to bottom from a clean clone, no manual edits".

## Step 12.1 🧑 Clone into a different folder, as a stranger would

```bash
git clone https://github.com/pkandamcobbold/m02-streamvaultanalysis.git /c/temp/clean-clone-test
```

```bash
cd /c/temp/clean-clone-test && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Paste your token into that `.env`, then:

```bash
.venv/Scripts/python run_pipeline.py
```

## Step 12.2 🧑 What you're actually testing

- No absolute paths. If anything references `C:\Users\PaapaAndam-Cobbold\...`, it fails here.
- `data/input/id_list.csv` is committed. If you gitignored `data/` wholesale, it isn't, and the clone has no input.
- Nothing depends on a file that only exists in your working copy (an interim CSV you made by hand, a cell you ran once).
- The error for a missing token is readable.
- The numbers match your original run. If they don't, something is non-deterministic — an unseeded sample, or a dict ordering.

## Step 12.3 🧑 Then delete the test clone

It has your token in it.

```bash
rm -rf /c/temp/clean-clone-test
```

---

# Final checklist, mapped to the marks

Work through this before submitting. Each line is a thing a grader can look for.

### Analyze (20%)
- [ ] Every fault: detection method, row count, **which group it hits**, effect on the recommendation, risk rank
- [ ] Faults ranked by how much they move the answer, not listed flat
- [ ] Real extremes kept and *said* to be kept; no fix applied to anything unbroken
- [ ] Disguised nulls found: zero budget, zero revenue, empty-string dates, zero runtime, implausible money
- [ ] Full account of the list: received → analysed → removed with reasons, adding up exactly
- [ ] What the gap costs Kwame, stated

### Apply — acquisition (20%)
- [ ] Explicit dtype on load; uniqueness asserted; reconciliation number recorded
- [ ] Session with timeout on every call, retry with backoff, `Retry-After` honoured, 404 not retried
- [ ] Every raw response cached with a timestamp; reruns don't re-fetch; resumable
- [ ] 404s recorded as ledger statuses, no crash
- [ ] Ledger status counts reconcile to the file's data-row count

### Apply / Create — analysis (20%)
- [ ] One table per grain, grain in a comment
- [ ] Generated columns renamed once
- [ ] Every merge has `validate=` and `indicator=True`, with the report kept
- [ ] Row count asserted across every join; no film dropped, no revenue duplicated
- [ ] No row loops in the analysis stages; named aggregations throughout
- [ ] Stage timings, boundary stated, 500-title projection

### Evaluate — reasoning (20%)
- [ ] Every judgement call has a five-part record, risk-ranked
- [ ] Rejected alternatives are real and *costed* — you can state the KPI under each
- [ ] Both windows from one parameterised code path
- [ ] Flip check automatic and loud
- [ ] Selection bias in franchises named
- [ ] What survives at 500 titles, per stage

### Evaluate / Create — client (20%)
- [ ] Memo is one page, business language, no tool names
- [ ] Recommendation in the first line (or the flip, if it flips)
- [ ] 3 franchises + 5 standalones, each with why it made the cut
- [ ] Deal note: relative value, and the one number that drove it
- [ ] What you couldn't verify, and what it costs him
- [ ] As-of date present
- [ ] One improvement, justified in terms of Kwame's or Adjoa's problem
- [ ] Clean-clone run passes

---

# Commit cadence

Commit at the end of every phase, not at the end of the lab. The history is evidence of how you worked, and a phase-sized commit is reviewable:

```
Scaffold project: structure, secrets handling, config, requirements
Stage 1: id ledger with explicit dtype, classification and reconciliation
Stage 2: cached TMDb fetcher with retry, rate limit and 404 log
Stage 3: flatten nested responses to films, cast, crew, genres
Stage 4: validated joins with indicator reports
Stage 5: profiling function and ranked fault list
Stage 6: parameterised cleaning rules, flags not deletions, decision log
Stage 7: KPIs for both windows, flip check, shortlist
Stage 8: stage timings and 500-title projection
Stage 9: live spot-check across four slices, discrepancies classified
Stage 10: diagnosis, decision notes, client memo, improvement
```

Before each one: `git status`, and *read it*.

---

# What's still open

Answers I'd get from your instructor rather than decide alone — but every one has a default below it, so none of them blocks you:

1. **Is there a stated time budget for the analysis stages?** Default if not: 10 seconds, acquisition excluded, justified from Adjoa's live-meeting use.
2. **Are the four spot-check slices franchise/standalone × pre-2000/2000+?** Default: yes, that reading.
3. **What as-of date should the memo carry** — the fetch date or the 31 October review date? Default: the fetch date, stated as such, since that's what the numbers are true of.
4. **Does "one improvement beyond the brief" have to be code**, or does a written artefact count? Default: build it as code, since that's unambiguously within scope either way.

