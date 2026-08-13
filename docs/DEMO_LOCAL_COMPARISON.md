# Kịch bản demo đối chiếu tài liệu trên localhost

Kịch bản này dành cho user, mentor hoặc reviewer muốn xem luồng đang hoạt động
mà không cần khởi tạo Camunda. Dùng tài liệu synthetic hoặc tài liệu private đã
được phép xử lý; không dùng PII thật trong ảnh chụp hoặc video công khai.

## Mục tiêu demo

Chứng minh một tài liệu đi qua đủ chuỗi:

`upload → preview nguồn → extraction → Ground Truth → comparison → HOLD/PASS`

Ba family cần trình bày:

| Family | Định dạng nên dùng | Kết quả cần thấy |
|---|---|---|
| CV | DOCX hoặc PDF | Template `cv-v2`, 10 field review-only |
| Hợp đồng thử việc | DOCX hoặc PDF | Template `probation-contract-v2`, 14 field review-only |
| IELTS | PDF, PNG hoặc JPG/JPEG | Template `ielts-certificate-v2`, 5 field; ảnh dùng OCR local |

## Chuẩn bị

1. Khởi động dashboard/API theo root `README.md`.
2. Mở `http://localhost:3000/workspace`.
3. Giữ chế độ **Biểu mẫu HCNS**.
4. Chuẩn bị file synthetic hoặc private đã được phép. Không commit file, kết quả
   OCR hoặc Ground Truth vào Git.
5. Nếu demo ảnh IELTS, kiểm tra `GET /health` báo đúng OCR backend mong muốn.

## Thao tác cho mỗi tài liệu

1. Upload file và bấm **Trích xuất tài liệu**.
2. Xác nhận bên trái hiển thị nguồn/preview; bên phải hiển thị đúng template,
   document type, confidence và validation status.
3. Kiểm tra khối metadata:
   - template và parser version;
   - intake parser;
   - OCR backend/version/model/device/profile nếu dùng ảnh;
   - matching policy và thời gian xử lý.
4. Đọc từng Prediction trực tiếp với nguồn, sau đó nhập Ground Truth. Không sao
   chép Prediction sang Ground Truth nếu chưa đối chiếu nguồn.
5. Bấm **Đối chiếu kết quả**.
6. Xác nhận mỗi field có một badge: `EXACT`, `ACCEPTED`, `MISMATCH`, `MISSING`
   hoặc `NEEDS_REVIEW`.
7. Ghi lại tổng Exact/Accepted/Sai và quyết định `HOLD`/`PASS`.

## Cách trình bày kết quả

- **FILE HIỆN TẠI** là kết quả vừa upload, dùng Ground Truth của chính file đó.
- **DATA-29 · AGGREGATE** là bằng chứng development đã seal, chỉ để tham khảo:
  strict `107/112`, accepted `112/112`, quyết định `HOLD`.
- Không dùng aggregate để che một mismatch của file hiện tại.
- `PASS` ở comparison không tự phê duyệt nghiệp vụ; `promotionAllowed=false`
  vẫn giữ nguyên.

## Checklist bằng chứng

| Bằng chứng | Đạt khi |
|---|---|
| Upload | UI chỉ cho chọn định dạng hợp lệ theo family |
| Source | Preview hoặc placeholder native hiển thị đúng file |
| Prediction | Đủ field schema, không tự điền giá trị không có trong nguồn |
| Ground Truth | Reviewer nhập từ nguồn và lưu trong session private |
| Comparison | Badge và exact/wrong count khớp các field đang hiển thị |
| Metadata | Nhìn thấy version thuật toán và profile đang chạy |
| Safety | Kết luận review-only, không có cloud/HRIS side effect |

## Kết quả smoke ngày 13/08/2026

- API synthetic: 7/7 tổ hợp CV DOCX/PDF, Contract DOCX/PDF, IELTS PDF/PNG/JPG.
- Browser E2E: 3/3 family hiển thị đủ source → comparison → conclusion.
- PaddleOCR runtime thật: IELTS PNG nhận đúng template và giữ
  `MANUAL_REVIEW`/`OCR_REVIEW_REQUIRED`.
- Fixture IELTS synthetic hiện cho `3 exact · 2 sai`; hai mismatch parser được
  giữ nguyên trên UI và quyết định là `HOLD`. Đây là bằng chứng màn hình bắt lỗi,
  không phải tuyên bố chất lượng production.
