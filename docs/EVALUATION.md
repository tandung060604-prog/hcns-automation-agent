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

## Metrics

- OCR: CER, WER, reading-order accuracy.
- Field: exact match, precision, recall, not-found rate.
- Workflow: auto-proposal rate, review rate, correction rate.
- Safety: false acceptance của trường nhạy cảm và side-effect policy violations.
- System: latency p50/p95, throughput, peak RAM/VRAM, failure rate.

## Promotion gate

Backend mới chỉ được promote khi:

1. không tăng false acceptance ở trường nhạy cảm;
2. field exact match cải thiện có ý nghĩa trên tập cố định;
3. latency/chi phí nằm trong SLO;
4. contract tests và regression pass;
5. license, model provenance và privacy được duyệt.

