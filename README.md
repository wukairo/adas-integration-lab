# ADAS Integration Lab

Mô phỏng ADAS bằng C++17, Linux SocketCAN và Python; triển khai CI/CT ở các phase sau.

Hiện tại: Phase 5, collision-warning core, Linux SocketCAN raw-frame receiver, DBC-based CAN decoder, Python CAN simulator và unit tests cho core/decoder/simulator.

## Bắt đầu

Làm theo [hướng dẫn Phase 0 trên VMware](docs/PHASE_0_GUIDE_VI.md).

Trong Ubuntu, tại thư mục project:

```bash
bash scripts/setup_ubuntu.sh
bash scripts/verify_phase0.sh
```

Build thủ công:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
./build/adas_app 50 100 0
```

Ví dụ kết quả: `WarningLevel=NONE`.

## Phase 2: Virtual CAN và raw CAN receiver

Chế độ nhận CAN dùng Linux SocketCAN và Classical CAN (payload tối đa 8 byte). Cần Linux với kernel hỗ trợ `vcan`, cùng các gói `iproute2`, `kmod` và `can-utils`. Chỉ cần quyền root/`sudo` khi cấu hình interface; ứng dụng chạy bằng user thường.

Tạo và bật `vcan0` (script chạy lặp lại an toàn, không thay interface cùng tên nếu nó không phải `vcan`):

```bash
bash scripts/setup_vcan.sh
```

Terminal 1 — nhận và in raw frames:

```bash
./build/adas_app --can vcan0
```

Terminal 2 — gửi frame bằng `cansend`:

```bash
cansend vcan0 123#0102030405060708
cansend vcan0 123#
cansend vcan0 123#FF
cansend vcan0 00000123#FF
cansend vcan0 123#R
```

Mỗi Classical CAN data frame hợp lệ được in thành một dòng và flush ngay. Ví dụ: `CAN id=0x123 format=standard dlc=8 data=01 02 03 04 05 06 07 08`. ID standard hiển thị 3 chữ số hex, ID extended 8 chữ số; byte hiển thị 2 chữ số hex viết hoa. DLC 0 có dạng `data=`. `dlc` trong output là payload length SocketCAN (0–8); wire DLC 9–15 là dạng hợp lệ chỉ khi payload dài 8 byte và được Linux biểu diễn riêng qua `len8_dlc`. Metadata `len8_dlc` sai bị bỏ qua kèm diagnostic stderr. RTR và error frames bị bỏ qua. Phase này chỉ nhận raw frames: chưa giải mã DBC và chưa đưa dữ liệu CAN vào collision-warning core.

`Ctrl+C` hoặc `SIGTERM` dừng receiver bình thường với mã thoát 0. Lỗi CAN/interface trả mã 1; sai cú pháp trả mã 2. `--can` cần interface đang tồn tại và bind được. Nếu `vcan` module không có trong kernel hoặc thiếu quyền thiết lập interface, script sẽ báo lỗi; kiểm tra `ip -details link show vcan0` sau khi cấu hình. Các lệnh gửi cần `can-utils` (`cansend`).

## Phase 3: DBC và decoded CAN signals

[`dbc/vehicle.dbc`](dbc/vehicle.dbc) định nghĩa hai standard Classical CAN message, mỗi message dài 8 byte:

| Message | ID | Signals |
| --- | ---: | --- |
| `VehicleState` | `0x100` | `VehicleSpeed` (km/h), `SteeringAngle` (deg), `BrakeStatus` |
| `RadarObject` | `0x200` | `ObjectDistance` (m), `RelativeVelocity` (m/s), `ObjectValid` |

Các signal số dùng Intel little-endian. `RelativeVelocity` dương nghĩa là đang tiến gần vật cản; âm nghĩa là đang ra xa. Chạy receiver ở Terminal 1:

```bash
./build/adas_app --decode vcan0
```

Gửi message ở Terminal 2:

```bash
cansend vcan0 100#200383FF01000000
cansend vcan0 200#C800BC0201000000
cansend vcan0 200#0000000000000000
```

Output tương ứng:

```text
VehicleState speed_kmh=80.00 steering_angle_deg=-12.50 brake_pressed=1
RadarObject distance_m=20.00 relative_velocity_mps=7.00 object_valid=1
RadarObject distance_m=0.00 relative_velocity_mps=0.00 object_valid=0
```

`ObjectValid=0` là message radar được giải mã thành công nhưng không có object hợp lệ; nó không tạo cảnh báo và không giống signal ngoài range. Frame có ID lạ hoặc format extended được bỏ qua kèm diagnostic; DLC sai và signal ngoài range được báo trên stderr, receiver vẫn chạy để nhận frame tiếp theo. Chế độ này chỉ decode và log; chưa ghép vehicle/radar state, gọi collision core từ CAN, hoặc quản lý freshness/timeout. `--can` vẫn dành cho xem raw frame, còn CLI ba số vẫn chạy collision core độc lập.

## Phase 4: Unit tests

Trên Ubuntu, cài GoogleTest từ hệ thống (`scripts/setup_ubuntu.sh` đã bao gồm gói này):

```bash
sudo apt-get update
sudo apt-get install libgtest-dev
cmake -S . -B build-phase4 -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON
cmake --build build-phase4 --parallel
ctest --test-dir build-phase4 -N
ctest --test-dir build-phase4 --output-on-failure
```

CTest discover 11 test GoogleTest thuộc hai nhóm `CollisionWarning` và `CanDecoder`. Nếu test fail, CTest in tên case và assertion lỗi; dùng `ctest --test-dir build-phase4 -R CollisionWarning --output-on-failure` (hoặc `CanDecoder`) để chạy riêng nhóm, và `./build-phase4/test_can_decoder --gtest_filter='CanDecoder.RadarVectorsDecodePhysicalSignals'` để chạy một case. Tests dựng `CanFrame` trong bộ nhớ, không cần vcan, sudo hay CAN traffic.

Để build ứng dụng mà không cần GoogleTest:

```bash
cmake -S . -B build-phase4-no-tests -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=OFF
cmake --build build-phase4-no-tests --parallel
```

Phase 4 kiểm tra các ngưỡng TTC, input không hợp lệ, DBC vectors, flags, DLC, ID, format và range của hai decoder. Khi kết thúc Phase 4, simulator chưa có; ghép vehicle/radar state, radar watchdog, kiểm thử CAN end-to-end và pipeline CI/CT vẫn thuộc phase sau.

## Phase 5: Python CAN simulator

Simulator dùng `python-can` và `cantools`, encode trực tiếp từ [`dbc/vehicle.dbc`](dbc/vehicle.dbc), rồi gửi standard Classical CAN frames qua SocketCAN. Cài dependency trong virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash scripts/setup_vcan.sh
```

Chạy một scenario mỗi lần; mặc định gửi 100 ms trong 3 giây trên `vcan0`:

```bash
.venv/bin/python scripts/simulate_can.py --scenario normal
.venv/bin/python scripts/simulate_can.py --scenario warning
.venv/bin/python scripts/simulate_can.py --scenario critical
.venv/bin/python scripts/simulate_can.py --scenario radar_timeout
.venv/bin/python scripts/simulate_can.py --scenario invalid_signal
```

Có thể đổi interface, DBC, chu kỳ và thời lượng. `radar_timeout` nhận thêm `--warmup-s` (mặc định 1 giây), còn scenario khác không nhận cờ này:

```bash
.venv/bin/python scripts/simulate_can.py --scenario warning --interface vcan0 --period-ms 50 --duration-s 2
.venv/bin/python scripts/simulate_can.py --scenario radar_timeout --warmup-s 1 --duration-s 3
.venv/bin/python scripts/simulate_can.py --scenario normal --dbc /path/to/vehicle.dbc
```

Scenario `normal`, `warning`, `critical` lần lượt encode `(speed, distance, relative velocity)` thành `(50, 100, 0)`, `(80, 20, 7)`, `(80, 10, 10)`. `radar_timeout` gửi cả `VehicleState` và `RadarObject` trong warmup; sau đó giữ `VehicleState` nhưng im lặng radar ít nhất 1 giây. `invalid_signal` chủ ý phát `VehicleSpeed=301 km/h` để decoder hiện tại ghi `INVALID_INPUT reason=OUT_OF_RANGE id=0x100`; các scenario bình thường vẫn kiểm tra strict range. Relative velocity dương là tốc độ tiến gần, không trừ vehicle speed thêm lần nữa.

Để quan sát frame và decode signals, khởi chạy receiver trước simulator:

```bash
./build-phase4/adas_app --decode vcan0
```

Simulator in `SIM_START`, từng `SIM_TX` với ID/DLC/payload và `SIM_STOP` với số frame gửi thành công. Mã thoát `0` là hoàn thành hoặc dừng bằng SIGINT/SIGTERM, `1` là dependency/DBC/interface/send failure, `2` là CLI hoặc timing không hợp lệ. Có thể gọi từ thư mục khác; DBC mặc định được tìm theo vị trí script. Script không tạo interface và không chạy bằng sudo.

Contract tests không cần `vcan0`:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_simulate_can.py' -v
```

Phase 5 chỉ cung cấp traffic mô phỏng và kiểm tra encoding/timing. Ứng dụng hiện tại vẫn chưa ghép state CAN vào collision core hoặc triển khai watchdog 500 ms; xác nhận `NONE/WARNING/CRITICAL/RADAR_TIMEOUT` từ CAN và test end-to-end thuộc Phase 6.

## Tài liệu gốc

- [Project specification](docs/adas_software_integration_ci_ct_project_spec.md)
- [Implementation plan](docs/ADAS_CI_CT_Implementation_Plan.md)

`src/`, `include/`, `tests/`, `dbc/`, `scripts/`, `integration/`, `config/` và `.github/workflows/` là skeleton cho các phase tiếp theo.


## Phase 1: Collision warning core

`adas_core` exposes `evaluateCollisionRisk(vehicle_speed_kmh, distance_m, relative_velocity_mps)` and has no CAN dependency or I/O. Positive relative velocity means closing on the obstacle and is used directly as closing speed; vehicle speed is validated as input only. All inputs must be finite, vehicle speed must be in `[0, 300]` km/h, and distance must be nonnegative. Invalid inputs throw `std::invalid_argument`; the CLI prints `INVALID_INPUT` and exits nonzero.

At zero distance, the result is `CRITICAL`. For positive distance, a nonpositive closing speed gives `NONE`; otherwise TTC is `distance_m / relative_velocity_mps` seconds. TTC `<= 2` gives `CRITICAL`, TTC `<= 4` gives `WARNING`, and TTC `> 4` gives `NONE`; comparisons use the unrounded value.

Build and run on the Ubuntu Server VM:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build --parallel
./build/adas_app 50 100 0
./build/adas_app 80 20 7
./build/adas_app 80 10 10
```

The CLI prints a stable token such as `WarningLevel=WARNING`. Usage: `adas_app <speed_kmh> <distance_m> <closing_speed_mps>`.
