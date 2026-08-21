# ADR-0007: Tách professional title và role title trong Contract

- Trạng thái: Accepted
- Ngày: 2026-08-19
- Phạm vi: Template-first Contract schema và downstream HR/Camunda mapping

## Bối cảnh

Năm tài liệu trong review PDF-001F đều có đồng thời nhãn `Chức danh chuyên
môn` và `Chức vụ/Vị trí`. Ground Truth của năm tài liệu chọn role title, trong
khi Contract 23 chọn professional title. Đây là xung đột ngữ nghĩa của một
trường `job_title`, không phải tài liệu thiếu dữ liệu hay lỗi OCR.

## Quyết định

1. Thêm hai trường `professional_title` và `role_title` vào runtime Contract
   schema.
2. `professional_title` lấy từ `Chức danh chuyên môn` và giữ nguyên nội dung
   nghề nghiệp.
3. `role_title` lấy từ `Chức vụ/Vị trí`; bỏ phần điều khoản quản lý sau dấu
   chấm phẩy để giữ tên vai trò.
4. `job_title` tiếp tục là trường tương thích. Nó ưu tiên `role_title` cho
   nghiệp vụ phân công nhân sự và Camunda; khi tài liệu không có `role_title`,
   dùng `professional_title` làm fallback có kiểm soát thay vì trả rỗng.
5. Giữ manual review, không sửa Ground Truth hoặc báo cáo lịch sử DATA-29 và
   DATA-31. Payload cũ được canonicalize additive sang schema mới.

## Hệ quả và cổng kiểm soát

- Contract runtime/manifest lên template `2.1`, schema `2.1.0`, parser
  `structured-hr/family-layout/2.2.0`; CV và IELTS giữ schema cũ.
- Downstream ưu tiên `role_title` khi cần vị trí công việc; `job_title` có thể
  dùng fallback nghề nghiệp khi tài liệu chỉ có một loại chức danh. Giao diện
  có thể hiển thị cả hai trường để người duyệt đối chiếu.
- Không đổi OCR backend/profile, không thêm ngoại lệ theo tài liệu và không
  mở CAM-001 chỉ vì schema đã đổi. Scan strict gate và DATA-31 gate vẫn là
  điều kiện riêng.
- Cần replay private PDF-001C và kiểm tra Contract 23 không bị mất trường.
  Chỉ lưu aggregate evidence ngoài Git; không ghi PII, OCR text hoặc Ground
  Truth vào repository.
