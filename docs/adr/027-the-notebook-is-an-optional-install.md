# ADR-027: The notebook is an optional install, separate from the pipeline's requirements

**Status:** Accepted · **Date:** 2026-11-19 · **Deciders:** Data team

## Context
The clean-clone test failed: `pip install -r requirements.txt` built nothing, because `jupyter`
transitively requires PyYAML, which has no Python 3.15 wheel and cannot compile from source here
(F19). An earlier check had passed because it resolved `jupyter` **alone**, where pip selects an
older jupyterlab that predates the dependency. This decides whether the project installs at all.

## Decision
Move `jupyter` to an optional `requirements-notebook.txt` that the pipeline does not need. The
analysis produces every artefact without it.

## Alternatives considered
- **Pin jupyterlab and jupyter-server to older versions** that avoid the offending dependency —
  pins two transitive packages to versions pip does not want, which breaks again the next time
  anything else moves.
- **Drop the notebook entirely** — discards the narrative that the deliverable shape calls for
  (Q11).

## Consequences
- `pip install -r requirements.txt` completes in **78 seconds, wheels only**, and installs 10
  packages instead of about 100.
- The notebook is one extra command, and `requirements-notebook.txt` says plainly that it may fail
  on Python 3.15 and that the pipeline is unaffected if it does.
- Verified end to end in a fresh clone: install, import with no path manipulation, the full test
  suite passing, and the no-token path giving instructions rather than a traceback.
- A reader who wants the notebook has to run a second command and may hit the same wall. That is a
  documented inconvenience for one optional artefact; the alternative was a repository that could
  not be installed at all.

## Revisit when
PyYAML ships a wheel for the Python in use, or the pinned pandas and numpy versions stop supporting
the Python the README claims. The current pins require **3.12 or newer**, which is stricter than the
3.10 the README and project metadata state — an open inconsistency to close.
