# Project State
## DATA-29 full explorer + three-family Camunda bridge (2026-08-13)

- Evidence Explorer no longer loads or renders private upload-session history.
  DATA-29 now exposes all 12 metric-linked sources through Contract `3`, CV `5`
  and IELTS `4` filters while retaining aggregate `107/112` exact and `112/112`
  accepted from the pinned report.
- Dashboard start allows `CV`, `CERTIFICATE` and `EMPLOYMENT_CONTRACT` alongside
  Leave/Overtime. The request sends only application ID, session UUID and declared
  type. `HCNS_CAMUNDA_PRIVATE_ROOT` must resolve to the dashboard `DataRoot`.
- `GET /api/camunda/case?id=...` exposes only process/type/state/current-task/
  incident metadata. The upload result shows processing, human-review, reupload,
  completed, rejected and incident states without exposing document values.
- Shadow policy remains unchanged: `autoContinueEnabled=false`, real HRIS and
  notification side effects disabled. Production promotion remains out of scope.
- Final validation: Python `543 passed`; Camunda/Template subset `60 passed`;
  web build and rendered-contract tests `14/14`; mypy passed for 90 source
  files; Ruff gates, compileall, repository hygiene and diff check passed.
  ESLint has zero errors and retains 23 pre-existing warnings.
- Live Camunda 7.13 local shadow completed one authorized CV process
  (`9c1d6b81-96d5-11f1-9d8f-2e6dc137b103`) and one authorized IELTS process
  (`9d181e50-96d5-11f1-9d8f-2e6dc137b103`). Both required HR Review, ended
  `COMPLETED`, recorded one review audit, and had zero incidents. Each produced
  one result and one idempotency record; HRIS and notification remained
  `SIMULATED`, and `autoContinueEnabled=false`.
- Contract live acceptance is still open because the authorized private root
  currently contains one CV and one IELTS upload but no probation-contract
  upload. DATA-29 is not substituted for this user-upload acceptance step.

## DATA-29 metric-linked document showcase (2026-08-13)

- Template-first upload now follows the frozen manifest at both UI and API
  boundaries: CV/probation contract accept DOCX/PDF; IELTS and CCCD accept
  PDF/PNG/JPG/JPEG. The detected template is checked against its own allowed
  file types before extraction continues.
- A local-only comparison route stores reviewer-entered Ground Truth beside the
  private Template-first session and applies matching policy v2. The workspace
  shows source, Prediction, Ground Truth, confidence/evidence, field badges,
  exact/wrong counts and a HOLD/PASS comparison decision. Promotion remains
  disabled independently of the comparison decision.
- The default evidence tab now opens four exact DATA-29 source documents: one
  Contract PDF, one CV PDF text, one CV PDF scan and one IELTS image. It shows
  4/12 while retaining the full aggregate `107/112` strict and `112/112` accepted.
- Per-document comparison derives matching policy `2.0.0` from the pinned report.
  Displayed cases reproduce `14/14`, `9/10`, `9/10` and `5/5` strict respectively.
- DATA-29 is explicitly labeled a development corpus. Independent
  uploaded sessions remain available but no longer stand in for the metric corpus.
- Final validation: Python full suite `540 passed`; frontend build and
  rendered-contract test `14/14`; mypy passed for 90 source files; repository
  hygiene, compileall and diff check passed. ESLint has zero errors and retains
  23 pre-existing warnings outside this delivery.
- Delivery branch: `codex/localhost-comparison-showcase`, targeting `main`.

Older entries below are retained as an audit trail only. Their evidence is not
loaded unless it belongs to the pinned DATA-29 chain described above.

## Codebase review repair track - pipeline/hygiene consolidation DONE (2026-08-12)
- The repository hygiene checker now inspects only Git-tracked paths through
  `git ls-files`; local worktrees, scratch output and private data are never
  traversed. `.worktrees/`, `output/` and `tmp/` are ignored, and the app README
  now matches CI's canonical `python -m pytest -q` command.
- The one cwd-dependent API test path was made repository-root relative. No
  duplicate runtime pipeline was introduced; `build_default_pipeline` remains
  the single composition entrypoint for the default intake plus understanding
  services.
- Validation: repository checker, touched-file Ruff, focused OCR test
  (`4 passed`), ignore checks and `git diff --check` passed. Final full-suite
  validation: Python `527 passed`; tracked-file Ruff, mypy (90 source files),
  compileall, repository checker and `git diff --check` all passed. Web `npm test`
  passed 14/14 and `npm run lint` passed with 23 warnings, zero errors.
- Root `README.md` now presents VinHRIS as a product: current capabilities,
  latest hardening changes, local setup, verified evidence, safety boundaries and
  production limits are separated for users, mentors and engineers.
- Delivery branch: `codex/codebase-hardening-readme`, targeting `main`.
  PDF/R-003 remains intentionally out of scope.
- GitHub CI exposed six legacy tests that hard-coded `C:/tmp`; their synthetic
  fixtures now use platform temporary directories so Python 3.10/3.12 jobs run
  consistently on Linux and Windows.

## Codebase review repair track - R-011 DONE (2026-08-12)
- Rendered landing-page contract tests now assert the current Vietnamese VinHRIS
  metadata and hero copy used by the local workspace UI; stale pre-redesign title
  assertions were removed.
- Validation: web `npm test` passed (`14/14` rendered-contract tests); `npm run lint`
  passed with 23 existing warnings and zero errors.
- Next READY: consolidate pipeline/import/path hygiene findings.

## Codebase review repair track - R-012 DONE (2026-08-12)
- Lazy PaddleOCR and EasyOCR template delegates now initialize under a per-engine
  lock, so concurrent first requests create exactly one backend instance while
  preserving the existing lazy-loading and error translation behavior.
- Regression coverage: eight concurrent recognition calls for each backend share
  one initialized delegate. Validation: targeted template tests `24 passed`,
  touched-file Ruff and compileall passed, and `git diff --check` passed.
- Next READY: R-011 web rendered-contract mismatch.

## Codebase review repair track — R-005 DONE (2026-08-12)
- Local JSON result stores now serialize idempotency commits and correction writes
  with a stdlib cross-process file lock; the check-then-write race no longer permits
  competing result/index updates for one idempotency key.
- Regression coverage: concurrent generic result retries keep one artifact; concurrent
  Template-first idempotency collisions produce one stored result and one rejection.
- Validation: targeted `pytest` 20 passed; touched-file Ruff passed; `git diff --check`
  passed. Next READY: R-007 dashboard local-boundary hardening.

## Codebase review repair track — R-007 DONE (2026-08-12)
- Dashboard requests now require a loopback Host header; non-local Host values are
  rejected before route handling. Camunda review/start JSON bodies are capped at the
  existing 2 MB review limit and return `413` when invalid or oversized.
- Regression coverage: Host parser unit cases, hostile Host HTTP request, and oversized
  Camunda JSON request. Validation: 14 targeted tests, helper/test Ruff, dashboard
  `E9,F`, compileall and `git diff --check` passed.
- Full dashboard lint retains pre-existing import-order/E402/E501 findings; no hygiene
  cleanup was folded into this security task. Next READY: R-006 CI test discovery.

## Codebase review repair track — R-006 DONE (2026-08-12)
- CI now runs `python -m pytest -q`, so pytest-style tests are collected alongside
  existing unittest-style cases; the prior `unittest discover` command missed them.
- Validation: CI-equivalent full Python suite `525 passed`; targeted security/store
  checks remained green; `git diff --check` passed. Next READY: R-012 OCR lazy-engine
  thread safety.

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
