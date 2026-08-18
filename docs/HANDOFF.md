# Handoff

## Current checkpoint (2026-08-14)

- Branch: `codex/alg-002-canonical-parser`
- Base at task start: `cfbdd78`; `origin/main` is now `b07c879` with a
  Plan.md-only delta. Changes are not committed or pushed.
- Checkpoint task: `UX-001`
- Status: workspace product redesign verified locally; PDF scan promotion remains HOLD.
- Next action: `CAM-001` remains blocked until the user provides an authorized
  Contract for live E2E; CCCD and Contract-image expansion remain closed.

## UX-001 workspace checkpoint

- The operational workspace now follows one navy/white/cyan visual system with
  a focused hero, five-layer platform rail, Contract/CV/IELTS scope, DATA-29
  quality boundary, local-shadow timeline, review queue and wide upload area.
- Header links preserve the existing anchors and add the correct local Camunda
  Tasklist URL. Mobile keeps navigation in a horizontal rail instead of hiding
  it completely.
- API calls, extraction, Evidence Explorer, private storage and
  `autoContinueEnabled=false` are unchanged. The hero only uses the existing
  local no-PII context asset.
- Verified: workspace/API/Tasklist HTTP `200`, EasyOCR with six health pipelines,
  no desktop horizontal overflow, web build and rendered tests `15/15`, ESLint
  `0` errors with `22` warnings.

## PDF-001 evidence

- The PDF classifier distinguishes native, scan and mixed page profiles. Mixed
  PDFs use the scan/manual-review path. The authorized corpus profile count was
  native `2`, scan `1`; mixed is covered by a PII-free regression fixture.
- PyMuPDF rasterization is lazy page-by-page rather than retaining all rendered
  PNG pages. Canonical EasyOCR is bounded by `canvas_size=1280` and
  `mag_ratio=1.3`.
- One cold plus 30 warm isolated samples completed with zero failures. Warm total
  p50/p95 is `9.378/12.532 s`; OCR p50/p95 is `7.918/10.945 s`; peak RSS p95 is
  `1.694 GB`; peak Python heap p95 is `66.2 MB`.
- The real PDF_SCAN quality slice is `9/10` exact required fields, `10/10`
  accepted and `9/9` applicable present. Classification is `1/1`, manual review
  is `1/1`, and sensitive false acceptance is `0`.
- Aggregate report:
  `C:\tmp\pdf001-template-scan-report-20260814-v6.json`.

## What is implemented

1. Contract, CV and IELTS registry entries use
   `structured-hr/family-layout` version `2.1.0`.
2. Template-first upload and the DATA-29 prediction adapter call the same
   `extract_structured_hr_fields` implementation.
3. The parser keeps native PDF line boundaries, multi-column CV geometry,
   bounded Contract parties and review-only IELTS layout handling.
4. Registry, health manifest and prediction metadata expose the same parser
   identity. CCCD, Camunda policy and matching policy are unchanged.

## Verified evidence

- Authorized Contract + CV replay: `8` documents, `87/92` strict and `92/92`
  accepted. Contract is `42/42`; CV is `45/50` strict and `50/50` accepted.
- Isolated Paddle replay: all `4` IELTS documents reached `20/20` strict and
  `20/20` accepted through parser `structured-hr/family-layout/2.1.0`.
- Full offline hybrid replay: `12` documents reached `107/112` strict and
  `112/112` accepted under matching policy `2.0.0`; Contract `42/42`, CV
  `45/50`, IELTS `20/20`.
- OCR exact was `29/30`; applicable presence was `99/99`; schema errors,
  parser regressions and sensitive false acceptance were all zero.
- Ground Truth, sealed prediction and report hashes remain unchanged.
- Gates: Python `550 passed`; ALG-002 targeted tests `30 passed`; targeted Ruff
  pass; targeted mypy pass for the two parser files; compile/hygiene pass; web
  build and rendered tests `15/15`; ESLint `0` errors (`22` warnings);
  production dependency audit `0` vulnerabilities.
- Full-repository Ruff/mypy still report legacy findings outside ALG-002 (105
  Ruff findings and 6 unused-ignore findings); no unrelated cleanup was mixed
  into this task.

## Closed gate

- `IELTS-OCR-001` is closed: the EasyOCR child uses isolated private
  site-packages, local VietOCR config is loaded explicitly, and the broken
  parent venv is not used.
- The CV skill-section refinement guard prevents a known OCR list-layout
  regression while preserving refinement for narrative lines.
- The replay completed with no residual replay process. Promotion remains
  disabled by design; this does not open production or real side effects.

## Scope boundaries

- The original dirty worktree and all unrelated CORS/VITE/CCCD files remain
  untouched. Raw documents and per-field results remain private outside Git.
- `autoContinueEnabled=false`; HRIS and notifications remain simulated.
- CCCD held-out, Contract images, production pilot and real side effects remain
  closed.
