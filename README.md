# ADAS Software Integration & CI/CT Platform

Monorepo học Software Integration: code hai component đã tách, phần integration,
DevOps và Jenkins để khung cho bạn tự triển khai.

| Phần | Vị trí | Trạng thái |
|---|---|---|
| Team CAN | `components/can/` | Receiver, decoder, DBC và unit tests giữ nguyên logic |
| Team ADAS | `components/adas/` | Collision logic và unit tests giữ nguyên logic |
| Integration Engineer | `integration/` | Khung: application, runtime, config, simulator, tests |
| Python automation | `scripts/` | Khung công việc |
| Jenkins / agent | `Jenkinsfile`, `devops/` | Placeholder và hướng dẫn việc cần làm |
| PR CI | `.github/workflows/` | Chưa có workflow hoạt động |
| Triển khai cũ | `reference/legacy/` | Giữ đầy đủ để tham khảo; không phải pipeline hiện tại |

## Kiểm tra từng component

Cần CMake >= 3.16, GCC hỗ trợ C++17, GoogleTest; CAN receiver cần Linux.
Unit tests dưới đây không cần vcan hoặc Python.

```bash
cmake -S components/can -B build-can -DBUILD_TESTING=ON
cmake --build build-can --parallel 2
ctest --test-dir build-can --output-on-failure

cmake -S components/adas -B build-adas -DBUILD_TESTING=ON
cmake --build build-adas --parallel 2
ctest --test-dir build-adas --output-on-failure
```

Root CMake và Jenkinsfile cố ý báo chưa triển khai; chưa có integrated application
mới. Các thư mục build cũ có thể chứa binary cũ, không dùng làm bằng chứng cho
cấu trúc mới.

## Phần bạn tự làm

Đọc `integration/README.md`, `scripts/README.md` và `devops/README.md`.
Trình tự: ghép application chạy local -> boundary/CAN tests -> Python automation
-> Jenkins -> Git integration cycle -> release baseline.

Spec và tài liệu trong `docs/` được giữ nguyên. Các đường dẫn, báo cáo nghiệm thu
và mô tả vận hành cũ phản ánh cấu trúc trước khi tách; cần cập nhật khi bạn hoàn
thành từng bước. Không có service, agent hay Jenkins job nào được chỉnh trên server.
