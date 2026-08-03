# Backlog

> Backlog có một task `IN_PROGRESS` tại mỗi workstream. Chi tiết trạng thái thực
> tế nằm ở [PROJECT_STATE.md](PROJECT_STATE.md); dữ liệu private không ghi ở đây.

| ID | Trạng thái | Mục tiêu | Phụ thuộc | Ưu tiên |
|---|---|---|---|---|
| OCR-HO-V2-001 | REVIEW | Đã seal prediction ẩn trên 15 CCCD held-out; chờ xác nhận Ground Truth để evaluate-once | Manifest v2, policy 11.6 | P0 |
| OCR-HO-V2-002 | DONE | Review Ground Truth độc lập, loại ảnh mặt sau, khóa queue và evaluate đúng một lần trên 14 ảnh | OCR-HO-V2-001 | P0 |
| OCR-HO-V2-003 | DONE | Local inspector đối chiếu Ground Truth và output Phase 11.5/11.6 sau evaluate-once | OCR-HO-V2-002 | P1 |
| TF-P1-001 | DONE | Template-first cho đơn nghỉ phép và tăng ca DOCX | 14 mẫu synthetic local | P0 |
| TF-P1-002 | DONE | Commit/push Template-first, chạy API local và live smoke hai DOCX gốc | TF-P1-001 | P0 |
| TF-P1-003 | DONE | Tích hợp Template-first vào OCR Lab localhost và hiển thị kết quả trích xuất | TF-P1-002 | P0 |
| TF-P1-004 | DONE | Cập nhật README theo các mẫu HCNS chuẩn, giữ nguyên tài liệu năng lực cũ | TF-P1-003 | P0 |
| TF-P1-005 | DONE | Ẩn held-out khỏi localhost dành cho mentor, giữ private feature flag | TF-P1-003 | P0 |
| TF-P1-006 | DONE | Evidence chỉ hiển thị đơn nghỉ phép/tăng ca và CCCD, giữ panel metadata | TF-P1-005 | P0 |
| TF-P1-007 | DONE | Thiết kế lại product showcase bên phải hero | TF-P1-006 | P1 |
| TF-P1-008 | DONE | Redesign landing theo tham chiếu, dùng trạng thái sản phẩm thật | TF-P1-007 | P1 |
| TF-P2-001 | PLANNED | Pilot Human Review qua Camunda User Task | TF-P1-001 | P1 |
| TF-P2-002 | IN_PROGRESS | DOCX/PDF/ảnh/scan cho hai template; native pass, OCR text gate mở | TF-P1-001 và dữ liệu được phê duyệt | P0 |
| TF-P2-002B | DONE | Vietnamese OCR Candidate Evaluation & Field Recovery cho field động còn sai | TF-P2-002A checkpoint, TF-P2-003A governance | P0 |
| TF-P2-003A | DONE | Version Governance và UAT Harness cho hai biểu mẫu | TF-P2-002A checkpoint | P1 |
| TF-P2-003B | DONE | Execute UAT và quản trị phiên bản trên bốn định dạng | TF-P2-002B đạt 44/54 | P1 |
| TF-P2-004 | BLOCKED | Paddle OCR fidelity candidates không đạt gate; superseded by evidence selection | TF-P2-003B, parser boundary checkpoint | P0 |
| TF-P2-005 | DONE | Evidence-driven OCR Backend Selection và controlled EasyOCR promotion | TF-P2-004 candidate evidence | P0 |
| WEEKLY-REPORT-2026-W31 | DONE | Audit và báo cáo mentor đã khử định danh | Evidence local được cấp quyền | P1 |
| TF-P2-003 | BLOCKED | UAT và quản trị phiên bản hai biểu mẫu | TF-P2-002 đạt gate | P1 |
| M4-CAM-001 | PLANNED | Dry-run Camunda 7.13 với External Task workers | OCR quality gate, mock HRIS | P1 |
| DATA-00 | DONE | Pin external source, isolate staging and reconcile dataset workstream | User-directed dataset commit | P0 |
| DATA-01 | DONE (PUBLIC TEST PROFILE) | Record explicit public/synthetic classification; keep unknown/private sources fail-closed | DATA-00 | P0 |
| DATA-02 | DONE | Build SHA-256/page-count inventory outside Git | DATA-01 | P0 |
| DATA-03 | DONE | Map CV/contract/certificate to generic IDP; add native TXT and versioned drift checks | DATA-02 | P0 |
| DATA-04 | DONE (HOLD) | Run EasyOCR aggregate-only pilot over 13 documents / 17 pages | DATA-03 | P0 |
| DATA-05 | DONE | Add synthetic inventory/mapping/parser regression coverage and checkpoint evidence | DATA-04 | P1 |
| DATA-06 | IN_PROGRESS | Add certificate schema and prediction-blind Ground Truth review artifact | DATA-05 | P0 |
| DATA-07 | IN_PROGRESS | Localhost review UI for source preview and independent confirmation of all 86 current external-dataset fields (56 contract fields in the reduced schema) | DATA-06 approved | P0 |

## DATA-00..DATA-05 acceptance criteria

- `DATA-00`: source commit is pinned; raw source is staged outside this Git
  repository; existing CCCD WIP remains untouched.
- `DATA-01`: governance fields are explicit; this synthetic repository source
  uses a user-directed `PUBLIC` + `APPROVED` test profile, while unknown/private
  sources still fail closed.
- `DATA-02`: every source has stable case ID, SHA-256, format and page count;
  inventory digest changes on any source drift.
- `DATA-03`: every category maps to a generic `DocumentType` or is rejected with
  a reason; Template-first v1 is never used as a fallback; TXT is native and
  PPTX remains `PARTIAL`.
- `DATA-04`: all staged documents run through the local pipeline; report is
  aggregate-only, OCR remains review-only, and no promotion occurs without
  approved Ground Truth.
- `DATA-05`: synthetic tests cover README exclusion, digest/page drift, mapping
  version drift, TXT routing and schema validation. Required checks are
  `pytest`, `ruff`, `mypy`, `compileall` and `check_repository.py`.
- `DATA-06`: certificate mapping has a versioned schema; the private review
  artifact covers every case/field with source digests, no model values, and
  remains `DRAFT` until an independent reviewer confirms it.
- `DATA-07`: localhost-only review routes expose source documents and the
  private draft for CV/contract/IELTS, hide predictions, persist edits outside
  Git, and allow `SEALED` only after every current field is explicitly
  confirmed. The contract subset is four cases × 14 fields; CV/IELTS review
  state is preserved across the contract-source replacement.

## OCR-HO-V2-001 acceptance criteria

- Manifest held-out gồm tối thiểu 15 tài liệu mới, không trùng SHA-256 với development.
- Prediction Phase 11.5 và Phase 11.6 được seal ngoài Git trước khi mở Ground Truth.
- Ground Truth được xác nhận từ ảnh gốc; prediction không hiển thị trong lúc review.
- Đánh giá đúng một lần, không chỉnh threshold trên tập held-out.
- Policy tiếp tục `SHADOW_REVIEW_ONLY` nếu candidate làm hỏng field primary hoặc không đạt gate.

## OCR-HO-V2-001 checkpoint (prediction sealed; evaluation pending)

- Dataset source: Roboflow test images selected deterministically by SHA-256 after
  excluding the 29 legacy Phase 11 samples and 8 prior private images. Fifteen
  file-level new documents were locked from 89 candidates.
- The source and authorization remain outside Git under the local private data
  root. The authorization records the user-directed local-only basis and the
  source dataset's CC BY 4.0 declaration; no network export was performed.
- Phase 11.5 and Phase 11.6 completed 15/15 documents with status
  `SHADOW_REVIEW_ONLY`; the sealed private prediction snapshot has
  `documentCount=15`, `groundTruthPresent=false`, and
  `predictionsHiddenDuringGroundTruthReview=true`.
- `validate_phase11_6_lock.py` returned `LOCK_VERIFIED` for phase `11.6.0`, six
  locked model artifacts, and 15 development documents. No promotion or
  threshold tuning was performed.
- Regression checks for this checkpoint: 10 held-out/lock tests passed, Ruff
  passed, repository hygiene passed, and `git diff --check` reported no content
  errors (only normal line-ending warnings).
- Ground Truth audit result: all 15 selected files have source YOLO label files,
  but those annotations contain only class IDs and polygons/boxes (field
  locations). They contain no text transcription for the eight OCR fields, so
  they are insufficient for an exact OCR evaluation.
- Decision: do not open or score the sealed predictions, and do not promote.
  The private manifest remains `PENDING_HUMAN_CONFIRMATION`; a human text
  transcription/verification pass is required before the one-time evaluation.

## TF-P1-001 acceptance criteria

- Hai template versioned được đăng ký và nhận diện bằng nội dung.
- Native DOCX parser được dùng; OCR không được gọi.
- Không tự điền field; thiếu/mâu thuẫn đi `MANUAL_REVIEW`.
- API và Camunda projection tương thích ngược, không chứa raw document.
- 14/14 mẫu đạt classification và required-field exact match 100%.
- Schema, unit test, static checks, tài liệu và handoff nhất quán.

## TF-P1-002 acceptance evidence

- Commit implementation `53b22fb` đã push và remote hash khớp local.
- API local bind `127.0.0.1:8765`; health và danh sách hai template phản hồi thành công.
- Hai DOCX gốc ngoài bộ regression được xử lý qua HTTP thật, đúng loại tài liệu,
  `AUTO_CONTINUE` và không có validation error.
- Chỉ báo cáo aggregate; session smoke-test đã xóa và không commit upload/PII.

## TF-P1-003 acceptance evidence

- `localhost:3000` chạy giao diện tổng; API root chuyển hướng về giao diện này.
- Template-first là chế độ mặc định, liệt kê hai template và giữ riêng luồng OCR/IDP cũ.
- Browser smoke hiển thị đúng loại đơn nghỉ phép, `SUCCESS`, `AUTO_CONTINUE`, field cards,
  quality metadata, JSON viewer và thao tác xóa local.
- Python 219 tests và web 8 tests pass; lint không có error hoặc warning mới.

## TF-P1-004 acceptance evidence

- README đặt hai mẫu HCNS chuẩn và cách thử DOCX mới trên dashboard ở phần đầu.
- README phân biệt 14 hồ sơ regression thuộc 2 loại biểu mẫu, dẫn tới báo cáo metric.
- Universal Intake, OCR/CCCD, generic IDP và Camunda cũ vẫn được giữ và gắn phạm vi rõ ràng.
- `git diff --check`, repository hygiene và 4 API tests pass.
## TF-P1-005 acceptance evidence

- Mentor view mặc định không render nav, metrics, tab hoặc tài liệu held-out.
- Frontend không gọi held-out summary/evidence khi feature flag tắt.
- `VITE_SHOW_HELDOUT=true` giữ nguyên chế độ quan sát riêng và build thành công.
- Browser smoke trên localhost không tìm thấy nhãn/nav/tab held-out; 9 web tests pass.

## TF-P1-006 acceptance evidence

- Endpoint chỉ đọc liệt kê và trả kết quả Template-first, lọc đúng nghỉ phép/tăng ca.
- Evidence mặc định chỉ còn tab Template-first và CCCD; upload HCNS generic không bị xóa.
- Panel metadata/Schema/JSON bên phải được giữ cho cả Template-first và CCCD.
- Browser smoke: một Template-first session, 30 CCCD; held-out và tab generic không hiển thị.

## TF-P1-007 acceptance evidence

- Hero dùng product showcase cho hai biểu mẫu chuẩn thay vì ảnh/visualization PII.
- Showcase mô tả chính xác DOCX → Template → JSON, validation và quality routing.
- Browser smoke xác nhận cả hai biểu mẫu và toàn bộ quality footer hiển thị rõ.

## TF-P1-008 acceptance evidence

- Landing hero giới thiệu HCNS Automation Agent, Template-first, Camunda và Human-in-the-Loop.
- Showcase dùng số template/session/CCCD thật, không thêm taskbar hoặc số liệu giả.
- Web build/tests pass; lint không có error.

## TF-P2-002 acceptance checkpoint

- API/UI nhận `.docx`, `.pdf`, `.png`, `.jpg`, `.jpeg`; panel metadata bên phải được giữ.
- UX mặc định chỉ có một vùng upload; ảnh/PDF hiển thị cạnh field/JSON. Luồng
  OCR/IDP cũ được giữ sau cờ `VITE_SHOW_LEGACY_UPLOAD`.
- File nguồn Template-first được lưu theo session và chỉ phục vụ lại qua endpoint
  loopback `/api/documents/source`.
- DOCX: 10/10 classification, 90/90 required-field exact match, 0 schema error.
- Native PDF: 10/10 classification, 90/90 required-field exact match, 0 schema error.
- Ảnh camera và PDF scan: 6/6 xử lý, 6/6 classification, 0 schema error,
  6/6 `MANUAL_REVIEW`, 0 false `AUTO_CONTINUE`.
- OCR required-field exact match hiện 31/54 (57.41%), chưa đạt gate đã duyệt là 80%.
- Không dùng Ground Truth/native counterpart để bù giá trị OCR; report chỉ chứa aggregate.
- Manifest nguồn khai báo 30 file nhưng thực có 26; 10 tham chiếu `files.image` bị stale.
- Live HTTP smoke ảnh camera trả đúng `LEAVE_REQUEST`, dùng PaddleOCR và bắt buộc
  `MANUAL_REVIEW`; session smoke đã xóa.
- API preview 6 tests và web 9 tests/build pass; full-suite checkpoint trước đó:
  Python 225 tests, Ruff, mypy, hygiene và diff check pass.

## TF-P2-002A implementation checkpoint

- Đã triển khai phục hồi field theo ROI cố định cho hai layout, parser dùng
  nhãn + vị trí hình học, và provenance chỉ chứa field/confidence/box/reason.
- Bộ sáu ảnh khóa đạt 41/54 (75.93%) và PDF scan đạt 36/54 (66.67%) ở lần chạy
  mới nhất; cả hai đều classification 6/6, schema 0, review 6/6, false auto 0.
- Gate 44/54 (81.48%) chưa đạt; lỗi còn lại là tên tiếng Việt động, `reason`
  và `workContent`. Không được mở TF-P2-003 hoặc dùng Ground Truth để bù giá trị.

## TF-P2-003A scope checkpoint

- Version manifest đóng băng `leave-request-v1` và `overtime-request-v1`, ghép
  `templateVersion`, `schemaRef`, `parserVersion` và required fields.
- UAT harness xác thực matrix DOCX/native PDF/ảnh/PDF scan, gate quality và
  aggregate-only reporting trước khi evaluator được chạy.
- TF-P2-003B (execute UAT) đã hoàn tất và pass toàn bộ gate sau khi candidate OCR vượt 44/54.

## TF-P2-002B completion checkpoint

- Trạng thái `DONE`; chỉ một task Template-first được phép triển khai tại một thời điểm.
- Phạm vi field: 4 tên động, 6 `reason`, 3 `workContent`; PDF scan thêm `department`
  và `jobTitle`.
- Không dùng Ground Truth/native twin để điền kết quả và không hardcode tên/nội dung.
- EasyOCR candidate được chọn cho controlled local evaluation: ảnh 48/54 (88.89%),
  PDF scan 45/54 (83.33%); cả hai 6/6 classification, schema errors 0, 6/6
  `MANUAL_REVIEW`, false `AUTO_CONTINUE` 0.
- Native DOCX/PDF vẫn 90/90 required-field exact match. Candidate không dùng
  Ground Truth/native twin để điền giá trị và report aggregate không chứa raw values.
- PaddleOCR là default ở checkpoint lịch sử này; TF-P2-005 đã đổi policy sau full UAT
  và ghi nhận rollback rõ ràng qua `HCNS_TEMPLATE_OCR_BACKEND=paddle`.

## TF-P2-003B completion checkpoint

- Trạng thái `DONE`; version manifest FROZEN_V1 khóa template/schema/parser pairing
  cho `leave-request-v1` và `overtime-request-v1`.
- UAT full matrix chạy đủ `docx`, `pdf`, `image`, `scan_pdf`, mỗi format 10/10
  available/processed; classification 10/10 và schema errors 0.
- Required-field exact match: DOCX 90/90, native PDF 90/90, image 82/90 (91.11%),
  scan PDF 77/90 (85.56%). OCR 20/20 items `MANUAL_REVIEW`, false `AUTO_CONTINUE` 0.
- Fail-closed mismatch test pass; report aggregate-only (`containsRawFieldValues: false`)
  và dataset integrity 30 actual files/30 references/0 stale references.
- Chưa có external deployment side effect; phạm vi kế hoạch hiện tại là local-only.

## TF-P2-004 checkpoint (2026-08-02)

- Parser boundary repair đã commit tại `655f51c`; targeted tests 19/19 pass.
- Paddle `PP-OCRv5_mobile_rec` candidate chỉ đạt 21/54 trên cả ảnh và PDF scan,
  nên không được promote. Classification 6/6, schema 0, OCR `MANUAL_REVIEW`
  6/6 và false `AUTO_CONTINUE` 0.
- Candidate `PP-OCRv5_server_rec` đạt 17/54 trên ảnh khóa và cũng bị loại.
- EasyOCR opt-in rerun đạt 50/54 ảnh và 48/54 PDF scan; cả hai pass quality
  gates. Candidate Paddle không đạt nên checkpoint này được supersede bởi TF-P2-005.

## TF-P2-005 checkpoint (2026-08-02)

- Trạng thái `DONE`; EasyOCR `vi-greedy` được promote làm backend mặc định cho
  ảnh/PDF scan của Template-first. Paddle rollback qua `HCNS_TEMPLATE_OCR_BACKEND=paddle`.
- Full UAT default: DOCX 90/90, native PDF 90/90, image 86/90, scan PDF 82/90;
  classification 10/10 cả bốn format, schema 0, OCR manual review 20/20,
  false auto 0 và report aggregate-only.
- CPU p95: 23.5s/image, 22.6s/scan PDF; model cache 93.99 MiB. Rollback Paddle
  smoke pass; VietOCR không được cài hoặc dùng trong route này.
- Deployment/production-readiness không thuộc kế hoạch hiện tại; không mở lại OCR
  candidate nếu chưa có evidence mới.

## OCR-HO-V2-002 checkpoint (local Ground Truth review gate)

- Đã thêm contract/backend local-only cho 15 CCCD held-out v2: summary, source
  preview, review/save, lock và evaluate-once. Endpoint không đọc prediction trong
  lúc người dùng xác nhận Ground Truth.
- Đã thêm UI `LOCAL GROUND TRUTH REVIEW · CCCD`, gated bởi
  `VITE_SHOW_GROUND_TRUTH_REVIEW=true`. Mỗi ảnh có 8 field, checkbox
  `Không có trên ảnh`, và hai assertion bắt buộc kiểm tra chữ/dấu với ảnh gốc.
- Prediction snapshot vẫn sealed ngoài Git; summary thực tế đang ở
  `PENDING_HUMAN_CONFIRMATION`, 4/14 tài liệu trong metric đã review, evaluate
  chưa chạy.
- Scope amendment: `CCCD-HO-005` được xác nhận là ảnh mặt sau
  (`OUT_OF_SCOPE_BACK`), không đánh dấu 8 field là không có và không đưa vào
  metric. Source audit vẫn giữ 15 ảnh; metric denominator còn 14 ảnh.
- Ground Truth và ảnh nguồn tiếp tục nằm ngoài repository tại private root; không
  ghi PII vào commit/report. Chỉ sau khi người dùng lưu đủ 14 tài liệu hợp lệ,
  giữ ảnh loại ở trạng thái `EXCLUDED`, và bấm khóa mới cho phép evaluate đúng
  một lần.
- Validation: `tests/test_cccd_heldout_review.py` 5 passed; web build và rendered
  HTML 9 passed; template API regression 25 passed; compileall và Ruff cho module
  mới/script/test đều pass.
- Evaluate-once đã chạy đúng một lần sau khi khóa Ground Truth: 14 tài liệu hợp lệ,
  112 field. Phase 11.5/11.6 đều đạt strict exact match 50.00%, ASCII exact
  match 50.89%, CER 80.71%, DER 16.14%; promotion gate giữ
  `SHADOW_REVIEW_ONLY` vì không đạt accepted precision/field presence và còn một
  sensitive false acceptance. Không có exact regression và không promote model.

## OCR-HO-V2-003 checkpoint (post-evaluation local inspector)

- Đã thêm endpoint read-only `/cccd-heldout/review/evaluation?id=...`; endpoint
  chỉ đọc Ground Truth và sealed prediction sau khi queue đã `CONFIRMED` và
  evaluate-once đã tạo report. Trong lúc review hoặc trước evaluation, prediction
  tiếp tục bị chặn.
- Localhost hiển thị output theo từng ảnh và 8 field: Ground Truth, Phase 11.5,
  Phase 11.6, strict/ASCII match, status/error class, confidence và ROI bbox.
  `CCCD-HO-005` không có output vì vẫn ngoài metric.
- Dữ liệu chi tiết chỉ được phục vụ loopback từ private root; không ghi raw OCR,
  Ground Truth hoặc prediction vào Git/report công khai.
- Validation: targeted review tests 5 passed, full Python suite 248 passed / 16
  subtests, web build + rendered HTML 10 passed, module Ruff/compileall passed,
  repository hygiene passed.
