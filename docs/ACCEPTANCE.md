# Nghiệm thu đồ án

Ngày kiểm chứng: 03/11/2026 (Asia/Saigon). Môi trường: Ubuntu 26.04.1, Linux 7.0.0-38-generic, SocketCAN trên vcan0 thật trong kernel.

## Bằng chứng local

| Hạng mục | Kết quả / evidence |
| --- | --- |
| Baseline Release + unit + cppcheck | Đạt; build-final/reports, 20 C++ và 17 Python tests trước mở rộng |
| Năm CAN scenarios gốc | 5/5 đạt; build-final/reports/live-baseline/summary.json |
| Fault injection mở rộng + trace | 9/9 đạt; build-final/fault-injection-reports/20261103T104925.018489Z-8950/summary.json |
| Hủy integration bằng SIGTERM | Đạt exit143, report tồn tại, cả ba process con đã dừng; build-final/reports/abort-validation/cleanup-evidence.json |
| Python suite gồm delivery tools | 31 tests đạt; build-final/python-final.log |
| Declarative Jenkins validator | Jenkins 2.580.2 trả Jenkinsfile successfully validated |
| Systemd vcan + Jenkins | Đã enabled; controller user ice, chỉ bind loopback 8080 |

Kết quả final Release/Jenkins/bisect/package được cập nhật sau khi source được commit và pipeline chạy. Logs lớn, controller state và secrets nằm dưới build directories (ignored), không đưa vào Git.

## Các bước phụ thuộc remote

Chưa có bằng chứng chạy GitHub Actions trên PR, required check/review rules, merge main hoặc GitHub webhook. Job Jenkins local kiểm chứng pipeline từ SCM nhánh feature hiện tại; không thay thế bằng chứng trigger remote. Chưa tự reboot server để thử service sau reboot; service đã cài/enabled và vcan đang hoạt động.

Tùy chọn coverage, Azure, Conan, Prometheus/Grafana chưa triển khai. Đây là virtual CAN, không ECU thật/HIL hoặc chứng nhận safety.
