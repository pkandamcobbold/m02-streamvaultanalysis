"""Stage 3 — transform: collapse to film grain, prove the join, build the mart.

Two jobs.

**The proven join.** Stage 1 produced four tables at three grains. The analysis
needs one row per film carrying its director, its lead actor and its genres.
Getting from there to here is where a pipeline quietly starts lying: a merge
against a table that is not unique on the key multiplies rows, every median
shifts, and nothing raises. So every merge is made with `validate=` and an
indicator, and the counts are written to a join report rather than trusted.

**The KPI tables.** Counts beside every statistic; the window is a parameter
called twice, never copy-pasted; and the statistics are chosen for the question
actually asked — "safer" is a claim about the floor and the spread, not the
average, so the lower quartile and the interquartile range carry more weight
here than the mean, which is reported beside them so the disagreement is
visible.

GRAINS produced:

    directors   one row per film per director  (both halves of a partnership)
    analysis    one row per film               (the analysis-ready table)

Nothing in the KPI half loops over rows to produce a number: every figure comes
from a named aggregation over a group (ADR-031).

See ADR-010 (the franchise split), ADR-012 (co-directors), ADR-018 (relative
measures per window), ADR-019 (medians, not means), ADR-020 (the flip check),
ADR-021 (the shortlist's labels) and ADR-022 (position inside one era).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from pipeline.config import ANALYSED_STATUSES
from pipeline.validate import add_hit_flags


# ===========================================================================
# Collapse to film grain and join, with validation
# (was src/streamvault/join.py)
# ===========================================================================

DIRECTOR_JOB = "Director"
LEAD_BILLING_ORDER = 0


JOIN_REPORT_COLUMNS = [
    "merge", "left_rows", "right_rows", "result_rows", "matched",
    "left_only", "right_only",
]


# ---------------------------------------------------------------------------
# Collapsing to film grain
# ---------------------------------------------------------------------------

def directors_long(crew: pd.DataFrame) -> pd.DataFrame:
    """GRAIN: one row per film per director.

    This is the table the talent analysis must use. A film directed by the
    Wachowskis was directed by *both* of them, and counting it for one would
    understate each of their filmographies — which matters directly, because
    `talent.min_films_for_reliable` asks how many films a person has.
    """
    directors = crew.loc[crew["job"] == DIRECTOR_JOB, ["tmdb_id", "person_id", "person_name"]]
    # One person credited as Director twice on one film is a TMDb data entry
    # artefact, not two directing jobs.
    return (
        directors.drop_duplicates(["tmdb_id", "person_id"])
        .sort_values(["tmdb_id", "person_name"], ignore_index=True)
    )


def collapse_directors(crew: pd.DataFrame) -> pd.DataFrame:
    """GRAIN: one row per film. A label for the directors, not a choice of one.

    **Sorted by name, deliberately.** 9 of 112 films have more than one
    credited director, and TMDb returns them in no fixed order: *The Matrix*
    lists Lana then Lilly Wachowski, *The Matrix Revolutions* lists Lilly then
    Lana. Taking `.first()` would therefore credit the same partnership to
    different people on different films — splitting a 3-film body of work into
    two filmographies of 2 and 1, so that neither clears a 3-film reliability
    threshold and a consistent directing partnership vanishes from the talent
    analysis. Sorting makes the label a property of the film rather than of the
    order a response happened to arrive in.

    `n_directors` is kept so the 9 co-directed films can be found again, and so
    any per-director statistic can say how many of its films were shared.
    """
    long = directors_long(crew)
    if long.empty:
        return pd.DataFrame({
            "tmdb_id": pd.Series(dtype="Int64"),
            "director_names": pd.Series(dtype="str"),
            "director_ids": pd.Series(dtype="str"),
            "n_directors": pd.Series(dtype="Int64"),
        })

    grouped = long.groupby("tmdb_id", as_index=False).agg(
        director_names=pd.NamedAgg("person_name", lambda names: " & ".join(sorted(names))),
        director_ids=pd.NamedAgg(
            "person_id", lambda ids: "|".join(str(value) for value in sorted(ids))
        ),
        n_directors=pd.NamedAgg("person_id", "size"),
    )
    grouped["n_directors"] = grouped["n_directors"].astype("Int64")
    return grouped


def collapse_leads(
    cast: pd.DataFrame, billing_order: int = LEAD_BILLING_ORDER
) -> pd.DataFrame:
    """GRAIN: one row per film. The billed lead, where there is exactly one.

    `billing_order == 0` is TMDb's lead. All 112 films in this list have
    exactly one, but that is a fact about this data and not a guarantee, so a
    tie is resolved by name — deterministically, for the same reason the
    directors are sorted — and counted, so the join report shows it happened.

    The order comes from `talent.lead_actor_billing_order` via
    `build_analysis_table`. It used to be read only from the module constant,
    so changing the setting did nothing — two sources of truth for one number,
    found by an audit. The constant remains as the default for direct callers.
    """
    leads = cast.loc[cast["billing_order"] == billing_order]
    leads = (
        leads.sort_values(["tmdb_id", "person_name"])
        .drop_duplicates("tmdb_id", keep="first")
        .loc[:, ["tmdb_id", "person_id", "person_name", "character"]]
        .rename(columns={
            "person_id": "lead_person_id",
            "person_name": "lead_name",
            "character": "lead_character",
        })
    )
    return leads.reset_index(drop=True)


def collapse_genres(genres: pd.DataFrame) -> pd.DataFrame:
    """GRAIN: one row per film. A sorted label and a count — not a "primary" genre.

    TMDb does not document its genre order as meaningful, so calling the first
    one "primary" would invent a fact and then rank films by it. Any genre
    analysis uses the long table and groups properly; this is a label for
    reading a row, and `n_genres` so a 5-genre film is not mistaken for a
    1-genre one.
    """
    if genres.empty:
        return pd.DataFrame({
            "tmdb_id": pd.Series(dtype="Int64"),
            "genre_names": pd.Series(dtype="str"),
            "n_genres": pd.Series(dtype="Int64"),
        })
    grouped = genres.groupby("tmdb_id", as_index=False).agg(
        genre_names=pd.NamedAgg("genre_name", lambda names: "|".join(sorted(names))),
        n_genres=pd.NamedAgg("genre_id", "nunique"),
    )
    grouped["n_genres"] = grouped["n_genres"].astype("Int64")
    return grouped


# ---------------------------------------------------------------------------
# The proven join
# ---------------------------------------------------------------------------

def _merge_proven(
    left: pd.DataFrame,
    right: pd.DataFrame,
    name: str,
    report: list[dict[str, Any]],
) -> pd.DataFrame:
    """One left join, validated, counted, and the indicator column removed.

    `validate="one_to_one"` is the whole point: it raises if either side is not
    unique on `tmdb_id`. That is the failure a human cannot see — a duplicated
    key multiplies rows, every statistic moves, and the result looks fine.

    The indicator is named per merge and dropped immediately. Left in place it
    would collide with the next merge's indicator, and pandas would resolve the
    collision by renaming rather than complaining.
    """
    indicator = f"_merge_{name}"
    merged = left.merge(
        right, on="tmdb_id", how="left", validate="one_to_one", indicator=indicator,
    )
    counts = merged[indicator].value_counts()
    report.append({
        "merge": name,
        "left_rows": len(left),
        "right_rows": len(right),
        "result_rows": len(merged),
        "matched": int(counts.get("both", 0)),
        "left_only": int(counts.get("left_only", 0)),
        "right_only": int(counts.get("right_only", 0)),
    })

    # A left join cannot produce right_only rows, so if one appears the merge
    # is not what it claims to be.
    assert int(counts.get("right_only", 0)) == 0, f"{name}: left join produced right_only rows"
    # The row count is the assertion that matters. A left join must never grow.
    assert len(merged) == len(left), (
        f"{name}: {len(left)} films in, {len(merged)} out — the merge multiplied rows"
    )
    return merged.drop(columns=[indicator])


def build_analysis_table(
    films: pd.DataFrame,
    cast: pd.DataFrame,
    crew: pd.DataFrame,
    genres: pd.DataFrame,
    settings: Any = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """GRAIN: one row per film. Returns (analysis table, join report).

    Three left joins from `films`. Left, not inner: a film with no director
    must keep its row and show a missing director, because an inner join would
    delete it from the film count and the deletion would be invisible —
    the count would simply be smaller than the number of films fetched.
    """
    billing_order = (
        int(settings["talent"]["lead_actor_billing_order"])
        if settings is not None else LEAD_BILLING_ORDER
    )
    report: list[dict[str, Any]] = []
    analysis = films.copy()
    analysis = _merge_proven(analysis, collapse_directors(crew), "directors", report)
    analysis = _merge_proven(
        analysis, collapse_leads(cast, billing_order), "leads", report
    )
    analysis = _merge_proven(analysis, collapse_genres(genres), "genres", report)

    return analysis, pd.DataFrame(report, columns=JOIN_REPORT_COLUMNS)


# ---------------------------------------------------------------------------
# Accounting: every id, start to finish
# ---------------------------------------------------------------------------

def account_for_every_id(ledger: pd.DataFrame, analysis: pd.DataFrame) -> pd.DataFrame:
    """One row per ledger status, with how many reached the analysis table.

    This is the table the memo's "127 received, N analysed, here is the rest"
    sentence is read off. It is built from the two ends of the pipeline and
    compared, rather than from a count anyone carried forward by hand.

    **A row counts as having reached the analysis only if it is the row that
    put the film there.** Testing "is this id in the analysis?" alone is wrong,
    and wrong in the direction that flatters: a duplicate row carries the *same
    id* as the row that was kept, so it would also answer yes, and the
    accounting would claim 113 of 127 rows became films when only 112 films
    exist. `ANALYSED_STATUSES` names the statuses that own their film; stage 6
    extends it when it starts excluding films for quality reasons.
    """
    in_analysis = set(analysis["tmdb_id"].dropna().astype(int))
    data = ledger.loc[ledger["status"] != "header_row"].copy()
    data["reached_analysis"] = [
        status in ANALYSED_STATUSES and not pd.isna(tmdb_id)
        and int(tmdb_id) in in_analysis
        for status, tmdb_id in zip(data["status"], data["tmdb_id"])
    ]
    summary = (
        data.groupby("status", as_index=False)
        .agg(
            source_rows=pd.NamedAgg("source_row", "size"),
            reached_analysis=pd.NamedAgg("reached_analysis", "sum"),
        )
        .sort_values("source_rows", ascending=False, ignore_index=True)
    )
    summary["reached_analysis"] = summary["reached_analysis"].astype("Int64")
    return summary


def assert_join(
    analysis: pd.DataFrame,
    films: pd.DataFrame,
    ledger: pd.DataFrame,
    accounting: pd.DataFrame,
) -> list[str]:
    """Hard-assert the join's integrity; report what is a finding about the data."""
    notes: list[str] = []

    assert len(analysis) == len(films), (
        f"analysis has {len(analysis)} rows for {len(films)} films"
    )
    assert analysis["tmdb_id"].is_unique, "analysis has more than one row for some film"

    # Every film that was fetched must reach the analysis, and nothing else may.
    fetched = set(
        ledger.loc[ledger["status"] == "fetched", "tmdb_id"].dropna().astype(int)
    )
    reached = set(analysis["tmdb_id"].dropna().astype(int))
    assert reached == fetched, (
        f"{len(fetched - reached)} fetched film(s) missing from the analysis, "
        f"{len(reached - fetched)} present that were never fetched"
    )

    # The accounting table must add up to the source rows, or the memo's
    # sentence about where the titles went is quoting a number nothing supports.
    assert int(accounting["source_rows"].sum()) == int(
        ledger.loc[ledger["status"] != "header_row"].shape[0]
    ), "the accounting table does not add up to the ledger's data rows"

    # --- findings, not failures -------------------------------------------
    for column, label in (
        ("director_names", "no director"),
        ("lead_name", "no billed lead"),
        ("genre_names", "no genre"),
    ):
        if column in analysis.columns:
            missing = analysis.loc[analysis[column].isna(), "tmdb_id"].tolist()
            if missing:
                notes.append(
                    f"NOTE: {len(missing)} film(s) have {label}: {missing}. They keep "
                    "their row — the left join is what makes that true — but every "
                    f"statistic grouped by {column} must report its own n."
                )

    if "n_directors" in analysis.columns:
        shared = analysis.loc[analysis["n_directors"] > 1]
        if len(shared):
            notes.append(
                f"NOTE: {len(shared)} film(s) have more than one credited director. "
                "The film-level label is the sorted partnership; per-director "
                "statistics must come from the long directors table, where the film "
                "counts for each of them."
            )
    return notes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def join_tables(
    settings: Any, ledger: pd.DataFrame, tables: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    """Join to film grain. Returns the analysis table and its evidence."""
    films, cast, crew, genres = (
        tables["films"], tables["cast"], tables["crew"], tables["genres"]
    )
    analysis, report = build_analysis_table(films, cast, crew, genres, settings)
    directors = directors_long(crew)
    accounting = account_for_every_id(ledger, analysis)

    for note in assert_join(analysis, films, ledger, accounting):
        print(f"[transform] {note}")

    print(f"[transform] analysis table: {len(analysis)} films, {len(analysis.columns)} columns")
    print(f"[transform] {len(directors)} director credits across "
          f"{directors['person_id'].nunique()} people")

    processed = settings.path(settings["paths"]["processed_dir"])
    interim = settings.path(settings["paths"]["interim_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    interim.mkdir(parents=True, exist_ok=True)
    analysis.to_csv(interim / "analysis.csv", index=False)
    directors.to_csv(interim / "directors.csv", index=False)
    report.to_csv(processed / "join_report.csv", index=False)
    accounting.to_csv(processed / "id_accounting.csv", index=False)

    return {
        "analysis": analysis,
        "directors": directors,
        "join_report": report,
        "accounting": accounting,
    }

# ===========================================================================
# The KPI tables: both windows, counts beside every statistic
# (was src/streamvault/kpis.py)
# ===========================================================================

GROUP_STRICT = "franchise_group_strict"
GROUP_LOOSE = "franchise_group_loose"

# `performance.hit_definition` names one of these. All three are computed at
# stage 6; this decides which one the reports treat as *the* hit rate, and
# `report_all_hit_definitions` decides whether the other two travel with it.
#
# Both settings were inert until an audit found them: the code reported all
# three unconditionally while ADR-015 credited a setting with that behaviour.
# A switch nothing reads is worse than no switch, because the decision record
# claims it can be flipped.
HIT_RATE_COLUMNS = {
    "roi": "hit_rate_roi",
    "above_median": "hit_rate_above_median",
    "top_quartile": "hit_rate_top_quartile",
}

POSITION_FIRST = "first"
POSITION_MIDDLE = "middle"
POSITION_LAST = "last"


# ---------------------------------------------------------------------------
# The core comparison
# ---------------------------------------------------------------------------

def _p25(series: pd.Series) -> float:
    return series.quantile(0.25)


def _p75(series: pd.Series) -> float:
    return series.quantile(0.75)


def primary_hit_column(settings: Any) -> str:
    """The hit-rate column `performance.hit_definition` selects."""
    definition = str(settings["performance"]["hit_definition"])
    if definition not in HIT_RATE_COLUMNS:
        raise ValueError(
            f"performance.hit_definition is {definition!r}; expected one of "
            f"{sorted(HIT_RATE_COLUMNS)}"
        )
    return HIT_RATE_COLUMNS[definition]


def compare_groups(
    films: pd.DataFrame,
    group_column: str = GROUP_STRICT,
    min_year: int | None = None,
    settings: Any = None,
) -> pd.DataFrame:
    """Franchise against standalone for one window. `min_year=None` is all years.

    Named aggregation throughout, counts beside every statistic, no row loops.

    `floor_roi` is the lower quartile rather than the minimum: a single worst
    film is an anecdote, and on this list the minimum is 1.13x for everyone
    (F12). The quartile is what "higher floor" can actually be measured as.
    """
    scope = films if min_year is None else films.loc[
        films["release_year"].notna() & (films["release_year"] >= min_year)
    ]
    money = scope.loc[scope["in_money_metrics"].fillna(False)]

    if money.empty:
        return pd.DataFrame(columns=[
            group_column, "films", "median_roi", "floor_roi", "upper_roi",
            "iqr_roi", "mean_roi", "min_roi", "max_roi", "hit_rate_roi",
            "hits_roi", "hit_rate_above_median", "hit_rate_top_quartile",
            "median_revenue", "median_budget", "median_rating", "median_votes",
        ])

    table = money.groupby(group_column, as_index=False).agg(
        films=pd.NamedAgg("tmdb_id", "size"),
        median_roi=pd.NamedAgg("roi", "median"),
        floor_roi=pd.NamedAgg("roi", _p25),
        upper_roi=pd.NamedAgg("roi", _p75),
        mean_roi=pd.NamedAgg("roi", "mean"),
        min_roi=pd.NamedAgg("roi", "min"),
        max_roi=pd.NamedAgg("roi", "max"),
        hits_roi=pd.NamedAgg("is_hit_roi", "sum"),
        hit_rate_roi=pd.NamedAgg("is_hit_roi", "mean"),
        hit_rate_above_median=pd.NamedAgg("is_hit_above_median", "mean"),
        hit_rate_top_quartile=pd.NamedAgg("is_hit_top_quartile", "mean"),
        median_revenue=pd.NamedAgg("revenue", "median"),
        median_budget=pd.NamedAgg("budget", "median"),
        median_rating=pd.NamedAgg("vote_average", "median"),
        median_votes=pd.NamedAgg("vote_count", "median"),
    )
    # Spread as the interquartile range, not the standard deviation: a few real
    # 70x returns (F11) inflate an SD without telling you anything about the
    # typical gap between a good and a bad film in the group.
    table["iqr_roi"] = table["upper_roi"] - table["floor_roi"]

    if settings is not None:
        primary = primary_hit_column(settings)
        table["hit_rate_primary"] = table[primary]
        table.attrs["hit_definition"] = settings["performance"]["hit_definition"]
        if not bool(settings["performance"]["report_all_hit_definitions"]):
            # Drop the alternatives the reader asked not to see. Kept as a
            # setting rather than hard-coded because F12 is the reason all
            # three are normally shown: on a list with no failures in it, no
            # single definition is defensible alone.
            table = table.drop(columns=[
                column for column in HIT_RATE_COLUMNS.values() if column != primary
            ])
    return table.round(3)


def by_window(
    cleaned: pd.DataFrame, settings: Any, group_column: str = GROUP_STRICT
) -> dict[str, pd.DataFrame]:
    """One comparison per configured window, each computed in its own pool.

    The relative hit flags are recomputed inside each window before the
    comparison, which is the whole of ADR-018: inherited flags would measure
    modern films against a median partly set by 1970s films.
    """
    tables: dict[str, pd.DataFrame] = {}
    for name, window in settings.windows.items():
        min_year = window["min_year"]
        scope = cleaned if min_year is None else cleaned.loc[
            cleaned["release_year"].notna() & (cleaned["release_year"] >= min_year)
        ]
        rescoped = add_hit_flags(scope.copy(), settings)
        tables[name] = compare_groups(
            rescoped, group_column, min_year=None, settings=settings
        )
    return tables


def flip_check(tables: dict[str, pd.DataFrame], group_column: str = GROUP_STRICT) -> pd.DataFrame:
    """Does the winner change between windows, and on which measure?

    Richer than a single boolean on purpose. The recommendation can hold on the
    median and flip on the floor, and that is a different conversation with
    Kwame than "it flips" or "it holds" — so every measure is checked and
    reported separately.
    """
    # Check the hit rate the reports actually lead with. With a non-default
    # hit_definition, `hit_rate_roi` may not even be in the table.
    sample = next(iter(tables.values()), pd.DataFrame())
    hit_column = (
        "hit_rate_primary" if "hit_rate_primary" in sample.columns else "hit_rate_roi"
    )
    measures = ["median_roi", "floor_roi", hit_column, "iqr_roi"]
    rows: list[dict[str, Any]] = []

    for measure in measures:
        winners: dict[str, Any] = {}
        for window, table in tables.items():
            if table.empty or measure not in table.columns:
                winners[window] = pd.NA
                continue
            # For spread, lower is better: a tighter group is the safer buy.
            index = table[measure].idxmin() if measure == "iqr_roi" \
                else table[measure].idxmax()
            winners[window] = table.loc[index, group_column]

        distinct = {value for value in winners.values() if not pd.isna(value)}
        rows.append({
            "measure": measure,
            "better_is": "lower" if measure == "iqr_roi" else "higher",
            **{f"winner_{window}": value for window, value in winners.items()},
            "flipped": len(distinct) > 1,
        })

    return pd.DataFrame(rows)


def announce_flip(flips: pd.DataFrame) -> list[str]:
    """Say it loudly if any measure flips. The brief asks for loudly."""
    notes: list[str] = []
    flipped = flips.loc[flips["flipped"]]
    if len(flipped):
        notes.append("=" * 70)
        notes.append(
            "RECOMMENDATION FLIPS BETWEEN WINDOWS on: "
            + ", ".join(flipped["measure"].tolist())
        )
        notes.append("This belongs in the memo's first paragraph, not a footnote.")
        notes.append("=" * 70)
    else:
        notes.append(
            "No measure flips between windows: the same group leads on median, "
            "floor, hit rate and spread in both. Yaw's objection changes the "
            "size of the answer (F10), not its direction."
        )
    return notes


# ---------------------------------------------------------------------------
# Inside a franchise: are the middle entries the weak ones?
# ---------------------------------------------------------------------------

def position_within_franchise(cleaned: pd.DataFrame, min_entries: int = 3) -> pd.DataFrame:
    """CL2: compare first, middle and last entries inside each collection.

    `min_entries=3` because a two-film collection has no middle, and including
    it would put its second film in the "last" bucket and silently change what
    "last" means. Ranked by release date, which is the order a viewer met them
    in and the order a bundle is built in.
    """
    scope = cleaned.loc[
        cleaned["collection_id"].notna() & cleaned["in_money_metrics"].fillna(False)
    ].copy()
    if scope.empty:
        return pd.DataFrame(columns=["position", "films", "collections",
                                     "median_roi", "floor_roi", "median_revenue"])

    scope["entries_on_list"] = scope.groupby("collection_id")["tmdb_id"].transform("size")
    scope = scope.loc[scope["entries_on_list"] >= min_entries].copy()
    if scope.empty:
        return pd.DataFrame(columns=["position", "films", "collections",
                                     "median_roi", "floor_roi", "median_revenue"])

    scope["entry_rank"] = (
        scope.groupby("collection_id")["release_date"].rank(method="first").astype("Int64")
    )
    scope["position"] = POSITION_MIDDLE
    scope.loc[scope["entry_rank"] == 1, "position"] = POSITION_FIRST
    scope.loc[scope["entry_rank"] == scope["entries_on_list"], "position"] = POSITION_LAST

    table = scope.groupby("position", as_index=False).agg(
        films=pd.NamedAgg("tmdb_id", "size"),
        collections=pd.NamedAgg("collection_id", "nunique"),
        median_roi=pd.NamedAgg("roi", "median"),
        floor_roi=pd.NamedAgg("roi", _p25),
        median_revenue=pd.NamedAgg("revenue", "median"),
        median_rating=pd.NamedAgg("vote_average", "median"),
    )
    order = {POSITION_FIRST: 0, POSITION_MIDDLE: 1, POSITION_LAST: 2}
    table = table.sort_values("position", key=lambda s: s.map(order), ignore_index=True)
    return table.round(3)


def gap_to_best_entry(cleaned: pd.DataFrame, min_entries: int = 2) -> pd.DataFrame:
    """How far below its collection's best entry does a typical entry sit?

    The other half of CL2. "We overpay for weak middle entries" is a claim
    about the gap *within* a bundle, which a cross-collection median hides: a
    bundle whose films are all mediocre and one whose opener carries it can
    have the same median.
    """
    scope = cleaned.loc[
        cleaned["collection_id"].notna() & cleaned["in_money_metrics"].fillna(False)
    ].copy()
    if scope.empty:
        return pd.DataFrame(columns=["collection_name", "entries_on_list", "best_roi",
                                     "median_roi", "worst_roi", "best_share_of_revenue"])

    scope["entries_on_list"] = scope.groupby("collection_id")["tmdb_id"].transform("size")
    scope = scope.loc[scope["entries_on_list"] >= min_entries]

    table = scope.groupby(["collection_id", "collection_name"], as_index=False).agg(
        entries_on_list=pd.NamedAgg("tmdb_id", "size"),
        best_roi=pd.NamedAgg("roi", "max"),
        median_roi=pd.NamedAgg("roi", "median"),
        worst_roi=pd.NamedAgg("roi", "min"),
        total_revenue=pd.NamedAgg("revenue", "sum"),
        top_film_revenue=pd.NamedAgg("revenue", "max"),
    )
    table["best_to_median"] = (table["best_roi"] / table["median_roi"]).round(2)
    # Question 6: the single number that drives a bundle's value.
    table["best_share_of_revenue"] = (
        table["top_film_revenue"] / table["total_revenue"]
    ).round(3)
    return table.sort_values("median_roi", ascending=False, ignore_index=True).round(3)


# ---------------------------------------------------------------------------
# Bundle economics — the unit of purchase
# ---------------------------------------------------------------------------

def bundle_table(cleaned: pd.DataFrame, settings: Any) -> pd.DataFrame:
    """One row per collection: a bundle is what Kwame actually buys.

    Aggregated to the collection because a per-film median answers a question
    nobody is asking. A bundle's value is its total; its risk is its weakest
    entry — both are here, beside the count of how many of its films are even
    on offer.
    """
    minimum = int(settings["franchise"]["min_members_on_list"])
    scope = cleaned.loc[
        cleaned["collection_id"].notna() & cleaned["in_money_metrics"].fillna(False)
    ]
    if scope.empty:
        return pd.DataFrame(columns=["collection_name", "films_on_list", "median_roi"])

    table = scope.groupby(["collection_id", "collection_name"], as_index=False).agg(
        films_on_list=pd.NamedAgg("tmdb_id", "size"),
        median_roi=pd.NamedAgg("roi", "median"),
        floor_roi=pd.NamedAgg("roi", "min"),
        best_roi=pd.NamedAgg("roi", "max"),
        total_revenue=pd.NamedAgg("revenue", "sum"),
        total_budget=pd.NamedAgg("budget", "sum"),
        median_rating=pd.NamedAgg("vote_average", "median"),
        first_year=pd.NamedAgg("release_year", "min"),
        last_year=pd.NamedAgg("release_year", "max"),
    )
    table["bundle_roi"] = (table["total_revenue"] / table["total_budget"]).round(3)
    table["is_buyable_bundle"] = table["films_on_list"] >= minimum
    return table.sort_values("median_roi", ascending=False, ignore_index=True).round(3)


# ---------------------------------------------------------------------------
# Talent
# ---------------------------------------------------------------------------

def talent_table(
    credits: pd.DataFrame, cleaned: pd.DataFrame, settings: Any, role: str
) -> pd.DataFrame:
    """Per-person performance, with the film count beside every name.

    `min_films_for_reliable` filters the *recommendation*, not the table: the
    count stays visible so a negotiator can see a three-film record for what it
    is. A name with 3 films and a name with 8 are not the same evidence, and
    hiding the difference is how a shortlist acquires a spurious star.
    """
    minimum = int(settings["talent"]["min_films_for_reliable"])
    money = cleaned.loc[cleaned["in_money_metrics"].fillna(False)]
    overall_median = money["roi"].astype("float64").median()

    joined = credits.merge(
        money[["tmdb_id", "roi", "is_hit_roi", "vote_average", "release_year"]],
        on="tmdb_id", how="inner", validate="many_to_one",
    )
    if joined.empty:
        return pd.DataFrame(columns=["person_id", "person_name", "role", "films",
                                     "median_roi", "above_overall_median"])

    table = joined.groupby(["person_id", "person_name"], as_index=False).agg(
        films=pd.NamedAgg("tmdb_id", "nunique"),
        median_roi=pd.NamedAgg("roi", "median"),
        floor_roi=pd.NamedAgg("roi", "min"),
        best_roi=pd.NamedAgg("roi", "max"),
        hit_rate_roi=pd.NamedAgg("is_hit_roi", "mean"),
        median_rating=pd.NamedAgg("vote_average", "median"),
        first_year=pd.NamedAgg("release_year", "min"),
        last_year=pd.NamedAgg("release_year", "max"),
    )
    table["role"] = role
    table["above_overall_median"] = table["median_roi"] > overall_median
    table["meets_min_films"] = table["films"] >= minimum
    return table.sort_values(
        ["meets_min_films", "median_roi"], ascending=[False, False], ignore_index=True
    ).round(3)


def leads_as_credits(cleaned: pd.DataFrame) -> pd.DataFrame:
    """The lead-actor columns, reshaped to the same shape as directors_long."""
    leads = cleaned.loc[cleaned["lead_person_id"].notna(),
                        ["tmdb_id", "lead_person_id", "lead_name"]]
    return leads.rename(columns={"lead_person_id": "person_id", "lead_name": "person_name"})


def billed_as_credits(cast: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """The top `top_n` billed actors per film, shaped like directors_long.

    The alternative to judging an actor by their lead roles only: a performer
    billed second or third is still a draw, and on a 112-film list the
    lead-only view leaves most of the cast unexamined.
    """
    billed = cast.loc[
        cast["billing_order"].notna() & (cast["billing_order"] < int(top_n)),
        ["tmdb_id", "person_id", "person_name"],
    ]
    return billed.drop_duplicates(["tmdb_id", "person_id"], ignore_index=True)


def talent_sensitivity(
    cast: pd.DataFrame, cleaned: pd.DataFrame, settings: Any
) -> pd.DataFrame:
    """Does the reliable-talent list survive widening from leads to top-N billed?

    `talent.sensitivity_top_n_billed` has existed since the planning stage with
    the comment "re-run the talent analysis on top-3 billed", and until an
    audit found it, nothing read it — a rejected alternative that was supposed
    to stay runnable and never was. This is that run.

    Returns one row per person who clears `min_films_for_reliable` under either
    view, with the film count and median return under each, so a name that
    appears only when the net is widened is visible as such rather than
    arriving unexplained.
    """
    top_n = int(settings["talent"]["sensitivity_top_n_billed"])
    minimum = int(settings["talent"]["min_films_for_reliable"])

    lead_view = talent_table(leads_as_credits(cleaned), cleaned, settings, "lead_actor")
    billed_view = talent_table(
        billed_as_credits(cast, top_n), cleaned, settings, f"top_{top_n}_billed"
    )
    if lead_view.empty and billed_view.empty:
        return pd.DataFrame(columns=["person_id", "person_name", "films_as_lead",
                                     "median_roi_as_lead", f"films_top_{top_n}",
                                     f"median_roi_top_{top_n}", "appears_only_when_widened"])

    keep = ["person_id", "person_name", "films", "median_roi", "meets_min_films"]
    merged = (
        lead_view[keep].rename(columns={
            "films": "films_as_lead", "median_roi": "median_roi_as_lead",
            "meets_min_films": "reliable_as_lead",
        })
        .merge(
            billed_view[keep].rename(columns={
                "films": f"films_top_{top_n}",
                "median_roi": f"median_roi_top_{top_n}",
                "meets_min_films": f"reliable_top_{top_n}",
            }),
            on=["person_id", "person_name"], how="outer",
        )
    )
    for column in ("reliable_as_lead", f"reliable_top_{top_n}"):
        merged[column] = merged[column].fillna(False).astype("boolean")

    merged = merged.loc[
        merged["reliable_as_lead"].fillna(False)
        | merged[f"reliable_top_{top_n}"].fillna(False)
    ].copy()
    merged["appears_only_when_widened"] = (
        ~merged["reliable_as_lead"].fillna(False)
        & merged[f"reliable_top_{top_n}"].fillna(False)
    )
    merged.attrs["min_films_for_reliable"] = minimum
    merged.attrs["top_n"] = top_n
    return merged.sort_values(
        [f"median_roi_top_{top_n}", "median_roi_as_lead"],
        ascending=False, ignore_index=True,
    )


# ---------------------------------------------------------------------------
# The shortlist
# ---------------------------------------------------------------------------

def shortlist(
    cleaned: pd.DataFrame, bundles: pd.DataFrame, settings: Any
) -> dict[str, pd.DataFrame]:
    """Three franchises and five standalones, by a rule simple enough to say.

    The rule: rank by median ROI within the group, having first required that
    the thing is actually buyable (a bundle needs `min_members_on_list` films
    on offer). Runners-up are included because "why it made the cut" means
    nothing without what did not.
    """
    n_franchises = int(settings["shortlist"]["n_franchises"])
    n_standalones = int(settings["shortlist"]["n_standalones"])
    runners = int(settings["shortlist"]["show_runners_up"])

    buyable = bundles.loc[bundles["is_buyable_bundle"]].copy()
    franchise_columns = ["collection_name", "films_on_list", "median_roi", "floor_roi",
                         "best_roi", "bundle_roi", "total_revenue", "median_rating",
                         "first_year", "last_year"]
    franchises = buyable.head(n_franchises + runners)[franchise_columns].copy()
    franchises["selected"] = [True] * min(n_franchises, len(franchises)) + \
        [False] * max(0, len(franchises) - n_franchises)

    standalones = cleaned.loc[
        (cleaned[GROUP_STRICT] == "standalone")
        & cleaned["in_money_metrics"].fillna(False)
    ].sort_values("roi", ascending=False, ignore_index=True)
    standalone_columns = ["tmdb_id", "title", "release_year", "roi", "revenue",
                          "budget", "vote_average", "vote_count", "rating_reliable",
                          "franchise_status"]
    standalones = standalones.head(n_standalones + runners)[standalone_columns].copy()
    standalones["selected"] = [True] * min(n_standalones, len(standalones)) + \
        [False] * max(0, len(standalones) - n_standalones)

    return {"franchises": franchises.round(3), "standalones": standalones.round(3)}


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def assert_kpis(
    tables: dict[str, pd.DataFrame], cleaned: pd.DataFrame, group_column: str = GROUP_STRICT
) -> list[str]:
    """Hard-assert the tables describe the films we think they do."""
    notes: list[str] = []
    eligible = int(cleaned["in_money_metrics"].fillna(False).sum())

    for window, table in tables.items():
        if table.empty:
            notes.append(f"NOTE: the {window} window has no films in money metrics.")
            continue

        # Counts beside every statistic is not decoration: it is the assertion
        # that the groups partition the window exactly.
        assert "films" in table.columns, f"{window}: no count column"
        assert table["films"].notna().all(), f"{window}: a group has no count"
        assert table[group_column].is_unique, f"{window}: a group appears twice"

        if window == "all_years":
            assert int(table["films"].sum()) == eligible, (
                f"all_years groups hold {int(table['films'].sum())} films, "
                f"but {eligible} are in money metrics"
            )

        thin = table.loc[table["films"] < 10]
        for row in thin.itertuples(index=False):
            notes.append(
                f"NOTE: in the {window} window, {getattr(row, group_column)} has only "
                f"{int(row.films)} films. Every statistic for that group is reported "
                "with its n for this reason; a median over this many films moves "
                "materially if one film enters or leaves."
            )
    return notes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def measure(
    settings: Any,
    cleaned: pd.DataFrame,
    directors: pd.DataFrame,
    cast: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Compute every KPI table. Every KPI table, both windows, plus the flip check."""
    strict = by_window(cleaned, settings, GROUP_STRICT)
    loose = by_window(cleaned, settings, GROUP_LOOSE)
    flips = flip_check(strict, GROUP_STRICT)

    for note in assert_kpis(strict, cleaned, GROUP_STRICT):
        print(f"[transform] {note}")
    for line in announce_flip(flips):
        print(f"[transform] {line}")

    bundles = bundle_table(cleaned, settings)
    positions = position_within_franchise(cleaned)
    gaps = gap_to_best_entry(cleaned)
    director_talent = talent_table(directors, cleaned, settings, "director")
    lead_talent = talent_table(leads_as_credits(cleaned), cleaned, settings, "lead_actor")
    picks = shortlist(cleaned, bundles, settings)
    widened = (
        talent_sensitivity(cast, cleaned, settings)
        if cast is not None else pd.DataFrame()
    )

    processed = settings.path(settings["paths"]["processed_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    for window, table in strict.items():
        table.to_csv(processed / f"kpi_{window}.csv", index=False)
    for window, table in loose.items():
        table.to_csv(processed / f"kpi_{window}_lone_as_franchise.csv", index=False)
    flips.to_csv(processed / "kpi_flip_check.csv", index=False)
    bundles.to_csv(processed / "kpi_bundles.csv", index=False)
    positions.to_csv(processed / "kpi_position_in_franchise.csv", index=False)
    gaps.to_csv(processed / "kpi_bundle_gaps.csv", index=False)
    director_talent.to_csv(processed / "kpi_talent_directors.csv", index=False)
    lead_talent.to_csv(processed / "kpi_talent_leads.csv", index=False)
    picks["franchises"].to_csv(processed / "shortlist_franchises.csv", index=False)
    picks["standalones"].to_csv(processed / "shortlist_standalones.csv", index=False)
    if not widened.empty:
        widened.to_csv(processed / "kpi_talent_sensitivity.csv", index=False)
        added = int(widened["appears_only_when_widened"].sum())
        print(
            f"[transform] talent sensitivity (top-"
            f"{settings['talent']['sensitivity_top_n_billed']} billed vs leads only): "
            f"{len(widened)} reliable name(s), {added} of them visible only when "
            "the net is widened"
        )

    print(f"[transform] {len(bundles)} collections, "
          f"{int(bundles['is_buyable_bundle'].sum())} of them buyable bundles")
    print(f"[transform] {int(director_talent['meets_min_films'].sum())} directors and "
          f"{int(lead_talent['meets_min_films'].sum())} leads meet the film minimum")

    return {
        "windows_strict": strict,
        "windows_loose": loose,
        "flips": flips,
        "bundles": bundles,
        "positions": positions,
        "bundle_gaps": gaps,
        "talent_directors": director_talent,
        "talent_leads": lead_talent,
        "talent_sensitivity": widened,
        "shortlist": picks,
    }


# ===========================================================================
# The stage entry point
# ===========================================================================

def transform(
    settings: Any,
    ledger: pd.DataFrame,
    cleaned: pd.DataFrame,
    cast: pd.DataFrame,
    crew: pd.DataFrame,
    genres: pd.DataFrame,
) -> dict[str, Any]:
    """Join the cleaned films to their credits, then compute every KPI table.

    The films arriving here already carry their cleaning flags, so the join is
    the last thing that changes the table's shape and the KPIs are computed on
    a table whose eligibility columns are already decided.
    """
    joined = join_tables(
        settings, ledger,
        {"films": cleaned, "cast": cast, "crew": crew, "genres": genres},
    )
    measured = measure(settings, joined["analysis"], joined["directors"], cast)
    return {**joined, **measured}
