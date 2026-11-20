"""How much of the franchise-standalone gap survives resampling.

The central comparison is a typical return of about 5.5 for 87 franchise films
against 5.0 for 25 standalones. Reported on its own, that reads as settled. It
is not: the groups are small and their spreads are wide, and the brief asks for
a recommendation Kwame can defend in a room where somebody will ask whether the
difference is real.

So every headline measure is resampled, and the interval is published beside the
figure. Three things about how:

**The interval, not a p-value.** Kwame is deciding where to put $14M, not
testing a hypothesis. "The gap could plausibly be anywhere from −6.3 to +3.1"
tells him what he needs; "p = 0.19" does not.

**Films in one franchise are not independent observations.** The 87 franchise
films come from 23 collections. Sequels share a cast, a director, an audience
and a marketing budget, so resampling individual films overstates how much
evidence there is. `cluster_bootstrap` resamples whole collections instead, and
both are reported — if they disagree, the per-film figure was flattering.

**Seeded.** `uncertainty.random_seed` fixes the draw, so a reviewer who re-runs
this sees the same intervals and can tell a real change from a new sample.

Nothing here changes a point estimate. It changes which measures the memo is
allowed to lead with: on this data the hit-rate gap excludes zero and the
typical-return gap does not (F-02).
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from pipeline.transform.kpis import GROUP_STRICT

UNCERTAINTY_COLUMNS = [
    "measure", "better_is", "franchise", "standalone", "gap",
    "ci_low", "ci_high", "share_franchise_ahead", "excludes_zero", "basis",
]

# The measures the memo can lead with, and how each is computed.
#
# Every statistic takes a 2-D array of resamples — one row per draw — and
# returns one figure per row. That is what keeps this inside the time budget: a
# Python loop over 10,000 draws took 4.1 seconds per group and the whole
# analysis is allowed 10, while the same work along an axis takes about 0.02.
# For the observed figure the array is passed as a single row.
MEASURES: dict[str, tuple[str, Callable[[np.ndarray], np.ndarray]]] = {
    "typical return": ("higher", lambda a: np.median(a, axis=1)),
    "weaker end": ("higher", lambda a: np.percentile(a, 25, axis=1)),
    "share clearing break-even": ("higher", lambda a: (a >= 2.5).mean(axis=1)),
    "spread": ("lower",
               lambda a: np.percentile(a, 75, axis=1) - np.percentile(a, 25, axis=1)),
}


def _observed(statistic: Callable[[np.ndarray], np.ndarray], values: np.ndarray) -> float:
    """The statistic on the real data, using the same code path as the resamples."""
    return float(statistic(values[None, :])[0])


def _groups(cleaned: pd.DataFrame, group_column: str) -> tuple[np.ndarray, np.ndarray]:
    """The two groups' returns, as plain arrays, money-eligible films only."""
    usable = cleaned.loc[cleaned["in_money_metrics"].fillna(False) & cleaned["roi"].notna()]
    franchise = usable.loc[usable[group_column] == "franchise", "roi"]
    standalone = usable.loc[usable[group_column] == "standalone", "roi"]
    return (franchise.to_numpy(dtype=float), standalone.to_numpy(dtype=float))


def _interval(
    draws: np.ndarray, better_is: str
) -> tuple[float, float, float, bool]:
    """Percentile interval, the share favouring franchise, and whether zero is out.

    `better_is` flips the direction for spread, where a *lower* figure is the
    better one: without this, a tighter franchise group would read as the gap
    going the wrong way.
    """
    low, high = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
    ahead = float((draws > 0).mean()) if better_is == "higher" else float((draws < 0).mean())
    return low, high, ahead, bool(low > 0 or high < 0)


def bootstrap_comparison(
    cleaned: pd.DataFrame,
    settings: Any,
    group_column: str = GROUP_STRICT,
) -> pd.DataFrame:
    """Resample films, and report an interval on each measure's gap."""
    config = settings.get("uncertainty") or {}
    samples = int(config.get("bootstrap_samples", 10_000))
    seed = int(config.get("random_seed", 20251031))

    franchise, standalone = _groups(cleaned, group_column)
    if len(franchise) < 2 or len(standalone) < 2:
        return pd.DataFrame(columns=UNCERTAINTY_COLUMNS)

    rng = np.random.default_rng(seed)
    # One index matrix per group, reused across measures: the same resamples
    # answer every question, so the measures are comparable to each other.
    picks_f = rng.integers(0, len(franchise), size=(samples, len(franchise)))
    picks_s = rng.integers(0, len(standalone), size=(samples, len(standalone)))

    resampled_f, resampled_s = franchise[picks_f], standalone[picks_s]

    rows: list[dict[str, Any]] = []
    for name, (better_is, statistic) in MEASURES.items():
        observed_f = _observed(statistic, franchise)
        observed_s = _observed(statistic, standalone)
        draws = statistic(resampled_f) - statistic(resampled_s)
        low, high, ahead, excludes = _interval(draws, better_is)
        rows.append({
            "measure": name,
            "better_is": better_is,
            "franchise": round(observed_f, 3),
            "standalone": round(observed_s, 3),
            "gap": round(observed_f - observed_s, 3),
            "ci_low": round(low, 3),
            "ci_high": round(high, 3),
            "share_franchise_ahead": round(ahead, 3),
            "excludes_zero": excludes,
            "basis": f"{samples:,} resamples of individual films",
        })
    return pd.DataFrame(rows, columns=UNCERTAINTY_COLUMNS)


def cluster_bootstrap(
    cleaned: pd.DataFrame,
    settings: Any,
    group_column: str = GROUP_STRICT,
) -> pd.DataFrame:
    """Resample whole franchises rather than individual films.

    Films in one franchise share almost everything that drives a return, so
    treating 87 of them as 87 independent observations overstates the evidence.
    Resampling the 23 collections whole is the honest unit, and the interval it
    gives is the one to quote if the two disagree.
    """
    config = settings.get("uncertainty") or {}
    # Its own, smaller count: resampling whole franchises gives draws of
    # differing length, so this one cannot be done along an axis and keeps a
    # loop. 2,000 draws move these intervals by about 0.02, which is far below
    # the width that changes any conclusion.
    samples = int(config.get("cluster_bootstrap_samples", 2_000))
    seed = int(config.get("random_seed", 20251031))

    usable = cleaned.loc[cleaned["in_money_metrics"].fillna(False) & cleaned["roi"].notna()]
    franchise = usable.loc[usable[group_column] == "franchise"]
    standalone = usable.loc[usable[group_column] == "standalone", "roi"].to_numpy(dtype=float)
    clusters = [
        group["roi"].to_numpy(dtype=float)
        for _, group in franchise.groupby("collection_id")
    ]
    if len(clusters) < 2 or len(standalone) < 2:
        return pd.DataFrame(columns=UNCERTAINTY_COLUMNS)

    rng = np.random.default_rng(seed)
    # Draw once, reuse for every measure, so the measures stay comparable.
    drawn_f = [
        np.concatenate([clusters[j] for j in rng.integers(0, len(clusters), len(clusters))])
        for _ in range(samples)
    ]
    drawn_s = standalone[rng.integers(0, len(standalone), size=(samples, len(standalone)))]

    rows: list[dict[str, Any]] = []
    all_franchise = np.concatenate(clusters)
    for name, (better_is, statistic) in MEASURES.items():
        observed_f = _observed(statistic, all_franchise)
        observed_s = _observed(statistic, standalone)
        franchise_draws = np.array([_observed(statistic, d) for d in drawn_f])
        draws = franchise_draws - statistic(drawn_s)
        low, high, ahead, excludes = _interval(draws, better_is)
        rows.append({
            "measure": name,
            "better_is": better_is,
            "franchise": round(observed_f, 3),
            "standalone": round(observed_s, 3),
            "gap": round(observed_f - observed_s, 3),
            "ci_low": round(low, 3),
            "ci_high": round(high, 3),
            "share_franchise_ahead": round(ahead, 3),
            "excludes_zero": excludes,
            "basis": f"{samples:,} resamples of {len(clusters)} whole franchises",
        })
    return pd.DataFrame(rows, columns=UNCERTAINTY_COLUMNS)


def measures_that_survive(uncertainty: pd.DataFrame) -> list[str]:
    """The measures whose interval excludes zero — the ones a memo may lead with."""
    if uncertainty.empty:
        return []
    return uncertainty.loc[uncertainty["excludes_zero"].fillna(False), "measure"].tolist()


def announce_uncertainty(uncertainty: pd.DataFrame, clustered: pd.DataFrame) -> list[str]:
    """Say plainly which measures hold and which do not. The brief asks for plainly."""
    notes: list[str] = []
    if uncertainty.empty:
        return ["NOTE: too few films in one group to resample; no intervals computed."]

    survive = measures_that_survive(uncertainty)
    fragile = [m for m in uncertainty["measure"] if m not in survive]
    if survive:
        notes.append(
            "Measures whose gap survives resampling: " + ", ".join(survive)
            + ". These are the ones the recommendation may lead with."
        )
    if fragile:
        notes.append(
            "Measures whose gap does NOT survive resampling: " + ", ".join(fragile)
            + ". The direction is still the more likely one, but this sample cannot "
            "establish it, and the memo must not claim otherwise."
        )
    if not clustered.empty:
        per_film = set(measures_that_survive(uncertainty))
        per_franchise = set(measures_that_survive(clustered))
        lost = per_film - per_franchise
        if lost:
            notes.append(
                "Resampling whole franchises rather than individual films removes: "
                + ", ".join(sorted(lost))
                + ". Sequels are not independent observations, so the per-film "
                "interval was the flattering one."
            )
        else:
            notes.append(
                "The same measures survive when whole franchises are resampled "
                "instead of individual films, so the result does not rest on "
                "treating sequels as independent."
            )
    return notes
