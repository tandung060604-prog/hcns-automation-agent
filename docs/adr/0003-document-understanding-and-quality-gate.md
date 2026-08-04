# ADR-0003: Document understanding and quality gate

Status: Accepted

## Context

M1 kết thúc tại `CanonicalDocument`; Camunda summary luôn có
`DocumentType.UNKNOWN`. Sản phẩm cần classification, extraction và validation
nhưng không được trộn business type với format routing, không được auto-accept
field nhạy cảm và không được biến Agent thành workflow engine.

Business JSON v1 chỉ mô tả field OCR đơn giản, không có classification
candidates, extractor provenance, quality score hay structured validation
issues.

## Decision

1. `DocumentClassifier` là port độc lập `DocumentParser`. Classifier chỉ đọc
   canonical content và không thay đổi parser routing.
2. Baseline đầu tiên là deterministic local rules có tên/version, candidates,
   confidence và source-location evidence. Nó chưa phải model production.
3. `FieldExtractorRegistry` đăng ký một extractor cho mỗi `DocumentType` và từ
   chối duplicate. M5 hỗ trợ sáu template review-first: CV, IELTS, hợp đồng thử việc,
   đơn nghỉ, tăng ca và CCCD mặt trước.
4. Field giữ value, confidence, sensitivity, extractor name/version và source
   evidence. Không lưu object parser/model.
5. Quality gate kiểm tra required field, confidence, sensitivity, duplicate
   conflict, ISO date/range, parser warning và extractor availability.
6. Field nhạy cảm, output thiếu/không chắc chắn hoặc type chưa có extractor luôn
   chuyển Human Review; quality gate không tự phê duyệt side effect.
7. `IdpResult` chứa canonical result, classification, validated fields và
   `QualityReport`. Durable store lưu toàn bộ IDP result trước khi complete job.
8. Business JSON nâng lên schema `2.0.0`; `fields` là array để giữ được nhiều
   candidate xung đột và provenance. Camunda vẫn chỉ nhận result reference cùng
   summary nhỏ.

## Consequences

- Camunda condition có thể dùng `documentType`, `qualityStatus` và
  `reviewRequired` mà không nhận raw content.
- Retry cùng idempotency key trả cùng classified result reference.
- Consumer Business JSON v1 phải migrate sang v2; đây là breaking schema change.
- Rule baseline chỉ là kiểm chứng architecture/contract. Promotion accuracy cần
  Ground Truth, per-type metrics và versioned model/rules.
- Document type chưa được hỗ trợ không bị giả vờ extract thành công; nó nhận
  `NO_FIELD_EXTRACTOR` và review.

## Rejected alternatives

- Suy ra `DocumentType` từ extension/parser: trộn technical và business routing.
- Một extractor tổng quát cho mọi loại tài liệu: khó kiểm chứng required fields
  và provenance.
- Quality score cao tự động bỏ qua field sensitivity: vi phạm HITL policy.
- Đưa raw Business JSON vào process variables: tăng rủi ro PII và payload lớn.
