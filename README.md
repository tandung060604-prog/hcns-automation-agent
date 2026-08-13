# VinHRIS — Cổng tác nghiệp tài liệu Hành chính - Nhân sự

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![OCR](https://img.shields.io/badge/OCR-PaddleOCR%20%2B%20EasyOCR-0A8FDC)](https://www.paddleocr.ai/)
[![Workflow](https://img.shields.io/badge/Workflow-Camunda%207.13-FF5A00)](https://camunda.com/platform-7/)
[![Privacy](https://img.shields.io/badge/Data-Local%20%2F%20Self--hosted-6B46C1)](#an-toàn-dữ-liệu)
[![CI](https://github.com/tandung060604-prog/hcns-automation-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/tandung060604-prog/hcns-automation-agent/actions/workflows/ci.yml)

VinHRIS là hệ thống Document AI chạy local, hỗ trợ tiếp nhận hồ sơ HCNS, đọc nội
dung, nhận diện biểu mẫu, trích xuất dữ liệu có cấu trúc và đưa các trường chưa
chắc chắn cho người dùng kiểm tra. Camunda 7 điều phối trạng thái quy trình; file
gốc, OCR text và dữ liệu chi tiết vẫn được giữ trong môi trường nội bộ.

> **Trạng thái sản phẩm:** MVP local-first đang hoạt động ở **shadow mode**.
> Hệ thống hỗ trợ demo end-to-end và đánh giá kỹ thuật, nhưng chưa tự tạo quyết
> định nhân sự hoặc ghi dữ liệu vào HRIS production.

## Giá trị chính

- Giảm nhập liệu lặp lại từ DOCX, PDF, ảnh scan và các biểu mẫu HCNS phổ biến.
- Ưu tiên native parser cho tài liệu có text; chỉ dùng OCR khi file thực sự cần.
- Gắn trạng thái, confidence và evidence vào từng trường để dễ đối chiếu.
- Luôn giữ con người trong vòng quyết định với xác nhận, chỉnh sửa, tải lại hoặc từ chối.
- Chỉ chuyển metadata và mã tham chiếu cần thiết sang Camunda, không đẩy file gốc vào workflow.

## Trạng thái hiện tại

| Thành phần | Trạng thái | Ý nghĩa thực tế |
|---|---|---|
| Universal document intake | Hoạt động | Nhận TXT, DOCX, PDF, XLSX, PPTX, PNG và JPG/JPEG |
| Template-first extraction | Hoạt động | CV/Hợp đồng nhận DOCX, PDF; IELTS/CCCD nhận PDF, PNG, JPG/JPEG theo manifest |
| OCR local | Hoạt động | PaddleOCR hoặc EasyOCR cho ảnh và PDF scan |
| Dashboard VinHRIS | Hoạt động | Upload, xem nguồn, nhập Ground Truth và đối chiếu từng field ngay trên localhost |
| Camunda 7 + Human-in-the-loop | Hoạt động ở shadow mode | Điều phối External Task/User Task, không tạo side effect nghiệp vụ thật |
| Kết quả local/idempotency | Đã gia cố | Ghi kết quả an toàn khi nhiều request chạy đồng thời |
| API dashboard | Chỉ local | Chỉ chấp nhận loopback Host và giới hạn kích thước request |
| Chất lượng scan nhạy cảm | Review-only | Confidence thấp hoặc scan chưa chắc chắn luôn cần người duyệt |

## Cập nhật mới nhất — 13/08/2026

- **Đối chiếu file hiện tại ngay sau upload:** màn hình thống nhất hiển thị tài
  liệu nguồn ở bên trái và Prediction, Ground Truth, confidence/evidence cùng
  badge `EXACT`, `ACCEPTED`, `MISMATCH`, `MISSING` hoặc `NEEDS_REVIEW` ở bên phải.
- **Kết luận rõ ràng:** mỗi lần đối chiếu có tổng số field đúng/sai và quyết định
  `HOLD`/`PASS`. `PASS` chỉ nói về phép so khớp file hiện tại; không tự phê duyệt
  nghiệp vụ và không mở promotion.
- **Metric mở được toàn bộ tài liệu nguồn:** DATA-29 hiển thị đủ 12 tài liệu đã
  trực tiếp tạo aggregate `107/112`, chia thành Contract `3`, CV `5`, IELTS `4`.
- **Metadata thuật toán có thể kiểm tra:** template/parser version, intake parser,
  OCR backend/version/model/device/profile, matching policy và thời gian xử lý
  được hiển thị cùng kết quả.
- **Đối chiếu đúng policy:** chi tiết từng tài liệu đọc matching policy `2.0.0`
  được pin trong chính report, nên số exact/accepted tái tạo cùng cách chấm DATA-29.
- **Explorer không trộn session upload:** khu vực evidence chỉ hiển thị source
  thuộc DATA-29; session upload vẫn được giữ private cho màn kết quả và Camunda.
- **Camunda cho ba họ tài liệu mới:** CV, hợp đồng thử việc và IELTS có thể đi từ
  kết quả upload vào local shadow workflow, bắt buộc Human Review và không tạo
  side effect HRIS/notification thật.
- **Baseline hiệu năng theo từng stage:** 30 warm run cho mỗi input class cho thấy
  DOCX/PDF text có p95 dưới `0,3 giây`, trong khi ảnh là `28,5 giây` và PDF scan
  là `67,5 giây` trên máy CPU 8 GB. Vì vậy chưa mở rộng CCCD/ảnh Contract; ưu
  tiên thống nhất parser path và tối ưu scan trước.

Các cập nhật hardening ngày 12/08/2026 vẫn được giữ nguyên:

- **An toàn khi xử lý đồng thời:** result store dùng file lock đa tiến trình, tránh
  hai request cùng ghi đè index hoặc tạo kết quả xung đột cho một idempotency key.
- **Biên API local rõ ràng hơn:** dashboard từ chối Host không phải loopback và
  trả `413` cho Camunda JSON body rỗng hoặc vượt giới hạn 2 MB.
- **Khởi tạo OCR ổn định:** PaddleOCR và EasyOCR lazy backend chỉ được khởi tạo
  một lần khi nhiều request đầu tiên đến cùng lúc.
- **CI chạy đúng toàn bộ test:** pipeline chuyển sang `pytest`, không còn bỏ sót
  test viết theo pytest style; fixture tạm hoạt động trên cả Windows và Linux.
- **Web contract đồng bộ giao diện:** rendered tests đã bám theo metadata và nội
  dung tiếng Việt hiện tại của VinHRIS.
- **Repository gọn và an toàn hơn:** hygiene checker chỉ kiểm tra file Git đang
  theo dõi; `.worktrees/`, `output/` và `tmp/` không bị quét hoặc đưa vào commit.

Chi tiết kỹ thuật và lịch sử xác minh nằm trong
[PROJECT_STATE](docs/PROJECT_STATE.md) và [HANDOFF](docs/HANDOFF.md).

## Luồng xử lý

```mermaid
flowchart TD
    A["Người dùng tải tài liệu"] --> B["Kiểm tra định dạng và chất lượng file"]
    B -->|"Có text layer"| C["Native parser"]
    B -->|"Ảnh hoặc PDF scan"| D["OCR local"]
    C --> E["Nhận diện loại tài liệu và template"]
    D --> E
    E --> F["Trích xuất và chuẩn hóa trường dữ liệu"]
    F --> G["Kiểm tra schema, confidence và dữ liệu thiếu"]
    G --> H["Người review nhập Ground Truth từ nguồn"]
    H --> I["Đối chiếu từng field và tạo HOLD/PASS"]
    I -->|"Cần xác minh"| J["Human review"]
    J -->|"Sửa hoặc xác nhận"| K["Business JSON"]
    J -->|"Yêu cầu tải lại"| A
    K --> L["Camunda điều phối trạng thái"]
    L --> M["Lưu kết quả và tham chiếu local"]
```

## Phạm vi tài liệu

| Nhóm tài liệu | Mức hỗ trợ | Chính sách hiện tại |
|---|---|---|
| Đơn xin nghỉ phép | End-to-end | Template-first, Camunda và Human-in-the-loop |
| Đơn xin tăng ca | End-to-end | Template-first, Camunda và Human-in-the-loop |
| CV | Local shadow E2E | DOCX/PDF; upload → extraction → Camunda → Human Review |
| Hợp đồng thử việc | Local shadow E2E | DOCX/PDF; không tự tạo quyết định nghiệp vụ |
| Chứng chỉ IELTS | Local shadow E2E | PDF/PNG/JPG/JPEG; ảnh đi qua OCR local và luôn cần người duyệt |
| CCCD mặt trước | Review-only | Chỉ dùng cho kiểm tra nội bộ, không tự phê duyệt |
| Hồ sơ chưa có schema | Intake/OCR | Không tự động đi tiếp cho đến khi có rule phù hợp |

Chưa tuyên bố hỗ trợ chữ viết tay, CCCD mặt sau hoặc tự động hóa quyết định
tuyển dụng, sa thải, lương, kỷ luật và phúc lợi.

## Bằng chứng chất lượng hiện có

Các số liệu dưới đây đến từ tập đánh giá local đã khóa, không phải cam kết chất
lượng production. Trạng thái promotion hiện vẫn là `HOLD` và
`promotionAllowed=false`.

| Phạm vi đánh giá | Kết quả | Diễn giải |
|---|---:|---|
| Leave + Overtime native | 30/30 chọn đúng template | 15 Leave Request và 15 Overtime Request |
| Leave + Overtime native | 0/30 lỗi validation | Đủ điều kiện chuyển đến bước Human review |
| Contract + CV + IELTS · DATA-29 | 107/112 field exact | Contract 42/42, CV 45/50, IELTS 20/20 |
| DATA-29 accepted | 112/112 field accepted | Matching policy v2; decision `HOLD`, không promotion |
| 12 tài liệu đang show | 107/112 exact, 112/112 accepted | Toàn bộ 3 Contract, 5 CV và 4 IELTS từ chính DATA-29 |
| Latency native warm p95 | DOCX 285 ms; PDF text 158 ms | 30 run/input class, local CPU 8 GB |
| Latency visual warm p95 | Ảnh 28,5 s; PDF scan 67,5 s | Chủ yếu nằm ở EasyOCR; chưa đạt gate mở rộng |
| JSON Schema | 0 lỗi | Kiểm tra cấu trúc trước khi chuyển workflow |

Dashboard chỉ hiển thị metric từ aggregate evidence đã seal. Inventory chỉ dùng
để đếm tài liệu local, không được dùng để tự tạo điểm số. Kết quả template v1 cũ
vẫn đọc được qua compatibility projection; kết quả mới phát ra theo contract v2.

## Chạy local

### Yêu cầu

- Python 3.10+
- Node.js 22+
- EasyOCR cho luồng Template-first mặc định; PaddleOCR chỉ cần khi dùng rollback
- Camunda 7.13 nếu cần demo workflow end-to-end

### Cài đặt

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1" # cần thiết nếu đường dẫn repo có ký tự tiếng Việt
python -m pip install -e ".[dev,easyocr]"

# Chỉ cài thêm khi cần rollback sang PaddleOCR
python -m pip install -e ".[paddle]"

Push-Location .\apps\ocr_lab\web
npm ci
Pop-Location
```

### Khởi động dashboard và API

```powershell
.\apps\ocr_lab\api\start_dashboard.ps1 `
  -DataRoot "C:\duong-dan\private-data" `
  -PythonPath ".\.venv\Scripts\python.exe"
```

Launcher mặc định chọn EasyOCR và chỉ báo sẵn sàng khi package của backend đang
chọn khả dụng. Dùng `-TemplateOcrBackend paddle` khi cần rollback rõ ràng. Mục
**System / Algorithm Version** trên workspace đọc trực tiếp `/health` để hiển thị
Template-first profile, OCR backend và parser/version của sáu template.

Sau khi khởi động:

- VinHRIS Dashboard: `http://localhost:3000`
- Local API: `http://127.0.0.1:8765`
- Camunda: `http://localhost:8080/camunda`

Hướng dẫn thao tác đầy đủ: [Demo Camunda + HITL](docs/DEMO_CAMUNDA_HITL.md).

Dashboard launcher đặt `HCNS_CAMUNDA_PRIVATE_ROOT` bằng đúng `DataRoot`. Worker
phải dùng cùng thư mục để giải tham chiếu UUID mà không đưa file hoặc field value
vào Camunda:

```powershell
$env:CAMUNDA_REST_URL = "http://127.0.0.1:8080/engine-rest"
$env:CAMUNDA_WORKER_ID = "hcns-local-shadow"
$env:HCNS_CAMUNDA_PRIVATE_ROOT = "C:\duong-dan\private-data"
hcns-agent-camunda-worker
```

### Demo nhanh cho user hoặc mentor

1. Mở `http://localhost:3000/workspace#explorer`.
2. Chọn **DATA-29 · 12 tài liệu metric · 3 Contract · 5 CV · 4 IELTS**.
3. Chọn bộ lọc Contract, CV hoặc IELTS rồi mở một tài liệu trong nhóm.
4. Kiểm tra source ở giữa và Prediction ↔ Ground Truth theo từng field bên phải.
5. Đối chiếu điểm riêng của file với aggregate toàn corpus phía trên.

DATA-29 source, Ground Truth, Prediction và report đều ở private local, không
commit vào Git. Đây là development corpus; tài liệu upload mới được đánh giá ở
màn kết quả upload và không làm thay đổi metric DATA-29.

## Kiểm thử

```powershell
python -m pytest -q
python -m ruff check src tests scripts `
  apps/ocr_lab/api/canonical_phase_metrics.py `
  apps/ocr_lab/api/local_server_security.py `
  apps/ocr_lab/api/phase14_review_store.py `
  apps/ocr_lab/api/upload_safety.py
python -m mypy src
python scripts/check_repository.py

Push-Location .\apps\ocr_lab\web
npm test
npm run lint
Pop-Location
```

Checkpoint hiện tại: Python `546 passed`; Camunda/Template subset `60 passed`;
frontend build và rendered-contract test `14/14`; mypy pass trên 90 source files;
Ruff, compileall, repository hygiene và diff check đều pass. ESLint có 0 error và
23 warning nền. Camunda 7.13 local shadow đã hoàn tất một CV và một IELTS qua HR
Review với incident bằng 0, HRIS/notification mô phỏng và
`autoContinueEnabled=false`. Contract còn chờ một tài liệu do người dùng upload
vào private root; DATA-29 không được dùng thay cho bước acceptance này.

## An toàn dữ liệu

- Không upload tài liệu HCNS lên cloud trong runtime local hiện tại.
- Không commit dataset, file upload, model weights, OCR output thật, secret hoặc PII.
- API dashboard chỉ nhận loopback Host; request Camunda được giới hạn kích thước.
- Camunda chỉ nhận scalar metadata và opaque result reference, không nhận raw Business JSON.
- Result store dùng idempotency key và khóa ghi để tránh kết quả trùng/xung đột.
- Trường thiếu, confidence thấp hoặc tài liệu scan luôn được chuyển sang Human review.
- Mọi action có thể tác động HRM/BPM cần policy cho phép và human approval.

## Kiến trúc repository

```text
src/hcns_agent/        Domain, application services, ports và adapters
apps/ocr_lab/api/      Local API và cầu nối Camunda
apps/ocr_lab/web/      Giao diện VinHRIS
camunda/               BPMN, DMN và cấu hình workflow
schemas/               JSON Schema cho output contract
tests/                 Contract, integration và regression tests
scripts/               Công cụ đánh giá và repository checks
docs/                  Kiến trúc, vận hành, tiến độ và bằng chứng
```

Nguyên tắc kiến trúc: native parser trước OCR, domain không phụ thuộc Camunda SDK,
Business JSON không đi qua process variables và mọi nhánh không chắc chắn phải
đi qua Human-in-the-loop.

## Tài liệu dành cho mentor và đội phát triển

- [Tổng quan tài liệu](docs/README.md)
- [Trạng thái kỹ thuật mới nhất](docs/PROJECT_STATE.md)
- [Kiến trúc hệ thống](docs/ARCHITECTURE.md)
- [Human-in-the-loop](docs/HUMAN_IN_THE_LOOP.md)
- [Phương pháp và metric đánh giá](docs/EVALUATION.md)
- [Hướng dẫn demo Camunda](docs/DEMO_CAMUNDA_HITL.md)
- [Demo đối chiếu CV/Contract/IELTS trên localhost](docs/DEMO_LOCAL_COMPARISON.md)
- [Báo cáo demo cho mentor](docs/DEMO_CAMUNDA_HITL_REPORT.md)
- [Handoff cho phiên phát triển tiếp theo](docs/HANDOFF.md)

## Giới hạn và hướng phát triển

Các hạng mục sau chưa được xem là tính năng production:

- Chữ viết tay và CCCD mặt sau.
- Tự động đưa ra quyết định nhân sự hoặc ghi trực tiếp vào HRIS.
- Tối ưu scan phức tạp: deskew, denoise, rotation và layout nhiều cột/bảng biểu.
- Promotion OCR cho các family đang ở trạng thái `HOLD`.
- DATA-29 là development corpus; `107/112` không chứng minh chất lượng
  trên tài liệu HCNS thật và không được dùng làm tuyên bố production-ready.
- Đóng gói production bằng Docker/GPU serving và quan sát vận hành hoàn chỉnh.
