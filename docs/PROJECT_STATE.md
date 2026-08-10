# Project State

## Current checkpoint (2026-08-10)

Current milestone: `DATA-27D-DEVELOPMENT-DELIVERY` is complete as a
development-only handoff. `DATA-26-PARSER-RECOVERY` remains `DONE / DEV HOLD`
with a passing development gate; no fallback or production promotion is
enabled.

Repository:
- Branch: `main`
- HEAD: `2ddd851` (`fix(web): keep legacy heldout flag out of rendered source`)
- Working tree was clean at checkpoint creation.

DATA-27A existing-pool audit is complete and `HOLD`. After SHA-256/history and
lineage exclusion, the available fresh counts are Contract `1`, CV `1`, and
IELTS `0`, below the required fresh held-out counts `10/10/5`. No new data is
required for this audit, but DATA-27 cannot claim an independent held-out gate
without either additional eligible data or an explicitly changed policy.

Development-only delivery artifact (aggregate, outside Git):
- `C:\\tmp\\data27d-development-delivery-20260810.json`

DATA-24 evaluate-once, GroundTruth and all raw private artifacts remain
immutable. DATA-27 fresh held-out generalization is `HOLD`; no evaluate-once
rerun is authorized.

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
DATA-23 locks and the original 10+5 IELTS split remain unchanged. DATA-27
fresh held-out generalization is blocked by the existing-pool audit.

Validation: targeted Python `25 passed`, worker Ruff and `py_compile` passed;
web `npm test` (13) and `npm run build` passed on the unchanged web surface.

Next action: use the DATA-27D development-only delivery for local review and
handoff. Do not create a held-out claim, rerun DATA-24, or promote a fallback.
The unrelated global task remains separately tracked in `BACKLOG.md`.

Archive: `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md`.
