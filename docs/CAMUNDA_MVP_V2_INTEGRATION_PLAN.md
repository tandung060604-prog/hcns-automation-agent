# Kế hoạch tích hợp Camunda cho đơn nghỉ phép và đơn tăng ca

Trạng thái: `M4_CLOSED_SET_SHADOW_PLAN`.
Task hoàn thành: `M4-CAM-004 DONE`.
Task kế tiếp: `M4-CAM-005 READY`.

Camunda Platform 7.13 và External Task REST API là mục tiêu đã khóa. Worker được
tách theo topic; Camunda tiếp tục sở hữu process state, retry, incident, User
Task và escalation.

## Mục tiêu và baseline

M4 tích hợp end-to-end đúng hai loại tài liệu đã có Template-first, parser,
validator, schema và UAT:

- `LEAVE_REQUEST` — đơn nghỉ phép;
- `OVERTIME_REQUEST` — đơn tăng ca.

Baseline `TF-P2-005` đã xác minh:

| Định dạng | Classification | Required-field exact match | Schema error | Routing |
|---|---:|---:|---:|---|
| DOCX | 10/10 | 90/90 | 0 | Native parser |
| PDF có text | 10/10 | 90/90 | 0 | Native parser |
| Ảnh | 10/10 | 86/90 (95,56%) | 0 | `MANUAL_REVIEW` |
| PDF scan | 10/10 | 82/90 (91,11%) | 0 | `MANUAL_REVIEW` |

Hai mươi tài liệu OCR UAT đều đi `MANUAL_REVIEW`; false `AUTO_CONTINUE` bằng
0. EasyOCR `vi-greedy` là backend mặc định cho Template-first; PaddleOCR là
rollback explicit qua `HCNS_TEMPLATE_OCR_BACKEND=paddle`.

## Phạm vi M4

Trong phạm vi:

- hai loại tài liệu trên ở DOCX, PDF có text, PNG/JPG/JPEG và PDF scan;
- file safety, native/OCR routing, template detection, extraction, validation,
  result store và provenance;
- BPMN/DMN, External Task worker, User Task, correction và re-upload loop;
- mock HRIS update và mock notification;
- local dry-run bằng dữ liệu synthetic/được cấp quyền.

Ngoài phạm vi:

- CCCD, hộ chiếu và mọi `IDENTITY_DOCUMENT`;
- CV, hợp đồng, chứng chỉ, bằng cấp, bảng chấm công, payroll, quyết định nhân sự,
  biên bản bàn giao và `OTHER_HR_DOCUMENT`;
- fallback sang generic IDP khi không khớp closed set;
- production deployment, public endpoint, tự động phê duyệt hoặc HRIS write thật.

Trong toàn bộ M4, `autoContinueEnabled=false`. Mọi nguồn OCR đi Human Review;
nguồn native đạt chất lượng cao cũng đi User Review để kiểm chứng tích hợp. Loại
ngoài closed set phải fail closed và không tạo side effect.

## Luồng và contract

Luồng kỹ thuật:

```text
Submit
→ document_validate_file
→ document_parse_content
→ document_detect_type
→ Confirm Type nếu mismatch/unknown
→ document_extract
→ document_normalize_validate
→ DMN quality routing
→ User Review / HR Review / Re-upload / Auto Continue
```

`document_parse_content` ưu tiên native parser cho PDF text, DOCX, XLSX và PPTX;
chỉ dùng OCR cho ảnh hoặc PDF scan. Raw file, OCR text, extracted field value,
ảnh và workbook không được đưa vào Camunda variables.

Mapping workflow của pilot:

| Kết quả | Hành vi |
|---|---|
| Khai báo và phát hiện đều là `LEAVE_REQUEST` | Tiếp tục extraction |
| Khai báo và phát hiện đều là `OVERTIME_REQUEST` | Tiếp tục extraction |
| Hai loại trên bị mismatch | Tạo Confirm Type User Task |
| Unknown hoặc loại ngoài closed set | Re-upload/reject, không fallback generic |

Process variables chỉ chứa identifier, status, confidence, version và opaque
reference. Whitelist thực thi nằm trong adapter Camunda 7 và được kiểm tra trước
mọi lệnh `complete` hoặc `bpmnError`.

## Quality routing

DMN nhận:

```text
qualityStatus
reviewRequired
sensitiveFieldNeedsReview
missingCriticalField
businessInconsistency
requiredFieldsComplete
overallConfidence
autoContinueEnabled
```

`AUTO_CONTINUE` chỉ hợp lệ khi quality `PASS`, không cần review, không có trường
nhạy cảm cần review, đủ trường, không bất nhất, confidence từ 0,9 và cờ rollout
được bật. Trường nhạy cảm/bất nhất đi `HR_REVIEW`; confidence trung bình đi
`USER_REVIEW`; thiếu trường trọng yếu hoặc confidence dưới 0,6 đi
`REQUEST_REUPLOAD`.

## Worker và lỗi

Camunda 7 adapter hỗ trợ `fetchAndLock`, `complete`, `failure`, `bpmnError` và
`extendLock`. Mỗi handler nhận reference, thực hiện một công việc hữu hạn, lưu
kết quả trước khi complete và dùng idempotency key.

Input nghiệp vụ không hợp lệ phát BPMN Error `DOCUMENT_INPUT_INVALID`. Timeout,
worker crash, model unavailable và storage lỗi tạm thời dùng External Task
failure để Camunda giảm retry và tạo incident.

Trong M4, `hris_update_employee_record` và `hr_notify_processing_result` chỉ dùng
mock handler, không tạo side effect thật. OCR Lab vẫn là công cụ benchmark;
không sở hữu Camunda User Task hoặc review queue.

## Khoảng trống còn lại sau M4-CAM-004

1. Correction hiện chỉ kiểm tra reference; chưa áp dụng payload sửa, ghi audit
   hoặc validation lại.
2. Chưa chạy correction/re-upload loop và reviewer audit end-to-end trên engine.
3. Ma trận dry-run 10 scenario của M4-CAM-006 chưa hoàn tất.

## Kế hoạch task

| ID | Trạng thái | Mục tiêu | Phụ thuộc |
|---|---|---|---|
| M4-CAM-001 | DONE | Khóa closed-set contract và đồng bộ BPMN/schema/test | TF-P2-005 DONE |
| M4-CAM-002 | DONE | Bind Template-first pipeline/result store vào External Task worker | M4-CAM-001 |
| M4-CAM-003 | DONE | Tạo projection đủ DMN input và kiểm thử routing shadow | M4-CAM-002 |
| M4-CAM-004 | DONE | Deploy BPMN/DMN lên Camunda 7.13 local và chạy smoke | M4-CAM-003, môi trường Camunda |
| M4-CAM-005 | READY | Hoàn thiện User Task, correction và re-upload loop | M4-CAM-004 |
| M4-CAM-006 | PLANNED | Chạy ma trận dry-run và quyết định shadow pilot | M4-CAM-005 |

### M4-CAM-001 — Closed-set contract alignment (`DONE`)

Mục tiêu: toàn bộ contract chỉ nhận đúng hai loại trong pilot và không lệch
giữa Python enum, JSON Schema, BPMN form và test.

Acceptance criteria:

- cả ba BPMN form có `LEAVE_REQUEST` và `OVERTIME_REQUEST`;
- test so sánh enum schema với toàn bộ lựa chọn BPMN, không chỉ một giá trị mẫu;
- closed-set guard từ chối loại ngoài hai loại trước extraction;
- `autoContinueEnabled=false` và mock side effects vẫn bị khóa;
- Camunda asset, contract và Template-first tests pass;
- không thay đổi domain enum hoặc đưa Camunda import vào domain/application.

Completion evidence (2026-08-04):

- BPMN `2.2.0-shadow` chỉ hiển thị `LEAVE_REQUEST` và `OVERTIME_REQUEST` ở cả
  ba form submit/confirm/re-upload;
- M4 allowlist là subset được kiểm tra của global workflow-document schema;
- `document_extract` phát `DOCUMENT_INPUT_INVALID` trước khi gọi operation nếu
  workflow type nằm ngoài closed set;
- shadow policy vẫn khóa auto-continue và real side effects;
- validation: 39 targeted tests passed; Ruff, mypy 79 source files, repository
  hygiene và `git diff --check` passed.

### M4-CAM-002 — Worker composition và idempotent result (`DONE`)

Mục tiêu: có entrypoint local tạo REST client, stage handlers, pipeline và
result store bằng dependency injection.

Acceptance criteria:

- sáu topic document đều được bind; thiếu/thừa topic làm startup fail closed;
- endpoint, worker identity và token chỉ lấy từ environment/secret store;
- result được lưu trước `complete`; replay cùng idempotency key dùng reference cũ;
- business error dùng `DOCUMENT_INPUT_INVALID`; technical error dùng failure và
  giảm retry;
- task dài có lock-extension policy kiểm chứng được;
- process variables chỉ chứa reference/scalar, không có raw payload.

Completion evidence (2026-08-04):

- entrypoint `hcns-agent-camunda-worker` tạo REST client, Template-first local
  pipeline, source resolver, private JSON result store và worker qua dependency
  injection;
- cấu hình kết nối chỉ đọc `CAMUNDA_REST_URL`, `CAMUNDA_WORKER_ID` và
  `CAMUNDA_BEARER_TOKEN`; private root chỉ đọc từ
  `HCNS_CAMUNDA_PRIVATE_ROOT` và phải là thư mục tuyệt đối đã tồn tại;
- registry bind đúng sáu document topic; thiếu hoặc thừa operation làm startup
  fail closed;
- `document_parse_content` lưu private result và idempotency index trước
  `complete`; replay cùng key dùng lại `camunda-m4://result/<sha256>` mà không
  chạy pipeline lần hai;
- nguồn sai phát `DOCUMENT_INPUT_INVALID`; lỗi Template/OCR/storage phát
  External Task failure và giảm retry;
- `document_parse_content` gọi `extendLock` lên 180 giây trước stage dài;
- output worker chỉ có scalar/reference; full Template-first payload nằm trong
  private result store. Correction vẫn reference-only; tám biến DMN từng được
  giữ cho M4-CAM-003 và nay đã hoàn thành ở task bên dưới;
- validation: 52 targeted tests passed; Ruff passed; mypy không có lỗi trên 81
  source files; repository hygiene và `git diff --check` passed.

### M4-CAM-003 — Template result tới DMN (`DONE`)

Mục tiêu: chuyển kết quả hai template thành process variables đủ và an toàn cho
DMN mà không làm application phụ thuộc Camunda.

`document_normalize_validate` phải trả đủ:

```text
qualityStatus
reviewRequired
sensitiveFieldNeedsReview
missingCriticalField
businessInconsistency
requiredFieldsComplete
overallConfidence
autoContinueEnabled
```

Acceptance criteria:

- adapter tạo đủ tám input và validate bằng whitelist/schema;
- `MANUAL_REVIEW` không được dùng làm output gateway cuối; DMN chọn
  `USER_REVIEW`, `HR_REVIEW` hoặc `REQUEST_REUPLOAD`;
- mọi nguồn OCR có false `AUTO_CONTINUE` bằng 0;
- missing critical field đi `REQUEST_REUPLOAD`;
- mismatch type tạo Confirm Type User Task;
- không có raw field value trong variables hoặc test report.

Completion evidence (2026-08-04):

- private result lưu projection đúng tám input cùng idempotent result; stage
  `document_normalize_validate` chỉ trả tám scalar và không trả
  `recommendedAction=MANUAL_REVIEW`;
- adapter kiểm tra exact key set, kiểu boolean, enum `qualityStatus`, confidence
  range và process-variable whitelist; regression validate cùng JSON Schema;
- native result hợp lệ có `qualityStatus=PASS` nhưng vẫn đi `USER_REVIEW` do
  `autoContinueEnabled=false`;
- ma trận synthetic `LEAVE_REQUEST`/`OVERTIME_REQUEST` × image/scan PDF đều có
  `autoContinueEnabled=false`, không có false `AUTO_CONTINUE` và đi Human Review;
- thiếu required field đặt `missingCriticalField=true` và đi
  `REQUEST_REUPLOAD`; bất nhất nghiệp vụ đi `HR_REVIEW`;
- declared/detected mismatch trả `classificationStatus=MISMATCH`; BPMN contract
  xác nhận gateway đi Confirm Type User Task;
- DMN output bị khóa trong `AUTO_CONTINUE`, `USER_REVIEW`, `HR_REVIEW` và
  `REQUEST_REUPLOAD`; không có `MANUAL_REVIEW` gateway output;
- validation: 59 targeted tests passed; Ruff passed; mypy không có lỗi trên 81
  source files; repository hygiene và `git diff --check` passed.

### M4-CAM-004 — Local deploy và smoke (`DONE`)

Điều kiện môi trường:

- `CAMUNDA_REST_URL` và `CAMUNDA_WORKER_ID`;
- token/credential ngoài Git nếu môi trường yêu cầu;
- quyền deploy BPMN/DMN vào local engine.

Acceptance criteria:

- BPMN/DMN deploy thành công lên Camunda 7.13;
- tạo được một process instance synthetic cho mỗi loại tài liệu;
- worker fetch, lock, complete và tạo đúng User Task;
- restart worker không mất process state hoặc duplicate result;
- không có HRIS/notification side effect thật.

Completion evidence (2026-08-04):

- Camunda BPM Run local được xác minh đúng `7.13.0`; REST chạy loopback và không
  yêu cầu ghi credential vào Git;
- lần deploy đầu bị engine từ chối do BPMN đặt artifact trước `sequenceFlow`;
  thứ tự XSD được sửa tối thiểu và có regression test;
- deploy sau sửa thành công với đúng một process definition và một decision
  definition;
- đơn nghỉ phép và đơn tăng ca synthetic đều đi qua worker tới
  `UserReview`, có `qualityStatus=PASS`, `recommendedAction=USER_REVIEW` và
  `autoContinueEnabled=false`;
- sau khi dừng worker, User Task/process state vẫn còn. Worker mới xử lý replay
  cùng idempotency key bằng reference cũ; số result file không tăng;
- ba process synthetic hoàn tất; history ghi `hrisUpdateStatus=SIMULATED` và
  `notificationStatus=SIMULATED` cho cả ba, không có side effect thật;
- worker smoke đã dừng sau kiểm tra; Camunda local vẫn chạy để xem
  deployment/history;
- validation: 60 targeted tests passed; Ruff passed; mypy không có lỗi trên 81
  source files; repository hygiene và `git diff --check` passed.

### M4-CAM-005 — Human Review loop

Acceptance criteria:

- reviewer thấy source/result reference, provenance, confidence, validation và
  lý do review;
- hỗ trợ `CONFIRMED`, `CORRECTED`, `REQUEST_REUPLOAD` và
  `UNRESOLVED`/escalation theo BPMN;
- correction chỉ truyền `correctionsReference`, sau đó validation lại;
- approval gắn reviewer ID, timestamp, case version và payload hash;
- quá SLA chỉ escalation, không auto-approve.

### M4-CAM-006 — Dry-run và quyết định pilot

Ma trận tối thiểu:

1. đơn nghỉ phép DOCX hợp lệ;
2. đơn tăng ca DOCX hợp lệ;
3. đơn nghỉ phép ảnh/PDF scan đi User Review;
4. đơn tăng ca ảnh/PDF scan đi User Review;
5. declared/detected type mismatch và Confirm Type;
6. file hỏng/không hỗ trợ;
7. thiếu required field;
8. reviewer correction rồi validation lại;
9. re-upload quá ba lần;
10. technical failure, retry và idempotent replay không duplicate side effect.

## Nghiệm thu

CI phải kiểm tra XML BPMN/DMN, topic contract, mapping enum, variable whitelist,
DMN route, REST payload, retry, BPMN Error, lock extension và idempotent replay.

M4 hoàn thành khi:

- M4-CAM-001..006 đều `DONE`;
- 10/10 dry-run scenario kết thúc ở expected state;
- hai loại tài liệu và bốn định dạng có evidence end-to-end;
- 0 false `AUTO_CONTINUE`;
- 0 raw document/OCR/field value trong Camunda variables và aggregate report;
- 0 duplicate result hoặc mock side effect khi retry;
- incident, BPMN Error và retry được phân biệt đúng;
- không có production side effect, secret hoặc PII trong Git;
- backlog, project state và handoff được cập nhật bằng kết quả thực tế.

Kiểm tra tĩnh trước khi kết nối engine:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
python -m pytest -q tests/test_camunda_contract.py tests/test_camunda_assets.py `
  tests/test_camunda7_adapter.py tests/test_template_first.py
python -m ruff check src tests
python -m mypy src
python scripts/check_repository.py
```

Unit test không gọi network hoặc phụ thuộc Camunda server. Smoke/dry-run chạy
riêng sau khi môi trường được cấp quyền.

Rollout theo thứ tự local dry-run rồi shadow pilot, vẫn chỉ cho hai loại tài
liệu. Việc bật `AUTO_CONTINUE`, thêm loại tài liệu hoặc ghi HRIS thật là M5 riêng,
cần authorization, retention, audit trail, threat model và phê duyệt nghiệp vụ.

## Bước kế tiếp

Chờ phê duyệt `M4-CAM-005`: triển khai correction/re-upload loop, reviewer audit
và validation lại sau correction. Không mở rộng closed set hoặc bật side effect
thật.
