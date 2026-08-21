# MVP document parity — task list

Scope: CV · Contract · IELTS · Leave · OT · CCCD  
Data: `vinhris-document-ai-dataset-main/data`  
Goal: cùng pipeline (scan → form → nộp HR → xem gốc → duyệt); khác nhau chỉ OCR vs extract native.

## Audit (2026-08-21)

| Loại | Dataset | Scan | Nộp HR | Xem gốc | Ghi chú |
|------|---------|------|--------|---------|---------|
| Leave DOCX/PDF | leave_request | OK | OK | source DOCX / preview PDF | Native extract |
| OT DOCX/PDF | overtime_request | OK | OK | OK | Native extract |
| CV DOCX/PDF text | cvs | OK | OK | OK | Structured-hr |
| CV PDF scan (raster) | tmp/cv-016-scan.pdf | OK | OK | OK | OCR path |
| Contract DOCX/PDF | contracts | OK | OK | source DOCX / preview PDF | Structured-hr |
| IELTS JPG/PNG | ielts | OK | OK | preview image | OCR |
| CCCD JPG | cccd | OK | OK | preview image | OCR + parser mới |

## Tasks

1. [x] **CCCD detect + submit** — anchors OCR-robust, `CitizenIdFrontParser`, `IDENTITY_CARD` vào Camunda upload + label VN
2. [x] **Xem tài liệu gốc** — preview ảnh/PDF; DOCX → tải source; archive fallback cho HR; Content-Type ổn định
3. [x] **CV PDF OCR** — PDF text & PDF scan (raster) process OK với paddle
4. [x] **Parity UX** — copy upload nhắc CCCD; field labels CCCD; cùng flow HR
5. [x] **Smoke dataset** — leave/OT/CV/contract/IELTS/CCCD: process → start → HR preview/source

## Notes

- OCR CCCD dùng latin recognizer → chữ VN méo; detect dựa fuzzy + variant anchors.
- DOCX không xem inline trên browser (415 preview) — UI tải file gốc.
- API cần restart sau đổi registry/parser (`HCNS_TEMPLATE_OCR_BACKEND=paddle`).
