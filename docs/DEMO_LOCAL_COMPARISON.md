# Demo DATA-29: mở đúng tài liệu đã tạo metric

Màn hình này nối trực tiếp aggregate DATA-29 với source, Prediction và Ground
Truth đã tạo ra điểm số. DATA-29 là development corpus được cấp quyền
chạy local; không phải bằng chứng chất lượng trên tài liệu HCNS thật.

## Phạm vi

- Toàn corpus: 12 tài liệu, 112 field.
- Strict exact: `107/112` — Contract `42/42`, CV `45/50`, IELTS `20/20`.
- Accepted: `112/112` theo matching policy `2.0.0`.
- Decision: `HOLD`; `promotionAllowed=false`.
- Localhost hiển thị đủ 12/12 tài liệu từ chính corpus theo ba nhóm 3/5/4.

| Bộ lọc | Số tài liệu | Field exact | Field accepted |
|---|---:|---:|---:|
| Contract | 3 | 42/42 | 42/42 |
| CV | 5 | 45/50 | 50/50 |
| IELTS | 4 | 20/20 | 20/20 |

## Cách xem

1. Mở `http://localhost:3000/workspace#explorer`.
2. Chọn **DATA-29 · 12 tài liệu metric · 3 Contract · 5 CV · 4 IELTS**.
3. Chọn bộ lọc Contract, CV hoặc IELTS rồi chọn một case trong danh sách.
4. Đọc source ở giữa; đọc Prediction, Ground Truth, match type và evidence bên phải.
5. Kiểm tra điểm riêng của case và matching policy `2.0.0`.

Source, inventory, sealed Ground Truth, Prediction và aggregate report đều nằm
ngoài Git. Source được resolve từ inventory đã khóa; SHA-256 của
Ground Truth và Prediction khớp marker DATA-29.

Khu vực evidence không hiển thị session upload độc lập. Session vẫn ở private
storage để màn kết quả hiện tại và Camunda local shadow có thể dùng UUID tham chiếu.
