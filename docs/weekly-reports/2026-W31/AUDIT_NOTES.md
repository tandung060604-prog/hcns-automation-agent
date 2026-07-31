# Audit notes - 2026-W31

## Phạm vi và phương pháp

Audit ngày 2026-07-31 trên repository local và dịch vụ loopback. Phân loại bằng chứng:

- **VERIFIED**: Git, cấu hình, tài liệu, endpoint health và giao diện local đã kiểm tra.
- **REPORTED**: trạng thái Railway chưa có cấu hình hay deployment record trong repository.
- **UNKNOWN**: kết quả CI của commit remote chưa được truy vấn từ GitHub trong audit này.

## Trạng thái repository

- `origin/main` trỏ tới `997d03187c1db01a2be46a6186dac3523761fdcb`, là checkpoint tích hợp giao diện tải tài liệu đa định dạng.
- Worktree đang mở tại nhánh `codex/m1-m2-document-understanding`, HEAD `d14965f`.
- Có một nhóm thử nghiệm CCCD chưa commit. Báo cáo không sửa, không stage và không dùng artifact từ nhóm này.
- CI khai báo Python 3.10/3.12, unittest, Ruff, mypy, repository hygiene, web test, lint và npm audit.

## Trạng thái sản phẩm local

- API loopback `127.0.0.1:8765` trả health `ok`.
- Web local `localhost:3000` đang lắng nghe.
- API liệt kê hai template-first form. UI hiển thị một điểm upload mặc định cho DOCX, PDF, PNG, JPG/JPEG cùng preview và JSON cạnh nhau.
- Không tìm thấy cấu hình Railway hoặc bằng chứng deployment production trong repository. Mọi kết luận vận hành trong report vì vậy chỉ áp dụng local-only.

## Bằng chứng và giới hạn dữ liệu

- Evidence hai biểu mẫu: DOCX 90/90 trường bắt buộc và PDF có lớp chữ 90/90. Sáu ảnh camera và sáu PDF scan có 31/54 trường bắt buộc, tương đương 57.41%, nên vẫn cần người kiểm tra.
- CCCD development có 30 session đã review. Selection trong `assets/cccd/selection.json` chỉ chứa ID băm, metadata thao tác và ranking score.
- Không đưa file nguồn, OCR text, filename gốc, Ground Truth hay ảnh CCCD chưa che vào report.
  Hình ảnh HCNS được phép hiển thị vì tập này là dữ liệu tổng hợp do AI tạo.

## Khoảng trống cần xử lý

1. Luồng ảnh/scan chưa đạt ngưỡng chính xác OCR 80% đã thống nhất.
2. Manifest multi-format khai báo 30 file nhưng chỉ chứa 26, trong đó 10 image reference stale.
3. Railway cần được thiết lập và smoke-test riêng sau khi người vận hành cung cấp cấu hình deployment.
4. Hướng cải thiện nhận dạng theo từng trường đã được phê duyệt nhưng tạm dừng trong lúc hoàn thiện báo cáo tuần.
