"""Tests for pipeline/config.py: the settings loader and the plain-language helpers.

Two things are pinned here. **A settings key must change behaviour or refuse to
load** (ADR-016): five keys were once declared and read by nobody, and two of
them were cited in decision records as the mechanism that made a judgement
reversible. And the figures a human reads are rendered in one place, because
the gate's failure messages and the memo must not disagree about what "20%"
looks like.
"""
from __future__ import annotations

import pytest

from pipeline.config import (
    Settings,
    load_settings,
    money,
    multiple,
    share,
    validate_settings,
)


def test_money_is_readable_aloud():
    assert money(470_653_000) == "$471m"
    assert money(2_942_649_778) == "$2.94bn"
    assert money(None) == "no figure"


def test_returns_are_never_written_as_an_acronym():
    assert multiple(5.526) == "5.5 times"
    assert share(0.954) == "95%"


def test_an_unimplemented_switch_fails_loudly_rather_than_being_ignored(tmp_path):
    """A settings key implies a switch. One nothing reads is worse than none,
    because a decision record credits it with making a judgement reversible.
    """
    from pipeline.config import Settings, validate_settings

    ok = Settings(raw={"profile": {"use_popularity_as_performance": False}},
                  root=tmp_path)
    validate_settings(ok)                      # must not raise

    bad = Settings(raw={"profile": {"use_popularity_as_performance": True}},
                   root=tmp_path)
    with pytest.raises(ValueError, match="not implemented"):
        validate_settings(bad)


def test_the_refusal_explains_why_and_points_at_the_decision(tmp_path):
    from pipeline.config import Settings, validate_settings

    bad = Settings(raw={"profile": {"use_popularity_as_performance": True}},
                   root=tmp_path)
    try:
        validate_settings(bad)
    except ValueError as error:
        message = str(error)
    assert "recomputed daily" in message
    assert "M8" in message
    assert "Set it back to false" in message


def test_a_bad_hit_definition_is_rejected_at_load(tmp_path):
    from pipeline.config import Settings, validate_settings

    bad = Settings(raw={"performance": {"hit_definition": "vibes"}}, root=tmp_path)
    with pytest.raises(ValueError, match="hit_definition"):
        validate_settings(bad)


def test_the_real_settings_file_validates():
    """The shipped configuration must pass its own validator."""
    from pipeline.config import load_settings

    load_settings()                            # raises if anything is inert-but-on
