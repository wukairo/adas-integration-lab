# Implementation Plan — ADAS Software Integration & CI/CT Platform

> **Nguồn:** `adas_software_integration_ci_ct_project_spec.md`  
> **Mục tiêu:** xây dựng C++ ADAS application nhận CAN data, kiểm tra tự động bằng Python/SocketCAN, tích hợp GitHub Actions + Jenkins, xuất reports/artifacts.  
> **Phạm vi:** Software Integration / Linux / C++ / CAN / DevOps / CI/CT. **Không làm** Computer Vision, AI, full AUTOSAR, Kubernetes.  
> **Chiến lược:** làm **local, manual → automated local → CI/CT → regression/release**. Chỉ chuyển phase khi đạt *Exit criteria*.

## 0. Nguyên tắc triển khai

- Mỗi phase thực hiện theo thứ tự: **Implement → Run locally → Test → Commit → Document**.
- Mỗi task có checkbox; ưu tiên **MUST** trước, **OPTIONAL** sau.
- Giữ `main` luôn build/test pass. Code mới đi qua `feature/*` hoặc `bugfix/*` + Pull Request.
- Phân biệt **Unit Test** (logic độc lập), **Integration Test** (CAN → application → output), và **CI test** (automation chạy hai loại test).
- Giữ log và exit code rõ ràng: `0` = pass, `!= 0` = fail.
- Dùng `vcan0` để mô phỏng CAN bus trên Linux; đây là **SIL-style integration test**, chưa phải ECU/HIL hoặc automotive-grade validation.

## Roadmap tổng thể

| Thứ tự | Phase | Kết quả có thể demo | Dependency |
|---:|---|---|---|
| 0 | Environment & Repository | Repo + toolchain hoạt động | — |
| 1 | C++ ADAS Core + CMake | Tính TTC và WARNING/CRITICAL | 0 |
| 2 | Virtual CAN + CAN Receiver | Nhận raw CAN frames qua `vcan0` | 0–1 |
| 3 | DBC + CAN Decoder | Decode physical signals | 2 |
| 4 | Unit Test | GoogleTest/CTest pass | 1, 3 |
| 5 | Python CAN Simulator | Gửi normal/warning/critical frames | 3 |
| 6 | End-to-End Integration Tests | Xác thực kết quả ADAS qua CAN | 4–5 |
| 7 | Python Automation + Static Analysis | Một lệnh chạy build/tests, có log | 6 |
| 8 | GitHub Actions + Jenkins CI/CT | PR quick CI, full Jenkins CI/CT | 7 |
| 9 | Basic Monitoring & Reports | `system_info.json`, CI artifacts | 8 |
| 10 | Fault Injection + Regression | Detect lỗi, `git bisect run` | 6–9 |
| 11 | Release Packaging & Traceability | Tagged `.tar.gz` release | 8–10 |
| 12 | Documentation & Final Demo | Reproducible demo từ clean checkout | 11 |
| Optional | Coverage / Conan / Azure / Real-time Monitoring | Mở rộng sau core | 12 |

---

## Phase 0 — Environment & Repository

**Mục tiêu:** có môi trường Linux và cấu trúc project thống nhất.

### Tasks

- [ ] Chuẩn bị Ubuntu Linux (local VM/máy thật). Kiểm tra `git`, `python3`, `g++`/`clang++`, `cmake`.
- [ ] Cài `can-utils`, `cppcheck`, GoogleTest hoặc chuẩn bị cơ chế lấy dependency cho CMake.
- [ ] Tạo GitHub repository `adas-integration-lab`; thêm `.gitignore`, `README.md` sơ bộ.
- [ ] Tạo skeleton `src/`, `include/`, `tests/`, `dbc/`, `scripts/`, `integration/`, `config/`, `.github/workflows/`.
- [ ] Tạo `CMakeLists.txt` tối thiểu và build executable `adas_app` in `Hello ADAS`.
- [ ] Commit baseline: `chore: initialize ADAS integration repository`.

### Verify

```bash
git --version
python3 --version
g++ --version
cmake --version
cmake -S . -B build
cmake --build build -j"$(nproc)"
./build/adas_app
```

**Exit criteria:** clean clone có thể configure/build/run, cấu trúc repo đúng spec.

---

## Phase 1 — C++ ADAS Core + CMake

**Mục tiêu:** implement collision logic trước, **không phụ thuộc CAN**.

### Tasks

- [ ] Tạo `include/collision_warning.hpp`, `src/collision_warning.cpp`.
- [ ] Định nghĩa `enum class WarningLevel { NONE, WARNING, CRITICAL };`.
- [ ] Implement `evaluateCollisionRisk(speed_kmh, distance_m, relative_velocity_mps)`.
- [ ] Khi `closing_speed > 0`: `TTC = distance / closing_speed`.
- [ ] Áp dụng thresholds từ spec: `TTC > 4s => NONE`; `2s < TTC <= 4s => WARNING`; `TTC <= 2s => CRITICAL`.
- [ ] Xử lý input bất thường: `distance <= 0`, `closing_speed <= 0`, invalid values. **Chốt behavior trong README/test trước khi code** (spec yêu cầu xử lý nhưng không định nghĩa hết output).
- [ ] CMake tạo `adas_core` library và `adas_app` executable.
- [ ] CLI demo tạm (hardcoded data hoặc command-line input) để thấy `NONE/WARNING/CRITICAL`.

### Verify

```bash
cmake -S . -B build
cmake --build build -j"$(nproc)"
./build/adas_app
```

**Exit criteria:** ADAS logic hoạt động độc lập, boundaries TTC được định nghĩa rõ, code compile sạch.

---

## Phase 2 — Virtual CAN + CAN Receiver

**Mục tiêu:** ứng dụng C++ nhận được CAN frames từ Linux SocketCAN.

### Tasks

- [ ] Viết `scripts/setup_vcan.sh` để tạo + `UP` `vcan0` (idempotent: chạy lại không fail vì interface đã tồn tại).
- [ ] Thử `candump` / `cansend` thủ công.
- [ ] Định nghĩa `CanFrame { id, dlc, data[8] }` trong header.
- [ ] Implement `CanReceiver` dùng `socket(PF_CAN, SOCK_RAW, CAN_RAW)`, interface lookup, `bind`, `read/recv`.
- [ ] Validate CAN ID, DLC; handle errors, signal termination, cleanup socket.
- [ ] Log CAN ID/DLC/payload để debug.

### Verify

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan  # chỉ cần khi chưa tồn tại
sudo ip link set vcan0 up
candump vcan0
# terminal khác:
cansend vcan0 123#0102030405060708
```

**Exit criteria:** `adas_app` nhận và in frame gửi bằng `cansend`; không leak socket khi thoát.

> **Lưu ý:** bước tạo `vcan0` có thể cần quyền root/CAP_NET_ADMIN; điều này ảnh hưởng tới thiết kế Jenkins agent sau này.

---

## Phase 3 — DBC + CAN Decoder

**Mục tiêu:** chuyển CAN bytes thành dữ liệu vehicle/radar có đơn vị rõ ràng.

### Tasks

- [ ] Tạo `dbc/vehicle.dbc` với `VehicleState` (`0x100`), `RadarObject` (`0x200`).
- [ ] Định nghĩa signals: `VehicleSpeed`, `SteeringAngle`, `BrakeStatus`, `ObjectDistance`, `RelativeVelocity`, `ObjectValid`.
- [ ] Chốt cho từng signal: `start bit`, `length`, `byte order`, `signedness`, `factor`, `offset`, `unit`.
- [ ] Implement `include/can_decoder.hpp`, `src/can_decoder.cpp`; map raw bytes → physical value (`raw * factor + offset`).
- [ ] Validate wrong CAN ID, wrong DLC, out-of-range values, invalid radar object.
- [ ] Cho `adas_app` nhận `0x100/0x200`, decode và log physical signals.
- [ ] Đảm bảo encode của Python simulator (Phase 5) **nhất quán** với cùng DBC; tránh tự định nghĩa hai format độc lập.

### Verify

- [ ] Gửi frame mẫu `VehicleState`, output ra speed/steering/brake chính xác.
- [ ] Gửi frame mẫu `RadarObject`, output ra distance/relative velocity/valid chính xác.
- [ ] Wrong ID/DLC được reject/log, không crash.

**Exit criteria:** raw CAN bytes → decoded structs đáng tin cậy, có test vectors bằng hex và expected values.

---

## Phase 4 — Unit Tests (GoogleTest + CTest)

**Mục tiêu:** có regression baseline chạy nhanh và độc lập với CAN interface.

### Tasks

- [ ] Cấu hình GoogleTest trong CMake, `enable_testing()` / `add_test()`.
- [ ] `tests/test_collision_warning.cpp`: NONE, WARNING, CRITICAL, TTC đúng `2.0`/`4.0`, zero closing speed, invalid distance.
- [ ] `tests/test_can_decoder.cpp`: signal scale/offset, signedness, endianness, wrong DLC/ID, invalid value.
- [ ] Test không cần `vcan0` hoặc quyền root.

### Verify

```bash
cmake -S . -B build
cmake --build build -j"$(nproc)"
ctest --test-dir build --output-on-failure
```

**Exit criteria:** tất cả unit tests pass; thay đổi logic sai phải làm test fail.

---

## Phase 5 — Python CAN Simulator

**Mục tiêu:** tạo traffic có kiểm soát thay cho ECU thật.

### Tasks

- [ ] Implement `scripts/simulate_can.py` bằng `python-can` + SocketCAN.
- [ ] Implement encode signals theo `dbc/vehicle.dbc` (có thể dùng `cantools`).
- [ ] CLI hỗ trợ `--scenario normal|warning|critical|radar_timeout|invalid_signal`.
- [ ] Dùng khoảng gửi frame/sequence có thể cấu hình; log scenario và payload.
- [ ] Đảm bảo `radar_timeout` dừng radar frame đủ lâu để trigger `500 ms` watchdog từ spec.

### Verify

```bash
python3 scripts/simulate_can.py --scenario normal
python3 scripts/simulate_can.py --scenario warning
python3 scripts/simulate_can.py --scenario critical
python3 scripts/simulate_can.py --scenario radar_timeout
```

**Exit criteria:** chạy simulator → `candump` thấy đúng CAN IDs, app decode và thay đổi risk state đúng.

---

## Phase 6 — End-to-End Integration Tests

**Mục tiêu:** verify toàn bộ path `Python simulator → vcan0 → C++ receiver → decoder → collision logic`.

### Tasks

- [ ] `integration/normal_drive.py`: `speed=50 km/h, distance=100 m, closing=0` → `NONE`.
- [ ] `integration/collision_warning.py`: `distance=20 m, closing=7 m/s` → `WARNING`.
- [ ] `integration/critical_collision.py`: `distance=10 m, closing=10 m/s` → `CRITICAL`.
- [ ] `integration/missing_message.py`: thiếu `RadarObject` > `500 ms` → `RADAR_TIMEOUT`.
- [ ] `integration/invalid_signal.py`: `VehicleSpeed > 300 km/h` → `INVALID_INPUT`.
- [ ] Chuẩn hóa output để test parse được (ví dụ key/value JSON line hoặc stable text tokens); đây là **đề xuất implementation** để test bền hơn.
- [ ] Test setup/teardown reset app/simulator, giới hạn timeout, không để lại process chạy nền.
- [ ] Test độc lập: mỗi scenario có expected result, log input và actual result khi fail.

### Verify

- [ ] Chạy đủ 5 scenarios; tất cả pass.
- [ ] Cố ý thay expected output hoặc sửa logic sai → ít nhất một scenario fail.
- [ ] Chạy test lại liên tiếp không bị stale process/CAN state.

**Exit criteria:** end-to-end testing có assertion thật, không chỉ xem log bằng mắt.

---

## Phase 7 — Local Automation + Static Analysis

**Mục tiêu:** biến quy trình thủ công thành command-driven, sẵn sàng chạy CI.

### Tasks

- [ ] `scripts/build.py`: `--build-type Debug|Release`, `--clean`; gọi CMake qua `subprocess.run`, propagate exit code.
- [ ] `scripts/run_tests.py`: launch app → start simulator → execute scenarios → validate → terminate/cleanup → report → exit code.
- [ ] `scripts/regression_test.sh`: chạy subset/full test dùng được bởi `git bisect run`.
- [ ] Tạo reports tự động (JUnit XML hoặc JSON là **đề xuất**; spec chỉ yêu cầu report/log).
- [ ] Chạy `cppcheck --enable=warning,performance`; chọn rule để warning nghiêm trọng có thể fail pipeline.
- [ ] Ghi logs/debug artifacts vào một output directory nhất quán, ví dụ `build/reports/`.

### Verify

```bash
python3 scripts/build.py --build-type Debug --clean
python3 scripts/run_tests.py
cppcheck --enable=warning,performance src/ include/
./scripts/regression_test.sh
```

**Exit criteria:** từ clean checkout, vài lệnh trên đủ build/test; test fail trả non-zero để CI detect.

---

## Phase 8 — GitHub Actions + Jenkins CI/CT

**Mục tiêu:** CI chạy tự động đúng theo Git workflow của spec.

### A. GitHub Actions — Quick CI khi Pull Request

- [ ] Tạo `.github/workflows/ci.yml`, trigger `pull_request`.
- [ ] Jobs: checkout → CMake configure → build → CTest.
- [ ] PR có failing unit test phải hiển thị failure; chỉ merge khi checks pass.

### B. Jenkins — Full CI/CT sau merge

- [ ] Chuẩn bị Jenkins controller + Linux build agent; cài dependencies.
- [ ] Cấu hình điều kiện cho `vcan0` (setup có quyền phù hợp; **không** chạy cả Jenkins controller dưới root).
- [ ] Tạo `Jenkinsfile`: Checkout → Environment → Configure → Build → Static Analysis → Unit Test → Integration Test → System Information → Package → Archive Artifact.
- [ ] Trigger build khi push/merge `main` (webhook hoặc SCM polling tùy môi trường).
- [ ] Jenkins fail đúng stage khi build, tests hoặc quality gate thất bại.
- [ ] Archive test reports/logs, binary, CAN trace, environment info (khi các file tương ứng đã được tạo).

### Verify

- [ ] Mở PR với test pass → Actions xanh.
- [ ] Mở PR với test fail → Actions đỏ.
- [ ] Merge `main` → Jenkins chạy full pipeline có SocketCAN integration.
- [ ] Mô phỏng một lỗi integration → Jenkins fail và có log/debug report.

**Exit criteria:** không cần chạy test bằng tay mỗi lần commit; quick CI và full CI có vai trò riêng.

---

## Phase 9 — Basic Monitoring & Reports (làm trước real-time)

**Mục tiêu:** implement đúng phần monitoring hiện tại của spec, đồng thời dễ nâng cấp về sau.

### Tasks bắt buộc từ spec

- [ ] Viết `scripts/collect_system_info.py`.
- [ ] Thu thập CPU, RAM, Disk, Load Average, Kernel, GCC, Python, CMake, Git commit.
- [ ] Xuất `system_info.json`.
- [ ] Jenkins chạy collector trong pipeline và archive JSON cùng build logs/test results.
- [ ] Ghi rõ thời điểm thu thập để tránh hiểu snapshot là real-time metrics (**đề xuất thêm**).

### Thiết kế mở rộng được (đề xuất, không bắt buộc từ spec)

- [ ] Tách **collector** (lấy giá trị metrics) khỏi **exporter** (serialize JSON).
- [ ] Dùng model dữ liệu thống nhất: `timestamp`, `metric_name`, `value`, `unit`, `labels` nếu phù hợp.
- [ ] Tách thêm process-specific counters nếu cần: test duration, app memory, CAN RX count, timeout count.
- [ ] Không gắn chặt collector với Jenkins; chạy local cũng tạo được JSON.

### Verify

```bash
python3 scripts/collect_system_info.py
python3 -m json.tool system_info.json
```

**Exit criteria:** `system_info.json` hợp lệ, chứa toolchain/kernel/git commit, truy cập được trong Jenkins artifacts.

**Quan trọng:** đây là **snapshot/build diagnostics**. Không gọi là real-time monitoring hoặc hard real-time validation.

---

## Phase 10 — Fault Injection + Automated Regression Detection

**Mục tiêu:** pipeline không chỉ xác nhận happy path mà còn bắt được failure modes.

### A. Fault Injection

- [ ] Simulator hỗ trợ: missing frame, invalid CAN ID, wrong DLC, invalid signal, message timeout, high message frequency, invalid configuration.
- [ ] Gắn mỗi fault với expected behavior rõ ràng (reject/log/error state/timeout), tránh giả định mọi fault đều phải crash/exit non-zero.
- [ ] Integration tests assert expected behavior; test fail nếu app xử lý sai.
- [ ] Khi fail, lưu CAN trace + application log + scenario metadata.

### B. Git Bisect

- [ ] Tạo commit history có một commit intentionally introduce regression sau baseline good.
- [ ] `scripts/regression_test.sh` trả `0` cho good, `1` cho bad (**có thể dùng exit 125 nếu commit không test được**).
- [ ] Chạy tự động:

```bash
git bisect start
git bisect bad HEAD
git bisect good <known-good-commit>
git bisect run ./scripts/regression_test.sh
git bisect reset
```

**Exit criteria:** demo được pipeline phát hiện lỗi và `git bisect` chỉ ra commit gây regression.

---

## Phase 11 — Release Packaging & Build Traceability

**Mục tiêu:** biến build pass thành artifact có thể truy vết.

### Tasks

- [ ] Build `Release`, tạo `release/bin/adas_app`, `release/config/adas.yaml`, `release/dbc/vehicle.dbc`.
- [ ] Generate `release/version.txt`: version, Git SHA, compiler, build type.
- [ ] Package `adas-app-v1.0.0.tar.gz` khi tag `v1.0.0`.
- [ ] Archive release tarball + reports trong Jenkins.
- [ ] Verify artifact giải nén và chạy được trên Linux environment tương thích.

### Verify

```bash
git tag v1.0.0
git push origin v1.0.0
# Sau khi pipeline package:
tar -tzf adas-app-v1.0.0.tar.gz
```

**Exit criteria:** từ artifact có thể biết **source commit + compiler + build configuration** đã tạo ra binary.

---

## Phase 12 — Documentation & Final Demo

**Mục tiêu:** người khác clone repo là tự dựng và xác minh được project.

### Tasks

- [ ] Hoàn thiện README: Overview, Architecture, Requirements, Build, Run, CAN Setup, Unit Test, Integration Test, CI, Fault Injection, Release.
- [ ] Vẽ architecture diagram: PR → Actions; merge → Jenkins → Linux agent → SocketCAN → reports/artifacts.
- [ ] Viết troubleshooting: thiếu `vcan`, `Permission denied`, missing deps, DBC mismatch, tests hang, Jenkins environment khác local.
- [ ] Ghi các limitation: simulated CAN, không ECU thật, không HIL, không safety-certified implementation.
- [ ] Chuẩn bị demo từ clean checkout.

### Demo checklist

- [ ] Checkout → build CMake → chạy C++ app.
- [ ] Setup `vcan0` → gửi CAN frames → quan sát decoder và `WARNING/CRITICAL`.
- [ ] Chạy GoogleTest/CTest + integration scenarios.
- [ ] Show GitHub Actions quick CI và Jenkins full CI/CT.
- [ ] Fault injection để chứng minh test phát hiện lỗi.
- [ ] Show `git bisect` tìm commit gây regression.
- [ ] Mở test report, `system_info.json`, release artifact + `version.txt`.

**Exit criteria:** demo hoàn chỉnh và reproducible; giải thích được failure propagation từ app → test runner → CI pipeline.

---

## Optional — Chỉ làm sau khi core project xong

| Nâng cấp | Làm gì | Khi nào đáng làm |
|---|---|---|
| Coverage | `gcov/lcov`, archive HTML coverage report | Muốn chứng minh mức test coverage |
| Conan | Dependency lock/profile, GoogleTest package | Muốn quản lý dependencies nghiêm túc |
| Azure Linux VM | Chuyển Jenkins build agent lên VM, SSH + monitoring | Muốn demo CI runner không nằm local |
| Prometheus + Grafana | Periodic metrics collection + `/metrics` exporter + dashboard | Muốn **continuous runtime observability** |
| Deterministic CAN Replay | Record/replay CAN traces để reproduce bugs | Muốn tăng chiều sâu automotive testing |
| Timing Validation | Đo processing latency/deadlines, flag violations | Muốn kiểm tra non-functional behavior |
| Requirements Traceability | Mapping requirement ID → test case → CI result | Muốn hướng tới validation workflow chặt chẽ |

### Đường nâng cấp monitoring sau này

```text
Current:
  Metrics Collector ──> JSON Exporter ──> Jenkins artifacts

Later (optional):
  Metrics Collector ──┬──> JSON Exporter ──> Jenkins artifacts
                      └──> Prometheus Exporter (/metrics)
                                   │
                              Prometheus
                                   │
                                Grafana
```

- Đừng rewrite collector; thêm exporter/sampling loop là phần lớn thay đổi.
- Với real-time monitoring, cần sampling liên tục, metric naming/labels, retention và alerting.
- **Prometheus/Grafana không đảm bảo hard real-time execution**; deadline validation là bài toán riêng.

---

## Tracking hằng ngày (copy cho mỗi task)

```markdown
### Task: <tên task>
- Branch: `feature/<name>`
- [ ] Code implemented
- [ ] Local verification passed
- [ ] Tests added/updated
- [ ] CI passed (nếu đã có CI)
- [ ] README/docs updated
- [ ] PR merged to main
- Evidence: <command/output/log/screenshot/commit>
```

## Definition of Done — Toàn đồ án

- [ ] C++17 ADAS logic + CMake + SocketCAN receiver + DBC decoder.
- [ ] Virtual CAN `vcan0`, Python simulator, ít nhất 5 integration scenarios.
- [ ] GoogleTest/CTest, regression tests, fault injection.
- [ ] Python build/test orchestration có cleanup, logs, reports, exit codes chính xác.
- [ ] GitHub Actions PR validation, Jenkins full CI/CT, static analysis.
- [ ] Basic monitoring JSON + CI artifacts.
- [ ] Automated `git bisect` demo, tagged release, `version.txt` traceability.
- [ ] README + architecture + reproducible final demo.
