# Python automation — bạn tự viết

- Build helper: configure/build, log commands, timeout và propagate exit codes.
- Test orchestrator: start app, wait ready, run simulator, assert results, cleanup children.
- Static analysis: tool errors/findings phải fail gate đúng cách.
- Diagnostics: system/toolchain/source identity, logs và CAN trace.
- Baseline/package: source SHA, config/DBC hashes, reports, artifact checksum và smoke test.

Mỗi thao tác cần chạy được local trước khi gọi từ Jenkins. Thiếu prerequisites
không được báo pass. Không copy nguyên script cũ mà chưa cập nhật đường dẫn.
Python dependencies cũ có trong `reference/legacy/requirements.txt`.
