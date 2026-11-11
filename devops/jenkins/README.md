# Jenkins — TODO

1. Checkout đúng candidate revision và ghi SHA.
2. Kiểm tra toolchain/Python dependencies và quyền dùng vcan.
3. Configure/build integrated application; chạy static analysis.
4. Chạy component tests, boundary tests và live CAN tests.
5. Archive logs/reports kể cả khi fail; chỉ package sau required gates pass.
6. Validate integration branch trước merge; release phải khớp SHA đã kiểm chứng.

Bạn chọn changes, đọc contract, tìm root cause và quyết định fix/baseline.
Jenkins gọi automation và cung cấp evidence; không tự quyết định semantic compatibility.
