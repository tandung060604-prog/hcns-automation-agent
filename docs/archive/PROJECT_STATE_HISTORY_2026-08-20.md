# Project State
Current milestone: DATA-31 SCOPE-AWARE REPLAY / QUALITY HOLD
Checkpoint task: `DATA-31-SCOPE-AWARE-REPLAY`
Next READY task: Review the 109-field scoped gate before CAM-001
Repository:
- Branch: `codex/alg-003-contract-scan-recovery`
- HEAD: `88473de899518a4660ed7b3dc0c13dc66978eb6b`
- Base: `origin/main` at the same commit; changes are uncommitted/unpushed and
  isolated from the original dirty worktree.
## ALG-003 implementation (2026-08-18)

- Canonical Contract/CV/IELTS parser is `structured-hr/family-layout/2.2.1`;
  Contract recovery covers numbered/split labels, identity numbers, multiline
  fields and the observed weekly-hours OCR separator. OCR remains `MANUAL_REVIEW`.

## PDF-001A result (2026-08-18)

- One authorized scan: baseline 150/1280 was `9/10` strict, `10/10` accepted;
  hires 200/2560 was `8/10`, `10/10`, with higher p95/RSS; `NOT_PROMOTED`.

## PDF-001C result (2026-08-18)

- Seven authorized scans / 98 fields at EasyOCR 150/1280/`none`: `96/98`
  present, `67/98` strict, `82/98` accepted, 0/7 technical errors, 7/7 review;
  controls had zero technical errors and scan p95/RAM was `NOT MEASURED`.

## PDF-001D result (2026-08-19)

- Shared parser is `structured-hr/family-layout/2.1.4`; recovery handles the
  observed `cẩp/ưrợ`, monthly-unit, `Công Ly`, `xuẩt`, `Nguyển` and `Quõc`
  OCR variants without document-specific values.
- Private replay `PDF-001C/pdf001d-final.json`: `98/98` present, `78/98` strict,
  `93/98` accepted, 0/7 technical errors and 7/7 review. OCR-recognition
  mismatches fell from 10 to 0 via `contextual-business-token-v1`; the remaining
  20 strict mismatches are normalization or policy boundary, not OCR.

## PDF-001I result (2026-08-19)

- Parser `2.2.1` adds general IELTS inline-label/layout recovery with synthetic
  coverage. DATA-31 replay reached `111/126` present, `58/126` strict and
  `63/126` accepted; `schemaErrors=0`.
- GT coverage is `78/126` populated and `48/126` empty; 38 empty-GT fields have
  a prediction and 10 are empty on both sides; the sealed Ground Truth is unchanged.
- Residual aggregate diagnoses: 38 prediction-for-absent-GT fields, 17
  recognized parser mismatches, 3 parser-missed, 2 OCR-not-recognized and 3
  below-80% partials. IELTS credential semantics and sparse Contract/CV GT are
  schema/coverage issues, not safe parser guesses.
- Required gate `121/126` strict and `126/126` accepted: `HOLD`, promotion
  disabled. Ground Truth and historical reports were not rewritten.

## DATA-31 and safety state

- DATA-31 historical report remains private/immutable at `59/126` strict and
  `64/126` accepted; latest recovery replay is private; DATA-29 remains
  historical at `107/112` and `112/112`; localhost unchanged.
- CAM-001 remains blocked by the scan gate and DATA-31 gate; no new
  process/session was created. `autoContinueEnabled=false`.
- HRIS/notifications remain simulated; raw documents, Ground Truth and values
  remain outside Git.

## PDF-001J coverage decision UI (2026-08-19)

- Localhost now exposes a private DATA-31 tab backed by `/data31/coverage`.
  It shows the 13 real source documents, the 48 missing Ground Truth slots,
  source preview, per-field `GROUND_TRUTH` input or `OUT_OF_SCOPE` decision,
  and locked IELTS semantics.
- Decisions are written only to the private `coverage-decision.json` overlay;
  the SEALED `ground-truth.json`, predictions and historical reports are not
  rewritten. Current state is `48/48` decided, `COMPLETE`, with `17`
  `OUT_OF_SCOPE` fields.
- Launcher command uses the DATA-31 private root and enables the tab only when
  `-ExternalDatasetCoverageDecision` is supplied. CAM-001 remains blocked.

## DATA-31 scope-aware replay (2026-08-20)

- The replay runner now applies the private coverage overlay in memory,
  excludes `OUT_OF_SCOPE` fields per case, and keeps full prediction schema
  validation. No sealed Ground Truth or parser behavior is changed.
- The active scope is `109` fields; strict threshold is `105/109` (preserving
  the prior `121/126` ratio) and accepted threshold is `109/109`.
- Scope-aware evaluation of the existing private EasyOCR/template-first
  prediction (`structured-hr/family-layout/2.2.1`) reached `72/109` strict,
  `80/109` accepted, `schemaErrors=0`, decision `HOLD`.
- A fresh OCR rerun was `NOT MEASURED` because local EasyOCR warm-up exited
  before producing a new artifact; the existing parser-matched prediction was
  reused only for this metric-policy replay. CAM-001 remains blocked.
## Verification

- PDF-001I targeted tests: `95 passed`; full Python suite before this UI task:
  `569 passed`.
- DATA-31 coverage/review/scope tests: `39 passed`; web build/rendered tests: `16/16`;
  frontend lint: `0 errors` with 22 existing warnings; coverage module mypy and
  compile checks pass.
- Active-source compile, repository hygiene and LongRun consistency remain
  covered by the prior checkpoint; legacy Ruff findings are pre-existing.

## PDF-001I-R1 parser recovery (2026-08-20)

- Parser `structured-hr/family-layout/2.2.2` now selects IELTS credential IDs
  from TRF/Form Number context and excludes validation, brand and URL text;
  raw identifier characters are preserved. This is a general parser rule and
  does not change OCR, Ground Truth or the public schema.
- An isolated private EasyOCR replay produced 8 pages and a diagnostic result
  of `64/109` strict, `71/109` accepted, `schemaErrors=0`. It is not promoted
  because it uses a separate page artifact and is below the official baseline
  (`72/109`, `80/109`).
- The direct long-lived Template-first replay remains `NOT MEASURED` because
  native Torch/EasyOCR CRAFT raised an access violation after partial work.
  The official scope-aware baseline remains authoritative; gate decision is
  `HOLD` and CAM-001 remains blocked.
- Validation after the parser change: targeted tests `66 passed`, full Python
  suite `576 passed`, Ruff, compileall and repository hygiene passed.

## DATA-31 owner semantics confirmation (2026-08-20)

- Product/HR owner confirmed: Contract `job_title` is `OUT_OF_SCOPE` only when
  the source truly has no such field; IELTS `credential_id` means TRF/Form
  Number, `credential_type` follows the printed certificate type, and
  `issue_date` is measured only when an actual issue date is printed.
- `OUT_OF_SCOPE` fields are excluded from the denominator; no synthetic Ground
  Truth is created. The sealed Ground Truth and existing coverage overlay were
  not rewritten.
- Recomputed scope-aware gate on the authoritative private prediction:
  `72/109` strict, `80/109` accepted, `schemaErrors=0`, decision `HOLD`.
  CAM-001 remains blocked.

## DATA-31 Quality Recovery R2 (2026-08-20)

- Aggregate-only review confirmed `37` strict mismatches: Contract `13`, CV
  `7`, IELTS `17`. The largest repeated group is IELTS layout/parser recovery
  (`15` recognized-but-missed fields); remaining differences are OCR misses,
  normalization, partial text or locked schema semantics.
- A fresh `13/13` private replay with Template-first + EasyOCR parser `2.2.2`
  completed successfully. It reached `72/109` strict, `80/109` accepted,
  `schemaErrors=0`, with no parser regression or sensitive false acceptance.
- No document-specific parser rule was justified. The R2 parser candidate is
  not promoted; Ground Truth, coverage overlay, historical reports and
  localhost remain unchanged. CAM-001 remains blocked.

## DATA-31 Quality Recovery R2 final (2026-08-20)

- The final implementation uses only general rules in the canonical parser:
  multi-word `First Name(s)` labels, Form Number candidate filtering, employee
  party title boundaries, printed IELTS type, grouped IELTS score rows and
  Vietnamese written-date canonical matching. Parser/manifest version is
  `structured-hr/family-layout/2.2.4`; EasyOCR remains the default.
- The private coverage overlay contains `12` confirmed IELTS semantic values
  (TRF/Form Number, printed type and printed issue date). The sealed Ground
  Truth file and historical reports remain untouched; no document-specific
  parser value was added.
- Fresh replay completed all `13/13` documents through Template-first +
  EasyOCR: `86/109` strict, `94/109` accepted, `105/109` present,
  `schemaErrors=0`, parser regressions `0`, sensitive false acceptance `0`.
  The required gate is `105/109` strict and `109/109` accepted, so the result
  is `HOLD`; 23 strict mismatches remain, including 8 accepted partials.
- CAM-001 remains blocked. No process/session, real side effect, commit, push
  or localhost promotion was performed.

## DATA-31 residual strict audit (2026-08-20)

- The authoritative R2G replay remains `86/109` strict, `94/109` accepted and
  `105/109` present. Exactly `15` fields are rejected strict; the other `8`
  of the `23` strict differences are accepted partial text.
- Aggregate classification of the 15 rejected fields:
  - Contract `6`: three locked `job_title` role-title semantics, one native
    employee-name label/suffix boundary in Ground Truth, one native workplace
    label boundary in Ground Truth, and one scan job-title OCR/title-policy
    mismatch.
  - CV `3`: one native skills presentation/normalization difference, one
    native full-name field-boundary difference, and one scan objective-narrative
    versus desired-role schema difference.
  - IELTS `6`: four OCR character substitutions in TRF/Form Number, one OCR
    missing recipient-name token, and one OCR miss of a visible overall-score
    cell.
- A private diagnostic using EasyOCR `canvas_size=2560`, `mag_ratio=1.3`, with
  and without the existing `content-roi-autocontrast-v1` profile, improved the
  four-image IELTS slice from `14/20` to `15/20` exact and `19/20` to `20/20`
  present. It is diagnostic-only, not a DATA-31 replay or promotion gate.
- No safe general parser rule was identified for the 15 fields. No Ground
  Truth, public schema or parser code was changed in this audit. CAM-001 stays
  blocked; the next READY task is an IELTS crop/OCR quality gate with latency
  and RAM evidence, followed by a full DATA-31 replay.
