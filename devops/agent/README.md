# Linux agent — TODO

- Kiểm tra CMake/GCC/GoogleTest/Python/cppcheck và dependencies simulator.
- Provision vcan một lần với quyền phù hợp; app/tests chạy user thường.
- Dùng Controller + Linux Agent hiện có; không cần thêm server.
- Serialize các run dùng chung vcan0, kể cả khác Jenkins jobs/manual runs.
- Thu phiên bản môi trường; clean checkout/build; kiểm tra chạy lại từ baseline.

Templates systemd/Nginx cũ ở `reference/legacy/`; chưa áp dụng cấu hình mới.
