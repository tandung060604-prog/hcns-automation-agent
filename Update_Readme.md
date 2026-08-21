# Update Readme — Nhánh `feat/deploy-cloudflare`

Tóm tắt thay đổi so với `main`. Chi tiết vận hành cũ giữ nguyên trong `README.md`, `Plan.md` và `docs/`.

## 1. Mới: `deploy_public.py` — Deploy công khai qua Cloudflare Tunnel

- Expose toàn stack ra internet bằng **quick tunnel miễn phí của Cloudflare** (không cần tài khoản, không mở port, HTTPS tự động).
- Tự chạy 3 tunnel: **API (8765)**, **Web dashboard (3000)**, **Camunda (8080)**; mỗi service một URL `https://<ngẫu nhiên>.trycloudflare.com`.
- Tự khởi động API + web + Camunda worker, chờ health-check rồi in URL cho người dùng.
- Chạy: `python deploy_public.py`. URL đổi mỗi lần chạy (bản chất quick tunnel); muốn URL cố định phải dùng Cloudflare named tunnel (cần tài khoản + domain).
- Đã sửa lỗi trong quá trình deploy: process/phần dư chiếm port, container tunnel bị conflict tên, CORS trả sai origin khiến trình duyệt chặn login.

## 2. Mới: `run_all_in_one.py` — Chạy local một lệnh

- Khởi động toàn bộ stack local bằng 1 file: API (kèm OCR), web dashboard, Camunda worker.
- `--with-camunda` tự bật Camunda engine qua Docker nếu chưa chạy.
- Chạy: `python run_all_in_one.py --data-root "$HOME/private-data"`; tắt bằng `Ctrl+C`.

## 3. Frontend (`apps/ocr_lab/web/app/*.tsx` — 9 file)

- `API_BASE` không còn hard-code, đọc từ biến môi trường:
  `const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";`
- Thêm `VITE_CAMUNDA_URL` (mặc định `http://127.0.0.1:8080`) cho link/health-check Camunda trong `MvpDemoPanel.tsx` và `Dashboard.tsx` (thay hard-code `127.0.0.1:8080`).
- MVP panel giờ nộp đơn theo một luồng thống nhất: user upload DOCX/PDF/ảnh, Template-first tự nhận diện loại tài liệu, dữ liệu trích xuất được điền thẳng vào form để user sửa rồi nộp sang HR.
- HR nhận notification realtime khi có đơn mới; khi HR duyệt/yêu cầu tải lại/từ chối thì user nhận notification realtime qua SSE, có polling fallback.

## 4. API security (`apps/ocr_lab/api/local_server_security.py`)

- `require_local_host_header` giờ hỗ trợ **allowlist qua env**:
  `HCNS_API_ALLOWED_HOSTS` — danh sách host được phép, hỗ trợ wildcard `*.trycloudflare.com`.
- Mặc định (không đặt env) vẫn **chỉ cho phép loopback** — hành vi cũ giữ nguyên.

## 5. API CORS (`apps/ocr_lab/api/serve_dashboard_api.py`)

- `cors_headers` giờ nhận danh sách origin qua env: `HCNS_API_CORS_ORIGINS`, hỗ trợ wildcard `https://*.trycloudflare.com`.
- Sửa logic wildcard: pattern chứa `*` được so prefix + suffix đúng cách; origin hợp lệ được echo lại đúng, preflight OPTIONS trả `Access-Control-Allow-Origin` chính xác.
- Mặc định (không đặt env) vẫn chỉ `localhost:3000/4173` — hành vi cũ giữ nguyên.

## 6. Web dev server (`apps/ocr_lab/web/vite.config.ts`)

- Thêm `server.allowedHosts: [".trycloudflare.com", "localhost", "127.0.0.1"]` — tránh Vite trả 403 khi truy cập qua tên miền tunnel.

## 7. Lưu ý vận hành

| Việc | Lệnh |
|---|---|
| Deploy public | `docker start camunda` rồi `python deploy_public.py` |
| Chạy local | `python run_all_in_one.py` |
| Tắt deploy | `Ctrl+C` hoặc `pkill -f deploy_public.py` + `docker rm -f $(docker ps -aq -f name=hcns-tunnel)` |
| Tắt Camunda | `docker stop camunda` |