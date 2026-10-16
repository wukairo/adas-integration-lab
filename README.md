# ADAS Integration Lab

Mô phỏng ADAS bằng C++17, Linux SocketCAN và Python; triển khai CI/CT ở các phase sau.

Hiện tại: baseline Phase 0, executable chỉ in `Hello ADAS`.

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
./build/adas_app
```

Kết quả: `Hello ADAS`. GoogleTest được cài ở Phase 0; unit tests triển khai ở Phase 4.

## Tài liệu gốc

- [Project specification](docs/adas_software_integration_ci_ct_project_spec.md)
- [Implementation plan](docs/ADAS_CI_CT_Implementation_Plan.md)

`src/`, `include/`, `tests/`, `dbc/`, `scripts/`, `integration/`, `config/` và `.github/workflows/` là skeleton cho các phase tiếp theo.
