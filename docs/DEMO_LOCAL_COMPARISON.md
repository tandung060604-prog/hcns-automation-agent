# Demo DATA-29: mở đúng tài liệu đã tạo metric

Màn hình này nối trực tiếp aggregate DATA-29 với source, Prediction và Ground
Truth đã tạo ra điểm số. DATA-29 là development corpus synthetic được cấp quyền
chạy local; không phải bằng chứng chất lượng trên tài liệu HCNS thật.

## Phạm vi

- Toàn corpus: 12 tài liệu, 112 field.
- Strict exact: `107/112` — Contract `42/42`, CV `45/50`, IELTS `20/20`.
- Accepted: `112/112` theo matching policy `2.0.0`.
- Decision: `HOLD`; `promotionAllowed=false`.
- Localhost hiển thị 4/12 tài liệu từ chính corpus, không dùng file đại diện.

| Case | Source thuộc DATA-29 | Định dạng | Điểm riêng |
|---|---|---|---:|
| `contract-002` | `02_contract_phuc_an_retail.pdf` | PDF text | 14/14 exact, 14/14 accepted |
| `cv-002` | `05_cv_le_thu_trang.pdf` | PDF text | 9/10 exact, 10/10 accepted |
| `cv-005` | `CV_02_Le_Quang_Huy_scan.pdf` | PDF scan | 9/10 exact, 10/10 accepted |
| `ielts-001` | `07_ielts_nguyen_thu_phuong.png` | Image/OCR | 5/5 exact, 5/5 accepted |

Bốn tài liệu đang show cộng lại là `37/39 exact`, `39/39 accepted`. Con số này
chỉ mô tả sample hiển thị; aggregate chính thức vẫn dùng đủ 12 tài liệu.

## Cách xem

1. Mở `http://localhost:3000/workspace#explorer`.
2. Chọn **DATA-29 · 4 tài liệu metric**.
3. Chọn một case trong danh sách.
4. Đọc source ở giữa; đọc Prediction, Ground Truth, match type và evidence bên phải.
5. Kiểm tra điểm riêng của case và matching policy `2.0.0`.

Source, inventory, sealed Ground Truth, Prediction và aggregate report đều nằm
ngoài Git. SHA-256 của bốn source đã được xác minh khớp inventory; SHA-256 của
Ground Truth và Prediction khớp marker DATA-29.

## Phân biệt hai tab

- **DATA-29 · 4 tài liệu metric:** đúng tài liệu đã tạo metric `107/112`.
- **Tài liệu đã xử lý:** session upload độc lập; kết quả ở đây không đại diện và
  không được cộng vào DATA-29.
