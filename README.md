# HCNS Automation Agent

Nền tảng **Agent tự động hóa nghiệp vụ hành chính nhân sự** với Intelligent
Document Processing, Camunda orchestration và Human-in-the-loop.

> IDP đọc và hiểu tài liệu. Agent phân tích và đề xuất. Camunda điều phối quy
> trình và con người.

Sản phẩm tiếp nhận CV, hồ sơ nhân viên, giấy tờ định danh, hợp đồng, quyết định,
đơn từ, bảng chấm công/lương, chứng chỉ, quy chế, công văn và biểu mẫu. CCCD chỉ
là một document type; đây không phải ứng dụng OCR CCCD.

## Universal Document Intake

```text
file/reference
  → format detection + file safety
  → deterministic parser routing
  → native PDF/DOCX/XLSX hoặc OCR cho ảnh/PDF scan
  → Canonical Document Model + provenance
  → DocumentType classification + field extraction
  → validation/quality gate + Business JSON v2
  → durable result reference + small routing summary
  → Camunda BPMN/User Task
```

`SourceFormat`, `DocumentType` và `WorkflowType` độc lập. Format chỉ chọn parser;
classification nghiệp vụ và workflow routing là các bước khác có context riêng.
Parser native được ưu tiên để giữ page, paragraph, table, sheet, cell, formula
và merged range. OCR chỉ chạy cho ảnh hoặc PDF scan.

Safety gate không chỉ tin extension: nó kiểm tra MIME khai báo, magic bytes,
OOXML ZIP, giới hạn size/page/archive, ZIP path traversal, expansion ratio,
macro, encryption và corruption. Legacy DOC/XLS trả `CONVERSION_REQUIRED`,
không tự chạy Office hay executable chuyển đổi.

## Document understanding

Classifier và extractor là hai port riêng. Baseline rule-based local phân loại
CV, hợp đồng lao động, đơn nghỉ phép, bảng chấm công và biểu mẫu hành chính;
extractor được phê duyệt hiện có cho bốn loại đầu. Type chưa biết/chưa có
extractor, field thiếu/xung đột/confidence thấp hoặc field nhạy cảm đều chuyển
review. Quality score không tự cấp quyền ghi HRM/BPM.

Business JSON `2.0.0` giữ classification candidates, field/extractor provenance,
structured validation issues và quality status. Raw canonical document tiếp tục
nằm trong result store, không đi vào process variables.

## Camunda boundary

Camunda là nguồn sự thật cho BPMN, Service/User Task, timer, SLA, retry,
escalation, assignment, incident và process state dài hạn. IDP chỉ validate,
parse, classify, extract, quality-gate, lưu result, rồi trả `ResultReference`
cùng các biến routing nhỏ. Raw file, OCR output và canonical payload không đi
vào process variables.

Worker contract có business/correlation/idempotency key và phân biệt technical
error với business error. Kết quả phải lưu xong trước khi complete job; retry
cùng idempotency key không tạo result thứ hai. Milestone này chưa chạy Camunda
server, BPMN production, review UI hoặc side effect HRM/BPM thật.

## Chạy kiểm thử

Yêu cầu Python 3.10+.

```powershell
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check src tests scripts
python -m mypy src
python scripts/check_repository.py
```

55+ unit/contract tests dùng fixture hoàn toàn synthetic: CV PDF, hợp
đồng DOCX, bảng chấm công XLSX và biểu mẫu ảnh. Test không dùng network, model
weights, Camunda server hoặc dữ liệu thật.

Ví dụ composition root:

```python
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.application.business_json import BusinessJsonBuilder
from hcns_agent.bootstrap import build_default_pipeline
from hcns_agent.ports.document_parser import DocumentSource

pipeline = build_default_pipeline(DeterministicMockOcrEngine())
result = pipeline.execute(
    DocumentSource(
        document_id="SYNTHETIC-001",
        filename="form.png",
        content=synthetic_bytes,
    )
)
business_json = BusinessJsonBuilder().build(result)
```

PaddleOCR được load lazy trong adapter và chỉ cài khi cần:

```powershell
python -m pip install -e ".[paddle]"
```

## Repository

```text
src/hcns_agent/
├── domain/          # Canonical/IDP result, classifications và quality models
├── application/     # intake, understanding, quality gate và job handler
├── ports/           # parser/OCR/classifier/extractor/storage/orchestrator
└── adapters/        # native parsers, OCR, rule baseline và result store
docs/                # architecture, security, evaluation và ADR
tests/               # synthetic unit/contract tests
```

Đọc [kiến trúc](docs/ARCHITECTURE.md),
[bảo mật dữ liệu](docs/DATA_SECURITY.md),
[ADR-0002](docs/adr/0002-universal-document-intake-and-camunda-boundary.md) và
[ADR-0003](docs/adr/0003-document-understanding-and-quality-gate.md) cùng
[trạng thái dự án](docs/PROJECT_STATE.md) trước khi mở rộng.
