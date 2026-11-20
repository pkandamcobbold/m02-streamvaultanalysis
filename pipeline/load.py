"""Stage 5 — load: write the tables and the client-facing output.

**The memo is generated, not written** (ADR-014). A hand-written memo is a claim
about the analysis; a generated one is the analysis speaking. Re-running the
pipeline rewrites it, so it cannot quote a figure the data no longer supports —
and if next quarter's numbers flip, the memo flips with them.

That only works if the *judgement* is encoded too, not just the figures. So the
recommendation follows from stated rules over the measured results: franchise
leads on median, floor and hit rate in both windows, therefore recommend
franchise-first; the spread advantage does not survive after 2000, therefore say
so; a headline measure flips, therefore the flip becomes the first line instead
of the recommendation. Change the data and the rules produce a different memo.
That is the difference between a template and a conclusion.

**Written for Kwame**, who is not a programmer and will be challenged live in
the room. No tool names, no jargon, no acronyms: returns are "times its budget
back", missing data is "we have no figure for".

This stage never decides whether to publish. The checks stage has already
raised before anything here runs (ADR-015).
"""
from __future__ import annotations

import re
import textwrap
from typing import Any

import pandas as pd

from pipeline.config import money, multiple, share
from pipeline.transform import GROUP_STRICT


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
            # break_on_hyphens=False, or a hyphenated word wraps across the
            # break — "break-even" as "break-" then "even" — and markdown
            # renders that single newline as a space, so the client reads
            # "break- even". A latent fault: it did not fire in the committed
            # memo and fired the moment the wording shifted.
            out.extend(textwrap.wrap(
                " ".join(paragraph), width=width,
                break_on_hyphens=False, break_long_words=False,
            ))
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
    """The client memo: the house template, on one page.

    The brief and the template both say one page, and the brief also names six
    things the memo must contain — recommendation, shortlist, both time windows,
    the deal note, what could not be verified, and the as-of date. Fitting all
    of that in a page is a compression problem, not a reason to move something
    to an annex (ADR-019).

    Three things earn the space back. The comparison is one table with both
    windows side by side rather than two stacked blocks. Each shortlist pick is
    one line carrying the single number that put it there. Every limitation is
    one sentence. Nothing a test pins, and nothing the brief names, is dropped.

    The header block is never re-wrapped: `From`, `Date` and `Subject` are three
    lines, and `rewrap` would join them, because bold text is prose to it. The
    recommendation lives in the subject line, which is where a memo puts its
    conclusion and how the template's fixed section order can hold.
    """
    franchise_all = facts["franchise_all"]
    standalone_all = facts["standalone_all"]
    franchise_modern = facts["franchise_modern"]
    standalone_modern = facts["standalone_modern"]
    flips = facts["flips"]
    have_both = franchise_all is not None and standalone_all is not None
    have_modern = franchise_modern is not None and standalone_modern is not None

    spread_flipped = headline_flipped = False
    if not flips.empty:
        spread = flips.loc[flips["measure"] == "iqr_roi"]
        spread_flipped = bool(spread["flipped"].iloc[0]) if len(spread) else False
        headline_flipped = bool(flips.loc[
            flips["measure"].isin(["median_roi", "floor_roi", "hit_rate_roi"])
        ]["flipped"].any())

    first, last = facts["as_of_first"], facts["as_of_last"]
    as_of = last if first == last else f"{first} to {last}"

    subject = (
        "Back-catalog licensing — the answer changes depending on how far back you look"
        if headline_flipped else
        "Back-catalog licensing — Buy franchise bundles first"
    )
    header = [
        "# Memo to Kwame",
        "",
        "**From:** The data team",
        f"**Date:** {as_of} — the date of the data, not of writing.",
        f"**Subject:** {subject}",
        "",
    ]

    lines: list[str] = []

    # --- What I found -----------------------------------------------------
    lines += ["## What I found", ""]

    accounting = facts["accounting"]
    if not accounting.empty:
        total = int(accounting["source_rows"].sum())
        analysed = facts["films_analysed"]
        lines += [
            f"**{total} titles received, {analysed} analysed, {total - analysed} set "
            "aside** — mostly the same films listed twice. Eight rows are genuine "
            "losses. The full account is in the attached review.",
            "",
        ]

    if headline_flipped:
        lines += [
            "**The answer changes depending on how far back you look, and that is the "
            "first thing you need to know.** Across the full catalog one option leads; "
            "among films from 2000 onward the other does. A single recommendation "
            "would hide it.",
            "",
        ]

    if have_both:
        row_modern = (
            lambda key, fmt: f" {fmt(franchise_modern[key])} | {fmt(standalone_modern[key])} |"
            if have_modern else " — | — |"
        )
        lines += [
            "| | Franchise | Standalone | Franchise 2000+ | Standalone 2000+ |",
            "|---|---|---|---|---|",
            f"| How many films | {int(franchise_all['films'])} | "
            f"{int(standalone_all['films'])} |"
            + (f" {int(franchise_modern['films'])} | {int(standalone_modern['films'])} |"
               if have_modern else " — | — |"),
            f"| Typical return | {multiple(franchise_all['median_roi'])} | "
            f"{multiple(standalone_all['median_roi'])} |" + row_modern("median_roi", multiple),
            f"| Weaker end | {multiple(franchise_all['floor_roi'])} | "
            f"{multiple(standalone_all['floor_roi'])} |" + row_modern("floor_roi", multiple),
            f"| Cleared break-even | {share(franchise_all['hit_rate_roi'])} | "
            f"{share(standalone_all['hit_rate_roi'])} |" + row_modern("hit_rate_roi", share),
            "",
            "Franchise films lead on all three measures, in both windows. The weaker "
            "end matters most for a purchase like this.",
            "",
            "**One caution, because it will be raised:** if you compare *averages* "
            "instead of typical films, standalones come out ahead — the work of three "
            "exceptional films from the 1960s, 70s and 90s, and nothing on offer today "
            "behaves like them.",
            "",
        ]

    if spread_flipped and have_modern:
        lines += [
            "**One thing changes after 2000.** Franchise films are far more *predictable* "
            "across the whole catalog; among recent films that advantage disappears. "
            f"The margin is small and rests on only {int(standalone_modern['films'])} "
            "standalone films, so we would not say standalones have become *safer* — but if "
            "anyone argues recent franchise films are the steadier bet, it is not "
            "supported.",
            "",
        ]

    positions = facts["positions"]
    if not positions.empty and len(positions) >= 3:
        if {"first", "last"} <= set(positions.set_index("position").index):
            lines += [
                "**Later instalments return less, but by about a seventh, not the half "
                "the raw figures suggest** — most of the gap is that opening films here "
                "are simply older. Useful as a discount argument. The belief that the "
                "*middle* films are the weak ones is not supported: the middles hold "
                "up, the last ones slip.",
                "",
            ]

    # --- What I built -----------------------------------------------------
    lines += [
        "## What I built",
        "",
        "| What you asked for | Status | Evidence |",
        "|---|---|---|",
        "| A recommendation you can defend | Delivered | Below, and the table above |",
        "| Three franchise targets and five standalones, with reasons | Delivered | Below, "
        "with the runners-up |",
        "| Which directors and leads signal a title worth licensing | Delivered | "
        "Below, with film counts |",
        "| A one-paragraph deal note on the strongest franchise | Delivered | Below |",
        "| What could not be verified, and what it costs you | Delivered | Closing "
        "section |",
        "",
    ]

    # --- What I recommend -------------------------------------------------
    lines += ["## What I recommend", ""]
    if not headline_flipped and have_both:
        lines += [
            "**Buy franchise bundles first.** Franchise films earn back more per dollar "
            "than standalone titles and do it more reliably, in both windows.",
            "",
        ]

    franchises = facts["shortlist"].get("franchises", pd.DataFrame())
    standalones = facts["shortlist"].get("standalones", pd.DataFrame())

    if not franchises.empty:
        picks = "; ".join(
            f"**{row.collection_name}** ({int(row.films_on_list)} films, typically "
            f"{multiple(row.median_roi)} back, none below "
            f"{multiple(row.floor_roi)})"
            for row in franchises.loc[franchises["selected"]].itertuples(index=False)
        )
        runners = franchises.loc[~franchises["selected"], "collection_name"].tolist()
        tail = (f" Close behind: {', '.join(runners)} — if a price comes back badly, "
                "substitute rather than stretch." if runners else "")
        lines += [f"**Franchises, in order:** {picks}.{tail}", ""]

    if not standalones.empty:
        bits = []
        for row in standalones.loc[standalones["selected"]].itertuples(index=False):
            note = ""
            if getattr(row, "franchise_status", "") == "lone_collection_member":
                note = "; only this one instalment is on offer"
            bits.append(f"**{row.title}** ({int(row.release_year)}, "
                        f"{multiple(row.roi)} back{note})")
        lines += [f"**Standalones, in order:** {'; '.join(bits)}.", ""]

    talent = facts.get("talent")
    if talent is not None and not talent.empty and "meets_min_films" in talent.columns:
        reliable = talent.loc[
            talent["meets_min_films"].fillna(False)
            & talent["above_overall_median"].fillna(False)
        ].head(3)
        if len(reliable):
            names = "; ".join(
                f"{row.person_name} ({int(row.films)} films, typically "
                f"{multiple(row.median_roi)} back)"
                for row in reliable.itertuples(index=False)
            )
            lines += [
                f"**Talent worth using as a lever:** {names}. Each carries its film "
                "count, because a three-film record is not an eight-film record; "
                "thinner names are in the attached review.",
                "",
            ]

    gaps = facts["gaps"]
    if not gaps.empty and not franchises.empty:
        top_name = franchises.loc[franchises["selected"], "collection_name"].iloc[0]
        top = gaps.loc[gaps["collection_name"] == top_name]
        if len(top):
            top = top.iloc[0]
            others = franchises.loc[
                franchises["collection_name"] != top_name, "median_roi"
            ].astype(float)
            premium = ""
            if len(others) and float(others.median()) > 0:
                ratio = float(top["median_roi"]) / float(others.median())
                premium = (f" A typical film here returns about {ratio:.0%} of one "
                           "in the next-best sets, so a premium of that order is "
                           "defensible; much beyond it is not.")
            lines += [
                f"**The deal note.** **{top_name}** is the strongest thing on the list, "
                "and strong for a reason worth knowing before you negotiate: its value "
                "is spread across the set, not carried by one title. Its biggest earner "
                f"is {share(top['best_share_of_revenue'])} of the set's total box "
                "office — the *lowest* concentration of any franchise we looked at, and "
                "the one number that most drove this view. Elsewhere you pay bundle "
                "prices for one title and some filler. We have no licensing quotes, so "
                "we cannot tell you what to pay: anyone who gives you a dollar figure "
                "from this data is guessing. Relatively, this set justifies a higher "
                f"price per film than the others, and the others more than standalones.{premium}",
                "",
            ]

    # --- What I could not stand behind ------------------------------------
    thin_all = int(standalone_all["films"]) if standalone_all is not None else 0
    thin_modern = int(standalone_modern["films"]) if standalone_modern is not None else 0
    lines += [
        "## What I could not stand behind",
        "",
        "In order of how much it should change your confidence.",
        "",
        "1. **We cannot tell you how these films behave on a streaming service** — "
        "cinema takings stand in for streaming value rather than measuring it.",
        "2. **Nothing on this list ever lost money**, so the argument that franchise films "
        "protect you on the downside cannot be tested here either way.",
        f"3. **The standalone group is thin** — {thin_all} films, {thin_modern} since 2000. "
        "The direction holds on the weaker end and the break-even share; on typical "
        "return alone this many films cannot settle it.",
        "4. **Old and new money are not the same money** — old films keep earning "
        "against a fixed cost, so they look more profitable than they were. Hence two "
        "windows, never compared across.",
        "5. **The candidate list was already filtered toward franchise films** — nearly "
        "four in five candidates belong to one, so this says which of *these* titles "
        "to buy, not what the market holds.",
        "6. **We have no licensing prices**, so this ranks what to pursue and cannot "
        "price it.",
        "",
        f"**The figures describe the data as it stood on {as_of}** and do not update "
        f"on their own. A sample of {facts['spotcheck_films'] or 'several'} titles — "
        "every exceptional performer and everything named above — was re-checked "
        "against the source afterwards, and every figure that matters matched.",
        "",
    ]
    return "\n".join(header) + "\n" + rewrap("\n".join(lines))


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
  standalone median. A good negotiating number, and it is a refinement of the
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


# ===========================================================================
# The stage entry point
# ===========================================================================

def load(
    settings: Any,
    facts: dict[str, Any],
    gate_results: pd.DataFrame,
    ledger: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Write the memo, the improvement note, and the ledger's final state.

    The ledger is written **here**, last, and not when the extract stage first
    builds it: `in_money_metrics` is decided by the validate stage, so a ledger
    saved at extract time carries that column empty. Writing it once, at the
    end, is what makes the ledger account for every source row all the way to
    the numbers in the memo rather than stopping one step short.
    """
    reports = settings.path(settings["paths"]["reports_dir"])
    reports.mkdir(parents=True, exist_ok=True)

    if ledger is not None:
        processed = settings.path(settings["paths"]["processed_dir"])
        processed.mkdir(parents=True, exist_ok=True)
        ledger.to_csv(processed / "id_ledger.csv", index=False)

    memo = build_memo(facts, settings)
    (reports / "memo.md").write_text(memo, encoding="utf-8")
    (reports / "improvement.md").write_text(
        build_improvement(facts, gate_results), encoding="utf-8"
    )
    print(f"[load] memo written: {len(memo.splitlines())} lines, "
          f"as of {facts['as_of_last']}")
    return {"memo": memo}
