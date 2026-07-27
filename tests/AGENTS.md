# Test agent instructions

- Test không đọc network, model thật hoặc private data.
- Fixture phải synthetic và không giống định danh người thật.
- Unit test state transition, policy và normalization trước UI.
- Adapter mới phải pass cùng OCR contract tests.
- Benchmark không chạy trong unit suite; report phải pin model/dataset version.
- Khi sửa bug, thêm regression test nhỏ nhất tái hiện lỗi.

