# Project State

Current milestone: M3 — Verified benchmark harness implemented; authorized run pending

Completed:
- M1 Universal Document Intake, safety, canonical model and native/OCR routing
- Independent SourceFormat, DocumentType and WorkflowType
- Vendor-neutral DocumentClassifier and FieldExtractor ports
- Deterministic classifier with candidates, confidence, version and provenance
- Deterministic extractor registry by DocumentType
- CV extractor: full name, skills and education
- Employment contract extractor: number, employee, dates and salary
- Leave request extractor: employee, dates and reason
- Native timesheet extractor: employee codes, entry count and formulas
- Required-field, confidence, sensitivity and extractor-availability validation
- Duplicate field conflict and ISO date/range validation
- Quality score/status with explicit Human Review reasons
- IdpResult persisted before Camunda job completion
- Business JSON schema 2.0.0 with classification/quality/field provenance
- Camunda summary carries documentType, qualityStatus and reviewRequired
- Offline benchmark Ground Truth/prediction/report/comparison schemas 1.0.0
- Aggregate OCR CER/WER and exact reading-order metrics
- Per-type classification and per-field exact-match metrics
- False PASS/REJECT, review, sensitive acceptance, latency/failure metrics
- Baseline/challenger promotion gate with privacy/license/provenance evidence
- Vendor-neutral IdpResult-to-benchmark adapter and CLI
- 60+ synthetic unit/contract/safety/architecture/benchmark tests
- Ruff, strict mypy, compile and repository hygiene gates

Architecture:
- IDP reads/understands; Agent analyzes/proposes; Camunda orchestrates
- SourceFormat selects parser; DocumentType selects extractor
- Quality gate never grants HRM/BPM side-effect authority
- Benchmark compares every backend through the same IdpResult contract
- Benchmark report is aggregate-only and contains no raw field values
- Camunda owns BPMN, User Task, timer, retry, escalation and process state
- Camunda 7 BPMN/DMN reference package added for review and dry-run

Security:
- No real PII, private-data, upload, OCR output or model weights added
- Classifier evidence stores source locations, not copied raw text
- Validation issues do not include field values
- Business JSON and canonical content stay behind result references
- Ground Truth/predictions stay outside Git; report requires disclosure review

Known limits:
- Rule classifier/extractors are architecture baselines, not accuracy-promoted models
- Supported extractors: CV, employment contract, leave request and timesheet
- Administrative/other types require review until an extractor is approved
- PPTX remains text-by-slide; legacy DOC/XLS require safe conversion
- No authorized real-document benchmark yet
- No Camunda deployment, review UI or HRM/BPM side effect
- Camunda environment link and deployment evidence remain pending

Key commands:
- `python -m unittest discover -s tests -v`
- `python -m ruff check src tests scripts`
- `python -m mypy src`
- `python scripts/check_repository.py`
- `hcns-agent-benchmark evaluate --ground-truth <file> --predictions <file> --output <file>`

Next:
- Obtain approval/manifest for a fixed 30–50 page Ground Truth outside Git
- Run PaddleOCR baseline and MinerU challenger on the same dataset digest
- Review aggregate comparison; do not promote until every gate passes
- M4 Camunda generation selection, SDK worker and BPMN dry-run
