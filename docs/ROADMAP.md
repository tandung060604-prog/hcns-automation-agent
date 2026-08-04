# Roadmap

## M0 — Architecture scaffold (completed)

- Ports/adapters, OCR mock/Paddle adapter và policy HITL ban đầu.

## M1 — Universal Document Intake (completed)

- Canonical Document Model đa định dạng.
- Content-based detection, file safety và deterministic parser registry.
- Native PDF/DOCX/XLSX; OCR routing cho ảnh/PDF scan.
- PPTX text extension point.
- Durable result reference, idempotent job handler và Camunda-neutral ports.
- Synthetic contract/safety/architecture tests.

## M2 — Classification and extraction (completed)

- DocumentType classifier độc lập SourceFormat, có confidence/provenance.
- Template/parser review-first cho CV, IELTS, probation contract, leave, overtime và CCCD mặt trước.
- Required/conflict/date/sensitivity validation và quality gate.
- Business JSON 2.0.0; Camunda summary có type/quality/review flag.

## M3 — Verified understanding benchmark (in progress)

- Hoàn thành harness/schema offline và aggregate-only report.
- Hoàn thành OCR CER/WER/reading-order, classification, extraction, quality và system metric.
- Hoàn thành promotion gate và adapter từ vendor-neutral `IdpResult`.
- Còn cần Ground Truth 30–50 trang có quyền sử dụng.
- Còn cần chạy PaddleOCR baseline và MinerU challenger trên cùng dataset version.

## M4 — Camunda pilot and Human Review

- Đã chọn Camunda Platform 7.13 và scaffold External Task REST worker.
- Đã khóa process-variable whitelist/schema, safety-first DMN và shadow mode.
- Còn cần bind stage operations, deploy local và dry-run một workflow.
- Camunda User Task tiếp tục là nguồn sự thật; custom UI chưa triển khai.
- Review UI hiển thị page/block/sheet/cell provenance, không tạo queue riêng.

## M5 — Controlled integration

- Camunda M5 review-first cho đúng sáu loại; Timesheet không còn là capability.
- Bổ sung Ground Truth/cohort gates trước mọi shadow pilot; không auto-approval.
- Result/object storage production, retention, authorization và audit.
- HRM/BPM connector giả lập trước; idempotency/replay/incident tests.
- Side effect thật chỉ bật từng action sau threat model, DPIA và approval.
