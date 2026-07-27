# Human-in-the-loop

## Khi nào bắt buộc review

- trường định danh, họ tên, ngày sinh, số hợp đồng, lương hoặc tài khoản;
- confidence thấp hơn policy;
- validation thất bại hoặc hai tài liệu mâu thuẫn;
- document type không chắc chắn;
- mọi hành động ghi HRM/BPM có tác động đến quyền lợi nhân viên;
- model, schema hoặc workflow vừa thay phiên bản.

## Review payload

Reviewer cần thấy:

- ảnh/crop nguồn;
- OCR text gốc;
- giá trị được đề xuất;
- confidence và validation;
- model/version;
- lý do yêu cầu review;
- hành động sẽ xảy ra sau khi approve.

Không chỉ đưa một textbox đã điền sẵn vì dễ tạo automation bias.

## Quyết định

- `APPROVE`: chấp nhận đề xuất không đổi.
- `CORRECT`: sửa giá trị và lưu cả trước/sau.
- `REJECT`: không cho case đi tiếp, bắt buộc lý do.

Approval phải gắn reviewer, thời điểm, case version và payload hash. Approval cũ
không được dùng lại sau khi tài liệu hoặc đề xuất thay đổi.

## SLA và escalation

Queue có priority nhưng không được tự approve khi quá SLA. Quá hạn chỉ làm phát
sinh escalation task cho người có thẩm quyền.

