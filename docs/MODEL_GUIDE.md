# Model Guide

## Vai trò của model

Model chỉ tạo quan sát và đề xuất. Policy quyết định trường nào được chấp nhận,
trường nào phải review và hành động nào có thể thực thi.

## PaddleOCR baseline

Phù hợp khi:

- cần chạy local trên CPU hoặc GPU nhỏ;
- ưu tiên OCR tiếng Việt theo dòng và bounding box;
- muốn license Apache 2.0 và dependency tương đối rõ;
- tài liệu chủ yếu là biểu mẫu, giấy tờ hoặc trang scan đơn giản.

Điểm cần đo: dấu tiếng Việt, ảnh mờ/nghiêng, CCCD, reading order nhiều cột và
bảng chấm công.

## MinerU challenger

Phù hợp khi:

- tài liệu có layout nhiều cột, bảng phức tạp hoặc nhiều trang;
- cần Markdown/JSON theo block và reading order;
- có đủ RAM/VRAM và chấp nhận dependency lớn hơn.

Không dùng một fork MinerU thiếu license/provenance. Khi thử nghiệm, pin phiên
bản upstream và lưu model manifest. Kiểm tra điều khoản attribution trước khi
cung cấp dịch vụ online.

## Luật chọn backend

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

