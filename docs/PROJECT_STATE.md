# Project State

Current milestone: M3 / Phase 14.5 — conditional OCR fallback analysis

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
- Hybrid orchestration: Paddle primary → EasyOCR/VietOCR independent verifiers
- Disagreement policy preserves the EasyOCR candidate and sets `needs_review`
- Authorized real-scan pilot: 15 reviewed CCCD, 671 detected line crops
- Real-scan agreement: 18/671 lines (2.68%); decision `NOT_PROMOTED`
- Phase 14.5 stratified all 214 seq2seq errors without publishing private text
- Document-level fallback replay: 44.34% Exact, 15.36% CER and 2.01% DER
- Fallback recovered 44 errors but lost two correct lines; `SHADOW_REVIEW_ONLY`
- Phase 14.2 processed 51 authorized sessions and 2,150 line crops without failure
- Exact verifier agreement accepted 188/2,150 lines; 1,962 need review
- Phase 14.3 kept `bbox_balanced_64`: 42.86% Exact Match and 15.29% CER
- Of 44 errors, alternate VietOCR crops recover only two by oracle
- Phase 14.4 corpus: 15 authorized documents and 309 confirmed line crops
- Seq2seq: 30.74% Exact, 18.19% CER; Transformer: 27.18% Exact, 14.16% CER
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
- Phase 14.5 fallback still regresses DER and two baseline-correct lines
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
- Repeat the frozen fallback on new held-out authorized documents
- Require zero baseline-correct loss before any controlled auto-selection
- Repeat the protocol on authorized real CV, contract, leave and timesheet scans
- Calibrate EasyOCR/VietOCR confidence before changing auto-accept thresholds
- Obtain approval/manifest for a fixed 30–50 page document Ground Truth outside Git
- Run PaddleOCR baseline and MinerU document challenger on the same dataset digest
- Review aggregate comparison; do not promote until every gate passes
- M4 Camunda generation selection, SDK worker and BPMN dry-run
