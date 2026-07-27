# Domain agent instructions

- Domain không import framework, adapter, filesystem, HTTP hoặc model SDK.
- Domain không sở hữu BPMN transition, User Task, timer, retry, escalation hoặc
  process state dài hạn; các trách nhiệm đó thuộc Camunda.
- Giá trị trích xuất luôn giữ confidence, status và provenance.
- Trường nhạy cảm không được auto-approve.
- `SourceFormat`, `DocumentType` và `WorkflowType` phải độc lập.
- Canonical model chỉ chứa kiểu Python chuẩn, không chứa object vendor.
- Giữ model nhỏ, immutable khi phù hợp; không đưa raw image bytes vào audit event.
