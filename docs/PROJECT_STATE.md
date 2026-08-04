# Project State

Current milestone: TF-P2-005 DONE; evidence-driven OCR backend selection passed UAT
Documentation profile: Standard (`PROJECT_STATE.md`, `BACKLOG.md`, `HANDOFF.md`)

Completed:
- Universal intake, Canonical Document, safety, native/OCR routing and quality contracts
- Generic multi-family pipeline retained as legacy-compatible behavior
- Camunda 7 worker/assets and process-variable whitelist
- Registered `leave-request-v1` and `overtime-request-v1`
- Content detection is normalized, filename-independent and closed-set
- DOCX/native PDF parse without OCR; image/PDF scan use a local, explicitly selected OCR backend
- Per-template extraction, validation, JSON Schema and quality routing
- Multi-format `GET /api/templates` and `POST /api/documents/process`
- One default upload surface with image/PDF preview beside structured fields/JSON
- Session-scoped source retention and loopback-only `GET /api/documents/source`
- Local evidence preview uses `GET /api/documents/preview`; PDFs render their first page
  through the existing local PDFium dependency so the browser never shows a blank iframe
- Private result JSON; Camunda receives only scalar metadata/reference
- README foregrounds the two forms while preserving legacy OCR/IDP documentation

TF-P2-002 evidence (2026-07-31):
- Accepted: `.docx`, `.pdf`, `.png`, `.jpg`, `.jpeg`
- DOCX: 10/10 classification, 90/90 required fields, 0 schema errors
- Native PDF: 10/10 classification, 90/90 required fields, 0 schema errors
- Six camera images: 6/6 processed/classified, 31/54 required fields, 0 schema errors
- Six in-memory image PDFs: same 6/6 and 31/54 result
- Every OCR source routes `MANUAL_REVIEW`; false `AUTO_CONTINUE` count is zero
- API/UI expose source format, parser, OCR engine/use and confidence
- Missing OCR runtime is explicit; OCR processing failure has a separate code
- Camera preprocessing rectifies page perspective and applies local contrast
- Aggregate evaluator does not log field values or add dataset/PII to Git
- Manifest declares 30 files but contains 26 and 10 stale image references
- Approved OCR exact-match gate remains open: 57.41% versus 80%

Preserved OCR evidence:
- CCCD Phase 11.5 dev (15): EM 60.00%, CER 43.60%, DER 12.65%; SHADOW
- CCCD Phase 11.6 replay (15): EM 60.00%, zero regression
- Held-out v1 has 9 new images and remains below the 15-document gate
- Phase 16 evaluate-once: classification 77.78%, Field EM 13.00%; NOT_PROMOTED
- Phase 17 live-v5: 15 docs; Field EM 14.63%, completeness 24.39%

Architecture:
- Native: DOCX/PDF -> safety -> native parser -> registry -> validator
- OCR: image/scan -> rectify -> selected local recognizer -> registry -> validator -> review
- IDP reads; Agent proposes; Camunda owns workflow and Human Review
- Unsupported templates never fall through to the generic extractor
- Raw documents/full payloads remain behind local references

Local runtime checkpoint:
- UI: `http://localhost:3000`; API: `http://127.0.0.1:8765`
- API was restarted from `.venv` after the preview change; web remains on `localhost:3000`;
  health returns `ok`
- Live camera upload returned `LEAVE_REQUEST` / `MANUAL_REVIEW`; smoke session deleted
- UX smoke trên desktop xác nhận một vùng upload, ảnh preview sticky cạnh metadata/JSON;
  PDF/PNG source round-trip khớp SHA-256 và các session smoke đã xóa
- Loopback development runtime only; no production deployment or HRIS side effect
- Template-first is the only default upload surface; legacy OCR/IDP is preserved
  behind `VITE_SHOW_LEGACY_UPLOAD=true`
- Mentor view hides held-out unless `VITE_SHOW_HELDOUT=true`
- Evidence retains Template-first/CCCD and the right metadata/JSON panel
- Hero uses the approved local workflow infographic; no remote asset is loaded
- Weekly report 2026-W31 includes two local evidence screenshots, two user-declared
  synthetic CCCD UI screenshots with Prediction JSON, and six input/result pairs from
  AI-generated HR forms; no real PII is tracked

Security:
- No dataset, Ground Truth, upload, model weight, secret or raw PII added to Git
- Regression reads the approved local synthetic set and reports aggregates only
- No cloud OCR/API call; server bind remains loopback

Known limits:
- Native DOCX/PDF pass; photographed/scanned text remains shadow-review quality
- EasyOCR candidate still leaves a bounded set of low-confidence fields for human review;
  it is opt-in and does not change the PaddleOCR default
- OCR sources remain `MANUAL_REVIEW`; candidate promotion does not enable automatic continuation
- Seven old overtime Ground Truth `department` labels do not occur in source DOCX
- Phase 11.6/CCCD WIP remains uncommitted and outside this task

TF-P2-002A checkpoint (2026-08-01):
- Approved six-image subset remains 6/6 classified, 0 schema errors, 6/6
  `MANUAL_REVIEW`, and 0 false `AUTO_CONTINUE`.
- Bounded template ROI evidence, geometry-aware label parsing, conservative
  vocabulary repair, and field-level provenance are implemented for both forms.
- Latest image rerun is 41/54 required exact fields (75.93%) and scan-PDF rerun
  is 36/54 (66.67%); the 80% gate is still open. Remaining aggregate mismatches
  are dynamic Vietnamese names, reason text, and overtime work-content text; no
  Ground Truth/native twin is used at runtime.
- Evaluator now classifies field failures as `ABSENT_IN_SOURCE`,
  `OCR_NOT_RECOGNIZED`, `OCR_RECOGNIZED_PARSER_MISSED`, or
  `VALIDATION_REJECTED` without writing field values to reports.

TF-P2-003A status (2026-08-01):
- DONE and pushed to `origin/main` at commit `ae93bf0`.
- Version governance freezes v1, validates schema/parser pairing and provides the
  four-format UAT matrix; it unblocked TF-P2-003B after the OCR gate opened.

TF-P2-002B DONE (2026-08-01):
- Objective: evaluate Vietnamese OCR candidates and recover only the remaining
  image/scan fields without Ground Truth/native twins or hardcoded document values.
- Scope: 4 dynamic names, 6 `reason`, 3 `workContent`; scan PDFs also include
  `department` and `jobTitle`.
- Implemented an optional EasyOCR Vietnamese backend, geometry-safe line grouping,
  conservative OCR artifact repair, and label/continuation parsing for the two templates.
- Locked six-document image rerun: 48/54 required exact (88.89%), 6/6
  classification, 0 schema errors, 6/6 `MANUAL_REVIEW`, and 0 false `AUTO_CONTINUE`.
- Locked six-document scan-PDF rerun: 45/54 required exact (83.33%), 6/6
  classification, 0 schema errors, 6/6 `MANUAL_REVIEW`, and 0 false `AUTO_CONTINUE`.
- Native regression remains 90/90 for DOCX and 90/90 for native PDF, with 0 schema
  errors. Reports contain aggregate metrics only (`containsRawFieldValues: false`).
- At the TF-P2-002B checkpoint PaddleOCR remained the default; the backend policy
  was revisited and changed only after the TF-P2-005 UAT evidence below.

TF-P2-003B DONE (2026-08-01):
- Frozen version governance passed: `validate_template_versions.py` reports PASS;
  registry, schema, parser versions, lifecycle and UAT policy are consistent.
- Fail-closed mismatch coverage passed in the versioning test suite; parser/schema
  drift is rejected before evaluation.
- Full UAT matrix passed with 10 available/processed items in each format:
  DOCX 90/90 and native PDF 90/90 required exact; image 82/90 (91.11%); scan PDF
  77/90 (85.56%).
- Classification is 10/10 for all four formats, schema errors are 0, and all OCR
  items route to `MANUAL_REVIEW` with 0 false `AUTO_CONTINUE`.
- Dataset integrity is clean for this run: 30 actual files, 30 references, 0 stale
  references, 10 linked images. The report has `containsRawFieldValues: false`.
- Runtime pairing recorded `docx/ooxml-native@1.0.0`, `pdf/pymupdf-native@1.0.0`,
  `image/ocr@1.0.0`, `pdf/scan-ocr@1.0.0`, and `easyocr/vi-greedy`.

TF-P2-004 evidence (2026-08-02):
- Commit `655f51c` adds a generic leave-reason boundary repair when OCR places the
  period sentence and the fixed reason label in one line; it does not use Ground
  Truth, native twins, or document values. Targeted tests: 19 passed.
- The explicitly probed Paddle `PP-OCRv5_mobile_rec` candidate reached 21/54
  required exact on locked images and 21/54 on locked scan PDFs. Classification
  was 6/6, schema errors 0, OCR review 6/6, and false `AUTO_CONTINUE` 0; it is
  rejected and was not promoted.
- A second explicit `PP-OCRv5_server_rec` image probe reached 17/54, so it is
  also rejected without a scan run.
- EasyOCR remains opt-in and reran at 50/54 on images and 48/54 on scan PDFs;
  both runs passed classification, schema, review-routing, and false-auto gates.
- Paddle candidates remain rejected for this template set. VietOCR was not
  installed or switched into this route; adding its runtime is a separate
  dependency/benchmark decision.

TF-P2-005 evidence (2026-08-02):
- EasyOCR `vi-greedy` is now the Template-first default for image/PDF-scan OCR;
  PaddleOCR remains an explicit rollback via `HCNS_TEMPLATE_OCR_BACKEND=paddle`.
- Full default UAT passed: DOCX 90/90, native PDF 90/90, image 86/90 (95.56%),
  and scan PDF 82/90 (91.11%). All four formats classified 10/10; schema errors
  0; all 20 OCR items routed to `MANUAL_REVIEW`; false `AUTO_CONTINUE` 0.
- Default runtime report identifies `easyocr/vi-greedy`, has clean dataset
  integrity (30 files/references, 0 stale), and `containsRawFieldValues=false`.
- CPU latency probe over six images and six scan PDFs measured p95 23.5s/image
  and 22.6s/scan PDF; the local EasyOCR model cache is 93.99 MiB.
- Explicit Paddle rollback smoke passed classification/schema/review gates on one
  image and reported `paddleocr/pp-ocrv5-vi`.

External dataset DATA-00..DATA-05 checkpoint (2026-08-02):
- Source is pinned to commit `dec17acbe2b409e0aa5daeb4db820d3e95d05bdf` and staged
  outside Git; README and generator scripts are excluded from inventory.
- Inventory is 13 documents / 17 pages with digest
  `sha256:fef7fb1b09e253536d7734bbe5369675fc5621b69eed5ec4fb1ad68d4e7cc0ec`.
- Folder-derived contract mapping covers CV, employment contract and certificate;
  all three remain on `GENERIC_IDP`, never Template-first v1.
- Native UTF-8 TXT parsing and certificate/short-contract classification are
  versioned; mapping and inventory drift validators fail closed.
- EasyOCR `vi-greedy` pilot processed 13/13 with 0 failures; folder-derived
  classification matched 12/13. Report is aggregate-only and contains no raw
  OCR/field values; quality counts are PASS 2, REVIEW_REQUIRED 6, REJECTED 5.
- The user-directed synthetic/public profile is `PUBLIC` + `APPROVED`; the
  aggregate report keeps promotion `HOLD` because independent Ground Truth is
  absent and the corpus is below the 30-page benchmark minimum.
- Pilot reason reporting is conditional on inventory governance; an approved
  public profile no longer reports a false authorization HOLD reason.
- Tracked artifacts: `config/external_dataset_mapping.json`,
  `schemas/external_dataset_inventory.schema.json`,
  `schemas/external_dataset_mapping.schema.json`, and the inventory/pilot
  scripts plus synthetic contract tests. Raw documents, inventory JSON and
  EasyOCR models remain outside the repository.
- Final validation for this checkpoint: `pytest` 239 passed; Ruff, mypy,
  compileall, `check_repository.py` and `git diff --check` passed.

External dataset DATA-06 checkpoint (2026-08-02):
- Certificate mapping is versioned through
  `schemas/hr_document_families/certificate.schema.json`; mapping status is
  `groundTruthStatus=DRAFT` and promotion remains disabled.
- A prediction-blind Ground Truth review artifact exists outside Git at
  `C:\tmp\hcns-dataset-run-dec17acb-ground-truth-draft.json`.
- The pre-contract-replacement draft covered 13 cases / 17 pages and 55
  expected fields; it was moved to a timestamped backup outside the staging
  root before the new contract source was installed.
- DATA-06 remains `IN_PROGRESS` until an independent reviewer confirms and
  seals the source-document values; only then may field-level evaluation run.

External dataset DATA-07 checkpoint (2026-08-03):
- DATA-07 was approved and the local review UI/API is implemented for the
  current synthetic external dataset: 12 documents / 16 pages and 86 fields.
  CV/IELTS remain unchanged (30 fields total); four contract cases use the
  reduced 14-field probation schema (56 fields total).
- The queue exposes source previews for image/PDF/TXT and native text previews
  for DOCX/PPTX, plus a dynamic field form for CV, contract and IELTS.
- API writes the private draft atomically outside Git and refuses `SEALED`
  until all fields are `CONFIRMED`; prediction/OCR output is never read by the
  review module.
- The old staged contract directory was moved to
  `C:\tmp\hcns-dataset-run-dec17acb-contract-old-20260803` (recoverable),
  and the new DOCX/PDF contract sources remain only in local staging.
- Inventory digest is
  `sha256:d1076de9fcfc675e881f4d5e2370765971974c779cfb9affb9faf926e3f9cb33`.
  The prediction-blind draft remains `DRAFT` / `IN_PROGRESS`; no field values
  were copied from OCR output. Mock pilot processed 12/12 with 0 failures and
  decision `HOLD`.
- Validation: targeted review tests 10 passed; full Python suite 249 passed plus
  16 subtests; Ruff and mypy passed. Web build/render tests pass; the existing
  Dashboard lint error is
  unrelated WIP.
- Runtime command: `apps/ocr_lab/api/start_dashboard.ps1 -DataRoot <data-root>
  -ExternalDatasetRoot C:\\tmp\\hcns-dataset-run-dec17acb` (inventory and draft
  paths infer from the staging root name).

External dataset DATA-08 checkpoint (2026-08-03):
- Scope is limited to independent review of the four canonical contract cases:
  two DOCX and two native-text PDF sources, 14 fields each (56 fields total).
  The two full-document PNG previews remain excluded as derivative duplicates;
  real-world contract image inputs are explicitly deferred.
- The review UI now defaults to the contract scope, keeps CV/IELTS selectable
  separately, renders PDF_TEXT and PDF_SCAN previews in an iframe, and labels
  the gate as a whole-dataset `SEALED` action.
- Current queue evidence: contract-001..004 are all `PENDING`, 0/56 reviewed;
  predictions remain hidden, `groundTruthStatus=DRAFT`, `canLock=false`.
- Web validation after the DATA-08 UI update: build plus rendered HTML 10/10;
  targeted component lint has 0 errors. No source field values were entered by
  the agent.

External dataset schema/scope update (2026-08-03):
- Contract Ground Truth was preserved at 4/4 cases and 56/56 confirmed fields.
- CV review now uses 10 fields per active case: `full_name`, `headline`,
  `email`, `phone_number`, `address`, `desired_role`, `years_experience`,
  `experience`, `skills`, and `education`. Only DOCX, IMAGE and PDF_SCAN are
  active; `cv-001` PLAIN_TEXT and `cv-004` PPTX are inventory-only.
- IELTS remains five fields (`recipient_name`, `credential_id`,
  `credential_type`, `overall_score`, `issue_date`); `overall_score` is the
  only score field. `recipient_name` is one source-preserved string in the
  printed `Family name + First name` order; the UI now states this explicitly.
- Queue snapshot is 12 inventory documents / 121 inventory fields, with 10
  active documents / 101 active fields. The active queue is now `SEALED` /
  `CONFIRMED`, `canLock=false`; predictions remain unopened.
- The local draft migration preserved matching prior fields and wrote a
  recoverable backup outside Git at
  `C:\tmp\hcns-dataset-run-dec17acb-ground-truth-draft-pre-cv10-20260803.json`.

External dataset SEALED checkpoint (2026-08-03):
- Independent review confirmed all active fields: four contract cases × 14,
  three CV cases × 10, and three IELTS cases × 5 (101 active fields).
- Seal marker: `C:\tmp\hcns-dataset-run-dec17acb-ground-truth-draft-SEALED.json`.
  It records `predictionsOpened=false`, `fieldCount=121` for the complete
  inventory schema, and the sealed Ground Truth SHA-256.
- No prediction/OCR values were opened or used for review. DATA-09 produced a
  local typed projection at
  `C:\tmp\hcns-dataset-run-dec17acb-typed-canonical.json`, preserving each
  reviewed `sourceValue` beside its canonical type. The aggregate-only report
  is at `C:\tmp\hcns-dataset-run-dec17acb-data09-aggregate-pilot.json`.
- DATA-09 pilot result: 10 active documents / 101 active fields, 97 normalized,
  4 explicitly missing optional values, 0 fields requiring re-review. Typed
  coverage is 15 dates, 4 integer currency fields, 10 numeric fields and 72
  strings. Predictions remain unopened and promotion is `HOLD`.
- DATA-10 was approved by explicit user direction after schema and aggregate
  re-validation. The local approval marker is
  `C:\tmp\hcns-dataset-run-dec17acb-typed-canonical-APPROVED.json`; it permits
  read-only downstream use only, with `predictionsOpened=false` and
  `promotionAllowed=false`.
- DATA-11 now exposes the approved projection through loopback GET-only API
  routes for summary, active document detail and JSON/CSV export. The reader
  rechecks artifact hashes and approval policy per request; default responses
  omit `sourceValue`, OCR text and predictions. POST/DELETE typed routes return
  `405`; no promotion or HR side effect is enabled. API/external regression is
  22 tests passing.

OCR-HO-V2-001 checkpoint (2026-08-02):
- From 89 file-level new candidates in the local CCCD test folder, 15 images
  were selected deterministically by SHA-256 after excluding the legacy 29 and
  prior private 8. They are locked outside Git at the private held-out root.
- Phase 11.5 and Phase 11.6 each completed 15/15 in
  `SHADOW_REVIEW_ONLY`. The sealed snapshot is blinded with
  `groundTruthPresent=false` and `predictionsHiddenDuringGroundTruthReview=true`;
  no field values were copied from Ground Truth or a sibling document.
- `validate_phase11_6_lock.py` returned `LOCK_VERIFIED` (`11.6.0`, six model
  artifacts, 15 development documents). Checkpoint tests: 10 passed; Ruff,
  `check_repository.py`, and `git diff --check` passed.
- Ground Truth audit checked 15/15 source label files. They are YOLO
  detection-only annotations (class IDs and polygons/boxes) and provide no
  text transcription for the eight OCR fields. Therefore they cannot be used
  as an independent exact-OCR Ground Truth.
- Decision is `NOT_PROMOTED`; predictions remain sealed and unscored. The
  manifest is still `PENDING_HUMAN_CONFIRMATION`; a human-verified text
  transcription must be added before the sealed snapshot is evaluated once.

OCR-HO-V2-002 checkpoint (local-only Ground Truth review gate, 2026-08-02):
- Backend contract and endpoints are implemented in
  `apps/ocr_lab/api/cccd_heldout_review.py` and
  `serve_dashboard_api.py`: summary, source preview, per-document save, lock,
  and evaluate-once.
- The localhost UI is gated by `VITE_SHOW_GROUND_TRUTH_REVIEW=true`; it shows
  the source image and eight field inputs but never exposes sealed prediction
  values during review.
- The private v2 root currently reports 15 documents, 8 fields/document,
  `PENDING_HUMAN_CONFIRMATION`, `canLock=false`, `canEvaluate=false`.
- Scope amendment: `CCCD-HO-005` is confirmed as `OUT_OF_SCOPE_BACK` because it
  is a back-side card image outside the front-side eight-field schema. It is
  retained in the source audit (`sourceDocumentCount=15`) but excluded from
  Ground Truth metrics (`documentCount=14`, `excludedDocumentCount=1`); its
  fields are not marked as absent and no sealed prediction or manifest entry
  was changed.
- No Ground Truth value, prediction, source image, or private manifest is tracked
-  in Git. The user completed the 14 eligible reviews; the queue was locked and
  the sealed snapshot was evaluated exactly once.
- Evaluate-once result: 14 documents / 112 fields; Phase 11.5 and 11.6 both have
  strict exact match 50.00%, ASCII exact match 50.89%, CER 80.71%, DER 16.14%,
  field presence 86.61%, and accepted precision 95.45%. Promotion gate is
  `SHADOW_REVIEW_ONLY`: no exact regression, but accepted precision, field
  presence, full-name/address checks, and sensitive-false-acceptance gate failed.
  No candidate was promoted.
- Tests: review/API/evaluate-once 5 passed; Template-first API regression 25
  passed; web build and rendered HTML 9 passed; new Python files pass Ruff and
  compileall. The legacy dashboard module still has its pre-existing import
  placement warnings when Ruff is run on `apps/` directly.

OCR-HO-V2-003 checkpoint (post-evaluation local inspector, 2026-08-03):
- Added read-only `/cccd-heldout/review/evaluation?id=...`; it is fail-closed
  until Ground Truth is `CONFIRMED` and the immutable evaluate-once report exists.
- Local UI now compares each eligible image's Ground Truth with Phase 11.5 and
  11.6 values, strict/ASCII verdicts, prediction status/error signals,
  confidence, and evidence ROI. Back-side `CCCD-HO-005` remains excluded.
- No raw private output is tracked in Git. Full Python suite: 248 passed and 16
  subtests; web build/rendered HTML: 10 passed; targeted Ruff/compileall and
  repository hygiene passed.

Key commands:
- `python -m pytest -q`
- `python -m ruff check src tests scripts`
- `python -m mypy src`
- `python scripts/check_repository.py`
- `python scripts/evaluate_template_multiformat.py --data-root <local-root>`
- Current UX/API target: API preview 7 passed; web 9 passed/build; ESLint 0 error,
  17 warning hiện hữu
- Previous full checkpoint: Python 225 passed; lint 0 errors/15 existing warnings
- Weekly report: `python scripts/validate_weekly_report.py` and report-script Ruff pass

M4-CAM-001 checkpoint (2026-08-04):
- Camunda BPMN `2.2.0-shadow` is closed to `LEAVE_REQUEST` and
  `OVERTIME_REQUEST` across submit, confirm-type and re-upload forms.
- The adapter owns an M4 allowlist; `document_extract` rejects an out-of-scope
  workflow type with `DOCUMENT_INPUT_INVALID` before invoking the operation.
- Global domain/workflow enums remain unchanged for legacy compatibility;
  `autoContinueEnabled=false` and mock-only side effects remain locked.
- Validation: 39 targeted tests passed; Ruff, mypy (79 source files), repository
  hygiene and `git diff --check` passed.
- Superseded next-task marker: M4-CAM-002 is now DONE; see the checkpoint below.

M4-CAM-002 checkpoint (2026-08-04):
- A local `hcns-agent-camunda-worker` entrypoint composes the REST client,
  Template-first pipeline, OCR Lab session source resolver, private JSON result
  store and all M4 handlers by dependency injection.
- All six document topics are bound exactly; missing or unexpected operations
  fail closed at startup. HRIS and notification remain simulated.
- Parse persists the full private result and idempotency index before worker
  completion. Replay reuses one deterministic opaque reference without running
  the pipeline again; raw field values never enter process variables.
- Invalid input emits `DOCUMENT_INPUT_INVALID`; technical failures decrement
  External Task retry. The parse topic extends its lock to 180 seconds before
  running the long stage.
- Runtime connection values come only from environment; no credential, endpoint
  or private path is committed. No Camunda deployment/server call was made.
- Validation: 52 targeted tests passed; Ruff passed; mypy passed on 81 source
  files; repository hygiene and `git diff --check` passed.
- Known deferral: correction is reference-only until M4-CAM-005. The previously
  deferred eight-variable DMN projection is now complete below.
- Superseded next-task marker: M4-CAM-003 is now DONE; see the checkpoint below.

M4-CAM-003 checkpoint (2026-08-04):
- The private idempotent result now includes an exact eight-scalar DMN quality
  projection. `document_normalize_validate` returns only those inputs and never
  forwards Template-first `MANUAL_REVIEW` as a gateway action.
- Projection validation checks the exact key set, scalar/boolean types,
  `qualityStatus`, confidence range, the Camunda whitelist and JSON Schema.
- Valid native documents route to `USER_REVIEW` because shadow policy keeps
  `autoContinueEnabled=false`. Four synthetic OCR paths covering both templates
  and image/scan PDF remain Human Review with zero false `AUTO_CONTINUE`.
- Missing required fields route to `REQUEST_REUPLOAD`; business inconsistencies
  route to `HR_REVIEW`; type mismatch targets the Confirm Type User Task.
- DMN output is restricted to `AUTO_CONTINUE`, `USER_REVIEW`, `HR_REVIEW` and
  `REQUEST_REUPLOAD`; no raw field value is returned in process variables.
- Validation: 59 targeted tests passed; Ruff passed; mypy passed on 81 source
  files; repository hygiene and `git diff --check` passed.
- No deployment or Camunda server call was made. Correction remains
  reference-only for M4-CAM-005.
- Superseded environment marker: M4-CAM-004 is now DONE below.

M4-CAM-004 checkpoint (2026-08-04):
- Camunda BPM Run 7.13.0 was verified locally and the REST deployment succeeded
  with one BPMN process plus one DMN decision.
- The first deployment exposed an XSD ordering defect: BPMN artifacts preceded
  sequence flows. The artifact block was moved after all flow elements and a
  regression test now locks Camunda 7.13-compatible ordering.
- Synthetic leave and overtime instances both reached `UserReview` with PASS,
  `USER_REVIEW` and `autoContinueEnabled=false`.
- Worker restart retained the active User Task/process state. A same-key replay
  reused the original opaque reference and kept the private result-file count
  unchanged.
- Three synthetic instances completed with HRIS and notification history values
  both `SIMULATED`; no real external side effect was enabled.
- Worker smoke processes were stopped. Camunda local remains running for
  deployment/history inspection; no credential or private value was recorded.
- Validation: 60 targeted tests passed; Ruff passed; mypy passed on 81 source
  files; repository hygiene and `git diff --check` passed.
- Superseded next-task marker: M4-CAM-005 is completed in the checkpoint below.

M4-CAM-005 checkpoint (2026-08-04):
- BPMN version `2.3.0-shadow` adds reviewer context, audit External Tasks,
  correction invalid boundary and SLA-only escalation timers.
- Private correction artifacts are content-addressed; corrected results retain
  the prior revision, require the current payload hash, increment case version,
  and rerun template validation plus DMN projection.
- Synthetic Camunda smoke completed `UNRESOLVED -> HRReview -> CORRECTED ->
  revalidation -> UserReview -> CONFIRMED` and
  `REQUEST_REUPLOAD -> UploadAgain -> UserReview -> CONFIRMED`.
- Five private audit artifacts, one correction artifact and one result revision
  were produced; HRIS/notification remained `SIMULATED`. No raw values were
  sent to Camunda.
- Validation: 36 targeted Camunda tests passed; Ruff and mypy passed; Camunda
  7.13 deployment succeeded; worker smoke processes were stopped.

M4-CAM-006 checkpoint (2026-08-04):
- Added `hcns_agent.adapters.camunda7.dry_run` and
  `scripts/run_camunda_m4_dry_run.py`; the runner is synthetic/local-only,
  uses a private temp store, makes no network call and emits aggregate metadata.
- Ten scenarios passed: native leave/overtime → `USER_REVIEW`; OCR leave/overtime
  → `HR_REVIEW` by the locked sensitive-field safety rule; mismatch/Confirm Type;
  fail-closed invalid input; missing required field; correction/revalidation;
  re-upload limit; technical retry/idempotent replay.
- Aggregate: 10/10, false `AUTO_CONTINUE` 0, duplicate result artifacts 0,
  technical retries 1, real side effects disabled and raw values absent.
- Decision: shadow pilot APPROVED WITH CONDITIONS for only leave/overtime in an
  isolated/local runtime. `autoContinueEnabled=false`; HRIS/notification remain
  `SIMULATED`. Production/public endpoint/real writes require M5 authorization.
- Verification: `tests/test_camunda_m4_dry_run.py` passed; Ruff and mypy passed
  for the new runner. No CCCD or private dataset work was changed.

M5-CAM-001 checkpoint (2026-08-04):
- User confirmed opening M5 shadow-pilot authorization. Task is `READY`, not DONE;
  no pilot cohort has been executed.
- Added `docs/CAMUNDA_M5_SHADOW_PILOT_RUNBOOK.md` covering scope, business/privacy
  gates, preflight, aggregate-only monitoring, rollback triggers and acceptance.
- Scope remains only leave/overtime in local/isolated Camunda 7.13; keep
  `autoContinueEnabled=false`, mock HRIS/notification and no CCCD/timesheet.
- Blockers before execution: business owner must provide cohort, reviewers,
  time window, retention and rollback authority. No raw value or credential is
  recorded in Git.

Next:
- M5-CAM-001 is READY. Complete the runbook's Business scope, Privacy/Retention
  and Rollback gates before executing any pilot cohort; keep localhost/loopback
  and the two-document closed set as the runtime target.
- Keep Paddle rollback and historical CCCD/held-out work outside the
  Template-first default unless a new evidence task is approved.

## OCR-HO-V2-004 checkpoint (2026-08-03)

- Candidate `OCR-HO-V2 v1.1.0` is implemented for development shadow use only.
  Orientation is explicitly `fixed_0_degree`; no 90°/180°/270° promotion path
  is enabled. Every result remains `MANUAL_REVIEW`.
- Parser boundary fixes cover bilingual-label contamination, OCR typo aliases,
  multiline origin/residence geometry, and unsafe expiry-date fallback. The
  candidate reads OCR evidence only; it does not use Ground Truth or sibling
  documents to fill values.
- Development regression on 15 archived reviewed images / 120 fields:
  baseline strict/ASCII exact 60.00%/61.67%, CER 43.60%, DER 12.65%, presence
  95.83%; v1.1 strict/ASCII exact 36.67%/40.00%, CER 50.75%, DER 17.00%,
  presence 70.00%.
- Gate: `DEVELOPMENT_FAIL`, with schema errors 0 and manual-review policy true,
  but exact regressions 33 and quality metrics below baseline. No production
  promotion; the official 14-document held-out evaluate-once artifact remains
  immutable. Localhost is running the v1.1 shadow output for inspection.

## OCR-HO-V2-005 checkpoint (2026-08-03)

- Added guarded shadow candidate policy v1.2.0 for Vietnamese CCCD field
  recovery. It consumes Phase 11.5 evidence only, cleans bilingual labels and
  line merges, and replaces a baseline value only when the baseline is unsafe
  and independent recognizer families agree.
- Development archive replay covered 15 documents / 120 fields at fixed 0°.
  Baseline strict/ASCII exact was 60.00%/61.67%; candidate remained
  60.00%/61.67%, improved CER from 43.60% to 43.06%, kept DER 12.65% and
  presence 95.83%, with 0 exact regressions and schema errors 0.
- All 120 candidate fields remain `MANUAL_REVIEW`. Gate is
  `DEVELOPMENT_PASS`, but `productionPromotionAllowed=false`; no runtime
  extractor or official held-out evaluate-once artifact was changed.
- Aggregate report is private-only at
  `CCCD_OCR_HO_V2_005_DEVELOPMENT_COMPARISON.{json,md}`. No PII or raw OCR is
  tracked.

## OCR-HO-V2-008 checkpoint (token-alignment candidate, 2026-08-03)

- Candidate `OCR-HO-V2 v11.8.1` aligns normalized address token sequences from
  independent recognizer families and restores only structural separators for
  `placeOfOrigin`; residence remains guarded by the v11.7 selector.
- Development comparison covered 15 reviewed images / 120 fields at fixed 0°:
  strict exact 60.00% -> 60.83%, ASCII exact 61.67% -> 63.33%, CER
  43.60% -> 42.47%, DER 12.65% -> 12.25%, presence 95.83%, region selection
  73.33% -> 81.67%.
- Exact improvements/regressions were 1/0; schema errors 0 and all 120 fields
  remained `MANUAL_REVIEW`. Development gate passed, but
  `productionPromotionAllowed=false` remains enforced. Localhost primary and
  the official 14-document held-out artifact were not changed.

## OCR-HO-V2-007 checkpoint (address ROI + Unicode replay, 2026-08-03)

- Candidate `OCR-HO-V2 v11.7.1` narrows recovery to `placeOfOrigin` and
  `placeOfResidence`. It uses same-row bilingual label geometry, removes
  neighboring labels/dates, and applies only reversible Unicode mojibake repair;
  protected fields remain the Phase 11.5 baseline.
- Development comparison covered 15 reviewed images / 120 fields at fixed 0°.
  Strict/ASCII exact stayed 60.00%/61.67%, CER improved 43.60% -> 43.27%,
  DER improved 12.65% -> 12.25%, presence stayed 95.83%, and region selection
  improved 73.33% -> 81.67%.
- Exact improvements/regressions were 0/0; schema errors were 0 and all 120
  fields remained `MANUAL_REVIEW`. Gate is `DEVELOPMENT_FAIL` because at least
  one exact improvement is mandatory. `productionPromotionAllowed=false`;
  localhost primary and the official 14-document held-out artifact are unchanged.

## OCR-HO-V2-011 checkpoint (deterministic address ROI, 2026-08-04)

- Candidate `OCR-HO-V2 v11.9.1` derives the two address ROIs from observed
  label anchors and clips the residence band before the expiry block. It is
  development shadow-only and keeps every output at `MANUAL_REVIEW`.
- The replay used only the available `paddle_ppocrv5` profile; optional
  EasyOCR/VietOCR packages were unavailable and this limitation is recorded.
  Ground Truth was scoring-only, never a candidate input.
- Metrics: strict exact 60.00% -> 60.00%, ASCII exact 61.67% -> 62.50%, CER
  43.60% -> 41.44%, DER 12.65% -> 15.81%, presence 95.83% -> 95.83%, region
  selection 73.33% -> 79.17%; exact improvements/regressions 0/0.
- Schema errors: 0; manual-review fields: 120/120. Gate is
  `DEVELOPMENT_FAIL` because DER regressed and no exact improvement exists.
  `productionPromotionAllowed=false`; localhost primary and the official
  14-document held-out evaluate-once artifact are unchanged.
- Private report: `CCCD_OCR_HO_V2_011_DEVELOPMENT_COMPARISON`.

## OCR-HO-V2-012 checkpoint (full recognizer replay, 2026-08-04)

- The locked private secondary runtime was restored with EasyOCR 1.7.2,
  VietOCR 0.3.13 and CPU Torch. EasyOCR/VietOCR model hashes all passed the
  Phase 11.6 policy; Paddle remained isolated in `D:\venv_paddle`.
- An existing Camunda adapter eager-import cycle was fixed with lazy runtime
  exports so the replay runner can import without changing public names.
- Full development replay (15 images / 120 fields, fixed 0 degrees): strict
  exact 60.00% -> 60.83%, ASCII exact 61.67% -> 62.50%, CER 43.60% ->
  42.09%, DER 12.65% -> 11.46%, presence 95.83%, region selection 73.33%
  -> 83.33%, exact improvements/regressions 1/0.
- Schema errors: 0; manual-review fields: 120/120. Gate is
  `DEVELOPMENT_PASS`, but `productionPromotionAllowed=false`. The localhost
  primary and official 14-document held-out evaluate-once artifact remain
  unchanged.
- Validation: 20 targeted Camunda/OCR tests passed, Ruff passed, and
  `scripts/check_repository.py` passed.

## OCR-HO-V2-013 checkpoint (promotion review and local canary, 2026-08-04)

- The private shadow inspector now resolves the v11.9.1 development report
  and `phase11_9_v2/field_consensus.json` automatically, without changing the
  v11.8 test fallback. The UI shows the candidate version from the API.
- Loopback runtime evidence: schema
  `ocr-ho-v2-013-promotion-review/1.0.0`, candidate `11.9.1`,
  `SHADOW_REVIEW_ONLY`, 15 development documents, and
  `groundTruthLoaded=false`. All 15 review decisions remain pending.
- The report gate is `DEVELOPMENT_PASS` with
  `productionPromotionAllowed=false`; no automatic review, promotion,
  held-out rerun, or primary-runtime change was performed.
- Canary smoke passed: API health, shadow summary, one document detail/preview,
  and the existing localhost web shell returned successfully.

## OCR-HO-V2-009 checkpoint (local shadow UAT, 2026-08-03)

- Implemented a loopback-only shadow inspector for OCR-HO-V2 v11.8.1. It
  renders each development source image alongside the Phase 11.5 baseline and
  Phase 11.8.1 candidate field values, changed/protected tags, ROI bbox,
  confidence and recognizer provenance.
- The endpoint explicitly reports `groundTruthLoaded=false`; it reads only
  `phase11_5` and `phase11_8_v2` artifacts. It never changes Template-first,
  the CCCD primary runtime, the official held-out artifact or promotion state.
- A private review store accepts one of `APPROVE_SHADOW`, `REJECT_SHADOW` or
  `NEEDS_FOLLOWUP` only after source comparison, changed-field inspection and
  `MANUAL_REVIEW` assertions. No raw review store is tracked in Git.
- Runtime evidence: 15 development documents are visible; v11.8.1 remains
  `DEVELOPMENT_PASS` with `productionPromotionAllowed=false`.
- Tests: shadow Python/API 3 passed; rendered web tests 11 passed; ESLint 0
  errors with 23 existing warnings; Ruff passed for new files and API E501.
  The web build remains unrun because the sandbox denies writes to
  `node_modules/.vite-temp`.

## OCR-HO-V2-006 checkpoint (targeted ROI/recognizer replay, 2026-08-03)

- Candidate `OCR-HO-V2 v11.6.1` ran a fresh four-variant ROI replay for
  `fullName`, `sex`, `nationality`, `placeOfOrigin`, and `placeOfResidence`.
  Other fields remained protected by the Phase 11.5 baseline; input stayed at
  fixed 0 degrees and every output stayed `MANUAL_REVIEW`.
- Development comparison covered 15 archived reviewed images / 120 fields.
  Baseline strict/ASCII exact was 60.00%/61.67%, CER 43.60%, DER 12.65%,
  presence 95.83%. Candidate was 60.00%/61.67%, CER 42.52%, DER 13.83%,
  presence 95.83%, with region-selection accuracy improving 73.33% -> 79.17%.
- No exact improvement and no exact regression were observed. Schema errors
  were 0 and all 120 fields remained manual review. Gate is
  `DEVELOPMENT_FAIL` because DER regressed and the promotion rule requires at
  least one exact improvement. `productionPromotionAllowed=false`.
- Candidate evidence and aggregate reports remain private-only; the official
  14-document held-out evaluate-once artifact and localhost primary runtime
  were not changed.

## Local real-document evidence refresh (2026-08-04)

- Local dashboard API was restarted against the active private root
  `C:\\Camunda\\private-data\\paddleocr-hr-baseline`; the older
  `paddleocr-hr-baseline-archive-20260803` is not used for Template-first evidence.
- `GET /api/documents/sessions` now returns 11 leave/overtime sessions: native
  DOCX/PDF sessions plus the latest image predictions using `easyocr/vi-greedy`.
- Preview/source smoke passed for leave and overtime images and a native PDF;
  `/health` is `ok`, and localhost web responds HTTP 200. No raw values were
  copied into Git or project state.
- CCCD, OCR-HO shadow and DATA-11 typed projection routes remain configured
  against their existing private artifacts.

## External image expansion checkpoint (2026-08-04)

- Created a private expanded staging root outside Git from the existing
  synthetic inventory plus 10 new PNGs supplied in `D:\bo_10_anh_tai_lieu_gia_lap`:
  4 contract, 3 CV and 3 IELTS images.
- Inventory `2026-08-04-image-expansion` verifies 22 documents / 26 pages.
  Existing case IDs and review state were preserved; the 10 new image cases
  remain `PENDING` in a new Ground Truth draft.
- EasyOCR aggregate-only pilot completed 22/22 cases with 0 failures using
  `easyocr/vi-greedy` 1.7.2. Report contains no raw OCR text or field values;
  promotion remains `HOLD` because Ground Truth is not sealed and page count
  is below the benchmark minimum.
- Local API now serves the expanded review dataset at `127.0.0.1:8765`:
  active review is 20 documents / 202 fields (contract 8/112, CV 6/60,
  IELTS 6/30). New image preview/source smoke tests returned HTTP 200 with
  `image/png`; predictions remain hidden during review.
- Review scope labels are now computed from API metadata instead of the old
  fixed case counts. DATA-11 typed projection is intentionally not attached to
  this unsealed expansion; the prior approved projection remains private-only.
