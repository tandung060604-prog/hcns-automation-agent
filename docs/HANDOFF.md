# Handoff

## Repository context

- Repository: `D:\AI Vin Thực Chiến\Side Project\PaddleOCR\hcns-automation-agent`
- Branch: `codex/m1-m2-document-understanding`
- Routing: [docs/README.md](README.md)
- Acceptance criteria: [docs/BACKLOG.md](BACKLOG.md)

## Active workstreams

### OCR-HO-V2-001 — CCCD held-out v2

- Manifest private đã khóa đủ 15 tài liệu không trùng development.
- Ingest 15/15 đã hoàn tất.
- Prediction Phase 11.5 đang chạy ẩn; Phase 11.6 sẽ chạy sau đó.
- Không mở prediction, không tính metric và không đưa PII vào Git trước khi
  Ground Truth được khóa.
- Policy hiện tại: `SHADOW_REVIEW_ONLY`.

### TF-P1-001 — Template-first MVP

- Hai template DOCX: `leave-request-v1` và `overtime-request-v1`.
- Native parsing là đường mặc định; tài liệu thiếu field hoặc mâu thuẫn đi
  `MANUAL_REVIEW`.
- WIP code/template changes phải được bảo toàn khi tiếp tục OCR workstream.

### TF-P1-002 — Checkpoint và local live smoke

- Implementation commit `53b22fb` đã push lên
  `origin/codex/m1-m2-document-understanding`; remote hash đã xác minh.
- API local đang nghe tại `http://127.0.0.1:8765` với PID quan sát tại checkpoint là
  `14312`; đây không phải production deployment.
- `/health` trả `ok`; `/api/templates` liệt kê đủ hai template.
- Hai DOCX gốc ngoài bộ regression đã trả đúng `LEAVE_REQUEST` và
  `OVERTIME_REQUEST`, cùng `AUTO_CONTINUE` và không có validation error.
- Hai session smoke-test đã xóa; không lưu raw PII trong tài liệu tracked hoặc log báo cáo.

## Verified evidence

- Repository hygiene đã pass ở checkpoint gần nhất.
- README có workflow Mermaid end-to-end và badge profile.
- Ground Truth, prediction, source và model weights vẫn ở local/private.
- Template-first full suite đạt 218 tests; Ruff, mypy, compileall và hygiene đều pass.

## Next action

1. Theo dõi `paddleocr-cccd-heldout-v2-final/predictions/hidden_predict.stdout.log`.
2. Chờ `HIDDEN_PREDICTIONS_STATUS.json` xuất hiện với
   `BLINDED_PREDICTIONS_READY`.
3. Cho người review xác nhận Ground Truth đủ 15 tài liệu.
4. Khóa Ground Truth, mở prediction và evaluate đúng một lần.

## First command after resume

```powershell
Set-Location "D:\AI Vin Thực Chiến\Side Project\PaddleOCR\hcns-automation-agent"
git status --short --branch
```
