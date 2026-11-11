# Phần Integration Engineer tự triển khai

Chỉ có khung, chưa có runtime/application/test implementation mới.

| Thư mục | Bạn viết gì |
|---|---|
| `src/`, `include/` | Application entry point, runtime, mapping CAN output sang ADAS input, watchdog/diagnostics |
| `config/` | Product configuration, validation và build metadata template |
| `simulator/` | Python CAN simulator sử dụng DBC của Team CAN |
| `tests/` | Boundary tests và end-to-end tests qua vcan |

Việc cần làm:

1. Viết root CMake ghép `components/can` và `components/adas` bằng public targets.
2. Viết runtime nhận frame, decode, kiểm tra validity/freshness, gọi ADAS logic.
3. Chốt output/readiness/exit-code contract cho application.
4. Kiểm tra mapping đơn vị, dấu, invalid inputs ở ranh giới components.
5. Viết simulator và live tests: normal/warning/critical/timeout/malformed input.
6. Thực hiện một integration cycle có team changes, failure, root cause, fix và regression test.
7. Gắn source SHA, toolchain/config/DBC identity và validation evidence với release baseline.

Git: `main` giữ baseline; feature branches bàn giao changes; chỉ dùng integration
branch tạm khi cần phối hợp. Validate candidate trước PR vào main, validate SHA
trên main trước release. Một Git SHA xác định toàn bộ components trong monorepo.

Tham khảo triển khai cũ trong `reference/legacy/`. Các script cũ dựa vào vị trí
repo gốc; không chạy trực tiếp từ reference và không coi chúng là phần đã hoàn thành.
