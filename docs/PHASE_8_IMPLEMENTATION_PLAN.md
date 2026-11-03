# Phase 8 — GitHub Actions + Jenkins CI/CT

## 1. Mục tiêu và căn cứ

Đưa automation Phase 7 vào Git workflow: Pull Request chạy quick CI trên GitHub Actions; sau merge `main`, Jenkins chạy build, static analysis, unit và live SocketCAN integration, rồi lưu artifacts đủ để truy vết cả run pass và fail.

Căn cứ:

- [Roadmap tổng thể](ADAS_CI_CT_Implementation_Plan.md), Phase 8–9.
- [Project specification](adas_software_integration_ci_ct_project_spec.md), Module 14–17 và 20: pipeline, Git workflow, monitoring và artifact traceability.
- [Plan Phase 7](PHASE_7_IMPLEMENTATION_PLAN.md), [README](../README.md) và implementation thực tế trong `scripts/`, `integration/`, `tests/`, `CMakeLists.txt`.

Baseline đã đọc ngày 23/10/2026:

- Branch hiện tại là `main`; working tree tracked sạch tại thời điểm lập plan. Chưa có `Jenkinsfile`; `.github/workflows/` mới có `.gitkeep`.
- `scripts/build.py` đã configure → build → CTest, hỗ trợ Debug/Release, `--skip-tests`, `--build-dir`, `--report-dir` và `--run-dir`.
- `scripts/run_tests.py --suite unit` chạy CTest và Python unittest; `--suite integration` chạy năm scenario `normal`, `warning`, `critical`, `radar_timeout`, `invalid_signal`. Runner dùng binary trong build directory được truyền, không tự build.
- `scripts/static_analysis.py` đã gate cppcheck và xuất `static_analysis.json`. Các runner xuất JSON/raw logs; chưa có JUnit XML adapter.
- `scripts/regression_test.sh` đã cung cấp quick/full nhưng gộp build và configure, mặc định Debug. Không dùng wrapper này để giả lập các Jenkins stage riêng.
- `scripts/setup_vcan.sh` tạo cố định `vcan0`, có gọi `sudo` khi cần; không phù hợp để gọi tùy ý trong CI không tương tác.
- Chưa có `scripts/collect_system_info.py`, packaging script hoặc runtime YAML trong `config/`. CMake dùng C++17, GoogleTest hệ thống và minimum CMake 3.16; Python scripts có type syntax cần Python 3.10 trở lên.
- `/docs/` đang bị ignore trong `.gitignore`; plan mới cần được add có chủ đích khi commit.

Đây là kế hoạch triển khai, chưa phải xác nhận CI hoạt động. Chưa chạy lại build/test, chưa xác minh GitHub settings, Jenkins instance, agent hay quyền SocketCAN trong phiên viết plan.

## 2. Phạm vi và đầu ra

| Đầu ra | Nội dung |
| --- | --- |
| `.github/workflows/ci.yml` | PR quick CI, timeout, checkout, dependencies, configure/build, unit gate và upload logs |
| `Jenkinsfile` | Full pipeline cho `main`, agent label rõ ràng, stage gates và archive trong `post always` |
| `scripts/package_artifact.py` | Đóng gói binary đã qua gate, DBC, metadata và checksum; không rebuild binary khác |
| `docs/PHASE_8_CI_SETUP.md` | Runbook GitHub checks, Jenkins job/agent/trigger, provisioning vcan, recovery và bằng chứng nghiệm thu |
| `README.md` | Commands CI, trạng thái checks, artifact paths và liên kết runbook |
| Cấu hình ngoài repo | Required PR check/review; Jenkins job theo dõi `main`, agent Linux và trigger |

Giữ nguyên behavior ứng dụng, simulator và state oracle của Phase 6–7. Không thêm Jenkins/GitHub credentials vào repo. Không triển khai Azure, metrics exporter, dashboard, coverage, lịch sử bisect hoặc fault scenarios mới trong phase này.

Các lựa chọn runner, timeout, retention và layout bên dưới là thiết kế đề xuất; kiểm tra tính tương thích trên hạ tầng thực khi implement.

### Ranh giới với Phase 9 và release

Roadmap Phase 8 có stage System Information, nhưng collector đầy đủ thuộc Phase 9. Phase 8 ghi build diagnostics dạng text: timestamp UTC, commit, toolchain, kernel và tình trạng vcan. Giữ stage System Information để lưu diagnostics đó; không gọi script chưa tồn tại hoặc đặt điều kiện bỏ qua rồi tuyên bố đã có monitoring. Phase 9 bổ sung `system_info.json` với CPU/RAM/Disk/Load Average và archive cùng reports.

Package trong Phase 8 là artifact của từng build `main`, có commit/build identity. Tag release `v1.0.0`, GitHub Release và trigger theo tag chưa thuộc gate này; khi làm release sẽ mở rộng contract naming/version. Không tạo `config/adas.yaml` giả vì runtime hiện chưa đọc file đó.

## 3. Contract CI chung

- Chạy trên Linux Ubuntu với toolchain hệ thống; chọn và ghi rõ image/OS baseline khi implement. Python tối thiểu 3.10; tạo `.venv` trong workspace và cài `requirements.txt`.
- Dependencies: Git, C++ compiler/build-essential, CMake/CTest, GoogleTest CMake package, Python/venv/pip; Jenkins thêm cppcheck, iproute2, can-utils, kmod và kernel hỗ trợ vcan.
- Không gọi `scripts/setup_ubuntu.sh` trong job: script này dành cho provisioning VM và cài cả VMware tools. PR runner chỉ cài packages cần dùng; agent Jenkins được admin chuẩn bị trước.
- Build CI dùng `Release`, `BUILD_TESTING=ON`, directory `build-ci/`. Unit và integration kiểm thử đúng `build-ci/adas_app`; package lấy chính binary này.
- Mỗi job có workspace riêng, xóa build/report cũ của job trước khi bắt đầu. Khởi tạo `build-ci/reports/ci/` ngay sau checkout và trước các stage có thể fail; không dùng `--clean` sau khi đã ghi diagnostics vào cây build.
- Log paths và return code là contract; nonzero phải làm stage/job fail. Không dùng `|| true`, `continue-on-error` hoặc catch rồi trả success cho build/test/static-analysis gate.
- Không có unit test được discover, thiếu tool, thiếu vcan hoặc thiếu artifact bắt buộc đều phải fail rõ ràng. Không map lỗi CI thành bisect skip `125`.
- Timeout đề xuất: PR job 15 phút, Jenkins pipeline 30 phút, integration stage 10 phút. Chốt lại theo thời gian đo trên agent; timeout phải để đủ thời gian cleanup và archive.
- Không cache CMake output hoặc reports ở phiên bản đầu. Nếu thêm cache dependency sau này, key phải theo OS/Python và hash requirements; không reuse executable từ commit khác.

## 4. GitHub Actions — Quick CI trên Pull Request

### 4.1. Workflow và required check

- [ ] Trigger `pull_request` vào `main`, gồm mở PR, cập nhật commit và reopen; thêm `workflow_dispatch` để chẩn đoán thủ công nếu cần.
- [ ] Job/check có tên ổn định, đề xuất `quick-ci`; `permissions: contents: read`. Dùng `pull_request`, không chạy mã PR qua `pull_request_target` có quyền ghi/secrets.
- [ ] Checkout source, cài system packages và Python dependencies. Chọn phiên bản/SHA của actions tương thích runner tại thời điểm implement; ghi lựa chọn trong review.
- [ ] Configure → Build → Unit Test là ba step riêng; mặc định chỉ một cấu hình Release để giữ quick CI gọn.
- [ ] Unit Test gọi runner Phase 7 để có cả C++ và Python tests. Không yêu cầu vcan hoặc quyền mạng đặc biệt trên PR runner.
- [ ] Upload reports với điều kiện `always()`, tên artifact gồm run ID/attempt, retention đề xuất 14 ngày. Giữ console logs cho lỗi xảy ra trước khi tạo được workspace/report.
- [ ] Có concurrency theo PR và cancel run cũ khi PR cập nhật; không làm thay đổi tên required check.

Command contract sau khi dependencies sẵn sàng, chạy từ repo root:

```bash
mkdir -p build-ci/reports/ci
cmake -S . -B build-ci -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build-ci --parallel 2
.venv/bin/python scripts/run_tests.py --suite unit \
  --build-dir build-ci --run-dir build-ci/reports/ci/unit
```

Hai lệnh CMake cần được capture stdout/stderr vào `reports/ci/configure.*.log`, `build.*.log` khi implement. Nếu dùng `tee`, bật `pipefail` để giữ lỗi command gốc. Runner unit đã kiểm tra discovery và chạy CTest, không chạy CTest thêm lần nữa trong workflow.

### 4.2. Git workflow

- [ ] Làm implementation trên feature branch, mở PR; không push trực tiếp vào `main`.
- [ ] Sau lần workflow đầu tạo check, cấu hình branch protection/ruleset bắt buộc `quick-ci` thành công và review trước merge, áp dụng cho `main` theo quyền repo thực tế.
- [ ] Không dùng path filters khiến required check không xuất hiện với PR chỉ sửa docs; PR nào vào `main` cũng phải có kết luận check.
- [ ] Ghi trong runbook cách xem checks, tải logs và re-run. Workflow YAML không tự cấu hình được branch protection; đây là bước setup ngoài repo cần evidence riêng.

## 5. Jenkins — Full CI/CT sau merge main

### 5.1. Controller, agent và vcan

- [ ] Controller dùng account thông thường; build chạy trên Linux agent chuyên dụng, label đề xuất `linux-socketcan`, tách khỏi controller.
- [ ] Provision toolchain, Java/runtime theo Jenkins deployment và kernel vcan trước khi đăng ký agent. Pipeline tạo venv/cài requirements bằng user của agent, không apt/sudo trong mỗi build.
- [ ] Admin dùng `scripts/setup_vcan.sh` khi provision host. Đảm bảo `vcan0` được khôi phục sau reboot trước khi agent nhận job, ví dụ service do admin quản lý.
- [ ] Pipeline chỉ kiểm tra `ip -details link show dev vcan0`, interface UP và khả năng mở SocketCAN bằng account agent. Không coi tên interface tồn tại là đủ; không dùng physical CAN interface để chạy tests.
- [ ] Agent chạy trực tiếp trong VM/host là baseline. Nếu dùng container, phải chứng minh network namespace chứa vcan và quyền truy cập hoạt động; thiếu prerequisite là Environment fail.
- [ ] `disableConcurrentBuilds()` để các run cùng job không gửi CAN đồng thời. Vì lock đó không bảo vệ job khác, baseline dành riêng agent/vcan0 cho job này, một executor và không có simulator thủ công chạy chung. Nếu chia sẻ agent, bắt buộc thêm resource lock dùng chung mọi job truy cập vcan0.
- [ ] Không reset/delete vcan trong `post`, không `pkill` toàn hệ thống. Runner chịu trách nhiệm dừng/reap process do nó tạo; kiểm tra thêm khi abort/timeout vì runner dùng process group riêng.

### 5.2. Job và trigger

- [ ] Tạo Pipeline from SCM trỏ `Jenkinsfile`, branch `main`; checkout đúng revision của build và ghi `git rev-parse HEAD`. Tắt implicit checkout nếu đã có Checkout stage riêng.
- [ ] Bật webhook push cho `main`; nếu không có endpoint nhận webhook thì dùng SCM polling và ghi rõ độ trễ. Chỉ chọn một cơ chế chính để tránh build trùng; có manual build để recovery.
- [ ] Jenkins đọc repo bằng credentials được quản lý trong Jenkins khi cần; không echo token hoặc archive môi trường chứa secrets.
- [ ] Chỉ chạy trusted `main` trên agent SocketCAN; PR vẫn do GitHub Actions xử lý.
- [ ] Đặt build retention, đề xuất giữ 20 build và artifacts 14 ngày; kiểm tra dung lượng thực tế trước khi chốt.

### 5.3. Stage contract

| Stage | Command/trách nhiệm | Điều kiện fail |
| --- | --- | --- |
| Checkout | Checkout revision, chuẩn bị workspace/report root sạch, lưu commit | SCM lỗi hoặc không xác định commit |
| Environment | Kiểm tra tools, tạo venv, cài requirements; ghi tool versions và vcan state | Dependency/network install lỗi, vcan thiếu/down hoặc không mở được socket |
| Configure | `cmake -S . -B build-ci -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON` | Configure/GoogleTest discovery configuration lỗi |
| Build | `cmake --build build-ci --parallel 2` | Compiler/linker lỗi |
| Static Analysis | `.venv/bin/python scripts/static_analysis.py --run-dir build-ci/reports/ci/static-analysis` | Wrapper hoặc quality gate nonzero |
| Unit Test | `.venv/bin/python scripts/run_tests.py --suite unit --build-dir build-ci --run-dir build-ci/reports/ci/unit` | C++/Python tests lỗi hoặc test discovery rỗng |
| Integration Test | `.venv/bin/python scripts/run_tests.py --suite integration --build-dir build-ci --interface vcan0 --run-dir build-ci/reports/ci/integration` | Bất kỳ scenario/preflight/cleanup lỗi hoặc scenario bắt buộc không chạy |
| System Information | Ghi build diagnostics text, timestamp và commit; Phase 9 bổ sung collector JSON | Không ghi được diagnostics bắt buộc |
| Package | Đóng gói chính executable Release đã test, DBC và version metadata | Input thiếu/sai commit hoặc tạo package/checksum lỗi |
| Archive Artifact | Publish artifacts qua `post { always { ... } }`, kể cả stage trước fail | Run pass thiếu output bắt buộc hoặc archive không thành công |

Dùng stage riêng thay vì gọi cả `regression_test.sh --suite full` rồi đánh dấu toàn bộ gate ở một stage. Tái sử dụng `run_tests.py` và `static_analysis.py` cho lifecycle/assertions/reports; không viết lại oracle trong Groovy. Configure/Build là CMake trực tiếp để giữ attribution đúng stage, không cần mở rộng CLI của `build.py` chỉ để phục vụ Jenkins.

Pipeline dừng các stage phụ thuộc sau gate lỗi. `post always` vẫn archive diagnostics, reports và logs đã có; không package binary khi các gate chưa pass. Diagnostics cơ bản được ghi sớm ở Environment để vẫn có dữ liệu khi chưa đến System Information.

## 6. Reports, CAN trace và packaging

Layout đề xuất dùng chung giữa CI commands:

```text
build-ci/
  adas_app
  reports/ci/
    environment.txt
    configure.stdout.log / configure.stderr.log
    build.stdout.log / build.stderr.log
    static-analysis/static_analysis.json
    unit/summary.json
    integration/summary.json
    integration/integration/<scenario>-<run-id>/...
    system-info.txt
    can-trace.log              # chỉ khi capture được bật và chạy thành công
  package/
    release/bin/adas_app
    release/dbc/vehicle.dbc
    release/version.txt
    adas-app-<short-sha>-<build-number>.tar.gz
    adas-app-<short-sha>-<build-number>.tar.gz.sha256
```

- [ ] Archive có chọn lọc `build-ci/reports/**`, package tarball/checksum và `build-ci/adas_app` nếu đã build thành công. Không archive toàn workspace, venv, `.git`, credentials hay mọi CMake object file.
- [ ] Report/logs là bắt buộc cho stage đã chạy. Nếu Environment/checkout fail sớm, cho phép chưa có test reports nhưng phải giữ build failed và diagnostic có sẵn; không dùng `allowEmptyArchive` để che mất package của run được coi là pass.
- [ ] JSON và raw logs là report contract bắt buộc ở phase này. Không gọi Jenkins `junit` lên file JSON hoặc giả định đã có XML. JUnit dashboard là tùy chọn riêng sau khi có adapter thực và kiểm thử mapping failure/error/not_run.
- [ ] Nếu thu CAN trace, dùng `candump` trên vcan0, bắt đầu trước integration, xác nhận process còn sống, lưu stderr và dừng/reap trong `finally`/`post`. Chỉ kill PID/process group của run; không để lỗi thu trace che lỗi integration gốc. Trace không thay assertions của app.
- [ ] CAN trace là artifact tùy chọn có trạng thái rõ ràng; mặc định JSON/app/simulator logs đã đủ gate. Chỉ archive trace khi đã tạo, không ghi claim có trace dựa trên file rỗng do redirect.
- [ ] `scripts/package_artifact.py` nhận build directory, output directory, commit và build number theo CLI được chốt khi implement. Từ chối binary/DBC thiếu, output trùng có thể ghi đè artifact cũ hoặc metadata không hợp lệ; trả nonzero nếu thất bại.
- [ ] `version.txt` ghi full commit SHA, build number, timestamp UTC, `build_type=Release`, compiler/toolchain thực dùng trong CMake cache. Không lấy compiler mặc định khác binary rồi gắn vào metadata.
- [ ] Package không chạy lại build. Sau tạo tarball, liệt kê/unpack trong thư mục tạm, kiểm tra layout và checksum; smoke test binary bằng CLI collision hiện có, không yêu cầu vcan để kiểm tra unpack.
- [ ] Artifact hướng tới Linux cùng kiến trúc/toolchain runtime đã ghi; chưa cam kết portable sang mọi distribution hoặc static linking.

## 7. Thứ tự triển khai

1. **Chốt baseline local:** dùng build directory mới, build Release, cppcheck, unit và đủ năm live scenarios. Ghi thời gian để điều chỉnh timeout; prerequisite live chưa đủ phải được giải quyết trước nghiệm thu Jenkins.
2. **Quick CI:** thêm workflow và README; mở PR để xác nhận runner cài được dependencies, tests không cần vcan và upload logs khi fail. Cấu hình required check/review sau khi tên check đã xuất hiện.
3. **Provision Jenkins:** controller/agent, vcan sau reboot, credentials và job `main`; thử commands bằng đúng account agent trước khi đưa vào Jenkinsfile.
4. **Full pipeline:** triển khai từng stage, cùng layout reports, fail propagation, diagnostics và `post always`; xác minh cleanup khi abort/timeout.
5. **Package:** thêm helper packaging và kiểm tra success/missing input bằng temp directories. Nối stage sau toàn bộ quality gates và validate archive completeness.
6. **Trigger và nghiệm thu:** merge PR hợp lệ, đối chiếu commit Jenkins build với commit `main`, chạy failure-path matrix, hoàn thiện runbook/evidence và bàn giao Phase 9.

Không cần thêm test lặp lại collision/decoder/runtime. Test code mới tập trung vào packaging input validation, metadata/checksum và failure propagation nếu thêm helper CI; cấu hình Actions/Jenkins cần kiểm tra trên chính engine tương ứng, local tests không thay thế được.

## 8. Ma trận nghiệm thu

| Tình huống | Kết quả phải quan sát được |
| --- | --- |
| PR hợp lệ, không có vcan | `quick-ci` xanh, C++/Python unit chạy, reports tải được |
| PR có unit assertion fail trong nhánh thử riêng | Check đỏ, required check chặn merge, có log assertion |
| Configure hoặc compile lỗi có kiểm soát | Đỏ đúng step/stage, không chạy tests/package phụ thuộc; archive logs đã có |
| Merge main hợp lệ | Jenkins tự chạy qua webhook/polling, SHA đúng revision, đủ năm live scenarios pass |
| Thiếu/down vcan trên agent thử cô lập | Environment đỏ với lý do rõ, không skip thành pass |
| Cppcheck controlled finding | Static Analysis đỏ, Package không chạy, có report finding |
| Integration assertion fail bằng fixture/checkout thử | Integration Test đỏ, summary + app/simulator logs có expected/actual, không có package mới |
| Abort/timeout giữa integration | Build aborted/failed theo nguyên nhân, không còn app/simulator/capture process của run; run kế tiếp pass |
| Hai thay đổi main liên tiếp | Jenkins không tranh chấp vcan; mỗi build có revision/artifacts riêng |
| Package input thiếu hoặc checksum/archive lỗi | Package/archive đỏ, không công bố package hợp lệ giả |
| Run pass hoàn chỉnh | Tarball unpack được, checksum đúng, binary trùng bản đã test, metadata khớp commit |
| Agent reboot | vcan được provision lại trước khi job chạy; full pipeline pass lần nữa |

Failure controls chỉ thực hiện trên feature branch, fixture, temporary checkout hoặc Jenkins job/agent thử cô lập; không merge code lỗi vào `main` để chứng minh gate. Những lỗi chỉ có thể thử trên nhánh thử Jenkins phải dùng job validation riêng, không mở quyền chạy mọi PR trên production agent.

Runbook lưu URL PR/check và Jenkins build, commit SHA, selected suites, return codes, report/package paths cùng kết quả kiểm tra cleanup. Chạy hai full build liên tiếp và một failure-path build; kết quả local đơn lẻ không đủ tuyên bố trigger/branch protection đã hoạt động.

## 9. Exit checklist và bàn giao

- [ ] `.github/workflows/ci.yml` chạy thật trên PR vào `main`, pass/fail phản ánh C++/Python unit gate, có reports kể cả failure.
- [ ] Required check/review được cấu hình và kiểm tra; flow feature branch → PR → merge được ghi trong runbook.
- [ ] Jenkins job `main` tự trigger, checkout đúng revision và build trên Linux agent thường, có vcan0 UP mà pipeline không cần sudo.
- [ ] Các stage Configure, Build, Static Analysis, Unit, Integration có lỗi thì fail đúng stage, không package khi gate fail.
- [ ] Đủ năm live scenarios chạy trên binary Release của chính build đó; không reuse executable hoặc reports cũ.
- [ ] Abort/timeout/failure cleanup được kiểm tra; các job không tranh chấp cùng vcan0.
- [ ] Logs/JSON/diagnostics truy cập được từ Jenkins khi pass và fail; CAN trace chỉ được claim khi thực sự capture.
- [ ] Package/checksum/metadata hợp lệ, unpack và smoke test pass; không có runtime config giả.
- [ ] README và setup runbook đủ để dựng lại job/agent, khôi phục vcan sau reboot và tìm artifacts.
- [ ] Evidence phân biệt rõ việc đã kiểm chứng với hạ tầng chưa sẵn sàng; không đánh dấu hoàn tất chỉ vì đã viết YAML/Jenkinsfile.
- [ ] Bàn giao Phase 9: thay/bổ sung diagnostics text bằng collector `system_info.json` đầy đủ, giữ archive/failure contract; chưa gọi diagnostics snapshot là real-time monitoring.
