"""Shared test data: the facts a memo and a gate are built from.

pytest finds the fixtures and helpers in this file automatically. A test asks
for a fixture by naming it as an argument, for example
`def test_something(memo_settings):`.

These live here rather than in one test file because two stages read the same
facts: the checks stage decides whether to publish them, and the load stage
turns them into the memo. Duplicating the builders into both files would let
the two drift apart, and a gate tested against different facts from the memo it
guards is not testing the gate.
"""
from __future__ import annotations

import pandas as pd
import pytest

from pipeline.checks import gather
from pipeline.config import Settings
from pipeline.transform import GROUP_STRICT


@pytest.fixture
def memo_settings(tmp_path):
    return Settings(
        raw={
            "paths": {"processed_dir": "data/processed", "reports_dir": "reports"},
            "gate": {
                "enabled": True, "max_unaccounted_rows": 0,
                "min_films_for_a_recommendation": 40,
                "max_missing_money_share": 0.20,
                "block_if_spotcheck_moves": True,
            },
        },
        root=tmp_path,
    )


def flat(text: str) -> str:
    """Collapse whitespace before asserting on prose.

    The memo is hard-wrapped for reading, so a sentence routinely spans two
    lines. Asserting the raw string would make every test a test of where the
    line breaks fall, and it would fail the next time a sentence is reworded by
    a word. These assertions are about what the memo says.
    """
    return " ".join(text.split())


def window_table(franchise_median=5.5, standalone_median=5.0, franchise_n=87,
                 standalone_n=25, franchise_floor=3.9, standalone_floor=2.6,
                 franchise_iqr=4.4, standalone_iqr=11.7):
    return pd.DataFrame({
        GROUP_STRICT: ["franchise", "standalone"],
        "films": [franchise_n, standalone_n],
        "median_roi": [franchise_median, standalone_median],
        "floor_roi": [franchise_floor, standalone_floor],
        "iqr_roi": [franchise_iqr, standalone_iqr],
        "hit_rate_roi": [0.954, 0.80],
        "median_revenue": [618_638_999, 291_465_000],
        "median_rating": [7.5, 7.9],
    })


def flip_table(spread_flipped=True, headline_flipped=False):
    return pd.DataFrame({
        "measure": ["median_roi", "floor_roi", "hit_rate_roi", "iqr_roi"],
        "better_is": ["higher", "higher", "higher", "lower"],
        "winner_all_years": ["franchise"] * 4,
        "winner_modern": [
            "standalone" if headline_flipped else "franchise",
            "franchise", "franchise",
            "standalone" if spread_flipped else "franchise",
        ],
        "flipped": [headline_flipped, False, False, spread_flipped],
    })


def accounting_table():
    return pd.DataFrame({
        "status": ["fetched", "duplicate", "not_found_404", "invalid_id",
                   "duplicate_other_namespace"],
        "source_rows": [112, 6, 5, 3, 1],
        "reached_analysis": pd.array([112, 0, 0, 0, 0], dtype="Int64"),
    })


def ledger_table(data_rows=127):
    return pd.DataFrame({
        "status": ["header_row"] + ["fetched"] * data_rows,
        "tmdb_id": pd.array([None] + list(range(1, data_rows + 1)), dtype="Int64"),
    })


def make_facts(settings, **overrides):
    inputs = {
        "accounting": accounting_table(),
        "ledger": ledger_table(),
        "cleaned": pd.DataFrame({
            "tmdb_id": pd.array(range(1, 113), dtype="Int64"),
            "in_money_metrics": pd.array([True] * 112, dtype="boolean"),
        }),
        "windows": {"all_years": window_table(),
                    "modern": window_table(franchise_n=59, standalone_n=12,
                                           franchise_iqr=2.47,
                                           standalone_iqr=2.30)},
        "flips": flip_table(),
        "bundles": pd.DataFrame(),
        "gaps": pd.DataFrame({
            "collection_name": ["Star Wars Collection"],
            "entries_on_list": [6], "best_roi": [70.5], "median_roi": [13.4],
            "worst_roi": [5.4], "best_to_median": [5.26],
            "best_share_of_revenue": [0.236],
        }),
        "positions": pd.DataFrame({
            "position": ["first", "middle", "last"],
            "films": [22, 41, 22], "median_roi": [7.76, 5.41, 4.44],
        }),
        "talent": pd.DataFrame(),
        "shortlist": {
            "franchises": pd.DataFrame({
                "collection_name": ["Star Wars Collection", "Runner Up Collection"],
                "films_on_list": [6, 3], "median_roi": [13.4, 8.3],
                "floor_roi": [5.4, 6.1], "best_roi": [70.5, 20.6],
                "bundle_roi": [10.8, 9.8], "median_rating": [7.69, 7.78],
                "first_year": [1977, 1985], "last_year": [2019, 1990],
                "selected": [True, False],
            }),
            "standalones": pd.DataFrame({
                "tmdb_id": pd.array([578, 429], dtype="Int64"),
                "title": ["Jaws", "The Good, the Bad and the Ugly"],
                "release_year": pd.array([1975, 1966], dtype="Int64"),
                "roi": [67.2, 32.4], "revenue": [470_653_000, 38_900_000],
                "budget": [7_000_000, 1_200_000],
                "vote_average": [7.7, 8.5], "vote_count": pd.array([12000, 8000],
                                                                   dtype="Int64"),
                "rating_reliable": [True, True],
                "franchise_status": ["lone_collection_member", "standalone"],
                "selected": [True, True],
            }),
        },
        "fetch_log": pd.DataFrame({
            "fetched_at": ["2026-11-19T13:00:00+00:00"] * 112,
        }),
        "spotcheck_movement": {"moved": False, "note": "nothing to substitute"},
        "spotcheck_films": 15,
        "eras": pd.DataFrame(),
    }
    inputs.update(overrides)
    return gather(settings, **inputs)
