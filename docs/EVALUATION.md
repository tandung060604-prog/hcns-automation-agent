# Evaluation

## Câu hỏi

Không hỏi “OCR nào tốt nhất?” mà hỏi “backend nào giảm sai sót và thời gian
review cho từng workflow HCNS trên phần cứng mục tiêu?”.

## Dataset tối thiểu

- 30–50 trang thật được cấp quyền hoặc đã ẩn danh;
- CV, định danh, hợp đồng, quyết định, đơn và chấm công;
- ảnh rõ, mờ, nghiêng, nhiều cột, bảng và tài liệu nhiều trang;
- Ground Truth do người dùng duyệt, có version.

Synthetic dùng để regression, không thay bằng chứng tài liệu thật.

Milestone Universal Document Intake có bốn fixture regression synthetic:

- CV dạng PDF text;
- hợp đồng dạng DOCX có heading/list/table;
- bảng chấm công XLSX có formula và merged range;
- biểu mẫu hành chính dạng ảnh, cộng một PDF scan sinh từ ảnh đó.

Fixture này chỉ chứng minh contract/routing/safety, không chứng minh accuracy
trên tài liệu HCNS thật.

## Metrics

- OCR: CER, WER, reading-order accuracy.
- Field: exact match, precision, recall, not-found rate.
- Workflow: auto-proposal rate, review rate, correction rate.
- Safety: false acceptance của trường nhạy cảm và side-effect policy violations.
- System: latency p50/p95, throughput, peak RAM/VRAM, failure rate.
- Intake: detection accuracy, unsafe-file rejection, native-vs-OCR routing,
  canonical structure preservation và idempotent completion.
- Classification: precision/recall/F1 và UNKNOWN/ambiguity rate theo
  `DocumentType`; không báo một accuracy tổng che lấp loại hiếm.
- Extraction: field exact match, missing/invalid/conflict rate và provenance
  coverage theo extractor/version.
- Quality gate: false PASS, false REJECT, review precision và sensitive-field
  false acceptance.

## Promotion gate

Backend mới chỉ được promote khi:

1. không tăng false acceptance ở trường nhạy cảm;
2. field exact match cải thiện có ý nghĩa trên tập cố định;
3. latency/chi phí nằm trong SLO;
4. contract tests và regression pass;
5. license, model provenance và privacy được duyệt.

PPTX hiện chỉ có parser text-by-slide ở trạng thái `PARTIAL`; chưa được đánh giá
fidelity shape/table/reading order. Legacy DOC/XLS không nằm trong accuracy
benchmark cho đến khi có conversion path an toàn được phê duyệt.

Rule classifier/extractors M2 chỉ là architecture baseline trên fixture
synthetic. Không promote để auto-route production cho đến khi chạy Ground Truth
có quyền sử dụng và kiểm false acceptance theo từng document type.
