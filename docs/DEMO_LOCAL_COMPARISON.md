# Demo DATA-31 R7: đối chiếu Prediction và Ground Truth trên localhost

Màn hình này nối trực tiếp aggregate DATA-31 R7 với source, Prediction và Ground
Truth đã tạo ra điểm số. DATA-31 là development corpus được cấp quyền chạy local;
owner đã chấp nhận gate cho shadow review, nhưng đây không phải bằng chứng chất
lượng production.

## Phạm vi

- Toàn corpus: 13 tài liệu, 109 field đo; 17 field `OUT_OF_SCOPE`.
- Strict exact: `104/109` — Contract `42/44`, CV `42/45`, IELTS `20/20`.
- Accepted: `108/109`; `109/109` field có kết quả.
- Matching policy: `2.1.0`; parser: `structured-hr/family-layout/2.2.8`.
- Owner decision: chấp nhận cho local shadow/demo; formal report vẫn `HOLD` và
  `promotionAllowed=false`.
- Localhost hiển thị đủ 13/13 tài liệu theo ba nhóm 4/5/4.

| Bộ lọc | Số tài liệu | Field exact | Field accepted |
|---|---:|---:|---:|
| Contract | 4 | 42/44 | 43/44 |
| CV | 5 | 42/45 | 45/45 |
| IELTS | 4 | 20/20 | 20/20 |

## Cách xem

1. Mở `http://localhost:3000/workspace?qa=real-only#upload`.
2. Chọn **DATA-31 · R7 · 13 tài liệu · 4 Contract · 5 CV · 4 IELTS**.
3. Chọn bộ lọc Contract, CV hoặc IELTS rồi chọn một case trong danh sách.
4. Đọc source ở giữa; đọc Prediction, Ground Truth, match type và evidence bên phải.
5. Kiểm tra điểm riêng của case và matching policy `2.1.0`.

Source, inventory, sealed Ground Truth, Prediction và aggregate report đều nằm
ngoài Git. Source được resolve từ inventory đã khóa; SHA-256 của Ground Truth và
Prediction khớp marker private DATA-31.

Khu vực evidence không hiển thị session upload độc lập. Session vẫn ở private
storage để màn kết quả hiện tại và Camunda local shadow có thể dùng UUID tham chiếu.

DATA-29 vẫn được giữ ở lịch sử để đối chiếu regression, không bị ghi đè bởi R7.
