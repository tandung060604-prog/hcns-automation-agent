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

## Network

Local backend là mặc định. Cloud OCR/VLM phải được phê duyệt riêng, có DPA phù
hợp, region/retention rõ ràng và redaction khi khả thi.

## Secrets

Secret chỉ lấy từ secret manager hoặc environment runtime. `.env`, token, cookie
và credential không được commit.

## Dataset

Chỉ dùng tài liệu thật khi có quyền sử dụng và mục đích được xác định. Dataset
benchmark phải có manifest nguồn/quyền/retention; report public chỉ chứa metric
tổng hợp.

