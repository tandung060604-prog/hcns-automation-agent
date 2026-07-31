# Project State

Current milestone: TF-P2-002 in progress; native multi-format passed, OCR text gate open
Documentation profile: Standard (`PROJECT_STATE.md`, `BACKLOG.md`, `HANDOFF.md`)

Completed:
- Universal intake, Canonical Document, safety, native/OCR routing and quality contracts
- Generic multi-family pipeline retained as legacy-compatible behavior
- Camunda 7 worker/assets and process-variable whitelist
- Registered `leave-request-v1` and `overtime-request-v1`
- Content detection is normalized, filename-independent and closed-set
- DOCX/native PDF parse without OCR; image/PDF scan use local PaddleOCR
- Per-template extraction, validation, JSON Schema and quality routing
- Multi-format `GET /api/templates` and `POST /api/documents/process`
- One default upload surface with image/PDF preview beside structured fields/JSON
- Session-scoped source retention and loopback-only `GET /api/documents/source`
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
- OCR: image/scan -> rectify -> PaddleOCR -> registry -> validator -> review
- IDP reads; Agent proposes; Camunda owns workflow and Human Review
- Unsupported templates never fall through to the generic extractor
- Raw documents/full payloads remain behind local references

Local runtime checkpoint:
- UI: `http://localhost:3000`; API: `http://127.0.0.1:8765`
- API PID `36764`; web PID `28852`; health reports OCR model loaded after smoke
- Live camera upload returned `LEAVE_REQUEST` / `MANUAL_REVIEW`; smoke session deleted
- UX smoke trên desktop xác nhận một vùng upload, ảnh preview sticky cạnh metadata/JSON;
  PDF/PNG source round-trip khớp SHA-256 và các session smoke đã xóa
- Loopback development runtime only; no production deployment or HRIS side effect
- Template-first is the only default upload surface; legacy OCR/IDP is preserved
  behind `VITE_SHOW_LEGACY_UPLOAD=true`
- Mentor view hides held-out unless `VITE_SHOW_HELDOUT=true`
- Evidence retains Template-first/CCCD and the right metadata/JSON panel
- Hero uses the approved local workflow infographic; no remote asset is loaded
- Weekly report 2026-W31 records a redacted audit, two safe local UI screenshots and a
  reproducible selection of four review-complete CCCD sessions; no source or PII is tracked

Security:
- No dataset, Ground Truth, upload, model weight, secret or raw PII added to Git
- Regression reads the approved local synthetic set and reports aggregates only
- No cloud OCR/API call; server bind remains loopback

Known limits:
- Native DOCX/PDF pass; photographed/scanned text remains shadow-review quality
- PaddleOCR loses Vietnamese characters in dynamic text on the six hard images
- TF-P2-002 is not DONE until OCR EM reaches 80% or scope is re-approved
- Seven old overtime Ground Truth `department` labels do not occur in source DOCX
- Phase 11.6/CCCD WIP remains uncommitted and outside this task

Key commands:
- `python -m pytest -q`
- `python -m ruff check src tests scripts`
- `python -m mypy src`
- `python scripts/check_repository.py`
- `python scripts/evaluate_template_multiformat.py --data-root <local-root>`
- Current UX/API target: API preview 6 passed; web 9 passed/build; ESLint 0 error,
  17 warning hiện hữu
- Previous full checkpoint: Python 225 passed; lint 0 errors/15 existing warnings
- Weekly report: `python scripts/validate_weekly_report.py` and report-script Ruff pass

Next:
- Keep TF-P2-002 as the only active Template-first task; do not start TF-P2-003
- Review a Vietnamese line-recognition improvement for camera/scan text
- Keep historical CCCD/held-out work deferred from the Template-first default
