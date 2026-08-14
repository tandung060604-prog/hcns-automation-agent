# Handoff

## Current checkpoint (2026-08-13)

- Branch: `codex/perf-001-stage-timing`
- HEAD: `406bf3d6f019e3c5d6ecd516d8a200ea45ebc509`
- Checkpoint task: `PERF-001-STAGE-TIMING`
- Status: implementation and authorized local benchmark complete; promotion HOLD.
- Next READY task: `ALG-002`

## Resume instructions

1. Preserve all unrelated CCCD changes and local untracked scripts.
2. Confirm ALG-001 PR #35 remains green or merged before rebasing PERF-001.
3. Use `scripts/benchmark_template_stages.py --resume` only with an authorized
   private dataset/work root outside Git.
4. Keep DATA-29 quality fixed at `107/112` strict and `112/112` accepted; timing
   does not authorize Ground Truth changes or promotion.
5. Implement ALG-002 before optimizing OCR so upload and evidence cannot drift.
6. Run PDF-001 next; do not open CCCD or Contract images before its quality,
   memory and p50/p95 gates pass.

## PERF-001 evidence

- Timing schema: `hcns-stage-timing/1.0.0`.
- Authorized measurements: 4 cold + 120 warm, with 30 warm per input class.
- Warm total p50/p95: DOCX `167/285 ms`, PDF text `134/158 ms`, image
  `19.5/28.5 s`, PDF scan `33.1/67.5 s`.
- One co-resident scan run hit a 1.20 GB allocation failure on the 8 GB host;
  isolated PDF scan and image runs completed without final-report failures.
- Live Camunda timing smoke: `1.215 s`; aggregate percentile `NOT_MEASURED` to
  avoid creating 31 pending Human Review cases.
- Report privacy audit passed: no raw field/OCR text, path, filename, UUID,
  document/process ID or email; `promotionAllowed=false`.
- Private report:
  `C:\tmp\hcns-perf-001-data29-20260813-v2\aggregate-report.json`.

## Scope boundaries

- Raw documents and per-run result payloads remain private and outside Git.
- No extraction algorithm, DATA-29 prediction, Ground Truth, matching policy,
  Camunda shadow policy, CCCD WIP or real side-effect configuration was changed.
- Full historical handoff is preserved at
  `docs/archive/HANDOFF_HISTORY_2026-08-13.md`.
