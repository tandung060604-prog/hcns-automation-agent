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
| TF-P2-002 | PLANNED | Xem xét PDF/ảnh cùng template | TF-P1-001 và dữ liệu được phê duyệt | P2 |
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
