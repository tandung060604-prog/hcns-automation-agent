# Architecture

## Nguyên tắc

Kiến trúc Ports and Adapters giữ nghiệp vụ HCNS độc lập với PaddleOCR, MinerU,
database hoặc BPM engine.

```text
Interface/API
    │
Application use cases
    │
Domain: document, field, review, workflow policy
    │
Ports: OCR / review queue / storage / workflow
    │
Adapters: PaddleOCR / MinerU / database / BPM
```

Dependency chỉ đi từ ngoài vào trong. `domain/` không import `application/`,
`ports/` hoặc `adapters/`. `application/` chỉ gọi Protocol trong `ports/`.

## Thành phần

### Domain

- `HrDocument`: tài liệu và loại nghiệp vụ.
- `ExtractedField`: value, confidence, provenance, validation.
- `WorkflowCase`: state machine có transition rõ ràng.
- `ReviewDecision`: approve, correct hoặc reject.

### Application

`ProcessDocument` điều phối OCR, đánh giá confidence và quyết định auto-propose
hay human review. Use case không biết engine thực tế là PaddleOCR hay MinerU.

### Ports

- `OcrEngine`: input tài liệu, output trang/dòng OCR chuẩn hóa.
- Tương lai: `ReviewQueue`, `DocumentStore`, `WorkflowGateway`, `AuditLog`.

### Adapters

- `DeterministicMockOcrEngine`: demo và contract tests.
- PaddleOCR: baseline cho tiếng Việt và máy CPU.
- MinerU: challenger cho layout, bảng và tài liệu dài.

## Ranh giới triển khai

Production nên tách:

1. Upload gateway quét file và cấp document ID.
2. OCR worker không có quyền ghi HRM.
3. Application service tạo đề xuất.
4. Review UI xác nhận/sửa.
5. Workflow connector nhận approval token và idempotency key.
6. Audit store append-only.

Chi tiết quyết định engine tại [ADR-0001](adr/0001-pluggable-ocr-backends.md).

