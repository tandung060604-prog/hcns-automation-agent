# Project State

Current milestone: OCR-HO-V2-017A CCCD secondary-runtime preflight checkpoint 2026-08-06; `DATA-20` DONE / HOLD
Documentation profile: Standard (`PROJECT_STATE.md`, `BACKLOG.md`, `HANDOFF.md`)

Checkpoint task: `OCR-HO-V2-017A` completed; runtime restored/verified, CCCD development gate HOLD.
Repository:
- Branch: `codex/data-18-cv-scan-recovery`
- HEAD: `13aa284`; unrelated OCR-HO WIP preserved.

Evidence summary:
- DATA-19 fresh aggregate: strict `90/112`, semantic `92/112`, accepted `105/112`;
  Contract `40/42` strict / `42/42` semantic, CV `30/50` strict/`45/50` accepted,
  IELTS `20/20`, classification `12/12`, schema `0`.
- Party extraction is bounded to `Bên A`/`Bên B`; fallback strips person prefix/role suffix
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

OCR-HO-V2-017A evidence: private runtime `C:\Camunda\private-data\paddleocr-hr-baseline\runtime`,
EasyOCR `1.7.2`, VietOCR `0.3.13`, CPU Torch; 6/6 model locks pass. Single-doc smoke:
16 crops, all 3 secondary profiles, runtime-only warnings. Artifact:
`C:\tmp\ocr-ho-v2-017a-preflight-20260806\preflight.log` plus private outputs; no source/primary change.
Next action: keep CCCD shadow/manual-review-only; no held-out/evaluate-once.
Next READY task: `OCR-HO-V2-017B` full 15/120 replay with restored secondary runtime.

Validation: targeted pytest `27 passed`; selected Ruff, compileall, `git diff --check` and
`scripts/validate_longrun_state.py` passed. Full-file Ruff retains baseline findings outside DATA-20.
Archive: `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md` preserves prior evidence.

## OCR-HO-V2-015/015A - 016A-R1/016B (DONE / HOLD)

- Sealed 15/120 diagnostics remain shadow-only: detector misses `0`, boundary
  misses fullName `7/15`, origin `6/15`, residence `13/15`; snapshot drift persists.
- 016A/016B parser-only candidates preserve manual review but remain below gates:
  AUTO exact `60.00%`, DER `14.62%`, presence `95.83%`, one exact regression;
  oracle ROI is `100%` but does not authorize promotion or held-out evaluation.
- Detailed replay artifacts remain in the private archive; no primary runtime or
  GroundTruth/evaluate-once artifact was changed.
