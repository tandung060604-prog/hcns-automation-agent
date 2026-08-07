# Project State

## Current checkpoint (2026-08-07)

Current milestone: `DATA-26-PARSER-RECOVERY` is implemented on the sealed
development split and is `DONE / DEV HOLD`. The development gate passes; no
fallback or promotion is enabled, and no DATA-24 rerun or held-out tuning is
allowed.

Repository:
- Branch: `codex/data26-parser-recovery`
- HEAD: `3c2eeb349ccbc651b38d212142c57550c52a59b7` (DATA-26 local scan refinement checkpoint)
- Working tree changes are limited to DATA-26 code, tests and factual state docs.

DATA-26 changes are conservative: CV glued header boundary recovery, geometry
inference for a narrow full-width section heading, duration normalization, and
an opt-in local VietOCR line-refinement path for scan replay. Schema, API,
policy v2, GroundTruth access rules and scan `MANUAL_REVIEW` policy are
unchanged.

Private hybrid replay artifacts (outside Git):
- Prediction: `C:\\tmp\\bo10-dev-predictions-data26-parser-recovery-vietocr-20260807.json`
- Aggregate: `C:\\tmp\\bo10-dev-aggregate-data26-parser-recovery-vietocr-20260807.json`
- Gate: `C:\\tmp\\bo10-data26-gate-vietocr-20260807.json`

Development aggregate: strict `102/112` (91.07%), accepted `112/112`, Contract
`42/42`, CV `40/50` (80%), IELTS `20/20`, applicable completeness `99/99`,
classification `12/12`, schema errors `0`, sensitive false acceptance `0`,
parser regression `0`, scan manual review `5/5`, false auto-continue `0`.
The DATA-20 gate is `PASS`; fallback remains disabled because the fixed scan
subset improvement is `3.33pp`, below the required `10pp`. Accepted text does
not replace strict EM.

DATA-25 policy-v2 post-hoc audit remains non-promotional (`144/265` canonical,
`155/265` accepted). DATA-24 evaluate-once and GroundTruth remain immutable;
DATA-23 locks and the 10+5 IELTS split remain unchanged. DATA-27 is blocked
until a fresh held-out split is supplied and separately approved.

Validation: targeted Python `25 passed`, worker Ruff and `py_compile` passed;
web `npm test` (13) and `npm run build` passed on the unchanged web surface.

Next action: keep DATA-27 blocked until a fresh prediction-blind held-out split
is supplied and separately approved. The unrelated global task remains in
`BACKLOG.md`.
Next READY task: `OCR-HO-V2-017B`. DATA-27 remains blocked for this workstream
until its fresh corpus and approval blockers are cleared.

Archive: `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md`.
