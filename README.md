# VinHRIS — cổng tác nghiệp tài liệu HCNS

VinHRIS là MVP Document AI chạy local/self-hosted: nhận hồ sơ, phân loại, trích xuất dữ liệu có bằng chứng và đưa kết quả cho con người duyệt. Camunda 7 là thành phần điều phối tùy chọn; file gốc và dữ liệu nhạy cảm không được đưa vào process variables.

Trạng thái nhánh `feat/deploy-cloudflare` ngày 2026-08-21:

- hỗ trợ Đơn nghỉ phép, Đơn tăng ca, CV, Hợp đồng thử việc, IELTS và CCCD mặt trước;
- website có luồng `USER → HR_REVIEWER → USER`, thông báo trong ứng dụng và lịch sử xử lý;
- OCR chọn bằng `--ocr-backend auto|easyocr|paddle`; chế độ `auto` ưu tiên engine đang được cài đặt;
- Cloudflare Quick Tunnel chỉ dành cho demo ngắn hạn với dữ liệu giả hoặc dữ liệu đã được phép sử dụng.

## Khởi động nhanh

Launcher hiện hỗ trợ Linux hoặc WSL2. Cần Python 3.10+, Node.js 22.13+ và Docker nếu muốn chạy Camunda.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[api,dev,easyocr]"
npm --prefix apps/ocr_lab/web ci
mkdir -p "$HOME/private-data"

# Chỉ chạy website + API
python run_all_in_one.py --data-root "$HOME/private-data" --ocr-backend auto --no-worker
```

Mở `http://localhost:3000/workspace`. Muốn chạy cả Camunda và worker:

```bash
python run_all_in_one.py --data-root "$HOME/private-data" --ocr-backend auto --with-camunda
```

Nhấn `Ctrl+C` tại terminal chạy launcher để dừng các tiến trình do launcher tạo.

## Tài khoản demo

| Tài khoản | Mật khẩu | Vai trò | Việc chính |
|---|---|---|---|
| `user` | `user123` | `USER` | Tải/chọn mẫu, kiểm tra dữ liệu, nộp sang HR, xem kết quả |
| `hr` | `hr123` | `HR_REVIEWER` | Đối chiếu tài liệu, duyệt, yêu cầu sửa hoặc từ chối |
| `admin` | `admin123` | `ADMIN` | Quản lý tài khoản, phân công HR và xem audit log |

Đây là tài khoản cố định cho demo. Không đưa hệ thống chứa dữ liệu thật ra Internet với các mật khẩu này.

## Cách website vận hành

1. `USER` mở **Nộp đơn**, tải DOCX/PDF/ảnh hoặc chọn mẫu, kiểm tra các trường được parser/OCR trích xuất rồi nộp sang HR.
2. `HR_REVIEWER` mở **Hàng đợi HR**, đối chiếu dữ liệu với tài liệu gốc và chọn duyệt, yêu cầu sửa hoặc từ chối.
3. `USER` nhận cập nhật gần thời gian thực trong ứng dụng, sau đó xem trạng thái và bằng chứng tại phần lịch sử.
4. `ADMIN` quản lý người dùng, quan hệ phụ trách và nhật ký. Quyền xem/tải hồ sơ vẫn do API kiểm tra theo vai trò và quan hệ được gán.

Các địa chỉ local mặc định:

| Thành phần | Địa chỉ |
|---|---|
| Landing page | `http://localhost:3000` |
| Workspace | `http://localhost:3000/workspace` |
| API/health | `http://127.0.0.1:8765/health` |
| Camunda Tasklist (tùy chọn, chỉ local/private) | `http://127.0.0.1:8080/camunda` |

## Ranh giới triển khai

`python deploy_public.py` tạo URL HTTPS ngẫu nhiên cho Web và API để demo nhanh. Script không công khai Camunda. Quick Tunnel không có lớp kiểm soát truy cập phù hợp cho production, URL thay đổi sau mỗi lần chạy và không được dùng với PII thật. Demo dài hạn phải dùng named Cloudflare Tunnel kèm Cloudflare Access hoặc một hạ tầng có xác thực tương đương.

Cloudflare Workers/Pages chỉ phù hợp cho frontend tĩnh/edge; chúng không thay thế máy chạy OCR worker và Camunda.

## Tài liệu

- [Hướng dẫn sử dụng và vận hành](docs/LOCAL_OPS_AND_DEPLOY.md)
- [Trạng thái dự án](docs/PROJECT_STATE.md)
- [Báo cáo smoke test](docs/REPORT.md)
- [Kiến trúc](docs/ARCHITECTURE.md)
- [An toàn dữ liệu](docs/DATA_SECURITY.md)
- [Human-in-the-loop](docs/HUMAN_IN_THE_LOOP.md)
