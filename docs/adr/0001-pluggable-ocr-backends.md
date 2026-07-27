# ADR-0001: Pluggable OCR backends

Status: Accepted

## Context

PaddleOCR đã có baseline tiếng Việt và chạy CPU tốt. MinerU mạnh về parsing bố
cục nhưng nặng hơn và chưa có benchmark HCNS đã xác nhận. Gắn nghiệp vụ trực
tiếp vào một engine sẽ làm việc thay model tốn kém.

## Decision

Application chỉ phụ thuộc `OcrEngine` port và canonical OCR result. PaddleOCR,
MinerU và các engine khác là adapter được contract-test bằng cùng fixture.

## Consequences

- Có thể benchmark và chuyển engine không sửa domain.
- Canonical result phải đủ provenance nhưng không cố chứa mọi output vendor.
- Tính năng riêng của engine đi vào `metadata`, không rò vào business schema.
- Cần duy trì adapter/version manifest và contract tests.

