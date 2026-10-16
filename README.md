# ADAS Integration Lab

Mô phỏng ADAS bằng C++17, Linux SocketCAN và Python; triển khai CI/CT ở các phase sau.

Hiện tại: Phase 1, collision-warning core và CLI demo.

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

Ví dụ kết quả: `WarningLevel=NONE`. GoogleTest được cài ở Phase 0; unit tests triển khai ở Phase 4.

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
