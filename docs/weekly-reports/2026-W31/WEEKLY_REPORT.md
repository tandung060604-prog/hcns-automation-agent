# Weekly Product Report - 2026-W31

## Tóm tắt điều hành

HCNS Automation Agent đã có luồng Template-first local cho hai biểu mẫu hành chính nhân sự: đơn nghỉ phép và đơn tăng ca. Hệ thống nhận DOCX, PDF và ảnh scan, ưu tiên native parsing khi có text layer, sau đó trả JSON có provenance và quality routing.

Trong tuần này, multi-format intake và preview được tích hợp vào UI local. Đường native đạt 100% trên bộ regression được phê duyệt. Đường OCR ảnh/scan chưa đạt gate, vì vậy mọi kết quả OCR tiếp tục bắt buộc `MANUAL_REVIEW`.

## Tình trạng theo quyết định

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Native DOCX cho hai template | Sẵn sàng local | 10/10 phân loại, 90/90 field required |
| Native PDF | Sẵn sàng local | 10/10 phân loại, 90/90 field required |
| Ảnh camera và PDF scan | Shadow review | 6/6 xử lý và phân loại, 31/54 field required |
| Auto routing cho OCR | Không mở | 0 false `AUTO_CONTINUE` |
| UI intake một điểm | Sẵn sàng local | DOCX, PDF, PNG, JPG/JPEG; preview cạnh JSON |
| Camunda/HRIS production | Chưa triển khai | Không có API call hay process instance production |

## Evidence cho hai biểu mẫu HCNS

| Loại tài liệu | Path xử lý | Kết quả đã xác minh | Quyết định |
|---|---|---:|---|
| Đơn nghỉ phép DOCX | Native parser | Required field exact-match đầy đủ trong regression native | `AUTO_CONTINUE` theo policy template |
| Đơn nghỉ phép PDF | Native parser | Required field exact-match đầy đủ trong regression native | `AUTO_CONTINUE` theo policy template |
| Đơn nghỉ phép ảnh | PaddleOCR local | Thuộc tập 31/54 field exact-match của sáu ảnh | `MANUAL_REVIEW` |
| Đơn tăng ca DOCX | Native parser | Required field exact-match đầy đủ trong regression native | `AUTO_CONTINUE` theo policy template |
| Đơn tăng ca PDF | Native parser | Required field exact-match đầy đủ trong regression native | `AUTO_CONTINUE` theo policy template |
| Đơn tăng ca ảnh | PaddleOCR local | Thuộc tập 31/54 field exact-match của sáu ảnh | `MANUAL_REVIEW` |

Report không kèm tài liệu gốc hoặc JSON có dữ liệu cá nhân. Những artifact nguồn chỉ tồn tại trong vùng local/private được cấp quyền.

## CCCD: mẫu evidence đã khử định danh

Selection gồm 4 mẫu trong 30 session review-complete. Ranking được tạo bằng script tái lập, ưu tiên review hoàn tất, OCR thành công, Phase 11 hiện diện, confidence thao tác và phạt nhẹ cho latency. ID mẫu là SHA-256 rút gọn của session ID; không lưu tên file hoặc nội dung.

Xem [selection.json](assets/cccd/selection.json) để kiểm tra ranking và privacy declaration.

## Trạng thái sản phẩm và UX

Hai screenshot an toàn thể hiện website local không chứa tài liệu hay dữ liệu cá nhân:

![Local product overview](assets/website/local-product.png)

![Unified document intake](assets/website/local-overview.png)

Giao diện hiện có một điểm upload mặc định, hiển thị preview ảnh/PDF và structured result cạnh nhau. Legacy OCR/IDP được giữ sau feature flag và không phải luồng mặc định.

## Rủi ro và kiểm soát

| Rủi ro | Kiểm soát đang áp dụng | Hành động tiếp theo |
|---|---|---|
| Mất dấu tiếng Việt, layout khó trên scan | `MANUAL_REVIEW`, không auto-fill trường thiếu | TF-P2-002A: field-level error classification và ROI recovery trên development-only |
| Overfit theo held-out | Evaluate-once và policy lock | Tạo held-out v2 độc lập sau khi khóa candidate mới |
| Lộ dữ liệu nhạy cảm | Local-only, private-data, report aggregate | Duy trì redaction validation trước mỗi report |
| Drift manifest multi-format | Đã ghi nhận mismatch 30 khai báo/26 file | Sửa manifest và stale reference trong task riêng |
| Sai phạm vi triển khai | API bind loopback, chưa có HRIS write | Railway deployment và external integration cần smoke-test/phê duyệt riêng |

## Đề xuất tuần kế tiếp

1. Tiếp tục TF-P2-002A, đo lỗi theo từng trường trên bộ development ảnh/scan; không dùng Ground Truth lúc inference.
2. Chỉ thử ROI/anchor recovery có provenance, giữ mọi kết quả chưa chắc ở `MANUAL_REVIEW`.
3. Chạy lại gate multi-format. Chỉ xem xét promotion khi OCR field exact-match đạt ít nhất 44/54 và không làm mất trường đúng.
4. Khi chuẩn bị Railway, bổ sung cấu hình deployment và chạy smoke-test với health, upload, source retention và session deletion.

## Khả năng tái lập

```powershell
python scripts/build_weekly_report_cccd_selection.py `
  --data-root <authorized-private-data-root> `
  --output docs/weekly-reports/2026-W31/assets/cccd/selection.json `
  --limit 4
python scripts/validate_weekly_report.py
```

Audit chi tiết: [AUDIT_NOTES.md](AUDIT_NOTES.md). Danh mục artifact: [EVIDENCE_MANIFEST.json](EVIDENCE_MANIFEST.json).
