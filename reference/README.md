# Triển khai trước khi tách

`legacy/` giữ nguyên code, tests, automation, cấu hình, README và pipeline trước
khi tách. CAN/ADAS được sao chép nguyên nội dung sang `components/` để phát triển tiếp.
Code legacy phục vụ tham khảo/khôi phục, không tham gia build mới.

Không chạy scripts trong legacy trực tiếp: chúng dùng vị trí file để xác định repo
root và có đường dẫn tương đối theo cấu trúc cũ. Workflow cũ ở đây không được
GitHub tự động kích hoạt. Tài liệu lịch sử trong `docs/` vẫn giữ nguyên.
