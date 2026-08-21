# Project State

Current milestone: MERGE main → `feat/deploy-cloudflare` (template/MVP primary)
Checkpoint task: `MERGE-MAIN-CV-IELTS-CONTRACT`
Next action: smoke upload CV / Contract / IELTS on MVP panel after API restart
Archive: `docs/archive/PROJECT_STATE_HISTORY_2026-08-20.md`

Repository:
- Active product branch: `feat/deploy-cloudflare` (MVP demo + Cloudflare deploy template).
- Merged from: `origin/main` @ `0c2e0ed` (DATA-31 R7, structured-hr Contract/CV/IELTS, templates).

## Verified current result

- DATA-31 private R7 (from `main`): 13/13 documents, Template-first + EasyOCR,
  parser `structured-hr/family-layout/2.2.8`; metrics `104/109` strict / `108/109` accepted.
- Unified Contract / CV / IELTS parser path via `src/hcns_agent/templates/structured_hr.py`.
- Downloadable blanks under `apps/ocr_lab/web/public/templates/`:
  `cv-v2.docx`, `probation-contract-v2.docx`, `leave-request-v1.docx`,
  `overtime-request-v1.docx`. IELTS uses PDF/image scan (no blank DOCX).
- Local product runtime remains Template-first + EasyOCR; Paddle is explicit rollback.
- MVP demo (this branch) remains the primary surface: login/RBAC, upload-first scan,
  HR queue, in-app notification, history/evidence archive, Cloudflare public deploy.
- Camunda upload types include Leave, OT, CV, CERTIFICATE (IELTS), EMPLOYMENT_CONTRACT.

## Residual / notes

- DATA-31 gate still HOLD vs `105/109` strict on main quality track.
- Formal Camunda promotion and real HRIS remain out of scope.
- Prefer this branch UI/nav/MVP when resolving conflicts with `main` hygiene cleanup.
