# DevOps — bạn tự triển khai

`jenkins/`: pipeline/job workflow. `agent/`: Linux/vcan provisioning.
Root `Jenkinsfile` chỉ là placeholder báo lỗi. Root `CMakeLists.txt` chưa ghép app.
Không có thay đổi nào trên server, service hay Jenkins job trong lần tách này.

Lưu ý: job hiện có nếu checkout revision mới sẽ gặp placeholder và fail có chủ đích.
Giữ baseline cũ cho job đang sử dụng cho tới khi bạn hoàn thiện pipeline mới.
Thư mục này không chứa credentials; cấu hình credentials trong Jenkins.
