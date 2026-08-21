# Project State
Current milestone: DATA-31 QUALITY RECOVERY R7 / QUALITY HOLD
Checkpoint task: `DATA-31-QUALITY-RECOVERY-R7`
Next action: resolve the remaining Contract-004 dual-title Ground Truth boundary
Next READY task: `DATA-31-QUALITY-RECOVERY-R8`
Archive: docs/archive/PROJECT_STATE_HISTORY_2026-08-20.md

Repository:
- Branch: `codex/alg-003-contract-scan-recovery`
- HEAD: `88473de899518a4660ed7b3dc0c13dc66978eb6b`
- Base: `origin/main` at the same commit
- Existing WIP is preserved; no commit, push, PR or deploy was performed.

## Verified current result

- DATA-31 private R7 replay: 13/13 documents, Template-first + EasyOCR,
  parser `structured-hr/family-layout/2.2.8`, matching policy `2.1.0`.
- Scope: 109 active fields; 17 OUT_OF_SCOPE; 12 private IELTS semantic
  overrides; sealed Ground Truth and DATA-29 remain unchanged.
- Metrics: `104/109` strict, `108/109` accepted, `109/109` present,
  `schemaErrors=0`, parser regression `0`, sensitive false acceptance `0`.
- Gate: HOLD against `105/109` strict and `109/109` accepted.
- CAM-001 remains BLOCKED; no process, session or real side effect was created.

## Residual audit

- Rejected strict residual: 1 field; 4 other differences are accepted partial
  text.
- Contract 2: one dual-title policy conflict and one accepted workplace
  boundary difference.
- CV 3: accepted skills, desired-role and experience long-field differences.
- IELTS now reaches `20/20` strict, `20/20` accepted and `20/20` present after
  bounded label-crop recovery for short names and the score row.
- Contract is `42/44` exact and CV `42/45` exact. Three Contract title fields
  now use the general professional-title fallback when no role title exists;
  the fourth is a dual-title Ground Truth conflict. Four accepted residuals
  remain long-field OCR/layout differences. The private overlay corrects one
  independently verified malformed CV name without changing sealed Ground Truth.
- Fresh crop-gate baseline at `canvas=1280, mag=1.3, preprocess=none` reached
  `18/20` strict, `18/20` accepted and `19/20` present; 30/30 warm runs had
  no failures. Warm p95 was `18.800 s` total, `17.994 s` OCR and `1.263 GB`
  RSS.
- Hi-res `canvas=2560` produced no aggregate report after more than ten
  minutes; observed RSS peaked above `2.2 GB` and the run was stopped safely.
  It has no accuracy result and is `NOT PROMOTED`.
- R4 uses the existing EasyOCR backend with a bounded `label-crop-v1` fallback;
  it does not run a second full-document OCR pass or change the default canvas.
- R5 adds only a general CV rule: when the objective is a multi-line narrative,
  retain the complete objective instead of reducing it to a role fragment.
  This raised accepted coverage by one field but did not change strict exact.
- R6 applies Product/HR-approved semantic boundaries in matching policy `2.1.0`
  for gender suffixes, labels, bullets, ampersands and terminal punctuation.
- R7 adds parser `2.2.8`: `job_title` prefers `role_title` and falls back to
  `professional_title` only when the role title is absent; CV skills preserve
  an unlabelled `Phần mềm` value instead of dropping it as layout.
- Parser recovery is general and synthetic-tested; no document-specific value
  or Ground Truth was added. Private semantic IELTS overrides remain the source
  of truth for TRF/Form Number and certificate issue date.

## Validation

- Targeted parser/version/OCR/evaluation tests: `113 passed`; template version
  governance and compile passed; full Python suite: NOT MEASURED in this
  checkpoint. DATA-31 R7 replay completed with `schemaErrors=0`, parser
  regression `0` and sensitive false acceptance `0`.
- Repository hygiene and `git diff --check`: passed.
- Focused Ruff: passed. Full-file Ruff remains not clean because of 14 existing
  findings in the WIP external-prediction file.

## Next gate

The 1280 default remains active. DATA-31 remains HOLD at `104/109` strict and
`108/109` accepted; CAM-001 must not be reopened until `105/109` and `109/109`
both pass.
