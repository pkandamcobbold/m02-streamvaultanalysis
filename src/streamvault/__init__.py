"""StreamVault back-catalog licensing analysis.

Stage modules, in the order run_pipeline.py calls them:

    config      settings.yaml + the API token from the environment
    ingest      stage 1 — load the id list, build the ledger
    fetch       stage 2 — cached, retried, rate-limited TMDb calls
    flatten     stage 3 — nested JSON to one table per grain
    join        stage 4 — validated merges with indicator reports
    profile     stage 5 — profiling and fault detection
    clean       stage 6 — parameterised cleaning rules (flags, not deletions)
    kpis        stage 7 — grouped aggregations for both time windows
    timing      stage 8 — per-stage timings and the 500-title projection
    spotcheck   stage 9 — live re-fetch and discrepancy classification
"""

__version__ = "0.1.0"
