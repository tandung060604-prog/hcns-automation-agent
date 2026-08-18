# Project State

Current milestone: UX-001 WORKSPACE REFRESH / VERIFIED LOCAL
Checkpoint task: `UX-001`
Next READY task: `CAM-001` is BLOCKED pending an authorized Contract upload

Repository:
- Branch: `codex/alg-002-canonical-parser`
- Base at task start: `cfbdd78`; `origin/main` is now `b07c879` with a
  Plan.md-only delta. Implementation is not committed or pushed.
- ALG-001 PR #35 and corrective PERF-001 PR #37 are merged into `main` with CI green.

## UX-001 workspace refresh (2026-08-14)

- `/workspace` now uses a product-first navy/white interface with one cyan
  accent. Navigation exposes Overview, Intake, Review Queue, Evidence and the
  local Camunda Tasklist without changing any API or process contract.
- The page explains the five runtime layers, the Contract/CV/IELTS scope,
  DATA-29 development-only metrics and the local-shadow workflow before the
  existing operational panels. The upload workspace remains the same local,
  private flow and is visually wider and easier to scan.
- The hero uses the existing local no-PII context asset. It does not render a
  Contract, CV or IELTS source document and does not introduce external asset
  requests.
- Responsive navigation remains available as a horizontal mobile rail;
  reduced-motion behavior is preserved. Browser inspection at 1280px found no
  horizontal overflow.

## PDF-001 PDF scan gate (2026-08-14)

- PDF page inspection now distinguishes native, scan and mixed profiles. Mixed
  documents route to the scan/manual-review path; the authorized corpus had 2
  native and 1 scan PDF, with mixed covered by a PII-free regression fixture.
- Scan rasterization is consumed page-by-page, and canonical EasyOCR uses the
  bounded `canvas_size=1280`, `mag_ratio=1.3` configuration.
- One cold plus 30 warm isolated samples completed with zero failures. Warm total
  p50/p95: `9.378/12.532 s`; OCR p50/p95: `7.918/10.945 s`; peak RSS p95:
  `1.694 GB`; peak Python heap p95: `66.2 MB`.
- The authorized PDF_SCAN quality slice reached `9/10` exact required fields,
  `10/10` accepted, `9/9` applicable present, classification `1/1`, and manual
  review `1/1`. Promotion remains disabled.
- Private aggregate report:
  `C:\tmp\pdf001-template-scan-report-20260814-v6.json`.

## ALG-002 canonical parser (2026-08-14)

- Contract, CV and IELTS now share parser ID `structured-hr/family-layout`,
  version `2.1.0`, through the existing `TemplateRegistry`.
- User upload and the DATA-29 adapter call one promoted field parser. A delegation
  test fails if the evidence adapter drifts back to a separate implementation.
- Native PDF lines, CV multi-column geometry, Contract party boundaries and IELTS
  review-only layout rules are preserved. English Contract labels remain backward
  compatible with the Camunda acceptance fixtures.
- Health/manifest/prediction metadata expose the same parser identity. No raw
  field, private path or content was added to public metadata.

## Quality and provenance

- Authorized Contract + CV replay is verified on all `8` documents: `87/92`
  strict and `92/92` accepted; Contract `42/42`, CV `45/50` and `50/50` accepted.
- Isolated Paddle replay is verified on all `4` IELTS documents: `20/20` strict
  and `20/20` accepted with parser `structured-hr/family-layout/2.1.0`.
- The full offline hybrid replay completed on 12 documents at `107/112` strict
  and `112/112` accepted under matching policy `2.0.0`: Contract `42/42`, CV
  `45/50`, IELTS `20/20`.
- OCR exact was `29/30`, applicable presence was `99/99`, and schema errors,
  parser regressions and sensitive false acceptance were all zero.
- The EasyOCR child is isolated from the Paddle parent; local VietOCR config is
  loaded explicitly. CV skill sections keep EasyOCR text to avoid line-refine
  list noise; other narrative lines retain refinement.
- Ground Truth, sealed prediction and sealed report were not changed.

## Verification

- Python `550 passed`; ALG-002 targeted tests `30 passed`; targeted Ruff and
  parser mypy checks pass; compileall, repository hygiene and diff checks pass.
- Web build and rendered tests `15/15`; ESLint `0` errors with `22` warnings;
  production dependency audit reports `0` vulnerabilities.
- Full-repository Ruff/mypy retain legacy findings outside ALG-002 (105 Ruff
  findings and 6 unused-ignore findings); no unrelated cleanup was mixed in.

## Active product/runtime state

- Default runtime remains Template-first + EasyOCR; Paddle is explicit rollback.
- `autoContinueEnabled=false`; HRIS and notifications remain simulated.
- The original dirty worktree and unrelated CORS/VITE/CCCD files are untouched;
  PDF-001 changes are limited to the canonical PDF intake, EasyOCR adapter and
  aggregate benchmark runner.
- CCCD held-out, Contract images and production pilot remain closed.

Next action: resolve the blocked authorized Contract E2E (`CAM-001`). Production
pilot, CCCD held-out and Contract-image expansion remain closed until their
independent data/quality gates pass.

Archive: prior state is in `docs/archive/PROJECT_STATE_HISTORY_2026-08-13.md`.
