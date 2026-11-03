# Jenkins qua Nginx

Cấu hình chuẩn bị cho `http://jenkins.ice.tech` trên port 80, proxy tới Jenkins
đang chạy ở `127.0.0.1:8080`. Headers và WebSocket theo
[hướng dẫn Jenkins Nginx](https://www.jenkins.io/doc/book/system-administration/reverse-proxy-configuration-nginx/).

Chạy trên server:

```bash
cd /home/ice/projects/adas-integration-lab
bash scripts/setup_jenkins_proxy.sh
```

Script cài Nginx, thêm virtual host riêng, kiểm tra `nginx -t`, bật service,
thêm hosts trên server và kiểm tra trang login bằng đúng Host header. Không chỉnh default site hoặc
service khác đang dùng port 80. Nếu port 80 đã bị chiếm thì cần xử lý xung đột
trước khi Nginx có thể start. Smoke test bỏ qua proxy môi trường để kiểm tra
trực tiếp Nginx local và chờ worker reload hoàn tất.

Đã chuyển sang controller `192.168.222.132`: Nginx active/enabled, virtual host
được bật, Jenkins URL là `http://jenkins.ice.tech/`. Trang login trả HTTP 200
qua IP LAN cổng 80. Firewall UFW hiện không bật.

Trên máy dùng trình duyệt, thêm dòng sau vào hosts hoặc tạo DNS record tương ứng:

```text
192.168.222.132 jenkins.ice.tech
```

- Windows: mở Notepad với quyền Administrator, sửa
  `C:\Windows\System32\drivers\etc\hosts`.
- Linux/macOS: sửa `/etc/hosts` bằng sudo.

Chỉ thêm hosts trên server không khiến máy cá nhân phân giải được tên miền.
Sau khi tên được phân giải, mở `http://jenkins.ice.tech`, đăng nhập bằng tài khoản
Jenkins hiện có. Trong Manage Jenkins → System → Jenkins Location, đặt Jenkins URL
thành `http://jenkins.ice.tech/` rồi Save. Giữ Jenkins ở loopback port 8080.

Nếu trước đây đã thêm địa chỉ `.129` vào hosts trên máy cá nhân, thay dòng đó
bằng `.132`; không giữ hai dòng cùng hostname. Trên Windows chạy
`ipconfig /flushdns` sau khi lưu. Server `.129` hiện là build agent, không còn
chạy Jenkins controller. Xem [kiến trúc phân tán](JENKINS_DISTRIBUTED.md).
