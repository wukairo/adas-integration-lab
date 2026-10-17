# ADAS Integration Lab

Mô phỏng ADAS bằng C++17, Linux SocketCAN và Python; triển khai CI/CT ở các phase sau.

Hiện tại: Phase 2, collision-warning core và Linux SocketCAN raw-frame receiver.

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
