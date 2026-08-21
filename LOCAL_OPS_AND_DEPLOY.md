# Hướng dẫn website, chạy local, Camunda và duy trì hệ thống

Tài liệu vận hành MVP VinHRIS trên máy local (và tùy chọn tunnel Cloudflare).  
Cập nhật: **2026-08-21**.

---

## 1. Website gồm những gì?

| Đường dẫn | Mục đích |
|-----------|----------|
| `/` | Landing VinHRIS (marketing / giới thiệu) |
| `/workspace` | **Khu vực làm việc MVP** — đăng nhập, nộp đơn, hàng đợi HR, thông báo, lịch sử, bằng chứng |

Workspace là bề mặt chính. Sau đăng nhập chỉ hiện panel tác nghiệp (diagnostic nâng cao tắt mặc định).

### Vai trò

- **USER:** quét tài liệu → sửa field → nộp HR → xem thông báo / lịch sử  
- **HR_REVIEWER:** hàng đợi → xem gốc → chấp nhận / yêu cầu nộp lại / từ chối  
- **ADMIN:** quản trị tài khoản / gán HR↔user / audit (tab Admin)

### Luồng nghiệp vụ (một câu)

Upload → nhận diện template → extract → nộp (archive file gốc) → HR duyệt → notification + lịch sử.

---

## 2. Thành phần hệ thống

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Web :3000   │────▶│ API :8765        │────▶│ ~/private-data  │
│ vinext/Next │     │ serve_dashboard  │     │ sessions/archive│
└─────────────┘     └────────┬─────────┘     └─────────────────┘
                             │
                    ┌────────▼─────────┐
                    │ Camunda :8080    │
                    │ + external worker│
                    └──────────────────┘
```

| Process | Lệnh / cổng | Ghi chú |
|---------|-------------|---------|
| API | `apps/ocr_lab/api/serve_dashboard_api.py` · **8765** | OCR + RBAC + archive |
| Web | `apps/ocr_lab/web` · `npm run dev` · **3000** | UI |
| Camunda | Run distribution · **8080** | BPMN HCNS |
| Worker | `hcns-agent-camunda-worker` | Parse / external tasks |

**Bắt buộc cùng data root:** API `--data-root` = `HCNS_CAMUNDA_PRIVATE_ROOT` của worker.

---

## 3. Cài đặt lần đầu (Linux)

```bash
cd /path/to/hcns-automation-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,paddle]"
# Nếu muốn EasyOCR: pip install -e ".[dev,easyocr]"

cd apps/ocr_lab/web
npm ci
cd -
mkdir -p ~/private-data tmp
```

### Camunda 7.13

1. Chạy Camunda Run (không bắt buộc login trên bản demo thường dùng).  
2. Deploy BPMN/DMN trong thư mục `camunda/` (xem `docs/CAMUNDA_*` nếu cần chi tiết version).  
3. Tasklist: http://localhost:8080/camunda  

Không có Camunda: API vẫn cho **nộp local** (`LOCAL-…` / pending HR) — đủ demo MVP; worker không bắt buộc cho duyệt local.

---

## 4. Khởi động hàng ngày

### Cách A — script gọn (API + web)

```bash
source .venv/bin/activate
bash scripts/start_dashboard_linux.sh "$HOME/private-data"
```

Mở: http://localhost:3000/workspace  

### Cách B — thủ công

```bash
# API
export HCNS_TEMPLATE_OCR_BACKEND=paddle   # hoặc auto / easyocr
.venv/bin/python -u apps/ocr_lab/api/serve_dashboard_api.py \
  --data-root "$HOME/private-data" --host 127.0.0.1 --port 8765

# Web (terminal khác)
cd apps/ocr_lab/web && npm run dev

# Worker (terminal khác, khi Camunda sẵn sàng)
export CAMUNDA_REST_URL=http://127.0.0.1:8080/engine-rest
export CAMUNDA_WORKER_ID=hcns-local-shadow
export HCNS_CAMUNDA_PRIVATE_ROOT="$HOME/private-data"
export HCNS_TEMPLATE_OCR_BACKEND=paddle
.venv/bin/hcns-agent-camunda-worker
```

### Kiểm tra nhanh

```bash
curl -sf http://127.0.0.1:8765/health | python3 -m json.tool | head
curl -sf -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/workspace
```

Trong `/health` xem `userUpload.templateOcrBackend` và `backendAvailable: true`.

---

## 5. Deploy public (Cloudflare quick tunnel)

Không cần account Cloudflare; URL `*.trycloudflare.com` đổi mỗi lần chạy.

```bash
source .venv/bin/activate
python deploy_public.py --data-root "$HOME/private-data" --ocr-backend auto
# hoặc ép paddle: --ocr-backend paddle
```

Script khởi động API + web (+ worker trừ khi `--no-worker`), warmup OCR, in URL công khai.  
**Ctrl+C** tắt toàn stack tunnel.

Yêu cầu: Docker (cloudflared image), Node, venv đã cài OCR backend.

---

## 6. Biến môi trường hay dùng

| Biến | Ý nghĩa |
|------|---------|
| `HCNS_TEMPLATE_OCR_BACKEND` | `paddle` · `easyocr` · `auto` |
| `HCNS_TEMPLATE_OCR_WARMUP` | `1` = load model lúc API start |
| `HCNS_CAMUNDA_PRIVATE_ROOT` | Data root (trùng `--data-root`) |
| `CAMUNDA_REST_URL` | Mặc định `http://127.0.0.1:8080/engine-rest` |
| `HCNS_API_CORS_ORIGINS` | CORS khi tunnel (deploy_public set sẵn) |
| `HCNS_API_ALLOWED_HOSTS` | Host header tunnel |

---

## 7. Duy trì hệ thống

### Logs

- API: `tmp/api.log`  
- Web: `tmp/web.log`  
- Deploy public: `tmp/` (theo tên process)

### Data

- Root: `~/private-data` (hoặc path bạn chọn)  
- Sessions upload: `user_uploads/sessions/`  
- MVP archive / submissions: dưới `mvp_demo/` (ownership, archive files, …)

**Backup:** copy cả data root.  
**Reset demo:** dừng API → xóa/đổi tên data root → tạo thư mục trống → start lại.

### OCR

- Đổi backend → **restart API và worker** cùng giá trị.  
- Worker lệch backend (EasyOCR khi API Paddle) → Parse Camunda dễ fail.  
- Lần đầu paddle tải model về `~/.paddlex/`.

### Khi “hỏng” thường gặp

| Hiện tượng | Việc kiểm |
|------------|-----------|
| `backendAvailable: false` | Cài paddle/easyocr; set `HCNS_TEMPLATE_OCR_BACKEND` đúng |
| Nộp xong HR không thấy / Parse fail | Worker chạy? Cùng data root & OCR backend? |
| Xem gốc DOCX trống | Đúng hành vi — dùng **Tải file gốc** |
| IELTS PNG nhận nhầm CCCD | Biết issue — ưu tiên JPG hoặc xem `docs/REPORT.md` |
| Font / UI lệch | Hard refresh; Be Vietnam Pro trong `layout.tsx` |

### Cập nhật code

```bash
git pull
source .venv/bin/activate
pip install -e ".[dev,paddle]"
cd apps/ocr_lab/web && npm ci && cd -
# restart API, web, worker
```

---

## 8. Smoke test thủ công (UI)

1. Login `user` → Nộp đơn → upload 1 file dataset → Quét → Nộp HR.  
2. Login `hr` → Hàng đợi → Xem chi tiết → Xem tài liệu gốc → Chấp nhận.  
3. Login `user` → Thông báo + Lịch sử.

Dataset gợi ý: `../vinhris-document-ai-dataset-main/data/` (Leave/OT/CV/Contract/IELTS/CCCD).  
Kết quả máy: [`REPORT.md`](REPORT.md).

---

## 9. Checklist vận hành

- [ ] venv + deps OCR  
- [ ] `~/private-data` tồn tại  
- [ ] API health OK, OCR loaded  
- [ ] Web `/workspace` 200  
- [ ] (Tuỳ chọn) Camunda :8080 + worker  
- [ ] Demo login 3 role  
- [ ] Một vòng nộp + duyệt thành công  

---

## 10. Liên kết thêm

- Kiến trúc: `ARCHITECTURE.md`  
- HITL / Camunda sâu: `HUMAN_IN_THE_LOOP.md`, `CAMUNDA_M5_SHADOW_PILOT_RUNBOOK.md`  
- Bảo mật dữ liệu: `DATA_SECURITY.md`
