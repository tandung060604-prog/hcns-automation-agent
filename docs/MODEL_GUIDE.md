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

## Phase 14.1 — primary theo Ground Truth đã xác nhận

Sau khi người dùng đối chiếu trực tiếp toàn bộ 77 crop của bốn tài liệu, thứ hạng
recognizer thay đổi: VietOCR `vgg_seq2seq` đạt 42.86% Exact Match và 15.59% CER;
Paddle raw đạt 25.97% Exact Match và 28.39% CER; EasyOCR tốt nhất đạt 7.79%
Exact Match và 41.49% CER.

Pipeline pilot vì vậy dùng VietOCR trên crop `bbox_balanced_64`, nhưng vẫn giữ
raw Paddle và toàn bộ geometry làm evidence. EasyOCR chỉ là verifier. Candidate
chỉ được auto-accept khi recognizer độc lập đồng thuận chính xác sau NFC; các
trường hợp khác bắt buộc `needs_review`.

Kết quả chỉ cho phép `PROMOTE_TO_CONTROLLED_PILOT`, không cho phép production.
Đồng thuận không được dùng thay Ground Truth và không được tự phục hồi dấu.

## Phase 14.2 — controlled pilot

Controlled pilot chạy offline trên 51 session local được cấp quyền, tổng cộng
2.150 crop dòng và không có session thất bại. Rule đồng thuận chính xác giữa
VietOCR primary và verifier chỉ chấp nhận 188 dòng (8,74%); 1.962 dòng còn lại
giữ nguyên evidence và chuyển `needs_review`.

Tỷ lệ chấp nhận này là chỉ số coverage vận hành, không phải accuracy. Accuracy
vẫn neo vào 77 crop có Ground Truth Phase 14.1; confidence không được dùng để
nới auto-accept khi chưa được calibration.

## Phase 14.3 — multi-crop diagnosis

Bốn profile crop được chạy lại bằng cùng VietOCR `vgg_seq2seq`. Profile
`bbox_balanced_64` vẫn tốt nhất với 42,86% Exact Match và 15,29% CER. Trong 44
dòng baseline sai, các crop VietOCR thay thế chỉ phục hồi tối đa hai dòng nếu
chọn bằng oracle; do đó không đủ bằng chứng để thêm runtime fallback theo crop.

Phân loại lỗi aggregate gồm 22 dòng thiếu/thay thế ký tự, 13 dòng
thay thế/khoảng trắng, sáu dòng thừa/thay thế và ba dòng chỉ sai dấu. Paddle có
thể đúng ở một số dòng nhưng chỉ được dùng làm review candidate, không làm rule
fallback tự động vì lựa chọn bằng Ground Truth tại runtime là không khả dụng.

## Phase 14.4 — blinded second-recognizer benchmark

Ground Truth được mở rộng lên 309 crop của 15 tài liệu. Cả hai model được chạy
ngầm và giữ prediction ẩn cho đến khi 309/309 dòng được người dùng xác nhận,
tránh annotation bias.

| VietOCR profile | Exact Match | CER | WER | DER | Mean |
|---|---:|---:|---:|---:|---:|
| `vgg_seq2seq` | 30,74% | 18,19% | 35,48% | 1,28% | 58,3 ms |
| `vgg_transformer` | 27,18% | 14,16% | 36,67% | 1,33% | 224,5 ms |

Transformer giảm CER nhưng giảm Exact Match, tăng WER/DER và chậm hơn khoảng
3,9 lần. Theo quality gate ưu tiên Exact Match và không cho phép CER/DER
regression tùy ý, challenger là `NOT_PROMOTED`; seq2seq vẫn là primary và toàn
bộ pipeline là `NOT_PRODUCTION_READY`.

## Phase 14.5 — conditional fallback

214 lỗi của seq2seq gồm 81 dòng thiếu/thay thế ký tự, 56 dòng thay thế/khoảng
trắng, 49 dòng thừa/thay thế và 28 dòng chỉ sai dấu. Transformer phục hồi chính
xác 16 lỗi của primary; raw Paddle phục hồi 53 lỗi. Oracle của ba recognizer đạt
159/309 dòng (51,46%), nhưng oracle không tồn tại ở runtime.

Rule review-only được đánh giá bằng leave-one-document-out:

1. nếu Transformer khớp chính xác Paddle và khác seq2seq, đề xuất Transformer;
2. nếu confidence seq2seq dưới 0,80, đưa Paddle làm review candidate;
3. mọi candidate thay đổi text vẫn mang `needs_review`.

Replay document-level đạt 44,34% Exact Match, 15,36% CER và 34,57% WER, phục
hồi 44 lỗi nhưng làm mất hai dòng seq2seq vốn đúng. DER tăng từ 1,28% lên 2,01%.
Vì vậy rule chỉ được chạy `SHADOW_REVIEW_ONLY`; không auto-accept và không thay
primary production.

## Phase 11.5 — CCCD Unicode và base-text evidence

CCCD mặt trước dùng profile ROI tương đối cho tám trường. Nhãn Việt/Anh chỉ
tinh chỉnh ROI trong biên dự kiến; nó không được phép trở thành giá trị field.
Mỗi ROI lưu bounding box, crop và candidate làm provenance.

Bốn recognizer chạy local trên bốn biến thể crop không phủ nhận dấu:

1. PaddleOCR PP-OCRv5;
2. EasyOCR `vi`;
3. VietOCR `vgg_seq2seq`;
4. VietOCR `vgg_transformer`.

Chỉ `exact_consensus` của ít nhất hai recognizer độc lập và validation hợp lệ
mới cho phép `value.status=accepted`. Nếu các model chỉ đồng thuận sau khi bỏ
dấu, `value` vẫn `needs_review`; `asciiValue` mang
`asciiStatus=verified_base_text`. `asciiValue` không bao giờ thay thế âm thầm
giá trị Unicode pháp lý.

Với họ tên, quốc tịch và hai trường địa chỉ, exact consensus chỉ gồm ký tự
ASCII vẫn là `needs_review`: pipeline phải có bằng chứng Unicode trực tiếp mới
được chấp nhận tự động. Chuẩn hóa enum không được tự sinh dấu còn thiếu.

Policy, manifest development, ROI/crop profile và sáu artifact model được khóa
SHA-256 trong `config/phase11_5_cccd_policy.json`. Tập 15 CCCD hiện tại là
development/regression do đã được dùng tinh chỉnh. Promotion chỉ được đánh giá
một lần trên tối thiểu 15 CCCD mới theo quy trình prediction ẩn rồi xác nhận
Ground Truth.

Kết quả development 15 CCCD sau khi khóa policy: Strict Field Exact Match
60,00%, ASCII Exact Match 61,67%, CER 43,60%, Base CER 41,87%, DER 12,65%,
Field Presence 95,83% và Accepted Precision 100%. So với Phase 11.4, lỗi mất
ký tự giảm 82,35% và không còn sensitive-field false acceptance. Gate vẫn
`SHADOW_REVIEW_ONLY`: full-name ASCII EM mới đạt 73,33%, address ASCII EM
3,33%, còn 5 field regression và ROI/candidate oracle của địa chỉ quá thấp.

## Phase 11.6 — ROI địa chỉ và selection họ tên

Policy 11.6 khóa ROI theo dải từ nhãn hiện tại đến nhãn kế tiếp, giới hạn địa chỉ
hai dòng và tăng điểm cho candidate họ tên sạch. Runtime CPU dùng EasyOCR
`greedy` thay cho `beamsearch`, do decoder beamsearch bị treo tại một crop địa
chỉ lớn trong lần chạy development. Manifest 15 CCCD, sáu artifact model, schema,
crop profile, recognition policy, runtime profile, runner, worker và evaluator
đều được khóa SHA-256 trong `config/phase11_6_cccd_policy.json`.

Replay đầu tiên trên 15/15 CCCD development hoàn tất với 480 crop nhưng làm
regression. Policy sau đó được sửa theo nguyên tắc baseline-preserving:

- chỉ OCR lại `fullName`, `placeOfOrigin` và `placeOfResidence`;
- crop bắt đầu dưới dòng nhãn, địa chỉ ghép tối đa hai dòng;
- `placeOfResidence` không còn bị cắt theo nhãn `dateOfExpiry` ở cột trái;
- năm field ngoài phạm vi luôn giữ kết quả/evidence Phase 11.5;
- candidate mục tiêu khác baseline chỉ được lưu làm shadow evidence;
- field mới tìm thấy luôn `needs_review`.

Replay cuối chạy 180 crop mục tiêu bằng EasyOCR/VietOCR và không dùng Ground
Truth trong inference:

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

Replay cuối không cải thiện hoặc làm mất field exact nào: improvement/regression
là 0/0. Điều kiện bảo vệ field Phase 11.5 đã đạt, nhưng full-name ASCII EM vẫn
73,33% và address ASCII EM vẫn 3,33%. Policy vì vậy tiếp tục
`SHADOW_REVIEW_ONLY`; ROI candidate có thể đi sang protocol held-out ẩn để đo
khả năng tổng quát hóa, nhưng chưa được dùng làm fallback tự động.

Phân tích riêng shadow candidate của ba ROI mới (không phải output được chọn)
đạt Strict EM 58,33%, ASCII EM 63,33%, CER 39,34%, DER 17,00% và Region
Selection Accuracy 85,83%. Full-name ASCII EM tăng lên 86,67%, nhưng origin chỉ
6,67% và residence vẫn 0%; Accepted Precision của shadow candidate là 96,15%.
Điều này cho thấy crop họ tên có tín hiệu cải thiện, còn ghép địa chỉ vẫn chưa
đủ bằng chứng để promote.

### Protocol held-out CCCD v2

Manifest private chứa 15 CCCD mới, không trùng SHA-256 với các manifest
development/private trước đó. Nguồn, manifest, policy và prediction Phase 11.5/
11.6 được khóa SHA-256 ngoài Git; prediction đã được seal trước khi mở Ground
Truth và vẫn ở `SHADOW_REVIEW_ONLY`.

Audit source test cho thấy 15/15 label files chỉ là YOLO detection annotations
(class IDs và polygon/box), không có text transcription của tám field OCR. Vì
vậy chúng chưa phải Ground Truth độc lập cho exact-OCR và chưa được phép mở
prediction để evaluate-once. Cần human-verified text transcription trước khi
đánh giá; Phase 11.5 vẫn là primary, Phase 11.6 vẫn là candidate
`SHADOW_REVIEW_ONLY`.

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
