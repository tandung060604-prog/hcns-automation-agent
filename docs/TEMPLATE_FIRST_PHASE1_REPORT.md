# Báo cáo Template-first Phase 1

## Kết quả

Đã triển khai closed-set pipeline cho:

- `leave-request-v1` / `LEAVE_REQUEST`;
- `overtime-request-v1` / `OVERTIME_REQUEST`.

Pipeline kiểm tra upload, đọc DOCX trực tiếp bằng OOXML, nhận diện template theo
anchor nội dung, trích xuất/chuẩn hóa field, validation, quality routing, lưu JSON
local theo session có thể xóa và tạo Camunda projection chỉ chứa metadata/reference.

## API

- `GET /api/templates`
- `POST /api/documents/process`

Các trạng thái routing: `AUTO_CONTINUE`, `MANUAL_REVIEW`,
`REJECT_UNSUPPORTED`, `TECHNICAL_ERROR`.

## Regression 14 mẫu

| Metric | Kết quả |
|---|---:|
| Template classification | 14/14 (100%) |
| Required-field exact match | 126/126 (100%) |
| All labeled-field exact match | 301/308 (97.73%) |
| JSON Schema errors | 0 |
| AUTO_CONTINUE | 14/14 |

Sai khác duy nhất là `department` trong 7 Ground Truth tăng ca: giá trị được gán
nhãn nhưng không xuất hiện trong DOCX. Theo nguyên tắc không suy diễn, parser giữ
`null`; field này là optional và không làm sai required-field gate.

## Required fields

Leave request: `employeeName`, `jobTitle`, `department`, `requestDate`,
`startDate`, `endDate`, `reason`.

Overtime request: `employeeName`, `jobTitle`, `requestDate`, `reason`,
`startDate`, `endDate`, `overtimeHoursPerDay`, `overtimeStartTime`,
`overtimeEndTime`, `totalOvertimeHours`, `workContent`.

## Validation đã chạy

- `python -m pytest -q`: 218 passed.
- `python -m ruff check src tests scripts`: passed.
- `python -m mypy src`: passed, 74 source files.
- `python scripts/check_repository.py`: passed.
- Regression 14 mẫu: passed.
- `git diff --check`: passed.

## Giới hạn

- Chỉ hỗ trợ native-text DOCX của hai template.
- Không có PDF/ảnh/OCR fallback trong Phase 1.
- Không hỗ trợ overnight overtime hoặc template tự do.
- Chưa deploy Camunda và chưa có side effect HRIS thật.

## Phase 2 đề xuất

Kết nối `MANUAL_REVIEW` với Camunda User Task trong một task riêng; giữ full
extracted payload ở private result store và chỉ truyền reference qua process
variables.

## TF-P2-002 — Multi-format checkpoint

Phase 1 vẫn được giữ nguyên như lịch sử ở trên. Phần mở rộng hiện tại nhận DOCX,
native PDF, PNG/JPG/JPEG và PDF scan cho đúng hai template đã đăng ký.

| Nguồn | Classification | Required-field EM | Schema | Routing |
|---|---:|---:|---:|---|
| DOCX | 10/10 | 90/90 (100%) | 0 | native |
| Native PDF | 10/10 | 90/90 (100%) | 0 | native |
| Camera image | 6/6 | 31/54 (57.41%) | 0 | 6/6 review |
| Image-backed PDF | 6/6 | 31/54 (57.41%) | 0 | 6/6 review |

OCR nhận đúng template và các trường số/ngày tốt hơn sau hiệu chỉnh phối cảnh,
nhưng mất dấu/ký tự ở tên, chức vụ, phòng ban và text tự do. Vì gate đã duyệt là
80%, TF-P2-002 vẫn `IN_PROGRESS`. Không dùng JSON Ground Truth hoặc DOCX/PDF
song sinh để sửa kết quả OCR.

Validation checkpoint: Python 225 tests; web build và 9 tests; Ruff, mypy,
repository hygiene và diff check đều pass. Live HTTP smoke bằng ảnh camera trả
đúng `LEAVE_REQUEST`, `paddleocr/pp-ocrv5-vi` và `MANUAL_REVIEW`; session đã xóa.
