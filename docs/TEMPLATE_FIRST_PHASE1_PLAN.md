# Kế hoạch Template-first Phase 1

## Mục tiêu

Chuyển MVP sang xử lý closed-set cho hai biểu mẫu DOCX chuẩn:

- `leave-request-v1` (`LEAVE_REQUEST`);
- `overtime-request-v1` (`OVERTIME_REQUEST`).

DOCX có text được đọc trực tiếp bằng parser OOXML hiện có. Phase này không dùng OCR,
không gọi dịch vụ cloud và không mở rộng sang loại tài liệu khác.

## Kiến trúc hiện tại

Pipeline hiện tại dùng Ports and Adapters:

```text
DocumentSource
  -> format detection + safety
  -> native DOCX parser
  -> CanonicalDocument
  -> classifier/extractor/quality gate
  -> result reference + Camunda variables
```

Local API dùng `ThreadingHTTPServer` trong `apps/ocr_lab/api/serve_dashboard_api.py`.
Camunda 7 adapter đã có whitelist process variables và không nhận raw document.

## Thay đổi dự kiến

- Thêm template registry, content-anchor detector và contract kết quả versioned.
- Thêm parser/validator riêng cho đơn nghỉ phép và đơn tăng ca.
- Thêm `OVERTIME_REQUEST` vào document/Camunda contract.
- Thêm JSON Schema cho output của từng template.
- Thêm `POST /api/documents/process` và `GET /api/templates`.
- Giữ pipeline generic cũ để tương thích, nhưng template endpoints chỉ hỗ trợ hai mẫu.
- Thêm regression runner nhận `--data-root`; không đưa DOCX/Ground Truth vào Git.

## Rủi ro tương thích

- DOCX có thể chia một câu thành nhiều XML run; detector/parser phải làm việc trên
  `CanonicalDocument`, không phụ thuộc filename hay một run riêng lẻ.
- API cũ đang phục vụ OCR Lab; route mới không được thay đổi route `/user/*`.
- Worktree đang có thay đổi Phase 11.6/CCCD; task này không sửa các file đó.
- Trường không có trong biểu mẫu phải giữ `null`; mâu thuẫn hoặc nhiều candidate phải
  chuyển `MANUAL_REVIEW`.

## Kế hoạch kiểm thử

1. Unit test detector, filename independence, normalization và unsupported document.
2. Unit test parse/normalize/validate cho từng template.
3. API contract test cho danh sách template và response xử lý.
4. Camunda contract test bảo đảm chỉ có scalar/reference được whitelist.
5. Regression 14 mẫu local: classification 100%, required-field exact match 100%,
   output pass JSON Schema.
6. Chạy toàn bộ pytest, Ruff, mypy và repository safety check.
