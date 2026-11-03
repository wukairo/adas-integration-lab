# Đồ án: ADAS Software Integration & CI/CT Platform

## 1. Mục tiêu

Xây dựng một hệ thống mô phỏng quy trình **Software Integration + DevOps + CI/CT cho Automotive/ADAS**.

Project tập trung vào các kỹ năng gần với stack:

- Linux
- Git / GitHub
- Jenkins
- GitHub Actions
- Python
- C++
- CMake
- CAN
- SocketCAN
- Unit Test
- Integration Test
- Static Analysis
- Build Artifact
- Monitoring
- Azure Linux VM (optional)

Mục tiêu cuối cùng:

```text
C++ ADAS component
        ↓
Git / GitHub
        ↓
Jenkins / GitHub Actions
        ↓
Linux Build Agent
        ↓
CMake + GCC
        ↓
Unit Test
        ↓
CAN Integration Test
        ↓
Python Automation
        ↓
Artifact + Report
```

---

# 2. Bài toán

Giả lập một ECU / ADAS application nhận dữ liệu từ CAN bus:

```text
Vehicle Speed
Steering Angle
Front Radar Distance
Relative Velocity
Brake Status
```

Ứng dụng C++ sẽ:

```text
CAN frames
   ↓
CAN Receiver
   ↓
CAN Decoder
   ↓
ADAS Logic
   ↓
Collision Warning
```

Ví dụ:

```text
Vehicle Speed = 80 km/h
Front Distance = 15 m
Closing Speed = 10 m/s
```

Ứng dụng tính:

```text
TTC = Time To Collision
```

Công thức:

```text
TTC = distance / closing_speed
```

Sau đó trả về:

```text
NONE
WARNING
CRITICAL
```

Không cần computer vision hoặc AI.

Trọng tâm đồ án là:

```text
Software Integration
CI / CT
Linux
Build Toolchain
Automation
CAN
Testing
Troubleshooting
```

---

# 3. Kiến trúc tổng thể

```text
                    GitHub
                      │
                  PR / Push
                      │
             ┌────────▼────────┐
             │ GitHub Actions  │
             │ Quick CI        │
             └────────┬────────┘
                      │
                   Merge
                      │
                      ▼
                 Jenkins
                      │
                      ▼
                Linux Agent
                      │
              CMake Configure
                      │
                  GCC Build
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
      Unit Test              Static Analysis
         │
         ▼
 Python CAN Simulator
         │
         ▼
 Linux SocketCAN / vcan0
         │
         ▼
 C++ ADAS Application
         │
         ▼
 Integration Tests
         │
         ▼
 Reports / Logs / Artifacts
```

---

# 4. Technology Stack

| Thành phần | Công nghệ |
|---|---|
| OS | Ubuntu Linux |
| Main Language | C++17 |
| Automation | Python 3 |
| Build System | CMake |
| Compiler | GCC / Clang |
| Unit Test | GoogleTest |
| Test Runner | CTest |
| CAN | SocketCAN |
| Virtual CAN | `vcan` |
| CAN CLI Tools | `can-utils` |
| DBC | cantools / custom decoder |
| CI | Jenkins |
| Pull Request CI | GitHub Actions |
| Source Control | Git |
| Static Analysis | cppcheck |
| Coverage | gcov / lcov |
| Config | YAML / JSON |
| Cloud | Azure Linux VM — optional |

Optional:

```text
Conan
Docker
Prometheus
Grafana
Ansible
```

Không cần Kubernetes.

---

# 5. Repository Structure

```text
adas-integration-lab/
│
├── CMakeLists.txt
├── README.md
├── Jenkinsfile
│
├── src/
│   ├── main.cpp
│   ├── can_receiver.cpp
│   ├── can_decoder.cpp
│   └── collision_warning.cpp
│
├── include/
│   ├── can_receiver.hpp
│   ├── can_decoder.hpp
│   └── collision_warning.hpp
│
├── tests/
│   ├── test_can_decoder.cpp
│   └── test_collision_warning.cpp
│
├── dbc/
│   └── vehicle.dbc
│
├── scripts/
│   ├── setup_vcan.sh
│   ├── build.py
│   ├── run_tests.py
│   ├── simulate_can.py
│   ├── regression_test.sh
│   └── collect_system_info.py
│
├── integration/
│   ├── normal_drive.py
│   ├── collision_warning.py
│   ├── critical_collision.py
│   ├── missing_message.py
│   └── invalid_signal.py
│
├── config/
│   └── adas.yaml
│
└── .github/
    └── workflows/
        └── ci.yml
```

---

# 6. Module 1 — Virtual CAN Environment

Dùng Linux SocketCAN.

Tạo interface:

```bash
sudo modprobe vcan

sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

Kiểm tra:

```bash
ip link show vcan0
```

Monitor CAN:

```bash
candump vcan0
```

Gửi frame:

```bash
cansend vcan0 123#0102030405060708
```

Yêu cầu:

- [ ] Có script tự setup `vcan0`
- [ ] Có thể gửi frame bằng `cansend`
- [ ] Có thể xem frame bằng `candump`
- [ ] C++ application đọc được frame

---

# 7. Module 2 — C++ CAN Receiver

Dùng Linux socket:

```text
PF_CAN
SOCK_RAW
CAN_RAW
```

Ví dụ architecture:

```cpp
class CanReceiver {
public:
    explicit CanReceiver(const std::string& interface_name);

    bool open();
    bool receive(CanFrame& frame);

private:
    int socket_fd_;
};
```

Phải xử lý:

```text
socket creation
interface lookup
bind
receive
error handling
cleanup
```

---

# 8. Module 3 — CAN Frame Model

Tạo structure:

```cpp
struct CanFrame {
    uint32_t id;
    uint8_t dlc;
    std::array<uint8_t, 8> data;
};
```

Yêu cầu:

- support standard CAN ID
- validate DLC
- log invalid frame

---

# 9. Module 4 — DBC

Tạo:

```text
dbc/vehicle.dbc
```

Thiết kế ít nhất 2 message.

## VehicleState

```text
CAN ID: 0x100
```

Signals:

```text
VehicleSpeed
SteeringAngle
BrakeStatus
```

## RadarObject

```text
CAN ID: 0x200
```

Signals:

```text
ObjectDistance
RelativeVelocity
ObjectValid
```

Signal definition cần có:

```text
start bit
length
byte order
signed / unsigned
factor
offset
unit
```

---

# 10. Module 5 — CAN Signal Decode

Công thức:

```text
physical = raw × factor + offset
```

Ví dụ:

```text
raw = 800
factor = 0.1
offset = 0

VehicleSpeed = 80 km/h
```

C++ phải decode signal từ raw CAN bytes.

Ví dụ interface:

```cpp
struct VehicleState {
    double speed_kmh;
    double steering_angle_deg;
    bool brake_pressed;
};

VehicleState decodeVehicleState(const CanFrame& frame);
```

---

# 11. Module 6 — ADAS Collision Logic

Tạo:

```cpp
enum class WarningLevel {
    NONE,
    WARNING,
    CRITICAL
};
```

Interface:

```cpp
WarningLevel evaluateCollisionRisk(
    double vehicle_speed_kmh,
    double distance_m,
    double relative_velocity_mps
);
```

Tính:

```text
closing_speed > 0
```

thì:

```text
TTC = distance / closing_speed
```

Logic đề xuất:

```text
TTC > 4 s           → NONE
2 s < TTC <= 4 s    → WARNING
TTC <= 2 s          → CRITICAL
```

Edge cases:

```text
distance <= 0
closing_speed <= 0
invalid signal
radar object invalid
```

---

# 12. Module 7 — Unit Tests

Dùng GoogleTest.

## Test CAN Decoder

Ví dụ:

```cpp
TEST(CanDecoder, DecodeVehicleSpeed) {
    EXPECT_DOUBLE_EQ(speed, 80.0);
}
```

Test:

- [ ] Vehicle speed
- [ ] Steering angle
- [ ] Brake state
- [ ] Radar distance
- [ ] Relative velocity
- [ ] Wrong DLC
- [ ] Wrong CAN ID

## Test Collision Logic

Test:

- [ ] no collision
- [ ] warning
- [ ] critical
- [ ] zero relative velocity
- [ ] invalid distance

Run:

```bash
ctest --test-dir build --output-on-failure
```

---

# 13. Module 8 — Python CAN Simulator

Dùng Python để gửi CAN traffic.

Có thể dùng:

```python
python-can
```

Ví dụ:

```python
import can

bus = can.interface.Bus(
    interface="socketcan",
    channel="vcan0"
)

msg = can.Message(
    arbitration_id=0x100,
    data=[0x20, 0x03, 0, 0, 0, 0, 0, 0],
    is_extended_id=False,
)

bus.send(msg)
```

Simulator phải hỗ trợ:

```bash
python3 scripts/simulate_can.py --scenario normal
python3 scripts/simulate_can.py --scenario warning
python3 scripts/simulate_can.py --scenario critical
python3 scripts/simulate_can.py --scenario radar_timeout
python3 scripts/simulate_can.py --scenario invalid_signal
```

---

# 14. Module 9 — Integration Tests

Đây là phần quan trọng nhất.

## Scenario 1 — Normal Driving

Input:

```text
speed = 50 km/h
distance = 100 m
relative velocity = 0
```

Expected:

```text
WarningLevel = NONE
```

---

## Scenario 2 — Collision Warning

Input:

```text
speed = 80 km/h
distance = 20 m
closing speed = 7 m/s
```

Expected:

```text
WarningLevel = WARNING
```

---

## Scenario 3 — Critical Collision

Input:

```text
distance = 10 m
closing speed = 10 m/s
```

Expected:

```text
TTC = 1 s
WarningLevel = CRITICAL
```

---

## Scenario 4 — Missing Radar Message

Dừng message:

```text
RadarObject
```

Nếu không nhận radar frame trong:

```text
500 ms
```

Application phải báo:

```text
RADAR_TIMEOUT
```

---

## Scenario 5 — Invalid Signal

Ví dụ:

```text
VehicleSpeed > 300 km/h
```

Expected:

```text
INVALID_INPUT
```

---

# 15. Module 10 — Python Test Orchestrator

Tạo:

```text
scripts/run_tests.py
```

Nhiệm vụ:

```text
start application
start CAN simulator
run scenario
capture output
validate result
stop processes
generate report
return exit code
```

Exit code:

```text
0 = all tests pass
1 = test failure
```

Đây là behavior quan trọng cho Jenkins.

---

# 16. Module 11 — CMake

Root:

```cmake
cmake_minimum_required(VERSION 3.16)

project(adas_integration_lab)

set(CMAKE_CXX_STANDARD 17)

add_library(adas_core
    src/can_decoder.cpp
    src/collision_warning.cpp
)

target_include_directories(
    adas_core
    PUBLIC include
)

add_executable(
    adas_app
    src/main.cpp
    src/can_receiver.cpp
)

target_link_libraries(
    adas_app
    PRIVATE adas_core
)
```

Thêm test:

```cmake
enable_testing()
```

---

# 17. Module 12 — Python Build Automation

Tạo:

```text
scripts/build.py
```

CLI:

```bash
python3 scripts/build.py \
    --build-type Debug \
    --clean
```

Workflow:

```text
clean optional
 ↓
cmake configure
 ↓
cmake build
 ↓
ctest
```

Phải sử dụng:

```python
subprocess.run()
```

và propagate exit code chính xác.

---

# 18. Module 13 — Static Analysis

Dùng:

```text
cppcheck
```

Ví dụ:

```bash
cppcheck \
  --enable=warning,performance \
  src/ include/
```

Optional:

```text
clang-tidy
```

Static analysis failure có thể fail pipeline.

---

# 19. Module 14 — Jenkins Pipeline

Tạo:

```text
Jenkinsfile
```

Pipeline:

```text
Checkout
    ↓
Environment Check
    ↓
Configure
    ↓
Build
    ↓
Static Analysis
    ↓
Unit Test
    ↓
Integration Test
    ↓
Collect System Info
    ↓
Package
    ↓
Archive Artifact
```

Ví dụ:

```groovy
pipeline {
    agent { label 'linux' }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Environment') {
            steps {
                sh '''
                    uname -a
                    gcc --version
                    cmake --version
                    python3 --version
                    df -h
                    free -h
                '''
            }
        }

        stage('Configure') {
            steps {
                sh 'cmake -S . -B build'
            }
        }

        stage('Build') {
            steps {
                sh 'cmake --build build -j$(nproc)'
            }
        }

        stage('Static Analysis') {
            steps {
                sh 'cppcheck --enable=warning,performance src/ include/'
            }
        }

        stage('Unit Test') {
            steps {
                sh '''
                    ctest \
                      --test-dir build \
                      --output-on-failure
                '''
            }
        }

        stage('Integration Test') {
            steps {
                sh '''
                    ./scripts/setup_vcan.sh
                    python3 scripts/run_tests.py
                '''
            }
        }

        stage('System Information') {
            steps {
                sh 'python3 scripts/collect_system_info.py'
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'build/**/*'
        }
    }
}
```

---

# 20. Module 15 — Git Workflow

Không push trực tiếp vào `main`.

Branches:

```text
main

feature/can-receiver
feature/can-decoder
feature/collision-warning
feature/ci
feature/integration-tests

bugfix/radar-timeout
```

Workflow:

```text
feature branch
      ↓
commit
      ↓
push
      ↓
Pull Request
      ↓
GitHub Actions
      ↓
review
      ↓
merge
      ↓
Jenkins Full CI/CT
```

---

# 21. Module 16 — GitHub Actions

Mục đích:

```text
quick validation on PR
```

Không cần chạy full SocketCAN integration nếu môi trường phức tạp.

Workflow:

```yaml
name: Pull Request CI

on:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Configure
        run: cmake -S . -B build

      - name: Build
        run: cmake --build build

      - name: Unit Test
        run: ctest --test-dir build --output-on-failure
```

Architecture:

```text
Pull Request
     ↓
GitHub Actions
quick build/test
     ↓
Merge main
     ↓
Jenkins
full integration / CAN / artifact
```

---

# 22. Module 17 — System Monitoring

Tạo:

```text
scripts/collect_system_info.py
```

Collect:

```text
CPU usage
RAM usage
Disk usage
Load average
Kernel
Compiler version
Python version
CMake version
Git commit
```

Output:

```text
system_info.json
```

Ví dụ:

```json
{
  "cpu_percent": 62.4,
  "memory_percent": 71.2,
  "disk_percent": 48.1,
  "gcc": "13.2.0",
  "kernel": "6.x",
  "git_commit": "a81373f"
}
```

Jenkins archive file này.

---

# 23. Module 18 — Fault Injection

Simulator phải có khả năng inject lỗi.

Scenarios:

```text
missing frame
invalid CAN ID
wrong DLC
invalid signal
message timeout
high message frequency
invalid configuration
```

Ví dụ:

```bash
python3 scripts/simulate_can.py \
    --scenario radar_timeout
```

Pipeline phải detect failure đúng.

---

# 24. Module 19 — Git Bisect Demo

Tạo lịch sử:

```text
Commit A  PASS
Commit B  PASS
Commit C  BUG INTRODUCED
Commit D
Commit E
```

Sau đó:

```bash
git bisect start

git bisect bad HEAD

git bisect good <commit-A>

git bisect run ./scripts/regression_test.sh
```

Mục tiêu:

```text
Git tự động tìm commit C
```

Đây là phần demo rất phù hợp Software Integration.

---

# 25. Module 20 — Build Artifact

Khi release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Pipeline tạo:

```text
adas-app-v1.0.0.tar.gz
```

Package:

```text
release/
├── bin/
│   └── adas_app
├── config/
│   └── adas.yaml
├── dbc/
│   └── vehicle.dbc
└── version.txt
```

`version.txt`:

```text
version=v1.0.0
git_commit=a81373f
compiler=gcc-13
build_type=Release
```

Mục tiêu:

```text
build traceability
```

---

# 26. Optional — Code Coverage

Dùng:

```text
gcov
lcov
```

Output:

```text
coverage.info
HTML report
```

Jenkins archive report.

---

# 27. Optional — Conan

Nếu muốn thêm dependency management:

```text
GoogleTest
```

có thể lấy qua Conan.

Học:

```text
conanfile.py
profile
dependency
binary package
```

---

# 28. Optional — Azure

Sau khi project chạy ổn local:

Deploy Jenkins agent lên:

```text
Azure Ubuntu VM
```

Architecture:

```text
GitHub
   ↓
Jenkins
   ↓
Azure Linux VM
   ↓
CMake / GCC / CTest
   ↓
SocketCAN Integration Test
```

Không cần:

```text
AKS
Kubernetes
Terraform
```

Mục tiêu chỉ là:

```text
VM
SSH
Linux
Jenkins agent
resource monitoring
```

---

# 29. Milestones

## Milestone 1 — C++ Core

- [ ] CMake project build được
- [ ] Collision logic hoạt động
- [ ] Unit test hoạt động

---

## Milestone 2 — CAN

- [ ] Setup `vcan0`
- [ ] Python gửi CAN
- [ ] C++ nhận CAN
- [ ] Decode signal

---

## Milestone 3 — Integration Testing

- [ ] Normal scenario
- [ ] Warning scenario
- [ ] Critical scenario
- [ ] Timeout scenario
- [ ] Invalid input scenario

---

## Milestone 4 — Automation

- [ ] Python build script
- [ ] Python test orchestrator
- [ ] System info collector

---

## Milestone 5 — CI

- [ ] GitHub Actions
- [ ] Jenkins Pipeline
- [ ] Static Analysis
- [ ] Artifact

---

## Milestone 6 — Software Integration Demo

- [ ] branching workflow
- [ ] intentional regression
- [ ] automated `git bisect`
- [ ] tagged release

---

## Milestone 7 — Optional Cloud

- [ ] Jenkins agent chạy trên Azure Linux VM

---

# 30. Definition of Done

Project hoàn thành khi đáp ứng:

## C++

- [ ] C++17 application
- [ ] CMake build
- [ ] CAN receiver
- [ ] CAN decoder
- [ ] collision logic

## CAN

- [ ] SocketCAN
- [ ] `vcan0`
- [ ] DBC
- [ ] signal scaling
- [ ] message timeout detection

## Test

- [ ] GoogleTest
- [ ] CTest
- [ ] Python integration tests
- [ ] regression tests
- [ ] fault injection

## CI

- [ ] GitHub Actions
- [ ] Jenkins
- [ ] static analysis
- [ ] artifact packaging

## Linux

- [ ] setup script
- [ ] system monitoring
- [ ] process handling
- [ ] exit code handling

## Git

- [ ] feature branches
- [ ] pull request flow
- [ ] release tag
- [ ] `git bisect`

## Documentation

- [ ] README
- [ ] Architecture diagram
- [ ] Build instructions
- [ ] Test instructions
- [ ] CI description

---

# 31. README phải mô tả

README nên có:

```text
Project Overview
Architecture
Requirements
Build
Run
CAN Setup
Unit Test
Integration Test
CI Pipeline
Git Workflow
Fault Injection
Release
```

---

# 32. Demo khi phỏng vấn

Demo flow đề xuất:

```text
1. Show repository.
2. Show CMake project.
3. Setup vcan0.
4. Run C++ application.
5. Send CAN messages.
6. Show decoded signals.
7. Trigger WARNING / CRITICAL.
8. Run unit tests.
9. Run integration tests.
10. Show Jenkins pipeline.
11. Show GitHub Actions.
12. Introduce regression.
13. Run git bisect.
14. Show release artifact.
```

---

# 33. Cách mô tả project trong interview

Có thể trình bày:

> I built a small ADAS software integration environment on Linux. The application was written in C++ and received simulated automotive data through Linux SocketCAN. Python scripts generated CAN traffic and automated integration tests. I used CMake for builds, GoogleTest and CTest for testing, GitHub Actions for pull-request validation, and Jenkins for the full CI and continuous-testing pipeline. I also added static analysis, resource monitoring, release artifacts, fault injection, and an automated Git bisect regression workflow.

Project cho phép interviewer hỏi sâu các mảng:

```text
Git
Linux
Jenkins
GitHub Actions
Python
C++
CMake
CAN
CI/CT
Software Integration
Testing
Azure
```

---

# 34. Phạm vi nên giữ

Không biến project thành:

```text
computer vision project
deep learning project
Kubernetes platform
full AUTOSAR stack
production cloud platform
```

Mục tiêu chính:

```text
Software Integration
+
Linux
+
Git
+
CI/CT
+
Automation
+
C++ Build Toolchain
+
CAN
+
Automotive Testing
```

Đây là phạm vi sát nhất với role đang chuẩn bị.
