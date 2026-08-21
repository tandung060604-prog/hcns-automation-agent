# Project State

Current milestone: PERF-001 DONE / LOCAL HOLD
Checkpoint task: `PERF-001-STAGE-TIMING`

Repository:
- Branch: `codex/perf-001-stage-timing`
- HEAD: `406bf3d6f019e3c5d6ecd516d8a200ea45ebc509`
- Base PR: ALG-001 PR #35, CI passed on Python 3.10/3.12 and OCR Lab Web.

## PERF-001 stage timing baseline (2026-08-13)

- Template-first emits additive `hcns-stage-timing/1.0.0` metadata for intake,
  OCR, template parsing/validation, private persistence and total time. Camunda
  start responses expose the same safe schema for the handoff stage.
- The resumable aggregate-only runner completed one cold plus `30` warm runs
  for each authorized DATA-29 class: DOCX, PDF text, PDF scan and image. It did
  not read Ground Truth and its report contains no field value, OCR text, path,
  filename, document/process ID or UUID.
- Warm total p50/p95 on this 8 GB CPU machine: DOCX `167/285 ms`, PDF text
  `134/158 ms`, image `19.5/28.5 s`, PDF scan `33.1/67.5 s`. OCR dominates the
  visual classes; native OCR timing is `0` by design.
- A co-resident API plus scan benchmark initially failed a 1.20 GB EasyOCR
  allocation. Isolated scan execution completed `30/30`, proving a local memory
  concurrency limit rather than a document/template failure.
- One live Camunda 7.13 start smoke returned safe timing metadata in `1.215 s`.
  Camunda p50/p95 remains `NOT_MEASURED` because no 31-case Human Review cohort
  was created only for benchmarking.
- Quality remains pinned DATA-29 `107/112` strict and `112/112` accepted;
  PERF-001 did not rerun or modify Ground Truth, prediction or matching policy.
- Private aggregate report:
  `C:\tmp\hcns-perf-001-data29-20260813-v2\aggregate-report.json`
  (`sha256:ce53c2bf4e00bf5f6b77c7bd97ac5b284cc09c732d43982c089d0af2d630b709`).

## Active product/runtime state

- Local product runtime is Template-first + EasyOCR; Paddle is explicit rollback.
- `/health` reports the selected backend and six frozen template/parser pipelines.
- DATA-29 Explorer shows 3 Contract, 5 CV and 4 IELTS metric-linked sources.
- CV and IELTS live Camunda shadow E2E passed with Human Review and zero incident;
  Contract live acceptance still needs an independent authorized user upload.
- `autoContinueEnabled=false`; HRIS and notification remain simulated.
- MVP demo now supports upload-first submission: Template-first auto-detects the
  document type, fills an editable submit form, notifies HR immediately, and
  streams HR decisions back to the submitter over local SSE with polling fallback.
- CCCD held-out/WIP and Contract-image expansion remain closed.

Next action: Implement ALG-002 so upload and DATA-29 share one canonical parser path,
then run PDF-001 memory/latency and quality gates with the PERF-001 runner.
Next READY task: `ALG-002`

Archive: full prior state is in `docs/archive/PROJECT_STATE_HISTORY_2026-08-13.md`;
older evidence remains in `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md`.
