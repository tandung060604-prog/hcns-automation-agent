# Project State

Current milestone: LongRun maintenance checkpoint 2026-08-06; `M5-CAM-001` READY
Documentation profile: Standard (`PROJECT_STATE.md`, `BACKLOG.md`, `HANDOFF.md`)

Checkpoint task: `LONGRUN-MAINT-001` DONE. Product WIP is preserved; no reset, stash,
cleanup, commit, or push was performed by this maintenance task.

Repository:
- Branch: `codex/ocr-ho-v2-014-localhost`
- HEAD: `643a9fe` (`fix(ocr-ho): persist diagnostic drafts locally`)
- Local changes remain in the OCR-HO/DATA-16 workstream and are recorded in `HANDOFF.md`.

Completed capability:
- Template-first leave/overtime intake with native DOCX/PDF parsing and local OCR routing.
- Canonical document, schema validation, provenance, quality routing and manual review.
- Localhost evidence UI, private result references and Camunda 7 shadow workflow.
- Correction/re-upload, audit, idempotency and aggregate-only evaluation safeguards.

Evidence summary:
- Native DOCX/PDF: 90/90 required fields, 0 schema errors.
- Template OCR: image 48/54 and scan PDF 45/54; all cases manual review; false
  `AUTO_CONTINUE` count 0.
- DATA-16 parser-v2 development run: 69/112 strict exact, 82/112 accepted text,
  classification 11/12, schema errors 0; promotion remains `HOLD`.
- M4 Camunda dry-run: 10/10 scenarios; real side effects disabled.

Safety and limits:
- Local/loopback processing only; no real HRIS, notification or production promotion.
- Private documents, Ground Truth, raw OCR and model weights stay outside Git.
- Image/scan OCR remains manual-review-only; broader OCR promotion gates remain open.

Next READY task: `M5-CAM-001`.
Next action: read `docs/CAMUNDA_M5_SHADOW_PILOT_RUNBOOK.md`, complete its gates, then
run only the documented preflight; do not start a cohort before approval.

Validation:
- `python scripts/validate_longrun_state.py`: PASS.
- `python -m compileall -q scripts/validate_longrun_state.py`: PASS.
- `.venv\\Scripts\\ruff.exe check scripts/validate_longrun_state.py`: PASS.
- `git diff --check`: PASS; Git emitted line-ending warnings only.
- `scripts/check_repository.py`: FAIL on pre-existing untracked `data/private`;
  no tracked private files were found and the directory was not changed.

Archive: `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md` preserves the prior
milestone evidence and status history.

First command after resume:

```powershell
Set-Location "D:\AI Vin Thực Chiến\Side Project\PaddleOCR\hcns-automation-agent"
python scripts/validate_longrun_state.py
git status --short --branch
```
