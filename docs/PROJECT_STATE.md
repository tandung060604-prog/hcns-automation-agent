# Project State

## Current checkpoint (2026-08-07)

Current milestone: `DATA-26-PARSER-RECOVERY` is implemented on the sealed
development split and remains `DONE / DEV HOLD` because the CV strict family
gate is not met. No DATA-24 rerun or held-out tuning is allowed.

Repository:
- Branch: `codex/data26-parser-recovery`
- HEAD: `efe8799` (DATA-25 implementation parent; update at commit checkpoint)
- Working tree changes are limited to DATA-26 code, tests and factual state docs.

DATA-26 changes are conservative: CV glued header boundary recovery, geometry
inference for a narrow full-width section heading, duration normalization, and
the development aggregate matching-policy selector. Schema, API, policy v2,
GroundTruth access rules and scan `MANUAL_REVIEW` policy are unchanged.

Private hybrid replay artifacts (outside Git):
- Prediction: `C:\\tmp\\bo10-dev-predictions-data26-parser-recovery-hybrid-v2-20260807.json`
- Aggregate: `C:\\tmp\\bo10-dev-aggregate-data26-parser-recovery-hybrid-v2-20260807.json`
- Gate: `C:\\tmp\\bo10-data26-gate-20260807.json`

Development aggregate: strict `101/112` (90.18%), accepted `111/112`, Contract
`42/42`, CV `39/50` (78%), IELTS `20/20`, applicable completeness `99/99`,
classification `12/12`, schema errors `0`, sensitive false acceptance `0`,
parser regression `0`, scan manual review `5/5`, false auto-continue `0`.
The only failed gate is CV strict; one scan experience field remains OCR
truncated. Accepted text does not replace strict EM, and no fallback/promotion
is eligible.

DATA-25 policy-v2 post-hoc audit remains non-promotional (`144/265` canonical,
`155/265` accepted). DATA-24 evaluate-once and GroundTruth remain immutable;
DATA-23 locks and the 10+5 IELTS split remain unchanged. DATA-27 is blocked
until a fresh held-out split is supplied and separately approved.

Validation: targeted Python `23 passed`, targeted Ruff passed, `py_compile` and
`git diff --check` passed; web `npm test` (13) and `npm run build` passed.

Next action: investigate the local OCR path for the remaining CV scan section
without using GroundTruth or changing the comparator. The unrelated global
task remains in `BACKLOG.md`.
Next READY task: `OCR-HO-V2-017B`.

Archive: `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md`.
