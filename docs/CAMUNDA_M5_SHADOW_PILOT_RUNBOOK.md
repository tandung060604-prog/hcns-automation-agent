# M5-CAM-001 — Camunda review-first shadow pilot

Status: `READY_FOR_AUTHORIZATION`, not production approval.

## Scope

The active closed set is exactly:

- `LEAVE_REQUEST` — `leave-request-v1`
- `OVERTIME_REQUEST` — `overtime-request-v1`
- `CV` — `cv-v1`
- `CERTIFICATE` — `ielts-certificate-v1`
- `EMPLOYMENT_CONTRACT` — `probation-contract-v1`
- `IDENTITY_DOCUMENT` — front-side only, `vietnam-citizen-id-front-v1`

Timesheet is removed from code, schema, API, dashboard and active tests. Citizen-ID back side, unknown, mismatch and generic documents fail closed to `REQUEST_REUPLOAD` or `Confirm Type`; there is no generic fallback.

## Non-negotiable safety gate

`autoContinueEnabled=false`, real HRIS/notification side effects are `SIMULATED`, Camunda receives only scalar status/reference variables, and private result storage completes before the process is completed. The pilot must show zero auto-continue, zero raw-value exposure, zero duplicate result, zero schema/whitelist error and no unreconciled case.

## Family gates

| Family | Gate before cohort |
|---|---|
| Leave / overtime | classification 100%; native required-field exact 100%; OCR required-field exact >=80%; schema errors 0; OCR always review |
| CV / IELTS / probation contract | >=15 authorized documents; prediction hidden before independent Ground Truth; review 100%; schema errors 0; held-out classification >=95%; OCR fields are review suggestions only |
| Citizen-ID front | >=15 eligible front images (current evidence: 14); blind Ground Truth review 100%; every sensitive field reviewed; no automatic acceptance |

Business owner must record cohort, reviewer, retention, time window and rollback authority outside the repository. Pilot performance target is p95 <=60 seconds for an image or scanned PDF and zero unreconciled cases.

## Local preflight

Use the declared `.venv` profile from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,easyocr]"
$env:PYTHONPATH = "src;tests"
.\.venv\Scripts\python.exe -m pytest -q tests/test_camunda_contract.py tests/test_camunda_assets.py tests/test_camunda7_adapter.py tests/test_camunda7_runtime.py tests/test_camunda_m4_dry_run.py
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy --no-incremental --no-sqlite-cache --cache-dir .venv/mypy src
.\.venv\Scripts\python.exe scripts/check_repository.py
.\.venv\Scripts\python.exe scripts/run_camunda_m4_dry_run.py
```

Do not use `C:\tmp` in the runbook. A dependency profile may be used only as a local troubleshooting fallback; it is not a gate artifact.

## Cohort sequence

1. Run leave/overtime shadow only after the owner signs cohort, retention and rollback.
2. Finish Ground Truth and authorization for CV, IELTS, probation contract and front-ID; run evaluate-once aggregate-only.
3. Open one family at a time. Stop on any safety-gate violation and keep process/private evidence for incident review.
4. Close out with aggregate counts for routing, retry, re-upload, review, incident, p95 latency and reconciliation. Never export raw OCR or field values.

There is no production, auto-approval or HRIS-write date in M5.
