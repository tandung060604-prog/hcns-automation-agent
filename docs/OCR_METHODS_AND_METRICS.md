# Tổng hợp phương pháp OCR và metric

> Tài liệu này tổng hợp những phương pháp đọc tài liệu, nhận dạng chữ và hậu xử lý
> OCR đã được chạy trong dự án từ các phase đầu đến checkpoint hiện tại.

- Cập nhật: **03/08/2026**.
- Nguồn số liệu: các report aggregate và checkpoint trong repository.
- Raw document, raw OCR text, Ground Truth và model weights nằm ngoài Git.
- Các số liệu có dataset khác nhau không được xếp hạng trực tiếp với nhau.

## Kết luận hiện tại

| Phạm vi | Phương pháp đang dùng | Quyết định |
|---|---|---|
| DOCX/PDF có lớp chữ | Native parser, không gọi OCR | Mặc định cho Template-first |
| Ảnh/PDF scan của hai biểu mẫu MVP | EasyOCR `vi-greedy` + parser theo template | Backend mặc định sau UAT `TF-P2-005` |
| Rollback Template-first | PaddleOCR `PP-OCRv5` | Chỉ bật explicit để chẩn đoán/đối chiếu |
| Pipeline OCR tổng quát/CCCD cũ | Paddle detector + EasyOCR/VietOCR + consensus/review | Giữ ở legacy hoặc shadow review |
| CCCD held-out | Phase 11.5/11.6 với nhiều recognizer và review gate | Chưa promote; `SHADOW_REVIEW_ONLY` |

EasyOCR không được chọn vì một giả định chung rằng nó luôn tốt hơn VietOCR. Nó được
chọn vì là backend có bằng chứng end-to-end phù hợp nhất cho **đúng hai template và
bốn định dạng của MVP**. VietOCR vẫn được giữ trong các pipeline cũ, benchmark và
CCCD để so sánh hoặc review.

## Cách đọc các metric

| Metric | Ý nghĩa | Tốt hơn khi |
|---|---|---|
| Exact Match (EM) | Toàn bộ chuỗi/trường khớp đúng sau chuẩn hóa cho phép | Cao hơn |
| Field Exact Match | Tỷ lệ trường nghiệp vụ khớp đúng | Cao hơn |
| CER | Tỷ lệ lỗi theo ký tự, gồm thêm/xóa/đổi ký tự | Thấp hơn |
| WER | Tỷ lệ lỗi theo từ | Thấp hơn |
| DER | Tỷ lệ lỗi liên quan đến dấu tiếng Việt | Thấp hơn |
| Field Presence/Completeness | Tỷ lệ trường có giá trị hoặc đủ dữ liệu | Cao hơn |
| Accepted Precision | Trong các giá trị được hệ thống chấp nhận, bao nhiêu giá trị đúng | Cao hơn |
| p95 latency | 95% lần chạy nhanh hơn hoặc bằng thời gian này | Thấp hơn |
| False `AUTO_CONTINUE` | OCR chưa chắc chắn nhưng vẫn tự động đi tiếp | Bằng 0 |

Có ba loại kết quả thường bị nhầm:

- **Line/crop recognition**: chấm một dòng hoặc một vùng ảnh đã cắt.
- **Document OCR**: chấm cả tài liệu nhiều trường.
- **Template field extraction**: chấm field nghiệp vụ sau OCR, parser và validation.

Vì vậy, ví dụ `82,92% Exact Match` trên 240 crop dòng không thể so trực tiếp với
`82/90 required fields` trên bộ UAT Template-first. Metric của Phase 14.6 trở đi dùng
`vi-ocr-metrics/1.0.0`; report cũ dùng mẫu số DER khác phải xem là legacy.

## 1. Kiến trúc OCR và các kỹ thuật dùng chung

OCR chỉ là một nhánh trong pipeline. Đường đi thực tế là:

```text
File đầu vào
  → kiểm tra MIME, magic bytes, kích thước, trang và an toàn archive
  → DOCX/PDF có chữ: native parser
  → ảnh/PDF scan: tiền xử lý + detector/recognizer OCR
  → chuẩn hóa field + lưu provenance
  → schema validation + quality gate
  → JSON kết quả hoặc human review
```

### Native parsing trước OCR

- PDF có text dùng PyMuPDF để đọc text, page và bounding box.
- DOCX đọc OOXML để giữ paragraph, list, table và metadata.
- XLSX đọc sheet/cell/formula bằng parser native; không OCR.
- Chỉ ảnh và PDF scan mới gọi `OcrEngine`.

Native parsing không có metric OCR vì nó không nhận dạng ảnh. Trong UAT
Template-first, DOCX và PDF native đều đạt `10/10 classification`, `90/90 required
fields` và `0 schema error`.

### Tiền xử lý, detector và hậu xử lý

| Kỹ thuật | Vai trò thực tế | Metric riêng |
|---|---|---|
| Rectify perspective | Sửa ảnh chụp bị nghiêng trước khi đọc | Không tách riêng; nằm trong metric end-to-end |
| Local contrast | Tăng khả năng đọc ảnh chụp/scan | Không tách riêng |
| Paddle text detector | Tạo box dòng và geometry evidence | Ở nhiều phase chỉ dùng làm detector, không phải text cuối |
| Template ROI | Chỉ lấy vùng dự kiến của từng trường | Được kiểm chứng trong các phase Template-first/CCCD |
| Geometry-aware line grouping | Gom các dòng cùng hàng, loại duplicate/box lồng nhau | Đóng góp vào rerun `48/54` và `45/54` của TF-P2-002B |
| Label/continuation parsing | Đọc giá trị sau nhãn và nối dòng tiếp theo | Đóng góp vào recovery, không dùng Ground Truth để điền |
| Vocabulary/artifact repair | Sửa lỗi OCR hình thức một cách bảo thủ | Không được tự thêm dấu hoặc giá trị không có bằng chứng |
| Field-level provenance | Lưu field lấy từ trang/box/crop/model nào | Bắt buộc cho review, không phải accuracy |
| Consensus và quality gate | Chỉ chấp nhận khi đủ bằng chứng; còn lại `needs_review` | OCR source hiện luôn `MANUAL_REVIEW` trong Template-first |

Các kỹ thuật trên không phải những OCR engine mới. Chúng là lớp tiền xử lý, chọn vùng,
chuẩn hóa và kiểm soát rủi ro đặt quanh recognizer.

## 2. Phase 11.5/11.6 — CCCD, nhiều recognizer và consensus

Pipeline CCCD chuyên biệt dùng tám ROI mặt trước. Bốn recognizer chạy trên các biến thể
crop:

1. PaddleOCR PP-OCRv5;
2. EasyOCR `vi`;
3. VietOCR `vgg_seq2seq`;
4. VietOCR `vgg_transformer`.

Một field chỉ được `accepted` khi có exact consensus từ ít nhất hai họ recognizer độc
lập và qua validation. Đồng thuận chỉ sau khi bỏ dấu vẫn phải `needs_review`; chuỗi
ASCII không thay thế giá trị Unicode pháp lý.

### Kết quả development Phase 11.5 và replay Phase 11.6

| Metric | Phase 11.5 | Phase 11.6 |
|---|---:|---:|
| Strict Field Exact Match | 60,00% | 60,00% |
| ASCII Field Exact Match | 61,67% | 61,67% |
| CER | 43,60% | 43,60% |
| Base CER | 41,87% | 41,87% |
| DER | 12,65% | 12,65% |
| Character Omission Rate | 2,50% | 2,50% |
| Field Presence | 95,83% | 95,83% |
| Accepted Precision | 100,00% | 100,00% |
| Mean duration/document | 250,7 giây | 56,4 giây |

Phase 11.6 bảo vệ được baseline nhưng không tăng exact match. `fullName` ASCII EM chỉ
đạt 73,33%, còn address ASCII EM 3,33%; policy vì vậy vẫn là `SHADOW_REVIEW_ONLY`.
Decoder EasyOCR `greedy` được giữ thay cho `beamsearch` vì beamsearch từng treo ở một
crop địa chỉ lớn trong development.

> Lưu ý: mean duration/document ở bảng trên là metric vận hành của từng replay scope;
> không nên dùng nó như phép so sánh tốc độ thuần giữa hai recognizer.

## 3. Phase 13.2 — recognition-only trên crop dòng synthetic

Corpus gồm **240 crop dòng**, trong đó 204 dòng có ký tự Việt mở rộng. Đây là phép thử
recognizer trên crop đã có sẵn, chưa phải pipeline tài liệu hoàn chỉnh và chưa phải
bằng chứng production.

| Recognizer | Exact Match | CER | DER | Accepted Precision | p95 |
|---|---:|---:|---:|---:|---:|
| EasyOCR 1.7.2 `vi` greedy | 82,92% | 0,89% | 0,00% | 100,00% | 187,7 ms |
| VietOCR 0.3.13 `vgg_seq2seq` | 72,50% | 3,67% | 3,01% | 0,00%* | 178,1 ms |
| PaddleOCR 3.7.0 Latin v5 | 19,58% | 12,51% | 7,87% | 17,74% | 161,4 ms |

`*` VietOCR không có prediction nào vượt confidence threshold `0,95`; confidence giữa
các engine chưa calibration nên không được so trực tiếp. Quyết định lúc đó là chọn
EasyOCR cho pilot recognition và dùng VietOCR làm recognizer kiểm chứng. Hai engine
đồng thuận 143/240 dòng; nhóm đồng thuận đạt precision 100% trên corpus này.

## 4. Phase 13.3 — hybrid OCR trên 15 CCCD scan thật

Pipeline lúc này là **PaddleOCR tạo box → EasyOCR đọc candidate chính → VietOCR
`vgg_seq2seq` kiểm chứng**. Khi hai chuỗi bất đồng, giữ candidate EasyOCR nhưng bắt buộc
review; VietOCR không được âm thầm thay text.

| Metric | Phase 9 reviewed reference | Phase 13.3 hybrid |
|---|---:|---:|
| Document CER | 0,00% | 68,74% |
| Document WER | 0,00% | 127,69% |
| Document Exact Match | 100,00% | 0,00% |
| Crop đồng thuận | — | 18/671 (2,68%) |

Phase 9 là reference đã được người dùng hiệu chỉnh trong session, không phải raw
recognizer baseline. Kết quả hybrid không tái lập được kết quả synthetic nên
`NOT_PROMOTED`; 653/671 crop phải review.

## 5. Phase 14 — VietOCR primary và fallback review-only

Sau khi có Ground Truth cấp crop cho 77 dòng của bốn tài liệu, thứ hạng thay đổi:

| Candidate trên 77 crop | Exact Match | CER | WER | DER |
|---|---:|---:|---:|---:|
| Paddle raw | 25,97% | 28,39% | 63,56% | 3,20% |
| EasyOCR best crop | 7,79% | 41,49% | — | 4,74% |
| VietOCR `vgg_seq2seq` | 42,86% | 15,59% | 32,20% | 0,77% |

VietOCR `vgg_seq2seq` được chọn làm primary cho controlled pilot trên crop
`bbox_balanced_64`, nhưng chỉ là `PROMOTE_TO_CONTROLLED_PILOT`, không phải production.
Trên 51 session chưa có Ground Truth đầy đủ, primary/verifier chỉ có 188/2.150 dòng
đồng thuận (`8,74%` coverage); đây không phải accuracy.

### Benchmark mù 309 crop / 15 tài liệu

| Profile | Exact Match | CER | WER | DER | p95 |
|---|---:|---:|---:|---:|---:|
| VietOCR `vgg_seq2seq` | 30,74% | 18,19% | 35,48% | 1,28% | 114,9 ms |
| VietOCR `vgg_transformer` | 27,18% | 14,16% | 36,67% | 1,33% | 492,1 ms |

Transformer giảm CER nhưng giảm Exact Match, tăng WER/DER và chậm hơn khoảng 4,3 lần
theo p95. Vì quality gate ưu tiên Exact Match và không chấp nhận regression an toàn,
`vgg_seq2seq` tiếp tục là primary; Transformer không được promote.

### Fallback có điều kiện

Rule review-only dùng Transformer và Paddle như candidate khi Seq2Seq không chắc:

| Chỉ số | Seq2Seq | Fallback leave-one-document-out |
|---|---:|---:|
| Exact Match | 30,74% | 44,34% |
| CER | 18,19% | 15,36% |
| WER | 35,48% | 34,57% |
| DER | 1,28% | 2,01% |

Fallback phục hồi 44 lỗi nhưng làm mất 2 dòng baseline vốn đúng. Vì có false switch,
mọi thay đổi text chỉ được đưa ra `needs_review`; toàn bộ policy Phase 14.8 vẫn là
`SHADOW_REVIEW_ONLY` và `NOT_PRODUCTION_READY`.

## 6. Phase 15–17 — OCR trong generic IDP nhiều họ tài liệu

Pipeline generic của Phase 15 dùng **Paddle detector → VietOCR Seq2Seq primary →
VietOCR Transformer verifier**. Native DOCX/PDF/XLSX không OCR; ảnh/PDF scan đi qua
pipeline này. Kết quả development trên 25 tài liệu synthetic, 31 trang và 1.025 crop:

| Họ tài liệu | Classification | Field EM | Completeness | Field CER |
|---|---:|---:|---:|---:|
| CV | 100% | 32,00% | 75,00% | 66,54% |
| Đơn/biểu mẫu hành chính | 100% | 51,22% | 88,89% | 43,74% |
| Hợp đồng/quyết định | 100% | 10,00% | 22,22% | 116,78% |
| Bằng cấp/chứng chỉ | 100% | 10,00% | 22,50% | 111,88% |
| Phiếu nhân viên/bảng biểu | 100% | 46,15% | 48,33% | 39,45% |
| **Tổng** | **100%** | **30,92%** | **51,39%** | **74,81%** |

Các số này chỉ dùng regression và tìm khoảng trống extractor, không phải accuracy
production. Parser Phase 16 cải thiện kết quả mà không chạy lại recognizer:

| Phạm vi | Field EM trước → sau | Completeness trước → sau | CER trước → sau |
|---|---:|---:|---:|
| Hợp đồng/quyết định | 10,00% → 25,00% | 22,22% → 51,11% | 116,78% → 72,10% |
| Bằng cấp/chứng chỉ | 10,00% → 27,50% | 22,50% → 65,00% | 111,88% → 80,20% |
| Tổng 5 họ | 30,92% → 37,50% | 51,39% → 65,67% | 74,81% → 60,30% |

Điều này cho thấy parser có thể phục hồi coverage/CER nhưng không chứng minh recognizer
đã đạt gate. Phase 16 held-out evaluate-once trên 18 tài liệu đạt classification
`77,78%`, Field EM `13,00%`, completeness `28,00%` và sensitive-field false acceptance
`2`; quyết định `NOT_PROMOTED`. Một phần lỗi đến từ prediction TIMESHEET thiếu bảng,
không được quy toàn bộ cho OCR.

Phase 17 khóa lại contract TIMESHEET ở cấp row/cell và giữ sensitive OCR field ở
`needs_review`. Local live-v5 replay ghi nhận **15 tài liệu, Field EM 14,63%,
completeness 24,39%**; vẫn là `SHADOW_REVIEW_ONLY`.

## 7. Template-first — từ Paddle baseline đến EasyOCR mặc định

Đây là route MVP hiện tại, chỉ dành cho hai biểu mẫu nghỉ phép/tăng ca.

### Các bước cải thiện field extraction

| Checkpoint | Phương pháp | Ảnh | PDF scan | Trạng thái |
|---|---|---:|---:|---|
| TF-P2-002 | PaddleOCR local + parser template ban đầu | 31/54 | 31/54 | Gate 80% chưa đạt |
| TF-P2-002A | ROI cố định, parse theo nhãn/vị trí, vocabulary repair, provenance | 41/54 (75,93%) | 36/54 (66,67%) | Chưa đạt gate |
| TF-P2-002B | EasyOCR `vi` tùy chọn + grouping/dedup + artifact/continuation repair | 48/54 (88,89%) | 45/54 (83,33%) | Đạt gate candidate |
| TF-P2-003B | UAT bốn định dạng sau field recovery | 82/90 (91,11%) | 77/90 (85,56%) | Đạt các gate routing/schema |

Trong các rerun này, classification là `6/6`, schema error `0`, OCR routing `6/6`
`MANUAL_REVIEW` và false `AUTO_CONTINUE` `0`. Native DOCX/PDF vẫn giữ `90/90`.

### So sánh candidate backend ở TF-P2-004

| Candidate | Ảnh | PDF scan | Kết luận |
|---|---:|---:|---|
| Paddle `PP-OCRv5_mobile_rec` | 21/54 | 21/54 | Loại, không promote |
| Paddle `PP-OCRv5_server_rec` | 17/54 | Chưa chạy | Loại sau probe ảnh |
| EasyOCR tùy chọn | 50/54 | 48/54 | Pass routing/schema/review gates |
| VietOCR | Chưa chạy trong route này | Chưa chạy | Giữ là quyết định benchmark/dependency riêng |

Paddle candidate không đạt promotion gate. VietOCR không được cài hoặc chuyển vào
Template-first route vì chưa có benchmark cùng điều kiện; phép thử full-page trước đó
làm metric giảm. Đây là lý do backend policy được chuyển sang UAT cuối của EasyOCR,
không phải tuyên bố VietOCR kém trong mọi bài toán.

### UAT cuối TF-P2-005 — kết quả được dùng hiện tại

| Định dạng | Classification | Required-field exact match | Schema error | Routing |
|---|---:|---:|---:|---|
| DOCX | 10/10 | 90/90 | 0 | Native parser |
| PDF native | 10/10 | 90/90 | 0 | Native parser |
| Ảnh | 10/10 | 86/90 (95,56%) | 0 | 10/10 `MANUAL_REVIEW` |
| PDF scan | 10/10 | 82/90 (91,11%) | 0 | 10/10 `MANUAL_REVIEW` |

Tổng OCR routing là `20/20 MANUAL_REVIEW`, false `AUTO_CONTINUE` là `0`. Đo trên CPU
local, p95 là **23,5 giây/ảnh** và **22,6 giây/PDF scan**; EasyOCR cache khoảng
**93,99 MiB**. PaddleOCR vẫn có rollback explicit qua
`HCNS_TEMPLATE_OCR_BACKEND=paddle`.

## 8. Pilot dữ liệu mở rộng

DATA-00..DATA-05 chạy EasyOCR `vi-greedy` trên **13 tài liệu / 17 trang** ngoài route
Template-first:

| Metric | Kết quả |
|---|---:|
| Processed | 13/13 |
| Processing failures | 0 |
| Folder-derived classification match | 12/13 |
| Quality PASS | 2 |
| Quality REVIEW_REQUIRED | 6 |
| Quality REJECTED | 5 |
| Promotion | `HOLD` |

`HOLD` vì chưa có Ground Truth độc lập và corpus 17 trang thấp hơn benchmark tối thiểu
30 trang. Dữ liệu CV/hợp đồng/chứng chỉ được map vào generic IDP, không được dùng như
template-first v1.

## 9. CCCD held-out v2 — evaluate-once

15 ảnh được khóa prediction trước; sau audit, 1 ảnh mặt sau bị loại khỏi schema mặt
trước, còn **14 ảnh hợp lệ / 112 field** được người dùng xác nhận Ground Truth và đánh
giá đúng một lần. Phase 11.5 và 11.6 có kết quả giống nhau:

| Metric | Phase 11.5 | Phase 11.6 |
|---|---:|---:|
| Strict Field Exact Match | 50,00% | 50,00% |
| ASCII Field Exact Match | 50,89% | 50,89% |
| CER | 80,71% | 80,71% |
| DER | 16,14% | 16,14% |
| Field Presence | 86,61% | 86,61% |
| Accepted Precision | 95,45% | 95,45% |

Accepted precision, field presence, full-name/address và sensitive-false-acceptance
không đạt gate. Kết luận là `SHADOW_REVIEW_ONLY`; không candidate nào được promote.
Raw prediction, Ground Truth và ảnh vẫn nằm ngoài Git.

## 10. Quyết định backend hiện tại

1. **Template-first image/PDF scan**: dùng EasyOCR `vi-greedy` mặc định.
2. **PaddleOCR**: giữ làm rollback explicit và detector/geometry evidence ở các pipeline
   cần nó.
3. **VietOCR**: giữ trong legacy, benchmark, CCCD và các protocol cũ; không phải default
   của Template-first vì chưa có kết quả promote cùng route.
4. **Mọi OCR source**: không tự động chấp nhận field thiếu/chưa chắc chắn; chuyển người
   kiểm tra.
5. **Native source**: ưu tiên parser trực tiếp, không gọi OCR khi file đã có text.

## Tài liệu nguồn

- [Model Guide](MODEL_GUIDE.md) — model, crop, charset và policy recognizer.
- [Evaluation](EVALUATION.md) — metric spec, benchmark và promotion gate.
- [Project State](PROJECT_STATE.md) — checkpoint hiện tại và quyết định backend.
- [Handoff](HANDOFF.md) — lịch sử workstream và bằng chứng bàn giao.
- [Data Security](DATA_SECURITY.md) — boundary PII, storage và provenance.
