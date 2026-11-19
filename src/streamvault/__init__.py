"""StreamVault back-catalog licensing analysis.

Stage modules, in the order run_pipeline.py calls them:

    config      settings.toml + the API token from the environment
    ingest      stage 1 — load the id list, build the ledger
    fetch       stage 2 — cached, retried, rate-limited TMDb calls
    flatten     stage 3 — nested JSON to one table per grain
    join        stage 4 — validated merges with indicator reports
    profile     stage 5 — profiling and fault detection
    clean       stage 6 — parameterised cleaning rules (flags, not deletions)
    kpis        stage 7 — grouped aggregations for both time windows
    budget      stage 8 — the time budget and the 500-title projection
    spotcheck   stage 9 — live re-fetch and discrepancy classification

Plus one helper, used by every stage rather than being one of them:

    timings     append each stage's duration to data/processed/run_timings.csv,
                which is what stage 8 computes the budget and projection from
"""

__version__ = "0.1.0"
