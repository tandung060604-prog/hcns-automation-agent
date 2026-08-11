# AGENTS.md

## Mission

Phát triển nền tảng Agent HCNS có IDP đa định dạng, Camunda orchestration và
Human-in-the-loop.
Ưu tiên theo thứ tự: an toàn PII, đúng nghiệp vụ, khả năng kiểm chứng, thay đổi
nhỏ, tiết kiệm token.

## Read first

Chỉ đọc các file cần cho tác vụ:

1. `docs/PROJECT_STATE.md`
2. file `AGENTS.md` gần thư mục đang sửa nhất
3. tài liệu được route trong bảng dưới

| Tác vụ | Chỉ đọc thêm |
|---|---|
| OCR/model | `docs/MODEL_GUIDE.md`, `docs/OCR_METHODS_AND_METRICS.md`, `src/hcns_agent/ports/ocr.py` |
| Intake/parser | `docs/ARCHITECTURE.md`, ADR-0002, `tests/AGENTS.md` |
| Classification/extraction | ADR-0003, `schemas/`, `docs/EVALUATION.md` |
| Workflow/HITL | `docs/WORKFLOWS.md`, `docs/HUMAN_IN_THE_LOOP.md` |
| Camunda 7 integration | `docs/CAMUNDA_MVP_V2_INTEGRATION_PLAN.md`, ADR-0002 |
| Template-first MVP | `docs/TEMPLATE_FIRST_PHASE1_PLAN.md`, `docs/TEMPLATE_FIRST_PHASE1_REPORT.md` |
| Kiến trúc | `docs/ARCHITECTURE.md`, ADR liên quan |
| Schema | `schemas/`, `docs/DATA_SECURITY.md` |
| Test/benchmark | `docs/EVALUATION.md`, `docs/adr/0006-ocr-acc-001-dataset-split.md`, `tests/AGENTS.md` |
| Tài liệu | `docs/AGENTS.md` |
| Trạng thái và handoff | `docs/README.md`, `docs/PROJECT_STATE.md`, `docs/BACKLOG.md`, `docs/HANDOFF.md` |
| Báo cáo tiến độ mentor | `docs/MENTOR_CAMUNDA_HITL_REPORT.md`, `docs/MENTOR_4_DAY_PROGRESS_REPORT.md`, `docs/EVALUATION.md` |

Không quét toàn repository, dataset, output OCR hoặc `node_modules`.

## Hard boundaries

- Không đọc hoặc log PII thật nếu người dùng chưa chỉ định rõ file và quyền sử dụng.
- Không gửi tài liệu HCNS lên cloud/API ngoài khi chưa được phê duyệt rõ ràng.
- Không commit dataset, model weights, OCR output thật, secret hoặc file upload.
- Không tự động hóa quyết định tuyển dụng, sa thải, lương, kỷ luật hay phúc lợi.
- Mọi action ghi HRM/BPM cần policy cho phép, idempotency key và human approval.
- Không thay đổi interface trong `ports/` mà không cập nhật contract tests và ADR.
- Không đưa Camunda/Zeebe SDK vào domain/application hoặc xây workflow engine
  Python cạnh tranh với Camunda.
- Native parser trước; chỉ dùng `OcrEngine` trong parser ảnh và PDF scan.

## Token budget discipline

- Dùng `rg` để tìm mục tiêu; tối đa 5 file cho lần khảo sát đầu.
- Không dump file lớn, JSON, log hoặc full diff.
- Ưu tiên `git diff --stat`, test mục tiêu rồi mới chạy toàn bộ suite.
- Mỗi turn chỉ xử lý một outcome có thể kiểm chứng.
- Không tạo tài liệu mới nếu tài liệu hiện có có thể cập nhật.
- Cập nhật `docs/PROJECT_STATE.md` tối đa 80 dòng sau milestone.

## Definition of done

- Code có type hints và không phụ thuộc trực tiếp adapter từ domain/application.
- Test bao phủ happy path và đường chuyển sang human review.
- Không có PII/secret trong diff.
- Tài liệu hoặc ADR được cập nhật nếu hành vi public thay đổi.
- Báo cáo: file đổi, kiểm thử, rủi ro còn lại, bước kế tiếp.
