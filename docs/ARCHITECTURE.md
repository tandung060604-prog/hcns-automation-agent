# Architecture

## Nguyên tắc phân trách nhiệm

> IDP đọc và hiểu tài liệu. Agent phân tích và đề xuất. Camunda điều phối quy
> trình và con người.

Hệ thống dùng Ports and Adapters. `domain/` không import framework, filesystem
hay SDK. `application/` chỉ phụ thuộc domain và Protocol trong `ports/`.
PaddleOCR, PyMuPDF, OOXML parser, storage và Camunda/Zeebe chỉ xuất hiện ở
adapter hoặc composition root.

```text
DocumentSource
  → FormatDetector
  → FileSafetyValidator
  → DocumentParserRegistry
      ├─ IMAGE      → ImageDocumentParser → OcrEngine
      ├─ PDF_TEXT   → NativePdfDocumentParser
      ├─ PDF_SCAN   → ScannedPdfDocumentParser → rasterizer → OcrEngine
      ├─ PLAIN_TEXT → PlainTextDocumentParser
      ├─ DOCX       → DocxDocumentParser
      ├─ XLSX       → XlsxDocumentParser
      └─ PPTX       → extension point
  → CanonicalDocument
  → DocumentClassifier
  → FieldExtractorRegistry
  → ValidationQualityGate
  → IdpResult + Business JSON v2
  → ResultStore
  → result reference + documentType/quality/review summary
  → Camunda BPMN
```

Native parser luôn được ưu tiên. OCR chỉ là dependency của parser ảnh và PDF
scan, không phải trung tâm hệ thống. Tài liệu và canonical result lớn nằm trong
storage được kiểm soát; Camunda chỉ nhận reference và biến routing nhỏ.

## Ba lớp phân loại độc lập

- `SourceFormat` chọn parser kỹ thuật: PLAIN_TEXT, IMAGE, PDF_TEXT, PDF_SCAN,
  DOCX, XLSX, PPTX, LEGACY_DOC, LEGACY_XLS hoặc UNKNOWN.
- `DocumentType` chọn extractor nghiệp vụ trong sáu họ active: CV, IELTS,
  probation contract, leave, overtime và CCCD mặt trước.
- `WorkflowType` là context quy trình do Camunda điều phối.

Format detection không suy ra `DocumentType`. `DocumentType` không tự quyết
định `WorkflowType` nếu thiếu context nghiệp vụ.

## Canonical Document Model

`CanonicalDocument` biểu diễn chung tài liệu phân trang, nội dung không phân
trang và workbook. Paragraph, heading, list, table, sheet/cell/formula, ảnh
nhúng, key/value, bounding box, confidence và source location đều giữ
provenance. Model chỉ chứa kiểu Python chuẩn; object của PaddleOCR, PyMuPDF,
python-docx, openpyxl, Camunda hoặc Zeebe không được đi qua boundary này.

`DocumentParser` công bố tên/version ổn định và capability theo `SourceFormat`.
Registry từ chối đăng ký trùng format nên routing không phụ thuộc thứ tự import.
PPTX được thêm bằng một parser mới, không sửa domain hoặc use case.

## Document understanding

### Template-first MVP boundary

MVP Phase 1 đặt một closed-set layer sau native DOCX parsing. `TemplateRegistry`
nhận diện bằng anchor trong `CanonicalDocument`, sau đó gọi parser và validator
versioned của đúng template. Filename không tham gia phân loại.

```text
DOCX -> safety -> native OOXML -> CanonicalDocument
     -> TemplateRegistry -> template parser -> validator
     -> AUTO_CONTINUE | MANUAL_REVIEW | REJECT_UNSUPPORTED
```

Registry mặc định chứa đúng sáu template versioned của M5. Pipeline
classifier/extractor generic vẫn tồn tại để tương thích, nhưng endpoint
`/api/documents/process` không dùng nó làm fallback cho tài liệu ngoài closed set.
Quyết định này được ghi tại
[ADR-0004](adr/0004-template-first-closed-set-mvp.md).

`DocumentClassifier` chỉ đọc canonical content; nó không nhìn extension để chọn
business type và không thay đổi parser. Baseline local deterministic trả
candidate, confidence, rule version và source-location evidence. Accuracy
production phải qua Ground Truth/promotion gate.

`FieldExtractorRegistry` map `DocumentType` sang extractor nghiệp vụ. M5 có
template/parser review-first cho CV, IELTS, probation contract, leave, overtime và CCCD mặt trước. Field giữ
value, confidence, sensitivity, extractor name/version và page/block hoặc
sheet/cell provenance.

`ValidationQualityGate` kiểm required field, confidence, sensitivity, duplicate
conflict, ISO date/range, parse warning và extractor availability. Kết quả là
`QualityReport(PASS|REVIEW_REQUIRED|REJECTED)`. Type chưa có extractor hoặc field
nhạy cảm luôn cần review; quality score không tự cấp quyền side effect.

Business JSON `2.0.0` là projection nhỏ từ `IdpResult`, không chứa raw file hoặc
toàn bộ canonical document. Chi tiết migration tại
[ADR-0003](adr/0003-document-understanding-and-quality-gate.md).

## Evaluation boundary

M3 benchmark nhận `IdpResult` qua một adapter vendor-neutral rồi so với Ground
Truth versioned. Baseline và challenger không được có đường metric riêng; cả hai
phải dùng cùng dataset ID/version/digest và cùng prediction contract.

```text
authorized Ground Truth ─┐
                         ├─ BenchmarkHarness ─ aggregate report
IdpResult predictions ───┘                    └─ PromotionGate
```

Ground Truth và prediction có field value nằm ngoài Git. `BenchmarkReport` chỉ
chứa count/rate, type/field name chuẩn, backend/model identifier, dataset
version/digest và latency/failure aggregate. Promotion gate là kiểm soát phát hành,
không ghi Camunda/HRM, không thay đổi `QualityReport` và không cấp quyền side effect.

## Safety trước parsing

Format detector kết hợp extension, declared MIME, magic bytes và cấu trúc OOXML
ZIP. `FileSafetyValidator` chạy trước parser và áp dụng giới hạn byte, số trang
PDF, số entry ZIP, tổng kích thước giải nén và compression ratio; chặn ZIP path
traversal, macro, file mã hóa/hỏng và legacy format cần chuyển đổi. Parser không
chạy macro, embedded executable hay tự follow external resource.

## Camunda boundary

Application nhận `DocumentJobRequest` có business/correlation/idempotency key,
schema version và timeout metadata. `IdpResult` phải được `ResultStore` lưu bền vững
trước khi gọi `ProcessOrchestratorPort.complete_document_job`. Technical error
và business error dùng taxonomy riêng. Retry cùng idempotency key phải trả cùng
result reference và không lặp side effect.

Camunda chịu trách nhiệm BPMN, Service/User Task, timer, SLA, retry ở cấp quy
trình, escalation, assignment, incident, compensation, versioning và process
state dài hạn. IDP không có review queue, scheduler hoặc state machine cạnh
tranh. Custom review UI sau này chỉ hiển thị provenance và hoàn thành User Task
do Camunda quản lý.

`domain/workflow.py` cũ từng chứa `WorkflowCase` và transition graph dài hạn.
API đó bị loại bỏ theo [ADR-0002](adr/0002-universal-document-intake-and-camunda-boundary.md);
business invariant cục bộ phải nằm trong policy/use case tương ứng, còn trạng
thái quy trình thuộc Camunda.

## Ranh giới triển khai

1. Upload gateway cấp document ID và kiểm tra size ban đầu.
2. IDP worker validate, parse, classify, extract, quality-gate và lưu IDP result.
3. Agent đọc Business JSON/result reference để phân tích/đề xuất trong task.
4. Camunda đánh giá BPMN condition và tạo User Task khi cần.
5. Review UI truy nguồn page/block/sheet/cell từ canonical model.
6. Connector HRM/BPM chỉ chạy sau policy và approval; milestone này chưa có
   side effect thật.

Chiến lược OCR backend được ghi tại
[ADR-0001](adr/0001-pluggable-ocr-backends.md).
