# Project State
## Canonical Template contract v2 (2026-08-11)
- CV, probation contract and IELTS now emit v2 template ids with the benchmark's
  snake_case fields; v1 local result files remain readable through a pure
  compatibility projection and are not rewritten.
- The latest aggregate DATA-29 evidence is display-only: strict `107/112`
  (Contract `42/42`, CV `45/50`, IELTS `20/20`), decision `HOLD`, and
  `promotionAllowed=false`. No raw Ground Truth/prediction values are exposed
  by the API or UI.
- Manifest, registry, v2 JSON schemas and UI field labels are parity-checked;
  leave/OT/CCCD template ids remain unchanged.

## Current local Camunda dataset
- Approved local source: `D:\HR_OT_Leave_Request_Dataset` (private, never committed).
  It contains 30 native documents: 15 Leave Request and 15 Overtime Request.
- Leave Request template v1.0 and Overtime Request parser v1.1.0 were checked
  against all 30 documents: correct template selection 30/30, validation errors
  0/30, and `AUTO_CONTINUE` eligibility 30/30. The Overtime parser now accepts
  both multi-day and single-day `Ngay ... lam/tang them ... gio` wording.
- Local Camunda uses this dataset only through opaque private session references.
  It stays shadow-only (`autoContinueEnabled=false`): every case stops at a human
  review task; no business side effect is performed automatically.

Current milestone: OCR-HO-V2-019L CCCD package-absence checkpoint completed 2026-08-10; `DATA-20` DONE / HOLD
Documentation profile: Standard (`PROJECT_STATE.md`, `BACKLOG.md`, `HANDOFF.md`)
Checkpoint task: `OCR-HO-V2-019L` reconfirmed no independent package/lock exists and kept replay/evaluate-once/selector/runtime/promotion closed; no GroundTruth was created or opened.
Repository:
- Branch: `codex/data-18-cv-scan-recovery`
- HEAD: `ac15756`; unrelated OCR-HO WIP preserved.
Evidence summary:
- DATA-19 fresh aggregate: strict `90/112`, semantic `92/112`, accepted `105/112`;
  Contract `40/42` strict / `42/42` semantic, CV `30/50` strict/`45/50` accepted,
  IELTS `20/20`, classification `12/12`, schema `0`.
- Party extraction is bounded to `Ben A`/`Ben B`; fallback strips person prefix/role suffix
  while preserving source characters. Scan remains `MANUAL_REVIEW`-only: 5/5, false auto `0`.
- GroundTruth and old evaluate-once are unchanged; all reports/predictions remain private.
- DATA-20 gate aggregate v4: strict `90/112`, semantic `92/112`, applicable completeness
  `99/99`, sensitive false acceptance `0`, parser-correct regressions `0`, schema `0`,
  classification `12/12`, scan strict `27/30`, scan manual-review `5/5`; strict CV family
  gate and fallback scan `+10pp` gate remain HOLD. Gate report is private and aggregate-only.
- DATA-20 artifacts: `C:\tmp\bo10-dev-aggregate-data20-regression-gates-v4.json`,
  `C:\tmp\bo10-dev-data20-gate-report-v4.json` and their markers; evaluate-once untouched.
## DATA-21 - PaddleOCR-VL local benchmark (DONE / HOLD)
- The private runner and synthetic coverage are implemented. The public pin
  `PaddleOCR-VL-1.6` resolves in PaddleOCR 3.7 to runtime model
  `PaddleOCR-VL-1.6-0.9B`; model/package/runtime hashes are recorded privately.
- CPU-first initialization downloaded the 1.93 GB model tree but exceeded the
  local initialization budget before the first scan completed. This is a runtime
  HOLD, not a quality PASS; no fallback or promotion was enabled.
- Private aggregate-only report/marker:
  `C:\tmp\bo10-data21-paddleocr-vl-benchmark-report-v5.json` and
  `C:\tmp\bo10-data21-paddleocr-vl.marker-v5.json` (`processedCount=0`,
  `failureRate=1.0`, `promotionAllowed=false`, `evaluateOnceArtifactTouched=false`).
  Raw model/runtime cache remains outside Git.
- Approved rerun used a 600-second CPU window with the same private cache. GPU was
  unavailable because the installed Paddle wheel is CPU-only; the native worker
  exited `1` after weight load before pipeline initialization. Rerun report/marker:
  `C:\tmp\bo10-data21-paddleocr-vl-benchmark-report-v8.json` and
  `C:\tmp\bo10-data21-paddleocr-vl.marker-v8.json`; quality metrics remain `null`.
- DATA-22 remains BLOCKED by approved source rights/retention and the minimum
  corpus; no held-out split or evaluate-once was opened.
OCR-HO-V2-017C artifact: `C:\Users\HP\AppData\Local\Temp\ocr-ho-v2-017c-20260807\CCCD_OCR_HO_V2_017C_DER_ATTRIBUTION.json`; scope is 15 documents / 45 target fields, `containsRawPII=false`, prediction remains sealed.
Canonical target classes: ROI `18`, recognizer `8`, parser `6`, selector `4`, diacritic `2`.
Profile oracle DER: VietOCR transformer `10.96%`, seq2seq `12.28%`; selected target DER `17.54%`.
Decision: 018B authorizationStatus=VALID_FOR_DEVELOPMENT_REPLAY; scope is 15/120 development-only.
Quality improvement is unproven; patch/replay remain denied.
Next action: review the validated residence cross-tab ceiling and choose a bounded non-selector diagnostic; do not open held-out/evaluate-once.
Next READY task: `OCR-HO-V2-019M`; wait for a complete independent package/lock before any replay review.
Validation: 019L included in relevant OCR-HO suite `163 passed`; touched-file Ruff, API compileall, `scripts/validate_longrun_state.py`, and `git diff --check` passed. Full-file Ruff retains baseline findings outside DATA-20.
Archive: `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md` preserves prior evidence.
## Historical OCR-HO status (DONE / HOLD)

- Detailed checkpoints through OCR-HO-V2-019L are preserved in
  `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md` and `docs/HANDOFF.md`.
- The OCR-HO workstream remains shadow-only: no selector, replay, runtime,
  held-out/evaluate-once or promotion action is open. Next READY remains
  `OCR-HO-V2-019M`, pending a complete independent package/lock.
