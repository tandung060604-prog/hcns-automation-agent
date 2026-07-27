# Domain agent instructions

- Domain không import framework, adapter, filesystem, HTTP hoặc model SDK.
- Transition phải explicit; không sửa state trực tiếp từ application/adapters.
- Giá trị trích xuất luôn giữ confidence, status và provenance.
- Trường nhạy cảm không được auto-approve.
- Khi thêm state/transition: cập nhật `docs/WORKFLOWS.md` và unit tests.
- Giữ model nhỏ, immutable khi phù hợp; không đưa raw image bytes vào audit event.

