# Audit notes - 2026-W31

## Phạm vi và phương pháp

Audit ngày 2026-07-31 trên repository local và dịch vụ loopback. Phân loại bằng chứng:

- **VERIFIED**: Git, cấu hình, tài liệu, endpoint health và giao diện local đã kiểm tra.
- **REPORTED**: trạng thái Railway chưa có cấu hình hay deployment record trong repository.
- **UNKNOWN**: kết quả CI của commit remote chưa được truy vấn từ GitHub trong audit này.

## Trạng thái repository

- `origin/main` trỏ tới `997d03187c1db01a2be46a6186dac3523761fdcb`, thông điệp merge TF-P2-002 UX và multi-format intake.
- Worktree đang mở tại nhánh `codex/m1-m2-document-understanding`, HEAD `d14965f`.
- Có một nhóm WIP Phase 11.6 CCCD chưa commit. Báo cáo không sửa, không stage và không dùng artifact từ nhóm này.
- CI khai báo Python 3.10/3.12, unittest, Ruff, mypy, repository hygiene, web test, lint và npm audit.

## Trạng thái sản phẩm local

- API loopback `127.0.0.1:8765` trả health `ok`.
- Web local `localhost:3000` đang lắng nghe.
- API liệt kê hai template-first form. UI hiển thị một điểm upload mặc định cho DOCX, PDF, PNG, JPG/JPEG cùng preview và JSON cạnh nhau.
- Không tìm thấy cấu hình Railway hoặc bằng chứng deployment production trong repository. Mọi kết luận vận hành trong report vì vậy chỉ áp dụng local-only.

## Bằng chứng và giới hạn dữ liệu

- Evidence Template-first: DOCX 90/90 field required và native PDF 90/90. Sáu ảnh camera và sáu PDF scan có 31/54 field required, tương đương 57.41%, nên vẫn `MANUAL_REVIEW`.
- CCCD development có 30 session đã review. Selection trong `assets/cccd/selection.json` chỉ chứa ID băm, metadata thao tác và ranking score.
- Không đưa file nguồn, OCR text, filename gốc, Ground Truth, field value hay ảnh CCCD/HCNS vào report.

## Khoảng trống cần xử lý

1. TF-P2-002 chưa đạt OCR exact-match gate 80% với tài liệu ảnh/scan.
2. Manifest multi-format khai báo 30 file nhưng chỉ chứa 26, trong đó 10 image reference stale.
3. Railway cần được thiết lập và smoke-test riêng sau khi người vận hành cung cấp cấu hình deployment.
4. TF-P2-002A field recovery đã được phê duyệt nhưng tạm dừng để không chạy song song với báo cáo tuần.
