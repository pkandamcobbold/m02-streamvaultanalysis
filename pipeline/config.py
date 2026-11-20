"""Configuration: settings.toml plus the secret from the environment.

Loaded once, passed down. No other module reads os.environ or opens the
settings file on its own, and nothing anywhere prints the token.

TOML is read with the standard library's tomllib (Python 3.11+), so the
config format costs no dependency and nothing to build. That matters more
than it sounds: the YAML library has no wheel for Python 3.15 and cannot
compile from source, which would have made a clean-clone install fail
outright on the machine this was developed on.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

# pipeline/config.py -> pipeline -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS = PROJECT_ROOT / "config" / "settings.toml"


class MissingTokenError(RuntimeError):
    """Raised with instructions, not a traceback, when the token is absent."""


@dataclass(frozen=True)
class Settings:
    """Parsed settings plus the project root, so paths never depend on cwd."""

    raw: dict[str, Any]
    root: Path

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def path(self, relative: str) -> Path:
        """Resolve a settings path against the project root, never the cwd.

        This is what makes "runs from a clean clone, no manual edits" true:
        no absolute paths anywhere, and the pipeline behaves the same whatever
        directory it is launched from.
        """
        return self.root / relative

    @property
    def windows(self) -> dict[str, dict[str, Any]]:
        """The time windows, as {key: {label, min_year}}.

        min_year is absent from the all-years window because TOML has no null.
        An absent key reads as None, meaning no lower bound — deliberately not
        0, which would be a real boundary and would silently exclude any film
        whose release date could not be parsed into a year.
        """
        return {
            name: {"label": body["label"], "min_year": body.get("min_year")}
            for name, body in self.raw["windows"].items()
        }


def validate_settings(settings: "Settings") -> None:
    """Refuse a setting that cannot do what it says.

    A settings key implies a switch: set it, and behaviour changes. Several
    keys in this file were inert until an audit found them, which is worse than
    their not existing — a decision record credited one of them with making a
    judgement reversible when flipping it did nothing.

    So anything not implemented fails loudly here rather than being read by
    nobody. `use_popularity_as_performance` is the case in point: M8 decided
    popularity must never enter a performance metric, because it is recomputed
    daily and recency-biased, so there is no code path for `true` and setting it
    is an error rather than a request.
    """
    profile = settings.get("profile") or {}
    if bool(profile.get("use_popularity_as_performance", False)):
        raise ValueError(
            "profile.use_popularity_as_performance = true is not implemented, "
            "deliberately.\n"
            "TMDb's popularity score is recomputed daily and is heavily biased "
            "toward recent films (Avengers: Endgame 85.7 against a 1966 classic "
            "at 0.5), so using it would rank against the back catalog this "
            "project exists to evaluate, and would make the analysis "
            "irreproducible from the same cache a month later. See M8 in "
            "decisions/.\n"
            "Set it back to false. If you genuinely want a demand signal, it "
            "needs a source whose values do not move under the analysis."
        )

    performance = settings.get("performance") or {}
    definition = performance.get("hit_definition")
    allowed = {"roi", "above_median", "top_quartile"}
    if definition is not None and definition not in allowed:
        raise ValueError(
            f"performance.hit_definition is {definition!r}; expected one of "
            f"{sorted(allowed)}."
        )


def load_settings(path: Path | None = None) -> Settings:
    settings_path = path or DEFAULT_SETTINGS
    if not settings_path.exists():
        raise FileNotFoundError(
            f"Settings file not found at {settings_path}.\n"
            "It is committed to the repo, so this usually means the file was "
            "moved or renamed. Restore it with: git checkout config/settings.toml"
        )
    with settings_path.open("rb") as handle:   # tomllib requires binary mode
        raw = tomllib.load(handle)
    settings = Settings(raw=raw, root=PROJECT_ROOT)
    validate_settings(settings)
    return settings


def load_token() -> str:
    """Read the TMDb v4 bearer token from .env or the environment.

    Fails with an instruction the reader can act on, not a KeyError.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.getenv("TMDB_BEARER_TOKEN", "").strip()

    if not token or token.startswith("paste_your"):
        raise MissingTokenError(
            "No TMDb token found.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Get your token: themoviedb.org -> Settings -> API ->\n"
            "     'API Read Access Token (v4 auth)' (the long value starting eyJ)\n"
            "  3. Paste it after TMDB_BEARER_TOKEN= in .env\n"
            "See the README section 'Setup', step 3."
        )
    return token

# ---------------------------------------------------------------------------
# Constants shared across stages, so no stage owns another stage's vocabulary
# ---------------------------------------------------------------------------

# Ledger statuses whose row is the one that put a film into the analysis. A
# duplicate row shares its id with the row that was kept, so id membership
# alone is not the question: testing "is this id in the analysis?" would count
# a duplicate as having reached it, and the accounting would claim 113 of 127
# rows became films when only 112 films exist. Lives here because both the
# transform stage (accounting) and the validate stage (the ledger's money
# column) need one answer to "which row owns the film?". See ADR-004.
ANALYSED_STATUSES = frozenset({"fetched"})

# The durable per-stage timing artefact: written by run_pipeline.py, read by
# the checks stage to compute the time budget and the 500-title projection.
# A figure quoted in a report and held nowhere else is a memory, not a
# measurement. See ADR-005.
TIMING_COLUMNS = [
    "run_at", "stage", "seconds", "api_calls", "cache_hits", "rows", "note",
]

TIMING_DTYPES = {
    "run_at": "str",
    "stage": "str",
    "seconds": "float",
    "api_calls": "Int64",
    "cache_hits": "Int64",
    "rows": "Int64",
    "note": "str",
}


# ---------------------------------------------------------------------------
# Plain language: how a figure is rendered for a human
# ---------------------------------------------------------------------------
# Shared because two stages render figures for a person to read: the release
# gate's failure messages and the memo. Keeping them here means the checks
# stage does not have to import the load stage to say "0%".

def money(value: Any) -> str:
    """$1,234,567 -> "$1.2m". The memo is read aloud, not audited."""
    if value is None or pd.isna(value):
        return "no figure"
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}bn"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.0f}m"
    return f"${value:,.0f}"


def multiple(value: Any) -> str:
    """5.526 -> "5.5 times". ROI never appears as an acronym."""
    if value is None or pd.isna(value):
        return "no figure"
    return f"{float(value):.1f} times"


def share(value: Any) -> str:
    if value is None or pd.isna(value):
        return "no figure"
    return f"{100 * float(value):.0f}%"
