# Báo cáo hiện trạng — Vietnamese HR Document Intelligence

> Đây là báo cáo lịch sử của corpus held-out đã retire, giữ lại để truy vết.
> Không dùng report này làm nguồn dữ liệu cho local runtime hoặc benchmark hiện tại.

> **Phạm vi báo cáo hiện tại:** chỉ dùng tập held-out 18 tài liệu HCNS có
> Ground Truth đã xác nhận và quyền xử lý local. Số liệu và hình ảnh synthetic,
> ảnh che PII và baseline Phase đầu đã được loại khỏi báo cáo này.

## 1. Corpus và quy trình đánh giá

Tập đánh giá `phase16-real-five-family-heldout-v1` gồm 18 tài liệu:

| Nhóm tài liệu | Số lượng |
|---|---:|
| CV và hồ sơ ứng viên | 5 |
| Đơn/biểu mẫu hành chính | 2 |
| Hợp đồng/quyết định nhân sự | 4 |
| Bằng cấp/chứng chỉ | 4 |
| Phiếu nhân viên/bảng biểu | 3 |
| **Tổng** | **18** |

OCR Lab đồng thời hiển thị riêng **30 session CCCD đã xác nhận Ground Truth**
trong vùng `LOCAL REAL-DOCUMENT EVIDENCE`. Các session CCCD là bằng chứng đối
chiếu local; không được cộng vào metric 18 tài liệu vì schema và protocol đánh
giá khác nhau.

Manifest được khóa bằng digest
`sha256:94c6356602bc99ddae3b1792da2c970c4d7cf0956604c6b2dcdbe8c26d28d702`.
Prediction được tạo và giữ ẩn trước khi Ground Truth được xác nhận. Tập này chỉ
được đánh giá một lần, không retune threshold sau khi xem kết quả.

## 2. Bằng chứng định lượng trên tài liệu thật

| Metric | Kết quả |
|---|---:|
| Classification Accuracy | **77,78%** |
| Field Exact Match | **13/100 — 13,00%** |
| Field Completeness | **28,00%** |
| Accepted Field Rate | **15,00%** |
| CER | **95,70%** |
| WER | **99,19%** |
| DER | **0,85%** |

Kết quả theo nhóm:

| Nhóm | Phân loại | Field Exact | Completeness | CER |
|---|---:|---:|---:|---:|
| CV | 60,00% | 13,04% | 13,04% | 90,89% |
| Đơn/biểu mẫu hành chính | 50,00% | 30,77% | 38,46% | 75,67% |
| Hợp đồng/quyết định | 100,00% | 18,18% | 40,91% | 121,18% |
| Bằng cấp/chứng chỉ | 75,00% | 3,23% | 29,03% | 95,04% |
| Phiếu nhân viên/bảng biểu | 100,00% | 9,09% | 18,18% | 93,15% |

**Quyết định:** `NOT_PROMOTED` và `NOT_PRODUCTION_READY`. Đây là số liệu
end-to-end trên tài liệu thật, không phải regression synthetic.

## 3. Recognizer đã chọn có thực sự được sử dụng không?

Có, đối với ảnh và PDF scan, luồng runtime hiện tại là:

```text
Paddle PP-OCRv5 detector
→ crop bbox_balanced_64
→ VietOCR vgg_seq2seq primary
→ VietOCR vgg_transformer verifier
→ strict agreement / needs_review
→ Canonical Document
→ classifier
→ parser field/table
```

- Paddle chỉ cung cấp geometry và audit evidence; text Paddle không đủ điều kiện
  tự động được chọn.
- `vgg_seq2seq` là recognizer primary đang tạo text cho Canonical Document.
- `vgg_transformer` đọc cùng crop để kiểm chứng.
- Khi hai model bất đồng, hệ thống giữ primary và đặt `needs_review`.
- `autoReplaceSelectedText=false`; không có fallback tự động.

Policy được khóa tại
`sha256:5dfd0186cacbe29a299c79d774aa4e2575f67a4675d6db15035762ed9b363fb6`.

## 4. Vì sao lỗi tiếng Việt vẫn chưa hết?

“Cấu hình tốt nhất” chỉ có nghĩa là tốt nhất trong số các candidate đã benchmark,
không có nghĩa đã vượt production gate. LODO fallback từng tăng tổng Exact Match,
nhưng gây false switch: một số dòng `vgg_seq2seq` vốn đúng bị thay thành sai.
Nếu bật tự động, tổng metric có thể tăng nhưng độ tin cậy của từng trường nhạy cảm
lại giảm.

Kết quả end-to-end 18 tài liệu còn cho thấy lỗi nằm ở nhiều tầng:

1. detector/crop có thể cắt mất dấu hoặc gộp sai dòng;
2. recognizer vẫn mất dấu, thay ký tự và nhầm chữ/số;
3. reading order sai trên layout nhiều cột;
4. classifier chọn sai family ở một số hồ sơ;
5. parser không ghép đúng nhãn–giá trị và block nhiều dòng;
6. Artifact bảng synthetic/Timesheet cũ đã retired, không thuộc scope sản phẩm và
   không được tính vào gate hoặc tiến độ Camunda M5.

Vì vậy chỉ đổi model nhận dạng không thể tự nó nâng Field Exact Match từ 13% lên
mức production.

## 5. Phương án xử lý tiếp theo

1. Lập error set theo từng tầng và family từ kết quả held-out đã tiêu thụ; không
   dùng 18 tài liệu này để chỉnh threshold.
2. Tạo development corpus riêng cho crop mất dấu, chữ nhỏ, font trang trọng,
   ảnh nghiêng và layout nhiều cột; fine-tune hoặc thay recognizer trên tập đó.
3. Chỉ cho fallback switch khi verifier agreement và regression chứng minh
   không làm mất dòng primary đúng; mọi trường hợp khác giữ `needs_review`.
4. Hoàn thiện parser nhiều dòng và table contract bằng development/regression
   riêng.
5. Khóa model/crop/policy mới, sau đó evaluate-once trên held-out v2 độc lập và
   quyết định promotion theo từng family.

## 6. Công khai bằng chứng và giới hạn quyền

Aggregate metric trong báo cáo này không chứa PII và có thể lưu trong Git. 18
tài liệu gốc hiện chỉ được cấp quyền xử lý local
(`authorizedLocalDocumentsOnly=true`), nên không được sao chép vào repository
công khai.

Khi chạy OCR Lab, tài liệu thật được phục vụ trực tiếp từ private-data tại
`http://localhost:3000/#explorer`, gồm hai tab: 18 tài liệu HCNS held-out và các
CCCD đã Ground Truth trong saved session. Muốn đưa ảnh thô vào báo cáo/Git công
khai cần bổ sung đủ ba xác nhận cho từng document/session ID:

- quyền công khai nội dung;
- quyền tái phân phối;
- sự đồng ý công khai PII của chủ thể dữ liệu.

Các artifact có thể kiểm toán:

- policy: `config/phase14_8_recognition_policy.json`;
- parser lock: `config/phase17_parser_lock.json`;
- metric spec: `docs/EVALUATION.md`;
- localhost: `apps/ocr_lab`.
