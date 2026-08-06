# Handoff

## Repository context

- Repository: `D:\AI Vin Thực Chiến\Side Project\PaddleOCR\hcns-automation-agent`
- Branch: `codex/data-18-cv-scan-recovery`
- HEAD: `13aa284613ba363cedfb12f0adbe4f11e50a5725` (`main` merge containing DATA-17)
- Routing: [docs/README.md](README.md)
- Acceptance criteria: [docs/BACKLOG.md](BACKLOG.md)

## Current checkpoint (2026-08-06)

- Checkpoint task: `OCR-HO-V2-017A` is complete; the existing private secondary
  runtime is restored and lock-verified, while CCCD development remains `HOLD`
  because snapshot, exact/DER and automatic-ROI gates remain unmet.
- Prior checkpoint `DATA-19-CONTRACT-SEMANTIC-NORMALIZATION` remains implemented;
  its development status is `HOLD` because raw Contract strict remains 40/42;
  additive semantic scoring is 42/42 and does not replace raw strict EM.
- `DATA-20-REGRESSION-AND-GATE-HARNESS` is implemented and `HOLD`: applicable
  completeness is `99/99`, sensitive false acceptance `0`, parser-correct
  regressions `0`, schema `0`, classification `12/12`, and scan manual-review
  remains `5/5`; CV strict and fallback `+10pp` gates are not met.
- Party extraction is bounded to `Bên A`/`Bên B`; fallback strips person prefix/role
  suffix while preserving source characters. Native parser/schema/API remain unchanged.
- Fresh private artifacts are `C:\tmp\bo10-dev-predictions-data19-contract-normalization-v2.json`,
  `C:\tmp\bo10-dev-aggregate-data19-contract-normalization-semantic-v2.json` and its marker.
  Aggregate: strict 90/112, semantic 92/112, accepted 105/112, Contract 40/42 strict /
  42/42 semantic, CV 30/50 strict / 45/50 accepted, IELTS 20/20, classification 12/12,
  schema errors 0.
- DATA-20 private artifacts are `C:\tmp\bo10-dev-aggregate-data20-regression-gates-v4.json`,
  `C:\tmp\bo10-dev-data20-gate-report-v4.json` and their markers. No GroundTruth or
  evaluate-once artifact was modified.
- DATA-21 runner/tests are implemented. PaddleOCR 3.7 resolves the public pin
  `PaddleOCR-VL-1.6` to `PaddleOCR-VL-1.6-0.9B`; CPU initialization downloaded the
  private model tree but exceeded the local budget before the first scan, so the
  benchmark is `HOLD` rather than a quality PASS. Report/marker:
  `C:\tmp\bo10-data21-paddleocr-vl-benchmark-report-v5.json` and
  `C:\tmp\bo10-data21-paddleocr-vl.marker-v5.json`. Fallback, promotion and
  evaluate-once remain disabled; raw runtime stays outside Git.
- DATA-22 remains blocked until approved source rights/retention and the minimum
  corpus are supplied; do not open held-out or evaluate-once.
- Approved DATA-21 rerun used a 600-second CPU window. GPU could not be used because
  the installed Paddle wheel is CPU-only; native worker exit `1` after weight load
  produced no prediction. Rerun report/marker are
  `C:\tmp\bo10-data21-paddleocr-vl-benchmark-report-v8.json` and
  `C:\tmp\bo10-data21-paddleocr-vl.marker-v8.json`; quality remains unscored/HOLD.
- Validation: targeted pytest 27 passed; selected Ruff, compileall, `git diff --check`
  and state consistency passed. Full-file Ruff retains baseline findings outside DATA-19.
- OCR-HO-V2-017A smoke evidence: runtime
  `C:\Camunda\private-data\paddleocr-hr-baseline\runtime` has EasyOCR 1.7.2,
  VietOCR 0.3.13 and CPU Torch; all 6 model locks pass. One private CCCD smoke
  processed 16 crops with all 3 secondary profiles. Artifact:
  `C:\tmp\ocr-ho-v2-017a-preflight-20260806\preflight.log`.
- No OCR source or primary runtime changed; all fields remain manual review and
  no held-out/evaluate-once action occurred.
- Next READY task: `OCR-HO-V2-017B`; run the full 15/120 development replay only
  after approval, keeping shadow/manual-review-only.

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

### DATA-08 — Independent contract review (DONE)

- Review scope is the four canonical contract cases only: DOCX/PDF for the two
  agreements, 14 fields per case, 56 fields total. The two full-document PNG
  previews are derivative duplicates and real-world contract images are
  deferred.
- The DATA-08 panel defaults to `contract`, hides predictions, and supports
  source preview for both native DOCX/PDF inputs. CV/IELTS remain selectable in
  a separate scope and are not changed by contract review.
- Queue snapshot after contract completion: contract-001..004 are `CONFIRMED`,
  56/56 fields reviewed. The remaining active queue is three CV cases × 10
  fields and three IELTS cases × 5 fields (101 active fields total).
- CV `PLAIN_TEXT` (`cv-001`) and `PPTX` (`cv-004`) remain in inventory for
  traceability but are marked `OUT_OF_SCOPE` and excluded from active review and
  the seal gate. IELTS has no component scores; `overall_score` is the only
  score field. `recipient_name` is stored as one source-preserved string in
  `Family name + First name` order.
- The private draft was migrated outside Git with matching values preserved;
  the pre-migration artifact is recoverable at
  `C:\tmp\hcns-dataset-run-dec17acb-ground-truth-draft-pre-cv10-20260803.json`.
- The active Ground Truth is now `SEALED` / `CONFIRMED`; `canLock=false` because
  the queue is already locked. The seal marker is
  `C:\tmp\hcns-dataset-run-dec17acb-ground-truth-draft-SEALED.json` and records
  `predictionsOpened=false`.
- DATA-09 completed the typed canonical projection at
  `C:\tmp\hcns-dataset-run-dec17acb-typed-canonical.json`; it retains each
  reviewed source string/value beside its canonical type. The aggregate-only
  report is at `C:\tmp\hcns-dataset-run-dec17acb-data09-aggregate-pilot.json`:
  10 active documents / 101 active fields, 97 normalized, 4 missing optional
  values and 0 fields requiring re-review. Predictions remain unopened and
  promotion is `HOLD`.

### DATA-10 — Typed canonical projection approval (APPROVED)

- User-directed approval was recorded at
  `C:\tmp\hcns-dataset-run-dec17acb-typed-canonical-APPROVED.json` after
  re-validating both DATA-09 artifacts against their JSON Schemas.
- Approval covers read-only downstream use of the typed projection only. It
  does not open predictions, promote a recognizer, or enable automatic HR
  decisions; `promotionAllowed=false` remains locked.
- Approval snapshot: 10 active documents / 101 fields, 97 normalized, 4
  missing optional values and 0 fields requiring re-review.

### DATA-11 — Typed projection API/export (DONE — READ-ONLY)

- Added loopback GET-only endpoints: `/external-dataset/typed/summary`,
  `/external-dataset/typed/document?id=...` and
  `/external-dataset/typed/export?format=json|csv`.
- Each request verifies the DATA-10 approval marker, projection/report hashes,
  sealed Ground Truth metadata and aggregate counts before serving data. POST
  and DELETE on the typed route return `405`; no write path was added.
- Default document/export responses omit `sourceValue`; an explicit localhost
  document query may request source values for local inspection only. No OCR,
  prediction or promotion data is exposed.
- Startup accepts optional typed artifact paths through `start_dashboard.ps1`;
  when omitted, paths are inferred beside the external dataset staging root.
- Validation: 22 API/external-data regression tests passed; module Ruff passed.

### DATA-09-R1 — Sealed image-expansion typed projection (DONE, HOLD)

- Rebuilt the private projection from the sealed
  `2026-08-04-image-expansion` inventory/Ground Truth: 20 active documents /
  202 active fields, with `predictionsOpened=false`.
- Projection artifact:
  `C:\tmp\hcns-dataset-run-dec17acb-image-expansion-20260804-typed-canonical.json`
  (`sha256:2d06eb14bc744873362252b548aca03d2f900611a4cedd7dc40bda2fa787036e`).
- Aggregate-only artifact:
  `C:\tmp\hcns-dataset-run-dec17acb-image-expansion-20260804-data09-aggregate-pilot.json`
  (`sha256:71518b77da548be98be67bf13464f2aa482c1de6b4d46f48bdb296e52ac0db69`).
  Aggregate counts: 186 normalized, 16 missing, 27 partial, 0 requiring
  review; decision is `HOLD`, with no raw values, OCR text or predictions.
- Validation passed: 6 targeted tests, Ruff, schema validation, DATA-11
  semantic validation, mypy for `src`, and repository hygiene.

### DATA-10-R1 — Read-only approval (DONE)

- User-directed approval is recorded at
  `C:\tmp\hcns-dataset-run-dec17acb-image-expansion-20260804-typed-canonical-APPROVED.json`.
  The marker is bound to the DATA-09-R1 projection/report hashes and keeps
  `predictionsOpened=false` and `promotionAllowed=false`.
- DATA-11 bundle validation passed. This is read-only approval only; it does
  not open predictions, promote a model or enable HR side effects.

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

### OCR-HO-V2-004 — development shadow v1.1 (REVIEW)

- The parser is versioned `1.1.0`, fixed to 0° input, and always returns
  `MANUAL_REVIEW`; the local API/UI shows the version and orientation policy.
- Development regression used 15 archived reviewed images / 120 fields. The
  v1.1 candidate scored 36.67% strict exact, 40.00% ASCII exact, 50.75% CER,
  17.00% DER, and 70.00% field presence versus the 60.00%/61.67%/43.60%/
  12.65%/95.83% Phase 11.5 baseline.
- Decision is `DEVELOPMENT_FAIL` with 33 exact regressions. No production
  promotion and no mutation of the official 14-document held-out report.
- Next recommended task: evaluate a Vietnamese OCR/ROI candidate against this
  development gate; keep OCR-HO-V2-004 in REVIEW until a non-regressing build.

### OCR-HO-V2-005 — guarded candidate recovery (REVIEW)

- Implemented `phase11_5_cccd_v2.py` and
  `scripts/evaluate_cccd_ocr_ho_v2_005.py` for a shadow-only, fixed-0-degree
  candidate policy. Selection uses sealed Phase 11.5 OCR evidence only and
  forces every candidate field to `MANUAL_REVIEW`.
- Development result on 15 archived reviewed images / 120 fields: strict and
  ASCII exact remain 60.00%/61.67%; CER improves 43.60% → 43.06%; DER and
  presence do not regress; exact regression count 0; schema errors 0.
- Gate: `DEVELOPMENT_PASS`, with production promotion explicitly disabled.
  This preserves the current runtime and the official held-out evaluate-once
  result. Only one guarded recovery was applied; unresolved OCR evidence still
  needs a fresh ROI/recognizer run.
- New targeted tests: `tests/test_ocr_ho_v2_005.py` (5 passed).

### OCR-HO-V2-008 - token-alignment candidate (DONE, shadow-only)

- `phase11_8_cccd_v2.py` and `evaluate_cccd_ocr_ho_v2_008.py` implement the
  approved token-alignment candidate. Selection uses OCR ROI evidence only,
  requires independent family support, and never receives Ground Truth.
- Development replay: 15 documents / 120 fields, fixed 0°. Strict/ASCII exact
  60.00% -> 60.83% / 61.67% -> 63.33%; CER 43.60% -> 42.47%; DER 12.65%
  -> 12.25%; presence 95.83%; region selection 73.33% -> 81.67%.
- Exact improvements/regressions are 1/0; schema errors 0; all fields remain
  manual review. Gate is `DEVELOPMENT_PASS`, while production promotion stays
  disabled by policy. Do not alter localhost primary or rerun held-out without
  a separately approved promotion task.

### OCR-HO-V2-007 - address ROI + Unicode replay (REVIEW)

- `phase11_7_cccd_v2.py` and `evaluate_cccd_ocr_ho_v2_007.py` implement a
  shadow-only v11.7.1 candidate for `placeOfOrigin` and `placeOfResidence`.
  Label-aware same-row ROI, neighboring-label cleanup, and reversible Unicode
  repair are used; no Ground Truth or sibling document can fill a value.
- Development replay: 15 documents / 120 fields, fixed 0°, strict/ASCII exact
  60.00%/61.67%, CER 43.27%, DER 12.25%, presence 95.83%, region selection
  81.67%. Exact improvements/regressions are 0/0; schema errors 0; all fields
  remain manual review.
- Decision is `DEVELOPMENT_FAIL` because the gate requires an exact improvement,
  despite CER/DER/region metrics improving. Keep the candidate shadow-only;
  localhost primary and the official 14-document held-out evaluate-once result
  remain unchanged. Next task must provide a genuinely exact address recovery
  without regression before any promotion or held-out rerun.

### OCR-HO-V2-011 - deterministic address ROI (REVIEW)

- Added `phase11_9_cccd_v2.py` and a development evaluator for deterministic
  address crops: the origin band is bounded by the residence label and the
  residence band is bounded before expiry. Ground Truth remains scoring-only.
- Replay covered 15 reviewed images / 120 fields at fixed 0 degrees. The
  current machine lacks optional EasyOCR/VietOCR packages, so the runner
  explicitly recorded a Paddle-only replay rather than claiming secondary OCR.
- Result: strict exact 60.00% -> 60.00%, ASCII exact 61.67% -> 62.50%, CER
  43.60% -> 41.44%, DER 12.65% -> 15.81%, region selection 73.33% -> 79.17%,
  exact improvement/regression 0/0, schema errors 0, manual review 120/120.
- Decision: `DEVELOPMENT_FAIL`; do not promote, do not change localhost
  primary, and do not rerun the official held-out evaluate-once. The next
  candidate needs verified secondary-recognizer runtime (or a tighter
  Paddle-only rule) that produces an exact address recovery without DER
  regression.

### OCR-HO-V2-012 - full secondary recognizer replay (REVIEW)

- Restored the locked private EasyOCR 1.7.2 / VietOCR 0.3.13 / CPU Torch
  runtime and verified all EasyOCR/VietOCR model hashes. The replay runner
  now passes the secondary site-package path only to its subprocess, keeping
  Paddle's environment isolated.
- Fixed a pre-existing eager-import cycle in the Camunda adapter package with
  lazy runtime exports; public adapter imports remain available.
- Replay covered 15 development images / 120 fields at fixed 0 degrees:
  strict exact 60.00% -> 60.83%, ASCII exact 61.67% -> 62.50%, CER 43.60%
  -> 42.09%, DER 12.65% -> 11.46%, region selection 73.33% -> 83.33%,
  exact improvement/regression 1/0, schema errors 0, manual review 120/120.
- Decision: `DEVELOPMENT_PASS`, but still shadow-only with
  `productionPromotionAllowed=false`. Do not rerun held-out or promote until
  the separate promotion task is explicitly approved. Tests: 20 pass, Ruff
  pass, repository hygiene pass.

### OCR-HO-V2-013 - promotion review and localhost canary (REVIEW)

- `phase11_8_shadow_uat.py` now selects the private v11.9.1 artifact
  (`phase11_9_v2/field_consensus.json`) when the 012 development report is
  present; its old v11.8 path remains the fallback for existing tests.
- The loopback API reports schema
  `ocr-ho-v2-013-promotion-review/1.0.0`, candidate `11.9.1`,
  `SHADOW_REVIEW_ONLY`, `groundTruthLoaded=false`, and 15 pending documents.
  The web shadow tab displays the candidate version dynamically.
- Canary evidence is read-only until a human records each local decision.
  `DEVELOPMENT_PASS` is not a production promotion: the gate still has
  `productionPromotionAllowed=false`, and neither the primary runtime nor the
  official held-out evaluate-once artifact changed.
- Verification: targeted shadow/API tests 4 passed; live loopback health,
  summary and detail preview returned successfully; localhost web shell HTTP
  200.

### OCR-HO-V2-009 - local shadow UAT (REVIEW)

- Added `phase11_8_shadow_uat.py` plus local API routes for inspecting the
  v11.8.1 development candidate without opening Ground Truth. The UI is gated
  by `VITE_SHOW_OCR_HO_SHADOW_UAT=true` and shows the source image, baseline,
  candidate, changed/protected fields and provenance.
- Review decisions are local-only and stored in the private archive at
  `output/phase11/OCR_HO_V2_009_SHADOW_UAT_REVIEWS.json`. Every save requires
  source comparison, changed-field inspection and confirmation that the
  candidate remains `MANUAL_REVIEW`.
- The candidate is still shadow-only: development gate `DEVELOPMENT_PASS`,
  `productionPromotionAllowed=false`, no held-out rerun and no primary runtime
  promotion. The next human action is to review the 15 images in the new tab.
- Verification: `tests/test_phase11_8_shadow_uat.py` 3 passed and rendered web
  tests 11 passed. ESLint reports 0 errors and 23 existing warnings. Web build
  was blocked by the sandbox refusing `node_modules/.vite-temp` writes.

### OCR-HO-V2-006 - targeted ROI/recognizer replay (REVIEW)

- `phase11_6_cccd_v2.py` and `evaluate_cccd_ocr_ho_v2_006.py` implement a
  shadow candidate v11.6.1. The candidate evaluates five unresolved fields
  with fresh ROI crops and keeps the other fields at the Phase 11.5 baseline.
- Replay result: 15 documents / 120 fields, strict/ASCII 60.00%/61.67%,
  CER 42.52%, DER 13.83%, presence 95.83%. Exact improvements/regressions are
  0/0; schema errors are 0; all 120 fields require manual review.
- Decision is `DEVELOPMENT_FAIL`: DER regressed and no exact improvement met
  the promotion gate. Keep the candidate shadow-only and leave the official
  14-document held-out report plus localhost primary runtime unchanged.
- Next investigation should narrow the origin/residence ROI and address
  Unicode/diacritic handling before another candidate replay; do not promote
  or rerun held-out evaluate-once without a new approved task.

### M4-CAM-001 — Camunda closed-set contract alignment (DONE)

- BPMN was bumped to `2.2.0-shadow`; submit, confirm-type and re-upload forms
  expose only `LEAVE_REQUEST` and `OVERTIME_REQUEST`.
- `M4_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES` is enforced by the M4 extract handler.
  An out-of-scope type raises `DOCUMENT_INPUT_INVALID` before the operation runs.
- Asset tests compare all three form enums with the M4 allowlist and verify that
  the allowlist remains a valid subset of the global JSON Schema enum.
- Shadow locks remain unchanged: `autoContinueEnabled=false`, real side effects
  disabled and HRIS/notification handlers simulated.
- Validation: 39 targeted tests passed in 1.74s; Ruff passed; mypy reported no
  issues in 79 source files; repository hygiene and diff check passed.
- Next READY task is M4-CAM-002. It requires explicit approval before binding a
  runnable worker; no Camunda deployment was performed in M4-CAM-001.

### M4-CAM-002 — Worker composition and idempotent result (DONE)

- `hcns-agent-camunda-worker` is the local runner. It reads Camunda connection
  data from environment and composes the REST client, Template-first pipeline,
  OCR Lab session source resolver, private result store and M4 handlers.
- `M4TemplateStageOperations` binds exactly six document topics. The registry
  rejects missing or unexpected operations before polling.
- `document_parse_content` writes the private result plus idempotency index
  before `complete`; replay uses the original deterministic reference and does
  not invoke the pipeline again.
- Invalid input maps to `DOCUMENT_INPUT_INVALID`; technical failures map to
  External Task failure with decremented retry. Parse extends its lock to
  180 seconds before processing.
- Worker output is scalar/reference-only. The private JSON result may contain
  extracted values but stays under `HCNS_CAMUNDA_PRIVATE_ROOT/camunda_m4`.
- Verification: 52 targeted tests passed in 2.60s; Ruff passed; mypy reported no
  issues in 81 source files; repository hygiene and diff check passed.
- No BPMN/DMN deployment or Camunda server call was made. Correction remains
  reference-only pending M4-CAM-005.
- Superseded next-task marker: M4-CAM-003 is now DONE in the checkpoint below.

### M4-CAM-003 — Template result to DMN projection (DONE)

- The private result store persists `_m4DmnQualityVariables` with exactly eight
  scalar DMN inputs. Normalize returns that projection only; it does not expose
  raw values or use `MANUAL_REVIEW` as a gateway output.
- Native PASS stays `USER_REVIEW` under the locked shadow policy. Synthetic
  leave/overtime image and scan-PDF cases remain Human Review with
  `autoContinueEnabled=false` and zero false `AUTO_CONTINUE`.
- Missing required fields route to `REQUEST_REUPLOAD`; business inconsistencies
  route to `HR_REVIEW`; mismatch is verified against the BPMN Confirm Type path.
- DMN output is restricted to four workflow actions and the projection is
  checked against the exact Python contract, whitelist and JSON Schema.
- Verification: 59 targeted tests passed; Ruff passed; mypy reported no issues
  in 81 source files; repository hygiene and diff check passed.
- No Camunda deployment/server call was made. Correction remains reference-only
  and belongs to M4-CAM-005.
- Superseded environment marker: M4-CAM-004 is now DONE in the checkpoint below.

### M4-CAM-004 — Local deploy and smoke (DONE)

- Local Camunda BPM Run was verified at 7.13.0. Deployment now succeeds with
  one process definition and one decision definition.
- The initial HTTP 400 identified invalid BPMN XSD ordering. Moving
  `textAnnotation`/`association` after every `sequenceFlow` fixed deployment;
  an asset regression prevents recurrence.
- Synthetic leave and overtime instances reached `UserReview` with shadow
  routing locked off from auto-continue.
- Restart evidence retained the first active User Task. Same-key replay reused
  the original result reference and created no additional result file.
- Three synthetic instances completed with `SIMULATED` HRIS and notification
  history values only. Worker smoke processes were stopped; Camunda remains
  available locally for inspection.
- Verification: 60 targeted tests passed; Ruff passed; mypy reported no issues
  in 81 source files; repository hygiene and diff check passed.
- M4-CAM-005 is DONE: correction/re-upload, reviewer audit and revalidation
  passed without enabling real side effects.

### M4-CAM-005 — Human review, correction and re-upload (DONE)

- BPMN `2.3.0-shadow` exposes sanitized source/result/provenance/confidence/
  validation context on UserReview and HRReview, then records reviewer ID,
  RFC3339 timestamp, case version and payload hash through an audit topic.
- `CORRECTED` resolves only an opaque `correctionsReference`; the private store
  checks the current payload hash, archives the prior result, increments the
  case version and reruns template validation/DMN. Invalid or stale corrections
  fail closed through `CORRECTION_INVALID`.
- SLA timers escalate UserReview to HRReview and HRReview to FinalHR; neither
  timer has an approval path. `REQUEST_REUPLOAD` increments the counter and
  returns to UploadAgain.
- Camunda 7.13 deploy version `2.3.0-shadow` succeeded. Synthetic smoke passed
  both correction and re-upload loops, with mock-only HRIS/notification history.
  Private evidence contains five audit artifacts, one correction and one result
  revision; no private value is recorded here.
- Verification: 36 targeted Camunda tests passed; Ruff and mypy passed; worker
  smoke processes were stopped; Camunda remains available locally.

### M4-CAM-006 — Dry-run 10 scenario và quyết định shadow pilot (DONE)

- Runner: `scripts/run_camunda_m4_dry_run.py` / module
  `hcns_agent.adapters.camunda7.dry_run`; synthetic/local-only, private temp
  store, no network and aggregate-only output.
- Result: 10/10 scenario pass; native DOCX routes `USER_REVIEW`, OCR image/scan
  routes `HR_REVIEW` under the locked sensitive-field rule; mismatch confirmation,
  fail-closed invalid input, missing field re-upload, correction/revalidation,
  re-upload limit and retry/idempotent replay all match expected state.
- Safety gates: false `AUTO_CONTINUE=0`, duplicate result artifacts `0`, one
  technical retry, `realSideEffectsEnabled=false`,
  `containsRawFieldValues=false`.
- Decision: approve a gated shadow pilot for only leave/overtime in isolated/local
  runtime. Keep `autoContinueEnabled=false` and mock HRIS/notification. M5
  authorization is still required for production/public endpoint/real writes.
- Verification: `tests/test_camunda_m4_dry_run.py` passed; no CCCD or private
  dataset files were changed.

### M5-CAM-001 — Shadow-pilot authorization (READY)

- User confirmed opening M5. The task is authorization/runbook preparation only;
  no real pilot cohort has run and no production permission was inferred.
- Runbook: `docs/CAMUNDA_M5_SHADOW_PILOT_RUNBOOK.md`; scope is the six-type
  review-first closed set in local/isolated Camunda 7.13 with
  `autoContinueEnabled=false` and simulated HRIS/notification. Leave/overtime
  remain the first eligible shadow cohort; the four new families require their
  own gates.
- Before execution, the business owner must fill cohort, reviewer, time window,
  retention and rollback authority. Raw values, credentials and private logs stay
  outside Git.
- First action after resume: read the runbook, complete the five gates, then run
  the documented preflight; do not start a cohort before all gates pass.

### OCR-EVIDENCE-LOCAL-001 — Unified local prediction versus Ground Truth (DONE, HOLD)

- The localhost workspace now has a single `TỔNG QUAN ĐỐI CHIẾU LOCAL` tab. It
  reuses the existing loopback summaries and links back to the field/session
  inspectors; it does not fabricate predictions for DATA-10 or expose raw PII.
- Runtime handoff: web `http://localhost:3000/workspace`, API
  `http://127.0.0.1:8765`. The current local process uses the private CCCD
  shadow archive and the image-expansion typed dataset roots documented in the
  previous checkpoint.
- Evidence decision: `NO_CAMUNDA`. Template-first is usable for its native
  and OCR review flow, while CCCD and broad HCNS held-out remain below the
  prediction gate. DATA-10-R1 is prediction-blind Ground Truth normalization.
- Next READY task should create/run a prediction artifact for the active
  CV/IELTS/contract dataset and use the unified tab for one aggregate-only
  comparison. Keep Camunda untouched until that evidence and the CCCD gate
  are approved.

### DATA-12 - Private prediction artifact and aggregate evaluation (DONE, HOLD)

- Prediction was generated from source documents only for 20 active documents
  and 202 typed fields. Native formats use the existing parser; image and PDF
  scan inputs use PaddleOCR. Ground Truth stayed unopened during prediction.
- The immutable evaluate-once report records classification 11/20, exact
  field matches 49/202 (24.3%), presence 86/202 (42.6%), and schema errors 0.
  Diagnosis counts are PARSER_MISSED=16,
  OCR_RECOGNIZED_PARSER_MISSED=47, OCR_NOT_RECOGNIZED=87.
- The report is HOLD with promotionAllowed=false; OCR remains MANUAL_REVIEW
  and false AUTO_CONTINUE=0. Raw prediction values and the marker are
  private files under C:\tmp, never committed.
- Local handoff: select DATA-12 Prediction + GT at
  http://localhost:3000/workspace; the loopback API serves summary and
  document comparison routes. DATA-10 and Camunda remain untouched.
- Next READY task is development-only classifier/parser recovery. The
  consumed evaluate-once marker must not be rerun; prepare a new artifact for
  any later gate.

### DATA-13 - OCR scope allowlist (DONE, HOLD)

- The original DATA-13 evaluate-once artifact remains immutable and records the
  previous CCCD/certificate-only policy. It must not be reopened.
- Evaluate-once result: 20 total / 11 evaluated / 9 excluded, 26/96 exact,
  59/96 present, schema errors 0, false `AUTO_CONTINUE=0`, decision `HOLD`.
  Private prediction/report/marker files are under `C:\tmp` and were not added
  to Git. DATA-12 and Camunda remain unchanged.
- Local handoff: select `DATA-13 · OCR SCOPE` at
  `http://localhost:3000/workspace`; excluded cases show
  `UNSUPPORTED_NO_OCR · khong tinh metric`.

### DATA-14 - Shared family parser recovery (DONE/DEV HOLD)

- Visual OCR scope now includes CV, employment contract, contract appendix and
  HR decision; every OCR result remains `MANUAL_REVIEW`.
- External prediction mapping reuses Phase 17 bounded-label/section helpers and
  emits `extractor`, `method`, `sourceSpan` and `reviewReason` provenance.
- Validation: full Python suite 316 passed; touched Ruff and source mypy passed;
  API `/health` is `ok` on loopback. No Ground Truth or evaluate-once artifact
  was changed.
- The bounded development-only prediction split is recorded in DATA-15 below.

### DATA-15-PREDICTION-INSPECTOR - Prediction-only localhost (DONE/DEV HOLD)

- The user did not provide Ground Truth. The 41.96% value in DATA-15 is a
  provisional local source-reviewed annotation, not an authoritative accuracy
  result.
- `http://localhost:3000/workspace` → `DATA-13 · OCR scope` serves the 12-file
  prediction artifact with `PREDICTION_READY`, `Field exact=—` and a visible
  prediction-only warning. Each field exposes status, method, source span/bbox
  and review reason.
- The old DATA-13 evaluate-once marker was not reopened or modified. Confirm
  or correct Ground Truth first, then run a new development aggregate.

### DATA-15-GT-REVIEW - Official Ground Truth input (READY/DRAFT)

- A fresh prediction-blind draft is configured at
  `C:\tmp\bo10-official-ground-truth-draft-20260805.json`: 12 documents, 112
  fields, all pending and empty. It is separate from the provisional
  source-reviewed file and from the DATA-13 prediction artifact.
- Use `http://localhost:3000/workspace` → `DATA-08 · 4 contract case review`.
  The panel now exposes source preview, field inputs, absent/unreadable
  checkboxes, per-case confirmation, and final SEALED. No benchmark has run.
- Current state is `DRAFT`, `0/112` confirmed, `canLock=false`. Do not click
  SEALED until all values have been checked against the original documents.

### DATA-15-GT-SEALED - Official Ground Truth locked (READY FOR DEV AGGREGATE)

- GroundTruth is now `SEALED`/`CONFIRMED`: 12 documents and 112/112 fields.
- Seal metadata is private at
  `C:\tmp\bo10-official-ground-truth-draft-20260805-SEALED.json` with
  `predictionsOpened=false`.
- No benchmark has run yet. Next action is a separate development aggregate;
  never modify or reopen the sealed GroundTruth.

### DATA-15-DEV-AGGREGATE - Official development comparison (DONE / HOLD)

- The sealed GroundTruth and DATA-13 prediction artifact were compared once in
  a separate private development report. The old evaluate-once artifact was
  not touched.
- Strict exact: `30/112` (`26.79%`); accepted long-text policy (case-insensitive
  and at least 80% token coverage): `43/112` (`38.39%`). Classification `11/12`,
  schema errors `0`; Contract `16/42`, CV `27/50`, IELTS `0/20` accepted.
- Report/marker are
  `C:\tmp\bo10-dev-aggregate-comparison-official-20260806.json` and
  `C:\tmp\bo10-dev-aggregate-comparison-official-20260806.marker.json`.
  DATA-13 localhost is now `DEVELOPMENT_EVALUATED` and exposes per-field
  GroundTruth/prediction/evidence. Promotion remains `HOLD`.

### DATA-16-PARSER-V2 - Contract/CV parser rerun (DONE / DEV HOLD)

- Native fixes are in `apps/ocr_lab/api/phase15_idp.py` and
  `apps/ocr_lab/api/external_dataset_prediction.py`: section-aware CV parsing,
  multi-column header/contact handling, Contract narrative/multiline labels,
  Vietnamese dates and schedule-derived weekly hours.
- Fresh private artifacts:
  `C:\tmp\bo10-dev-predictions-data13-parser-v2-20260806.json`,
  `C:\tmp\bo10-dev-aggregate-comparison-parser-v2-20260806.json`, and marker.
  Strict `69/112` (`61.61%`), accepted text `82/112` (`73.21%`), Contract
  `40/42`, CV `42/50`, IELTS `0/20`, classification `11/12`, schema errors `0`.
  Decision remains `HOLD`.
- API `127.0.0.1:8765` and localhost DATA-13 are connected to parser-v2; the
  visible tab shows both metrics and field-level GroundTruth/prediction/evidence.

Next READY action: improve certificate and scanned-CV OCR while keeping scan/
image results manual-review-only; preserve sealed GT and evaluate-once.

### DATA-15 - User bundle development benchmark (DONE/DEV HOLD)

- The 12-file bundle from `D:\bo_10_file_contract_cv_ielts_v2` was copied to a
  new private staging root and inventoried without changing the existing DATA-13
  root, Ground Truth or evaluate-once marker.
- PaddleOCR local prediction completed for all 12 documents. Independent
  source review confirmed and sealed 112 Ground Truth fields with
  `predictionsOpened=false`. The separate development aggregate comparison
  scored 47/112 exact (41.96%): Contract 30/42, CV 17/50, IELTS 0/20;
  classification agreement was 11/12 and schema errors were 0.
- Diagnostics: `PARSER_MISSED=13`,
  `OCR_RECOGNIZED_PARSER_MISSED=9`, `OCR_NOT_RECOGNIZED=23`; OCR remains
  manual-review-only and false `AUTO_CONTINUE=0`. Decision is `HOLD`.
- Private artifacts: `C:\tmp\bo10-dev-split-20260805.json`,
  `C:\tmp\bo10-dev-predictions-data13-private-20260805.json`,
  `C:\tmp\bo10-dev-ground-truth-draft-20260805.json`,
  `C:\tmp\bo10-dev-ground-truth-draft-20260805-SEALED.json`, and
  `C:\tmp\bo10-dev-aggregate-comparison-20260805.json`.
- Next READY action: fix IELTS OCR/layout and contract/CV label mapping using
  these field diagnostics, then create a fresh held-out split. Do not reopen
  the consumed DATA-13 evaluate-once artifact.

### LOCAL-SCOPE-001 - Mentor-safe localhost (DONE)

- The default local profile shows only active upload/template evidence. Held-out,
  Ground Truth, Shadow UAT and external dataset review are private-flagged and
  are not fetched when their flags are `false`.
- Keep `VITE_SHOW_LEGACY_UPLOAD=true` locally for CCCD/certificate OCR. Set a
  review flag to `true` only for a private observation session, then restart Vite.
- No private artifact or evaluation marker was removed. Next task must read the
  three state files and select one `READY` task before changing code.

### DATA-17 - Certificate/IELTS and scanned-CV OCR (DONE / DEV HOLD)

- Added a local hybrid OCR route: EasyOCR `vi+en` for scanned CV and local
  PaddleOCR for IELTS layout/pattern recovery. Native DOCX/PDF continues to
  use the shared parser path.
- The 12-document development comparison covers 112 sealed fields. Strict
  exact is `90/112` (`80.36%`); accepted long-text coverage is `104/112`
  (`92.86%`). Contract is `40/42` strict, CV `30/50` strict and `44/50`
  accepted, IELTS `20/20` strict. Classification is `12/12`; schema errors
  are `0`.
- All image/scan outputs remain `MANUAL_REVIEW`: 5 scanned documents, 0 false
  auto-continue and 0 `UNSUPPORTED_NO_OCR`. The API/UI shows field-level
  GroundTruth, prediction, evidence and review reason at DATA-13.
- Private artifacts are `C:\tmp\bo10-dev-predictions-data13-ocr-v7-20260806.json`,
  `C:\tmp\bo10-dev-aggregate-comparison-ocr-v7-20260806.json` and its marker.
  This is development-only (`evaluateOnceArtifactTouched=false`,
  `promotionAllowed=false`); the old evaluate-once artifact and sealed GT were
  not changed. Remaining HOLD items are CV narrative OCR truncation/coverage
  and one Contract representative-name semantic subset.

## First command after resume

```powershell
Set-Location "D:\AI Vin Thực Chiến\Side Project\PaddleOCR\hcns-automation-agent"
git status --short --branch
```

### OCR-HO-V2-015 - canonical CCCD diagnostic checkpoint (DONE / HOLD)

- Added `scripts/analyze_ocr_ho_v2_015.py`; the historical 014 analyzer now
  dispatches to it without overwriting the 014 report.
- Added diagnostic gates and a regression test proving snapshot mismatch holds
  development and held-out readiness. Target tests: `10 passed`; Ruff on all
  touched OCR-HO-V2 files: pass.
- Private aggregate report:
  `C:\Camunda\private-data\paddleocr-hr-baseline-archive-20260803\output\phase11\reports\CCCD_OCR_HO_V2_015_DIAGNOSTIC.json`.
  It records dataset isolation (`CCCD` / `DATA-HO-014`), baseline `11.9.1`,
  protocols, artifact digests, DER counts, error transitions, and no raw PII.
- Observed: `SNAPSHOT_MISMATCH`, exact regression `1`, schema errors `0`,
  protected regressions `0`, automatic ROI `13.33% / 13.33% / 6.67%` for
  fullName/origin/residence, and oracle ROI `100% / 100% / 100%`. Both gates
  are `HOLD`; no evaluate-once, primary-runtime promotion, or held-out opening.
- Next decision: review detector/snapshot drift first. Do not start 016A/016B
  until the error class and smallest affected layer are explicitly selected.

### OCR-HO-V2-015A - drift and ROI attribution checkpoint (DONE / 016A READY)

- The first 015 automatic-ROI calculation used `result.document.pages`, while
  the sealed manifest was created from `result.phase11.pages`. That source
  mismatch invalidated the initial `13.33% / 13.33% / 6.67%` ROI figures.
- After correction, automatic ROI is `53.33% / 60.00% / 13.33%` for
  fullName/origin/residence. Across all target fields, detector misses are
  `0`, crop/page misses are `0`, and all failures are boundary/line-selection
  misses. Residence is `13/15` boundary misses: `8` inside the automatic region
  bbox but not selected, `5` outside the bbox.
- Snapshot drift is confirmed rather than resolved: baseline 11.9.1 and
  15/120 scope are stable, but README candidate numbers do not reproduce from
  the current sealed candidate artifact. Candidate metrics remain explicitly
  oracle-line diagnostic; the gate remains `HOLD`.
- Decision: mark `OCR-HO-V2-016A` `READY` for one minimal boundary-rule patch.
  Do not change recognizer, parser, normalization or primary runtime in 016A;
  require a fresh development replay after the patch.

### OCR-HO-V2-016A - residence anchor boundary replay (DONE / HOLD)

- Implemented one boundary-only change in `phase11_10_cccd_v2.py`: retain a
  residence anchor line when the existing field-candidate cleanup yields at
  least two tokens. Added one synthetic regression test; no recognizer,
  parser, normalization or primary-runtime path changed.
- Fresh local replay is prediction-blind and aggregate-only over `15/15` CCCD
  documents and `120/120` fields with baseline `11.9.1`, candidate `11.10.1`,
  and `AUTO_DETECTOR` mapping. Report:
  `C:\tmp\cccd-ho-v2-016a-stage-20260806\CCCD_OCR_HO_V2_016A_DEVELOPMENT_REPLAY.json`.
- Results: strict exact `60.00%` vs baseline `60.83%`, ASCII `63.33%` vs
  `62.50%`, CER `40.15%`, DER `14.62%` (`37/253` vs `29/253`), presence
  `95.83%`; exact improvement `0`, exact regression `1`, schema errors `0`,
  protected regressions `0`. Automatic ROI is `53.33% / 60.00% / 66.67%`
  for fullName/origin/residence. Snapshot mismatch keeps both gates `HOLD`.
- All fields remain manual review (`acceptedCoverage=0`, sensitive false
  acceptance `0`); no primary promotion, held-out opening or evaluate-once.
  Replay was Paddle-only because EasyOCR/VietOCR optional runtimes are not
  installed. Next action is review evidence before any 016B layer change.

### OCR-HO-V2-016A-R1 - independent oracle diagnostic (DONE / HOLD)

- Analyzer now accepts a separate oracle phase root and reports oracle metrics
  outside the AUTO_DETECTOR gate. The private R1 replay used sealed line IDs in
  a copied staging tree; the 016A AUTO artifact was not overwritten.
- Report:
  `C:\tmp\cccd-ho-v2-016a-r1-20260806\CCCD_OCR_HO_V2_016A_R1_DIAGNOSTIC.json`.
  Oracle ROI is `100% / 100% / 100%`; oracle exact `60.00%`, ASCII `62.50%`,
  CER `39.07%`, DER `11.86% (30/253)`, presence `95.83%`.
- Oracle classes are parser contamination `15`, recognizer miss `13`, and
  diacritic miss `5`; select parser cleanup as the single provisional 016B
  layer. Exact and DER still fail acceptance, so 016B remains BLOCKED; all
  fields stay manual review and no held-out/evaluate-once/promotion occurred.

### OCR-HO-V2-016B - parser-only replay (DONE / HOLD)

- Candidate `11.10.2` changed only parser cleanup for merged residence labels;
  recognizer, Unicode normalization, reading order and ROI code were unchanged.
  Regression suite: `13 passed`; touched-file Ruff, compileall and state checks
  pass.
- Fresh AUTO_DETECTOR replay report:
  `C:\tmp\cccd-ho-v2-016b-rerun-20260806\CCCD_OCR_HO_V2_016B_DEVELOPMENT_REPLAY.json`.
  Results remain exact `60.00%`, ASCII `63.33%`, CER `40.15%`, DER `14.62%`
  (`37/253`), presence `95.83%`; exact improvements `0`, exact regression `1`,
  schema errors `0`, sensitive false acceptance `0`. Parser cleanup did not
  clear the recognizer consensus bottleneck, so the development gate is HOLD.
- Do not continue to another layer or promote. Keep all fields manual review;
  next decision requires a separately approved recognizer/runtime task.

### OCR-HO-V2-017A - secondary-runtime preflight (DONE / HOLD)

- Reused the existing private runtime at
  `C:\Camunda\private-data\paddleocr-hr-baseline\runtime`; no package/model was
  added. EasyOCR `1.7.2`, VietOCR `0.3.13`, CPU Torch, and all six policy model
  hashes/sizes passed `validate_phase11_5_lock.py`.
- A one-document private smoke initialized the worker and processed 16 crops with
  `easyocr_vi`, `vietocr_vgg_seq2seq`, and `vietocr_vgg_transformer`; warnings were
  runtime-only (`easyocr_scalar_overflow`, Torch load/nested-tensor warnings).
- Evidence: `C:\tmp\ocr-ho-v2-017a-preflight-20260806\preflight.log` and the
  private `phase11_10_v2_017a_preflight_private` directory. The prior 15-document
  report was restored from the archive after the single-document smoke.
- No OCR source, primary runtime, GroundTruth, held-out artifact, or evaluate-once
  marker changed. Next READY task is `OCR-HO-V2-017B`: full development replay.
