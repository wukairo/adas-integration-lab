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

## Jenkins local trên server đồ án

Truy cập qua Nginx port 80: **http://jenkins.ice.tech**. Trên máy dùng trình
duyệt, thêm `192.168.222.129 jenkins.ice.tech` vào hosts nếu chưa có DNS phù hợp.
Xem [cấu hình và hướng dẫn reverse proxy](JENKINS_PROXY.md).

Controller kiểm chứng được đặt dưới `build-jenkins/` (ignored), bind `127.0.0.1:8080`, chạy bằng user ice. Tài khoản `admin`, mật khẩu riêng ở `build-jenkins/home/admin-password` (quyền 0600); không dùng mật khẩu sudo làm mật khẩu Jenkins. Kết nối qua SSH tunnel `ssh -L 8080:127.0.0.1:8080 <user>@<server>` rồi mở localhost:8080.

Job `adas-validation` hiện dùng local SCM nhánh `main` sau khi merge phần triển khai. Các runs #1/#2 trong evidence lịch sử chạy trên nhánh feature trước khi merge. Job local chưa chứng minh trigger từ GitHub hoặc repository rules. Cấu hình cho phép local Git checkout chỉ dành cho controller lab này. Chi tiết runs thực xem ACCEPTANCE.md.

Khởi động lại controller đã provision: `bash scripts/start_jenkins_lab.sh`. Template systemd `scripts/systemd/adas-jenkins.service.in` dùng placeholders `@USER@` và `@PROJECT@`; thay bằng user thường và đường dẫn clone rồi cài vào `/etc/systemd/system/adas-jenkins.service`. Dừng controller cũ trước khi bật service để tránh tranh port 8080. Không commit thư mục build-jenkins vì chứa tài khoản, logs và state.

Runtime Jenkins đã dùng để kiểm chứng: 2.580.2 LTS, SHA-256 WAR `d98032d2401c540a35613a82ed358921fcf3166d5e6eaaaf60a7941845be3251`, lấy từ [Jenkins download](https://www.jenkins.io/download/). Java 21; cài thêm `fontconfig libharfbuzz0b` nếu Java headless thiếu font manager. Plugins đã được tải bằng [plugin installation manager](https://github.com/jenkinsci/plugin-installation-manager-tool), gồm workflow-aggregator, pipeline-model-definition, git và timestamper cùng dependencies. Log bootstrap nằm trong build-jenkins/plugin-install.log.
