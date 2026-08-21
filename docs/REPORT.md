# Báo cáo smoke dataset — 2026-08-21

**Môi trường:** API `127.0.0.1:8765` (OCR backend paddle), workspace `localhost:3000`  
**Dataset:** `../vinhris-document-ai-dataset-main/data`  
**Luồng test:** `process` → `camunda/start` → HR `preview` / `source`  
**Tài khoản:** `user/user123` nộp · `hr/hr123` xem gốc  
**Raw JSONL:** `tmp/smoke_report_20260821.jsonl`

## Tóm tắt

| Kết quả | Số case |
|---------|---------|
| Process HTTP 200 | **11 / 11** |
| Nhận đúng loại tài liệu | **10 / 11** |
| Nộp HR (`camundaEligible` + start SUBMITTED) | **11 / 11** |
| HR lấy file gốc (`/source` 200) | **11 / 11** |
| Preview inline (ảnh/PDF) | **7 / 7** non-DOCX |
| Preview DOCX | **415** (đúng thiết kế — tải `/source`) |

**Verdict:** MVP đủ dùng cho Leave / OT / CV / Contract / IELTS (JPG) / CCCD.  
**Lỗi cần theo dõi:** `ielts-002.png` bị detect thành `IDENTITY_CARD` (CCCD).

## Mẫu đại diện đã chạy

| Loại | Định dạng | File | Detect | Template | Nộp HR | Preview | Source |
|------|-----------|------|--------|----------|--------|---------|--------|
| Leave | DOCX | `leave-request-001.docx` | LEAVE_REQUEST ✅ | leave-request-v1 | SUBMITTED | 415 (DOCX) | 200 |
| Leave | PDF | `leave-request-002.pdf` | LEAVE_REQUEST ✅ | leave-request-v1 | SUBMITTED | PNG 200 | PDF 200 |
| OT | DOCX | `overtime-request-001.docx` | OVERTIME_REQUEST ✅ | overtime-request-v1 | SUBMITTED | 415 | 200 |
| OT | PDF | `overtime-request-002.pdf` | OVERTIME_REQUEST ✅ | overtime-request-v1 | SUBMITTED | PNG 200 | PDF 200 |
| CV | DOCX | `cv-001.docx` | CV ✅ | cv-v2 | SUBMITTED | 415 | 200 |
| CV | PDF | `cv-016.pdf` | CV ✅ | cv-v2 | SUBMITTED | PNG 200 | PDF 200 |
| Contract | DOCX | `contract-001.docx` | EMPLOYMENT_CONTRACT ✅ | probation-contract-v2 | SUBMITTED | 415 | 200 |
| Contract | PDF | `contract-015.pdf` | EMPLOYMENT_CONTRACT ✅ | probation-contract-v2 | SUBMITTED | PNG 200 | PDF 200 |
| IELTS | JPG | `ielts-001.jpg` | CERTIFICATE ✅ | ielts-certificate-v2 | SUBMITTED | JPEG 200 | 200 |
| IELTS | PNG | `ielts-002.png` | **IDENTITY_CARD ❌** | vietnam-citizen-id-front-v1 | SUBMITTED* | PNG 200 | 200 |
| CCCD | JPG | `cccd-001.jpg` | IDENTITY_CARD ✅ | vietnam-citizen-id-front-v1 | SUBMITTED | JPEG 200 | 200 |

\*Nộp HR vẫn thành công vì `IDENTITY_CARD` đã được bật Camunda; nhưng **sai loại tài liệu**.

## Ghi chú chất lượng extract

| Case | Confidence / action | Missing fields (ví dụ) |
|------|---------------------|-------------------------|
| Leave / OT | 1.0 · AUTO_CONTINUE | formNumber, employeeId, … (template demo thường thiếu) |
| CV | ~0.67 · MANUAL_REVIEW | address |
| Contract | 0.75 · MANUAL_REVIEW | (không thiếu required trong mẫu này) |
| IELTS JPG | ~0.67 · MANUAL_REVIEW | — |
| CCCD JPG | ~0.47 · MANUAL_REVIEW | sex, nationality, placeOfResidence (OCR latin méo chữ VN) |
| IELTS PNG (sai loại) | 0.2 · MANUAL_REVIEW | nhiều field CCCD trống |

## Kết luận theo loại

1. **Leave / OT:** DOCX & PDF ổn; native extract; DOCX xem gốc = tải file.
2. **CV:** DOCX & PDF text ổn; structured-hr; thiếu `address` trên mẫu test.
3. **Contract:** DOCX & PDF ổn; structured-hr.
4. **IELTS:** JPG ổn; **PNG `ielts-002` bị nhầm CCCD** — cần siết anchor / ưu tiên CERTIFICATE khi có “IELTS” / “band score”.
5. **CCCD:** JPG detect + nộp OK; field phụ (giới tính, quốc tịch) còn yếu do OCR.

## Việc nên làm tiếp (từ report này)

1. Fix mis-detect IELTS PNG → CERTIFICATE (không nhận CCCD).
2. Cải thiện OCR/parser CCCD cho sex / nationality / residence.
3. (Tuỳ chọn) smoke thêm 1 IELTS PNG khác sau khi fix.

## Cách tái chạy

```bash
# API phải sẵn sàng; OCR paddle khuyến nghị
# Sau đó chạy lại script smoke tương tự hoặc:
python3 - <<'PY'
# xem tmp/smoke_report_20260821.jsonl
PY
```
