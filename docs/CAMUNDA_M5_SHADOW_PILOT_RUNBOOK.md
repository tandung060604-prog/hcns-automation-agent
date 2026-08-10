# M5-CAM-001 — Camunda review-first shadow pilot

Status: `LOCAL_PREFLIGHT_PASS / AUTHORIZED_SYNTHETIC_ONLY`, not production approval.

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

## Authorization record (synthetic-only; real cohort not approved)

The following fields are the minimum authorization packet. The current record
authorizes only the two synthetic cases below; a real cohort remains
`PENDING_OWNER_INPUT` and is not authorized:

| Field | Required value | Current state |
|---|---|---|
| Owner | accountable synthetic business-owner role ID | `m5-synthetic-business-owner` |
| Reviewer | independent synthetic reviewer role ID | `m5-independent-synthetic-reviewer` |
| Cohort | synthetic IDs or approved document-family scope | `SYNTHETIC_ONLY` |
| Time window | start/end with timezone | `2026-08-10 15:55–18:00 +07:00` |
| Retention | private-store expiry and deletion owner | `2026-08-17 23:59:59 +07:00; owner role` |
| Rollback authority | named role and trigger | `owner role; any safety-gate violation` |
| Side effects | HRIS/notification writes | `DISABLED` |
| Review policy | every result and every scan | `MANUAL_REVIEW` |
| DATA-24 | old evaluate-once/GT | `IMMUTABLE; NOT OPENED` |

These are synthetic governance role IDs, not personal identities or production
approval. The private authorization record is
`C:\Camunda\private-data\m5-cam-001\authorization\M5-CAM-001-AUTHORIZATION.json`.
It must never be used to open a real cohort or enable side effects.

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

M5-CAM-001A and M5-CAM-001B completed this local preflight on 2026-08-10 with two synthetic native
DOCX sources only. Both reached `UserReview` and completed the simulated flow;
`AUTO_CONTINUE=0`, raw exposure `0`, duplicates `0`, unreconciled cases `0`, real
side effects `0`, and both cases completed below 60 seconds. It does not authorize
a real cohort.

M5-CAM-001B also projects Phase15 metadata through the sanitized scalar/reference
boundary. It rejects raw fields and filesystem paths, and supplies an opaque
result reference instead of Phase15's private artifact path.

M5-CAM-001C validates authorization enforcement without opening a real cohort:
the active synthetic run passes, an expired authorization is refused before any
Camunda process start, and a simulated `autoContinueCount > 0` violation returns
fail-closed rollback. The aggregate smoke report is private-only at
`C:\Camunda\private-data\m5-cam-001c\reports\m5-cam-001c-auth-smoke.json`.

For a new local-only synthetic run, start the approved local Camunda 7.13 runtime
and write the create-only aggregate report outside the repository:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts/run_camunda_m5_shadow_preflight.py `
  --camunda-url http://127.0.0.1:8080/engine-rest `
  --private-root C:\Camunda\private-data\m5-cam-001a `
  --output C:\Camunda\private-data\m5-cam-001a\reports\m5-shadow-preflight.json
```

Run the authorization smoke only with the private synthetic record:

```powershell
.\.venv\Scripts\python.exe scripts/run_camunda_m5_authorization_smoke.py `
  --camunda-url http://127.0.0.1:8080/engine-rest `
  --authorization C:\Camunda\private-data\m5-cam-001\authorization\M5-CAM-001-AUTHORIZATION.json `
  --private-root C:\Camunda\private-data\m5-cam-001c `
  --output C:\Camunda\private-data\m5-cam-001c\reports\m5-cam-001c-auth-smoke.json
```

Do not use `C:\tmp` in the runbook. A dependency profile may be used only as a local troubleshooting fallback; it is not a gate artifact.

## Cohort sequence

1. Run leave/overtime shadow only after the owner signs cohort, retention and rollback.
2. Finish Ground Truth and authorization for CV, IELTS, probation contract and front-ID; run evaluate-once aggregate-only.
3. Open one family at a time. Stop on any safety-gate violation and keep process/private evidence for incident review.
4. Close out with aggregate counts for routing, retry, re-upload, review, incident, p95 latency and reconciliation. Never export raw OCR or field values.

There is no production, auto-approval or HRIS-write date in M5.
