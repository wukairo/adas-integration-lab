# Phase 5 — Python CAN Simulator

## 1. Mục tiêu và căn cứ

Xây dựng simulator phát Classical CAN traffic có kiểm soát qua SocketCAN, encode từ `dbc/vehicle.dbc`, phục vụ demo local và làm nguồn input cho integration tests Phase 6.

Căn cứ:

- [Đặc tả đồ án](adas_software_integration_ci_ct_project_spec.md), Module 8–9: năm scenario và radar timeout 500 ms.
- [Roadmap](ADAS_CI_CT_Implementation_Plan.md), Phase 5–6.
- [Plan Phase 3](PHASE_3_IMPLEMENTATION_PLAN.md), [plan Phase 4](PHASE_4_IMPLEMENTATION_PLAN.md), README và code thực tế.

Baseline đã đọc ngày 18/10/2026, HEAD `0462fdf` (`test: add Phase 4 unit test baseline`):

- Có collision core, SocketCAN receiver, DBC, decoder và hai GoogleTest executable. README ghi 11 tests; phiên viết plan này chưa chạy lại tests.
- `adas_app --can <interface>` in raw frames; `--decode <interface>` in physical signals và diagnostic. CLI ba số gọi collision core độc lập.
- CAN decode chưa gọi collision core, chưa giữ vehicle/radar state và chưa có radar watchdog.
- Chưa có `scripts/simulate_can.py` hoặc manifest dependency Python.
- `scripts/setup_ubuntu.sh` đã cài Python, pip, venv, can-utils; `scripts/setup_vcan.sh` đã có.

Trước khi implement, kiểm tra lại hướng dẫn repo nếu có, branch, status và baseline; bảo toàn thay đổi đang có. Branch đề xuất: `feature/python-can-simulator`, chỉ tạo nếu chưa ở branch phù hợp. Không tự commit/push khi chưa được yêu cầu.

## 2. Phạm vi và cách nghiệm thu

Phase 5 triển khai sender, năm scenario, cấu hình timing, log, xử lý lỗi/cleanup và kiểm chứng payload với decoder hiện có.

Roadmap ghi exit criteria gồm “app decode và thay đổi risk state đúng”, nhưng application hiện chưa có đường CAN → collision core. Chia nghiệm thu rõ ràng:

1. **Gate Phase 5 — simulator:** traffic đúng DBC, đúng sequence/timing, decoder đọc đúng giá trị; `invalid_signal` tạo diagnostic đúng; radar traffic thực sự dừng trong khi vehicle tiếp tục.
2. **Gate end-to-end Phase 6:** bổ sung state aggregation, gọi collision core, watchdog rồi assert `NONE/WARNING/CRITICAL/RADAR_TIMEOUT` từ CAN.

Đây là điều chỉnh trình tự so với câu exit criteria của roadmap để phản ánh dependency còn thiếu. Hoàn thành gate simulator chưa đồng nghĩa đã đạt toàn bộ exit criteria end-to-end của roadmap. Nếu cần giữ nguyên exit criteria đó ngay ở Phase 5, phải kéo phần application bridge và watchdog trong mục 10 vào phạm vi thực hiện trước khi đóng phase.

Không mở rộng sang Jenkins, GitHub Actions, test orchestrator, report framework, replay, high-frequency faults hoặc các fault khác của Phase 10.

## 3. Đầu ra và file thay đổi

| File | Nội dung |
| --- | --- |
| `scripts/simulate_can.py` | CLI, scenario definitions, DBC encoder, scheduler và SocketCAN sender |
| `requirements.txt` | Dependency runtime `python-can`, `cantools`, chốt version sau khi kiểm chứng trên Ubuntu mục tiêu |
| `tests/test_simulate_can.py` | Kiểm tra vectors, fault encoding và sequence bằng standard-library unittest; không cần vcan |
| `README.md` | Setup venv, cách chạy năm scenario, expected decode, timing và giới hạn phase |
| `docs/PHASE_5_IMPLEMENTATION_PLAN.md` | Kế hoạch này và checklist nghiệm thu |

Giữ `dbc/vehicle.dbc` làm nguồn format. Không cần sửa C++/CMake cho gate simulator. Nếu phát hiện sai khác DBC/decoder, ghi rõ và xử lý lỗi riêng trước khi nghiệm thu, tránh sửa format để khớp dữ liệu simulator sai.

Không thêm package Python vào apt setup hay cài pip toàn hệ thống; dùng `.venv/` đã được gitignore. Không đưa venv, trace và build outputs vào source.

## 4. CAN và encoding contract

- Backend SocketCAN, interface mặc định `vcan0`; không tự tạo interface trong simulator.
- Standard 11-bit Classical CAN: `VehicleState` ID `0x100`, `RadarObject` ID `0x200`, DLC=8. Không bật CAN FD, extended ID hoặc RTR.
- Load DBC theo đường dẫn suy ra từ vị trí script, không từ current working directory. Có `--dbc` cho override; relative override được resolve từ working directory của người gọi.
- Encode bằng `cantools` từ signal names; không dựng thêm encoder byte thủ công cho happy path.
- Kiểm tra DBC trước khi mở bus: có hai message, đúng ID/length/format, đủ signals và layout/scale/range tương thích contract hiện tại. DBC khác contract phải fail rõ ràng thay vì âm thầm phát dữ liệu C++ hiểu sai.
- Reserved bits ghi 0. Relative velocity dương là tiến gần, không trừ thêm vehicle speed.
- Happy path giữ strict range validation. Chỉ encoder của `invalid_signal` được bỏ kiểm tra physical range có chủ đích; giá trị vẫn phải biểu diễn được trong raw 16 bit.
- Không tắt validation toàn cục hoặc clamp 301 km/h về 300.

| Signal | Layout | Factor | Physical range |
| --- | --- | ---: | --- |
| VehicleSpeed | bit 0, unsigned 16, little-endian | 0.1 | 0..300 km/h |
| SteeringAngle | bit 16, signed 16, little-endian | 0.1 | -720..720 deg |
| BrakeStatus | bit 32, unsigned 1 | 1 | 0/1 |
| ObjectDistance | bit 0, unsigned 16, little-endian | 0.1 | 0..500 m |
| RelativeVelocity | bit 16, signed 16, little-endian | 0.01 | -100..100 m/s |
| ObjectValid | bit 32, unsigned 1 | 1 | 0/1 |

## 5. Scenario definitions

Mỗi lần chạy chỉ một scenario, finite duration. Steering=0, brake=0, ObjectValid=1 cho các scenario mặc định. Critical dùng speed=80 km/h (spec không chốt speed cho case này; đây là lựa chọn simulator).

| Scenario | Speed / distance / relative | Vehicle payload | Radar payload | Kết quả kiểm chứng Phase 5 | Kết quả end-to-end Phase 6 |
| --- | --- | --- | --- | --- | --- |
| `normal` | 50 / 100 / 0 | `F401000000000000` | `E803000001000000` | Decode đúng ba giá trị | NONE |
| `warning` | 80 / 20 / 7 | `2003000000000000` | `C800BC0201000000` | Decode đúng; TTC tham chiếu 20/7 | WARNING |
| `critical` | 80 / 10 / 10 | `2003000000000000` | `6400E80301000000` | Decode đúng; TTC tham chiếu 1 s | CRITICAL |
| `radar_timeout` | 50 / 100 / 0 trong warmup | Như normal, phát suốt | Như normal, chỉ warmup | Sau warmup không có 0x200; 0x100 vẫn phát | RADAR_TIMEOUT sau ngưỡng 500 ms |
| `invalid_signal` | **301** / 100 / 0 | `C20B000000000000` | Như normal | stderr có `INVALID_INPUT reason=OUT_OF_RANGE id=0x100`; app tiếp tục nhận | INVALID_INPUT |

Payload là oracle cố định được suy ra từ DBC để đối chiếu; không lấy output của chính encoder làm expected. Fault scenario gửi speed=301 trong toàn bộ thời gian, có log `fault=VehicleSpeedOutOfRange`; send thành công vẫn trả 0 vì đây là injection có chủ đích.

Không dùng ObjectValid=0 thay cho radar timeout: đây vẫn là một radar message đã nhận. Không dùng wrong DLC/ID thay cho invalid physical signal.

## 6. CLI và timing đề xuất

```text
python3 scripts/simulate_can.py
  --scenario normal|warning|critical|radar_timeout|invalid_signal
  [--interface vcan0]
  [--dbc PATH]
  [--period-ms 100]
  [--duration-s 3]
  [--warmup-s 1]
```

- `--scenario` bắt buộc; các giá trị khác có default như trên.
- `period-ms` hữu hạn, >0; `duration-s` hữu hạn, >0. Mọi cấu hình phải được validate trước khi mở bus hoặc gửi frame.
- `warmup-s` chỉ dành cho `radar_timeout`; nếu user chỉ định ở scenario khác, báo lỗi cú pháp. Với timeout, warmup >0 và ít nhất một period, warmup < duration; khoảng `duration - warmup` phải **>=1 s** để có margin rõ ràng so với watchdog 500 ms.
- Scheduler dùng monotonic clock, tick đầu tại t=0; mỗi tick gửi VehicleState trước, RadarObject sau nếu được phép.
- Normal/warning/critical/invalid_signal gửi cả hai message tại mỗi tick t < duration.
- Radar_timeout gửi radar khi t < warmup; từ t >= warmup đến hết duration chỉ gửi vehicle. Không phát radar recovery trong scenario cơ bản.
- Kiểm tra điều kiện warmup bằng thời gian thực monotonic ngay trước send radar, tránh tick trễ vẫn gửi radar trong vùng silence.
- Dùng deadline tuyệt đối cho các tick để giảm drift. Nếu trễ, bỏ các tick đã lỡ và chuyển tới tick tương lai; không burst bù.
- Mỗi send có timeout hữu hạn, được giới hạn bởi thời gian còn lại của lần chạy. Không chờ vô hạn hoặc retry vô hạn khi interface lỗi.

Đây là traffic simulation trên Linux userspace, không cam kết hard real-time hoặc chu kỳ chính xác tuyệt đối. Kiểm chứng timeout dựa trên timestamp trace của frame radar cuối cùng, không chỉ dựa vào log “warmup ended”.

## 7. Phân lớp, log và lifecycle

Giữ script nhỏ nhưng tách các hàm có trách nhiệm rõ:

1. Parse/validate CLI và load/validate DBC.
2. Tạo signal dictionaries và encode hai message cho scenario.
3. Sinh quyết định tick/phase từ elapsed time; có thể kiểm tra bằng fake clock.
4. Mở bus, gửi frame và đóng bus trong finally/context manager.
5. `main()` trả exit code; import module không mở bus, chạy scheduler hoặc parse CLI.

Clock/sleep và send function có thể truyền vào scheduler để kiểm chứng sequence bằng fake, không cần chờ timeout thật. Chưa cần tạo package hoặc abstract class framework.

Log stdout theo một dòng mỗi event và flush ngay:

```text
SIM_START scenario=warning interface=vcan0 period_ms=100 duration_s=3
SIM_TX t_ms=0 scenario=warning id=0x100 dlc=8 data=2003000000000000
SIM_TX t_ms=0 scenario=warning id=0x200 dlc=8 data=C800BC0201000000
SIM_PHASE t_ms=1000 phase=radar_silence
SIM_STOP reason=completed vehicle_sent=30 radar_sent=30
```

Các dòng chỉ minh họa format; SIM_PHASE thuộc timeout, số frame thực tế được đếm từ send thành công, không hardcode theo duration. `t_ms` là elapsed monotonic và có thể khác nhẹ giữa hai send trong cùng tick. Log payload phải phản ánh đúng message đã gửi thành công; lỗi và diagnostic đi stderr. Không in `WarningLevel` hoặc `RADAR_TIMEOUT` như thể simulator đã đo output application.

Exit codes:

| Code | Ý nghĩa |
| ---: | --- |
| 0 | Hoàn thành hoặc dừng có kiểm soát bằng SIGINT/SIGTERM; log lý do dừng |
| 1 | Thiếu dependency, DBC lỗi/không tương thích, lỗi mở bus hoặc send |
| 2 | Sai CLI hoặc cấu hình timing không hợp lệ |

Dừng bằng signal phải thoát vòng gửi, đóng bus và in summary; không để process nền. Simulator không launch/kill application, không dùng sudo và không thay cấu hình mạng.

## 8. Thứ tự thực hiện

- [x] **Bước 1 — dependency và encoding:** tạo venv, chọn versions chạy được trên Ubuntu mục tiêu, ghi requirements; load DBC và encode các vectors trước khi nối CAN.
- [ ] **Bước 2 — sender tối thiểu:** chạy normal trên vcan0; đối chiếu candump và `--decode` với bảng payload.
- [x] **Bước 3 — happy scenarios:** thêm warning/critical, CLI finite duration, interface/DBC override; kiểm tra chạy từ thư mục khác.
- [x] **Bước 4 — fault scenarios:** invalid_signal qua nhánh encode riêng; radar_timeout có warmup/silence, vehicle tiếp tục phát.
- [x] **Bước 5 — robustness:** monotonic scheduler, send timeout, log/summary, lỗi dependency/interface/DBC và signal cleanup.
- [ ] **Bước 6 — kiểm chứng:** hoàn thành ma trận dưới, chạy lại CTest baseline, cập nhật README theo kết quả thực tế.

Không cần sửa build C++ để cài Python dependencies. CMake/CTest tiếp tục dùng riêng cho suites C++ trong phase này.

## 9. Kế hoạch kiểm chứng

### 9.1. Kiểm tra không cần vcan

Dùng unittest, mock bus và fake clock. Đây là kiểm tra contract encoding và timing có ảnh hưởng trực tiếp tới Phase 6:

- [x] Năm bộ payload trong bảng scenario khớp byte literal, ID/format/DLC đúng; reserved bits bằng 0.
- [x] Một vector signed: steering=-12.5 và relative=-7 encode đúng `83FF` và `44FD` ở bytes 2–3 của message tương ứng.
- [x] Strict happy-path encoding reject speed=301; nhánh fault encode được đúng raw 3010; không thay đổi validation happy path.
- [x] Fake clock: radar có trong warmup, không xuất hiện từ warmup trở đi, vehicle vẫn có trong silence; tick trễ không gây burst bù.
- [x] Cấu hình NaN/infinity/zero/âm, duration không đủ silence: trả 2 trước khi mở bus.
- [x] Mock send failure trả lỗi runtime và vẫn đóng bus.
- [ ] SIGINT/SIGTERM kiểm tra thực tế ở bước live.

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_simulate_can.py' -v
```

### 9.2. Setup và live demo trên Ubuntu

Các lệnh dưới là hướng dẫn sau khi implement, chưa được chạy trong phiên viết plan:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash scripts/setup_vcan.sh
cmake -S . -B build-phase5 -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON
cmake --build build-phase5 --parallel
ctest --test-dir build-phase5 --output-on-failure
```

Mở terminal A để thu trace, terminal B để decode, terminal C chạy từng scenario. Receiver phải sẵn sàng trước khi sender phát:

```bash
# Terminal A
candump -tz vcan0

# Terminal B
./build-phase5/adas_app --decode vcan0

# Terminal C: chạy lần lượt, quan sát kết quả sau mỗi lệnh
.venv/bin/python scripts/simulate_can.py --scenario normal
.venv/bin/python scripts/simulate_can.py --scenario warning
.venv/bin/python scripts/simulate_can.py --scenario critical
.venv/bin/python scripts/simulate_can.py --scenario radar_timeout
.venv/bin/python scripts/simulate_can.py --scenario invalid_signal
```

| Kiểm tra live | Điều kiện đạt |
| --- | --- |
| Ba happy scenarios | Trace khớp bảng; app decode speed/distance/relative đúng |
| Radar timeout | Có radar ban đầu; từ frame radar cuối tới hết chạy có khoảng trống >=1 s, vehicle vẫn hiện trong khoảng này |
| Invalid signal | 0x100 chứa `C20B`; stderr application báo OUT_OF_RANGE; radar tiếp tục decode |
| Period override | Chạy `--period-ms 50 --duration-s 2`, trace cho thấy nhịp xấp xỉ 50 ms trên máy không quá tải; ghi sai lệch quan sát |
| Interface không tồn tại | Dùng `--interface vcan_missing`: lỗi rõ, code 1, không treo |
| DBC không tồn tại/sai contract | Code 1 trước khi phát frame |
| Timing sai | Ví dụ `--period-ms 0`, timeout với `--duration-s 1`: code 2 trước khi mở bus |
| Stop signals | Chạy duration dài, lần lượt Ctrl+C và SIGTERM: code 0, summary ghi interrupted, process kết thúc và socket đóng |
| Chạy lại | Chạy cùng scenario hai lần liên tiếp, không có process/sender cũ tiếp tục phát |
| Working directory | Gọi script bằng absolute path từ `/tmp`, không truyền --dbc: vẫn tìm đúng DBC mặc định |

Để kiểm tra khoảng trống radar, chỉ chạy một sender trên interface thử nghiệm và không có nguồn CAN khác phát 0x200. Khi cần giữ bằng chứng, lưu candump/app log vào `/tmp/adas-phase5/`; không đưa trace vào source. Không coi thiếu output RADAR_TIMEOUT từ app hiện tại là simulator thất bại; watchdog chưa được triển khai.

## 10. Bàn giao bắt buộc cho Phase 6

Trước khi viết integration assertions, chốt và triển khai application bridge:

- Ghép latest valid VehicleState/RadarObject; xác định thời điểm đủ input, thời điểm evaluate và freshness của vehicle.
- Chỉ gọi collision core với input hợp lệ, object_valid=true. Chốt output khi object_valid=false, lỗi decode hoặc dữ liệu cũ, tránh giữ cảnh báo cũ vô hạn.
- Watchdog radar dùng monotonic clock; chốt mốc bắt đầu khi startup chưa có radar, loại frame nào refresh timestamp, điều kiện biên 500 ms và cách recovery.
- Chạy watchdog cả khi không có CAN traffic; tận dụng receive timeout/poll, không chỉ kiểm tra sau khi nhận frame.
- Chuẩn hóa output application để assert NONE/WARNING/CRITICAL/RADAR_TIMEOUT/INVALID_INPUT; phân biệt state với diagnostic và exit code.
- Test runner quản lý readiness, startup/teardown, deadlines và không để các scenario dùng stale state. Simulator chỉ cung cấp traffic; không tự quyết định test pass/fail.

Các điểm trên là dependency còn thiếu được xác nhận từ source, không phải chức năng đã hoàn thành ở Phase 4. Ngưỡng 500 ms là yêu cầu spec; các policy startup/freshness/recovery cần được chốt trong plan Phase 6 và có tests riêng.

## 11. Exit checklist

- [x] Cài được dependency từ requirements trong venv sạch; kiểm chứng Ubuntu 26.04.1, Python 3.14.4, `python-can 4.6.1`, `cantools 40.7.1`.
- [ ] Năm CLI scenarios chạy được, mặc định kết thúc sau 3 s; override interface/DBC/period/duration hoạt động.
- [ ] Payload/ID/DLC/format đúng DBC và oracle; happy path strict, fault speed=301 không bị clamp.
- [ ] Timeout warmup gửi cả hai ID, silence >=1 s không gửi radar và vẫn gửi vehicle; xác nhận bằng trace.
- [ ] Decoder đọc đúng happy inputs; invalid_signal tạo INVALID_INPUT OUT_OF_RANGE.
- [ ] Log có scenario/timing/payload/count; errors và exit codes đúng; signal cleanup hoạt động.
- [x] Python contract tests (9 cases) và C++ baseline (11 tests) pass.
- [x] README ghi cách setup/run, expected payloads và giới hạn CAN → risk/watchdog.
- [x] Review diff, `git diff --check` sạch; venv/build artifacts bị ignore.
- [x] Gate simulator chưa đạt đầy đủ: contract/unit gate pass, live SocketCAN gate blocked do môi trường không cho sudo xác thực để nạp `vcan`; gate end-to-end Phase 6 chưa chạy.

`docs/` hiện bị `.gitignore` loại trừ. Kế hoạch được lưu local theo cấu trúc tài liệu sẵn có; không tự thay chính sách ignore, stage, commit hoặc push.
