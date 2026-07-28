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

## Benchmark contract M3

Harness offline dùng bốn JSON Schema version `1.0.0`:

- `benchmark_ground_truth.schema.json`: manifest quyền sử dụng/approval/retention,
  dataset digest và Ground Truth;
- `benchmark_predictions.schema.json`: backend/model version, output field, quality
  status, latency và failure code;
- `benchmark_report.schema.json`: metric tổng hợp, không có raw expected/predicted
  field value;
- `benchmark_comparison.schema.json`: hai aggregate report và quyết định
  `PROMOTE|HOLD` có từng check.

Ground Truth và prediction chứa field value nên phải nằm ngoài repository trong
data root được kiểm soát. Unit test chỉ tạo fixture synthetic trong thư mục tạm và
không đọc `dataset/`.

`prediction_case_from_idp_result` chuyển `IdpResult` vendor-neutral thành benchmark
prediction. Vì vậy PaddleOCR baseline và MinerU challenger phải đi qua cùng intake,
classification, extraction và quality contract; harness không chứa nhánh riêng theo
vendor.

Field exact match là equality có kiểu trên scalar chuẩn của Business JSON. Candidate
sai hoặc duplicate làm tăng predicted count; field không có candidate làm tăng
not-found. Classification macro metric tính trên từng type có Ground Truth support,
đồng thời báo riêng `UNKNOWN` rate. OCR metric dùng edit distance tổng hợp để tính
CER/WER và exact line-sequence cho reading-order accuracy; raw transcription không
đi vào report. Report còn có false PASS, false REJECT, review precision/rate,
sensitive-field false acceptance, latency p50/p95 và failure rate.

```powershell
hcns-agent-benchmark evaluate `
  --ground-truth <authorized-ground-truth.json> `
  --predictions <predictions.json> `
  --output <aggregate-report.json>

hcns-agent-benchmark compare `
  --ground-truth <authorized-ground-truth.json> `
  --baseline <paddle-baseline.json> `
  --challenger <mineru-challenger.json> `
  --output <aggregate-comparison.json>
```

`compare` mặc định trả exit code `2` khi quyết định là `HOLD`. Approval flags không
có giá trị mặc định đúng; operator phải cung cấp rõ sau khi contract/regression,
privacy, license và model provenance đã được duyệt. Không commit report trước khi
review disclosure, dù report không chứa raw value.

## Phase 13.1 — Vietnamese recognition-only

Benchmark tài liệu tổng thể không đủ để chẩn đoán hiện tượng mất dấu. Phase 13.1
đánh giá các recognizer trên cùng crop dòng và cùng Ground Truth NFC bằng ba
schema riêng:

- `recognition_ground_truth.schema.json`: text chuẩn private và cờ xác nhận quyền
  đánh giá local;
- `recognition_predictions.schema.json`: text dự đoán, confidence và duration
  private;
- `recognition_report.schema.json`: metric aggregate, không chứa raw text.

Ngoài CER, WER và Exact Match, report có:

- `Diacritic Error Rate`: phần edit error còn lại sau khi bỏ dấu trên reference
  và prediction;
- `predictionNfcViolationCount`: số prediction chưa ở Unicode NFC;
- `acceptedPrecision`: tỷ lệ exact trong nhóm confidence đạt threshold;
- latency p50/p95.

Từ Phase 14.6, mọi recognition benchmark dùng metric spec
`vi-ocr-metrics/1.0.0`:

- Exact Match là so sánh nghiêm ngặt sau NFC và chuẩn hóa khoảng trắng, vẫn giữ
  nguyên hoa/thường, dấu câu và dấu tiếng Việt;
- `casefoldExactMatchRate` chỉ dùng chẩn đoán agreement, không được thay Exact
  Match;
- CER/WER dùng Levenshtein trên chuỗi/từ đã chuẩn hóa;
- DER lấy số edit do dấu gây ra chia cho số ký tự reference có dấu.

Các script Phase 14.1–14.5 gọi cùng adapter metric và có parity test với
`VietnameseRecognitionBenchmark`. Report lịch sử dùng mẫu số DER theo tổng ký
tự phải được xem là legacy và không so trực tiếp với report spec 1.0.0.

Confidence cao không thay thế Exact Match. Nếu model không có ký tự đúng trong
output vocabulary, confidence vẫn có thể cao trong khi `acceptedPrecision` thấp.

### Protocol khóa Phase 14.6

`config/phase14_6_benchmark_lock.json` cố định policy review-only, crop
`bbox_balanced_64`, SHA-256 của hai VietOCR weights và Paddle detector. Script
`validate_phase14_6_lock.py` từ chối chạy nếu code policy, metric spec, kích
thước hoặc hash model thay đổi.

Tập held-out phải có ít nhất 15 tài liệu được quyền dùng local. Trình tự không
được đảo:

1. xác minh lock và tạo prediction trong trạng thái ẩn;
2. người dùng xác nhận Ground Truth chỉ dựa trên crop/ảnh gốc;
3. mở prediction và đánh giá đúng một lần;
4. không chỉnh threshold/crop/policy trên tập held-out;
5. không promote nếu làm mất bất kỳ dòng baseline-correct nào.

```powershell
python scripts/phase14_6_heldout_protocol.py seal `
  --predictions <private-hidden-predictions.json> `
  --output <private-sealed-predictions.json>

# Chỉ chạy sau khi Ground Truth đã được xác nhận mà không nhìn prediction.
python scripts/phase14_6_heldout_protocol.py evaluate `
  --sealed-predictions <private-sealed-predictions.json> `
  --ground-truth <private-confirmed-ground-truth.json> `
  --output <aggregate-heldout-evaluation.json>
```

Lệnh `evaluate` không hỗ trợ overwrite. Artifact kết quả đã tồn tại đồng nghĩa
evaluation held-out đã được sử dụng; muốn thử policy khác phải thu thập một tập
held-out mới.

```powershell
hcns-agent-recognition evaluate `
  --ground-truth <private-line-ground-truth.json> `
  --predictions <private-predictions.json> `
  --output <aggregate-recognition-report.json> `
  --confidence-threshold 0.95
```

Ground Truth và prediction không được commit. Report aggregate chỉ được publish
sau disclosure review; danh sách missing charset được phép lưu vì không chứa nội
dung tài liệu.

### Quy trình Phase 13.2

```powershell
python scripts/phase13_2_recognition.py prepare `
  --source-root <private-native-pdf-root> `
  --output-root <private-phase13-corpus> `
  --max-cases 240 --dpi 300

python scripts/phase13_2_recognition.py run `
  --backend <paddle|easyocr|vietocr> `
  --manifest <private-corpus-manifest.json> `
  --output <private-predictions.json>

python scripts/phase13_2_recognition.py select `
  --report <paddle-report.json> `
  --report <easyocr-report.json> `
  --report <vietocr-report.json> `
  --baseline-model latin_PP-OCRv5_mobile_rec `
  --output <recognizer-selection.json>
```

Crop được tạo từ bounding box dòng của PDF native để loại detector khỏi biến số
benchmark. Mỗi crop, source và toàn corpus đều có SHA-256; runner từ chối crop bị
thay đổi. Cả ba backend phải dùng đúng cùng manifest digest.

Ranking ưu tiên Exact Match cao nhất, sau đó DER thấp nhất, accepted precision
cao nhất và latency p95 thấp nhất. Challenger chỉ được chọn cho pilot khi Exact
Match và DER đều không tệ hơn baseline, đồng thời ít nhất một metric tốt hơn.

### Phase 13.3 — lặp lại trên scan thật có quyền sử dụng

Pipeline pilot dùng box của PaddleOCR, nhận dạng từng crop bằng EasyOCR `vi` và
kiểm chứng độc lập bằng VietOCR `vgg_seq2seq`. Hai chuỗi chỉ được xem là đồng
thuận sau NFC, `casefold` và chuẩn hóa khoảng trắng. Nếu bất đồng, pipeline giữ
ứng viên EasyOCR nhưng bắt buộc gắn `needs_review`; VietOCR không được phép âm
thầm sửa kết quả.

Tập đánh giá private gồm 15 CCCD scan thật được người dùng xác nhận cả
`comparedWithImage=true`, `allTextChecked=true` và đủ 8 trường Ground Truth.
Manifest private cố định bằng SHA-256:

```text
sha256:e60642e231d9c959423c94c622f5c46488edc8789036dd2318c7acefb513ea61
```

Kết quả aggregate:

| Chỉ số | Phase 9 reviewed baseline | Phase 13.3 hybrid |
|---|---:|---:|
| Document CER trung bình | 0.00% | 68.74% |
| Document WER trung bình | 0.00% | 127.69% |
| Document Exact Match | 100.00% | 0.00% |

Phase 9 ở bảng trên là bản đã được hiệu chỉnh/xác nhận trong session, nên chỉ là
reference vận hành, không phải raw-recognizer baseline. Hybrid có 671 crop; chỉ
18 dòng đồng thuận (2.68%), 653 dòng phải review. Kết luận
`NOT_PROMOTED`: kết quả synthetic Phase 13.2 không tái lập trên scan thật và chưa
đủ bằng chứng để thay recognizer production. Manifest, crop, prediction và text
Ground Truth nằm ngoài Git tại `private-data/output/phase13_3/`.

### Phase 14.1 — Ground Truth cấp crop đã xác nhận

Người dùng đã đối chiếu trực tiếp 77 crop thuộc bốn tài liệu, kiểm tra toàn bộ chữ
và dấu tiếng Việt. Ground Truth và prediction vẫn nằm ngoài Git. Digest private:

```text
sha256:eadcadc94b753999784baa5923f0ee19e138f9e3cc22dcf60780ad0ac4310d56
```

| Candidate | Exact Match | CER | WER | DER |
|---|---:|---:|---:|---:|
| Paddle raw | 25.97% | 28.39% | 63.56% | 3.20% |
| EasyOCR best crop | 7.79% | 41.49% | — | 4.74% |
| VietOCR `vgg_seq2seq` | 42.86% | 15.59% | 32.20% | 0.77% |

VietOCR được chọn làm primary cho controlled pilot trên crop `bbox_balanced_64`.
Quyết định là `PROMOTE_TO_CONTROLLED_PILOT`, đồng thời
`NOT_PRODUCTION_READY` vì corpus mới có bốn tài liệu.

### Phase 14.2 — coverage của controlled pilot

Pipeline được chạy offline trên 51 session local có quyền sử dụng, gồm 2.150 crop
dòng và không có session thất bại. Exact agreement giữa primary và verifier chấp
nhận 188 dòng (8,74%); 1.962 dòng được chuyển `needs_review`.

Đây là phép đo coverage, không phải accuracy vì các session chưa có Ground Truth
cấp dòng đầy đủ. Không dùng 8,74% để suy ra độ chính xác hoặc thay đổi production
gate; accuracy tiếp tục tham chiếu tập 77 crop đã xác nhận.

### Phase 14.3 — benchmark nhiều crop

VietOCR `vgg_seq2seq` được chạy trên bốn profile crop của cùng 77 dòng đã xác
nhận. `bbox_balanced_64` tiếp tục được chọn với 42,86% Exact Match và 15,29% CER.
Ba profile khác chỉ phục hồi tối đa 2/44 lỗi nếu được chọn bằng oracle.

| Nhóm lỗi của primary | Số dòng |
|---|---:|
| Thiếu/thay thế ký tự | 22 |
| Thay thế/khoảng trắng | 13 |
| Thừa/thay thế ký tự | 6 |
| Chỉ sai dấu | 3 |

Oracle recovery chỉ là trần phân tích, không phải rule runtime. Quyết định vẫn là
giữ một crop cố định, chuyển bất đồng sang review và mở rộng corpus trước khi
thử recognizer thứ hai.

### Phase 14.4 — benchmark mù recognizer thứ hai

Corpus được mở rộng lên 309 crop thuộc 15 tài liệu có quyền sử dụng. Prediction
của `vgg_seq2seq` và `vgg_transformer` được tính trước nhưng giữ ẩn cho đến khi
Ground Truth đạt 309/309; benchmark sau đó chỉ đọc artifact đã bịt kín.

| Profile | Exact Match | CER | WER | DER | p95 |
|---|---:|---:|---:|---:|---:|
| `vgg_seq2seq` | 30,74% | 18,19% | 35,48% | 1,28% | 114,9 ms |
| `vgg_transformer` | 27,18% | 14,16% | 36,67% | 1,33% | 492,1 ms |

`vgg_transformer` không đạt gate promote vì Exact Match giảm 3,56 điểm phần
trăm, WER và DER tăng, đồng thời p95 chậm hơn khoảng 4,3 lần. Kết luận:
`vgg_seq2seq` tiếp tục là primary, challenger `NOT_PROMOTED` và hệ thống
`NOT_PRODUCTION_READY`.

### Phase 14.5 — error stratification và conditional fallback

Toàn bộ 214 lỗi seq2seq được phân loại aggregate, không ghi raw text vào report:

| Nhóm lỗi | Số dòng |
|---|---:|
| Thiếu/thay thế ký tự | 81 |
| Thay thế/khoảng trắng | 56 |
| Thừa/thay thế ký tự | 49 |
| Chỉ sai dấu | 28 |

Transformer đúng ở 16 dòng seq2seq sai; Paddle đúng ở 53 dòng. Rule fallback
chọn threshold chỉ trên 14 document rồi replay document còn lại; cả 15 fold đều
chọn confidence threshold 0,80.

| Chỉ số | Seq2seq | Fallback LODO |
|---|---:|---:|
| Exact Match | 30,74% | 44,34% |
| CER | 18,19% | 15,36% |
| WER | 35,48% | 34,57% |
| DER | 1,28% | 2,01% |

Fallback chuyển 138/309 candidate, phục hồi 44 lỗi và làm mất hai dòng baseline
vốn đúng. 13/15 document cải thiện theo tổng Exact Match, không document nào
giảm tổng Exact, nhưng hai false switches vẫn vi phạm gate an toàn. Quyết định:
`SHADOW_REVIEW_ONLY`, mọi switch phải `needs_review`.
