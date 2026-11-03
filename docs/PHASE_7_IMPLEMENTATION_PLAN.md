# Phase 7 — Local Automation + Static Analysis

## 1. Mục tiêu và căn cứ

Tự động hóa quy trình local từ build tới kiểm thử và static analysis, có logs/report và exit code để Phase 8 gọi trực tiếp từ CI.

Căn cứ:

- [Roadmap](ADAS_CI_CT_Implementation_Plan.md), Phase 7: build wrapper, test orchestrator, regression entrypoint, cppcheck và output directory thống nhất.
- [Project specification](adas_software_integration_ci_ct_project_spec.md), Module 10, 12–13: quản lý app/simulator, report, `subprocess.run()`, configure → build → CTest và static analysis.
- [Plan Phase 6](PHASE_6_IMPLEMENTATION_PLAN.md): tái sử dụng lifecycle/assertions của integration helper.

Baseline kiểm tra ngày 23/10/2026:

- Có CMake targets cho core, decoder, runtime, SocketCAN app và ba GoogleTest executables; `BUILD_TESTING=ON` cần GoogleTest hệ thống.
- Có Python simulator contract tests tại `tests/test_simulate_can.py` và năm integration entrypoints.
- `integration/common.py` đã có readiness, assertions, deadline, logs và process cleanup; `run_scenario()` hiện parse CLI trực tiếp và trả số nguyên, chưa trả structured result.
- App/log mặc định của integration helper vẫn trỏ tới `build-phase6/`; Phase 7 phải truyền đường dẫn rõ ràng để không chạy nhầm binary cũ.
- Chưa có `scripts/build.py`, `scripts/run_tests.py`, `scripts/regression_test.sh` hoặc static-analysis wrapper. Dependency Ubuntu đã gồm cppcheck.
- `.gitignore` đang ignore toàn bộ `/docs/`; file plan mới cần được add có chủ đích khi người dùng muốn commit.

Đây là kế hoạch triển khai; chưa chạy lại build, tests hoặc live SocketCAN để xác nhận baseline pass trong phiên viết plan.

## 2. Phạm vi và đầu ra

| File | Thay đổi dự kiến |
| --- | --- |
| `scripts/build.py` | Configure, build, CTest; clean tùy chọn; lưu command logs |
| `scripts/run_tests.py` | Chạy unit/Python/integration theo suite và tổng hợp kết quả |
| `scripts/static_analysis.py` | Gọi cppcheck với quality gate và logs nhất quán |
| `scripts/regression_test.sh` | Một lệnh chạy build, analysis và subset/full tests; dùng được cho bisect |
| `scripts/automation_common.py` | Chỉ tách helper command/log/result dùng chung khi có nhu cầu thực tế |
| `integration/common.py` | Tách API chạy scenario khỏi CLI; trả structured result sau cleanup |
| Năm `integration/*.py` entrypoints | Giữ cách chạy standalone và expected behavior hiện có |
| `tests/test_automation.py` | Test failure propagation, reports, clean guard và interruption |
| `README.md` | Lệnh local automation, artifacts, exit codes và troubleshooting |

Giữ nguyên collision logic, output `ADAS_READY`/`ADAS_STATE`, watchdog và năm scenario. GitHub Actions/Jenkins thuộc Phase 8; system collector thuộc Phase 9; thêm fault scenarios và demo bisect history thuộc Phase 10. Không thêm dependency report framework: JSON/XML dùng thư viện chuẩn Python.

Các CLI, schema và quality policy dưới đây là quyết định thiết kế cho Phase 7; spec yêu cầu behavior nhưng chưa chốt những chi tiết này.

## 3. Contract lệnh và đường dẫn

Tất cả script xác định repo root từ `__file__`, không phụ thuộc working directory. Đường dẫn tương đối do người dùng truyền được resolve từ working directory lúc gọi. Dùng argument list, `shell=False`, `sys.executable` cho Python subprocess; không tự cài dependency hoặc gọi sudo trong test runner.

CLI dự kiến:

```text
build.py [--build-type Debug|Release] [--clean]
         [--build-dir PATH] [--report-dir PATH] [--jobs N] [--skip-tests]
run_tests.py [--suite unit|integration|all] [--scenario NAME ...]
             [--build-dir PATH] [--report-dir PATH] [--interface vcan0]
static_analysis.py [--report-dir PATH]
regression_test.sh [--suite quick|full] [--bisect] [--build-dir PATH]
```

Defaults: Debug, `build/`, report root `<build-dir>/reports/`, `run_tests --suite all`, `regression --suite full`. Scenario names là `normal`, `warning`, `critical`, `radar_timeout`, `invalid_signal`; `--scenario` chỉ hợp lệ với suite có integration. Reject tên sai, selection rỗng và `--jobs <= 0` trước khi chạy command.

Mỗi invocation tạo thư mục riêng dưới report root, chứa command logs, report và scenario artifacts. Wrapper tổng truyền cùng run directory cho các stage; không tự tạo các cây report rời nhau. In đường dẫn report ngay khi bắt đầu và khi kết thúc.

Exit codes:

| Entry point | Contract |
| --- | --- |
| `build.py` | `0` pass; command configure/build/CTest fail thì trả lại code dương của command đó, dừng stage sau; lỗi wrapper/dependency `1`, CLI `2` |
| `run_tests.py` | `0` tất cả selected tests pass; `1` assertion, prerequisite, timeout, cleanup hoặc report failure; CLI `2` |
| `static_analysis.py` | `0` pass; finding bị gate hoặc tool failure `1`; CLI `2` |
| `regression_test.sh` | `0` pass; `1` build/test/analysis failure; CLI `2`; `--bisect` chỉ dùng `125` cho prerequisite không đủ để kiểm thử |

SIGINT trả `130`, SIGTERM trả `143` sau cleanup; subprocess chết bởi signal được chuẩn hóa theo `128 + signal`, không trả raw returncode âm. Không map build/test failure sang `125`: làm vậy có thể che commit gây regression. Bisect wrapper giữ interrupt code >=128 để Git dừng thay vì đánh dấu bad.

## 4. Build automation

- [ ] `build.py` gọi tuần tự bằng `subprocess.run()`:

```text
cmake -S <repo> -B <build> -DCMAKE_BUILD_TYPE=<type> -DBUILD_TESTING=ON
cmake --build <build> --parallel <jobs>
ctest --test-dir <build> --output-on-failure --no-tests=error
```

- [ ] Mặc định chạy CTest đúng spec; `--skip-tests` phục vụ wrapper tổng để tránh chạy CTest hai lần.
- [ ] Ghi stdout/stderr và command/returncode/duration theo stage; in tiến độ và diagnostic đủ đọc khi fail.
- [ ] `--clean` chỉ xóa build directory đã resolve, sau validation; mặc định không xóa.
- [ ] Từ chối repo root, thư mục cha của repo, filesystem root, source directories, symlink build directory và cây chứa `.git`. Directory có sẵn chỉ được clean khi có CMake cache xác nhận `CMAKE_HOME_DIRECTORY` là repo này hoặc marker do automation tạo. Build directory mới/không tồn tại được chấp nhận.
- [ ] Report directory phải nằm ngoài vùng sắp xóa hoặc được tạo sau clean; từ chối cấu hình có thể xóa source/artifact input. Không xóa log của invocation đang chạy.
- [ ] Không tự đổi compiler/generator trong cache đang có; báo CMake diagnostic và hướng dẫn dùng build directory mới/clean.

`--no-tests=error` phải được kiểm tra hỗ trợ trên toolchain mục tiêu; nếu CTest cũ không hỗ trợ, kiểm tra test discovery có ít nhất một test trước khi chạy. Không nâng minimum CMake chỉ để lấy report XML. GoogleTest CTest vẫn là suite độc lập với vcan.

## 5. Test orchestrator và tái sử dụng Phase 6

### 5.1. API integration

- [ ] Tách `run_scenario()` thành lõi nhận scenario, expected level, app path, interface và log root; trả result gồm status, reason, elapsed time, artifacts và process exit codes **sau finally/cleanup**.
- [ ] Giữ adapter CLI trả `0/1/2` cho năm entrypoints hiện có; không parse `sys.argv` bên trong API được orchestrator gọi.
- [ ] Giữ assertions Phase 6, app readiness, simulator exit checks và lifecycle tại một nơi. Không dùng log `SIM_TX` thay application state để kết luận pass.
- [ ] Orchestrator truyền `<build-dir>/adas_app` và scenario log root, tránh default `build-phase6`.
- [ ] Bảo đảm lỗi preflight/cleanup vẫn có structured result; không suy luận outcome bằng cách parse chuỗi `PASS` hoặc scrape `summary.txt`.

### 5.2. Suite execution

| Suite | Nội dung |
| --- | --- |
| `unit` | CTest C++ + Python unittest discovery `tests/test_*.py`, không cần CAN |
| `integration` | Năm scenario hoặc subset được chọn, chạy tuần tự trên một interface |
| `all` | Unit trước, integration sau; chỉ pass khi tất cả selected tests pass |

- [ ] Runner không tự build; binary/test prerequisites phải tồn tại, thiếu thì fail kèm lệnh khắc phục.
- [ ] Integration preflight kiểm tra dependency, app và interface trước khi launch; không silently skip khi thiếu vcan. `unit` vẫn chạy được trên máy không có vcan.
- [ ] Mỗi scenario khởi tạo app/simulator riêng. Scenario fail sau cleanup thành công thì tiếp tục scenario kế tiếp để lấy đủ kết quả; cleanup không chắc chắn thì dừng integration và đánh dấu các case còn lại `not_run`.
- [ ] Thu kết quả unit fail và vẫn cho integration chạy nếu prerequisites đủ; prerequisite chung fail thì ghi rõ những case không chạy. Suite tổng luôn nonzero nếu có failure/error/not_run bắt buộc.
- [ ] SIGINT/SIGTERM dừng launch mới, chuyển qua cleanup, chốt partial report. Không để shell wrapper bị kill mà app/simulator còn sống.
- [ ] Có timeout hữu hạn cho command tests và scenario, kill/reap process group do invocation tạo khi hết hạn; không `pkill` theo tên. Giữ deadline scenario và readiness hiện có trừ khi có bằng chứng cần sửa.

Helper hiện bắt KeyboardInterrupt và không có handler SIGTERM riêng. Khi refactor phải chuyển interruption lên orchestrator để dừng cả suite, đồng thời bảo đảm helper luôn cleanup trước khi trả/raise.

## 6. Reports và artifacts

JSON là report bắt buộc của thiết kế này; JUnit XML là phần bổ sung thuận tiện cho Phase 8. Không cần JUnit để đạt yêu cầu report/log gốc của spec.

```text
build/reports/<run-id>/
  summary.json
  junit.xml                 # nếu triển khai adapter
  configure.stdout.log / configure.stderr.log
  build.stdout.log / build.stderr.log
  ctest.stdout.log / ctest.stderr.log
  python-tests.stdout.log / python-tests.stderr.log
  cppcheck.stdout.log / cppcheck.stderr.log
  integration/<scenario>-<unique-id>/
    app.stdout.log / app.stderr.log
    simulator.stdout.log / simulator.stderr.log
    summary.txt
```

`summary.json` có `schema_version`, run ID, UTC start/end timestamp, duration đo monotonic, selected suite/scenarios, build type/path, interface, overall status và danh sách results. Mỗi result có name/stage, status (`passed`, `failed`, `error`, `not_run`), command dạng array khi áp dụng, exit code, duration, reason và artifact paths. Missing tool/interface là error, assertion sai là failed; cả hai làm run fail.

Viết report ngay cả khi configure/preflight fail hoặc bị interrupt; cập nhật atomic qua temporary file + rename. Nếu không ghi được report thì stderr và exit nonzero. Report phải khớp trạng thái sau cleanup, không ghi pass trước khi teardown kết thúc.

Có thể biểu diễn CTest/Python suite thành một result tổng với raw logs; không giả lập từng case nếu chưa thu được dữ liệu. Nếu xuất JUnit, dùng XML serializer để escape nội dung; mapping prerequisite/cleanup lỗi sang error, assertion sang failure và không chạy sang skipped kèm lý do. JSON overall vẫn fail khi thiếu selected gate, kể cả JUnit gọi case đó skipped.

## 7. Static analysis quality gate

- [ ] Thêm wrapper chạy cppcheck từ repo root trên production `src/` và `include/`, không quét build/venv.
- [ ] Command baseline dự kiến:

```bash
cppcheck --enable=warning,performance --std=c++17 --language=c++ \
  --error-exitcode=1 -I include src/ include/
```

- [ ] Chốt gate: mọi diagnostic severity `error`, `warning`, `performance` trong phạm vi này làm fail. Thiếu cppcheck hoặc command không chạy thành công cũng fail.
- [ ] Xem baseline findings; sửa lỗi thật trước. Chỉ suppression hẹp theo diagnostic/file khi đã chứng minh false positive và có giải thích; không thêm suppression diện rộng để làm xanh gate.
- [ ] Lưu stdout/stderr, command, tool version và exit code; optional XML report nếu cần CI sau này.
- [ ] Kiểm tra behavior trên cppcheck cài ở Ubuntu mục tiêu; không coi missing system headers đơn thuần là code defect. Ghi rõ cấu hình platform/preprocessor được phân tích và hạn chế đối với Linux SocketCAN.

Không bắt buộc clang-tidy, coverage hoặc quét Python lint trong Phase 7.

## 8. Regression entrypoint

`regression_test.sh` là wrapper mỏng, resolve repo root, quote paths và dùng Python interpreter đã chọn từ môi trường (ví dụ `PYTHON=.venv/bin/python`). Khi gọi từ nơi khác vẫn tìm được scripts. Không chạy sudo hoặc cài dependencies.

```text
preflight → build.py --skip-tests → static_analysis.py → run_tests.py
```

- `--suite quick`: C++/Python unit tests và static analysis, không cần vcan.
- `--suite full` mặc định: thêm đủ năm live integration scenarios.
- Build/configure/analysis fail thì dừng với report chỉ rõ stage và stage sau `not_run`.
- Tạo một run directory chung, tổng hợp status từ các stage mà không ghi đè report con.
- Không reuse binary cũ sau configure/build fail. Bisect dùng build directory riêng và clean có guard mỗi lần để tránh artifact từ commit khác.
- `--bisect`: preflight thiếu tool/dependency/vcan trả `125`; source compile lỗi hoặc test/quality gate fail trả `1`. Không map mọi exception thành skip. Thiếu entrypoint trên commit cũ không tự coi là good; giới hạn bisect range có automation hoặc cung cấp harness ổn định ở Phase 10.

Phase 7 xác minh wrapper phù hợp contract bisect; chưa tạo commit lỗi hoặc chạy demo lịch sử regression.

## 9. Thứ tự triển khai và kiểm chứng

1. **Khóa baseline:** kiểm tra branch/status, chạy CTest + Python suite và năm live scenarios trên Ubuntu có vcan; ghi lại failures có sẵn trước khi sửa automation. Branch đề xuất `feature/local-automation`.
2. **Build wrapper:** implement CLI/path/clean guards, configure → build → CTest, logs và propagation; kiểm chứng Debug, Release, clean, gọi ngoài repo và path có khoảng trắng.
3. **Integration API:** tách CLI khỏi lõi, result sau cleanup; xác nhận năm scripts standalone giữ behavior và exit codes.
4. **Runner/report:** suite selection, aggregate JSON, deadlines/interruption; chạy unit không vcan và full có vcan.
5. **Cppcheck:** chạy baseline, xử lý findings, đưa gate vào wrapper có logs.
6. **Regression wrapper:** quick/full, cùng run directory, mapping bisect và không chạy trùng CTest.
7. **Nghiệm thu/document:** negative controls, cập nhật README và review diff. Commit/push/PR chỉ thực hiện khi được yêu cầu.

Tests mới tập trung vào failure paths của automation, dùng fake command executables/process fixture có kiểm soát, không yêu cầu sudo hoặc phá source thật:

- Configure/build/CTest trả code lỗi: wrapper trả đúng code, không chạy stage phụ thuộc.
- Clean target nguy hiểm, symlink hoặc CMake cache thuộc repo khác: từ chối và giữ nguyên marker files.
- Scenario assertion sai, app không ready, simulator fail và cleanup escalation: report fail, không còn child process.
- SIGINT/SIGTERM giữa scenario: không launch test kế tiếp, lưu partial report và cleanup app/simulator.
- Tool/interface thiếu: full fail; unit vẫn chạy; bisect chỉ skip prerequisite đã xác định.
- Invalid selection/zero tests không được thành pass; report ghi expected/actual/reason và artifact paths tồn tại.
- Test failure được wrapper map thành bad (`1`), không phải skip (`125`); report ghi đúng status khi teardown fail.

Không nhân bản tests TTC/decoder/runtime đã có. Failure controls dùng fixture hoặc temporary checkout, không commit logic sai vào source.

## 10. Lệnh nghiệm thu dự kiến

Sau khi implement, trên Ubuntu đã cài toolchain/GoogleTest/cppcheck và tạo venv:

```bash
.venv/bin/python scripts/build.py --build-type Debug --clean
.venv/bin/python scripts/run_tests.py --suite unit
.venv/bin/python scripts/static_analysis.py

bash scripts/setup_vcan.sh
.venv/bin/python scripts/run_tests.py --suite all
PYTHON=.venv/bin/python bash scripts/regression_test.sh --suite full

.venv/bin/python scripts/build.py --build-type Release --build-dir build-release
.venv/bin/python scripts/run_tests.py --suite all --build-dir build-release
```

Sau khi đã setup dependencies/vcan, lệnh vận hành full hằng ngày là:

```bash
PYTHON=.venv/bin/python ./scripts/regression_test.sh
```

Thêm executable bit cho shell wrapper khi implement. Chạy full liên tiếp hai lần để kiểm tra artifact isolation và process cleanup; kiểm tra report của cả successful và failed invocation. Nếu môi trường không hỗ trợ vcan, ghi rõ live gate chưa xác minh; unit/fixture tests không thay thế gate này.

## 11. Exit checklist

- [ ] Debug/Release build từ clean checkout với dependencies đã chuẩn bị; configure/build/CTest errors được propagate.
- [ ] Một lệnh regression full thực hiện build, static analysis, C++/Python unit và đủ năm live scenarios; không có test chạy trùng vô ý.
- [ ] Quick/unit chạy không cần vcan; full thiếu vcan trả lỗi rõ ràng.
- [ ] Năm integration entrypoints cũ vẫn chạy standalone; runner dùng đúng binary được chọn.
- [ ] Scenario fail, timeout, interruption và cleanup fail đều không tạo pass giả hoặc process sót.
- [ ] Reports/logs nằm dưới output root thống nhất, riêng từng run và tồn tại cả khi fail sớm.
- [ ] Cppcheck quality gate thật sự trả nonzero với controlled finding; baseline findings đã được review.
- [ ] Regression exit codes phân biệt good/bad/untestable và interrupt; không che source regression thành skip.
- [ ] README mô tả prerequisites, command, expected output, artifacts và troubleshooting.
- [ ] Không đưa binary, venv, logs vào commit; bàn giao commands/exit codes/artifact paths cho Phase 8.
