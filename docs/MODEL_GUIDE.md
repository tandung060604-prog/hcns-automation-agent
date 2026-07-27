# Model Guide

## Vai trò của model

Model chỉ tạo quan sát và đề xuất. Policy quyết định trường nào được chấp nhận,
trường nào phải review và hành động nào có thể thực thi.

Classifier rule-based M2 là baseline deterministic có version/provenance, không
phải tuyên bố accuracy production. Model classifier/extractor sau này phải trả
cùng port và không được dùng `SourceFormat` như nhãn business.

## Native parser first

Không dùng OCR như parser mặc định:

- PDF có text dùng PyMuPDF native và giữ page/bounding box;
- DOCX đọc OOXML để giữ heading, paragraph, list, table và metadata;
- XLSX dùng openpyxl với `data_only=False`, giữ raw value, data type, formula và
  merged range, không tính lại công thức;
- ảnh và PDF scan mới gọi `OcrEngine`.

SDK/model chỉ nằm trong adapter. Unit test dùng fake OCR và không tải weights.

## PaddleOCR baseline

Phù hợp khi:

- cần chạy local trên CPU hoặc GPU nhỏ;
- ưu tiên OCR tiếng Việt theo dòng và bounding box;
- muốn license Apache 2.0 và dependency tương đối rõ;
- tài liệu chủ yếu là biểu mẫu, giấy tờ hoặc trang scan đơn giản.

Điểm cần đo: dấu tiếng Việt, ảnh mờ/nghiêng, giấy tờ định danh, reading order
nhiều cột và tài liệu scan có bảng.

### Giới hạn recognizer tiếng Việt

`lang="vi"` không tự bảo đảm model có thể phát ra mọi ký tự tiếng Việt. Trước
khi benchmark, phải audit dictionary/output vocabulary bằng:

```powershell
hcns-agent-recognition audit-charset `
  --dictionary <recognition-dictionary.txt> `
  --model-identifier <model-id> `
  --output <aggregate-charset-audit.json>
```

Audit hiện dùng 134 chữ cái tiếng Việt mở rộng ở dạng Unicode NFC. Thay dictionary
ở inference không sửa được model đã huấn luyện vì chỉ số lớp output phải khớp với
dictionary lúc train. Model thiếu ký tự phải được thay hoặc fine-tune với charset
đầy đủ.

Phase 13.1 giữ detector hiện tại và đánh giá recognizer trên cùng tập crop dòng.
Ground Truth/prediction chứa text phải ở private-data; report aggregate được phép
lưu CER, WER, Exact Match, Diacritic Error Rate, accepted precision và latency.

```powershell
hcns-agent-recognition evaluate `
  --ground-truth <private-line-ground-truth.json> `
  --predictions <private-recognizer-predictions.json> `
  --output <aggregate-recognition-report.json>
```

NFC normalization chỉ chuẩn hóa biểu diễn Unicode, không được dùng để tự đoán
dấu đã mất. Candidate hậu xử lý phải giữ raw OCR và chuyển `needs_review` nếu
không có đủ bằng chứng.

## MinerU challenger

Phù hợp khi:

- tài liệu có layout nhiều cột, bảng phức tạp hoặc nhiều trang;
- cần Markdown/JSON theo block và reading order;
- có đủ RAM/VRAM và chấp nhận dependency lớn hơn.

Không dùng fork MinerU thiếu license/provenance. Khi thử nghiệm, pin phiên
bản upstream và lưu model manifest. Kiểm tra điều khoản attribution trước khi
cung cấp dịch vụ online.

MinerU không đi vào domain/application và chưa được promote vào default intake.

## Luật chọn OCR backend

Không chọn theo demo hoặc benchmark chung. Hai engine phải chạy trên cùng:

- input bytes;
- tập Ground Truth;
- normalization;
- schema field;
- phần cứng và giới hạn timeout.

Challenger chỉ thay baseline khi cải thiện field exact match đủ lớn và không làm
vi phạm privacy, latency hoặc chi phí vận hành.

## Model manifest bắt buộc

Mỗi lần benchmark phải lưu:

```json
{
  "engine": "paddleocr",
  "packageVersion": "x.y.z",
  "detectionModel": "model-id",
  "recognitionModel": "model-id",
  "device": "cpu",
  "parametersHash": "sha256:...",
  "datasetVersion": "hr-ground-truth-v1"
}
```

Không lưu raw PII trong manifest.
