# Project State

Current milestone: M3 / Phase 14.6 — frozen held-out OCR evaluation readiness

Completed:
- M1 Universal Document Intake, safety, canonical model and native/OCR routing
- Independent SourceFormat/DocumentType/WorkflowType with vendor-neutral ports
- Deterministic classifier and extractors for CV, contract, leave and timesheet
- Quality score/status with explicit Human Review reasons
- Business JSON schema 2.0.0 with classification/quality/field provenance
- Offline benchmark Ground Truth/prediction/report/comparison schemas 1.0.0
- Baseline/challenger promotion gate with privacy/license/provenance evidence
- Recognition-only contracts and Vietnamese NFC audit with 134 characters
- Hybrid orchestration: Paddle primary → EasyOCR/VietOCR independent verifiers
- Disagreement policy preserves the EasyOCR candidate and sets `needs_review`
- Authorized real-scan pilot: 15 reviewed CCCD, 671 detected line crops
- Real-scan agreement: 18/671 lines (2.68%); decision `NOT_PROMOTED`
- Phase 14.5 stratified all 214 seq2seq errors without publishing private text
- Canonical LODO fallback replay: 40.13% Exact, 16.91% CER and 11.02% DER
- LODO recovered 30 errors but lost one correct line; `SHADOW_REVIEW_ONLY`
- Canonical metric spec `vi-ocr-metrics/1.0.0` shared across Phase 14 adapters
- Versioned recognition policies never auto-replace text in shadow mode
- Phase 14.6 lock pins policy, crop and SHA-256 for three local model artifacts
- Held-out runner seals predictions, rejects Ground Truth leakage and evaluates once
- OCR Lab source is tracked under `apps/ocr_lab` with Python and web CI
- Upload content safety and F5/resume behavior have executable tests
- Phase 14.3 kept `bbox_balanced_64`: 42.86% Exact Match and 15.29% CER
- Phase 14.4 corpus: 15 authorized documents and 309 confirmed line crops
- Seq2seq: 30.74% Exact, 18.19% CER; Transformer: 27.18% Exact, 14.16% CER
- 101 synthetic unit/contract/safety/architecture/benchmark tests
- Ruff, strict mypy, compile and repository hygiene gates

Architecture:
- IDP reads/understands; Agent analyzes/proposes; Camunda orchestrates
- SourceFormat selects parser; DocumentType selects extractor
- Benchmark compares every backend through the same IdpResult contract
- Benchmark report is aggregate-only and contains no raw field values
- Camunda owns BPMN, User Task, timer, retry, escalation and process state
- Camunda 7 BPMN/DMN reference package added for review and dry-run

Security:
- No real PII, private-data, upload, OCR output or model weights added
- Business JSON and canonical content stay behind result references
- Ground Truth/predictions stay outside Git; report requires disclosure review

Known limits:
- Rule classifier/extractors are architecture baselines, not accuracy-promoted models
- Supported extractors: CV, employment contract, leave request and timesheet
- Administrative/other types require review until an extractor is approved
- PPTX remains text-by-slide; legacy DOC/XLS require safe conversion
- Real-scan pilot is only 15 CCCD and does not cover the HR document portfolio
- Phase 14.5 fallback still regresses DER and one held-out baseline-correct line
- Historical Phase 14 DER used a legacy denominator and must not be compared
  directly with metric spec 1.0.0
- Verifier agreement is not calibrated as correctness evidence on real scans
- No Camunda deployment, review UI or HRM/BPM side effect
- Camunda environment link and deployment evidence remain pending

Key commands:
- `python -m unittest discover -s tests -v`
- `python -m ruff check src tests scripts`
- `python -m mypy src`
- `python scripts/check_repository.py`
- `python scripts/validate_phase14_6_lock.py --private-runtime <path> --paddle-model <path>`
- `cd apps/ocr_lab/web && npm test`
- `hcns-agent-benchmark evaluate --ground-truth <file> --predictions <file> --output <file>`

Next:
- Collect at least 15 new held-out authorized documents
- Verify the frozen lock, generate hidden predictions, then confirm Ground Truth
- Evaluate once without threshold, crop or policy retuning
- Require zero baseline-correct loss before any controlled auto-selection
- Repeat the protocol on authorized real CV, contract, leave and timesheet scans
- Calibrate EasyOCR/VietOCR confidence before changing auto-accept thresholds
- Obtain approval/manifest for a fixed 30–50 page document Ground Truth outside Git
- Run PaddleOCR baseline and MinerU document challenger on the same dataset digest
- Review aggregate comparison; do not promote until every gate passes
- M4 Camunda generation selection, SDK worker and BPMN dry-run
