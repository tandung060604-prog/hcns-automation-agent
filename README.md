# HCNS Automation Agent

Nền tảng nghiên cứu **Agent tự động hóa nghiệp vụ hành chính nhân sự**:

- OCR giấy tờ và hồ sơ của bộ phận HCNS;
- chuẩn hóa kết quả thành dữ liệu nghiệp vụ có nguồn gốc;
- xây dựng workflow tự động có **Human-in-the-loop (HITL)**;
- giữ dữ liệu nhân sự nhạy cảm trong ranh giới triển khai được kiểm soát.

> Trạng thái: research scaffold. Chưa được dùng để tự động ra quyết định nhân sự
> hoặc ghi dữ liệu vào HRM/ERP khi chưa có phê duyệt của con người.

## Điểm khác biệt

```text
Tài liệu HCNS
    │
    ▼
OCR backend có thể thay thế
    │
    ▼
Phân loại + trích xuất + kiểm tra chất lượng
    │
    ├── đủ tin cậy ──► đề xuất hành động
    │
    └── thiếu/không chắc ──► hàng đợi Human Review
                                  │
                                  ▼
                         Phê duyệt / sửa / từ chối
                                  │
                                  ▼
                     Business JSON + audit trail
```

Agent **không được tự ý** tuyển dụng, sa thải, thay đổi lương, chấm công, nghỉ
phép hoặc dữ liệu định danh. Agent chỉ đọc, kiểm tra, đề xuất và thực thi các
hành động đã được policy cho phép.

## Phạm vi nghiệp vụ ưu tiên

1. Tiếp nhận và kiểm tra hồ sơ nhân viên.
2. OCR CCCD/hộ chiếu, CV, hợp đồng, quyết định, đơn từ và bảng chấm công.
3. Đối chiếu trường bắt buộc, phát hiện thiếu hoặc mâu thuẫn.
4. Tạo task cho chuyên viên HCNS xác nhận.
5. Sinh Business JSON và audit trail để tích hợp HRM/BPM sau phê duyệt.

Xem [tầm nhìn sản phẩm](docs/VISION.md), [kiến trúc](docs/ARCHITECTURE.md) và
[workflow mẫu](docs/WORKFLOWS.md).

## Kiến trúc repository

```text
src/hcns_agent/
├── domain/          # Entity, policy và trạng thái workflow
├── application/     # Use case điều phối OCR và HITL
├── ports/           # Hợp đồng OCR, review, storage, workflow
└── adapters/        # PaddleOCR, MinerU, mock và tích hợp ngoài
configs/             # Policy không chứa secret
schemas/             # JSON Schema cho dữ liệu trao đổi
docs/                # Model guide, bảo mật, đánh giá và ADR
tests/               # Unit/contract tests, không chứa PII thật
```

## Chạy nhanh

Yêu cầu Python 3.10+.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m hcns_agent.demo
```

Demo dùng OCR giả lập, không tải model và không xử lý PII thật.

Để dùng PaddleOCR local:

```powershell
python -m pip install -e ".[paddle]"
```

Khởi tạo backend trong application composition root:

```python
from hcns_agent.adapters.paddleocr import PaddleOcrEngine

ocr_engine = PaddleOcrEngine.from_default(device="cpu")
```

Model chỉ được tải trong `from_default`; import package và chạy unit test không
phát sinh network hoặc tải weights.

## Nguyên tắc phát triển

- OCR engine là adapter: PaddleOCR hiện là baseline; MinerU là challenger cho
  layout/bảng phức tạp.
- Không đổi engine mặc định nếu chưa benchmark trên cùng tập Ground Truth.
- Mọi trường nhạy cảm phải kèm confidence, provenance và trạng thái review.
- Mọi side effect nghiệp vụ phải idempotent và có audit trail.
- Dataset thật không nằm trong Git; test dùng dữ liệu synthetic.
- Đọc [AGENTS.md](AGENTS.md) trước khi dùng coding agent.

## Lộ trình gần

- Hoàn thiện bộ Ground Truth 30–50 trang HCNS được cấp quyền.
- Benchmark PaddleOCR và MinerU qua cùng `OcrEngine` contract.
- Hoàn thiện review queue và schema cho onboarding.
- Tích hợp BPM/HRM ở chế độ dry-run trước khi cho phép ghi thật.

Chi tiết tại [ROADMAP.md](docs/ROADMAP.md).
