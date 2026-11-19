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

from dotenv import load_dotenv

# src/streamvault/config.py -> src/streamvault -> src -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
    nobody. `use_popularity_as_performance` is the case in point: DR-13 decided
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
            "irreproducible from the same cache a month later. See DR-13 in "
            "reports/decision_log.md.\n"
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
