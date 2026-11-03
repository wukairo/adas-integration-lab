# Phase 6 — End-to-End Integration Tests

## 1. Mục tiêu và căn cứ

Hoàn thiện và kiểm chứng đường đi thực tế:

```text
Python simulator → Linux SocketCAN/vcan0 → C++ receiver
                 → DBC decoder → state aggregation → collision core
                 → application output → Python assertions
```

Căn cứ:

- [Đặc tả đồ án](adas_software_integration_ci_ct_project_spec.md), Module 6, 8–10: collision logic, năm scenario, watchdog radar 500 ms và quản lý process.
- [Roadmap](ADAS_CI_CT_Implementation_Plan.md), Phase 6–7: integration assertions ở Phase 6; automation tổng hợp, build wrapper và reports ở Phase 7.
- [Plan Phase 5](PHASE_5_IMPLEMENTATION_PLAN.md), mục 10: các quyết định runtime còn thiếu cần chốt trước khi viết assertions.
- `README.md`, CMake và source hiện tại của receiver, decoder, collision core, simulator, unit tests.

Baseline đọc ngày 21/10/2026, HEAD `1c48768` (`feat(simulator): add python socketCAN scenario simulator`):

- Có CLI ba số gọi collision core; `--can` chỉ in raw frames; `--decode` chỉ decode/log.
- Có `CanReceiver::receive(int timeout_ms)`, phù hợp để chạy watchdog ngay cả khi bus im lặng. Empty optional còn có thể do EINTR/frame bị bỏ qua, không đồng nghĩa radar đã timeout.
- Có decoder trả `std::variant<decoded struct, DecodeError>`; lỗi range đã có diagnostic `INVALID_INPUT`.
- Có simulator đủ năm scenario, default period 100 ms, duration 3 s; timeout warmup 1 s rồi chỉ gửi vehicle; invalid speed=301 km/h.
- Chưa có runtime nối CAN với collision core, state aggregation, freshness/watchdog hoặc integration test thực thi; `integration/` chỉ có `.gitkeep`.
- README ghi baseline 11 C++ tests; plan Phase 5 ghi 9 Python contract tests. Phiên viết kế hoạch này chưa chạy lại suites.
- Plan Phase 5 ghi live SocketCAN gate còn chưa được xác minh do môi trường không nạp được vcan. Cần chạy lại gate trên Ubuntu mục tiêu trước khi kết luận end-to-end pass.

Trước khi implement: đọc hướng dẫn repo nếu có, kiểm tra branch/status và bảo toàn thay đổi hiện có. Branch đề xuất `feature/end-to-end-integration`; không tự commit/push trong bước viết plan.

## 2. Phạm vi và đầu ra

Phase 6 gồm hai phần phụ thuộc nhau:

1. **Application bridge:** ghép vehicle/radar state, gọi core, kiểm tra freshness, watchdog 500 ms, output có contract rõ.
2. **Integration tests:** năm scenario thật qua SocketCAN, process readiness/cleanup, deadlines, assertions và logs khi fail.

Application bridge là phần cần bổ sung để đạt exit criteria CAN → ADAS đã được bàn giao từ Phase 5. Chỉ viết tests quanh `--decode` chưa đủ chứng minh collision logic hoặc watchdog hoạt động.

| File | Công việc dự kiến |
| --- | --- |
| `include/adas_runtime.hpp` | State model, runtime events/results, API nhận frame và tick theo thời gian |
| `src/adas_runtime.cpp` | Dispatch decoder, cập nhật state, freshness, watchdog, gọi core |
| `src/main.cpp` | Thêm `--adas <interface>`, readiness, event output, vòng lặp runtime |
| `CMakeLists.txt` | Library `adas_runtime` phụ thuộc core/decoder; link app và runtime tests |
| `tests/test_adas_runtime.cpp` | Deterministic tests cho state/timing/recovery, không cần vcan |
| `integration/common.py` | Helper quản lý process, đọc output, deadline, assertions và cleanup |
| `integration/normal_drive.py` | `normal` → NONE |
| `integration/collision_warning.py` | `warning` → WARNING |
| `integration/critical_collision.py` | `critical` → CRITICAL |
| `integration/missing_message.py` | Warmup → ngừng radar → RADAR_TIMEOUT |
| `integration/invalid_signal.py` | Speed=301 → INVALID_INPUT |
| `README.md` | Cách chạy runtime, năm tests, expected output và troubleshooting |

Không đưa `scripts/build.py`, `scripts/run_tests.py`, JUnit/report framework, cppcheck, Jenkins hay GitHub Actions vào Phase 6. Helper lifecycle là cần thiết ngay để tests độc lập chạy được; Phase 7 tái sử dụng helper khi tạo orchestrator tổng hợp. Không thêm YAML config hoặc dependency Python mới nếu chưa cần; thời hạn runtime dùng constant có tên trong phase này.

## 3. Contract runtime cần triển khai

Các ngưỡng TTC, năm scenario và radar timeout 500 ms là yêu cầu từ spec. Chính sách startup, vehicle freshness, precedence và output dưới đây là **quyết định thiết kế đề xuất cho Phase 6**, nhằm giải quyết các điểm spec chưa quy định.

### 3.1. CLI và state aggregation

Thêm:

```bash
./build-phase6/adas_app --adas vcan0
```

Giữ tương thích CLI ba số, `--can`, `--decode` và hành vi lỗi hiện có. Trên nền tảng không hỗ trợ SocketCAN, `--adas` báo unsupported và trả 1; sai cú pháp trả 2.

Runtime giữ latest decoded vehicle/radar, timestamp nhận thành công và cờ lỗi cho từng nguồn. Timestamp lấy bằng `std::chrono::steady_clock`; core không biết socket, clock hoặc I/O. Runtime nhận `now` từ caller để test thời gian giả, không tự sleep.

- Ghép latest available states; không yêu cầu frame cùng tick hoặc cùng timestamp.
- Nhận vehicle trước hoặc radar trước đều được. Chỉ đánh giá risk khi đủ input hợp lệ và còn fresh.
- Evaluate sau mỗi frame liên quan và mỗi tick; chỉ emit state khi thay đổi để tránh spam. Lỗi frame có diagnostic riêng dù state không đổi.
- `RelativeVelocity` dương là closing speed, truyền thẳng vào core; không trừ vehicle speed lần nữa.
- Steering/brake vẫn decode và validate nhưng chưa ảnh hưởng thuật toán TTC.
- `ObjectValid=0` vẫn là radar message hợp lệ, refresh watchdog; khi các nguồn đều hợp lệ/fresh, kết quả NONE với reason `NO_OBJECT`, không gọi core.
- TTC giữ nguyên: `<=2 s` CRITICAL, `<=4 s` WARNING, còn lại NONE; khoảng cách 0 là CRITICAL khi object valid; closing speed <=0 với khoảng cách dương là NONE.

### 3.2. Freshness, invalid input và recovery

| Sự kiện | Chính sách |
| --- | --- |
| Chưa có vehicle/radar | WAITING_FOR_INPUT, không phát WarningLevel |
| Valid VehicleState | Thay state, timestamp và xóa lỗi vehicle trước đó |
| Valid RadarObject, kể cả ObjectValid=0 | Thay state, timestamp và xóa lỗi radar trước đó |
| Vehicle/radar OUT_OF_RANGE | Đánh dấu nguồn đó invalid ngay; không dùng lại giá trị tốt cũ để evaluate; không refresh timestamp |
| Known standard ID nhưng sai DLC | Diagnostic DECODE_ERROR; đánh dấu nguồn tương ứng không dùng được tới khi có frame hợp lệ; không refresh timestamp |
| Unknown ID/extended/RTR/error frame | Bỏ qua/diagnostic theo receiver/decoder; không cập nhật state hoặc bất kỳ freshness timestamp nào |
| Vehicle từng hợp lệ nhưng tuổi >=500 ms | VEHICLE_TIMEOUT, dừng phát risk từ dữ liệu cũ |
| Radar chưa từng hợp lệ hoặc tuổi >=500 ms | RADAR_TIMEOUT theo mục 3.3 |
| Frame hợp lệ trở lại | Xóa lỗi nguồn đó; tự evaluate lại nếu cả hai nguồn đủ điều kiện |

`VEHICLE_TIMEOUT` và ngưỡng vehicle 500 ms là policy bổ sung để không dùng speed cũ vô hạn, không phải yêu cầu 500 ms cho vehicle từ spec. Wrong DLC làm nguồn unavailable với trạng thái INVALID_INPUT reason `WRONG_DLC`; diagnostic vẫn phân biệt với OUT_OF_RANGE. Không thay đổi hành vi decode-only của Phase 3.

Thứ tự ưu tiên trạng thái duy nhất sau mỗi update/tick:

1. RADAR_TIMEOUT nếu radar deadline đã hết.
2. INVALID_INPUT nếu một nguồn đang mang lỗi range/DLC chưa được thay bởi frame hợp lệ.
3. VEHICLE_TIMEOUT nếu vehicle từng có nhưng đã hết freshness.
4. WAITING_FOR_INPUT nếu vẫn thiếu nguồn.
5. NONE/WARNING/CRITICAL khi đủ điều kiện.

Diagnostic INVALID_INPUT vẫn được emit khi gặp frame out-of-range dù trạng thái hiện tại có ưu tiên timeout. Bài test invalid_signal phải assert **state INVALID_INPUT**, không chỉ tìm diagnostic. Sau timeout/recovery phải có state event mới; không giữ hoặc in risk cũ như kết quả hiện tại.

### 3.3. Radar watchdog

- Khởi tạo mốc chờ radar tại thời điểm runtime bắt đầu sau khi socket bind thành công.
- Trước radar hợp lệ đầu tiên: tuổi = now − startup; sau đó: tuổi = now − last valid radar.
- Timeout khi tuổi **>=500 ms**; ở 499 ms chưa timeout. Mốc bằng 500 ms là policy biên được chốt để test deterministic.
- Chỉ frame standard 0x200, DLC=8, decode thành công mới refresh radar timestamp. Radar invalid object vẫn refresh; malformed/range lỗi không refresh.
- Tick watchdog cả khi không có traffic, chỉ có vehicle, hoặc có traffic không liên quan. Không dựa vào việc `receive()` trả empty optional để suy ra timeout.
- Vòng lặp nhận dùng wait tối đa 50 ms, có thể rút ngắn theo deadline gần nhất. Kiểm tra state/deadline trước và sau receive, kể cả khi socket liên tục có frame.
- Emit RADAR_TIMEOUT một lần khi chuyển trạng thái. Radar hợp lệ trở lại tự thoát timeout, với output theo precedence ở trên.

Đây là watchdog userspace trên Linux; live tests có scheduling tolerance, không coi là kiểm chứng hard real-time. Unit tests kiểm tra chính xác biên 500 ms; live test xác nhận timeout không sớm và xuất hiện trong cửa sổ có giới hạn.

## 4. Output contract và exit code

Chọn stable key/value lines để dùng lại token `WarningLevel=...` đang có, không cần thư viện JSON cho C++.

Stdout của `--adas`, mỗi event một dòng và flush ngay:

```text
ADAS_READY interface=vcan0 radar_timeout_ms=500 vehicle_timeout_ms=500
ADAS_STATE t_ms=0 status=WAITING_FOR_INPUT reason=MISSING_INPUT
ADAS_STATE t_ms=10 status=OK WarningLevel=WARNING reason=RISK_EVALUATED
ADAS_STATE t_ms=1510 status=RADAR_TIMEOUT reason=RADAR_STALE radar_age_ms=500
ADAS_STATE t_ms=20 status=INVALID_INPUT reason=OUT_OF_RANGE source=VehicleState
```

Các dòng là ví dụ độc lập, không phải cùng một sequence. `t_ms` là elapsed steady time từ runtime startup, ghi đủ độ chính xác để kiểm tra timing; parser không phụ thuộc thứ tự keys. State không OK tuyệt đối không có trường WarningLevel. NONE do không có object dùng `status=OK WarningLevel=NONE reason=NO_OBJECT`.

- ADAS_READY chỉ phát sau bind và khởi tạo runtime thành công, trước vòng nhận frame; đây là handshake cho tests.
- Diagnostics ở stderr: giữ các category/reason có nghĩa như `INVALID_INPUT reason=OUT_OF_RANGE id=0x100`, `DECODE_ERROR reason=WRONG_DLC`.
- Với timeout event, thêm `last_radar_ms` (hoặc `radar_seen=0` nếu chưa từng nhận) và `radar_age_ms` để đối chiếu mốc. Dữ liệu thời gian dùng cùng clock với t_ms.
- Parser nhận diện event theo từ đầu dòng, parse fields chính xác; không dùng substring `WARNING` vì có thể nhầm CRITICAL hoặc log nguồn khác.
- App không tự kết thúc khi gặp invalid input hoặc radar timeout: đây là kết quả xử lý dữ liệu, không phải process failure.

| Process | 0 | 1 | 2 |
| --- | --- | --- | --- |
| App runtime | Dừng có kiểm soát SIGINT/SIGTERM | Lỗi socket/interface/runtime fatal | Sai CLI |
| Test scenario | Assertions pass, processes/cleanup hợp lệ | Assertion, môi trường, process hoặc cleanup fail | Sai CLI test |

Simulator giữ nguyên contract exit code Phase 5. Simulator/app exit 0 đơn lẻ không chứng minh test pass; test phải kiểm tra output và thời điểm.

## 5. Ma trận năm integration scenarios

Mỗi test tạo app và simulator mới, chạy tuần tự trên một interface không có sender khác. Defaults dùng period 100 ms và duration 3 s như simulator hiện tại.

| Test | Simulator/input | Assertions bắt buộc |
| --- | --- | --- |
| `normal_drive.py` | `normal`: 50 / 100 / 0 | Nhận state OK/NONE sau readiness và traffic; không có WARNING/CRITICAL/INVALID_INPUT/timeout trong cửa sổ traffic ổn định |
| `collision_warning.py` | `warning`: 80 / 20 / 7 | Nhận OK/WARNING, TTC tham chiếu 20/7; không có NONE/CRITICAL hoặc error state sau khi đủ input |
| `critical_collision.py` | `critical`: 80 / 10 / 10 | Nhận OK/CRITICAL, TTC=1 s; không có NONE/WARNING hoặc error state sau khi đủ input |
| `missing_message.py` | `radar_timeout`: warmup 1 s, duration 3 s | Có OK/NONE trong warmup trước RADAR_TIMEOUT; timeout xảy ra khi radar_age >=500 ms, vehicle vẫn đang được gửi; không có risk state trở lại trong radar silence |
| `invalid_signal.py` | `invalid_signal`: speed=301 km/h | Có state INVALID_INPUT/OUT_OF_RANGE/source=VehicleState và diagnostic đúng ID; không có state OK/risk trong cửa sổ traffic; app tiếp tục sống tới teardown |

Cửa sổ đánh giá bắt đầu sau khi simulator đã phát input cần thiết và kết thúc tại completion của simulator; xử lý phần tail theo timestamp event để không coi timeout sau khi nguồn đã kết thúc là lỗi scenario happy path. Không yêu cầu output lặp lại mỗi tick vì runtime chỉ emit transition. WAITING_FOR_INPUT tạm thời trước khi đủ hai nguồn là hợp lệ.

Timeout test phải chứng minh chuỗi **đã nhận radar → ngừng radar → timeout**, không chấp nhận timeout do app khởi chạy nhưng chưa nhận frame. Đối chiếu simulator SIM_TX/SIM_PHASE và app last_radar_ms/radar_age_ms; SIM log chỉ là bằng chứng nguồn phát, không được dùng làm kết quả application.

Live timing acceptance đề xuất: timeout event có `radar_age_ms` trong [500, 800] trên Ubuntu VM không quá tải. Cận trên gồm poll/scheduling margin, không sửa ngưỡng runtime thành 800 ms. Nếu vượt, test fail và lưu log để phân tích tải/độ trễ. Kiểm tra giới hạn trên từ timestamp app; thời gian đọc pipe của Python chỉ phục vụ deadline, tránh sai lệch do buffering.

Nếu startup app tới first radar >=500 ms vì host chậm, fail rõ readiness/startup timing và ghi evidence; không lặng lẽ coi timeout startup là kết quả missing_message. Không tự retry để biến kết quả fail thành pass.

## 6. Test helper: readiness, deadlines và teardown

Mỗi file scenario là entrypoint nhỏ gọi helper dùng chung, không sao chép quản lý process.

CLI thống nhất dự kiến:

```text
.venv/bin/python integration/<test>.py
  [--app build-phase6/adas_app]
  [--interface vcan0]
  [--log-dir build-phase6/integration-logs]
```

Đường dẫn mặc định app/simulator/DBC được resolve theo vị trí repo, hoạt động khi gọi từ thư mục khác. Dùng `sys.executable` khởi chạy simulator để giữ đúng venv. `Popen` dùng argument list, không `shell=True`.

Lifecycle:

1. Validate app executable, simulator và dependency; kiểm tra interface tồn tại, UP và loại vcan. Không chạy sudo/tự tạo interface trong tests.
2. Mở thư mục log riêng cho mỗi invocation/scenario, tránh ghi đè evidence.
3. Launch app `--adas`; đọc stdout và stderr đồng thời để tránh đầy pipe.
4. Đợi ADAS_READY với timeout tối đa 2 s; app chết trước readiness là fail ngay.
5. Launch simulator scenario tương ứng; đọc log đồng thời, kiểm tra process bất thường trong suốt bài test.
6. Thu state events và timestamps, assert thứ tự/giá trị/cửa sổ thời gian; đợi simulator hoàn thành bình thường (exit 0 và SIM_STOP reason=completed).
7. Trong `finally`, dừng process còn sống bằng SIGTERM; chờ tối đa 2 s, sau đó kill và wait/reap nếu cần. Forced kill hoặc exit bất thường ngoài dự kiến làm test fail.
8. Đóng pipes/join reader workers có deadline; in PASS/FAIL, nguyên nhân, expected/actual, vị trí log; trả code chính xác.

Giới hạn tổng cho mỗi scenario đề xuất 10 s, bao gồm startup và simulator; teardown có budget riêng hữu hạn tối đa 4 s. Dùng monotonic deadline cho mọi wait. App phải còn sống lúc bắt đầu teardown; app tự thoát sớm dù code 0 vẫn là failure.

Chỉ terminate process/group do chính invocation tạo, không `pkill` theo tên. Ctrl+C cũng đi qua cleanup. Không chạy song song năm tests trên cùng vcan; nếu sau này chạy song song phải dùng interface riêng. Socket mới mỗi test tránh queue cũ, nhưng vẫn cần bảo đảm sender cũ đã được reap trước test kế tiếp.

Lưu app stdout/stderr, simulator stdout/stderr và summary scenario gồm command, expected, actual, exit codes, timing. Có thể ghi summary text đơn giản trong Phase 6; machine-readable aggregate report thuộc Phase 7. Không bắt buộc candump chạy nền trong helper; khi debug có thể thu trace riêng.

## 7. Unit tests cho runtime mới

Không kiểm tra lại toàn bộ decoder/core bằng các tests trùng lặp. Tập trung vào behavior mới với frame vectors và thời gian giả:

- Nhận vehicle/radar theo cả hai thứ tự; trước khi đủ input không evaluate; latest update làm risk chuyển đúng.
- Radar tuổi 499 ms chưa timeout, 500 ms timeout; startup chưa từng nhận radar cũng có deadline.
- Không có frame nào, chỉ vehicle liên tục, hoặc unknown frames liên tục vẫn timeout đúng; timestamp nguồn khác không refresh radar.
- Radar ObjectValid=0 refresh watchdog, trả NONE/NO_OBJECT khi vehicle fresh.
- OUT_OF_RANGE sau một state tốt làm nguồn invalid ngay; không dùng cached value; valid frame mới phục hồi đúng.
- Wrong DLC làm nguồn unavailable; unknown/extended không thay state hoặc timestamps.
- Vehicle stale không tạo risk; cập nhật vehicle phục hồi khi radar còn fresh.
- Timeout có ưu tiên hơn lỗi cũ; nhận radar lại nhưng vehicle vẫn lỗi thì INVALID_INPUT; đủ hai nguồn hợp lệ mới phát risk.
- Một state giữ nguyên không emit lặp; recovery rồi timeout lại tạo transition mới.

Runtime tests không liên kết socket và không sleep. CTest mặc định tiếp tục là unit suite, không tự yêu cầu vcan/root để configure hoặc chạy tests.

Helper Python chỉ cần tests tập trung vào failure paths có rủi ro treo/leak: readiness timeout, app chết sớm, simulator fail, pipe có nhiều output, exception trong assertion và cleanup escalation. Có thể dùng subprocess fixture nhỏ chạy Python; không dựng framework hoặc mirror từng dòng implementation.

## 8. Thứ tự triển khai

### Bước 1 — Xác minh prerequisites và khóa contract

- [ ] Kiểm tra branch/status, dependencies, vcan trên Ubuntu mục tiêu.
- [ ] Chạy lại baseline C++ và Python tests; kiểm chứng live simulator vectors, radar silence và signal cleanup còn thiếu ở Phase 5.
- [ ] Ghi output contract, freshness và precedence vào README trước khi viết assertions.

### Bước 2 — Runtime độc lập với SocketCAN

- [ ] Tạo state model/API `onFrame(frame, now)` và `tick(now)` hoặc tương đương.
- [ ] Implement decode/update/invalidate/freshness/watchdog/core evaluation.
- [ ] CMake target và deterministic runtime tests; baseline tests vẫn pass.

### Bước 3 — CLI runtime

- [ ] Thêm `--adas`, readiness sau bind, stdout events/stderr diagnostics.
- [ ] Bounded receive và tick khi bus bận lẫn im lặng.
- [ ] Kiểm chứng thủ công ba risk levels, timeout, invalid input, recovery và SIGINT/SIGTERM.

### Bước 4 — Integration helper và ba happy paths

- [ ] Readiness handshake, concurrent pipe drains, deadline và cleanup trong finally.
- [ ] Implement normal/warning/critical scripts với assertions thật và log riêng.
- [ ] Mỗi script chạy riêng pass; app startup failure cho failure rõ ràng.

### Bước 5 — Timeout và invalid signal

- [ ] Implement missing_message với warmup/radar age/vehicle continuity assertions.
- [ ] Implement invalid_signal với runtime state assertion, diagnostic và app liveness.
- [ ] Kiểm tra startup timeout không thể làm missing_message pass giả.

### Bước 6 — Nghiệm thu và bàn giao

- [ ] Chạy đủ năm tests tuần tự, rồi chạy lại cả bộ lần thứ hai để kiểm tra isolation/cleanup.
- [ ] Negative control bằng expected result sai: test phải trả 1, logs đầy đủ và không còn process con.
- [ ] Chạy baseline + runtime tests, cập nhật README và ghi evidence live thực tế.
- [ ] Review diff/check whitespace; không đưa binary, venv hoặc logs vào source.

Ưu tiên hoàn thành runtime và watchdog trước test scripts; không dùng simulator output để giả lập output ADAS còn thiếu.

## 9. Lệnh nghiệm thu sau khi implement

Các lệnh dưới là hướng dẫn dự kiến, chưa được chạy trong phiên viết plan này.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash scripts/setup_vcan.sh

cmake -S . -B build-phase6 -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON
cmake --build build-phase6 --parallel
ctest --test-dir build-phase6 --output-on-failure
.venv/bin/python -m unittest discover -s tests -p 'test_simulate_can.py' -v

.venv/bin/python integration/normal_drive.py --app build-phase6/adas_app
.venv/bin/python integration/collision_warning.py --app build-phase6/adas_app
.venv/bin/python integration/critical_collision.py --app build-phase6/adas_app
.venv/bin/python integration/missing_message.py --app build-phase6/adas_app
.venv/bin/python integration/invalid_signal.py --app build-phase6/adas_app
```

Manual runtime demo: mở `./build-phase6/adas_app --adas vcan0` trước, rồi chạy từng simulator scenario ở terminal khác. Với recovery, trên cùng app: chạy radar_timeout tới khi có timeout, sau đó chạy normal để quan sát phục hồi khi cả hai nguồn đã fresh. Với no-traffic startup: mở app không sender, quan sát RADAR_TIMEOUT sau ngưỡng. Với vehicle-only silence: xác nhận không giữ risk khi vehicle stale dù radar tiếp tục.

Negative control: trong bản thử nghiệm tạm, đổi expected level của warning sang CRITICAL; chạy test và xác nhận code 1 rồi khôi phục ngay. Không commit expectation sai hoặc cố ý sửa production logic. Kiểm tra `git diff --check` và review diff sau khi khôi phục.

Nếu môi trường không có vcan/kernel capability, ghi rõ live gate chưa chạy; unit/mock pass không thay thế SocketCAN end-to-end pass.

## 10. Exit checklist và bàn giao Phase 7

- [ ] `--adas` thực sự nhận CAN, decode, ghép state và gọi collision core.
- [ ] Startup/missing/invalid/stale/no-object/recovery có policy rõ và deterministic tests.
- [ ] Radar watchdog dùng steady clock, threshold 500 ms, chạy được khi không traffic và khi bus bận.
- [ ] Output parse được, flush ngay; readiness phản ánh socket đã sẵn sàng.
- [ ] Đủ năm integration scripts chạy độc lập qua vcan, assert đúng application state.
- [ ] Timeout test xác minh warmup → silence → timeout đúng tuổi radar trong khi vehicle tiếp tục.
- [ ] Invalid signal test xác minh state INVALID_INPUT và app sống, không chỉ bắt log lỗi.
- [ ] Readiness/process failures/deadlines/Ctrl+C được cleanup, không còn process nền.
- [ ] Chạy liên tiếp hai lượt không nhiễm state/traffic cũ; negative control fail đúng exit code.
- [ ] Baseline C++/Python tests và runtime tests pass; README có command/evidence đúng thực tế.

Phase 7 tái sử dụng scenario definitions và helper để tạo `scripts/run_tests.py`, tổng hợp logs/reports, thêm build automation, regression wrapper và static analysis. Không viết lại state oracle hoặc lifecycle độc lập trong orchestrator.

`docs/` đang bị `.gitignore` loại trừ. File kế hoạch được lưu local theo các phase trước; không thay quy tắc ignore hoặc tự stage/commit/push.
