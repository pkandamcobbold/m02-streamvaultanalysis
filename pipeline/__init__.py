"""StreamVault back-catalog licensing analysis.

Five stage modules, in the order run_pipeline.py calls them:

    config      settings.toml, the API token, and the constants stages share
    extract     the candidate list, the TMDb fetch, and the shaped tables
    validate    profiling, fault classification, and the cleaning flags
    transform   the proven join and every KPI table, both windows
    checks      the release gate, the live spot-check, and the time budget
    load        the generated memo and the improvement note

The reasoning behind every choice is in docs/adr/, one file per decision.
"""

__version__ = "0.2.0"
