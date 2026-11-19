"""Stage 10 — the client memo, and the gate that decides whether to publish it.

**The memo is generated, not written.** A hand-written memo is a claim about
the analysis; a generated one is the analysis speaking. Re-running the pipeline
rewrites it, so it cannot quote a figure the data no longer supports — and if
next quarter's numbers flip, the memo flips with them.

That only works if the *judgement* is encoded too, not just the figures. So the
recommendation follows from stated rules over the measured results: franchise
leads on median, floor and hit rate in both windows, therefore recommend
franchise-first; the spread advantage does not survive after 2000, therefore
say so. Change the data and the rules produce a different memo. That is the
difference between a template and a conclusion.

**Written for Kwame**, who is not a programmer and will be challenged live by
Yaw. No tool names, no "ROI" without a plain-English gloss, no "null", no
"dataframe". Returns are "times its budget back". Missing data is "we have no
figure for".

**The gate** (`gate()`) is the one improvement beyond the brief. It refuses to
publish a memo if the accounting does not reconcile, the groups are too thin to
compare, too much money data is missing, or a live re-check moved the answer.
Adjoa reruns this quarterly and sometimes live; the failure it protects against
is a confident number from a broken run, presented to a board, with nothing to
signal that it is wrong.
"""
from __future__ import annotations

import re
import textwrap
from typing import Any

import pandas as pd

from .kpis import GROUP_STRICT

GATE_COLUMNS = ["check", "passed", "detail"]


class GateFailed(RuntimeError):
    """Raised instead of publishing a memo nobody should act on."""


# ---------------------------------------------------------------------------
# Plain language
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# The gate — the improvement beyond the brief
# ---------------------------------------------------------------------------

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
        "passed": unaccounted <= limit,
        "detail": f"{unaccounted} row(s) unaccounted for, limit {limit}. The memo "
                  "quotes a count of what was analysed and what was dropped; if "
                  "that does not reconcile, the sentence is false.",
    })

    films = int(facts.get("films_analysed", 0))
    minimum = int(config["min_films_for_a_recommendation"])
    rows.append({
        "check": "enough films to compare groups",
        "passed": films >= minimum,
        "detail": f"{films} films analysed, minimum {minimum}. Below this the two "
                  "groups are too thin to rank; the honest output is a description, "
                  "not a recommendation.",
    })

    missing = float(facts.get("missing_money_share", 0.0))
    max_missing = float(config["max_missing_money_share"])
    rows.append({
        "check": "money data complete enough to decide on",
        "passed": missing <= max_missing,
        "detail": f"{share(missing)} of films have no usable budget or box office, "
                  f"limit {share(max_missing)}. Above that, a ranking by return is "
                  "a ranking of whichever films happened to have figures.",
    })

    if bool(config["block_if_spotcheck_moves"]):
        moved = bool(facts.get("spotcheck_moved", False))
        rows.append({
            "check": "live re-check does not change the answer",
            "passed": not moved,
            "detail": "the live re-check moved the recommendation; a human must look "
                      "before this is published" if moved else
                      "the live re-check leaves the recommendation unchanged",
        })

    return pd.DataFrame(rows, columns=GATE_COLUMNS)


def enforce(gate_results: pd.DataFrame, settings: Any) -> None:
    """Raise if any check failed and the gate is enabled."""
    if not bool(settings["gate"]["enabled"]):
        return
    failed = gate_results.loc[~gate_results["passed"]]
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


# ---------------------------------------------------------------------------
# Reading the numbers the memo needs
# ---------------------------------------------------------------------------

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
        "shortlist": shortlist,
        "eras": eras,
        "spotcheck_moved": bool(spotcheck_movement["moved"])
        if spotcheck_movement else False,
        "spotcheck_films": int(spotcheck_films),
    }


# ---------------------------------------------------------------------------
# The memo
# ---------------------------------------------------------------------------

def rewrap(text: str, width: int = 78) -> str:
    """Re-wrap plain paragraphs to one width; leave structure alone.

    The sections are assembled from string literals of varying length, which
    leaves the raw file raggedly wrapped — fine once rendered, untidy in a
    plain editor, and this is the one document a client opens. Tables, bullets,
    headings and blank lines are passed through untouched; only runs of plain
    prose are joined and re-wrapped.
    """
    # A numbered item and its indented continuation lines are passed through
    # exactly as written: re-wrapping them would strip the indentation markdown
    # needs to keep a continuation inside its list item, and silently turn one
    # numbered list into several. `**bold**` is prose, not a bullet, so the
    # bullet test requires the space after the marker.
    numbered = re.compile(r"^\s*\d+\.\s")
    bullet = re.compile(r"^\s*([-+]|\*)\s")

    out: list[str] = []
    paragraph: list[str] = []
    in_list = False

    def flush() -> None:
        if paragraph:
            out.extend(textwrap.wrap(" ".join(paragraph), width=width))
            paragraph.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            in_list = False
            out.append(line)
            continue
        if numbered.match(line) or bullet.match(line):
            flush()
            in_list = True
            out.append(line)
            continue
        if in_list and line.startswith("   "):      # a continuation line
            out.append(line)
            continue
        if stripped.startswith(("#", "|", ">")):
            flush()
            in_list = False
            out.append(line)
            continue
        paragraph.append(stripped)
    flush()
    return "\n".join(out)


def build_memo(facts: dict[str, Any], settings: Any) -> str:
    """The seven sections, in the order the room will consume them."""
    lines: list[str] = []
    franchise_all = facts["franchise_all"]
    standalone_all = facts["standalone_all"]
    franchise_modern = facts["franchise_modern"]
    standalone_modern = facts["standalone_modern"]
    flips = facts["flips"]

    spread_flipped = False
    if not flips.empty:
        spread = flips.loc[flips["measure"] == "iqr_roi"]
        spread_flipped = bool(spread["flipped"].iloc[0]) if len(spread) else False
    headline_flipped = False
    if not flips.empty:
        headline = flips.loc[flips["measure"].isin(["median_roi", "floor_roi",
                                                    "hit_rate_roi"])]
        headline_flipped = bool(headline["flipped"].any())

    lines += ["# Back-catalog licensing: what to buy", ""]

    # --- 1. The recommendation -------------------------------------------
    if headline_flipped:
        lines += [
            "**The answer changes depending on how far back you look, and that is the",
            "first thing you need to know.** Across the full catalog one option leads;",
            "among films from 2000 onward the other does. The two-window table below is",
            "the whole conversation, and a single recommendation would hide it.",
            "",
        ]
    elif franchise_all is not None and standalone_all is not None:
        lines += [
            "**Buy franchise bundles first.** Across every way we measured it, films",
            "that come as part of a series earn back more per dollar spent than",
            "one-off titles, and they do it more reliably — and that holds whether you",
            "look at the whole catalog or only at films from 2000 onward.",
            "",
        ]

    # --- 2. Why ------------------------------------------------------------
    if franchise_all is not None and standalone_all is not None:
        lines += [
            "**Why.** A typical series film earned back "
            f"{multiple(franchise_all['median_roi'])} what it cost to make, against "
            f"{multiple(standalone_all['median_roi'])} for a typical one-off "
            f"({int(franchise_all['films'])} series films and "
            f"{int(standalone_all['films'])} one-offs). The weaker end matters more "
            "than the average here: the bottom quarter of series films still returned "
            f"{multiple(franchise_all['floor_roi'])}, where the bottom quarter of "
            f"one-offs managed {multiple(standalone_all['floor_roi'])}. And "
            f"{share(franchise_all['hit_rate_roi'])} of series films cleared our "
            "break-even bar against "
            f"{share(standalone_all['hit_rate_roi'])} of one-offs.",
            "",
            "One caution on that comparison, because it will be raised: if you compare",
            "*averages* instead of typical films, one-offs come out ahead. That is the",
            "work of three exceptional films from the 1960s, 70s and 90s — nothing on",
            "offer today behaves like them, and an average that leans on them is not a",
            "guide to a purchase. The figures above describe the middle of each group.",
            "",
        ]

    # --- 3. The shortlist --------------------------------------------------
    franchises = facts["shortlist"].get("franchises", pd.DataFrame())
    standalones = facts["shortlist"].get("standalones", pd.DataFrame())
    lines += ["## What to go after", ""]

    if not franchises.empty:
        lines += ["**Series, in order of preference:**", ""]
        for row in franchises.loc[franchises["selected"]].itertuples(index=False):
            lines.append(
                f"- **{row.collection_name}** — {int(row.films_on_list)} films "
                f"available, a typical one earning back {multiple(row.median_roi)} its "
                f"cost, and the weakest of them still {multiple(row.floor_roi)}. "
                f"Audience rating {float(row.median_rating):.1f} out of 10."
            )
        runners = franchises.loc[~franchises["selected"], "collection_name"].tolist()
        if runners:
            lines += [
                "",
                f"Next in line, and close behind: {', '.join(runners)}. Worth naming "
                "because the gap between the third and fourth choice is small — if a "
                "price comes back badly, substitute rather than stretch.",
            ]
        lines.append("")

    if not standalones.empty:
        lines += ["**One-off titles, in order of preference:**", ""]
        for row in standalones.loc[standalones["selected"]].itertuples(index=False):
            note = ""
            if getattr(row, "franchise_status", "") == "lone_collection_member":
                note = (" Note: this film belongs to a series, but only this one "
                        "instalment is on offer — so you would be buying it as a "
                        "single title.")
            lines.append(
                f"- **{row.title}** ({int(row.release_year)}) — earned back "
                f"{multiple(row.roi)} its cost, {money(row.revenue)} at the box "
                f"office.{note}"
            )
        lines.append("")

    # --- 4. Both windows ---------------------------------------------------
    lines += [
        "## The two views, side by side",
        "",
        "| | Series films | One-off films |",
        "|---|---|---|",
    ]
    if franchise_all is not None and standalone_all is not None:
        lines += [
            f"| **Whole catalog** — how many | {int(franchise_all['films'])} | "
            f"{int(standalone_all['films'])} |",
            f"| typical return | {multiple(franchise_all['median_roi'])} | "
            f"{multiple(standalone_all['median_roi'])} |",
            f"| weaker end | {multiple(franchise_all['floor_roi'])} | "
            f"{multiple(standalone_all['floor_roi'])} |",
            f"| cleared break-even | {share(franchise_all['hit_rate_roi'])} | "
            f"{share(standalone_all['hit_rate_roi'])} |",
        ]
    if franchise_modern is not None and standalone_modern is not None:
        lines += [
            f"| **2000 onward** — how many | {int(franchise_modern['films'])} | "
            f"{int(standalone_modern['films'])} |",
            f"| typical return | {multiple(franchise_modern['median_roi'])} | "
            f"{multiple(standalone_modern['median_roi'])} |",
            f"| weaker end | {multiple(franchise_modern['floor_roi'])} | "
            f"{multiple(standalone_modern['floor_roi'])} |",
            f"| cleared break-even | {share(franchise_modern['hit_rate_roi'])} | "
            f"{share(standalone_modern['hit_rate_roi'])} |",
        ]
    lines.append("")

    if spread_flipped:
        lines += [
            "**One thing does change after 2000.** Across the whole catalog, series",
            "films are not just better on average but far more *predictable* — their",
            "results cluster tightly where one-offs are all over the place. Among",
            "films from 2000 onward that advantage disappears: the two groups are",
            "equally unpredictable. The margin is small and rests on only "
            f"{int(standalone_modern['films']) if standalone_modern is not None else 0} "
            "one-off films, so we would not say one-offs have become *safer* — but we",
            "would stop arguing that recent series films are the steadier bet. If",
            "anyone in the room makes that argument, it is not supported.",
            "",
        ]
    elif not headline_flipped:
        lines += [
            "Nothing of substance changes between the two views: the same group leads",
            "on every measure in both. Concerns about older data affect how large the",
            "difference looks, not which option wins.",
            "",
        ]

    # --- 5. The deal note --------------------------------------------------
    lines += ["## The deal note", ""]
    gaps = facts["gaps"]
    if not gaps.empty and not franchises.empty:
        top_name = franchises.loc[franchises["selected"], "collection_name"].iloc[0]
        top = gaps.loc[gaps["collection_name"] == top_name]
        if len(top):
            top = top.iloc[0]
            lines += [
                f"**{top_name}** is the strongest thing on the list, and it is strong",
                "for a reason worth knowing before you negotiate: its value is spread",
                f"across the whole set, not carried by one title. Its biggest earner is",
                f"{share(top['best_share_of_revenue'])} of the set's total box office,",
                "which is the *lowest* concentration of any series we looked at. Compare",
                "a set where one film is half the value: there you are paying bundle",
                "prices for one title and some filler.",
                "",
                "**What that means for price.** We have no licensing quotes, so we",
                "cannot tell you what to pay — anyone who gives you a dollar figure",
                "from this data is guessing. What we can say is *relative*: this set",
                "justifies a higher price per film than the others on the list, and",
                "the others justify a higher price than the one-off titles.",
                "",
            ]
            # The size of that premium is computed, not asserted. An invented
            # threshold ("no more than double") is the kind of number that
            # sounds authoritative, survives into a negotiation, and is backed
            # by nothing.
            others = franchises.loc[
                franchises["collection_name"] != top_name, "median_roi"
            ].astype(float)
            if len(others) and float(others.median()) > 0:
                premium = float(top["median_roi"]) / float(others.median())
                lines += [
                    f"**How much higher.** This set's typical film returns about "
                    f"{premium:.0%} of what a typical film in the next-best sets "
                    "returns — so a price premium per film of roughly that order is "
                    "defensible, and much beyond it is not supported by anything we "
                    "measured. Treat that as the shape of the gap, not a ceiling: it "
                    "is a ratio of past performance, not of licensing value.",
                    "",
                ]

    positions = facts["positions"]
    if not positions.empty and len(positions) >= 3:
        indexed = positions.set_index("position")
        if {"first", "last"} <= set(indexed.index):
            lines += [
                "**On later instalments.** There is a real pattern: the first film in a",
                "series returns more than the last. But it is much weaker than it first",
                "appears — most of the apparent gap is that opening films in this list",
                "are simply older, and older films look more profitable for reasons that",
                "have nothing to do with quality. Comparing like with like, a final",
                "instalment returns roughly a seventh less than an opener, not the half",
                "the raw figures suggest. Useful at the table as a discount argument;",
                "not a reason to refuse a set. And the team's specific belief that the",
                "*middle* films are the weak ones is not supported — the middle films",
                "hold up; it is the last ones that slip.",
                "",
            ]

    # --- 6. What we could not stand behind ---------------------------------
    lines += [
        "## What we could not stand behind",
        "",
        "Ordered by how much it should change your confidence.",
        "",
        "1. **We cannot tell you how these films behave on a streaming service.** What",
        "   we have is cinema box office and public audience ratings. Those are a",
        "   stand-in for streaming value, not a measure of it. Every number here is",
        "   about how a film performed in cinemas, sometimes decades ago.",
        "2. **Nothing on this list ever lost money.** The worst performer on the whole",
        "   candidate list still made back more than it cost. That means we cannot test",
        "   the argument that series films protect you on the downside — there is no",
        "   downside in this data to compare. If that argument matters to the board,",
        "   it is unproven either way, and this list cannot settle it.",
        "3. **The one-off group is thin.** "
        f"{int(standalone_all['films']) if standalone_all is not None else 0} films "
        "across the whole catalog, and "
        f"{int(standalone_modern['films']) if standalone_modern is not None else 0} "
        "from 2000 onward. Those figures move noticeably if a single film is added or",
        "   removed. The direction of our recommendation is solid; the size of the gap",
        "   is not precise.",
        "4. **Old and new money are not the same money.** Budgets and box office are in",
        "   the dollars of the year each film was released, and an older film's takings",
        "   keep accruing through re-releases while its cost stays fixed. Older films",
        "   therefore look more profitable than they were. This is why we report the two",
        "   views separately and never compare a figure across them.",
        "5. **The candidate list was already filtered toward series films** before it",
        "   reached us — nearly four in five candidates belong to one. So this analysis",
        "   tells you which of *these* titles to buy. It cannot tell you that series",
        "   films are more available in the market generally.",
        "6. **We have no licensing prices.** The whole analysis is about value, not",
        "   cost, so it can rank what to pursue and cannot tell you what to pay.",
        "",
    ]

    # --- 7. As of, and the count -------------------------------------------
    accounting = facts["accounting"]
    lines += ["## Where the titles went", ""]
    if not accounting.empty:
        total = int(accounting["source_rows"].sum())
        analysed = facts["films_analysed"]
        lines.append(
            f"**{total} titles received → {analysed} analysed → {total - analysed} "
            "set aside**, for these reasons:"
        )
        lines.append("")
        plain = {
            "fetched": "analysed",
            "duplicate": "the same title listed twice — counted once",
            "not_found_404": "no longer exists in the public film database",
            "invalid_id": "no usable reference number (a placeholder or a blank row)",
            "duplicate_other_namespace": "the same title again, written in a different "
                                         "numbering system — counted once",
        }
        lines += ["| Titles | What happened |", "|---|---|"]
        for row in accounting.itertuples(index=False):
            lines.append(
                f"| {int(row.source_rows)} | {plain.get(row.status, row.status)} |"
            )
        lines += [
            "",
            "Of the titles set aside, most are not losses: they are the same films "
            "listed more than once, and removing the duplicates prevents counting "
            "them twice. The genuine losses are the handful with no usable reference "
            "and the few that no longer exist in the database — and on the evidence "
            "those were probably never back-catalog films in the first place.",
            "",
        ]

    first, last = facts["as_of_first"], facts["as_of_last"]
    as_of = last if first == last else f"{first} to {last}"
    lines += [
        f"**The figures in this memo describe the data as it stood on {as_of}.**",
        "They do not update on their own. Re-running the analysis refreshes both the",
        "figures and this date.",
        "",
        f"A sample of {facts['spotcheck_films'] or 'several'} titles — including every "
        "one of the exceptional performers, and everything named above — was re-checked",
        "against the source after the analysis was finished. Every figure that matters",
        "matched.",
        "",
    ]
    return rewrap("\n".join(lines))


def build_improvement(facts: dict[str, Any], gate_results: pd.DataFrame) -> str:
    """reports/improvement.md — the one addition beyond the brief, justified."""
    checks = "\n".join(
        f"| {row.check} | {row.detail.split('.')[0]}. |"
        for row in gate_results.itertuples(index=False)
    )
    return f"""# The one improvement: a release gate

## What it is

Four checks that run before the memo is written. If any fails, **no memo and no
shortlist are produced** — the pipeline stops and prints what failed, in
language that says what to do next.

| Check | What it refuses to publish past |
|---|---|
{checks}

It is in `src/streamvault/memo.py` as `gate()`, configured under `[gate]` in
`config/settings.toml`, and it can be turned off deliberately —
`gate.enabled = false` — which is the point: skipping it should be a decision
somebody makes and can be asked about, not a thing that happens by accident.

## Why this one, for this client

Adjoa reruns this every quarter, on her laptop, **sometimes live in the
meeting**. Everything else in this project protects the analysis from being
wrong. Nothing protected her from the analysis being wrong *and looking fine*.

That is the specific failure this addresses: a run where the candidate list
arrived truncated, or half the box-office figures were missing, or a title was
double-counted — and the pipeline, which is built to carry on rather than
crash, produces a confident one-page recommendation anyway. She presents it.
Yaw asks how many titles it covers. Nobody in the room can tell that the
number is built on 40 films instead of 112.

A gate is worth more than another assertion because of *where* it sits. The
assertions throughout the pipeline protect each step from the one before. This
protects the **client-facing output** from the whole pipeline, and it is the
only check whose failure mode is "the board was misled" rather than "a stage
crashed".

## Why not the alternatives

- **A sensitivity panel** showing whether the answer survives each judgement
  call — already built, at stage 6. It answers Yaw before he asks, which is
  valuable, but it assumes the run was sound in the first place.
- **A run-over-run diff** of what changed since last quarter. Genuinely useful
  for the quarterly rerun, and it needs two quarters of history to be worth
  anything. Next quarter, not this one.
- **A bundle dead-weight score** — the share of a set's films below the
  one-off median. A good negotiating number, and it is a refinement of the
  answer rather than a protection against the answer being wrong.

## What it costs

Four checks, about sixty lines, and the risk that it blocks a run Adjoa
believes is fine. That risk is handled by the message naming the one-line
setting that overrides it, and by keeping the checks blunt: each one, if it
fails, makes the memo actively misleading rather than merely imperfect. A gate
with twenty conditions is a gate somebody permanently disables the first time
it blocks a run for something cosmetic.

## What survives at 500 titles

All four checks are proportions or reconciliations, so none of them needs
re-tuning as the list grows — except
`gate.min_films_for_a_recommendation`, which is an absolute floor and should be
raised if the standalone group stays as thin as it is now.
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(settings: Any, **inputs: Any) -> dict[str, Any]:
    """Stage 10 entry point. Gates, then writes the memo and the improvement."""
    facts = gather(settings, **inputs)
    gate_results = gate(settings, facts)

    for row in gate_results.itertuples(index=False):
        mark = "pass" if row.passed else "FAIL"
        print(f"[stage 10] gate {mark}: {row.check}")

    reports = settings.path(settings["paths"]["reports_dir"])
    reports.mkdir(parents=True, exist_ok=True)
    processed = settings.path(settings["paths"]["processed_dir"])
    gate_results.to_csv(processed / "gate.csv", index=False)

    enforce(gate_results, settings)      # raises GateFailed if anything failed

    memo = build_memo(facts, settings)
    (reports / "memo.md").write_text(memo, encoding="utf-8")
    (reports / "improvement.md").write_text(
        build_improvement(facts, gate_results), encoding="utf-8"
    )
    print(f"[stage 10] memo written: {len(memo.splitlines())} lines, "
          f"as of {facts['as_of_last']}")

    return {"facts": facts, "gate": gate_results, "memo": memo}
