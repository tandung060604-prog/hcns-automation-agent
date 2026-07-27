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

## Phase 13.2 — Kết quả recognition-only

Corpus `synthetic-hr-v2-vi-lines` version `1.0.0` gồm 240 crop dòng ở 300 DPI,
trong đó 204 dòng có ký tự Việt mở rộng. Corpus và prediction nằm trong
private-data; digest cố định:

```text
sha256:aabe6e292dd1baff7c9a94f30aa5f83c4e4b741f9209fd5e5caf181d6223ee5b
```

| Recognizer | Exact Match | CER | DER | Accepted precision | p95 |
|---|---:|---:|---:|---:|---:|
| EasyOCR 1.7.2 `vi` greedy | 82.92% | 0.89% | 0.00% | 100.00% | 187.7 ms |
| VietOCR 0.3.13 `vgg_seq2seq` | 72.50% | 3.67% | 3.01% | 0.00%* | 178.1 ms |
| PaddleOCR 3.7.0 Latin v5 | 19.58% | 12.51% | 7.87% | 17.74% | 161.4 ms |

`*` VietOCR không có prediction nào đạt confidence threshold 0.95; confidence
giữa các engine không được so trực tiếp khi chưa calibration.

Quyết định: `easyocr-vi-greedy` được chọn cho pilot recognition, chưa được
promote production. VietOCR là recognizer kiểm chứng. EasyOCR và VietOCR đồng
thuận 143/240 dòng; precision của nhóm đồng thuận đạt 100% trên corpus này.

Policy pilot:

1. Paddle detector tiếp tục tạo vùng dòng.
2. EasyOCR nhận dạng crop độ phân giải cao.
3. VietOCR nhận dạng độc lập cùng crop.
4. Chỉ auto-accept khi hai chuỗi NFC đồng thuận và validation nghiệp vụ đạt.
5. Mọi trường hợp khác là `needs_review`; không điền dấu bằng suy đoán.

Corpus synthetic sạch không chứng minh accuracy production. Cần lặp lại policy
trên line-crop corpus từ tài liệu thật có quyền sử dụng trước khi thay default
recognizer.

VietOCR 0.3.13 pin một số dependency training cũ, bao gồm Pillow 10.2. Runtime
pilot chỉ cài dependency cần cho inference để không hạ phiên bản Pillow của
EasyOCR. Triển khai dài hạn phải dùng môi trường VietOCR riêng, khóa hash weights
và làm `pip check`; không dùng nguyên runtime pilot làm image production.

## Phase 13.3 — hybrid real-scan pilot

`HybridVietnameseOcrEngine` giữ detector và geometry tách khỏi recognizer:

1. PaddleOCR cung cấp box dòng và raw detector evidence.
2. EasyOCR `vi` nhận dạng crop độ phân giải cao và tạo candidate chính.
3. VietOCR `vgg_seq2seq` đọc cùng crop để kiểm chứng.
4. Chỉ candidate đồng thuận chính xác sau chuẩn hóa NFC mới có trạng thái
   `accepted`; mọi bất đồng là `needs_review`.

Kết quả 15 CCCD thật, digest
`sha256:e60642e231d9c959423c94c622f5c46488edc8789036dd2318c7acefb513ea61`,
cho thấy chỉ 18/671 crop đồng thuận (2.68%) và document CER hybrid là 68.74%.
Vì vậy Phase 13.3 không được promote. Bước tiếp theo phải tạo Ground Truth ở cấp
dòng/crop để tách lỗi detector/crop khỏi lỗi recognizer, rồi hiệu chỉnh padding,
perspective và cấu hình nhận dạng trên từng nhóm trường.

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
