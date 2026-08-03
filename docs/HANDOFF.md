# Handoff

## Repository context

- Repository: `D:\AI Vin Thực Chiến\Side Project\PaddleOCR\hcns-automation-agent`
- Branch: `codex/m1-m2-document-understanding`
- Routing: [docs/README.md](README.md)
- Acceptance criteria: [docs/BACKLOG.md](BACKLOG.md)

## Active workstreams

### OCR-HO-V2-001 — CCCD held-out v2

- Manifest private đã khóa đủ 15 tài liệu không trùng development.
- Ingest 15/15 đã hoàn tất.
- Prediction Phase 11.5 đang chạy ẩn; Phase 11.6 sẽ chạy sau đó.
- Không mở prediction, không tính metric và không đưa PII vào Git trước khi
  Ground Truth được khóa.
- Policy hiện tại: `SHADOW_REVIEW_ONLY`.

### OCR-HO-V2-002 — Local Ground Truth review gate (IN_PROGRESS)

- API local currently runs at `http://127.0.0.1:8765` with
  `--cccd-heldout-root C:\Camunda\private-data\paddleocr-hr-cccd-heldout-v2`.
- Web local runs at `http://localhost:3000/` with
  `VITE_SHOW_GROUND_TRUTH_REVIEW=true`; the visible section is
  `LOCAL GROUND TRUTH REVIEW · CCCD`.
- The UI lists 15 images and shows each source image plus eight field inputs. It
  requires both source-image and full-diacritic assertions before saving.
- `CCCD-HO-005` is now marked `OUT_OF_SCOPE_BACK`: it remains visible for source
  audit, is not treated as eight missing fields, and is excluded from the metric.
  The current denominator is 14 eligible front-side images out of 15 sources.
- Ground Truth is now `CONFIRMED` after 14/14 eligible reviews; the queue was
  locked and evaluate-once ran exactly once. The aggregate result is
  `SHADOW_REVIEW_ONLY` (strict exact 50.00%, ASCII exact 50.89%, CER 80.71%,
  DER 16.14%, 112 fields). No candidate was promoted.
- Do not rerun evaluate-once or open the private prediction JSON. Keep the
  sealed snapshot and evaluation report immutable; the next task must address
  the failed promotion gates with new development evidence, not held-out tuning.
- OCR-HO-V2-003 adds a local-only post-evaluation inspector at
  `/cccd-heldout/review/evaluation?id=...`. After selecting an image, the panel
  shows Ground Truth versus Phase 11.5/11.6, match verdict, error class,
  confidence, and ROI. It is unavailable before evaluation and does not expose
  `CCCD-HO-005` because that document is out of scope.
- Private outputs remain outside Git: `ground_truth/ground_truth_confirmed_private.json`,
  `ground_truth/GROUND_TRUTH_LOCK.json`, and `evaluation/evaluate_once_private.json`.

### TF-P1-001 — Template-first MVP

- Hai template DOCX: `leave-request-v1` và `overtime-request-v1`.
- Native parsing là đường mặc định; tài liệu thiếu field hoặc mâu thuẫn đi
  `MANUAL_REVIEW`.
- WIP code/template changes phải được bảo toàn khi tiếp tục OCR workstream.

### TF-P1-002 — Checkpoint và local live smoke

- Implementation commit `53b22fb` đã push lên
  `origin/codex/m1-m2-document-understanding`; remote hash đã xác minh.
- API local đang nghe tại `http://127.0.0.1:8765` với PID quan sát tại checkpoint là
  `14312`; đây không phải production deployment.
- `/health` trả `ok`; `/api/templates` liệt kê đủ hai template.
- Hai DOCX gốc ngoài bộ regression đã trả đúng `LEAVE_REQUEST` và
  `OVERTIME_REQUEST`, cùng `AUTO_CONTINUE` và không có validation error.
- Hai session smoke-test đã xóa; không lưu raw PII trong tài liệu tracked hoặc log báo cáo.

### TF-P1-003 — OCR Lab Template-first UI

- Giao diện tổng chạy tại `http://localhost:3000`; API root `127.0.0.1:8765` redirect về đó.
- Chế độ mặc định “Mẫu chuẩn” gọi `/api/documents/process`, nhận DOCX và hiển thị field,
  missing fields, validation, confidence, recommended action cùng JSON đầy đủ.
- Luồng `/user/upload` cũ vẫn có trong chế độ “OCR / IDP cũ”.
- Browser smoke đơn nghỉ phép trả `SUCCESS` / `AUTO_CONTINUE`, 19 field cards,
  confidence và anchor match 100%; kết quả local được giữ mở cho người dùng.
- PID quan sát tại checkpoint: API `27752`, web `28852`; cả hai chỉ bind local.
- `tsc --noEmit` vẫn có lỗi baseline ở Phase 14/worker; build chính thức và lint không có error.

### TF-P1-004 — README cho các mẫu HCNS chuẩn

- README đưa Template-first Phase 1 và hai mẫu nghỉ phép/tăng ca lên thành luồng MVP mặc định.
- Làm rõ bộ regression gồm 14 hồ sơ synthetic thuộc 2 loại biểu mẫu, không phải 14 loại đơn.
- Thêm hướng dẫn thử DOCX mới trên `localhost:3000` và dẫn tới báo cáo metric chi tiết.
- Không xóa tài liệu cũ; Universal Intake, OCR/CCCD, generic IDP và Camunda vẫn được giữ.
- Lần chạy API test đầu thiếu `PYTHONPATH=src` nên lỗi collection; chạy lại đúng môi trường
  đạt 4/4. Repository hygiene và `git diff --check` đều pass.

### TF-P1-005 — Mentor-safe localhost

- Held-out nav, metrics, proof strip, evidence tab và private authorization note bị ẩn mặc định.
- Held-out summary/evidence không được fetch trong mentor view.
- Đặt `VITE_SHOW_HELDOUT=true` trước khi chạy web để bật lại chế độ quan sát riêng.
- Default build và private build đều pass; web 9/9 tests, lint 0 error/19 warning cũ.
- Browser smoke xác nhận không còn “REAL HELD-OUT · EVALUATE ONCE”, nav hoặc tab held-out.
- Một lần chạy hai build song song gặp `EBUSY` ở `dist`; chạy tuần tự sau đó đều pass.

### TF-P1-006 — Template-first evidence và CCCD

- API có `GET /api/documents/sessions` và `GET /api/documents/result?id=...`, chỉ đọc
  `template_first/result.json` của `LEAVE_REQUEST` và `OVERTIME_REQUEST`.
- Evidence ẩn danh sách upload HCNS generic cũ nhưng không xóa session hoặc chức năng legacy.
- Tab Template-first hiển thị danh sách, metadata DOCX native và field/JSON ở panel bên phải.
- Tab CCCD và panel Schema/JSON cũ được giữ nguyên.
- Browser smoke mặc định thấy một Template-first session và 30 CCCD, không thấy held-out/generic.
- API restart bằng `.venv`, PID quan sát tại checkpoint là `31572`; health trả `ok`.
- Lần start bằng Python hệ thống thiếu `cv2`; không thay đổi dữ liệu và đã sửa bằng `.venv`.

### TF-P1-007 — Product showcase không PII

- Khối hero bên phải thay ảnh tài liệu bằng showcase hai biểu mẫu nghỉ phép và tăng ca.
- Showcase thể hiện luồng DOCX → Template → JSON, native parsing, validation và quality routing.
- Không dùng ảnh tài liệu thật hoặc PII trong hero; kiểm tra trực quan localhost đã pass.
- Web build/tests 9/9, API tests 4/4, lint 0 error và 15 warning có sẵn.

### TF-P1-008 — Landing page HCNS

- Hero được tái cấu trúc theo landing tham chiếu, giữ CTA và navigation hiện có.
- Phần dashboard minh họa lấy số template, session Template-first và CCCD đã review từ trạng thái runtime.
- Không thêm taskbar, user menu, số liệu giả hoặc PII.

### TF-P2-002 — Multi-format hai biểu mẫu

- Đang là task Template-first duy nhất `IN_PROGRESS`; chưa mở TF-P2-003.
- DOCX và PDF native đi parser riêng, không gọi OCR; ảnh/PDF scan dùng PaddleOCR local.
- API/UI nhận năm extension và giữ panel metadata/JSON, bổ sung source/parser/OCR metadata.
- Mặc định chỉ còn một vùng upload cho DOCX/PDF/PNG/JPG/JPEG; ảnh/PDF được xem
  cạnh kết quả field/JSON. Luồng OCR/IDP cũ không bị xóa và có thể bật riêng bằng
  `VITE_SHOW_LEGACY_UPLOAD=true`.
- File nguồn Template-first nằm trong session private và được phục vụ lại qua
  `/api/documents/source` trên loopback.
- Local Real-Document Evidence phục vụ preview ảnh trực tiếp và preview PNG
  trang đầu của PDF qua `/api/documents/preview`; không còn placeholder PDF trắng.
- DOCX và PDF native đều đạt 10/10 classification, 90/90 required fields, 0 schema error.
- Sáu ảnh camera và sáu PDF scan đều xử lý/phân loại 6/6, schema sạch và bắt buộc review.
- OCR exact match đạt 31/54 (57.41%), thấp hơn gate 80%; sai số còn lại ở tên, chức vụ,
  phòng ban, lý do và nội dung công việc tiếng Việt.
- Không dùng Ground Truth để phục hồi dấu; phép thử VietOCR full-page không được đưa vào code
  vì làm metric giảm.
- Dataset local có 26 file thực so với 30 file khai báo và 10 tham chiếu image cũ bị stale.
- Báo cáo evaluator aggregate không chứa raw field value; raw probe tạm đã xóa.
- API preview 6 tests và web 9 tests/build pass; full checkpoint trước đó giữ
  Python 225 tests, Ruff, mypy, hygiene và diff check pass.
- API PID `36764`, web PID `28852`; health `ok`, OCR model đã load sau smoke.
- Live HTTP smoke ảnh camera trả đúng `LEAVE_REQUEST` / `MANUAL_REVIEW`; session đã xóa.
- UX smoke desktop xác nhận preview ảnh sticky nằm cạnh panel metadata/JSON; source
  PDF/PNG tải lại khớp SHA-256 và mọi session smoke đã xóa.

### TF-P2-002A — OCR Field Recovery checkpoint

- ROI cố định, parsing theo nhãn + vị trí hình học, vocabulary repair bảo thủ và
  provenance field-level đã được triển khai; recognizer v3 thử nghiệm không được
  promote vì chưa vượt primary.
- Locked image rerun mới nhất: 41/54 exact (75.93%); PDF scan đạt 36/54
  (66.67%). Cả hai đều classification 6/6, schema 0, `MANUAL_REVIEW` 6/6,
  false `AUTO_CONTINUE` 0.
- Gate 44/54 (81.48%) vẫn mở; còn mismatch aggregate ở tên động, `reason` và
  `workContent`. Không dùng Ground Truth/native twin và chưa mở TF-P2-003.
- Báo cáo evaluator lưu taxonomy field-level, chỉ aggregate/provenance metadata,
  không lưu giá trị OCR thô.

### TF-P2-003A — Version Governance & UAT Harness

- Đã hoàn tất và push lên `origin/main` tại commit `ae93bf0` sau checkpoint
  TF-P2-002A.
- Scope là manifest version đóng băng, ghép schema/parser và compatibility matrix;
  không thay đổi runtime OCR.
- Harness phải fail-closed khi registry, schema hoặc parser version lệch nhau và
  chỉ cho evaluator chạy với report aggregate-only.
- TF-P2-003B đã hoàn tất; TF-P2-002B đạt 48/54 trên ảnh và 45/54 trên PDF
  scan, sau đó UAT full matrix vượt tất cả gate.

### TF-P2-002B — Vietnamese OCR Candidate Evaluation & Field Recovery (DONE)

- Mục tiêu: đánh giá candidate recognizer/tiền xử lý cho các field động còn sai trên
  ảnh và PDF scan, không dùng Ground Truth/native twin để điền và không hardcode
  tên/nội dung.
- Phạm vi bắt buộc: 4 tên, 6 `reason`, 3 `workContent`; scan PDF thêm
  `department` và `jobTitle`.
- Acceptance: tối thiểu 44/54 required exact (81.48%), không regression các field
  đúng, schema errors 0, false `AUTO_CONTINUE` 0 và mọi OCR source `MANUAL_REVIEW`.
- Đã thêm EasyOCR `vi` dưới optional extra, không thay đổi PaddleOCR mặc định.
- Geometry grouping/dedup, OCR artifact repair và label continuation parsing phục hồi
  field động mà không dùng Ground Truth/native twin hoặc hardcode tên/nội dung.
- Ảnh locked subset: 48/54 exact, 6/6 classification, schema 0, review 6/6, false auto 0.
- PDF scan locked subset: 45/54 exact, 6/6 classification, schema 0, review 6/6, false auto 0.
- DOCX/native PDF regression: 90/90 exact mỗi format, schema 0; report chỉ aggregate.

### TF-P2-003B — UAT & Version Governance (DONE)

- `validate_template_versions.py` PASS; manifest FROZEN_V1, registry/schema/parser
  pairing và UAT policy không drift.
- Fail-closed parserVersion mismatch test PASS.
- UAT bốn format đủ 10/10 available/processed: DOCX 90/90, native PDF 90/90,
  image 82/90 (91.11%), scan PDF 77/90 (85.56%).
- Classification 10/10 cả bốn format, schema 0, OCR `MANUAL_REVIEW` 20/20,
  false `AUTO_CONTINUE` 0; report aggregate-only và 0 stale file references.
- Chưa có external deployment side effect; phạm vi checkpoint này là local-only.

### LOCAL-EVIDENCE-PREVIEW-001 — completed

- Preview panel giữa đã hiển thị ảnh HCNS trực tiếp và render trang đầu PDF bằng
  PDFium local; inspector schema/JSON bên phải được giữ nguyên.
- Test API mục tiêu đạt 7/7; web build và rendered HTML đạt 9/9; lint 0 error với
  các warning hiện hữu.
- Browser smoke trên localhost xác nhận PDF preview có kích thước 953×1348,
  ảnh preview 1448×1086 và metadata `LEAVE_REQUEST`/`OVERTIME_REQUEST` vẫn hiển thị.
- Report đã bổ sung hai screenshot Local Real-Document Evidence, hai screenshot CCCD
  do người dùng cung cấp (đã xác nhận synthetic) và hai Prediction JSON tách khỏi
  Ground Truth.

## Verified evidence

- Repository hygiene đã pass ở checkpoint gần nhất.
- README có workflow Mermaid end-to-end và badge profile.
- Ground Truth, prediction, source và model weights vẫn ở local/private.
- Template-first full suite đạt 219 tests; Ruff, mypy, compileall và hygiene đều pass.
- OCR Lab build và 8 web tests pass; lint giữ nguyên 19 warning có sẵn, không có error.

### TF-P2-004 — Vietnamese OCR Fidelity & ROI Boundary Recovery (BLOCKED/SUPERSEDED)

- Current branch is `codex/m1-m2-document-understanding`; HEAD includes
  `655f51c` parser boundary repair. Unrelated CCCD WIP remains uncommitted.
- The repair removes a preceding leave-period sentence when OCR combines it with
  the fixed reason label. Targeted parser/adapter tests: 19 passed; Ruff and
  repository hygiene passed.
- Paddle `PP-OCRv5_mobile_rec` was evaluated as an explicit candidate only:
  21/54 exact on locked images and 21/54 on locked scan PDFs, with 6/6
  classification, schema 0, 6/6 manual review, and false auto 0. It is not
  promoted. EasyOCR opt-in rerun is 50/54 images and 48/54 scan PDFs.
- The additional `PP-OCRv5_server_rec` image probe reached 17/54 and was also
  rejected without a scan run.
- Paddle candidates did not reach the promotion gate, so this Paddle-specific
  route is superseded by the evidence-driven backend selection below. VietOCR
  remains legacy/shadow and is not installed in Template-first.

### TF-P2-005 — Evidence-driven OCR Backend Selection (DONE)

- EasyOCR `vi-greedy` is the default Template-first OCR backend for image and
  scan PDF. Paddle remains an explicit rollback using
  `HCNS_TEMPLATE_OCR_BACKEND=paddle`.
- Full default UAT passed: DOCX 90/90, native PDF 90/90, image 86/90, scan PDF
  82/90; all formats classify 10/10, schema 0, OCR review 20/20 and false auto 0.
- Runtime is aggregate-only with 30/30 files/references and 0 stale references.
  CPU p95 was 23.5s/image and 22.6s/scan PDF; EasyOCR cache size 93.99 MiB.
- Explicit Paddle rollback smoke passed its routing/schema/review gates. No
  VietOCR dependency or model was added.

### DATA-00..DATA-05 — External dataset intake (DONE / HOLD)

- Source commit `dec17acbe2b409e0aa5daeb4db820d3e95d05bdf` is staged outside the
  repository; raw documents and model cache are not tracked.
- Inventory is pinned at 13 documents / 17 pages and is verified by SHA-256,
  source-format and page-count drift checks.
- Mapping covers CV, employment contract and certificate through generic IDP;
  Template-first v1 is explicitly unsupported for every category.
- Native TXT parser, certificate markers and short-contract markers were added
  with synthetic tests; PPTX remains text-only `PARTIAL` by policy.
- EasyOCR `vi-greedy` pilot: 13/13 processed, 0 failures, 12/13 folder-derived
  classification matches; report is aggregate-only with 0 raw OCR/field values.
- Final validation: Python `pytest` 239 passed; Ruff, mypy, compileall,
  repository hygiene and `git diff --check` passed.
- The user directed this simulated repository dataset to use a `PUBLIC` +
  `APPROVED` test profile. Promotion remains `HOLD` because independently
  reviewed Ground Truth is absent and 17 pages is below the benchmark minimum
  of 30.
- Exact next action: create a sealed Ground Truth split and the certificate
  schema, then rerun the existing aggregate benchmark without changing frozen
  Template-first schemas.

### DATA-06 — Certificate schema and Ground Truth review (IN_PROGRESS)

- Mapping now references `schemas/hr_document_families/certificate.schema.json`;
  `groundTruthStatus` is `DRAFT`.
- The pre-replacement artifact covered 13 cases / 17 pages and 55 pending
  fields. It is retained as a timestamped backup outside the staging root.
- Next action: an independent reviewer fills and confirms the source-document
  fields, then seals the artifact before any field-level benchmark run.

### DATA-07 — Local external-dataset Ground Truth review UI (IN_PROGRESS)

- DATA-07 was approved and implemented as a loopback-only review panel for the
  current 12 synthetic `cv`/`contract`/`ielts` cases (86 fields / 16 pages).
- The contract staging source was replaced from `D:\bo_mau_hop_dong_thu_viec`.
  Four canonical cases remain (two contracts × DOCX/PDF); PNG full-document
  previews are excluded as derivative files. Each contract has 14 review fields
  through `schemas/hr_document_families/probation_contract.schema.json`.
- CV/IELTS source files and review state are preserved; only the contract cases
  were rebuilt. The old contract staging directory is recoverable at
  `C:\tmp\hcns-dataset-run-dec17acb-contract-old-20260803`.
- API routes are `/external-dataset/review/summary`, `/document`, `/save`, and
  `/lock`. The API reads only the staging source and the private Ground Truth
  draft; predictions are not exposed. Draft writes and the seal marker remain
  outside Git.
- Start the UI with `start_dashboard.ps1 -ExternalDatasetRoot` and the optional
  inventory/draft paths. Set `VITE_SHOW_EXTERNAL_DATASET_REVIEW=true` (the
  launcher sets it automatically when the external root is supplied).
- DATA-07 is not a promotion approval: an independent reviewer still has to
  open each source, confirm the 56 contract fields (and any remaining CV/IELTS
  fields), and explicitly press `SEALED`.

### OCR-HO-V2-001 — CCCD held-out prediction seal (REVIEW)

- Fifteen file-level new CCCD images were selected from the Roboflow test set
  after excluding legacy/private SHA-256 matches and locked in the private
  manifest. Raw images, authorization, model cache, and predictions are not in
  Git.
- Phase 11.5 and Phase 11.6 both completed 15/15 with
  `SHADOW_REVIEW_ONLY`. The private prediction snapshot is sealed before any
  Ground Truth was opened; the aggregate status file reports
  `BLINDED_PREDICTIONS_READY`, `sampleGate=SUFFICIENT`, and
  `groundTruthPresent=false`.
- Lock verification passed for phase 11.6.0 with six model artifacts and the
  15-document development manifest. Held-out/lock tests (10), Ruff,
  `check_repository.py`, and `git diff --check` passed.
- Ground Truth audit found 15/15 source label files, but they are YOLO
  detection-only annotations (class IDs plus polygons/boxes) with no text
  transcription for the eight OCR fields. This is not an independent text
  Ground Truth and cannot support an exact OCR score.
- Decision: do not open/score the sealed predictions and do not promote. The
  manifest remains `PENDING_HUMAN_CONFIRMATION`; obtain a human-verified text
  transcription first, then evaluate the sealed snapshot exactly once.

## Next action

1. Giữ localhost/loopback là runtime target; không mở task deployment trong kế
   hoạch hiện tại. Giữ rollback Paddle.
2. Giữ CCCD/held-out workstream ngoài Template-first default.

### WEEKLY-REPORT-2026-W31 — completed

- Report artifacts live under `docs/weekly-reports/2026-W31/`.
- `assets/cccd/selection.json` remains as legacy ranking metadata; current report
  evidence uses two user-declared synthetic CCCD screenshots and two Prediction JSON files.
- The report has six unredacted input/result pairs for leave/overtime DOCX, PDF and image
  sources. These sources are AI-generated synthetic data; result cards come from actual
  engine output, not Ground Truth.
- Safe website screenshots were captured with no document selected. Run
  `python scripts/validate_weekly_report.py` before changing the report.

## First command after resume

```powershell
Set-Location "D:\AI Vin Thực Chiến\Side Project\PaddleOCR\hcns-automation-agent"
git status --short --branch
```
