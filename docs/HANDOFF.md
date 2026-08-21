# Handoff

## Current checkpoint (2026-08-21)

- Reference branch: `main` / `3c48ac2`; active maintenance branch:
  `codex/repository-governance`.
- Task: repository hygiene and documentation refresh; no parser, OCR policy,
  schema, Camunda behavior or private corpus was changed.
- Removed two unreferenced frontend panels and one unreferenced legacy policy;
  moved v1 DOCX masters to `docs/archive/templates-v1/`.
- Root README now routes users to local startup, private dataset boundaries,
  tests and the canonical documentation map. GitHub Pages now packages the four
  current blank DOCX downloads with its static artifact.
- Validation: `python scripts/check_repository.py`, focused pytest `9 passed`,
  frontend `npm test` `16/16`, and lint `0` errors (`22` existing warnings).

## Previous DATA-31 recovery notes

### DATA-31 Quality Recovery R4 — 2026-08-20

- Added bounded `label-crop-v1` recovery to the existing EasyOCR adapter. It
  re-reads only detected IELTS name/result rows, scales short-name crops when
  needed, restores source geometry and keeps manual review. No new engine,
  dependency, document-specific value or matching-policy change was added.
- Preserved the source conjunction in CV desired-role extraction instead of
  rewriting it to `/`.
- Fresh private 13-document replay with parser `2.2.6` reached `93/109` strict,
  `100/109` accepted and `106/109` present; `schemaErrors=0`, parser
  regression `0`, sensitive false acceptance `0`.
- By family: Contract `34/44` exact, CV `39/45` exact and IELTS `20/20`
  exact/accepted/present. IELTS OCR residuals are cleared; Contract/CV remain
  below the DATA-31 gate because of locked title/workplace semantics, native
  field boundaries, long text and one malformed Ground Truth token.
- Evidence: `D:\document_ai_hr_dataset\.reviews\DATA-31\report-r4e-20260820.json`
  and `summary-r4e-20260820.json`. Reports are aggregate-only and remain
  outside Git. CAM-001 remains blocked until `105/109 strict` and `109/109`
  accepted pass.

### DATA-31 IELTS crop gate — 2026-08-20

- Fresh private baseline on the four IELTS cases, parser
  `structured-hr/family-layout/2.2.5`, EasyOCR `canvas=1280`, `mag=1.3`,
  `preprocess=none`: `18/20` strict, `18/20` accepted and `19/20` present.
  All `30/30` warm samples completed without failure; warm p95 was `18.800 s`
  total, `17.994 s` OCR and `1.263 GB` RSS.
- Hi-res `canvas=2560` candidate did not produce an aggregate report after
  more than ten minutes. Observed RSS exceeded `2.2 GB`; the process was
  stopped safely and no accuracy claim was made. Candidate decision:
  `NOT_PROMOTED`.
- Evidence: `D:\document_ai_hr_dataset\.reviews\DATA-31\ielts-crop-benchmark-r3-baseline-20260820.json`.
  No raw OCR, field values, PII or private paths are exposed in the report.
- Product remains on the 1280 default; DATA-31 is still below `105/109`
  strict and `109/109` accepted, so CAM-001 remains blocked.

## DATA-31 IELTS OCR recovery R3 (2026-08-20)

- Parser `structured-hr/family-layout/2.2.5` adds a structural TRF/Form Number
  rule: it prefers the labelled footer token, rejects arbitrary score-row text,
  and repairs only OCR digit confusions supported by the same-form six-digit
  Candidate Number. Synthetic regression coverage passed.
- Fresh private replay with the existing EasyOCR `1280` default reached
  `90/109` strict, `98/109` accepted and `105/109` present; `schemaErrors=0`,
  parser regressions `0`, sensitive false acceptance `0`.
- IELTS reached `18/20` strict. The remaining two are true OCR omissions: one
  family name and one Overall Band score. Aggregate evidence is private at
  `D:\document_ai_hr_dataset\.reviews\DATA-31\report-r3-20260820.json` and
  `summary-r3-20260820.json`.
- A direct 2560-canvas probe recovered the Overall score in one sample, but it
  is not promoted and is not DATA-31 gate evidence. CAM-001 remains blocked
  until both `105/109 strict` and `109/109 accepted` pass.

## Implementation

- Added additive benchmark parameters for PDF DPI, EasyOCR canvas size and
  magnification ratio. Defaults remain `150`, `1280` and `1.3`.
- The selected profile is passed through the existing Template-first service,
  PyMuPDF rasterizer and EasyOCR adapter. The runtime report records the
  profile without exposing source paths, OCR text or field values.
- Added regression coverage for the 2560 EasyOCR canvas profile. No product
  default, API schema, parser policy or Camunda behavior was promoted.
- Added the benchmark-only `content-roi-autocontrast-v1` profile. It uses a
  bounded content crop plus grayscale/autocontrast, restores box offsets and
  leaves the product default at `none`.

## Verified benchmark

- Cohort/model: one authorized DATA-29 PDF_SCAN; EasyOCR 1.7.2 `vi-greedy`,
  parser `structured-hr/family-layout/2.1.1`, matching policy `2.0.0`.
- Baseline 150/1280: `9/10` strict, `10/10` accepted; total p95 `12.500 s`,
  OCR p95 `10.907 s`, RSS p95 `1.266 GB`, heap p95 `66.2 MB`.
- Candidate 200/2560: `8/10` strict, `10/10` accepted; total p95 `50.657 s`,
  OCR p95 `48.441 s`, RSS p95 `3.485 GB`, heap p95 `199.0 MB`.
- Both profiles completed `30/30` warm samples with zero failures and retained
  `MANUAL_REVIEW`. Candidate quality regressed and resource cost increased;
  it is not promoted.
- Supporting authorized Contract probe: baseline `13/14` strict, candidate
  `10/14` strict; both had `14/14` present and stayed manual review.

## PDF-001B result

- On the authorized Contract, baseline `none` scored `14/14` present,
  `13/14` strict and `14/14` accepted. The bounded ROI/autocontrast candidate
  scored `13/14` present, `10/14` strict and `12/14` accepted.
- Candidate is `NOT_PROMOTED` because quality regressed. Candidate p95/RAM was
  not used as promotion evidence; a duplicated isolated run was discarded
  after exact process verification. Product remains 150 DPI / 1280 / `none`.

## PDF-001C result

- Seven authorized PDF scans were evaluated with user-confirmed private Ground
  Truth: `96/98` present, `67/98` strict, `82/98` accepted, 0 technical errors,
  and 7/7 manual review. Strict rate `68.4%` fails the 80% scan gate.
- Fourteen DOCX and seven native PDF controls processed successfully with zero
  technical errors. Scan-cohort p95/RAM is `NOT MEASURED`; the long run was
  stopped before completion and partial numbers were discarded.

## ALG-004 result

- A private replay of the seven scans reproduced all `31` strict mismatches and
  wrote only aggregate evidence. Classification: `15` normalization/policy-
  accepted, `10` parser boundary, `6` OCR recognition, `0` Ground Truth review.
- The accepted group contains `7` cases with full Ground Truth token coverage
  and `8` over-extractions. Compact Ground Truth evidence was located for `24`
  mismatches and not located for `7`; Ground Truth status is confirmed.
- The safe report is outside Git. It contains no document IDs, source paths,
  field values or OCR text. No preprocessing profile was tried or promoted.

## ALG-005 result

- Parser `structured-hr/family-layout/2.1.2` fixes the confirmed OCR label and
  salary boundaries with synthetic regression coverage.
- Seven authorized PDF scans replayed at EasyOCR 150 DPI / 1280 / `none`:
  `98/98` present, `69/98` strict, `84/98` accepted, 0 technical errors and
  7/7 manual review. The strict gate remains HOLD.
- Residual strict mismatches are `15` normalization/policy-accepted, `10` OCR
  recognition, `4` competing job-title labels and `0` Ground Truth review.
  Role precedence is deliberately unchanged because it regresses Contract 23.

## ALG-006 result

- Canonical policy: `Chức danh chuyên môn` wins when populated; `Chức vụ/Vị trí`
  is a fallback only when the professional-title value is missing. No
  document-specific exception, OCR profile or localhost route was promoted.
- Parser and manifest are `structured-hr/family-layout/2.1.3`. The private
  aggregate-only replay is `D:\document_ai_hr_dataset\.reviews\PDF-001C\alg006-replay.json`.
- Replay: `98/98` present, `69/98` strict, `84/98` accepted, 0 technical errors,
  7/7 manual review. The strict rate is `70.4%`, so the quality gate remains
  HOLD and CAM-001 must not start.

## PDF-001D result

- Parser `structured-hr/family-layout/2.1.4` adds only general OCR recovery for
  observed allowance labels/units, employer tokens and person-name diacritics;
  no private value or document-specific branch was added.
- The authorized seven-scan replay is stored privately at
  `D:\document_ai_hr_dataset\.reviews\PDF-001C\pdf001d-final.json`:
  `98/98` present, `78/98` strict, `93/98` accepted, 0/7 technical errors and
  7/7 manual review. OCR-recognition mismatches are `0` versus `10` before.
- EasyOCR remains `vi-greedy`, 150 DPI, canvas 1280, preprocess `none`.
  Beamsearch and `vi-en`/ROI candidates were not promoted; no product route,
  DATA-29, DATA-31 or Camunda state changed.
- The remaining strict mismatches are normalization and job-title boundary
  cases under the locked professional-title precedence versus role-title Ground
  Truth; they are separate PDF-001E review work, not an OCR engine promotion.

## Validation

- Targeted PDF/OCR/parser tests: `61 passed`; full Python suite: `565 passed`.
- ALG-004 analyzer Ruff, compile and private replay passed; no analyzer process
  remains running. Full Python suite: `560 passed`.
- Active-source Ruff, mypy for 91 files, compile, repository hygiene and LongRun
  consistency pass. Web build/rendered tests remain `15/15`; frontend build
  passes and lint has 0 errors (22 pre-existing warnings).

## PDF-001E result

- The private aggregate-only counterfactual is at
  `D:\document_ai_hr_dataset\.reviews\PDF-001C\pdf001e-job-title-policy.json`.
- Professional-first is `78/98` strict and `93/98` accepted. Role-first is
  `77/98` strict and `98/98` accepted, and it loses Contract 23 strict exact.
- No role-first or conditional heuristic was promoted. The existing
  professional-title-first policy remains canonical; the five remaining
  role-title conflicts need independent business review, not a parser guess.

## PDF-001F result

- The independent visual review covered the five conflict documents. Every
  source visibly contains both `Chức danh chuyên môn` and `Chức vụ/Vị trí`; the
  role title matches Ground Truth in all five, while Contract 23 Ground Truth
  uses the professional title.
- This is a schema/label-policy conflict, not missing data or OCR ambiguity.
  The aggregate-only report is private at
  `D:\document_ai_hr_dataset\.reviews\PDF-001F\pdf001f-independent-business-review.json`.
- Do not change parser policy, Ground Truth, DATA-29/DATA-31 metrics or
  Camunda routing until the product owner defines the two title fields.

## PDF-001G result

- Accepted schema: `professional_title` is the professional label;
  `role_title` is the staffed role with the management clause removed;
  runtime `job_title` maps to `role_title` for HR/Camunda.
- Contract runtime is template `2.1`, schema `2.1.0`, parser
  `structured-hr/family-layout/2.2.0`; CV/IELTS schemas remain unchanged.
- Private replay at
  `D:\document_ai_hr_dataset\.reviews\PDF-001G\pdf001g-schema-replay.json`:
  `97/98` present, `82/98` strict, `96/98` accepted, 0 technical errors and
  7/7 manual review. Contract 23 parity is recorded separately at
  `D:\document_ai_hr_dataset\.reviews\PDF-001G\contract23-parity.json` with
  all boolean checks passing and no raw values.
- Validation: targeted schema/parser/API tests `68 passed`; full Python suite
  `566 passed`; active-source Ruff, mypy for 91 files, compile, repository
  hygiene and LongRun state checks pass. The full suite required a temporary
  local `tests/__init__.py` marker because this machine has a conflicting
  site-packages package named `tests`; the marker was deleted afterward.
- Historical DATA-29/DATA-31 reports remain untouched. The replay is not a
  production promotion; next is DATA-31 quality recovery.

## PDF-001H result

- DATA-31 was replayed in private storage through the current Template-first +
  EasyOCR service using the additive `professional_title`/`role_title` schema
  and the frozen 126-field historical comparator.
- Result: `97/126` present, `55/126` strict and `60/126` accepted, with
  `schemaErrors=0`. The quality gate requires `121/126` strict and `126/126`
  accepted, so the decision is `HOLD` and promotion is disabled.
- Title schema checks: professional title `4/4`, role title `1/4`, runtime
  `job_title` maps to `role_title` `4/4`, Contract 23 historical parity passes.
- Aggregate-only summary is private at
  `D:\document_ai_hr_dataset\.reviews\PDF-001H\template-first-v2\schema-replay-summary.json`.
  The private prediction/report are in the same directory. DATA-29 and the
  historical DATA-31 report were not overwritten; Ground Truth was not
  rewritten.
- CAM-001 remains blocked. No process/session was created, no real side effect
  was performed, and `autoContinueEnabled=false` remains in force.
- Validation: targeted replay/schema tests `69 passed`; full Python suite
  `567 passed`; mypy, compile, manifest parity, repository hygiene and
  LongRun state checks pass. Web build plus rendered tests are `15/15`, and
  lint has 0 errors with 22 pre-existing warnings.

## PDF-001I result

- Parser `structured-hr/family-layout/2.2.1` adds general IELTS OCR recovery
  for inline label/value blocks, embedded form numbers, inline band scores and
  dates. Synthetic regression coverage is included; no document-specific
  value or OCR profile was added.
- Private DATA-31 replay through Template-first + EasyOCR reached `111/126`
  present, `58/126` strict and `63/126` accepted, with `schemaErrors=0`.
- Aggregate diagnoses: 38 prediction-for-absent-GT fields; 17 recognized
  parser mismatches; 3 parser-missed; 2 OCR-not-recognized; and 3 below-80%
  partials. The remaining IELTS identifier/type semantics and sparse
  Contract/CV Ground Truth are schema/coverage decisions, not safe parser
  guesses.
- Aggregate-only summary is private at
  `D:\document_ai_hr_dataset\.reviews\PDF-001I\template-first-v4\schema-replay-summary.json`.
  Ground Truth and historical DATA-29/DATA-31 reports were not rewritten.
- Validation: targeted tests `95 passed`; full Python suite `569 passed`;
  Ruff, mypy for 91 files, compile, manifest parity, repository hygiene and
  LongRun state checks pass. CAM-001 remains blocked; no process/session or
  real side effect was created.

## PDF-001J coverage decision UI result

- DATA-31 private coverage routes are `/data31/coverage/summary`,
  `/document` and `/save`. The UI is available from the DATA-31 tab when the
  launcher receives `-ExternalDatasetCoverageDecision`.
- The tab shows `13` real source documents and `48` missing Ground Truth slots.
  It accepts either a field value (`GROUND_TRUTH`) or an explicit
  `OUT_OF_SCOPE` choice and displays the five locked IELTS semantics.
- Writes go only to the private `coverage-decision.json` overlay. The sealed
  `ground-truth.json`, predictions, DATA-29/DATA-31 historical reports and
  Camunda state remain unchanged. Current state is `COMPLETE`, `48/48`
  decided, with `17` `OUT_OF_SCOPE` fields.
- Validation: coverage/review tests `12 passed`, web build/rendered tests
  `16/16`, lint `0 errors` with 22 existing warnings, coverage module mypy and
  compile pass. Local health is EasyOCR available with six pipelines.

## DATA-31 scope-aware replay result

- `scripts/run_data31_schema_replay.py` accepts `--coverage-decision`, merges
  `GROUND_TRUTH` values in memory, excludes `OUT_OF_SCOPE` per case, and still
  validates the full prediction field schema.
- Active scope is `109` fields. The preserved strict ratio gives a `105/109`
  threshold; accepted requires `109/109`.
- Private scope-aware evaluation: `72/109` strict, `80/109` accepted,
  `schemaErrors=0`, decision `HOLD`. Reports remain outside Git.
- The existing private prediction is Template-first + EasyOCR parser `2.2.1`.
  A fresh OCR rerun was `NOT MEASURED` because local EasyOCR warm-up exited
  before producing a new artifact. No parser, Ground Truth SEALED file or
  Camunda state was changed.

## Resume instructions

1. Review the R6 private aggregate evidence and decide whether the remaining
   role-title policy residuals should supersede ADR-0007.
2. Do not add a professional-title fallback while ADR-0007 remains accepted.
3. Keep CAM-001 blocked until `105/109` strict and `109/109` accepted both pass.

## Scope boundaries

- Raw documents, Ground Truth, OCR output and private benchmark artifacts stay
  outside Git. DATA-29 remains immutable and localhost remains unchanged.
- `autoContinueEnabled=false`; HRIS and notifications remain simulated.

### DATA-31-QUALITY-RECOVERY-R5 result — 2026-08-21

- The canonical parser is `structured-hr/family-layout/2.2.7`. R5 adds one
  general CV recovery rule: a multi-line objective with career-intent markers
  remains a complete long field instead of being reduced to a role fragment.
  Contract title precedence, Ground Truth and OCR profile were not changed.
- Private replay completed all `13/13` documents through Template-first +
  EasyOCR. Aggregate metrics are `93/109` strict, `101/109` accepted and
  `106/109` present; Contract `34/44`, CV `39/45`, IELTS `20/20` exact.
- Safety checks are all clean: `schemaErrors=0`, parser regression `0`,
  sensitive false acceptance `0`, raw/private exposure `0`, and promotion is
  disabled. The accepted metric improved by one field; strict did not improve.
- Private evidence is stored at
  `D:\document_ai_hr_dataset\.reviews\DATA-31\prediction-r5-20260821.json`,
  `report-r5-20260821.json` and `summary-r5-20260821.json`.
- The gate remains `HOLD` against `105/109` strict and `109/109` accepted.
  Remaining Contract/CV residuals are locked title/field-boundary semantics,
  Ground Truth formatting or OCR punctuation/diacritic differences. No safe
  general parser rule remains justified from this replay. CAM-001 stays
  blocked; no process, session, side effect, commit, push or PR was created.
- Validation: targeted suite `87 passed`; focused Ruff, compile and
  `git diff --check` passed. Full Python suite, frontend tests/build and live
  Camunda E2E were not measured in R5.

### DATA-31-QUALITY-RECOVERY-R7 result — 2026-08-21

- Added parser `structured-hr/family-layout/2.2.8`. Contract `job_title` keeps
  `role_title` precedence and falls back to `professional_title` only when no
  role title exists. Native CV skills no longer discard an unlabelled
  `Phần mềm` prefix.
- Private replay completed `13/13` documents: `104/109` strict, `108/109`
  accepted and `109/109` present. Family totals are Contract `42/44`, CV
  `42/45` and IELTS `20/20` exact. Safety is clean: schema errors `0`, parser
  regression `0`, scan parser regression `0`, sensitive false acceptance `0`.
- One strict residual remains: a dual-title Contract where sealed Ground Truth
  selects `professional_title` while the active role-first policy selects
  `role_title`. Four long-field differences remain accepted partials and stay
  manual-review only; no OCR/diacritic broadening was added.
- Evidence: `D:\document_ai_hr_dataset\.reviews\DATA-31\prediction-r7-20260821.json`,
  `report-r7-20260821.json` and `summary-r7-20260821.json`; all remain private.
- Validation: targeted suite `118 passed`; template version governance,
  compile, `git diff --check` and LongRun state passed. Full Python suite,
  frontend suite and live Camunda E2E remain NOT MEASURED. CAM-001 stays
  blocked; no commit, push, PR, process or side effect was created.

### DATA-31-QUALITY-RECOVERY-R6 result — 2026-08-21

- Product/HR confirmed C1–C4 and V1–V4. Matching policy `2.1.0` now treats
  approved gender suffixes, field labels, list bullets, Vietnamese `&`/`và`
  layout and terminal punctuation as presentation differences. The existing
  role-only `job_title` ADR remains in force; no professional-title fallback
  was introduced.
- One private GT overlay entry corrects the CV-004 name after independent
  source-file verification. Sealed Ground Truth and DATA-29 remain unchanged;
  the overlay now contains `13` approved values.
- Full private replay completed `13/13` documents: `100/109` strict,
  `105/109` accepted and `106/109` present. Family totals are Contract
  `39/44`, CV `41/45` and IELTS `20/20` exact. Safety remains clean:
  `schemaErrors=0`, parser regression `0`, sensitive false acceptance `0`,
  raw/private exposure `0`, promotion disabled.
- Remaining strict residuals are the four Contract `job_title` fields under
  the role-only policy. Five long-field differences remain accepted partials;
  no document-specific OCR repair is justified.
- Private evidence is stored at
  `D:\document_ai_hr_dataset\.reviews\DATA-31\prediction-r6-20260821.json`,
  `report-r6-20260821.json` and `summary-r6-20260821.json`.
- Validation: targeted suite `105 passed`; focused Ruff, compile,
  `git diff --check` and LongRun state checks pass. Full Python suite,
  frontend tests/build and live Camunda E2E were not measured in R6.

## PDF-001I-R1 mismatch recovery — 2026-08-20

- Implemented the smallest safe parser change in
  `src/hcns_agent/templates/structured_hr.py`: IELTS `credential_id` now uses
  TRF/Form Number context, rejects validation/brand/URL candidates and keeps
  source identifier characters. Parser/manifest version: `2.2.2`.
- Existing private OCR pages were replayed without exposing raw data. The
  diagnostic artifact reached `64/109` strict and `71/109` accepted with zero
  schema errors, below the authoritative `72/109` and `80/109` baseline; it is
  not promoted. A semantic probe confirmed the corrected context rule.
- Direct full Template-first replay is still `NOT MEASURED` because native
  Torch/EasyOCR CRAFT crashed with an access violation after partial work.
- Quality gate remains `HOLD` (`105/109` strict, `109/109` accepted). CAM-001
  stays blocked. No process/session, real side effect, commit, push or PR was
  created.
- Validation: targeted tests `66 passed`; full Python suite `576 passed`;
  Ruff, compileall and repository hygiene passed.
- The PDF-001C analyzer was also aligned to the canonical parser version, so
  future diagnostics cannot silently claim parser `2.2.0`.

### Field-level mismatch classification (aggregate-only)

| Family | Strict mismatches | Classification | Handling |
|---|---:|---|---|
| Contract | `13` | Date representation (`3`), role-title schema (`4`), name/GT suffix (`1`), workplace boundary (`4`), allowance boundary (`1`) | Keep date/title semantics explicit; do not guess role title; accepted partials remain review-only |
| CV | `7` | Skills layout/abbreviation (`3`), desired-role narrative (`2`), experience boundary (`1`), one GT text discrepancy (`1`) | Keep long text manual-review; no lexicon or GT rewrite |
| IELTS | `17` | Credential ID/type/date semantics (`12`), recipient layout (`3`), overall-score OCR (`2`) | Parser now fixes TRF/Form Number context; owner must resolve sealed GT semantics |

This accounts for all `37` strict mismatches in the authoritative `72/109`
baseline. It does not treat accepted partials as exact and does not convert
schema/GT conflicts into parser fixes.

The replay runner now accepts an additive private `scopeOverrides` overlay for
already-populated fields that are outside the approved runtime semantics. It
validates category and source digest, accepts only `OUT_OF_SCOPE`, leaves the
sealed Ground Truth untouched, and reports the override count separately. The
current private overlay has no such override yet; active scope remains `109`.

### DATA-31 owner decision and replay — 2026-08-20

Product/HR confirmed that Contract `job_title` is `OUT_OF_SCOPE` only when the
source truly lacks the field; IELTS `credential_id` is the TRF/Form Number,
`credential_type` follows the printed certificate type, and `issue_date` is
measured only when an actual issue date is printed. `OUT_OF_SCOPE` fields are
excluded from the denominator and no synthetic Ground Truth is created.

The existing private coverage overlay was already complete (`48/48`, `17`
`OUT_OF_SCOPE`). Recomputing the scope-aware gate on the authoritative private
prediction produced `72/109` strict, `80/109` accepted, `schemaErrors=0`, and
`HOLD`. Sealed Ground Truth, predictions, historical reports and Camunda state
were not rewritten. CAM-001 remains blocked.

### DATA-31 Quality Recovery R2 — 2026-08-20

- Aggregate-only classification confirmed `37` strict mismatches: Contract
  `13`, CV `7`, IELTS `17`. The repeated groups are IELTS recognized-but-missed
  layout fields (`15`), Contract parser/OCR boundaries, and CV long-text or
  normalization differences.
- Fresh private replay completed all `13/13` documents with Template-first +
  EasyOCR parser `2.2.2`: `72/109` strict, `80/109` accepted,
  `schemaErrors=0`, parser regressions `0`, sensitive false acceptance `0`.
- No general parser rule met the promotion bar. No code, Ground Truth,
  coverage overlay, historical report or Camunda state was changed for R2;
  CAM-001 stays blocked.

### DATA-31 Quality Recovery R2 final — 2026-08-20

- The canonical parser is now `structured-hr/family-layout/2.2.4`. The small
  general fixes cover multi-word `First Name(s)`, Form Number decoys,
  employee-party title boundaries, printed IELTS type and grouped IELTS
  result rows. Matching policy also recognizes Vietnamese written dates as the
  same calendar date; EasyOCR and public schemas were not changed.
- The private coverage overlay records `12` confirmed IELTS semantic values.
  Sealed Ground Truth, DATA-29 and historical DATA-31 reports remain intact;
  no raw values or OCR text entered Git.
- Final private replay: `13/13` documents, `86/109` strict, `94/109`
  accepted, `105/109` present, `schemaErrors=0`, parser regressions `0`, and
  sensitive false acceptance `0`. The gate is `HOLD` against `105/109` strict
  and `109/109` accepted. The remaining 23 strict mismatches are split across
  locked title/GT semantics, OCR identifier/name/score misses, and accepted or
  below-threshold long-text differences; no safe document-specific fix was
  promoted.
- Private artifacts: `D:\document_ai_hr_dataset\.reviews\DATA-31\prediction-r2g-20260820.json`,
  `report-r2g-20260820.json`, and `summary-r2g-20260820.json`.
- Validation after the final change: targeted tests `76 passed`, full Python
  suite `580 passed`, repository hygiene and diff checks passed. CAM-001
  remains blocked; no process, session or real side effect was created.

### DATA-31 residual strict audit — 2026-08-20

- R2G remains authoritative at `86/109` strict, `94/109` accepted and
  `105/109` present. The rejected strict residual is `15` fields; `8` further
  differences are accepted partial text.
- Contract residual `6`: three locked role-title semantics, two native
  Ground-Truth field-boundary/label differences, and one scan OCR/title-policy
  mismatch. CV residual `3`: two native presentation/field-boundary semantics
  and one scan objective-versus-role schema difference.
- IELTS residual `6` is OCR-driven: four TRF/Form Number character errors, one
  missing recipient-name token and one missed visible overall-score cell.
- A private hi-res EasyOCR diagnostic (`canvas_size=2560`, `mag_ratio=1.3`)
  with and without the existing autocontrast profile improved the IELTS slice
  `14/20 → 15/20` exact and `19/20 → 20/20` present. It was not promoted and
  was not used to claim a full DATA-31 gate.
- No parser, schema or Ground Truth change is justified by this audit. Next
  task: IELTS crop/OCR gate with p95/RAM evidence, then full replay. CAM-001
  remains blocked.
