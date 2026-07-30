# Project State

Current milestone: M3 / Phase 17 plus M4 Camunda 7 shadow scaffolding
Completed:
- M1 Universal Document Intake, safety, canonical model and native/OCR routing
- Independent SourceFormat/DocumentType/WorkflowType with vendor-neutral ports
- Unified five-family classifier/extractors for 15 Vietnamese HR subtypes
- Quality score/status with explicit Human Review reasons
- Business JSON schema 2.0.0 with classification/quality/field provenance
- Offline benchmark Ground Truth/prediction/report/comparison schemas 1.0.0
- Baseline/challenger promotion gate with privacy/license/provenance evidence
- Recognition-only contracts and Vietnamese NFC audit with 134 characters
- Phase 14.8: Seq2Seq primary, Transformer verifier, Paddle detector-only evidence
- Strict disagreement policy preserves Seq2Seq and always sets `needs_review`
- CCCD Phase 11.5 dev (15): EM 60.00%, ASCII EM 61.67%, CER 43.60%, DER 12.65%; SHADOW
- Accepted precision 56.96%→94.74%; coverage 65.83%→31.67%; `NOT_PROMOTED`
- Phase 14.8 dev corpus keeps fallback disabled; LODO recovered 30 errors but lost one correct line
- Separate diagnostic analysis covers 149 locked Ground Truth lines without raw text
- Canonical metric spec `vi-ocr-metrics/1.0.0` shared across Phase 14 adapters
- Versioned recognition policies never auto-replace text in shadow mode
- Phase 14.6 lock pins policy, crop and SHA-256 for three local model artifacts
- Held-out runner seals predictions, rejects Ground Truth leakage and evaluates once
- OCR Lab resumes on F5 and shows local source beside Ground Truth/prediction JSON
- Camunda 7 REST client covers fetch/complete/failure/BPMN error/lock extension
- BPMN parses content before classification; DMN blocks unsafe auto-continue
- Process-variable schema/whitelist and nine-topic shadow handler registry
- Phase 15 development benchmark: 25 documents, 31 pages and 1,025 line crops
- Five-family classification is 100% on synthetic development data only
- Phase 16 structured parser raises Field EM 30.92%→37.50% and completeness 51.39%→65.67%
- Contract/decision EM 25.00%; credential EM 27.50%; CER 60.30%, DER 1.55%; development-only
- Phase 16 real held-out manifest locks 18 authorized documents across five families
- Hidden predictions are sealed for 771 crops; 261 disagreements remain `needs_review`
- Phase 16 TIMESHEET Ground Truth stores native rows and aggregate row/cell metrics
- Phase 16 Ground Truth confirmed for 18/18 documents with predictions hidden
- Phase 16 evaluate-once: classification 77.78%, Field EM 13.00%,
  completeness 28.00%, false acceptance 2; `NOT_PROMOTED`
- Native PDF text, DOCX and XLSX bypass OCR and preserve native structures
- Phase 17 live-v5 audit: 15 docs; Field EM 14.63%, completeness 24.39%, classification 73.33%

Architecture:
- IDP reads/understands; Agent analyzes/proposes; Camunda orchestrates
- SourceFormat selects native/OCR parser; family and subtype select extractor/schema
- Benchmark compares every backend through the same IdpResult contract
- Benchmark report is aggregate-only and contains no raw field values
- Camunda owns BPMN, User Task, timer, retry, escalation and process state
- Camunda owns routing; adapter remains shadow-only until OCR promotion

Security:
- No real PII, private-data, upload, OCR output or model weights added
- Business JSON and canonical content stay behind result references
- Ground Truth/predictions stay outside Git; report requires disclosure review

Known limits:
- Rule classifier/extractors are architecture baselines, not accuracy-promoted models
- Five family schemas cover CV, administrative, contract/decision, credential and table
- Contract/decision and credential Field EM remain only 25.00%/27.50% after Phase 16
- PPTX remains text-by-slide; legacy DOC/XLS require safe conversion
- Phase 15 classification tuning used synthetic data and is not held-out evidence
- Locked Phase 16 TIMESHEET predictions had legacy scalar output and no tables
- Live-v5 audit still misroutes three credential scans as identity documents
- Historical Phase 14 DER is not comparable with metric spec 1.0.0
- Verifier agreement is not calibrated as correctness evidence on real scans
- No Camunda deployment, bound stage operations or real HRIS side effect
- Camunda environment link and deployment evidence remain pending

Key commands:
- `python -m unittest discover -s tests -v`
- `python -m ruff check src tests scripts`
- `python -m mypy src`
- `python scripts/check_repository.py`
- `hcns-agent-benchmark evaluate --ground-truth <file> --predictions <file> --output <file>`

Next:
- Collect authorized, non-duplicate documents in `paddleocr-hr-heldout-v2`
- Confirm authorization, prepare manifest and run hidden predictions
- Add classification macro precision/recall/F1 and UNKNOWN rate on held-out data
- Keep all unsupported/uncertain fields in `needs_review`
- Promote only per family/subtype after its own quality gate passes
- Keep reviewed Business JSON behind `resultReference`, never process variables
- Bind M4 stage operations and execute Camunda 7.13 local dry-run
