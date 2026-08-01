# Backlog

> Backlog có một task `IN_PROGRESS` tại mỗi workstream. Chi tiết trạng thái thực
> tế nằm ở [PROJECT_STATE.md](PROJECT_STATE.md); dữ liệu private không ghi ở đây.

| ID | Trạng thái | Mục tiêu | Phụ thuộc | Ưu tiên |
|---|---|---|---|---|
| OCR-HO-V2-001 | IN_PROGRESS | Chạy prediction ẩn trên 15 CCCD held-out, khóa Ground Truth rồi evaluate-once | Manifest v2, policy 11.6 | P0 |
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

## OCR-HO-V2-001 acceptance criteria

- Manifest held-out gồm tối thiểu 15 tài liệu mới, không trùng SHA-256 với development.
- Prediction Phase 11.5 và Phase 11.6 được seal ngoài Git trước khi mở Ground Truth.
- Ground Truth được xác nhận từ ảnh gốc; prediction không hiển thị trong lúc review.
- Đánh giá đúng một lần, không chỉnh threshold trên tập held-out.
- Policy tiếp tục `SHADOW_REVIEW_ONLY` nếu candidate làm hỏng field primary hoặc không đạt gate.

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
- Chưa triển khai Railway, Camunda hay HRIS; bước kế tiếp cần task deployment riêng.

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
- Bước tiếp theo là task Railway/production-readiness riêng, không mở lại OCR
  candidate nếu chưa có evidence mới.
