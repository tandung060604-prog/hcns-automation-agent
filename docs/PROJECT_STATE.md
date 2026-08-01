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

Next:
- Prepare a separate Railway deployment/production-readiness task with the
  EasyOCR model-storage and CPU-latency constraints recorded above.
- Keep Paddle rollback and historical CCCD/held-out work outside the
  Template-first default unless a new evidence task is approved.
