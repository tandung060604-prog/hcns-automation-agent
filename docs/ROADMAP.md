# Roadmap

## M0 — Scaffold

- Domain, ports, mock adapter, HITL state machine.
- Documentation, policies và repository guardrails.

## M1 — Verified benchmark

- Import pipeline Ground Truth có quyền sử dụng.
- Adapter PaddleOCR và contract tests.
- Báo cáo theo document type, không chỉ metric tổng.

## M2 — Challenger

- Adapter MinerU upstream trong environment tách biệt.
- Bake-off PaddleOCR/MinerU trên cùng dataset.
- Routing engine theo loại tài liệu nếu có bằng chứng.

## M3 — Review application

- Review queue, crop/provenance và correction history.
- Role-based access, approval expiry và audit export.

## M4 — Workflow pilot

- Onboarding và đơn nghỉ phép ở chế độ dry-run.
- Connector BPM/HRM giả lập, idempotency và replay tests.

## M5 — Controlled production

- Threat model, DPIA, retention và backup/restore.
- SLO, monitoring, incident response và rollback.
- Cho phép từng side effect theo policy, không bật hàng loạt.

