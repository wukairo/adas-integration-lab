# Team ADAS

Sở hữu collision warning logic, public API và thuật toán unit tests.
Target: `adas_core`. Không phụ thuộc CAN types, DBC hoặc SocketCAN.

Public API: `include/collision_warning.hpp`.
Input: speed km/h, distance m, relative velocity m/s; vận tốc dương là tiến gần.
Output: `NONE`, `WARNING`, `CRITICAL`. Có overload dùng ngưỡng TTC cấu hình.
Đọc header và tests để biết input validation và threshold boundaries.

Khi bàn giao thay đổi: ghi API/behavior bị ảnh hưởng và kết quả unit tests.
