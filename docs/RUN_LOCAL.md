# README: Launcher `run_local.py` và thay đổi gần đây

Tài liệu này mô tả launcher chạy local bằng Python thuần (không cần
PowerShell), các lỗi đã phát hiện khi kiểm chứng và cách sử dụng.

## Launcher `run_local.py` (mới)

Script `run_local.py` ở thư mục gốc repository khởi động đồng thời hai
server trên mọi hệ điều hành (Windows/macOS/Linux), chỉ dùng Python stdlib:

| Server | Lệnh | URL |
|---|---|---|
| OCR/IDP API | `apps/ocr_lab/api/serve_dashboard_api.py` | `http://127.0.0.1:8765` |
| Dashboard UI | `npm run dev` trong `apps/ocr_lab/web` | `http://localhost:3000` |

Tính năng:

- Tự chọn interpreter: `.venv` nếu tồn tại, ngược lại dùng Python hiện tại;
  mặc định gán `PYTHONPATH=src`.
- `--setup`: tạo `.venv`, cài `pip install -e ".[dev]"`, chạy `npm ci`.
- `--full`: kèm `--setup` cài thêm `paddle,easyocr` (OCR nặng).
- Kiểm tra health trước khi báo "ready": API dùng `/health`, UI dùng `/`.
- Nếu port đã có server chạy thì bỏ qua, không khởi động trùng.
- Ctrl+C (hay SIGTERM trên POSIX) dừng sạch cả hai server con, không để lại
  process treo; nếu một server chết, launcher tự dừng server còn lại.
- `--no-ui` chỉ chạy API OCR.

### Cách dùng

```bash
python run_local.py --data-root /path/to/private-data
python run_local.py --data-root /path/to/private-data --setup
python run_local.py --data-root /path/to/private-data --full
python run_local.py --data-root /path/to/private-data --no-ui
```

Sau khi lên, mở http://localhost:3000 tải tài liệu, hoặc gọi API trực tiếp
ví dụ `curl http://127.0.0.1:8765/api/templates`.

## Lỗi đã tìm thấy và sửa khi kiểm chứng

1. **Health-check UI sai endpoint.** Launcher trước gọi `GET /health` lên
   dashboard UI; Vite trả `404` cho đường này và trả `200` tại `/`, khiến
   launcher báo "UI không healthy" mỗi lần chạy dù server hoạt động bình
   thường. Đã sửa thành kiểm tra `/`.
2. **Process treo sau khi dừng.** `timeout`/kill launcher làm server con
   (API 8765, UI 3000) bị orphan, chiếm port và khiến lần chạy sau dùng
   server cũ với `--data-root` sai. Đã thêm `install_stop_handlers()` bắt
   SIGTERM (POSIX) và kill cả process group; Windows dùng `taskkill /T /F`.
3. **Log sai định dạng prefix** trong `spawn` (`[{prefix}]` hiển thị nguyên
   văn); đã sửa thành f-string.

## Kết quả kiểm chứng trực tiếp

- `GET /health` trên API: `200`; dashboard UI tại `/`: `200`.
- `GET /api/templates`: trả đúng danh sách template active (CV, IELTS, ...),
  xác nhận parser/template service hoạt động.
- Upload thử `01_don_xin_nghi_phep_v1.docx`: trả `status=SUCCESS`,
  `templateId=leave-request-v1`, `documentType=LEAVE_REQUEST`,
  `detectionConfidence=1.0`, matched anchors đúng.
- `ruff check` và `py_compile` trên `run_local.py`: pass.
- Quy trình đầy đủ: API healthy → `npm ci` (nếu thiếu) → `vinext dev` chạy
  và có thể truy cập UI, launcher dừng được cả hai server.

## Ghi chú vận hành

- Dữ liệu private (upload, session, Ground Truth) chỉ nằm dưới `--data-root`
  do người vận hành chỉ định; API chỉ bind loopback.
- OCR model (PaddleOCR/EasyOCR) được load lần đầu khi có tài liệu scan,
  nên lần chạy đầu sau upload có thể chậm.
- Không đưa tài liệu thật, output OCR hoặc PII vào Git.