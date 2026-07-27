# Project State

Current milestone: M3 / Phase 14 — real-scan OCR hardening and line review

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
- Recognition-only Ground Truth/prediction/report contracts
- Vietnamese NFC charset audit with 134 extended characters
- CER, WER, Exact Match, Diacritic Error Rate and accepted precision
- Fixed 240-line synthetic Vietnamese crop corpus at 300 DPI in private-data
- PaddleOCR, EasyOCR and VietOCR evaluated on one dataset digest
- EasyOCR `vi` selected for pilot: 82.92% Exact Match, 0.89% CER, 0.00% DER
- EasyOCR/VietOCR agreement: 143/240 lines at 100% agreement precision
- Hybrid orchestration: Paddle primary → EasyOCR/VietOCR independent verifiers
- Disagreement policy preserves the EasyOCR candidate and sets `needs_review`
- Authorized real-scan pilot: 15 reviewed CCCD, 671 detected line crops
- Real-scan agreement: 18/671 lines (2.68%); decision `NOT_PROMOTED`
- Phase 14 provisional line corpus: 4 reviewed documents, 77 index-aligned crops
- Paddle raw: 75.32% Exact Match, 6.82% CER, 1.60% DER
- Best EasyOCR crop profile: 5.19% Exact Match and 44.33% CER
- VietOCR on the best crop: 20.78% Exact Match and 33.33% CER
- Paddle confirmed by at least one verifier: 7/77 at 100% provisional precision
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
- Phase 14 line alignment is provisional until every crop is reviewed directly
- No Camunda deployment, review UI or HRM/BPM side effect
- Camunda environment link and deployment evidence remain pending

Key commands:
- `python -m unittest discover -s tests -v`
- `python -m ruff check src tests scripts`
- `python -m mypy src`
- `python scripts/check_repository.py`
- `hcns-agent-benchmark evaluate --ground-truth <file> --predictions <file> --output <file>`

Next:
- Complete localhost review for the 77 provisionally aligned private crops
- Expand line-level review to the remaining 594 Phase 13.3 crops
- Keep Paddle as primary; do not replace it with EasyOCR/VietOCR
- Repeat the protocol on authorized real CV, contract, leave and timesheet scans
- Calibrate EasyOCR/VietOCR confidence before changing auto-accept thresholds
- Obtain approval/manifest for a fixed 30–50 page document Ground Truth outside Git
- Run PaddleOCR baseline and MinerU document challenger on the same dataset digest
- Review aggregate comparison; do not promote until every gate passes
- M4 Camunda generation selection, SDK worker and BPMN dry-run
