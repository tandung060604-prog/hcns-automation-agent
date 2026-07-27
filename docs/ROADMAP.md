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
- Extractor CV, hợp đồng lao động, đơn nghỉ phép và chấm công.
- Required/conflict/date/sensitivity validation và quality gate.
- Business JSON 2.0.0; Camunda summary có type/quality/review flag.

## M3 — Verified understanding benchmark (in progress)

- Hoàn thành harness/schema offline và aggregate-only report.
- Hoàn thành OCR CER/WER/reading-order, classification, extraction, quality và system metric.
- Hoàn thành promotion gate và adapter từ vendor-neutral `IdpResult`.
- Còn cần Ground Truth 30–50 trang có quyền sử dụng.
- Còn cần chạy PaddleOCR baseline và MinerU challenger trên cùng dataset version.

## M4 — Camunda pilot and Human Review

- Chọn Camunda 7/8 ở infrastructure, triển khai SDK-specific job worker.
- BPMN dry-run cho một workflow; Camunda User Task là nguồn sự thật.
- Review UI hiển thị page/block/sheet/cell provenance, không tạo queue riêng.

## M5 — Controlled integration

- Result/object storage production, retention, authorization và audit.
- HRM/BPM connector giả lập trước; idempotency/replay/incident tests.
- Side effect thật chỉ bật từng action sau threat model, DPIA và approval.
