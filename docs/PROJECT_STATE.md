# Project State

## M5-CAM-001D local shadow review-only (2026-08-10)

M5-CAM-001D đã hoàn tất kiểm tra metadata-only trên projection private hiện có
70 tài liệu (Contract 30, CV 30, IELTS/chứng chỉ 10). Luồng chỉ tạo opaque
reference và scalar process variables; không mở Camunda, không đọc Ground Truth
hay evaluate-once. Kết quả aggregate: `70/70 MANUAL_REVIEW`, scan `27/27`
`MANUAL_REVIEW`, unsupported `2/2` giữ manual review, idempotency mismatch `0`,
duplicate reference `0`, raw exposure `0`, auto-continue `0`, process start `0`
và real side effect `0`. `passed=true`, nhưng `promotionAllowed=false` theo
thiết kế local shadow review-only. Báo cáo private không nằm trong Git/cloud.

## DATA-30B local benchmark metric checkpoint (2026-08-10)

The localhost benchmark cards now load the sealed DATA-29 development
aggregate while keeping the DATA-22 prediction-only count separate. Displayed
development metrics are Contract `42/42` strict, CV `45/50` strict and IELTS
`20/20` strict; accepted is `42/42`, `50/50` and `20/20`. Cards show benchmark
counts `3/5/4` and local prediction-only counts `30/30/10` by Contract/CV/IELTS.
DATA-17 and DATA-24 remain immutable; no new data, GroundTruth rerun or
evaluate-once was performed. API summary, Python compile, web build and 15 web
tests passed; raw artifacts remain outside Git/cloud.

## M5-CAM-001B Phase15 scalar/reference bridge (2026-08-10)

M5-CAM-001B đã nối projection Phase15 tối giản vào Submit task của Camunda
trên đúng hai fixture synthetic leave/overtime. Bridge chuẩn hóa classification
status về vocabulary Camunda, thay artifact path bằng opaque reference do caller
cấp, ép `autoContinueEnabled=false` và fail-closed với raw field/path variables.

- Camunda thực tế: cả hai case đạt `UserReview` và hoàn tất simulated flow.
- Aggregate gates: `AUTO_CONTINUE=0`, raw exposure `0`, duplicate `0`,
  unreconciled `0`, real side effects `0`; thời gian case 2.485s và 1.234s.
- Không dùng Phase12, không đọc cohort thật, không thêm `documentSourcePath`,
  không sửa DATA-17/24/27 artifacts. Test bridge dùng fixture metadata synthetic.

## User-directed local private corpus authorization (2026-08-10)

The user has authorized the existing project corpus for local gate, replay and
localhost review runs. This is a local-only operating profile, not a cloud or
Git data permission: raw documents/OCR/predictions/PII remain outside the
repository, Camunda receives scalar/reference values only, scan inputs remain
`MANUAL_REVIEW`, side effects stay disabled, and DATA-24 remains immutable.

## DATA-30A local private replay review (2026-08-10)

Localhost now reads a private prediction-only projection of the existing
DATA-22 development inventory: `70` documents (`30/30/10` by Contract/CV/IELTS),
`68` predictions and `2` explicit `UNSUPPORTED_FORMAT` records. All `27` scan
documents show `MANUAL_REVIEW`; no GroundTruth or evaluate-once artifact is
read. Projection and source files remain outside Git/cloud at the authorized
private root. API/UI verification found `70` review buttons and `2` unsupported
records; promotion remains `HOLD`.

## M5-CAM-001 authorization state (2026-08-10)

Authorization is `AUTHORIZED_SYNTHETIC_ONLY`; it uses role IDs
`m5-synthetic-business-owner` and `m5-independent-synthetic-reviewer`, a
2026-08-10 15:55–18:00 (+07:00) window, seven-day private retention and
owner-role rollback authority. It authorizes only two synthetic
leave/overtime cases. Real cohort remains closed; side effects are `DISABLED`,
every result is `MANUAL_REVIEW`, and DATA-24/GroundTruth/evaluate-once remains
immutable and unopened.

## M5-CAM-001C authorization expiry/rollback smoke (2026-08-10)

M5-CAM-001C is `DONE` for the synthetic-only authorization. The active
leave/overtime run passed with `MANUAL_REVIEW`, auto-continue `0`, raw exposure
`0`, duplicates `0`, unreconciled `0` and real side effects `0`. An expired
authorization was rejected before any Camunda process start (`0` start
attempts). A simulated `autoContinueCount > 0` violation returned
`rollbackRequired=true`, `allowedToComplete=false` and the fail-closed stop/delete/
escalate action. No gate changed and DATA-24 remained unopened.

## M5-CAM-001A local synthetic shadow preflight (2026-08-10)

Preflight Camunda local is `PASS` on the implementation branch
`codex/m5-cam-001a-shadow-preflight`; it is not a production or cohort approval.

- Current BPMN/DMN deployed to local Camunda 7.13; two native DOCX fixtures only
  (`LEAVE_REQUEST`, `OVERTIME_REQUEST`) reached `UserReview`, were confirmed by a
  synthetic reviewer, then completed the simulated HRIS/notification path.
- Gates: `AUTO_CONTINUE=0`, raw exposure `0`, duplicate artifacts `0`,
  unreconciled cases `0`, real side effects `0`; case durations were 2.781s and
  1.609s, both below 60s.
- Worker polling now retries an unavailable local Camunda REST endpoint using
  bounded exponential backoff. The new runner creates source/result/report files
  only below the caller-selected private root and emits aggregate-only evidence.
- No real leave/overtime cohort, no OCR/CV/contract/IELTS dataset, no GroundTruth,
  and no existing evaluate-once artifact were accessed. The next decision is still
  owner authorization for a real shadow cohort, not automatic promotion.

## DATA-30 main reconciliation & development freeze (2026-08-10)

Repository đã được đồng bộ fast-forward với `origin/main`:

- Branch hiện hành: `main`.
- HEAD và `origin/main`: đang đồng bộ tại checkpoint DATA-30 sau merge PR #16;
  xác minh bằng cách đối chiếu `git rev-parse HEAD` và `git rev-parse origin/main`.
- Working tree sạch; không còn thay đổi local chưa commit.
- PR #15 (DATA-29 implementation) và PR #16 (README tiếng Việt) đã merge; CI
  Python 3.10, Python 3.12 và OCR Lab Web đều `SUCCESS`.

Development delivery được đóng băng ở trạng thái `DEVELOPMENT COMPLETE /
HELD-OUT HOLD`. Metrics DATA-29 hiện hành trên 12 tài liệu và 112 field:
strict `107/112`, accepted `112/112`, Contract `42/42`, CV `45/50`, IELTS
`20/20`, applicable completeness `99/99`, classification `12/12`, schema
errors `0`, sensitive false acceptance `0`, parser regression `0`, scan
`5/5 MANUAL_REVIEW`, false auto-continue `0`. Fallback vẫn disabled vì scan
strict improvement `3.3334pp` thấp hơn ngưỡng `10pp`.

Không thêm dữ liệu, không sửa parser, không rerun DATA-24, không thay đổi
GroundTruth/evaluate-once cũ và không promote fallback. DATA-27 held-out
generalization tiếp tục `HOLD` do existing-pool audit không đủ tài liệu mới.
Raw document, OCR, prediction và GroundTruth vẫn nằm ngoài Git/cloud.

## DATA-29 CV residual recovery (2026-08-10)

DATA-29 là checkpoint parser development-only đã được tích hợp vào `main` tại
`54eafd0`; implementation ban đầu nằm trên branch
`codex/data29-cv-residual-recovery`, dựa trên `b958021`. Nó dùng năm tài liệu
CV development hiện có và không thêm data. Runtime extraction không
read GroundTruth; DATA-17, DATA-24 and DATA-27 artifacts remain immutable.

Fresh private aggregate: strict `107/112` (95.54%), accepted `112/112`;
Contract `42/42`, CV `45/50`, IELTS `20/20`; applicable completeness `99/99`,
classification `12/12`, schema errors `0`, sensitive false acceptance `0`,
parser regression `0`, scan manual review `5/5`, false auto-continue `0`.
The residual CV accepted-partial set is exactly five `experience` fields;
`skills` and `desired_role` no longer have accepted-partial fields. DATA-20
development gate is `PASS`; fallback remains disabled because scan strict
improvement is `3.3334pp`, below the required `10pp`.

Implementation is bounded to native section stops, native skill-list label and
ampersand normalization, desired-role title conjunction normalization, and a
same-document one-edit OCR token repair for scan skills. Schema/API and the
scan `MANUAL_REVIEW` policy are unchanged.

Aggregate-only handoff artifact (outside Git):
`C:\tmp\data29-cv-residual-recovery-20260810.json`.
Private prediction/aggregate/gate files are outside Git; no raw values are
recorded in this state file.

## DATA-28 historical checkpoint (2026-08-10)

Current milestone: `DATA-28-LOCAL-REVIEW-HANDOFF` is complete as a
development-only local handoff. `DATA-26-PARSER-RECOVERY` remains `DONE / DEV
HOLD` with a passing development gate; no fallback or production promotion is
enabled.

Repository:
- Branch: `main`
- HEAD: `5d85780` (`fix(web): refresh nanoid security patch`)
- Working tree was clean at checkpoint creation.

DATA-27A existing-pool audit is complete and `HOLD`. After SHA-256/history and
lineage exclusion, the available fresh counts are Contract `1`, CV `1`, and
IELTS `0`, below the required fresh held-out counts `10/10/5`. No new data is
required for this audit, but DATA-27 cannot claim an independent held-out gate
without either additional eligible data or an explicitly changed policy.

Development-only delivery artifact (aggregate, outside Git):
- `C:\\tmp\\data27d-development-delivery-20260810.json`

DATA-24 evaluate-once, GroundTruth and all raw private artifacts remain
immutable. DATA-27 fresh held-out generalization is `HOLD`; no evaluate-once
rerun is authorized.

DATA-28 localhost review evidence:
- URL: `http://localhost:3000/workspace`
- API: `http://127.0.0.1:8765`
- Scope: 12 development documents / 112 fields; Contract `3/42`, CV `5/50`,
  IELTS `4/20`.
- Remaining strict gap: CV accepted-partial/over-extraction in `experience`
  `5`, `skills` `4`, and `desired_role` `1`; Contract and IELTS have no strict
  field gap in this replay.
- Scan policy: 5/5 manual review, false auto-continue `0`.
- Aggregate handoff artifact: `C:\\tmp\\data28-local-review-handoff-20260810.json`.

The private `.env.local` only enables the external review tab for this local
observation session and is ignored by Git.

DATA-26 changes are conservative: CV glued header boundary recovery, geometry
inference for a narrow full-width section heading, duration normalization, and
an opt-in local VietOCR line-refinement path for scan replay. Schema, API,
policy v2, GroundTruth access rules and scan `MANUAL_REVIEW` policy are
unchanged.

Private hybrid replay artifacts (outside Git):
- Prediction: `C:\\tmp\\bo10-dev-predictions-data26-parser-recovery-vietocr-20260807.json`
- Aggregate: `C:\\tmp\\bo10-dev-aggregate-data26-parser-recovery-vietocr-20260807.json`
- Gate: `C:\\tmp\\bo10-data26-gate-vietocr-20260807.json`

Development aggregate: strict `102/112` (91.07%), accepted `112/112`, Contract
`42/42`, CV `40/50` (80%), IELTS `20/20`, applicable completeness `99/99`,
classification `12/12`, schema errors `0`, sensitive false acceptance `0`,
parser regression `0`, scan manual review `5/5`, false auto-continue `0`.
The DATA-20 gate is `PASS`; fallback remains disabled because the fixed scan
subset improvement is `3.33pp`, below the required `10pp`. Accepted text does
not replace strict EM.

DATA-25 policy-v2 post-hoc audit remains non-promotional (`144/265` canonical,
`155/265` accepted). DATA-24 evaluate-once and GroundTruth remain immutable;
DATA-23 locks and the original 10+5 IELTS split remain unchanged. DATA-27
fresh held-out generalization is blocked by the existing-pool audit.

Validation: targeted Python `25 passed`, worker Ruff and `py_compile` passed;
web `npm test` (13) and `npm run build` passed on the unchanged web surface.

Next action: keep the localhost review surface available for handoff. Do not
create a held-out claim, rerun DATA-24, or promote a fallback. The unrelated
global task remains separately tracked in `BACKLOG.md`.

Archive: `docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md`.

## LOCAL-PRIVATE-DATA-AUTHORIZED gate/replay (2026-08-10)

User-authorized local replay used the existing private DATA-22 development
corpus (`70` documents: Contract `30`, CV `30`, IELTS `10`). PaddleOCR ran
locally on CPU for `68` Phase-12-supported documents. The remaining `2`
documents use unsupported `.txt`/`.pptx` formats and remain
`MANUAL_REVIEW/UNSUPPORTED_FORMAT`; they were not silently dropped.

Aggregate-only replay evidence (outside Git):
`C:\\Camunda\\private-data\\local-private-data-authorized-20260810\\data22-development-r3-local-gate-replay-aggregate.json`.
The report contains counts and hashes only; no raw document, OCR, prediction,
field value or PII. Scan coverage is `27/27 MANUAL_REVIEW`. GroundTruth was not
provided, so strict EM, accepted text and completeness are intentionally
`NOT_COMPUTED`; promotion decision is `HOLD`. DATA-24 remains immutable and
was not reopened.
