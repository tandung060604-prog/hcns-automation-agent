# Documentation Map

Tài liệu được giữ ở `docs/` với tên `UPPER_SNAKE_CASE.md` để dễ tìm kiếm và giữ
liên kết ổn định. Không đổi tên tài liệu lịch sử nếu không có migration link.

## Điều hành dự án

| Tài liệu | Vai trò | Khi cập nhật |
|---|---|---|
| [PROJECT_STATE.md](PROJECT_STATE.md) | Sự thật hiện tại, milestone, rủi ro và giới hạn | Sau milestone hoặc thay đổi policy |
| [BACKLOG.md](BACKLOG.md) | Task có trạng thái, phụ thuộc và acceptance criteria | Khi bắt đầu/kết thúc task |
| [HANDOFF.md](HANDOFF.md) | Checkpoint để session/agent khác tiếp tục | Trước khi kết thúc workstream |
| [archive/PROJECT_STATE_HISTORY_2026-08-06.md](archive/PROJECT_STATE_HISTORY_2026-08-06.md) | Evidence lịch sử theo milestone | Khi rút gọn state hiện tại |
| [ROADMAP.md](ROADMAP.md) | Định hướng milestone dài hạn | Khi thay đổi ưu tiên |

## OCR và đánh giá

| Tài liệu | Vai trò |
|---|---|
| [MODEL_GUIDE.md](MODEL_GUIDE.md) | Model, crop, policy và promotion gate |
| [OCR_METHODS_AND_METRICS.md](OCR_METHODS_AND_METRICS.md) | Toàn bộ phương pháp OCR đã thử và metric theo từng phase/dataset |
| [EVALUATION.md](EVALUATION.md) | Metric, benchmark và cách đọc kết quả |
| [DATA_SECURITY.md](DATA_SECURITY.md) | PII, storage, provenance và boundary |
| [MENTOR_4_DAY_PROGRESS_REPORT.md](MENTOR_4_DAY_PROGRESS_REPORT.md) | Báo cáo tiến độ đã tổng hợp |

## Kiến trúc và workflow

| Tài liệu | Vai trò |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Boundary domain/application/adapter |
| [WORKFLOWS.md](WORKFLOWS.md) | Quy tắc orchestration và trạng thái |
| [HUMAN_IN_THE_LOOP.md](HUMAN_IN_THE_LOOP.md) | Review, correction và escalation |
| [CAMUNDA_MVP_V2_INTEGRATION_PLAN.md](CAMUNDA_MVP_V2_INTEGRATION_PLAN.md) | Kế hoạch tích hợp Camunda 7 |
| [TEMPLATE_FIRST_PHASE1_PLAN.md](TEMPLATE_FIRST_PHASE1_PLAN.md) | Quy tắc mở template mới |
| [TEMPLATE_FIRST_PHASE1_REPORT.md](TEMPLATE_FIRST_PHASE1_REPORT.md) | Bằng chứng nghiệm thu template-first |

Các quyết định kiến trúc khó đảo ngược nằm trong thư mục [`adr/`](adr/), theo quy
ước `NNNN-kebab-case.md`.

## Quy ước

- README định hướng và hướng dẫn chạy nhanh; tài liệu trong `docs/` ghi quyết
  định, vận hành và bằng chứng có thể kiểm chứng.
- Không lưu Ground Truth, OCR output thật, model weights, raw PII hoặc secret
  trong repository.
- Tài liệu mới phải được thêm vào bảng này và routing tương ứng trong root
  `AGENTS.md`.
