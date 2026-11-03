# Runbook CI/CT và demo

## Linux agent

1. Clone repo, chạy `bash scripts/setup_ubuntu.sh`, tạo venv và cài requirements.
2. Provision `bash scripts/setup_vcan.sh`. Xác nhận `ip -details link show vcan0` và user agent bind được SocketCAN.
3. Dành riêng vcan0 cho một agent/executor, label `linux-socketcan`. Jenkinsfile disableConcurrentBuilds chỉ khóa cùng job; nhiều job phải dùng agent/bus riêng hoặc shared resource lock.
4. Jenkins controller/agent chạy user thường. Java/plugin requirements xem [Jenkins Linux](https://www.jenkins.io/doc/book/installing/linux/) và [WAR deployment](https://www.jenkins.io/doc/book/installing/war-file/). Cần Pipeline, Git, Declarative Pipeline, Timestamper.
5. Kiểm tra đủ dung lượng cho CMake/venv/reports và retention trước khi build.

Để khôi phục vcan sau reboot (admin provision một lần):

```bash
sudo install -D -m 0755 scripts/setup_vcan.sh /usr/local/libexec/adas-setup-vcan
sudo install -m 0644 scripts/systemd/adas-vcan.service /etc/systemd/system/adas-vcan.service
sudo systemctl daemon-reload
sudo systemctl enable --now adas-vcan.service
```

Service chỉ tạo/bật interface, không xóa bus đang dùng. Khi đổi kernel kiểm tra modules vcan tương ứng. Chạy lại service không thay interface cùng tên nếu không phải vcan.

## Jenkins job

Tạo Pipeline from SCM, Git repository của đồ án, branch `*/main`, Script Path `Jenkinsfile`. Configure credentials qua Jenkins nếu repo private. Jenkinsfile sử dụng checkout revision của build, tạo workspace sạch và full Release gate. SCM polling `H/5 * * * *` là trigger mặc định; khi chuyển webhook thì bỏ polling để tránh build trùng. Release tag dùng job riêng với branch/tag spec tương ứng; local tag chưa push không tự trigger remote.

Artifacts: `build-ci/reports/ci/**`, `build-ci/package/**`, executable Release. Tìm unit/integration summary JSON, logs app/simulator, static analysis report, system_info JSON và version.txt trong tarball. Các JSON chưa phải JUnit XML; không đưa JSON vào bước junit. Post archive dữ liệu đã có kể cả lỗi; run lỗi sớm có thể không có test/package. Package chỉ chạy sau mọi gate đạt.

GitHub: tạo PR vào main để chạy check `quick-ci`; bật required check và review trong repository rules sau khi check xuất hiện. Quyền admin/repository và credentials phải được cấu hình bởi tài khoản có quyền. Không coi workflow YAML tồn tại là bằng chứng check/branch protection đã chạy.

## Nghiệm thu pass/fail

- Hai full builds liên tiếp: cùng quality gates, đủ chín live scenarios, SHA checkout khớp metadata và package.
- Failure thử trên checkout/job cô lập: đổi assertion C++ hoặc threshold để Unit Test đỏ; Package phải bị skip, test logs vẫn archive. Không merge regression vào main.
- Thiếu/down vcan trên agent thử: Environment đỏ; không skip integration thành pass.
- Abort giữa integration: kiểm tra không còn app/simulator/candump của run; run tiếp theo phải đạt. Không dùng pkill toàn máy.
- Package missing binary/metadata hoặc checksum sai phải nonzero; helper có negative-path tests.
- Sau reboot: kiểm tra service + interface rồi chạy full pipeline. Không tự reboot server trong khi đang có phiên làm việc.

## Demo local từ source sạch

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash scripts/setup_vcan.sh
.venv/bin/python scripts/build.py --build-type Release --build-dir build-demo
.venv/bin/python scripts/static_analysis.py
.venv/bin/python scripts/run_tests.py --suite all --build-dir build-demo
.venv/bin/python scripts/collect_system_info.py --build-dir build-demo --output build-demo/reports/system_info.json
.venv/bin/python scripts/package_artifact.py --build-dir build-demo --output-dir build-demo/package --build-number demo
.venv/bin/python scripts/demo_bisect.py
```

Để release có tên version: tạo annotated tag sau khi đã commit và kiểm chứng source, configure/build lại rồi package. `git push origin <branch>` và `git push origin v1.0.0` là bước công bố remote theo quyền của repository; không ghi credentials vào repo.

## Jenkins phân tán đang vận hành

Controller và Nginx chạy trên `192.168.222.132`; build/test CAN chạy trên agent
`192.168.222.129`, user `jenkins-agent`, label `linux-socketcan`, một executor.
Controller có `0` executor. Agent kết nối WebSocket qua cổng 80.

Truy cập **http://jenkins.ice.tech**, hosts trên máy dùng trình duyệt phải trỏ
`192.168.222.132 jenkins.ice.tech`. Username/password, credentials, history và
artifacts Jenkins được giữ nguyên sau migration.

Xem [runbook controller/agent](JENKINS_DISTRIBUTED.md) cho paths, services,
SCM credential chỉ đọc, rollback snapshot và troubleshooting; xem
[cấu hình Nginx](JENKINS_PROXY.md) cho virtual host. Jenkins runtime không còn
phụ thuộc thư mục source/build-jenkins trên server `.129`.

Job `adas-validation` dùng SCM qua SSH tới source repo trên `.129`, branch
`*/main`. Job failure demo cũ được giữ history nhưng disabled. Các runs #1/#2
trong evidence gốc được thực hiện trước migration; bằng chứng migration ghi
riêng, không thay thế kết quả lịch sử.

Runtime đang dùng Jenkins 2.580.2 LTS, Java 21. WAR SHA-256:
`d98032d2401c540a35613a82ed358921fcf3166d5e6eaaaf60a7941845be3251`.
