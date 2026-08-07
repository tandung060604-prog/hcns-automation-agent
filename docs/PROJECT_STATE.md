# Project State
Current milestone: OCR-HO-V2-018F CCCD recognizer/token attribution checkpoint 2026-08-07; `DATA-20` DONE / HOLD
Documentation profile: Standard (`PROJECT_STATE.md`, `BACKLOG.md`, `HANDOFF.md`)
Checkpoint task: `OCR-HO-V2-018F` recognizer/token evidence attributed; no selector, replay or patch authorized.
Repository:
- Branch: `codex/data-18-cv-scan-recovery`
- HEAD: `6883d68`; unrelated OCR-HO WIP preserved.
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
OCR-HO-V2-017C artifact: `C:\Users\HP\AppData\Local\Temp\ocr-ho-v2-017c-20260807\CCCD_OCR_HO_V2_017C_DER_ATTRIBUTION.json`;
scope is 15 documents / 45 target fields, `containsRawPII=false`, prediction remains sealed.
Canonical target classes: ROI `18`, recognizer `8`, parser `6`, selector `4`, diacritic `2`.
Profile oracle DER: VietOCR transformer `10.96%`, seq2seq `12.28%`; selected target DER `17.54%`.
Decision: 018B authorizationStatus=VALID_FOR_DEVELOPMENT_REPLAY; scope is 15/120 development-only.
Quality improvement is unproven; patch/replay remain denied.
Next action: review/run the authorized development replay; do not open held-out/evaluate-once.
Next READY task: `OCR-HO-V2-018G`; owner review is required before any selector counterfactual; keep primary runtime/held-out/evaluate-once closed.
Validation: 018B tests `3 passed`; Ruff, py_compile, artifact invariants, `git diff --check`, and
`scripts/validate_longrun_state.py` passed. Full-file Ruff retains baseline findings outside DATA-20.
Archive: `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md` preserves prior evidence.
## DATA-22..DATA-24 - revised corpus gate (2026-08-07)

- Private user-supplied inventories are available outside Git:
  `C:\tmp\data22-user-contract-cv-20260807-inventory.json` (28 Contract,
  30 CV) and `C:\tmp\data22-user-ielts-20260807-inventory.json` (15 IELTS
  images). The IELTS gate is now 10 development + 5 held-out; DATA-17's
  historical IELTS `20/20` remains unchanged.
- DATA-22 split policy and validators are implemented, with scans fixed to
  `MANUAL_REVIEW` and masked fields represented as absent (`null`) for scoring.
  The current private candidate is `HOLD`: eight candidate documents overlap
  the prior image-expansion history by SHA-256, so they cannot be reused as
  independent development data.
- DATA-23 lock validation and DATA-24 create-only evaluator are implemented
  with synthetic regression coverage. Neither held-out locks nor evaluate-once
  artifacts have been opened or created.

## OCR-HO-V2-015/015A - 016A-R1/016B (DONE / HOLD)
- Sealed 15/120 diagnostics remain shadow-only: detector misses `0`, boundary
  misses fullName `7/15`, origin `6/15`, residence `13/15`; snapshot drift persists.
- 016A/016B parser-only candidates preserve manual review but remain below gates:
  AUTO exact `60.00%`, DER `14.62%`, presence `95.83%`, one exact regression;
  oracle ROI is `100%` but does not authorize promotion or held-out evaluation.
- Detailed replay artifacts remain in the private archive; no primary runtime or
  GroundTruth/evaluate-once artifact was changed.
## OCR-HO-V2-017D..017J - selector, ROI and profile review (DONE / HOLD)
- 017D worsened DER; 017E/017F made no switch; 017H had no global 50% boundary cause; 017I/017J kept HOLD.
## OCR-HO-V2-017K..017M - line/token cohort evidence (DONE / HOLD)
- 017K recognizer disagreement `291/630`; 017M separated AUTO_REGION_MISS line IDs from AUTO_REGION_HIT recognizer errors.
## OCR-HO-V2-017N..017P - residence boundary evidence (DONE / HOLD)
- Global bottom boundary `8/18`; residence `3/5`; geometry cases share one band, overflow `2/3`, line-ID overlap `0`.
## OCR-HO-V2-017Q - minimal boundary-rule review (DONE / HOLD)
- Artifact: `C:\Users\HP\AppData\Local\Temp\ocr-ho-v2-017q-20260807\CCCD_OCR_HO_V2_017Q_RESIDENCE_GEOMETRY_MINIMAL_BOUNDARY_RULE_REVIEW.json`; aggregate-only, sealed.
- Candidate: bottom-only extension capped at `15` pixels, preserve `maxValueLines=2`, no line-ID remap; `patchAuthorized=false`, `replayAuthorized=false`.
- Gates HOLD, schema/sensitive/accepted `0`, manual review; Next READY: `OCR-HO-V2-017R`.
## OCR-HO-V2-017R - patch-gated review (DONE / HOLD)
- Artifact: `C:\Users\HP\AppData\Local\Temp\ocr-ho-v2-017r-20260807\CCCD_OCR_HO_V2_017R_RESIDENCE_GEOMETRY_PATCH_GATED_REVIEW.json`; bounded rule PASS, line-ID evidence HOLD; patch/replay denied.
## OCR-HO-V2-017S - independent line-ID mapping evidence (DONE / HOLD)
- Artifact: `C:\Users\HP\AppData\Local\Temp\ocr-ho-v2-017s-20260807\CCCD_OCR_HO_V2_017S_INDEPENDENT_LINE_ID_MAPPING_EVIDENCE.json`; source `15/15`, overlap `61/61`; diagnostic-only, patch/replay denied.
## OCR-HO-V2-017T - patch-gate reconciliation (DONE / HOLD)
- Artifact: `C:\Users\HP\AppData\Local\Temp\ocr-ho-v2-017t-20260807\CCCD_OCR_HO_V2_017T_PATCH_GATE_RECONCILIATION.json`; rule/evidence PASS, quality unproven; explicit approval required.
## OCR-HO-V2-017U - explicit patch authorization review (DONE / HOLD)
- Artifact: `C:\Users\HP\AppData\Local\Temp\ocr-ho-v2-017u-20260807\CCCD_OCR_HO_V2_017U_EXPLICIT_PATCH_AUTHORIZATION_REVIEW.json`; authorization record missing; patch/replay denied; Next READY: `OCR-HO-V2-017V`.
## OCR-HO-V2-017V - authorization-record intake (DONE / HOLD)
- Artifact: `C:\Users\HP\AppData\Local\Temp\ocr-ho-v2-017v-20260807\CCCD_OCR_HO_V2_017V_AUTHORIZATION_INTAKE.json`; status `VALID_FOR_PATCH_REVIEW`; patch/replay denied.
- 017W surface `PASS`; 017X held guard placement; 017Y resolved insertion; Next READY: `OCR-HO-V2-017Z`.
## OCR-HO-V2-018F - recognizer/token attribution (DONE / HOLD): artifact `C:\Users\HP\AppData\Local\Temp\ocr-ho-v2-018f-20260807\CCCD_OCR_HO_V2_018F_RECOGNIZER_TOKEN_ATTRIBUTION.json`; AUTO_REGION_HIT recognizer disagreement `291/375 = 77.6%`, token mismatch `11`, line-order mismatch `72`; no selector, replay or patch; Next READY: `OCR-HO-V2-018G` owner review.
