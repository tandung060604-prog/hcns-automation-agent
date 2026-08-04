# M5-CAM-001 — Shadow pilot authorization và runbook

Trạng thái: `READY`.

M5 được mở theo xác nhận của người dùng trong session hiện tại. Đây là
authorization để chuẩn bị và chạy **shadow pilot có kiểm soát**, chưa phải
production approval và chưa bật side effect thật.

## Mục tiêu

Xác nhận vận hành giới hạn của Camunda 7.13 cho đúng hai loại tài liệu:

- `LEAVE_REQUEST` — đơn nghỉ phép;
- `OVERTIME_REQUEST` — đơn tăng ca.

Pilot kế thừa closed set và safety policy của M4:

- native DOCX/PDF và ảnh/PDF scan được xử lý bởi Template-first;
- OCR luôn Human Review; native high-confidence vẫn `USER_REVIEW` trong shadow;
- `autoContinueEnabled=false`;
- HRIS update và notification chỉ `SIMULATED`;
- Camunda variables chỉ chứa status, confidence, version và opaque reference;
- không mở CCCD, bảng chấm công, loại tài liệu mới hoặc generic-IDP fallback.

## Điều kiện phải chốt trước khi chạy

| Gate | Chủ sở hữu | Bằng chứng bắt buộc |
|---|---|---|
| Business scope | Người phê duyệt nghiệp vụ | cohort, reviewer HCNS và thời gian pilot |
| Environment | Kỹ thuật | Camunda 7.13 local/isolated, worker health check |
| Safety policy | Kỹ thuật + nghiệp vụ | `AUTO_CONTINUE=false`, side effect giả lập, whitelist pass |
| Privacy/retention | Người phê duyệt rủi ro | retention, quyền truy cập private store, xóa sau pilot |
| Rollback | Vận hành | trigger, người có quyền dừng worker và cách giữ process state |

Các ô chưa có người hoặc thời gian cụ thể là **blocker trước execution**, không
được tự suy đoán trong repository.

## Preflight

Chạy từ repository root, dùng Python runtime/dependency profile đã được xác nhận:

```powershell
$env:PYTHONPATH = "C:\tmp\hcns-m4-cam-005-deps;$(Resolve-Path 'src');$(Resolve-Path 'tests')"
python -m pytest -q tests/test_camunda_contract.py tests/test_camunda_assets.py `
  tests/test_camunda7_adapter.py tests/test_camunda7_runtime.py tests/test_camunda_m4_dry_run.py
python -m ruff check src tests
python -m mypy --no-incremental --no-sqlite-cache --cache-dir C:/tmp/hcns-m5-mypy src
python scripts/check_repository.py
python scripts/run_camunda_m4_dry_run.py
```

Preflight chỉ được coi là đạt khi toàn bộ scenario synthetic pass và aggregate
report vẫn có `falseAutoContinue=0`, `duplicateResultArtifacts=0`,
`realSideEffectsEnabled=false` và `containsRawFieldValues=false`.

## Cách chạy shadow pilot

1. Người phê duyệt ghi nhận cohort/reviewer/time window ngoài Git; không đưa
   tên nhân viên, raw OCR, file upload hoặc credential vào repository.
2. Kỹ thuật xác nhận engine và worker đang trỏ tới local/isolated runtime,
   private source/result root hợp lệ và không bật connector HRIS thật.
3. Chạy preflight ở trên; nếu fail thì dừng, không nạp cohort.
4. Nạp cohort đã được cấp quyền qua intake hiện có. Mỗi case phải có opaque
   `applicationId`/`idempotencyKey`; worker complete sau khi private result đã
   được lưu.
5. Theo dõi aggregate-only: số case theo routing, BPMN Error, retry, incident,
   re-upload, audit và duplicate result. Không export field value hoặc raw OCR.
6. Kết thúc time window bằng closeout report; đối chiếu số case nhận vào với
   số case hoàn tất/review/re-upload/incident và lưu evidence private ngoài Git.

## Trigger dừng và rollback

Dừng nạp case mới và dừng worker nếu có một trong các điều kiện:

- bất kỳ `AUTO_CONTINUE` nào trong shadow;
- process variable chứa raw file/OCR/field value hoặc reference ngoài whitelist;
- HRIS/notification chuyển khỏi `SIMULATED`;
- duplicate result/audit hoặc idempotency mismatch;
- incident/retry tăng bất thường hoặc private store không còn khả dụng;
- reviewer không thể truy cập User Task hoặc audit không gắn được reviewer/version/hash.

Rollback là thao tác vận hành có thể đảo ngược: dừng worker, giữ process state để
điều tra, khóa intake pilot và quay về preflight trước khi chạy lại. Không xóa
process history hoặc private evidence trước khi hoàn tất retention/incident review.

## Acceptance criteria M5-CAM-001

- Business owner xác nhận scope, cohort, reviewer, time window và retention.
- Local/isolated Camunda 7.13 và worker health check pass.
- Preflight M4 và dry-run 10 scenario pass lại trước cohort.
- Trong pilot: `AUTO_CONTINUE=0`, real side effect `0`, raw value exposure `0`,
  duplicate result `0` và mọi lỗi kỹ thuật phân biệt được với BPMN Error.
- Closeout report aggregate-only, có incident/rollback decision và evidence
  private ở ngoài Git.
- Mọi thay đổi sang production/public endpoint, auto-approval, loại tài liệu
  mới hoặc HRIS write thật được tách thành authorization M5 riêng.

## Trạng thái hiện tại và bước kế tiếp

M5-CAM-001 đã được mở `READY`; chưa chạy cohort thật. Bước kế tiếp là người
phê duyệt điền các điều kiện Business scope/Privacy/Retention/Rollback ở trên,
sau đó mới cho phép execution theo runbook.
