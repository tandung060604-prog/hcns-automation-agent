# HCNS Automation Agent

Nền tảng xử lý tài liệu hành chính nhân sự tiếng Việt theo hướng **Intelligent
Document Processing (IDP)**, kết hợp quy trình kiểm duyệt của con người và khả
năng điều phối bằng Camunda.

> IDP đọc và chuẩn hóa tài liệu. Agent phân tích và đề xuất. Camunda điều phối
> quy trình. Con người phê duyệt các quyết định quan trọng.

Dự án được thiết kế để tiếp nhận nhiều loại hồ sơ HCNS, trích xuất dữ liệu có
bằng chứng, đánh giá chất lượng và tạo Business JSON sẵn sàng cho tầng quy trình.
CCCD chỉ là một trong nhiều loại tài liệu được hỗ trợ; mục tiêu của dự án không
giới hạn ở nhận dạng giấy tờ định danh.

## Mục tiêu

- Tiếp nhận thống nhất ảnh, PDF, DOCX, XLSX và PPTX.
- Ưu tiên trích xuất native với tài liệu có lớp văn bản; chỉ dùng OCR cho ảnh
  hoặc PDF scan.
- Chuẩn hóa kết quả về Canonical Document Model có provenance.
- Phân loại tài liệu, trích xuất trường nghiệp vụ và kiểm tra chất lượng.
- Không tự suy đoán hoặc âm thầm điền trường thiếu bằng AI.
- Chuyển trường không chắc chắn sang `needs_review` để con người đối chiếu.
- Tạo Business JSON nhỏ gọn, có version và phù hợp để Camunda định tuyến.
- Giữ tài liệu thật, OCR output và PII trong môi trường local/private.

## Luồng xử lý tổng thể

```text
Tài liệu hoặc document reference
  → kiểm tra định dạng và an toàn tệp
  → chọn native parser hoặc OCR
  → Canonical Document Model + provenance
  → phân loại DocumentType
  → trích xuất trường và bảng
  → validation + quality gate
  → PASS / REVIEW / REJECT
  → Business JSON + resultReference
  → Camunda Service Task / User Task
```

Ba khái niệm được tách biệt:

- `SourceFormat` quyết định cách đọc tệp.
- `DocumentType` quyết định extractor nghiệp vụ.
- `WorkflowType` là ngữ cảnh quy trình do Camunda quản lý.

Thiết kế này giúp thay OCR backend hoặc mở rộng loại tài liệu mà không đưa logic
Camunda vào domain của IDP.

## Khả năng hiện có

### Tiếp nhận đa định dạng

| Định dạng | Cách xử lý ưu tiên |
|---|---|
| PNG, JPG, JPEG | OCR engine thông qua `OcrEngine` port |
| PDF có text layer | Native PDF extraction |
| PDF scan hoặc hybrid | Native extraction kết hợp OCR khi cần |
| DOCX | Đọc paragraph và table trực tiếp |
| XLSX | Đọc sheet, cell, formula và merged range trực tiếp |
| PPTX | Trích xuất text theo slide |
| DOC, XLS legacy | Trả `CONVERSION_REQUIRED`; không tự chạy Office |

Safety gate kiểm tra MIME, magic bytes, cấu trúc OOXML ZIP, giới hạn dung lượng,
page count, archive expansion ratio, path traversal, macro, encryption và file
hỏng. Hệ thống không chỉ tin phần mở rộng của tên tệp.

### Document understanding

Kiến trúc đã có classifier và extractor độc lập, với baseline deterministic cho:

- CV;
- hợp đồng lao động;
- đơn xin nghỉ phép;
- bảng chấm công;
- phiếu và biểu mẫu hành chính nhân sự.

Các trường được trả kèm nguồn bằng chứng như trang, block, bounding box,
sheet/row/cell hoặc source reference. Document type chưa chắc chắn, extractor
chưa được phê duyệt, trường thiếu/xung đột hoặc confidence thấp đều phải qua
Human-in-the-loop.

### Quality gate và Business JSON

Quality gate đánh giá required field, confidence, validation, xung đột, trường
nhạy cảm và khả năng truy nguyên. Kết quả sử dụng ba trạng thái:

- `PASS`: đủ điều kiện kỹ thuật theo policy hiện hành;
- `REVIEW`: cần người có thẩm quyền kiểm tra;
- `REJECT`: đầu vào không hợp lệ hoặc không thể xử lý an toàn.

Business JSON `2.0.0` chứa classification candidates, field provenance,
validation issues, quality status và `resultReference`. Raw file, toàn bộ OCR
text và Canonical Document payload không được đưa vào process variables.

## Benchmark có thể kiểm chứng

Benchmark harness chạy offline và áp dụng cùng một `IdpResult` contract cho
baseline lẫn challenger. Các nhóm metric gồm:

- OCR CER, WER và exact reading order;
- classification accuracy theo loại tài liệu;
- field exact match và document completeness;
- false `PASS`/`REJECT`, review rate và sensitive false acceptance;
- latency, failure rate và promotion gate.

Ground Truth, prediction chứa field value và tài liệu nguồn phải nằm ngoài Git.
Report trong repository chỉ được chứa metric tổng hợp, không chứa raw PII.

```powershell
hcns-agent-benchmark evaluate `
  --ground-truth <authorized-ground-truth.json> `
  --predictions <baseline-predictions.json> `
  --output <aggregate-report.json>
```

Challenger chỉ được promote khi sử dụng đúng cùng dataset version/digest, cải
thiện metric mục tiêu và không làm tăng false `PASS`, sensitive false acceptance
hoặc rủi ro vận hành.

Để chẩn đoán riêng lỗi mất dấu tiếng Việt, Phase 13.1 có CLI recognition-only:

```powershell
hcns-agent-recognition audit-charset `
  --dictionary <recognition-dictionary.txt> `
  --model-identifier <model-id> `
  --output <charset-audit.json>

hcns-agent-recognition evaluate `
  --ground-truth <private-line-ground-truth.json> `
  --predictions <private-recognizer-predictions.json> `
  --output <aggregate-recognition-report.json>
```

Report chỉ chứa CER, WER, Exact Match, Diacritic Error Rate, accepted precision
và latency; raw text vẫn nằm ngoài Git.

Từ Phase 14.6, các phase recognition dùng chung metric spec
`vi-ocr-metrics/1.0.0`. Exact Match giữ nguyên hoa/thường và dấu câu; agreement
sau `casefold` được báo cáo riêng. DER dùng số ký tự reference có dấu làm mẫu
số, nên report cũ trước spec này không được so trực tiếp.

Phase 13.2 đã chạy ba recognizer trên cùng corpus synthetic 240 crop dòng:
EasyOCR `vi` đạt 82,92% Exact Match và 0% DER, được chọn cho pilot; VietOCR
`vgg_seq2seq` làm recognizer kiểm chứng. Đây chưa phải tuyên bố production:
trường chỉ được auto-accept khi hai engine đồng thuận và validation đạt, nếu
không sẽ chuyển `needs_review`.

Phase 13.3 đã tích hợp chuỗi Paddle detector → EasyOCR → VietOCR verifier và
thử trên 15 CCCD scan thật đã xác nhận Ground Truth. Chỉ 18/671 dòng đồng thuận
(2,68%), document CER hybrid 68,74%; vì vậy quyết định hiện tại là
`NOT_PROMOTED`. Kết quả này xác nhận corpus synthetic chưa đủ để thay recognizer
production và mọi dòng bất đồng vẫn phải qua human review.

Phase 14 đã mở rộng Ground Truth lên 309/309 crop của 15 tài liệu thật có quyền
sử dụng. Benchmark mù chọn VietOCR `vgg_seq2seq` (30,74% Exact Match,
18,19% CER) thay vì `vgg_transformer` (27,18% Exact Match, 14,16% CER); model
Transformer chậm hơn và không đạt promotion gate. Khi tính lại theo metric spec
1.0.0, Phase 14.5 fallback document-level đạt 40,13% Exact Match nhưng làm mất
một dòng primary vốn
đúng; vì vậy chỉ chạy `SHADOW_REVIEW_ONLY`. Pipeline vẫn
`NOT_PRODUCTION_READY`; prediction bất đồng tiếp tục đi qua human review.

Phase 14.6 đã khóa `bbox_balanced_64`, policy review-only và SHA-256 của
VietOCR seq2seq, VietOCR transformer cùng Paddle detector. Khi dataset mới sẵn
sàng, hệ thống phải tạo prediction ẩn trước, xác nhận Ground Truth từ ảnh gốc,
rồi đánh giá một lần mà không chỉnh threshold trên tập held-out.

## OCR Lab local

Source website và API local nằm tại [`apps/ocr_lab`](apps/ocr_lab/README.md).
Giao diện hỗ trợ upload, xem evidence/JSON, xác nhận Ground Truth dòng và tiếp
tục đúng crop chưa review sau khi tải lại trang. Upload được kiểm tra magic
content, format mismatch, encryption, macro, archive expansion và page limit
trước parser/OCR.

## Camunda và Human-in-the-loop

Camunda là nguồn sự thật cho BPMN, Service Task, User Task, timer, SLA, retry,
escalation, assignment, incident và process state dài hạn. IDP worker chỉ xử lý
một job hữu hạn, lưu kết quả bền vững rồi trả `resultReference` cùng routing
summary.

Repository có package tham chiếu:

- [`camunda/HR_DOCUMENT_AGENT_MVP_V2.bpmn`](camunda/HR_DOCUMENT_AGENT_MVP_V2.bpmn)
- [`camunda/HR_DOCUMENT_QUALITY_ROUTING.dmn`](camunda/HR_DOCUMENT_QUALITY_ROUTING.dmn)

Package hiện là tài sản thiết kế dành cho review/dry-run, chưa phải xác nhận đã
deploy production. **Liên kết Camunda Modeler/Operate/Tasklist sẽ được cập nhật
sau khi môi trường tích hợp được công bố.**

Xem thêm [thiết kế workflow](docs/WORKFLOWS.md) và
[Human-in-the-loop](docs/HUMAN_IN_THE_LOOP.md).

## Cài đặt

Yêu cầu Python 3.10 trở lên.

```powershell
git clone https://github.com/tandung060604-prog/hcns-automation-agent.git
cd hcns-automation-agent

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

PaddleOCR là dependency tùy chọn và được load lazy:

```powershell
python -m pip install -e ".[paddle]"
```

MinerU challenger:

```powershell
python -m pip install -e ".[mineru]"
```

Không cài cả hai backend nếu chỉ cần chạy unit/contract tests.

## Chạy kiểm thử

```powershell
python -m unittest discover -s tests -v
python -m ruff check src tests scripts
python -m mypy src
python scripts/check_repository.py
```

Test sử dụng fixture synthetic, không cần network, model weights, Camunda server
hoặc tài liệu thật.

## Ví dụ sử dụng pipeline

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
        content=b"synthetic-content",
    )
)
business_json = BusinessJsonBuilder().build(result)
```

## Cấu trúc repository

```text
src/hcns_agent/
├── domain/          # Canonical model, IDP result, quality và evaluation
├── application/     # intake, understanding, benchmark và job handling
├── ports/           # parser, OCR, classifier, extractor và orchestration
└── adapters/        # native parsers, OCR, storage và benchmark JSON

schemas/             # JSON Schema cho Business JSON và benchmark
camunda/             # BPMN/DMN package tham chiếu
configs/             # policy cấu hình được version hóa
docs/                # kiến trúc, bảo mật, evaluation, workflow và ADR
tests/               # synthetic unit/contract/architecture tests
scripts/             # repository quality checks
```

## An toàn dữ liệu

- Không commit dataset, model weights, upload, Ground Truth riêng tư hoặc OCR
  output thật.
- Không gửi tài liệu HCNS lên cloud/API nếu chưa có phê duyệt rõ ràng.
- Không đặt raw file, raw OCR hoặc PII đầy đủ trong Camunda process variables.
- Không tự động hóa quyết định tuyển dụng, sa thải, lương, kỷ luật hoặc phúc lợi.
- Mọi hành động ghi HRM/BPM phải có policy, idempotency key và human approval.

Đọc [chính sách an toàn dữ liệu](docs/DATA_SECURITY.md) trước khi chạy với tài
liệu thật.

## Trạng thái dự án

Dự án hiện ở giai đoạn benchmark có thể kiểm chứng:

- Universal Document Intake và native/OCR routing đã có.
- Canonical model, classifier, extractor và quality gate đã có.
- Benchmark baseline/challenger và promotion gate đã có.
- Benchmark recognition-only và audit charset tiếng Việt đã có.
- EasyOCR đã được chọn cho pilot recognition; VietOCR dùng để kiểm chứng.
- Camunda BPMN/DMN package tham chiếu đã được bổ sung.
- Benchmark trên tài liệu thật có quyền sử dụng và triển khai Camunda thực tế
  vẫn đang chờ phê duyệt.

Các baseline rule-based và fixture synthetic dùng để kiểm tra kiến trúc/contract,
không phải tuyên bố độ chính xác production. Xem
[trạng thái dự án](docs/PROJECT_STATE.md), [kiến trúc](docs/ARCHITECTURE.md),
[đánh giá](docs/EVALUATION.md) và [lộ trình](docs/ROADMAP.md).

## Giấy phép và đóng góp

Các dependency và model backend tuân theo giấy phép riêng của từng dự án. Trước
khi đưa model hoặc dataset mới vào benchmark, cần ghi rõ nguồn, version, license
và phạm vi sử dụng.

Khi đóng góp, hãy chạy đầy đủ quality gates, không đưa dữ liệu thật vào commit và
đảm bảo thay đổi public contract được cập nhật bằng test cùng tài liệu liên quan.
