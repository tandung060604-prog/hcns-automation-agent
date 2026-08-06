# OCR Lab chạy hoàn toàn trên máy local

`apps/ocr_lab` là giao diện thử nghiệm có human review cho OCR/IDP tài liệu
HCNS. Ngoài CCCD, Phase 15 xử lý năm họ tài liệu: CV, đơn/biểu mẫu hành chính,
hợp đồng/quyết định, bằng cấp/chứng chỉ và phiếu nhân viên/bảng biểu. Source
được quản lý cùng repository sản phẩm, còn tài liệu thật, Ground Truth, kết quả
OCR và model weights luôn nằm ngoài Git.

## Cấu trúc

- `web/`: giao diện tại `http://localhost:3000`.
- `api/`: API local tại `http://127.0.0.1:8765`.
- Template-first nhận DOCX/PDF có text; OCR ảnh/PDF scan chỉ dành cho CCCD và chứng chỉ.
- API chỉ đọc/ghi dưới `--data-root` do người vận hành cung cấp.

## Chạy local

Chuẩn bị dependency một lần:

```powershell
python -m pip install -e ".[dev]"
Set-Location apps\ocr_lab\web
npm ci
```

Khởi động từ thư mục gốc repository:

```powershell
.\apps\ocr_lab\api\start_dashboard.ps1 `
  -DataRoot "C:\Camunda\private-data\paddleocr-hr-baseline" `
  -HeldoutRoot "C:\Camunda\private-data\paddleocr-hr-heldout-v1"
```

Mỗi lần đổi private root hãy dùng lại script này; script kiểm tra API health và
không để localhost chạy im lặng với shadow root sai hoặc hàng đợi OCR-HO bằng 0.

Script chỉ bind API vào loopback. Upload được kiểm tra theo nội dung: giới hạn
kích thước/trang, format mismatch, PDF mã hóa, Office macro, archive path và
archive expansion đều bị chặn trước parser/OCR.

## Profile localhost mentor-safe

Mặc định giao diện chỉ hiển thị upload/template đang active và không gọi các
summary của held-out, Ground Truth review, Shadow UAT hoặc external dataset.
Các cờ `VITE_SHOW_HELDOUT`, `VITE_SHOW_GROUND_TRUTH_REVIEW`,
`VITE_SHOW_EXTERNAL_DATASET_REVIEW` và `VITE_SHOW_OCR_HO_SHADOW_UAT` trong
`web/.env.local` phải để `false` khi mở localhost cho mentor. Bật từng cờ chỉ
trong phiên quan sát riêng rồi restart Vite; dữ liệu private không bị xóa.

Phiên xác nhận OCR-HO-V2 dùng thêm `VITE_SHOW_OCR_HO_DIAGNOSTIC_GT=true`.
Tab `Prediction-blind GT` chỉ đọc ảnh nguồn và line ID; tab `Shadow UAT` là
audit baseline/candidate riêng, không dùng để tạo Ground Truth.

Upload vẫn giữ hai đường xử lý cần thiết: Template-first cho DOCX/PDF native
của HCNS và OCR/IDP cho ảnh hoặc PDF scan thuộc CCCD/chứng chỉ. CV, contract và
biểu mẫu HCNS dạng scan bị policy từ chối OCR (`OCR_DISABLED_BY_POLICY`).

## Luồng Phase 14.8 và Phase 15

```text
Upload
→ kiểm tra an toàn
→ native parse (DOCX/PDF text) hoặc OCR scan theo allowlist CCCD/chứng chỉ
→ Paddle detector
→ VietOCR Seq2Seq primary
→ VietOCR Transformer verifier
→ phân loại họ + subtype
→ trích xuất field/table có evidence
→ human review
→ Automatic JSON + Reviewed JSON
```

Paddle chỉ cung cấp geometry/audit evidence và không được tự chọn làm text
fallback. Nếu hai VietOCR model bất đồng, Seq2Seq được giữ nguyên và dòng mang
`needs_review`.

Trong phần kết quả Phase 15, sửa từng field bằng tài liệu gốc, xác nhận hai ô
kiểm tra rồi bấm **Xác nhận các trường Phase 15**. API giữ nguyên artifact tự
động và tạo riêng `idp_result_reviewed.json` cùng `business_reviewed.json`.
Tải lại trang vẫn thấy trạng thái `Field review ✓`.

## Bằng chứng held-out thật trên localhost (private observation)

Profile mentor-safe mặc định không hiển thị aggregate của 18 tài liệu held-out
hoặc hàng đợi Ground Truth. Khi bật cờ private tương ứng, dashboard cho phép
đối chiếu tài liệu gốc từ `private-data`. Endpoint
`/heldout/summary` không trả raw field value, OCR text, tên file hoặc PII.
Endpoint `/heldout/document` chỉ hoạt động trên API loopback và chỉ resolve
document ID đã có trong manifest. Tab CCCD lấy riêng các saved session
`IDENTITY_DOCUMENT` đã Ground Truth, bỏ trùng theo tên file và phục vụ ảnh gốc
qua `/user/source`; các session này không bị trộn vào metric held-out 18 tài
liệu.

Corpus hiện có `authorizedLocalDocumentsOnly=true`: tài liệu thật không được
đóng gói vào web build hoặc commit Git. Report công khai chỉ chứa aggregate
không có PII.

Endpoint `/heldout/evidence` chỉ chạy trên loopback và trả Ground Truth,
prediction cùng `schemaRef` của đúng document cho panel đối chiếu field/JSON.
Local Real-Document Evidence có ba nguồn tách biệt: held-out HCNS, session upload
HCNS và CCCD đã Ground Truth; mỗi nguồn hiển thị ảnh/file bên trái, schema/field
hoặc JSON bên phải và không nhúng artifact private vào web build.
Định tuyến CCCD chỉ dùng orientation thực sự được chọn. Classifier cuối bác
route CCCD cũ khi có nhiều marker CV độc lập; audit live-v5 mới nhất vẫn phát
hiện ba ảnh bằng cấp/chứng chỉ bị route nhầm sang `IDENTITY_DOCUMENT`, nên vấn
đề route ngoài CV chưa được coi là đã sửa xong.

Local Evidence ưu tiên prediction từ replay 15 tài liệu bằng đúng pipeline
localhost hiện hành: PP-OCRv5 detector, VietOCR Seq2Seq/Transformer và parser
Phase 17. Hai nguồn tham chiếu cũ (policy v4 khóa và sealed parser 1.0) vẫn có
nút chuyển riêng. Replay chạy sau khi Ground Truth đã mở nên chỉ là audit,
không đủ điều kiện promotion.

Riêng CCCD dùng pipeline chuyên biệt Phase 11.5 thay vì parser HCNS tổng quát.
Tám ROI mặt trước chạy PaddleOCR PP-OCRv5, EasyOCR `vi`, VietOCR Seq2Seq và
Transformer trên bốn crop profile. JSON giữ riêng `value` Unicode và
`asciiValue`; chuỗi không dấu chỉ phục vụ tìm kiếm/review và không thay thế
giá trị pháp lý. Chỉ đồng thuận chính xác từ ít nhất hai họ recognizer độc lập
mới có thể `accepted`; các trường còn lại là `needs_review`. Local Evidence
hiển thị Ground Truth, prediction Unicode, prediction không dấu, lớp lỗi,
crop và toàn bộ candidate ngay tại từng field.
Họ tên, quốc tịch và địa chỉ chỉ có exact consensus ASCII vẫn phải review;
pipeline không tự thêm dấu để tạo giá trị pháp lý.

Development 15 CCCD hiện đạt Field EM 60,00%, ASCII EM 61,67%, CER 43,60%,
DER 12,65%, Field Presence 95,83% và Accepted Precision 100%. Full-name ASCII
EM 73,33% và address ASCII EM 3,33% vẫn dưới gate, nên policy tiếp tục
`SHADOW_REVIEW_ONLY`.

## Ground Truth và F5

Review đã lưu được API trả về trong `lineReviews`. Giao diện tạo queue chỉ từ
các case chưa có review, nên tải lại trang sẽ tiếp tục ở crop chưa xác nhận đầu
tiên. Ground Truth không được suy ra từ text của recognizer.

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
Set-Location apps\ocr_lab\web
npm test
```

Không commit `node_modules`, `.next`, `dist`, `.wrangler`, file upload, output,
Ground Truth private hoặc model weights.
