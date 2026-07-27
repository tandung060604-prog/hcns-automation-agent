# Human-in-the-loop

Camunda User Task là biểu diễn ưu tiên và là nguồn sự thật cho assignment, task
state, deadline, escalation, authorization và bước tiếp theo. Custom Review UI
chỉ đọc result reference/provenance và hoàn thành task qua Camunda; không sở hữu
review queue hoặc state machine độc lập.

## Khi nào bắt buộc review

- trường định danh, họ tên, ngày sinh, số hợp đồng, lương hoặc tài khoản;
- confidence thấp hơn policy;
- validation thất bại hoặc hai tài liệu mâu thuẫn;
- document type không chắc chắn;
- mọi hành động ghi HRM/BPM có tác động đến quyền lợi nhân viên;
- model, schema hoặc workflow vừa thay phiên bản.
- parser warning, unreadable block hoặc quality gate không đạt.
- document type chưa chắc chắn/chưa có extractor được phê duyệt;
- required field thiếu, field xung đột hoặc date range không hợp lệ;

## Review payload

Reviewer cần thấy:

- ảnh/crop hoặc source reference;
- OCR text gốc;
- giá trị được đề xuất;
- confidence và validation;
- model/version;
- lý do yêu cầu review;
- hành động sẽ xảy ra sau khi approve.
- page/block hoặc sheet/row/cell và bounding box khi có.

Không chỉ đưa một textbox đã điền sẵn vì dễ tạo automation bias.

## Quyết định

- `APPROVE`: chấp nhận đề xuất không đổi.
- `CORRECT`: sửa giá trị và lưu cả trước/sau.
- `REJECT`: không cho case đi tiếp, bắt buộc lý do.

Approval phải gắn reviewer, thời điểm, case version và payload hash. Approval cũ
không được dùng lại sau khi tài liệu hoặc đề xuất thay đổi.

## SLA và escalation

Camunda có thể gán priority nhưng không được tự approve khi quá SLA. Quá hạn chỉ
làm phát sinh escalation theo BPMN cho người có thẩm quyền.
