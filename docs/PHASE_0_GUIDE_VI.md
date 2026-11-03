# Phase 0 — làm trên VMware Workstation Pro

## Cập nhật sau khi tạo VM

Đã xác nhận VM `Ubuntu 64-bit`: 2 vCPU (1 socket × 2 cores), RAM 4096 MB, NAT, disk 40 GiB.
Đã bật VM, VMware Tools đã cung cấp IP `192.168.222.129` (IP có thể đổi).
ISO đang gắn là Ubuntu 26.04.1 **Server** AMD64; cần kiểm tra `/etc/os-release` trong guest để xác nhận OS thực tế.
Server dùng được cho lab, không cần cài lại Desktop. Các bước giao diện Desktop bên dưới chỉ áp dụng nếu dùng Desktop.
Baseline đã commit: `b5e3d41`; bỏ qua hướng dẫn tạo lại baseline bên dưới.
Chưa đăng nhập guest; package/toolchain Linux và build Linux chưa được xác minh.

Mục tiêu: Ubuntu có toolchain, repo đúng cấu trúc, build/run ra `Hello ADAS`.
Chưa cần Jenkins, Docker, collision logic hay CAN receiver. `vcan0` thuộc Phase 2.

## 1. Trạng thái đã kiểm tra

- Windows đã có Git, CMake 3.31 và GCC 14.2 qua MinGW.
- VMware Workstation đang mở; `vmrun list` trả `Total running VMs: 0` lúc kiểm tra.
- Có thể gọi `C:\Program Files\VMware\VMware Workstation\vmrun.exe` từ môi trường làm việc này.
- Điều này chưa có nghĩa là đã truy cập được Ubuntu. Chưa có guest đang chạy, IP/SSH hay phiên xác thực để cài package trong guest.
- Đã chuẩn bị skeleton, CMake C++17, app Hello ADAS, script cài Ubuntu và script verify.
- Build Windows chỉ là kiểm tra mã nguồn; Phase 0 vẫn cần build trên Linux và clean clone.

## 2. Tạo hoặc mở Ubuntu VM — bạn thao tác trong VMware

Nếu đã có Ubuntu VM: mở file `.vmx` bằng File → Open và Power on, bỏ qua bước tạo mới.

Nếu chưa có:

1. Tải Ubuntu Desktop **24.04 LTS, AMD64** từ https://releases.ubuntu.com/24.04/ (chọn ISO Desktop, không chọn ARM64).
   Hướng dẫn Ubuntu chính thức: https://ubuntu.com/desktop/docs/en/24.04/tutorial/install-ubuntu-desktop/
2. VMware → File → New Virtual Machine → Typical. Chọn ISO; nếu Easy Install gây khó hiểu, chọn cài OS sau rồi gắn ISO trong VM Settings → CD/DVD.
3. Guest OS: Linux / Ubuntu 64-bit. Đặt tên `adas-ubuntu`.
4. Gợi ý cho lab: 2 CPU cores, RAM 4 GB (8 GB nếu máy host đủ), disk 40 GB dạng growable, Network Adapter = NAT. Đây là cấu hình đề xuất cho lab, không phải yêu cầu cứng của spec. Chừa RAM cho Windows.
5. Khởi động VM → Install Ubuntu → tạo username/password của riêng bạn. Tùy chọn xóa đĩa chỉ dùng với **đĩa ảo của VM mới**, không thao tác lên ổ Windows.
6. Sau khi cài xong, restart và tháo ISO nếu được yêu cầu. Đăng nhập desktop, mở Terminal bằng Ctrl+Alt+T.

## 3. Đưa project vào Ubuntu

Cách dễ khi chưa có GitHub là Shared Folders:

1. Trong VMware: VM Settings → Options → Shared Folders → Always enabled → Add.
2. Host path: `D:\devops practice\ADAS CICT`; share name: `adas-project`. Có thể chọn Read-only vì sẽ copy vào home Linux.
3. Trong Ubuntu Terminal, cài công cụ chia sẻ rồi mount nếu chưa tự xuất hiện:

```bash
sudo apt update
sudo apt install -y open-vm-tools open-vm-tools-desktop
sudo mkdir -p /mnt/hgfs
sudo vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other
ls /mnt/hgfs/adas-project
```

Nếu đã thấy share thì không cần mount lại. Nếu báo share không tồn tại, kiểm tra tên share và restart guest sau khi cài VMware tools.

Copy sang Linux để tránh vấn đề quyền file và hiệu năng trên shared folder:

```bash
mkdir -p ~/projects
# Chỉ dùng đích mới, chưa chứa công việc khác:
cp -a /mnt/hgfs/adas-project ~/projects/adas-integration-lab
cd ~/projects/adas-integration-lab
```

Không copy build Windows sang build Linux. Script dùng `build/`; bản kiểm tra Windows dùng `build-windows/` riêng.

## 4. Cài dependency và build — đã có script

Chạy **trong Ubuntu**, không chạy ở PowerShell/Git Bash:

```bash
cd ~/projects/adas-integration-lab
bash scripts/setup_ubuntu.sh
bash scripts/verify_phase0.sh
```

Nhập password Ubuntu khi sudo hỏi (terminal không hiện ký tự). Script cài Git, GCC/Make, CMake, Python/pip/venv, can-utils, cppcheck, GoogleTest và công cụ hệ thống.
Chưa cài `python-can`/`cantools`: dành cho phase simulator; khi đó dùng virtual environment.

Kỳ vọng cuối output:

```text
Hello ADAS
PASS: Linux toolchain and Hello ADAS verified. GitHub/clean clone must be checked separately.
```

Nếu apt không tải được, kiểm tra network NAT và Internet trong Ubuntu trước. Nếu CMake báo cache từ máy khác, dùng build directory mới: `cmake -S . -B build-linux` và `cmake --build build-linux --parallel`, rồi chạy `./build-linux/adas_app`.

## 5. GitHub và baseline

Đã khởi tạo Git local trên nhánh `main`, nhưng chưa tạo được commit baseline do lỗi môi trường chạy lệnh. Không cần tạo Git history thứ hai nếu thư mục copy đã chứa `.git`.
Nếu copy `.git` sang Ubuntu và Git báo ownership không khớp, chỉ với bản copy trong home của bạn, chạy `sudo chown -R "$(id -un):$(id -gn)" ~/projects/adas-integration-lab`.

Tạo baseline trong Ubuntu (điền tên/email Git của bạn nếu chưa cấu hình):

```bash
git config user.name "TEN_CUA_BAN"
git config user.email "EMAIL_GIT_CUA_BAN"
git add .
git commit -m "chore: initialize ADAS integration repository"
```

Trên github.com, đăng nhập và tạo repo **adas-integration-lab**, chọn visibility mong muốn. Để repo rỗng: không thêm README/license/gitignore trên web vì local đã có.

Trong local repo (Windows hoặc Ubuntu), kiểm tra trước:

```bash
git status
git log -1 --oneline
git remote -v
```

Nếu chưa có remote, thay `YOUR_GITHUB_USERNAME` bằng tài khoản của bạn:

```bash
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/adas-integration-lab.git
git push -u origin main
```

Thực hiện đăng nhập GitHub theo hướng dẫn của Git trên máy bạn. Không gửi password/token vào chat.
Đây là bootstrap initial baseline; thay đổi tiếp theo đi qua `feature/*` và Pull Request theo plan.

## 6. Xác minh từ clean clone trên Ubuntu

Sau khi đã push, dùng một thư mục mới:

```bash
mkdir -p ~/phase0-check
cd ~/phase0-check
git clone https://github.com/YOUR_GITHUB_USERNAME/adas-integration-lab.git
cd adas-integration-lab
bash scripts/verify_phase0.sh
```

Phase 0 hoàn tất khi clean clone này build/run thành công, dependency đủ và baseline đã lên GitHub. Không đánh dấu hoàn tất chỉ vì build Windows thành công.

## 7. Nếu muốn trợ lý thao tác tiếp trong VM

Trợ lý hiện truy cập được shell Windows và `vmrun`, chưa điều khiển được cửa sổ VMware hay terminal guest.
Cách thuận tiện để chạy lệnh trong guest là SSH, sau khi bạn bật Ubuntu:

```bash
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
hostname -I
whoami
```

Gửi IP và username Ubuntu, cùng đường dẫn `.vmx` nếu muốn kiểm tra VM cụ thể. Không gửi mật khẩu/private key.
Truy cập SSH còn cần xác thực được thiết lập trên host; có IP không đồng nghĩa đã đăng nhập được. Bạn có thể tự chạy các script ở trên mà không cần SSH.
Nếu bật UFW, chỉ mở SSH cho IP host cần truy cập; không cần port-forward SSH ra Internet.

## Checklist

- [x] Skeleton, README, gitignore, CMake C++17 và Hello ADAS.
- [x] Script cài dependency Ubuntu và script verify.
- [ ] Ubuntu VM đã chạy, có Internet.
- [ ] Dependency được cài và verify pass trong Ubuntu.
- [ ] GitHub repo, push baseline và clean clone verify.
