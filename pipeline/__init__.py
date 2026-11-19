"""StreamVault back-catalog licensing analysis.

Five stage modules, in the order run_pipeline.py calls them:

    config      settings.toml, the API token, and the constants stages share
    extract/    ids, fetch, shape — the list, the API, the four tables
    validate/   profile, clean — the verdicts, then the flags
    transform/  join, kpis, bundles, talent — the proof, then the answers
    checks/     gate, spotcheck, budget — what must pass before publishing
    load        the generated memo and the improvement note

Four of the five stages are packages, one module per job (ADR-033). Each is
imported and called as though it were still a single module: the package
exposes the stage's entry point and its whole public surface, so no caller has
to know the difference.

The reasoning behind every choice is in docs/adr/, one file per decision.
"""

__version__ = "0.2.0"
