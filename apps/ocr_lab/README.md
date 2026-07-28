# OCR Lab chạy hoàn toàn trên máy local

`apps/ocr_lab` là giao diện thử nghiệm có human review cho OCR/IDP tài liệu
HCNS. Source được quản lý cùng repository sản phẩm, còn tài liệu thật, Ground
Truth, kết quả OCR và model weights luôn nằm ngoài Git.

## Cấu trúc

- `web/`: giao diện tại `http://localhost:3000`.
- `api/`: API local tại `http://127.0.0.1:8765`.
- API chỉ đọc/ghi dưới `--data-root` do người vận hành cung cấp.

## Chạy local

Chuẩn bị dependency một lần:

```powershell
python -m pip install -e ".[dev]"
Set-Location apps\ocr_lab\web
npm ci
```

Khởi động từ thư mục gốc repository:

```powershell
.\apps\ocr_lab\api\start_dashboard.ps1 `
  -DataRoot "C:\Camunda\private-data\paddleocr-hr-baseline"
```

Script chỉ bind API vào loopback. Upload được kiểm tra theo nội dung: giới hạn
kích thước/trang, format mismatch, PDF mã hóa, Office macro, archive path và
archive expansion đều bị chặn trước parser/OCR.

## Ground Truth và F5

Review đã lưu được API trả về trong `lineReviews`. Giao diện tạo queue chỉ từ
các case chưa có review, nên tải lại trang sẽ tiếp tục ở crop chưa xác nhận đầu
tiên. Ground Truth không được suy ra từ text của recognizer.

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
Set-Location apps\ocr_lab\web
npm test
```

Không commit `node_modules`, `.next`, `dist`, `.wrangler`, file upload, output,
Ground Truth private hoặc model weights.
