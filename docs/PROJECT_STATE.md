# Project State

Current milestone: M3 / Phase 14.2 — controlled real-scan OCR pilot

Completed:
- M1 Universal Document Intake, safety, canonical model and native/OCR routing
- Independent SourceFormat/DocumentType/WorkflowType with vendor-neutral ports
- Deterministic classifier and extractors for CV, contract, leave and timesheet
- Required-field, confidence, sensitivity and extractor-availability validation
- Duplicate field conflict and ISO date/range validation
- Quality score/status with explicit Human Review reasons
- IdpResult persisted before Camunda job completion
- Business JSON schema 2.0.0 with classification/quality/field provenance
- Camunda summary carries documentType, qualityStatus and reviewRequired
- Offline benchmark Ground Truth/prediction/report/comparison schemas 1.0.0
- Aggregate OCR, classification, field, safety, review and latency metrics
- Baseline/challenger promotion gate with privacy/license/provenance evidence
- Vendor-neutral IdpResult-to-benchmark adapter and CLI
- Recognition-only contracts and Vietnamese NFC audit with 134 characters
- CER, WER, Exact Match, Diacritic Error Rate and accepted precision
- Fixed 240-line synthetic Vietnamese crop corpus at 300 DPI in private-data
- PaddleOCR, EasyOCR and VietOCR evaluated on one dataset digest
- EasyOCR `vi` selected for pilot: 82.92% Exact Match, 0.89% CER, 0.00% DER
- EasyOCR/VietOCR agreement: 143/240 lines at 100% agreement precision
- Hybrid orchestration: Paddle primary → EasyOCR/VietOCR independent verifiers
- Disagreement policy preserves the EasyOCR candidate and sets `needs_review`
- Authorized real-scan pilot: 15 reviewed CCCD, 671 detected line crops
- Real-scan agreement: 18/671 lines (2.68%); decision `NOT_PROMOTED`
- Phase 14.1 corpus: 4 authorized documents and 77 user-confirmed line crops
- VietOCR `vgg_seq2seq`: 42.86% Exact Match, 15.59% CER and 0.77% DER
- Phase 14.1 decision: controlled pilot only; `NOT_PRODUCTION_READY`
- Phase 14.2 processed 51 authorized sessions and 2,150 line crops without failure
- Exact verifier agreement accepted 188/2,150 lines; 1,962 need review
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
- Real-scan pilot is only 15 CCCD and does not cover the HR document portfolio
- Phase 13.3 document CER is 68.74%; detector/crop/recognizer chain needs diagnosis
- Verifier agreement is not calibrated as correctness evidence on real scans
- Phase 14.1 covers only four documents; it does not represent the HR portfolio
- No Camunda deployment, review UI or HRM/BPM side effect
- Camunda environment link and deployment evidence remain pending

Key commands:
- `python -m unittest discover -s tests -v`
- `python -m ruff check src tests scripts`
- `python -m mypy src`
- `python scripts/check_repository.py`
- `hcns-agent-benchmark evaluate --ground-truth <file> --predictions <file> --output <file>`

Next:
- Expand Ground Truth beyond the four Phase 14.1 documents
- Measure controlled-pilot accuracy; operational coverage is not accuracy
- Repeat the protocol on authorized real CV, contract, leave and timesheet scans
- Calibrate EasyOCR/VietOCR confidence before changing auto-accept thresholds
- Obtain approval/manifest for a fixed 30–50 page document Ground Truth outside Git
- Run PaddleOCR baseline and MinerU document challenger on the same dataset digest
- Review aggregate comparison; do not promote until every gate passes
- M4 Camunda generation selection, SDK worker and BPMN dry-run
