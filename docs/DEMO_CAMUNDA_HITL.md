# Kịch bản quay demo Camunda HITL — làm lại từ đầu

Tài liệu này là checklist điều phối một buổi demo local cho hai loại tài liệu:

- Đơn xin nghỉ phép (`LEAVE_REQUEST`)
- Đơn xin tăng ca (`OVERTIME_REQUEST`)

Mục tiêu là chứng minh một luồng **OCR/template extraction → người nộp kiểm tra →
HCNS quyết định → Camunda điều phối → kết thúc**. File gốc, nội dung OCR và JSON
chi tiết chỉ ở máy local; Camunda chỉ nhận mã tham chiếu.

> Không chạy các case cũ. Mỗi case bắt đầu bằng một file mới trên localhost. Sau mỗi
> checkpoint, dừng lại và gửi ảnh cho người hỗ trợ trước khi thực hiện checkpoint kế tiếp.

## 1. Quy ước quay và ảnh cần gửi

| Mã ảnh | Thời điểm | Màn hình | Cần nhìn thấy | Không cần/không nên hiển thị |
|---|---|---|---|---|
| S0 | Trước khi demo | Dashboard và worker | Dashboard online; worker đang polling | Log dài, dữ liệu tài liệu cũ |
| S1 | Sau trích xuất | Localhost | Loại tài liệu, trạng thái, confidence, nút `Đưa vào Camunda` | Toàn bộ JSON, PII trên preview |
| S2 | Sau đưa vào Camunda | Cockpit Runtime | Instance mới, node `Người nộp xác nhận dữ liệu` đang active | Danh sách biến không cần thiết |
| S3 | Sau quyết định người nộp | Hàng đợi HITL + Cockpit Runtime | Case xuất hiện đúng cột/đúng node tiếp theo | Nội dung OCR chi tiết |
| S4 | Trước quyết định HCNS | Localhost | HCNS kiểm tra local, bản gốc và trường cần rà soát | Toàn bộ JSON hoặc PII |
| S5 | Sau kết thúc | Tasklist hoặc Hàng đợi HITL + Cockpit Dashboard | Task đã hết; `Running Process Instances = 0` | Không tìm màn History trong Cockpit |

**Lưu ý về Cockpit:** Cockpit đang dùng hiển thị runtime. Node active chỉ xuất hiện khi
instance còn chạy. Khi bấm Complete ở bước cuối, instance biến mất khỏi Runtime và số
instance chạy về `0`; đó là bằng chứng case đã kết thúc, không phải lỗi.

## 2. Chuẩn bị sạch trước khi bắt đầu

1. Mở Camunda, dashboard local và một worker External Task.
2. Mở ba tab: **Localhost**, **Camunda Tasklist**, **Camunda Cockpit**.
3. Đảm bảo Tasklist không có task từ lần demo trước. Nếu còn, chỉ xoá/hoàn tất các
   case demo mà bạn tạo; không tác động vào dữ liệu khác.
4. Trên Cockpit, chọn process **HR Document Processing and Onboarding Agent MVP V2**
   và để sẵn trang Runtime.
5. Chụp **S0**: dashboard online và cửa sổ worker đang chạy.

Điểm dừng: gửi S0. Chỉ tiếp tục khi dashboard và worker đều hoạt động.

## 3. Case A — Leave Request đi qua hai vai trò HITL

Đây là case chính để quay video/report vì thấy đầy đủ Người nộp → HCNS.

### A1. Tạo và trích xuất tài liệu

1. Trên localhost, chọn một file mới trong bộ `Leave_Request` đã được phê duyệt cho demo.
2. Bấm **Trích xuất tài liệu**.
3. Kiểm tra hệ thống nhận `LEAVE_REQUEST`, trạng thái thành công và các trường hiển thị hợp lý.
4. Che hoặc không quay các vùng chứa thông tin cá nhân khi cần.
5. Chụp **S1-A**.

Điểm dừng: gửi S1-A.

### A2. Khởi tạo workflow

1. Cuộn xuống cuối khung kết quả local.
2. Bấm **Đưa vào Camunda** một lần và chờ phản hồi thành công.
3. Chuyển sang Cockpit Runtime, refresh nếu cần, mở instance mới nhất.
4. Xác nhận node **Người nộp xác nhận dữ liệu** đang active.
5. Chụp **S2-A**: sơ đồ BPMN có node active. Có thể chụp phần biến điều phối, nhưng không
   cần mở giá trị tham chiếu hoặc dữ liệu cá nhân.

Điểm dừng: gửi S2-A. Không Complete task trước khi đã chụp ảnh này.

### A3. Người nộp chuyển case sang HCNS

1. Trở lại localhost, mở **Hàng đợi HITL**.
2. Trong cột **Nhân viên / người nộp**, bấm **Kiểm tra local** để đối chiếu bản gốc và kết quả.
3. Chọn **Chuyển HCNS**. Đây tương ứng với quyết định `UNRESOLVED`, không nói rằng OCR sai;
   nó chỉ yêu cầu HCNS kiểm tra độc lập.
4. Chờ worker hoàn thành bước audit, sau đó refresh Hàng đợi HITL và Cockpit Runtime.
5. Chụp **S3-A**: case xuất hiện ở cột HCNS và node **HCNS kiểm tra dữ liệu** active.

Điểm dừng: gửi S3-A.

### A4. HCNS kiểm tra và chấp nhận

1. Trong cột **HCNS**, bấm **Kiểm tra local**.
2. Đối chiếu bản gốc với các trường; chỉ quay những vùng được phép hiển thị.
3. Bấm **Chấp nhận** (`CONFIRMED`).
4. Đợi worker chạy audit, cập nhật mô phỏng và thông báo mô phỏng.
5. Refresh Tasklist/Hàng đợi HITL: task của case phải biến mất.
6. Refresh Cockpit Dashboard hoặc Runtime: số instance đang chạy về `0` khi không còn case nào khác.
7. Chụp **S4-A** (màn kiểm tra HCNS, trước khi chấp nhận) và **S5-A** (case đã kết thúc).

Kết quả cần ghi vào report: Leave Request đã đi qua **hai điểm HITL**, và các bước cập nhật/
thông báo chỉ là mô phỏng local, không ghi vào HRIS thật hoặc gửi email thật.

## 4. Case B — Overtime Request, nhánh xác nhận nhanh

Case này chứng minh workflow không bắt buộc chuyển HCNS khi người nộp xác nhận kết quả.

1. Lặp lại A1 và A2 nhưng chọn một file mới trong `Overtime_Request`.
2. Chụp **S1-B** và **S2-B** khi node `Người nộp xác nhận dữ liệu` đang active.
3. Tại Hàng đợi HITL, người nộp bấm **Xác nhận chính xác** (`CONFIRMED`).
4. Chờ worker và refresh Cockpit.
5. Xác nhận không xuất hiện task HCNS cho case này; case đi tới kết thúc.
6. Chụp **S5-B**: hàng đợi không còn task của case và Cockpit không còn instance chạy.

Kết quả cần ghi: Overtime Request đã hoàn thành theo nhánh nhanh, không có HRReview vì người
nộp đã xác nhận kết quả.

## 5. Case C — Overtime Request, yêu cầu tải lại (tuỳ chọn)

Chỉ chạy case này sau A và B. Nó dài hơn vì màn tải lại trên dashboard chưa gắn trực tiếp với
task `UploadAgain`; thao tác hoàn thành `UploadAgain` thực hiện trong Camunda Tasklist.

1. Tạo Overtime Request mới; Người nộp chọn **Chuyển HCNS**.
2. Tại HCNS, chọn **Yêu cầu tải lại** (`REQUEST_REUPLOAD`).
3. Chụp Cockpit khi task **Tải lại tài liệu** active.
4. Tạo/trích xuất một Overtime Request mới trên localhost để lấy một tham chiếu local mới.
5. Trong Tasklist, claim task `Tải lại tài liệu`, nhập mã tham chiếu mới và loại
   `OVERTIME_REQUEST`, sau đó Complete.
6. Khi quay lại `Người nộp xác nhận dữ liệu`, chọn **Xác nhận chính xác** để kết thúc.

Không dùng Case C trong video ngắn nếu chưa cần trình bày chức năng tải lại.

## 6. Checklist bàn giao từng checkpoint

Khi đến mỗi điểm dừng, gửi đúng ba thông tin sau:

```text
Case: A / B / C
Checkpoint: S0 / S1 / S2 / S3 / S4 / S5
Ảnh: đính kèm ảnh chụp màn hình
```

Người hỗ trợ sẽ trả lời theo mẫu:

```text
Đã kiểm tra: đạt / cần làm lại
Bằng chứng đã thấy: ...
Bước tiếp theo duy nhất: ...
Ảnh tiếp theo cần gửi: ...
```

Không bấm Complete khi chưa nhận bàn giao checkpoint hiện tại. Điều này giúp giữ node active
để Cockpit có thể hiển thị luồng di chuyển và tránh mất bằng chứng runtime.

## 7. Bảng tổng kết report sau buổi demo

| Case | Loại tài liệu | Quyết định người nộp | Quyết định HCNS | Bằng chứng chính | Trạng thái |
|---|---|---|---|---|---|
| A | Leave Request | Chuyển HCNS | Chấp nhận | S1-A đến S5-A | Điền sau demo |
| B | Overtime Request | Xác nhận chính xác | Không áp dụng | S1-B, S2-B, S5-B | Điền sau demo |
| C | Overtime Request | Chuyển HCNS | Yêu cầu tải lại | Ảnh task UploadAgain | Tuỳ chọn |

## 8. Sự cố thường gặp

| Hiện tượng | Kiểm tra trước tiên |
|---|---|
| Localhost không vào được | Dashboard local còn chạy và port 3000 còn lắng nghe |
| Bấm đưa vào Camunda nhưng không có task | Worker còn chạy; sau đó refresh Hàng đợi HITL/Tasklist |
| Task biến mất sau Complete | Bình thường: refresh Cockpit để xem node tiếp theo hoặc số instance chạy |
| Cockpit không thấy case đã Complete | Bình thường: trang Runtime chỉ hiển thị case đang chạy; dùng S5 làm bằng chứng kết thúc |
| Hàng đợi có case cũ | Không dùng lại case cũ; tạo case mới và xác nhận mã tham chiếu mới |

## 9. Mốc bắt đầu lại

Buổi demo mới luôn bắt đầu tại **S0**. Sau khi gửi S0, nhiệm vụ bàn giao đầu tiên là **A1 — tạo
và trích xuất một Leave Request mới**. Không cần chạy lại benchmark hay thay đổi parser trong
buổi quay demo.
