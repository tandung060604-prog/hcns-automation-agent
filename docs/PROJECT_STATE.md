# Project State

Current milestone: Template-first Phase 1 complete; closed-set DOCX MVP
Documentation profile: Standard — `PROJECT_STATE.md`, `BACKLOG.md`, `HANDOFF.md`
with routing index in `docs/README.md`

Completed:
- Universal intake, safety, Canonical Document, native/OCR routing and quality contracts
- Generic multi-family pipeline retained as legacy-compatible behavior
- Camunda 7 REST worker, BPMN/DMN shadow assets and process-variable whitelist
- Template registry with `leave-request-v1` and `overtime-request-v1`
- Content-anchor detection is Unicode/case/whitespace normalized and filename-independent
- Native DOCX parsing only; OCR is forbidden in template-first Phase 1
- Per-template extraction, normalization, validation, JSON Schema and quality routing
- Local `GET /api/templates` and `POST /api/documents/process`
- README foregrounds the two standard HCNS forms and preserves legacy IDP/OCR documentation
- Result JSON stored under private data root; Camunda receives only scalar metadata/reference
- Local synthetic regression: 14/14 classification, 126/126 required fields, 0 schema errors
- All labeled fields: 301/308 exact; 7 overtime `department` labels contradict source content
- Missing/ambiguous fields remain `null` or route to `MANUAL_REVIEW`
- Unsupported templates route `REJECT_UNSUPPORTED`; corrupt/crashed parsing is technical error

Preserved OCR evidence:
- CCCD Phase 11.5 dev (15): EM 60.00%, ASCII EM 61.67%, CER 43.60%, DER 12.65%; SHADOW
- CCCD Phase 11.6 protected replay (15): EM 60.00%, ASCII EM 61.67%, zero regression
- Phase 11.6 lock verified; 180/180 target crops completed with EasyOCR greedy on CPU
- CCCD held-out v1 has 9 new non-duplicate images; predictions locked and Ground Truth hidden
- Held-out v1 remains below the 15-document gate and `SHADOW_REVIEW_ONLY`
- Phase 16 evaluate-once: classification 77.78%, Field EM 13.00%, `NOT_PROMOTED`
- Phase 17 live-v5: 15 docs; Field EM 14.63%, completeness 24.39%, classification 73.33%

Architecture:
- Template-first endpoint: DOCX -> safety -> native OOXML -> registry -> parser -> validator
- IDP reads/understands; Agent proposes; Camunda owns workflow and Human Review
- Generic classifier/extractors are not a fallback for unsupported template-first uploads
- Raw document and full extracted payload remain behind a local result reference

Runtime checkpoint (2026-07-31):
- Template-first implementation commit `53b22fb` was pushed to
  `origin/codex/m1-m2-document-understanding` and verified by remote hash
- Local API was started on `127.0.0.1:8765` with PID `14312`; `/health` reports `ok`
- `/api/templates` lists `leave-request-v1` and `overtime-request-v1`
- Live HTTP smoke used two original DOCX files outside the 14-file regression set
- Both uploads returned `SUCCESS`, the expected document type, `AUTO_CONTINUE` and zero
  validation errors; smoke sessions were deleted after aggregate-only verification
- This is a loopback development runtime, not a production deployment

Local UI checkpoint (2026-07-31):
- OCR Lab defaults to Template-first; mentor view hides held-out unless `VITE_SHOW_HELDOUT=true`
- Evidence shows Template-first/CCCD; hero now showcases standard forms without PII imagery
- Legacy OCR/IDP upload remains available as a separate mode
- API root redirects to the main local UI; API PID `27752`, web PID `28852` at checkpoint
- Browser smoke processed an original leave-request DOCX as `SUCCESS` / `AUTO_CONTINUE`,
  rendered 19 field cards and kept the local result visible for user inspection
- Python suite: 219 passed; web build/tests: 8 passed; lint: 0 errors, 19 existing warnings
- Standalone `tsc --noEmit` remains non-gating because of pre-existing Phase 14/worker errors

Security:
- No dataset, Ground Truth, upload, model weight, secret or raw PII added to Git
- Regression reads the explicitly supplied local synthetic dataset and logs aggregates only
- No cloud/API call; API binds loopback through the existing server guard

Known limits:
- Phase 1 supports only native-text DOCX for the two registered templates
- PDF/image/OCR fallback, arbitrary layouts and generic document forcing are out of scope
- Seven overtime Ground Truth `department` values do not occur in source DOCX; parser keeps null
- No production Camunda deployment or real HRIS side effect
- Phase 11.6/CCCD WIP remains uncommitted and outside the template-first task

Key commands:
- `python -m pytest -q`
- `python -m ruff check src tests scripts`
- `python -m mypy src`
- `python scripts/check_repository.py`
- `python scripts/evaluate_template_phase1.py --data-root <local-synthetic-root>`

Next:
- Review and approve a separate Phase 2 task for Camunda User Task/Human Review integration
- Keep PDF/scan support blocked until the native DOCX contract remains stable
- Treat historical CCCD/held-out work as deferred, not as the template-first MVP default
