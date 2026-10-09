# Dead state in agentic execution: host-CPU microarchitecture characterization

Branch `dead-state`. Paper draft lives in Overleaf (project 6ac8aa85482474c388fdab8a); this directory
holds everything needed to regenerate its numbers and figures.

- `scripts/` — dbx Scarab patch (`dbx_patch.py`, `libs/dbx.{c,h}`), PPS unit selection, the LLC policy
  study runner (`run_sims.py`), the methodology-audit runner (`audit_sims.py`), table builder, figures.
- `data/` — LLC study results (160 PPS units x 6 LLC configs): `results.csv`, `summary.json`.
- `lit/` — literature notes: methodology survey (ISCA/MICRO), characterization style (Seshadri, Basu),
  prior work on agentic execution.
- `fig/` — paper figures.

Pod paths: study `/localdisk/deepanjm/deadblock/{sims,audit}`; Scarab `/localdisk/deepanjm/deadblock/scarab`.
