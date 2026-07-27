# Product Vision

## Vấn đề

HCNS tiếp nhận PDF, ảnh, Word, Excel và nhiều biểu mẫu không đồng nhất. OCR đơn
lẻ chỉ tạo text; nó không giữ đầy đủ cấu trúc, bằng chứng, trách nhiệm phê duyệt
hay trạng thái quy trình.

## Tầm nhìn

Xây dựng nền tảng gồm ba vai trò tách biệt:

1. **IDP đọc và hiểu tài liệu**: intake an toàn, native parsing/OCR khi cần,
   canonicalization, classification, extraction, validation và provenance.
2. **Agent phân tích và đề xuất**: phát hiện thiếu/mâu thuẫn, soạn task/email/
   Business JSON và gọi tool trong policy.
3. **Camunda điều phối quy trình và con người**: BPMN, User Task, SLA, retry,
   escalation, assignment và process audit.

Luồng đích tạo Business JSON đã kiểm chứng, đưa field nhạy cảm hoặc không chắc
chắn sang Human Review và chỉ cho side effect sau policy/approval.

## Phạm vi tài liệu

CV, hồ sơ nhân viên, CCCD/hộ chiếu, hợp đồng/phụ lục, quyết định, đơn nghỉ/công
tác/đề nghị, chấm công/lương, chứng chỉ/bằng cấp, quy chế/quy trình, công văn,
thông báo, biểu mẫu và tài liệu chưa xác định đều là input hợp lệ. CCCD không
phải trung tâm sản phẩm.

## Ranh giới quyết định

Agent không tự tuyển dụng, sa thải, đổi lương, phê duyệt nghỉ phép, sửa định
danh hoặc ghi field nhạy cảm vào HRM. Agent không thay Camunda quyết định bước
quy trình dài hạn. Review có thể dùng custom UI, nhưng Camunda vẫn sở hữu User
Task, authorization, deadline và bước tiếp theo.

## Chỉ số thành công

- giảm thời gian nhập liệu/đối chiếu và correction rate;
- tăng field exact match trên dữ liệu được duyệt;
- mọi field có provenance truy về page/block/sheet/cell;
- không side effect trái policy hoặc process state song song Camunda;
- không có raw PII/file lớn trong process variables hay log.
