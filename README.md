# VinHRIS — Document AI cho tác nghiệp HCNS

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Workflow](https://img.shields.io/badge/Workflow-Camunda%207.13-FF5A00)](https://camunda.com/platform-7/)
[![Data](https://img.shields.io/badge/Data-Local%20%2F%20Self--hosted-6B46C1)](#an-toàn-dữ-liệu)
[![CI](https://github.com/tandung060604-prog/hcns-automation-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/tandung060604-prog/hcns-automation-agent/actions/workflows/ci.yml)

VinHRIS nhận tài liệu hành chính – nhân sự, trích xuất dữ liệu có cấu trúc và
đưa mọi điểm chưa chắc chắn qua Human Review. Hệ thống ưu tiên native parser
cho tài liệu có text; OCR chỉ chạy local khi ảnh hoặc PDF scan thực sự cần đọc.

> **Trạng thái:** local/shadow, chưa phải production. Chưa có authentication,
> RBAC, notification thật, HRIS side effect hoặc deployment internet-facing.

## Năng lực hiện có

- Tiếp nhận DOCX, PDF, PNG và JPG/JPEG với kiểm tra extension, MIME, magic
  bytes, giới hạn kích thước/trang và Office archive safety.
- Sáu nhóm tài liệu: CCCD mặt trước, chứng chỉ IELTS, CV, hợp đồng thử việc,
  đơn nghỉ phép và đơn tăng ca.
- Kết quả có schema, confidence, provenance, parser/OCR version và action đề
  xuất; tài liệu scan hoặc field nhạy cảm luôn giữ `MANUAL_REVIEW`.
- Camunda 7 local shadow nhận opaque reference/scalar metadata, không nhận file
  gốc hoặc raw Business JSON; HRIS và notification vẫn là mô phỏng.
- Dashboard local có upload, source preview, structured result và đối chiếu
  evidence theo policy.

## Luồng xử lý

```text
Upload local
  → kiểm tra an toàn
  → native parser hoặc OCR local
  → nhận diện template + validate schema
  → evidence / confidence
  → Human Review
  → Camunda shadow bằng opaque references
```

Không có bước nào trong luồng trên tự động phê duyệt tuyển dụng, nghỉ phép,
lương, kỷ luật hoặc thay đổi HRIS.

## Cấu trúc repository

```text
hcns-automation-agent/
├── apps/ocr_lab/          # Local API, frontend và hướng dẫn vận hành
├── src/hcns_agent/        # Domain, application services và adapters
├── schemas/               # Business/template/Camunda schemas
├── config/                # Policy và template manifest đang active
├── camunda/               # BPMN, DMN và asset Camunda 7
├── scripts/               # Tool kiểm tra, benchmark và local operation
├── tests/                 # Test synthetic, không đọc private data
├── docs/                  # Kiến trúc, policy, đánh giá và handoff
│   └── archive/           # Evidence/tài liệu lịch sử và DOCX master v1
└── Plan.md                # Roadmap website, RBAC và deployment
```

`config/` là nguồn policy active. Các vật liệu lịch sử được giữ trong
`docs/archive/`; không dùng cho luồng mới nếu chưa có quyết định versioning.
Dataset thật, Ground Truth, OCR output, model weights, uploads và secret không
thuộc repository này.

## Chạy local

### Yêu cầu

- Python 3.10+
- Node.js 22+
- EasyOCR cho Template-first mặc định; PaddleOCR chỉ dùng khi cần rollback
- Camunda 7.13 khi cần demo workflow end-to-end

### Cài đặt

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"
python -m pip install -e ".[dev,easyocr]"

Push-Location .\apps\ocr_lab\web
npm ci
Pop-Location
```

Chỉ cài PaddleOCR khi cần rollback rõ ràng:

```powershell
python -m pip install -e ".[paddle]"
```

Khởi động API và frontend local:

```powershell
.\apps\ocr_lab\api\start_dashboard.ps1 `
  -DataRoot "C:\duong-dan\private-data" `
  -PythonPath ".\.venv\Scripts\python.exe"
```

- Dashboard: `http://localhost:3000`
- Local API: `http://127.0.0.1:8765`
- Camunda: `http://localhost:8080` khi đã chạy riêng

Hướng dẫn vận hành chi tiết: [apps/ocr_lab/README.md](apps/ocr_lab/README.md).

## Mẫu tải về và dataset private

Frontend phát hành bốn DOCX trống, có placeholder, tại các URL ổn định:

- `/templates/cv-v2.docx`
- `/templates/probation-contract-v2.docx`
- `/templates/leave-request-v1.docx`
- `/templates/overtime-request-v1.docx`

CCCD và IELTS không có mẫu giả: chỉ upload ảnh/PDF thật, rõ nét và đầy đủ.
Dataset để mentor/partner trải nghiệm được quản lý riêng ở repository private
[`vinhris-document-ai-dataset`](https://github.com/tandung060604-prog/vinhris-document-ai-dataset).
Clone riêng dataset, chọn file trong sáu thư mục `data/` và upload thủ công;
tuyệt đối không copy dataset vào Docker image, frontend bundle hay deployment
public.

GitHub Pages chỉ là static/read-only demo. Artifact có asset trình bày và bốn
DOCX mẫu, nhưng không có API, private dataset, Ground Truth hay phiên upload.

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

CI chạy Python 3.10/3.12, frontend build/rendered tests, lint, mypy, compile
check và repository hygiene. Không dùng corpus private hoặc OCR cloud trong test.

## An toàn dữ liệu

- API local chỉ bind loopback; không mở port trực tiếp ra LAN/Internet.
- Không commit PII, dataset, uploads, Ground Truth, OCR output, model weights,
  token hay file `.env`.
- Chỉ dùng policy đã phê duyệt, idempotency key và Human Review trước mọi action
  có thể tác động hệ thống HRM/BPM.
- Không gửi tài liệu HCNS lên cloud/API bên ngoài trong runtime local hiện tại.

## Tài liệu

| Nhu cầu | Tài liệu |
| --- | --- |
| Trạng thái, rủi ro và next task | [PROJECT_STATE](docs/PROJECT_STATE.md) |
| Handoff giữa các workstream | [HANDOFF](docs/HANDOFF.md) |
| Backlog và acceptance criteria | [BACKLOG](docs/BACKLOG.md) |
| Kiến trúc | [ARCHITECTURE](docs/ARCHITECTURE.md) |
| Workflow và Human Review | [WORKFLOWS](docs/WORKFLOWS.md), [HUMAN_IN_THE_LOOP](docs/HUMAN_IN_THE_LOOP.md) |
| Bảo mật PII | [DATA_SECURITY](docs/DATA_SECURITY.md) |
| Model, OCR và đánh giá | [MODEL_GUIDE](docs/MODEL_GUIDE.md), [EVALUATION](docs/EVALUATION.md) |
| Roadmap app/RBAC/deploy | [Plan.md](Plan.md) |

Xem đầy đủ tại [docs/README.md](docs/README.md). Quy tắc đóng góp, boundary và
PII safety nằm trong [AGENTS.md](AGENTS.md).

## Quy ước thay đổi

1. Thay đổi nhỏ, có test tương ứng và không đưa private data vào diff.
2. Policy/schema/interface công khai phải cập nhật tài liệu hoặc contract test.
3. Không xóa artifact lịch sử hoặc migration compatibility khi chưa xác nhận
   không còn consumer; chuyển vào `docs/archive/` khi cần giữ traceability.
4. Chỉ merge khi CI xanh và thay đổi không làm nới quyền tự động của workflow.
