# Data Security and PII

## Phân loại

- Public: tài liệu dự án và dữ liệu synthetic.
- Internal: policy, metric tổng hợp, cấu hình không secret.
- Confidential: CV, hợp đồng, chấm công, quyết định.
- Restricted: CCCD/hộ chiếu, tài khoản, lương, dữ liệu sức khỏe.

## Quy tắc lưu trữ

- Git chỉ chứa Public/Internal đã làm sạch.
- File thật nằm ngoài repository trong encrypted data root.
- Output OCR kế thừa mức nhạy cảm của file nguồn.
- Log dùng document ID; không log raw text hoặc field value.
- Retention có hạn và hỗ trợ xóa theo case/document.
- Canonical result lớn nằm trong result/object store; Camunda chỉ giữ opaque
  reference và biến routing nhỏ.

## Network

Local backend là mặc định. Cloud OCR/VLM phải được phê duyệt riêng, có DPA phù
hợp, region/retention rõ ràng và redaction khi khả thi.

Parser local không tự follow external link/resource, chạy macro, embedded code
hay executable chuyển đổi. Unit tests không dùng network.

## Intake safety

- Detect bằng magic bytes và cấu trúc OOXML, không chỉ extension/MIME.
- Chặn file vượt size/page limit, ZIP path traversal, archive expansion và entry
  count bất thường.
- Từ chối macro-enabled, encrypted/password-protected và corrupted document.
- Legacy DOC/XLS chỉ trả `CONVERSION_REQUIRED`; không tự chạy Microsoft Office.

Camunda process variables không chứa raw file, raw OCR text, canonical payload,
ảnh, bảng tính đầy đủ hoặc PII không cần cho routing. Chỉ dùng document/case ID,
business/correlation/idempotency key, format/type/status, review flag, schema
version, error code và result reference.

Classification evidence chỉ lưu source location và marker ID có version, không
copy đoạn raw text. Validation issue không chứa field value. Business JSON có
field nghiệp vụ nên kế thừa sensitivity của tài liệu nguồn và chỉ được lưu/truy
cập qua result store được kiểm soát.

## Secrets

Secret chỉ lấy từ secret manager hoặc environment runtime. `.env`, token, cookie
và credential không được commit.

## Dataset

Chỉ dùng tài liệu thật khi có quyền sử dụng và mục đích được xác định. Dataset
benchmark phải có manifest nguồn/quyền/retention; report public chỉ chứa metric
tổng hợp.

Fixture unit/contract test phải synthetic. Không đọc/copy private-data, upload,
model weights hoặc OCR output thật vào repository.
