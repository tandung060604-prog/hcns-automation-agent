# Camunda M5 — review-first cho 6 loại tài liệu HCNS

## Trạng thái

M4 đã dry-run 10/10 và bộ test Camunda hiện có 37/37 pass cho leave/overtime. M5 mở allowlist thành đúng sáu workflow type nhưng chưa chạy cohort thật, chưa auto-decision và chưa ghi HRIS.

## Closed set

| Workflow type | Template | Route mặc định |
|---|---|---|
| `LEAVE_REQUEST` | `leave-request-v1` | `USER_REVIEW` hoặc `HR_REVIEW` theo DMN |
| `OVERTIME_REQUEST` | `overtime-request-v1` | `USER_REVIEW` hoặc `HR_REVIEW` theo DMN |
| `CV` | `cv-v1` | `HR_REVIEW` |
| `CERTIFICATE` | `ielts-certificate-v1` | `HR_REVIEW` |
| `EMPLOYMENT_CONTRACT` | `probation-contract-v1` | `HR_REVIEW` |
| `IDENTITY_DOCUMENT` | `vietnam-citizen-id-front-v1` | `HR_REVIEW`; front only |

Timesheet is retired: no enum, classifier/extractor, business schema, policy, API, dashboard or active test may advertise it. Historical private artifacts remain outside the active manifest for traceability.

## Contract and safety

One BPMN and one DMN are reused. BPMN form allowlists contain only the six values; back-side ID, unknown, mismatch and generic input fail closed. Camunda variables are scalar/reference-only and never contain raw file, OCR or field values. `autoContinueEnabled=false`; HRIS and notification are simulated; result is private and stored before `complete`; idempotency and correction/re-upload audit remain mandatory.

## Template-first implementation

The four new templates are versioned and have explicit anchors, parser, validator, schema and provenance. They are review-only: missing fields fail closed, extracted values remain private, and no field is automatically accepted. IELTS is a `CERTIFICATE`; probation contract is an `EMPLOYMENT_CONTRACT`; citizen ID accepts only the front image.

## Gates

- Global: auto-continue 0, real side effects 0, raw-value exposure 0, duplicate results 0, schema/whitelist errors 0.
- Leave/overtime: classification 100%, native exact 100%, OCR required-field exact >=80%, schema errors 0, OCR always review.
- CV/IELTS/probation: >=15 authorized documents per family, blind independent Ground Truth review 100%, schema errors 0, held-out classification >=95%; OCR is review suggestion only.
- Citizen-ID front: >=15 eligible front images (current evidence 14), blind review 100%, every sensitive field reviewed, no automatic acceptance.
- Pilot: owner signs cohort/reviewer/retention/time window/rollback; preflight, health check and dry-run pass; p95 image/PDF scan <=60 seconds; no unreconciled case.

## Execution order

1. Keep leave/overtime in shadow only after business authorization.
2. Complete pending Ground Truth and authorized cohorts for the four new families.
3. Evaluate once aggregate-only, then open one family per cohort and close out before the next.

No production or auto-approval date is part of M5.
