# Demo đối chiếu tài liệu thật trên localhost

Kịch bản này dành cho user, mentor hoặc reviewer xem trực tiếp tài liệu đã được
chủ sở hữu cho phép. Showcase không dùng dữ liệu mô phỏng để thay cho tài liệu
thật và không khởi tạo Camunda.

## Quy tắc dữ liệu

- Chỉ dùng tài liệu thật đã có quyền xem và xử lý.
- Xác minh file nguồn trước khi chạy; lưu SHA-256 trong bằng chứng local.
- File nguồn, Ground Truth, OCR output và comparison chỉ nằm trong data root
  private, không commit vào Git.
- Nếu chưa có tài liệu thật của một family, ghi rõ `CHƯA CÓ BẰNG CHỨNG`; không
  thay bằng tài liệu minh họa.
- Kết quả `PASS`/`HOLD` chỉ áp dụng cho file đang xem và không tự duyệt nghiệp vụ.

## Bằng chứng đang có ngày 13/08/2026

| Family | File nguồn local | SHA-256 | Kết quả hiện tại |
|---|---|---|---|
| CV | CV PDF cá nhân trong data root private | `8ad0b6f60f40f8f7e9c442958e3cd608199f5f272ffc11ed53d8c88d9e6e1a30` | `0/10 exact`, `HOLD` |
| IELTS | `ielts-001.png` | `b49a069f8f78753b96e201cdab9d9c3b6414a364567f6331f98a64ce0c5dc8be` | `0/5 exact`, `HOLD` |
| Hợp đồng thử việc | Chưa có file thật đủ điều kiện | — | Chưa có bằng chứng |

CV được đọc bằng `pdf/pymupdf-native`. IELTS được xử lý bằng PaddleOCR
`PP-OCRv5_mobile_det + latin_PP-OCRv5_mobile_rec` trên CPU. Hai file đều được
nhập Ground Truth trực tiếp từ nguồn và giữ `MANUAL_REVIEW`.

Kết quả xấu là bằng chứng quan trọng: thuật toán hiện nhận diện đúng family nhưng
parser gắn sai field trên cả CV và IELTS. Không dùng hai family này cho quyết định
nghiệp vụ hoặc tuyên bố production-ready.

## Cách mở kết quả đã lưu

1. Khởi động API bằng data root private chứa các session thật, không truyền báo
   cáo aggregate của corpus khác.
2. Mở `http://localhost:3000/workspace`.
3. Tại **Kho hồ sơ**, chọn **Tài liệu đã xử lý**.
4. Chọn CV hoặc IELTS. UI hiển thị source, template, parser và giá trị trích xuất.
5. Bấm vào tài liệu để mở khu **Đối chiếu kết quả · Current file**.
6. Đọc từng cột Prediction, Ground Truth, confidence/evidence và badge kết quả.

## Cách chạy một tài liệu thật mới

1. Xác nhận quyền sử dụng và tính nguyên bản của tài liệu.
2. Tính SHA-256 trước khi upload.
3. Upload trong chế độ **Biểu mẫu HCNS** và bấm **Trích xuất tài liệu**.
4. Đối chiếu preview với từng Prediction rồi nhập Ground Truth từ chính nguồn.
5. Bấm **Đối chiếu kết quả** và ghi lại số Exact/Accepted/Sai cùng `HOLD`/`PASS`.
6. Giữ toàn bộ session ngoài Git. Nếu parser sai, giữ nguyên mismatch và mở task
   sửa thuật toán; không sửa Ground Truth để làm đẹp chỉ số.

## Checklist trình bày

| Bằng chứng | Điều kiện đạt |
|---|---|
| Quyền sử dụng | Chủ sở hữu đã cho phép xem và xử lý |
| Nguồn | Preview đúng file, hash nguồn đã ghi local |
| Prediction | Kết quả do runtime hiện tại tạo ra |
| Ground Truth | Reviewer nhập trực tiếp từ tài liệu nguồn |
| Comparison | Badge và tổng số đúng/sai khớp từng field |
| Metadata | Thấy template/parser/OCR model/profile đang chạy |
| Safety | Local-only, review-only, không có HRIS/Camunda side effect |
