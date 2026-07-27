# Product Vision

## Vấn đề

Bộ phận HCNS tiếp nhận nhiều giấy tờ không đồng nhất, phải nhập lại dữ liệu,
đối chiếu thủ công và chuyển task qua nhiều người. OCR riêng lẻ chỉ tạo text;
nó chưa giải quyết tính đúng đắn, trách nhiệm phê duyệt và tích hợp nghiệp vụ.

## Tầm nhìn

Xây dựng một Agent hỗ trợ chuyên viên HCNS từ lúc nhận tài liệu đến lúc tạo dữ
liệu có thể sử dụng:

1. đọc và phân loại giấy tờ;
2. trích xuất trường kèm bằng chứng;
3. kiểm tra quy tắc và phát hiện mâu thuẫn;
4. đề xuất bước tiếp theo;
5. chuyển đúng điểm không chắc chắn cho con người;
6. chỉ thực thi side effect sau phê duyệt.

## Agent được phép

- OCR và phân loại tài liệu.
- Đánh dấu trường thiếu, mờ, hết hạn hoặc không nhất quán.
- Soạn đề xuất task/email/Business JSON.
- Chạy workflow ở chế độ dry-run.
- Thực thi hành động ít rủi ro đã được policy cho phép.

## Agent không được phép

- Tự đưa ra quyết định tuyển dụng, chấm dứt hợp đồng, kỷ luật hoặc lương.
- Suy diễn thuộc tính nhạy cảm không có trong tài liệu.
- Tự sửa dữ liệu định danh để làm tăng confidence.
- Gửi PII ra ngoài ranh giới triển khai.
- Bỏ qua human review chỉ vì workflow cần chạy nhanh.

## Chỉ số thành công

- Giảm thời gian nhập liệu và đối chiếu.
- Tăng field exact match trên dữ liệu được duyệt.
- Không có side effect trái policy.
- 100% thay đổi nghiệp vụ có provenance và audit trail.
- Chuyên viên có thể sửa/từ chối đề xuất một cách rõ ràng.

