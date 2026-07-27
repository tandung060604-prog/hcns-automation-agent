# ADR-0002: Universal Document Intake and Camunda boundary

Status: Accepted

## Context

Scaffold ban đầu gọi `OcrEngine` trực tiếp cho mọi tài liệu và đặt một transition
graph dài hạn trong `domain/workflow.py`. Cách này không hỗ trợ native DOCX/XLSX,
không có safety gate hay canonical model đa định dạng, đồng thời trùng trách
nhiệm BPMN/User Task/process state của Camunda.

## Decision

1. Tách `SourceFormat`, `DocumentType` và `WorkflowType`; không dùng một
   classifier/router chung.
2. Thêm `FormatDetector`, `FileSafetyValidator` và registry deterministic trước
   mọi parser.
3. Application chỉ gọi vendor-neutral `DocumentParser`. Ảnh và PDF scan dùng
   `OcrEngine`; PDF text, DOCX và XLSX dùng native parser.
4. Mọi adapter chuẩn hóa về `CanonicalDocument` với source location,
   confidence, warning, parser/model provenance và schema version.
5. Result lớn được lưu qua `ResultStore`; Camunda nhận `ResultReference` cùng
   summary nhỏ, business/correlation/idempotency metadata.
6. Loại bỏ `WorkflowCase`, `WorkflowState` và transition graph dài hạn khỏi
   domain. Camunda là nguồn sự thật duy nhất cho process state, retry, timer,
   SLA, escalation và User Task.
7. Không chọn Camunda 7 hay 8 trong domain/application. SDK tương lai chỉ nằm
   trong infrastructure adapter.

## Consequences

- Parser mới, gồm PPTX, đăng ký qua cùng port mà không sửa use case.
- Unit/contract test dùng synthetic bytes, fake OCR/rasterizer/store/orchestrator;
  không cần model, network hay Camunda server.
- Intake phải lưu result trước khi báo complete và phải tái sử dụng result theo
  idempotency key.
- Canonical model không chứa object vendor; tính năng vendor-specific chỉ được
  chuyển thành primitive metadata có kiểm soát.
- Breaking migration: code dùng `WorkflowCase.transition(...)` phải chuyển sang
  BPMN của Camunda. Code gọi OCR trực tiếp bằng `HrDocument.path` phải chuyển
  sang `DocumentSource` hoặc Universal Document Intake.

## Rejected alternatives

- OCR mọi định dạng: mất cấu trúc native, công thức và provenance.
- Đặt branch theo vendor trong router: làm application phụ thuộc adapter.
- Giữ Python workflow state machine song song Camunda: tạo hai nguồn sự thật và
  hành vi retry/escalation không nhất quán.
- Lưu raw file/canonical payload trong process variables: tăng rủi ro PII và
  vượt giới hạn vận hành.
