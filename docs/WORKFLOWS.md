# HCNS Workflows

## Ownership

Camunda BPMN là nguồn sự thật duy nhất cho onboarding, hồ sơ nhân viên, hợp
đồng, nghỉ phép, chấm công, payroll và công văn. Camunda sở hữu Service/User
Task, timer, SLA, retry, escalation, assignment, incident, compensation,
versioning và process state dài hạn.

IDP worker chỉ thực hiện một job hữu hạn:

```text
Camunda Service Task
  → documentId/reference + business/correlation/idempotency key
  → worker tải source trong storage được kiểm soát
  → safety + parse + canonicalize
  → lưu result bền vững
  → trả resultReference + small summary
  → Camunda đánh giá BPMN condition
  → Camunda tạo User Task nếu cần
```

Worker không complete trước khi result được lưu. Retry dùng cùng idempotency key
và không tạo duplicate side effect. Technical error và business error được báo
riêng; chính Camunda quyết định retry/escalation ở cấp process.

## Context nghiệp vụ

`WorkflowType` là context Camunda, không phải kết quả format detection.
`DocumentType` và `qualityStatus` có thể góp vào BPMN condition nhưng không tự
quyết định toàn bộ workflow khi thiếu case context. M2 trả type/confidence,
quality status và review flag; Camunda vẫn quyết định bước tiếp theo.

## Process variables

Chỉ giữ document/case ID, business/correlation/idempotency key, source format,
document type, parse/quality/review status, result reference, schema version và
error code. Không giữ raw file, raw OCR, canonical payload, ảnh hoặc workbook.

Milestone này không chứa BPMN production, scheduler, task assignment engine,
review queue, process persistence hoặc connector HRM thật.

## Package tham chiếu

Repository lưu hai tài sản thiết kế để review và dry-run:

- `camunda/HR_DOCUMENT_AGENT_MVP_V2.bpmn`
- `camunda/HR_DOCUMENT_QUALITY_ROUTING.dmn`

Package mô tả luồng intake, kiểm tra chất lượng, Human Review và định tuyến bằng
DMN cho Camunda Platform 7.13. Đây chưa phải bằng chứng triển khai production;
endpoint, credentials, deployment ID và liên kết tới môi trường Camunda không
được lưu trong Git. Liên kết Modeler/Operate/Tasklist sẽ được bổ sung sau khi môi
trường tích hợp được phê duyệt.
