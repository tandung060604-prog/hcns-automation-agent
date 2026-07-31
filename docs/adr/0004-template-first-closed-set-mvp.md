# ADR-0004: Template-first closed-set cho MVP

Status: Accepted

## Bối cảnh

Pipeline generic nhiều loại tài liệu và nhiều layout tạo quá nhiều biến số để chứng
minh độ đúng của classifier, parser và benchmark. Phase 1 có hai biểu mẫu DOCX chuẩn
do tổ chức kiểm soát: đơn nghỉ phép và đơn tăng ca.

## Quyết định

- Endpoint MVP dùng registry versioned và chỉ xử lý template đã đăng ký.
- Nhận diện dựa trên nội dung/anchor đã chuẩn hóa, không dựa filename.
- DOCX có text luôn dùng native OOXML; OCR không thuộc Phase 1.
- Mỗi template sở hữu parser, validator, schema và regression evidence riêng.
- Không khớp closed set thì `REJECT_UNSUPPORTED`; thiếu hoặc mâu thuẫn thì
  `MANUAL_REVIEW`.
- Pipeline generic cũ được giữ để tương thích nhưng không là fallback của endpoint
  template-first.
- Camunda chỉ nhận routing metadata và result reference, không nhận raw document hay
  full extracted payload.

## Hệ quả

Độ bao phủ loại tài liệu giảm nhưng hành vi có thể kiểm chứng trên từng template.
Thêm template mới cần definition, parser, validator, schema và evidence riêng. PDF
scan/ảnh chỉ được xem xét sau khi native DOCX đạt gate.
