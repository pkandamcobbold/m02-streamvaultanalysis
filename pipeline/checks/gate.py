"""The release gate: the one improvement beyond the brief (ADR-015).

Four blunt checks run before the memo is written: every source row accounted
for, enough films to compare groups, money data complete enough to decide on,
and a live re-check that does not change the answer. If any fails, no memo and
no shortlist are produced — the run stops and prints what failed, naming the
setting that overrides it.

Adjoa reruns this quarterly and sometimes live in the meeting. Everything else
in this project protects the analysis from being wrong; this protects her from
the analysis being wrong *and looking fine*.

Deliberately a small number of blunt checks. A gate with twenty conditions is a
gate nobody trusts: the first time it blocks a run for something cosmetic,
somebody adds a flag to skip it, and then it protects nothing.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.config import share
from pipeline.transform import GROUP_STRICT

# `status` is the source of truth and `passed` is a convenience derived from
# it, because a check can be neither passed nor failed: it can have been
# skipped. Only a `fail` blocks publication — a `not_checked` is reported and
# carried into the memo, so an unverified claim is never presented as a
# verified one.
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_NOT_CHECKED = "not_checked"

GATE_COLUMNS = ["check", "status", "passed", "detail"]


class GateFailed(RuntimeError):
    """Raised instead of publishing a memo nobody should act on."""


# ===========================================================================
# The release gate — the one improvement beyond the brief (ADR-015)
# (was src/streamvault/memo.py)
# ===========================================================================

def gate(settings: Any, facts: dict[str, Any]) -> pd.DataFrame:
    """Decide whether these results may be published. Returns one row per check.

    Deliberately a small number of blunt checks. A gate with twenty conditions
    is a gate nobody trusts: the first time it blocks a run for something
    cosmetic, somebody adds a flag to skip it, and then it protects nothing.
    Every check here is one that, if it failed, would make the memo actively
    misleading rather than merely imperfect.
    """
    config = settings["gate"]
    rows: list[dict[str, Any]] = []

    unaccounted = int(facts.get("unaccounted_rows", 0))
    limit = int(config["max_unaccounted_rows"])
    rows.append({
        "check": "every source row accounted for",
        "status": STATUS_PASS if unaccounted <= limit else STATUS_FAIL,
        "passed": unaccounted <= limit,
        "detail": f"{unaccounted} row(s) unaccounted for, limit {limit}. The memo "
                  "quotes a count of what was analysed and what was dropped; if "
                  "that does not reconcile, the sentence is false.",
    })

    films = int(facts.get("films_analysed", 0))
    minimum = int(config["min_films_for_a_recommendation"])
    rows.append({
        "check": "enough films to compare groups",
        "status": STATUS_PASS if films >= minimum else STATUS_FAIL,
        "passed": films >= minimum,
        "detail": f"{films} films analysed, minimum {minimum}. Below this the two "
                  "groups are too thin to rank; the honest output is a description, "
                  "not a recommendation.",
    })

    missing = float(facts.get("missing_money_share", 0.0))
    max_missing = float(config["max_missing_money_share"])
    rows.append({
        "check": "money data complete enough to decide on",
        "status": STATUS_PASS if missing <= max_missing else STATUS_FAIL,
        "passed": missing <= max_missing,
        "detail": f"{share(missing)} of films have no usable budget or box office, "
                  f"limit {share(max_missing)}. Above that, a ranking by return is "
                  "a ranking of whichever films happened to have figures.",
    })

    if bool(config["block_if_spotcheck_moves"]):
        # Three states, not two. `--no-spotcheck` leaves `spotcheck_moved` as
        # None, and the old `bool(facts.get(..., False))` turned that into
        # False, so the gate reported this check as *passed* when it had never
        # run. It did not crash, which was worse: the run log recorded
        # gate_passed=true on the strength of a check nobody performed.
        moved = facts.get("spotcheck_moved")
        if moved is None:
            status = STATUS_NOT_CHECKED
            detail = ("the live re-check did not run (--no-spotcheck), so whether a "
                      "difference would move the recommendation is unverified. Not a "
                      "failure, and not a pass either")
        elif moved:
            status = STATUS_FAIL
            detail = ("the live re-check moved the recommendation; a human must look "
                      "before this is published")
        else:
            status = STATUS_PASS
            detail = "the live re-check leaves the recommendation unchanged"
        rows.append({
            "check": "live re-check does not change the answer",
            "status": status,
            "passed": status == STATUS_PASS,
            "detail": detail,
        })

    return pd.DataFrame(rows, columns=GATE_COLUMNS)


def enforce(gate_results: pd.DataFrame, settings: Any) -> None:
    """Raise if any check failed and the gate is enabled."""
    if not bool(settings["gate"]["enabled"]):
        return
    # Blocks on `fail` only. Filtering on `~passed` would also block a
    # `not_checked`, which would turn "we could not verify this" into "this
    # failed" and make --no-spotcheck unusable.
    failed = gate_results.loc[gate_results["status"] == STATUS_FAIL]
    if failed.empty:
        return
    lines = ["The memo was not written, because these checks failed:", ""]
    for row in failed.itertuples(index=False):
        lines.append(f"  * {row.check}")
        lines.append(f"    {row.detail}")
    lines += [
        "",
        "Nothing is wrong with your computer. The analysis produced results that",
        "should not be put in front of a board without someone looking first.",
        "Read reports/data_diagnosis.md, then either fix the input or, if you have",
        "decided the run is sound anyway, set gate.enabled = false in",
        "config/settings.toml and run again — and say in the meeting that you did.",
    ]
    raise GateFailed("\n".join(lines))


def gather(
    settings: Any,
    accounting: pd.DataFrame,
    ledger: pd.DataFrame,
    cleaned: pd.DataFrame,
    windows: dict[str, pd.DataFrame],
    flips: pd.DataFrame,
    bundles: pd.DataFrame,
    gaps: pd.DataFrame,
    positions: pd.DataFrame,
    talent: pd.DataFrame,
    shortlist: dict[str, pd.DataFrame],
    fetch_log: pd.DataFrame,
    spotcheck_movement: dict[str, Any] | None,
    spotcheck_films: int,
    eras: pd.DataFrame,
    talent_leads: pd.DataFrame | None = None,
    positions_modern: pd.DataFrame | None = None,
    positions_paired: pd.DataFrame | None = None,
    uncertainty: pd.DataFrame | None = None,
    uncertainty_by_franchise: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Everything the memo quotes, in one dictionary, computed once."""
    source_rows = int(accounting["source_rows"].sum()) if not accounting.empty else 0
    analysed = int(accounting.loc[accounting["status"] == "fetched",
                                  "reached_analysis"].sum()) \
        if not accounting.empty else 0

    # A genuine cross-check between two tables built independently: the ledger
    # has one row per line of the source file, and the accounting table is
    # grouped from it at stage 4. Comparing the accounting total against its
    # own total would be a tautology and would pass whatever went wrong.
    ledger_data_rows = int(
        (ledger["status"] != "header_row").sum()
    ) if "status" in ledger.columns else source_rows
    unaccounted = abs(ledger_data_rows - source_rows)

    dates = fetch_log["fetched_at"].dropna().astype(str).str.slice(0, 10) \
        if "fetched_at" in fetch_log.columns else pd.Series(dtype=str)

    all_years = windows.get("all_years", pd.DataFrame())
    modern = windows.get("modern", pd.DataFrame())

    def group_row(table: pd.DataFrame, group: str) -> pd.Series | None:
        if table.empty or GROUP_STRICT not in table.columns:
            return None
        rows = table.loc[table[GROUP_STRICT] == group]
        return rows.iloc[0] if len(rows) else None

    in_money = cleaned["in_money_metrics"].fillna(False) \
        if "in_money_metrics" in cleaned.columns else pd.Series(dtype=bool)

    return {
        "source_rows": source_rows,
        "films_analysed": analysed,
        "unaccounted_rows": unaccounted,
        "ledger_data_rows": ledger_data_rows,
        "missing_money_share": float(1 - in_money.mean()) if len(in_money) else 0.0,
        "accounting": accounting,
        "as_of_first": dates.min() if len(dates) else None,
        "as_of_last": dates.max() if len(dates) else None,
        "all_years": all_years,
        "modern": modern,
        "franchise_all": group_row(all_years, "franchise"),
        "standalone_all": group_row(all_years, "standalone"),
        "franchise_modern": group_row(modern, "franchise"),
        "standalone_modern": group_row(modern, "standalone"),
        "flips": flips,
        "bundles": bundles,
        "gaps": gaps,
        "positions": positions,
        "talent": talent,
        "talent_leads": talent_leads,
        "positions_modern": positions_modern,
        "positions_paired": positions_paired,
        "uncertainty": uncertainty,
        "uncertainty_by_franchise": uncertainty_by_franchise,
        "shortlist": shortlist,
        "eras": eras,
        "spotcheck_moved": bool(spotcheck_movement["moved"])
        if spotcheck_movement else False,
        "spotcheck_films": int(spotcheck_films),
    }
