# Project State

Current milestone: M2 — Document Understanding and Quality Gate implemented

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
- 55+ synthetic unit/contract/safety/architecture tests
- Ruff, strict mypy, compile and repository hygiene gates

Architecture:
- IDP reads/understands; Agent analyzes/proposes; Camunda orchestrates
- SourceFormat selects parser; DocumentType selects extractor
- Quality gate never grants HRM/BPM side-effect authority
- Camunda owns BPMN, User Task, timer, retry, escalation and process state

Security:
- No real PII, private-data, upload, OCR output or model weights added
- Classifier evidence stores source locations, not copied raw text
- Validation issues do not include field values
- Business JSON and canonical content stay behind result references

Known limits:
- Rule classifier/extractors are architecture baselines, not accuracy-promoted models
- Supported extractors: CV, employment contract, leave request and timesheet
- Administrative/other types require review until an extractor is approved
- PPTX remains text-by-slide; legacy DOC/XLS require safe conversion
- No authorized real-document benchmark yet
- No Camunda deployment, review UI or HRM/BPM side effect

Key commands:
- `python -m unittest discover -s tests -v`
- `python -m ruff check src tests scripts`
- `python -m mypy src`
- `python scripts/check_repository.py`

Next:
- M3 authorized classification/extraction/OCR benchmark and promotion gates
- Expand extractors only from prioritized workflow evidence
- M4 Camunda generation selection, SDK worker and BPMN dry-run
