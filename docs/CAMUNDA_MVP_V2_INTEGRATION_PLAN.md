# Kế hoạch tích hợp HCNS IDP với Camunda MVP V2

Trạng thái: `M4_SHADOW_SCAFFOLDING`.

Tiến độ ước tính trước khi triển khai scaffolding là 46% cho một pilot
end-to-end. Camunda Platform 7.13 và External Task REST API là mục tiêu đã khóa.
Worker được tách theo topic; Camunda tiếp tục sở hữu process state, retry,
incident, User Task và escalation.

## Điều kiện mở controlled pilot

M4 chỉ được chuyển từ shadow sang controlled pilot sau khi OCR Phase 14.6 đạt:

- ít nhất 15 tài liệu held-out mới có quyền sử dụng;
- model, crop profile, metric spec và `RecognitionPolicy` được khóa SHA-256;
- candidate không làm mất dòng primary vốn đúng;
- Exact Match và DER không suy giảm;
- sensitive-field false acceptance bằng 0;
- Ground Truth được xác nhận trước khi mở prediction;
- không chỉnh threshold, crop hoặc policy trên held-out.

Khi các điều kiện này chưa đạt, `autoContinueEnabled` phải giữ `false`; mọi hồ
sơ đủ điều kiện tự động trên lý thuyết vẫn chuyển `USER_REVIEW`.

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

Mapping workflow:

| Domain `DocumentType` | Camunda workflow type |
|---|---|
| `IDENTITY_CARD`, `PASSPORT` | `IDENTITY_DOCUMENT` |
| `EMPLOYEE_PROFILE` | `EMPLOYEE_INFORMATION_FORM` |
| `EMPLOYMENT_CONTRACT`, `CONTRACT_APPENDIX` | `EMPLOYMENT_CONTRACT` |
| `CV` | `CV` |
| `DEGREE`, `CERTIFICATE`, `HR_DECISION`, `LEAVE_REQUEST`, `TIMESHEET` | giữ nguyên |
| loại chưa hỗ trợ | `OTHER_HR_DOCUMENT` và bắt buộc review |

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

## Nghiệm thu

CI phải kiểm tra XML BPMN/DMN, topic contract, mapping enum, variable whitelist,
DMN route, REST payload, retry, BPMN Error, lock extension và idempotent replay.

Dry-run Camunda 7.13 phải bao phủ: hồ sơ auto đủ điều kiện, trường nhạy cảm,
confidence trung bình, thiếu trường trọng yếu, mismatch loại tài liệu, file
hỏng, lỗi kỹ thuật, correction loop, quá ba lượt upload và retry không tạo
duplicate side effect.

Endpoint, credential và worker identity chỉ lấy từ environment/secret store.
Rollout theo thứ tự local dry-run, shadow pilot rồi controlled pilot. M5 chỉ bắt
đầu sau authorization, retention, audit trail, reviewer identity, payload hash
và kiểm thử side effect idempotent.
