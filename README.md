# HCNS Automation Agent

[![CI](https://github.com/tandung060604-prog/hcns-automation-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/tandung060604-prog/hcns-automation-agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-Web-3178C6?logo=typescript&logoColor=white)
![OCR](https://img.shields.io/badge/OCR-EasyOCR%20vi--greedy-0A8FDC)
![Workflow](https://img.shields.io/badge/Workflow-Camunda%207.13-FF5A00)
![Privacy](https://img.shields.io/badge/PII-Private%20by%20default-6B46C1)
![Status](https://img.shields.io/badge/Status-Local%20UAT%20passed-16745A)

> Hệ thống đọc và xử lý hồ sơ hành chính nhân sự bằng AI, ưu tiên giữ dữ liệu trên
> máy nội bộ, kiểm tra kết quả trước khi chuyển cho người duyệt và quy trình nghiệp vụ.

Tính đến **03/08/2026**, luồng hai biểu mẫu HCNS đã chạy được trên máy local qua
dashboard; công việc tiếp theo là hoàn thiện dữ liệu mở rộng và quy trình người duyệt.

## Sản phẩm này làm gì?

HCNS Automation Agent nhận một hồ sơ như đơn nghỉ phép, đơn tăng ca, CV, hợp đồng
hoặc giấy tờ nhân sự; sau đó:

1. kiểm tra file có đúng định dạng và an toàn hay không;
2. đọc trực tiếp nội dung nếu file đã có chữ, hoặc dùng OCR nếu là ảnh/PDF scan;
3. nhận diện loại hồ sơ và lấy ra các trường cần thiết;
4. kiểm tra dữ liệu có đủ, đúng mẫu và có bằng chứng hay không;
5. tự chuyển kết quả đủ tin cậy sang bước tiếp theo, hoặc đưa trường chưa chắc chắn
   cho người dùng kiểm tra;
6. tạo JSON gọn để hệ thống quy trình Camunda có thể tiếp nhận.

Bản MVP (phiên bản nhỏ nhất đã chạy được) đang tập trung vào hai biểu mẫu chuẩn do
doanh nghiệp cung cấp:

| Biểu mẫu đang chạy | Mã kỹ thuật | Kết quả hệ thống trả về |
|---|---|---|
| Đơn xin nghỉ phép | `LEAVE_REQUEST` | Các trường thông tin, lỗi kiểm tra và hướng xử lý |
| Đơn xin tăng ca | `OVERTIME_REQUEST` | Các trường thông tin, lỗi kiểm tra và hướng xử lý |

Đây là cách tiếp cận có chủ đích: chỉ tự động xử lý những mẫu đã được khai báo,
kiểm thử và quản lý phiên bản; tài liệu lạ không bị ép vào một mẫu gần giống.

## Đã làm được gì?

### Bốn loại file đã được kiểm thử

| File người dùng đưa vào | Cách hệ thống đọc | Kết quả thử nghiệm mới nhất |
|---|---|---:|
| DOCX (Word) | Đọc trực tiếp đoạn văn/bảng trong file | Nhận diện đúng 10/10; trường bắt buộc đúng 90/90 |
| PDF có chữ | Đọc trực tiếp lớp chữ của PDF | Nhận diện đúng 10/10; trường bắt buộc đúng 90/90 |
| Ảnh PNG/JPG/JPEG | OCR tiếng Việt bằng EasyOCR `vi-greedy` | Nhận diện đúng 10/10; trường bắt buộc đúng 86/90 (95,56%) |
| PDF scan | Render trang rồi OCR tiếng Việt | Nhận diện đúng 10/10; trường bắt buộc đúng 82/90 (91,11%) |

Các kết quả trên là kiểm thử chấp nhận tại máy local (UAT) trên bộ dữ liệu của hai biểu mẫu,
không phải
10 loại tài liệu hay 10 mẫu khác nhau. Toàn bộ lần chạy có 0 lỗi JSON Schema;
20/20 trường hợp dùng OCR đều được chuyển sang người kiểm tra và không có trường hợp
OCR sai nhưng vẫn tự động đi tiếp.

### Những phần sản phẩm đã chạy thật

| Phần sản phẩm | Kết quả hiện tại |
|---|---|
| Giao diện local trên máy | Có thể tải file, xem bản xem trước cạnh kết quả, xem từng trường và JSON |
| Nhận diện mẫu | Nhận diện hai phiên bản đơn nghỉ phép/tăng ca đã đăng ký |
| Đọc nhiều định dạng | DOCX/PDF có chữ đọc trực tiếp; ảnh/PDF scan dùng OCR |
| Kiểm tra chất lượng | Thiếu trường thông tin, sai mẫu, mâu thuẫn hoặc OCR chưa chắc chắn đều cần người kiểm tra |
| Lưu trữ | File gốc, thông tin cá nhân, kết quả OCR và file mô hình nằm ngoài Git, trong vùng local/private |
| Kết nối quy trình | Có sơ đồ quy trình và thành phần thực hiện từng việc cho Camunda; đang mô phỏng, chưa triển khai môi trường thật |

## Tiến độ hiện tại

| Hạng mục dễ hiểu | Đã làm được | Trạng thái |
|---|---|---|
| MVP hai biểu mẫu HCNS | Đã có mẫu chuẩn, bộ trường, bộ đọc, kiểm tra và dashboard local | **Đang dùng làm luồng mặc định** |
| Chọn công cụ OCR | Đã thử các công cụ trên cùng bộ UAT; EasyOCR `vi-greedy` cho kết quả tốt nhất trong luồng hiện tại | **Hoàn tất** |
| Dữ liệu mở rộng CV/hợp đồng/chứng chỉ | Đã chạy thử 13 tài liệu/17 trang; 13/13 file xử lý được, 12/13 phân loại theo thư mục khớp | **Tạm giữ để bổ sung dữ liệu chuẩn** |
| Màn hình người duyệt dữ liệu | Đã có màn hình local để mở nguồn và xác nhận từng trường, không hiển thị dự đoán OCR | **Hoàn tất** |
| Rà soát hợp đồng | Đang rà soát 4 hồ sơ DOCX/PDF, tổng cộng 56 trường; hiện mới xác nhận 0/56 | **Đang làm** |
| OCR CCCD | Đã đánh giá một lần trên 14 ảnh hợp lệ; độ khớp trường 50%, chưa đủ an toàn để tự động dùng | **Chỉ kiểm tra thủ công, chưa dùng trong môi trường thật** |
| Điều phối quy trình nhân sự | Có thiết kế quy trình và thành phần Camunda mô phỏng | **Chưa triển khai môi trường thật** |

### Cách hiểu các con số

- **Nhận diện đúng 10/10**: trong 10 file kiểm thử, hệ thống nhận đúng loại mẫu.
- **Trường bắt buộc đúng 90/90**: 90 lần kiểm tra trường thông tin đều khớp dữ liệu chuẩn.
- **13 tài liệu/17 trang**: bộ dữ liệu mở rộng nhỏ dùng cho chạy thử, chưa đủ lớn để
  kết luận chất lượng trong môi trường thật.
- **50% trên CCCD**: kết quả hiện tại chỉ dùng để tìm lỗi và cho người duyệt xem lại,
  không phải cam kết hệ thống tự đọc CCCD chính xác.

## Kỹ thuật được sử dụng

| Kỹ thuật | Dùng để làm gì trong sản phẩm |
|---|---|
| Python 3.10+ | Xây luồng xử lý file, đọc tài liệu, kiểm tra dữ liệu và dịch vụ local |
| TypeScript web dashboard | Giao diện tải file, xem bản xem trước và kiểm tra kết quả |
| Native parsing | Đọc trực tiếp nội dung DOCX/PDF có chữ, nên nhanh và ít sai hơn OCR |
| EasyOCR `vi-greedy` | Đọc tiếng Việt trong ảnh và PDF scan; đây là lựa chọn mặc định hiện tại |
| PaddleOCR | Phương án quay lại khi cần so sánh hoặc chẩn đoán, không phải backend mặc định |
| JSON Schema | Kiểm tra JSON (dữ liệu dạng máy đọc được) có đủ trường và đúng kiểu dữ liệu |
| Provenance | Lưu dấu vết trường thông tin lấy từ trang, vùng ảnh hoặc nguồn nào để người duyệt đối chiếu |
| Human-in-the-loop | Đưa trường thiếu hoặc chưa chắc chắn cho con người xác nhận |
| Camunda 7.13 | Điều phối các bước xử lý, phê duyệt, thử lại và trạng thái quy trình |
| Pytest, Ruff, mypy | Kiểm tra hành vi, chất lượng code và kiểu dữ liệu |

### Một số từ khóa cần hiểu

- **IDP**: viết tắt của Intelligent Document Processing, tức là tự động đọc, hiểu và kiểm tra tài liệu.
- **Native parsing**: đọc trực tiếp chữ trong file Word/PDF, không cần nhận dạng hình ảnh.
- **OCR**: nhận dạng chữ từ ảnh hoặc PDF scan.
- **Provenance**: thông tin cho biết một giá trị được lấy từ đâu để có thể kiểm tra lại.
- **Human review**: người dùng xác nhận kết quả trước khi hệ thống dùng tiếp.
- **Quality gate**: bộ điều kiện quyết định kết quả được đi tiếp, cần người kiểm tra hay bị từ chối.
- **Camunda**: công cụ điều phối quy trình; nó không tự đọc file thay cho pipeline IDP.
- **Ground Truth**: dữ liệu chuẩn do người có trách nhiệm xác nhận, dùng để chấm kết quả thử nghiệm.
- **Synthetic**: dữ liệu giả lập dùng để kiểm thử, không phải hồ sơ thật của nhân viên.
- **Local-only/private**: dữ liệu thật chỉ chạy trên máy hoặc vùng lưu trữ được cấp quyền,
  không tự gửi lên cloud và không commit vào Git.

## Luồng xử lý thực tế

```text
Tải hồ sơ
  → kiểm tra file an toàn
  → đọc trực tiếp hoặc OCR
  → nhận diện mẫu hồ sơ
  → lấy các trường thông tin
  → kiểm tra dữ liệu và bằng chứng
  → đủ tin cậy: tạo JSON / chưa chắc chắn: người dùng kiểm tra
  → Camunda điều phối bước tiếp theo
```

Hệ thống không tự đoán trường bị thiếu. Với DOCX/PDF có chữ và dữ liệu hợp lệ, kết quả
có thể đi tiếp theo quy định của mẫu. Với ảnh/PDF scan, kết quả hiện luôn cần người kiểm tra.
Tài liệu không thuộc hai mẫu hiện tại bị từ chối thay vì bị đoán sang mẫu gần nhất.

## Chạy thử trên máy local

Yêu cầu: Python 3.10+, Node.js/npm và một thư mục dữ liệu riêng do người vận hành quản lý.

```powershell
git clone https://github.com/tandung060604-prog/hcns-automation-agent.git
Set-Location hcns-automation-agent

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,easyocr]"

Set-Location apps\ocr_lab\web
npm ci
Set-Location ..\..\..

.\apps\ocr_lab\api\start_dashboard.ps1 `
  -DataRoot "C:\path\to\private-data\paddleocr-hr-baseline" `
  -PythonPath ".\.venv\Scripts\python.exe"
```

Mở `http://localhost:3000`, tải một DOCX/PDF/PNG/JPG thuộc hai biểu mẫu, xem bản xem trước,
các trường và JSON. Xóa phiên local khi không còn cần kết quả. Hướng dẫn chi tiết nằm tại
[`apps/ocr_lab`](apps/ocr_lab/README.md).

## Kiểm thử và mức độ sẵn sàng

Các test mặc định dùng dữ liệu giả lập (synthetic), không cần tài liệu thật, file mô hình hoặc
Camunda server:

```powershell
python -m pytest -q
python -m ruff check src tests scripts
python -m mypy src
python scripts/check_repository.py
```

Checkpoint gần nhất của màn hình kiểm tra dữ liệu ghi nhận 249 test Python và 16 subtests,
cùng Ruff, mypy, compileall, repository hygiene và `git diff --check` pass. Đây là bằng
chứng cho chất lượng kỹ thuật của phiên bản hiện tại, không phải tuyên bố hệ thống đã
sẵn sàng tự động hóa mọi loại hồ sơ trong môi trường thật.

## README, tài liệu và ảnh/PDF khác nhau thế nào?

- **README.md**: giải thích sản phẩm, kết quả đã làm và cách chạy nhanh.
- **`docs/`**: tài liệu chi tiết về kiến trúc, bảo mật, cách đo chất lượng và các checkpoint.
- **`docs/weekly-reports/`**: báo cáo, screenshot và PDF dùng làm bằng chứng của các phiên
  chạy; chúng không phải template mới hay loại file runtime mới.
- **Private data root**: nơi chứa file thật, Ground Truth, kết quả OCR và file mô hình; không
  đưa vào Git.

Đọc thêm trong [Documentation Map](docs/README.md):

- [Architecture](docs/ARCHITECTURE.md) — cách chia các phần của hệ thống.
- [Evaluation](docs/EVALUATION.md) — cách đo và cách đọc kết quả.
- [Data Security](docs/DATA_SECURITY.md) — cách bảo vệ PII và dữ liệu nguồn.
- [Workflows](docs/WORKFLOWS.md) — các trạng thái xử lý và review.
- [Human-in-the-loop](docs/HUMAN_IN_THE_LOOP.md) — cách con người sửa và xác nhận kết quả.
- [Project State](docs/PROJECT_STATE.md) — tiến độ và bằng chứng mới nhất.

## Giới hạn hiện tại

- MVP mới mở hai biểu mẫu nghỉ phép và tăng ca đã được quản lý phiên bản.
- Ảnh và PDF scan đã OCR được nhưng vẫn bắt buộc người kiểm tra.
- Dữ liệu mở rộng CV/hợp đồng/chứng chỉ đang ở giai đoạn rà soát Ground Truth, chưa dùng
  để tuyên bố chất lượng trong môi trường thật.
- OCR CCCD chưa đạt mức an toàn để tự động chấp nhận.
- Camunda mới ở mức thiết kế/mô phỏng; chưa có Railway hay triển khai môi trường thật.
- Hệ thống không tự động quyết định tuyển dụng, sa thải, lương, kỷ luật hoặc phúc lợi.

## An toàn dữ liệu

- Không commit dataset, file tải lên, kết quả OCR thật, Ground Truth riêng tư, file mô hình
  hoặc secret.
- Không gửi tài liệu HCNS lên cloud/API nếu chưa có phê duyệt rõ ràng.
- Không đưa raw file, raw OCR hoặc full PII vào Camunda process variables.
- Mọi action ghi HRM/BPM cần policy, idempotency key và human approval.

Đọc [Data Security](docs/DATA_SECURITY.md) trước khi chạy với dữ liệu thật.

## Giấy phép và đóng góp

Dependency, OCR backend và model tuân theo license riêng của từng dự án. Khi thêm model,
dataset hoặc template, cần ghi rõ nguồn, version, license và cách kiểm thử tương ứng.
Trước khi tạo commit, chạy các quality gates ở trên và kiểm tra không có dữ liệu thật trong diff.
