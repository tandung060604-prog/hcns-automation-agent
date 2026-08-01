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
| TF-P2-003A | IN_PROGRESS | Version Governance và UAT Harness cho hai biểu mẫu | TF-P2-002A checkpoint | P1 |
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
- TF-P2-003B (execute UAT) vẫn `BLOCKED` cho đến khi TF-P2-002A đạt 44/54.
