# Hướng dẫn sử dụng và vận hành VinHRIS

Tài liệu này áp dụng cho MVP trên nhánh `feat/deploy-cloudflare`: chạy local, dùng website, nối Camunda và mở demo ngắn hạn qua Cloudflare Quick Tunnel.

## 1. Mô hình vận hành

```text
Trình duyệt :3000 → Local API :8765 → private data root
                              ↘ Camunda :8080 ← external worker
```

- Web hiển thị landing page và `/workspace`.
- API xử lý đăng nhập demo, RBAC, upload, parser/OCR, hàng đợi HR, thông báo và archive.
- API lưu session dưới `<data-root>/user_uploads/sessions` và dữ liệu nghiệp vụ dưới `<data-root>/mvp_demo`.
- Camunda và worker là tùy chọn. Worker phải dùng cùng data root với API.
- Camunda chỉ nhận reference/metadata cần cho workflow; không nhận file gốc hoặc nội dung PII.

## 2. Yêu cầu và cài đặt

Launcher dùng các tiện ích Linux, vì vậy hãy chạy trên Linux hoặc WSL2.

| Thành phần | Yêu cầu |
|---|---|
| Python | 3.10+ |
| Node.js | 22.13+ và npm |
| Docker | Chỉ bắt buộc khi launcher tự chạy Camunda hoặc Cloudflare Tunnel |
| RAM | Tùy OCR backend; lần tải model đầu tiên có thể chậm |

```bash
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[api,dev,easyocr]"
npm --prefix apps/ocr_lab/web ci
mkdir -p "$HOME/private-data"
```

Đổi `easyocr` thành `paddle` nếu muốn cài PaddleOCR. Không cần cài cả hai nếu chỉ dùng một engine.

## 3. Khởi động local

### Website và API, không Camunda

```bash
python run_all_in_one.py \
  --data-root "$HOME/private-data" \
  --ocr-backend auto \
  --no-worker
```

Mở `http://localhost:3000/workspace`.

### Website, API, Camunda và worker

Docker phải hoạt động trước khi chạy:

```bash
python run_all_in_one.py \
  --data-root "$HOME/private-data" \
  --ocr-backend auto \
  --with-camunda
```

Launcher chỉ tạo Camunda container khi cổng 8080 chưa có engine. Nếu Camunda đã chạy, worker sẽ nối vào `http://127.0.0.1:8080/engine-rest`.

### Shell launcher tối giản

```bash
bash scripts/start_dashboard_linux.sh "$HOME/private-data"
```

Script này chạy Web + API và hiện ghim OCR về PaddleOCR; nó không khởi động Camunda hoặc external worker.

### Chạy từng thành phần

API:

```bash
export HCNS_TEMPLATE_OCR_BACKEND=easyocr
.venv/bin/python -u apps/ocr_lab/api/serve_dashboard_api.py \
  --data-root "$HOME/private-data" --host 127.0.0.1 --port 8765
```

Web, ở terminal khác:

```bash
VITE_API_BASE=http://127.0.0.1:8765 npm --prefix apps/ocr_lab/web run dev
```

Worker, chỉ khi Camunda đang chạy:

```bash
export CAMUNDA_REST_URL=http://127.0.0.1:8080/engine-rest
export CAMUNDA_WORKER_ID=hcns-local-shadow
export HCNS_CAMUNDA_PRIVATE_ROOT="$HOME/private-data"
.venv/bin/python -m hcns_agent.camunda_worker_cli
```

## 4. Hướng dẫn sử dụng website

### USER nộp hồ sơ

1. Đăng nhập `user` / `user123`.
2. Mở **Nộp đơn**, chọn mẫu hoặc tải DOCX, PDF, JPG hay PNG thuộc loại được hỗ trợ.
3. Chạy phân tích, kiểm tra loại tài liệu và từng trường được trích xuất.
4. Sửa dữ liệu nếu cần rồi nộp sang HR. Không coi kết quả OCR là quyết định cuối cùng.

### HR thẩm định

1. Đăng nhập `hr` / `hr123`.
2. Mở **Hàng đợi HR** và chọn hồ sơ được phân công.
3. Đối chiếu trường dữ liệu với preview tài liệu gốc hoặc tải DOCX để xem bằng ứng dụng phù hợp.
4. Chọn **Duyệt**, **Yêu cầu sửa/nộp lại** hoặc **Từ chối**, kèm lý do khi giao diện yêu cầu.

### USER xem kết quả

1. Mở thông báo trong ứng dụng; cập nhật dùng SSE và có polling dự phòng nên có thể trễ vài giây.
2. Mở phần lịch sử/bằng chứng để xem trạng thái và tài liệu mà tài khoản được phép truy cập.

### ADMIN quản trị

Đăng nhập `admin` / `admin123` để quản lý tài khoản, gán HR phụ trách và xem audit log. API vẫn là nơi quyết định quyền truy cập; không dựa vào việc ẩn/hiện nút trên giao diện.

## 5. Demo qua Cloudflare Quick Tunnel

Quick Tunnel chỉ dành cho buổi demo có người kiểm soát, với dữ liệu tổng hợp hoặc dữ liệu đã được phê duyệt:

```bash
python deploy_public.py \
  --data-root "$HOME/private-data" \
  --ocr-backend auto \
  --no-worker
```

Script sẽ:

1. mở một tunnel cho API và cấu hình Host/CORS cho `*.trycloudflare.com`;
2. chạy API, warm-up OCR và chạy Web với URL API vừa tạo;
3. mở một tunnel cho Web rồi in URL `/workspace`;
4. đóng các tiến trình/tunnel do nó tạo khi nhận `Ctrl+C`.

Camunda engine và Tasklist không được đưa qua Quick Tunnel. Nếu Camunda chạy local, worker vẫn có thể nối vào engine nội bộ; người dùng ngoài mạng không được mở Tasklist.

Không dùng Quick Tunnel cho production hoặc PII thật vì tài khoản demo có mật khẩu cố định, URL không ổn định và không có lớp Access allowlist. Demo dài hạn cần named Cloudflare Tunnel + Cloudflare Access hoặc cơ chế xác thực tương đương. Cloudflare Pages/Workers không chạy thay OCR worker hay Camunda.

## 6. Kiểm tra sau khi khởi động

```bash
curl -fsS http://127.0.0.1:8765/health | python3 -m json.tool
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/workspace
```

Kỳ vọng API trả trạng thái tốt, OCR backend đúng với cấu hình và Web trả HTTP `200`. Khi chạy tunnel, kiểm tra lại cùng các URL được script in ra bằng một file demo không chứa PII.

## 7. Dữ liệu, sao lưu và khởi động lại

- Luôn truyền một data root tuyệt đối và riêng cho môi trường demo.
- `--data-root` của API và `HCNS_CAMUNDA_PRIVATE_ROOT` của worker phải trỏ cùng thư mục.
- Dừng launcher bằng `Ctrl+C` trước khi sao lưu.
- Để làm mới demo, không xóa trực tiếp. Hãy xác nhận đường dẫn cụ thể rồi đổi tên hoặc di chuyển riêng thư mục data root sang một thư mục backup có ngày giờ; sau đó khởi động lại với một data root rỗng mới.
- Log runtime nằm trong `tmp/`. Không commit log, upload hoặc archive vào Git.

Launcher chỉ dừng các tiến trình/container do chính phiên chạy đó tạo. Camunda đã tồn tại trước launcher có thể cần được dừng riêng bởi người vận hành.

## 8. Biến môi trường chính

| Biến | Công dụng |
|---|---|
| `HCNS_TEMPLATE_OCR_BACKEND` | `easyocr` hoặc `paddle`; launcher xử lý lựa chọn `auto` |
| `HCNS_TEMPLATE_OCR_WARMUP` | Bật/tắt tải model trước khi nhận upload |
| `HCNS_CAMUNDA_PRIVATE_ROOT` | Data root của worker, phải khớp API |
| `CAMUNDA_REST_URL` | REST endpoint private của Camunda |
| `CAMUNDA_WORKER_ID` | Định danh external worker |
| `VITE_API_BASE` | URL API được Web gọi |
| `VITE_CAMUNDA_URL` | Link Tasklist cho vận hành local; không đặt thành URL Quick Tunnel |
| `HCNS_API_ALLOWED_HOSTS` | Host headers API chấp nhận; `deploy_public.py` tự cấu hình cho Quick Tunnel |
| `HCNS_API_CORS_ORIGINS` | Origins được gọi API; `deploy_public.py` tự cấu hình cho Quick Tunnel |

## 9. Xử lý sự cố

| Hiện tượng | Kiểm tra |
|---|---|
| `/health` báo OCR chưa sẵn sàng | Xác nhận extra `easyocr`/`paddle` đã cài và backend đã chọn đúng; xem `tmp/api.log` |
| Web không gọi được API | Dừng launcher cũ và chạy lại để tạo đúng `VITE_API_BASE`; xem `tmp/web.log` |
| Quick Tunnel báo Error 1033 | Xem `tmp/tunnel_api.log` và `tmp/tunnel_web.log`; kiểm tra Docker và kết nối mạng |
| HR không thấy hồ sơ | Kiểm tra quan hệ HR–USER, trạng thái hồ sơ và data root của API/worker |
| Worker không nhận task | Kiểm tra Camunda ở cổng 8080, `CAMUNDA_REST_URL` và `tmp/worker.log` |
| DOCX không preview trong trình duyệt | Tải file và mở bằng Word/LibreOffice; đây không phải định dạng preview trực tiếp |
| Cổng 3000/8765 đã được dùng | Dừng phiên launcher cũ hoặc tiến trình đang giữ cổng rồi chạy lại |

## 10. Tài liệu liên quan

- [Trạng thái dự án](PROJECT_STATE.md)
- [Kiến trúc](ARCHITECTURE.md)
- [An toàn dữ liệu](DATA_SECURITY.md)
- [Human-in-the-loop](HUMAN_IN_THE_LOOP.md)
- [Camunda shadow pilot runbook](CAMUNDA_M5_SHADOW_PILOT_RUNBOOK.md)
- [Báo cáo smoke test](REPORT.md)
