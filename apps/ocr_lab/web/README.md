# HR Document Intelligence — web local

Giao diện hiển thị bằng chứng OCR, JSON có cấu trúc, hàng đợi Ground Truth và
benchmark recognizer. Website gọi API local tại `http://127.0.0.1:8765`; dữ liệu
tài liệu không được gửi lên dịch vụ cloud.

Yêu cầu Node.js `>=22.13.0`.

```bash
npm ci
npm run dev
npm test
```

`npm test` build website và chạy kiểm thử hành vi queue resume sau khi tải lại
trang. Xem hướng dẫn vận hành đầy đủ tại `../README.md`.
