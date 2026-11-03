# Kế hoạch hoàn thiện đồ án

## Baseline

- Đọc đặc tả và kế hoạch hiện có, giữ nguyên mã nguồn người dùng.
- Build Release mới tại `build-final`, chạy C++/Python unit và cppcheck.
- Thiết lập vcan0 và kiểm chứng đủ năm kịch bản SocketCAN gốc.

## Công cụ giao nộp

- Collector JSON: CPU, RAM, disk, load, kernel, compiler, Python, CMake, Git SHA và thời điểm UTC.
- Package binary Release đã kiểm thử, DBC, metadata toolchain và checksum; giải nén và smoke test.
- Mở rộng fault injection: unknown ID, wrong DLC, high frequency, invalid configuration.
- Demo Git bisect trên lịch sử cô lập, có regression thật và evidence.

## Tích hợp CI

- Jenkins tách từng quality gate, fail đúng stage, archive diagnostics kể cả lỗi.
- Quick CI cho PR không yêu cầu vcan; full CI dùng agent Linux có vcan.
- Kiểm chứng bằng Jenkins thực nếu tải được runtime và plugins.
- Không tuyên bố GitHub check/branch protection/webhook đã hoạt động khi chưa có evidence từ dịch vụ.

## Nghiệm thu và commit

- Chạy full regression mới, kiểm tra process cleanup và negative paths.
- Chạy demo bisect, collector, package checksum/unpack/smoke.
- Viết README, runbook và bảng evidence với hạn chế hạ tầng còn lại.
- Commit theo nhóm thay đổi, thông điệp Conventional Commits mô tả chức năng.
