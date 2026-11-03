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

## Nghiệm thu release v1.0.0

Source release: `b20f66676c028ff8e3da3efda9dac698ea2b05e5`, tag local `v1.0.0`. Commit evidence được ghi sau release; tag tiếp tục trỏ đúng source đã được build và kiểm thử.

| Hạng mục | Kết quả cuối |
| --- | --- |
| Unit + static analysis | 28/28 C++ và 36/36 Python tests; cppcheck đạt |
| Full Jenkins run 1 | [adas-validation #1](http://127.0.0.1:8080/job/adas-validation/1/) SUCCESS, khoảng 61 giây, 85 artifacts |
| Full Jenkins run 2 | [adas-validation #2](http://127.0.0.1:8080/job/adas-validation/2/) SUCCESS, khoảng 59 giây, release tag archive |
| Live integration trên mỗi Jenkins run | 9/9 scenarios đạt, app/simulator logs và candump trace được archive |
| Controlled regression | [adas-failure-validation #1](http://127.0.0.1:8080/job/adas-failure-validation/1/) FAILURE đúng Unit Test; threshold 2.0→2.1 làm test TTC fail; Package bị skip, 18 artifacts logs vẫn được lưu |
| Cấu hình runtime thật | YAML đổi ngưỡng TTC tạo CRITICAL từ traffic mặc định WARNING; watchdog 150ms timeout đạt |
| Git bisect final | Good exit0, bad exit1, tìm đúng first bad commit và reset thành công; build-final/bisect-evidence/ |
| Release | build-final/package/adas-app-v1.0.0.tar.gz và .sha256; unpack, layout, binary hash, smoke test đạt |
| Source/toolchain | version.txt khớp SHA/tag, Release, GNU 15.2.0; provenance được ghi khi CMake configure |

[Bằng chứng JSON đã lọc](evidence/validation.json) lưu các kết quả trên trong Git. Các URL Jenkins dùng SSH tunnel theo runbook. Job failure cố ý đỏ nằm trong clone cô lập, không đưa regression vào source release.

 Logs lớn, controller state và secrets nằm dưới build directories (ignored), không đưa vào Git.

## Các bước phụ thuộc remote

Chưa có bằng chứng chạy GitHub Actions trên PR, required check/review rules, merge main hoặc GitHub webhook. Job Jenkins local kiểm chứng pipeline từ SCM nhánh feature hiện tại; không thay thế bằng chứng trigger remote. Đã kiểm chứng SIGTERM của runner local; chưa thử nút Abort trong UI Jenkins. Chưa tự reboot server để thử service sau reboot; service đã cài/enabled và vcan đang hoạt động.

Tùy chọn coverage, Azure, Conan, Prometheus/Grafana chưa triển khai. Đây là virtual CAN, không ECU thật/HIL hoặc chứng nhận safety.
