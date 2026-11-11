# Team CAN

Sở hữu receiver, decoder, public CAN types, DBC và decoder unit tests.
Targets: `adas_decoder`; `adas_can` trên Linux. Không phụ thuộc component ADAS.

Public headers ở `include/`; DBC ở `dbc/vehicle.dbc`.
`VehicleState.speed_kmh` dùng km/h; `RadarObject.distance_m` dùng m;
`relative_velocity_mps` dùng m/s, dương nghĩa là đang tiến gần.
Decoder trả variant dữ liệu hoặc `DecodeError`. SocketCAN receiver quản lý socket
và trả optional frame; đọc header để biết timeout và error behavior.

Khi bàn giao thay đổi: ghi API/DBC/behavior bị ảnh hưởng và kết quả unit tests.
Component tests pass chưa chứng minh integrated application pass.
