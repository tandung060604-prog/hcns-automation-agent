# OCR Lab chạy hoàn toàn trên máy local

`apps/ocr_lab` là giao diện thử nghiệm có human review cho OCR/IDP tài liệu
HCNS. Ngoài CCCD, Phase 15 xử lý năm họ tài liệu: CV, đơn/biểu mẫu hành chính,
hợp đồng/quyết định, bằng cấp/chứng chỉ và phiếu nhân viên/bảng biểu. Source
được quản lý cùng repository sản phẩm, còn tài liệu thật, Ground Truth, kết quả
OCR và model weights luôn nằm ngoài Git.

## Cấu trúc

- `web/`: giao diện tại `http://localhost:3000`.
- `api/`: API local tại `http://127.0.0.1:8765`.
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

Script chỉ bind API vào loopback. Upload được kiểm tra theo nội dung: giới hạn
kích thước/trang, format mismatch, PDF mã hóa, Office macro, archive path và
archive expansion đều bị chặn trước parser/OCR.

## Luồng Phase 14.8 và Phase 15

```text
Upload
→ kiểm tra an toàn
→ native parse (PDF text/DOCX/XLSX) hoặc OCR scan
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

## Bằng chứng held-out thật trên localhost

Màn hình chính chỉ hiển thị aggregate của 18 tài liệu held-out thật đã Ground
Truth và cho phép đối chiếu tài liệu gốc từ `private-data`. Endpoint
`/heldout/summary` không trả raw field value, OCR text, tên file hoặc PII.
Endpoint `/heldout/document` chỉ hoạt động trên API loopback và chỉ resolve
document ID đã có trong manifest. Tab CCCD lấy riêng các saved session
`IDENTITY_DOCUMENT` đã Ground Truth, bỏ trùng theo tên file và phục vụ ảnh gốc
qua `/user/source`; các session này không bị trộn vào metric held-out 18 tài
liệu.

Corpus hiện có `authorizedLocalDocumentsOnly=true`: tài liệu thật không được
đóng gói vào web build hoặc commit Git. Report công khai chỉ chứa aggregate
không có PII.

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
