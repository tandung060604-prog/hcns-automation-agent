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

### TF-P1-003 — OCR Lab Template-first UI

- Giao diện tổng chạy tại `http://localhost:3000`; API root `127.0.0.1:8765` redirect về đó.
- Chế độ mặc định “Mẫu chuẩn” gọi `/api/documents/process`, nhận DOCX và hiển thị field,
  missing fields, validation, confidence, recommended action cùng JSON đầy đủ.
- Luồng `/user/upload` cũ vẫn có trong chế độ “OCR / IDP cũ”.
- Browser smoke đơn nghỉ phép trả `SUCCESS` / `AUTO_CONTINUE`, 19 field cards,
  confidence và anchor match 100%; kết quả local được giữ mở cho người dùng.
- PID quan sát tại checkpoint: API `27752`, web `28852`; cả hai chỉ bind local.
- `tsc --noEmit` vẫn có lỗi baseline ở Phase 14/worker; build chính thức và lint không có error.

### TF-P1-004 — README cho các mẫu HCNS chuẩn

- README đưa Template-first Phase 1 và hai mẫu nghỉ phép/tăng ca lên thành luồng MVP mặc định.
- Làm rõ bộ regression gồm 14 hồ sơ synthetic thuộc 2 loại biểu mẫu, không phải 14 loại đơn.
- Thêm hướng dẫn thử DOCX mới trên `localhost:3000` và dẫn tới báo cáo metric chi tiết.
- Không xóa tài liệu cũ; Universal Intake, OCR/CCCD, generic IDP và Camunda vẫn được giữ.
- Lần chạy API test đầu thiếu `PYTHONPATH=src` nên lỗi collection; chạy lại đúng môi trường
  đạt 4/4. Repository hygiene và `git diff --check` đều pass.

### TF-P1-005 — Mentor-safe localhost

- Held-out nav, metrics, proof strip, evidence tab và private authorization note bị ẩn mặc định.
- Held-out summary/evidence không được fetch trong mentor view.
- Đặt `VITE_SHOW_HELDOUT=true` trước khi chạy web để bật lại chế độ quan sát riêng.
- Default build và private build đều pass; web 9/9 tests, lint 0 error/19 warning cũ.
- Browser smoke xác nhận không còn “REAL HELD-OUT · EVALUATE ONCE”, nav hoặc tab held-out.
- Một lần chạy hai build song song gặp `EBUSY` ở `dist`; chạy tuần tự sau đó đều pass.

### TF-P1-006 — Template-first evidence và CCCD

- API có `GET /api/documents/sessions` và `GET /api/documents/result?id=...`, chỉ đọc
  `template_first/result.json` của `LEAVE_REQUEST` và `OVERTIME_REQUEST`.
- Evidence ẩn danh sách upload HCNS generic cũ nhưng không xóa session hoặc chức năng legacy.
- Tab Template-first hiển thị danh sách, metadata DOCX native và field/JSON ở panel bên phải.
- Tab CCCD và panel Schema/JSON cũ được giữ nguyên.
- Browser smoke mặc định thấy một Template-first session và 30 CCCD, không thấy held-out/generic.
- API restart bằng `.venv`, PID quan sát tại checkpoint là `31572`; health trả `ok`.
- Lần start bằng Python hệ thống thiếu `cv2`; không thay đổi dữ liệu và đã sửa bằng `.venv`.

### TF-P1-007 — Product showcase không PII

- Khối hero bên phải thay ảnh tài liệu bằng showcase hai biểu mẫu nghỉ phép và tăng ca.
- Showcase thể hiện luồng DOCX → Template → JSON, native parsing, validation và quality routing.
- Không dùng ảnh tài liệu thật hoặc PII trong hero; kiểm tra trực quan localhost đã pass.
- Web build/tests 9/9, API tests 4/4, lint 0 error và 15 warning có sẵn.

### TF-P1-008 — Landing page HCNS

- Hero được tái cấu trúc theo landing tham chiếu, giữ CTA và navigation hiện có.
- Phần dashboard minh họa lấy số template, session Template-first và CCCD đã review từ trạng thái runtime.
- Không thêm taskbar, user menu, số liệu giả hoặc PII.

### TF-P2-002 — Multi-format hai biểu mẫu

- Đang là task Template-first duy nhất `IN_PROGRESS`; chưa mở TF-P2-003.
- DOCX và PDF native đi parser riêng, không gọi OCR; ảnh/PDF scan dùng PaddleOCR local.
- API/UI nhận năm extension và giữ panel metadata/JSON, bổ sung source/parser/OCR metadata.
- Mặc định chỉ còn một vùng upload cho DOCX/PDF/PNG/JPG/JPEG; ảnh/PDF được xem
  cạnh kết quả field/JSON. Luồng OCR/IDP cũ không bị xóa và có thể bật riêng bằng
  `VITE_SHOW_LEGACY_UPLOAD=true`.
- File nguồn Template-first nằm trong session private và được phục vụ lại qua
  `/api/documents/source` trên loopback.
- DOCX và PDF native đều đạt 10/10 classification, 90/90 required fields, 0 schema error.
- Sáu ảnh camera và sáu PDF scan đều xử lý/phân loại 6/6, schema sạch và bắt buộc review.
- OCR exact match đạt 31/54 (57.41%), thấp hơn gate 80%; sai số còn lại ở tên, chức vụ,
  phòng ban, lý do và nội dung công việc tiếng Việt.
- Không dùng Ground Truth để phục hồi dấu; phép thử VietOCR full-page không được đưa vào code
  vì làm metric giảm.
- Dataset local có 26 file thực so với 30 file khai báo và 10 tham chiếu image cũ bị stale.
- Báo cáo evaluator aggregate không chứa raw field value; raw probe tạm đã xóa.
- API preview 6 tests và web 9 tests/build pass; full checkpoint trước đó giữ
  Python 225 tests, Ruff, mypy, hygiene và diff check pass.
- API PID `36764`, web PID `28852`; health `ok`, OCR model đã load sau smoke.
- Live HTTP smoke ảnh camera trả đúng `LEAVE_REQUEST` / `MANUAL_REVIEW`; session đã xóa.
- UX smoke desktop xác nhận preview ảnh sticky nằm cạnh panel metadata/JSON; source
  PDF/PNG tải lại khớp SHA-256 và mọi session smoke đã xóa.

## Verified evidence

- Repository hygiene đã pass ở checkpoint gần nhất.
- README có workflow Mermaid end-to-end và badge profile.
- Ground Truth, prediction, source và model weights vẫn ở local/private.
- Template-first full suite đạt 219 tests; Ruff, mypy, compileall và hygiene đều pass.
- OCR Lab build và 8 web tests pass; lint giữ nguyên 19 warning có sẵn, không có error.

## Next action

1. Giữ TF-P2-002 ở `IN_PROGRESS` vì OCR exact match còn dưới 80%.
2. Trình người dùng bằng chứng và xin duyệt hướng cải thiện recognizer riêng.
3. Chỉ mở TF-P2-003 sau khi TF-P2-002 đạt gate hoặc acceptance được phê duyệt lại.

## First command after resume

```powershell
Set-Location "D:\AI Vin Thực Chiến\Side Project\PaddleOCR\hcns-automation-agent"
git status --short --branch
```
