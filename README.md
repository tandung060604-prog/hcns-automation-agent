# VinHRIS — Cổng tác nghiệp tài liệu HCNS

Document AI chạy **local / self-hosted**: tiếp nhận hồ sơ, nhận diện biểu mẫu, trích xuất có cấu trúc, HR duyệt kèm tài liệu gốc. Camunda 7 điều phối workflow; file và field chi tiết không đẩy vào engine.

**Trạng thái (2026-08-21):** MVP workspace dùng được cho Leave · OT · CV · Contract · IELTS · CCCD. OCR template mặc định trên máy này: **Paddle** (`HCNS_TEMPLATE_OCR_BACKEND=paddle` hoặc `auto`). Báo cáo smoke mới nhất: [`docs/REPORT.md`](docs/REPORT.md).

## Tài khoản demo

| User | Pass | Role |
|------|------|------|
| `admin` | `admin123` | ADMIN |
| `hr` | `hr123` | HR_REVIEWER |
| `user` | `user123` | USER |

## URL local

| Dịch vụ | URL |
|---------|-----|
| Landing | http://localhost:3000 |
| Workspace (MVP) | http://localhost:3000/workspace |
| API | http://127.0.0.1:8765 |
| Camunda Tasklist | http://localhost:8080/camunda |

## Biểu mẫu hỗ trợ

| Loại | File | Cách đọc |
|------|------|----------|
| Đơn nghỉ phép | DOCX / PDF | Native extract |
| Đơn tăng ca | DOCX / PDF | Native extract |
| CV | DOCX / PDF | Structured-hr (+ OCR nếu PDF scan) |
| Hợp đồng thử việc | DOCX / PDF | Structured-hr |
| IELTS / chứng chỉ | PDF / JPG / PNG | OCR |
| CCCD mặt trước | JPG / PNG / PDF | OCR |

Mẫu blank (trừ IELTS/CCCD): `apps/ocr_lab/web/public/templates/`.

## Chạy nhanh (Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,paddle]"   # hoặc .[easyocr] nếu dùng EasyOCR

cd apps/ocr_lab/web && npm ci && cd -

# Terminal 1 — API + web
bash scripts/start_dashboard_linux.sh "$HOME/private-data"

# Terminal 2 — Camunda worker (Camunda :8080 đã chạy + BPMN đã deploy)
export CAMUNDA_REST_URL=http://127.0.0.1:8080/engine-rest
export CAMUNDA_WORKER_ID=hcns-local-shadow
export HCNS_CAMUNDA_PRIVATE_ROOT="$HOME/private-data"
export HCNS_TEMPLATE_OCR_BACKEND=paddle
.venv/bin/hcns-agent-camunda-worker
```

Hướng dẫn đầy đủ (website, Camunda, deploy public, duy trì):  
→ **[`docs/LOCAL_OPS_AND_DEPLOY.md`](docs/LOCAL_OPS_AND_DEPLOY.md)**

## Luồng MVP

1. `user` upload DOCX/PDF/ảnh → quét → chỉnh form → nộp HR  
2. `hr` hàng đợi → xem chi tiết / tài liệu gốc → Chấp nhận / Nộp lại / Từ chối  
3. `user` nhận thông báo; lịch sử + bằng chứng sau khi chấp nhận  

DOCX không xem inline trên trình duyệt (tải file). PDF/ảnh xem preview.

## Tài liệu quan trọng

| File | Nội dung |
|------|----------|
| [`docs/REPORT.md`](docs/REPORT.md) | Smoke dataset 2026-08-21 |
| [`docs/LOCAL_OPS_AND_DEPLOY.md`](docs/LOCAL_OPS_AND_DEPLOY.md) | Vận hành & deploy |
| [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) | Trạng thái kỹ thuật |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Kiến trúc |
| [`docs/HUMAN_IN_THE_LOOP.md`](docs/HUMAN_IN_THE_LOOP.md) | HITL |

## An toàn dữ liệu

Dữ liệu demo nằm trong `HCNS` data root (mặc định `~/private-data`): sessions, submissions, archive. Không gửi file gốc sang Camunda — chỉ metadata / reference.

## License / scope

MVP nội bộ / nghiên cứu. Chưa phải production multi-tenant hay tích hợp HRIS thật.
