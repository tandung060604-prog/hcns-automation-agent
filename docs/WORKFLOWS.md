# HCNS Workflows

## 1. Onboarding hồ sơ nhân viên

```text
RECEIVED → OCR_COMPLETE → VALIDATED
                         ├─ đủ + policy pass → REVIEW_REQUIRED
                         └─ thiếu/lỗi        → REVIEW_REQUIRED
REVIEW_REQUIRED → APPROVED → READY_TO_SYNC → COMPLETED
                └─ REJECTED
```

Dù confidence cao, định danh cá nhân vẫn phải review trước lần ghi HRM đầu tiên.

## 2. Đơn nghỉ phép

Agent đọc loại đơn, nhân viên, khoảng ngày và lý do; đối chiếu chính sách và số
dư phép qua port nghiệp vụ. Agent được tạo đề xuất nhưng quản lý/người có thẩm
quyền phê duyệt.

## 3. Hợp đồng lao động

Agent trích xuất số hợp đồng, bên ký, loại, thời hạn và các mốc cần nhắc. Lương,
phụ cấp và điều khoản nhạy cảm luôn được review. Agent có thể tạo reminder nhưng
không tự gia hạn/chấm dứt.

## 4. Bảng chấm công

Ưu tiên parser bảng/native XLSX trước OCR ảnh. Agent phát hiện ô thiếu, tổng giờ
bất thường và chênh lệch; chuyên viên xác nhận trước khi chuyển payroll.

## Quy tắc chung

- Mỗi workflow có schema version.
- Transition không hợp lệ phải bị từ chối.
- Connector bên ngoài mặc định dry-run.
- Retry phải dùng cùng idempotency key.
- Audit event không chứa raw file và chỉ lưu PII tối thiểu cần thiết.

