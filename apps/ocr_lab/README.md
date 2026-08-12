# OCR Lab chạy hoàn toàn trên máy local

`apps/ocr_lab` là giao diện thử nghiệm có human review cho OCR/IDP tài liệu
HCNS. Ngoài CCCD, Phase 15 xử lý năm họ tài liệu: CV, đơn/biểu mẫu hành chính,
hợp đồng/quyết định, bằng cấp/chứng chỉ và phiếu nhân viên/bảng biểu. Source
được quản lý cùng repository sản phẩm, còn tài liệu thật, Ground Truth, kết quả
OCR và model weights luôn nằm ngoài Git.

## Cấu trúc

- `web/`: giao diện tại `http://localhost:3000`.
- `api/`: API local tại `http://127.0.0.1:8765`.
- Template-first nhận DOCX/PDF có text. Route DATA-17 development cho phép OCR local
  ảnh/PDF scan của CV, Contract và IELTS/chứng chỉ; mọi output scan vẫn `MANUAL_REVIEW`.
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
  -DataRoot "C:\Camunda\private-data\paddleocr-hr-baseline"
```

Mỗi lần đổi private root hãy dùng lại script này; script kiểm tra API health và
không để localhost chạy im lặng với shadow root sai hoặc hàng đợi OCR-HO bằng 0.

Script chỉ bind API vào loopback. Upload được kiểm tra theo nội dung: giới hạn
kích thước/trang, format mismatch, PDF mã hóa, Office macro, archive path và
archive expansion đều bị chặn trước parser/OCR.

## Profile localhost mentor-safe

Mặc định giao diện chỉ hiển thị upload/template đang active và không gọi các
summary của Ground Truth review, Shadow UAT hoặc external dataset. Các cờ
`VITE_SHOW_GROUND_TRUTH_REVIEW`,
`VITE_SHOW_EXTERNAL_DATASET_REVIEW` và `VITE_SHOW_OCR_HO_SHADOW_UAT` trong
`web/.env.local` phải để `false` khi mở localhost cho mentor. Bật từng cờ chỉ
trong phiên quan sát riêng rồi restart Vite; dữ liệu private không bị xóa.

Phiên xác nhận OCR-HO-V2 dùng thêm `VITE_SHOW_OCR_HO_DIAGNOSTIC_GT=true`.
Tab `Prediction-blind GT` chỉ đọc ảnh nguồn và line ID; tab `Shadow UAT` là
audit baseline/candidate riêng, không dùng để tạo Ground Truth.
Bản nháp được lưu local khi chuyển tài liệu; chỉ `LINES CHECKED` mới được tính
là Ground Truth đã xác nhận.

Upload vẫn giữ hai đường xử lý cần thiết: Template-first cho DOCX/PDF native
của HCNS và OCR/IDP cho nguồn scan nằm trong scope. DATA-17 mở riêng route
development cho CV, Contract và IELTS/chứng chỉ; OCR chỉ tạo evidence để review,
không tự động chấp nhận. Profile upload thông thường vẫn fail-closed ngoài allowlist.

## Luồng Phase 14.8 và Phase 15

```text
Upload
→ kiểm tra an toàn
→ native parse (DOCX/PDF text) hoặc local OCR scan theo family/scope
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

## Bằng chứng tài liệu thật trên localhost

### DATA-28 local-review handoff

For the current CI-green development handoff, run the API and web locally with
the private DATA-26 development bundle, then open
`http://localhost:3000/workspace` and choose **DATA-12 · Prediction + GT**.
The private session exposes 12 development documents (3 Contract, 5 CV, 4
IELTS) and 112 field comparisons. The remaining strict CV gap is recorded only
as aggregate review evidence: `experience` 5, `skills` 4 and `desired_role` 1;
Contract and IELTS have no remaining strict gap in this replay. Keep all five
scan/image documents on `MANUAL_REVIEW`. Do not use this view to reopen
DATA-24, create DATA-27 held-out evidence or enable fallback.

Dashboard chỉ đọc các nguồn local hiện hành: session upload/template, CCCD đã
review và OCR-HO shadow/diagnostic khi được bật riêng. Các nguồn có scope và
mẫu số độc lập; dữ liệu thật không được đóng gói vào web build hoặc commit Git.

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
python -m pytest -q
Set-Location apps\ocr_lab\web
npm test
```

Không commit `node_modules`, `.next`, `dist`, `.wrangler`, file upload, output,
Ground Truth private hoặc model weights.

## OCR-HO-V2-014 sealed development replay

The prediction-blind line mapping is sealed outside Git at
`OCR_HO_V2_014_GT_SEALED_PRIVATE.json`. Its digest is exposed by the diagnostic
summary; once the marker exists, both draft and final Ground Truth writes return
`400`. The replay report publishes `developmentRegressionGate` and
`heldoutReadinessGate` independently. The current result is development-improved
but readiness HOLD (residence ASCII remains below threshold), so no new held-out
set is created and no lexicon or fifth engine is enabled.

## DATA-17 development comparison (2026-08-06)

The private 12-document split contains 112 sealed fields. The local hybrid route
uses EasyOCR `vi+en` for scanned CV and PaddleOCR for IELTS layout/patterns;
native Contract/CV documents continue through the shared layout-aware parsers.

| Family | Strict exact | Accepted text |
|---|---:|---:|
| Contract | 40/42 (95.24%) | 40/42 (95.24%) |
| CV | 30/50 (60%) | 44/50 (88%) |
| IELTS/certificate | 20/20 (100%) | 20/20 (100%) |
| **Total** | **90/112 (80.36%)** | **104/112 (92.86%)** |

Classification is 12/12 and schema errors are 0. The five image/PDF-scan
documents remain `MANUAL_REVIEW`; no cloud OCR is used. This is a separate
development aggregate (`promotionAllowed=false`) and does not reopen the old
evaluate-once artifact.
