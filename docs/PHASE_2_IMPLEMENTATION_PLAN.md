# Phase 2 — Virtual CAN và CAN Receiver

## Mục tiêu và điểm bắt đầu

Triển khai trên branch `feature/phase-2-can-receiver`, tạo từ `main` sau Phase 1 (`b17299f`). Kết quả: `adas_app --can vcan0` nhận và in raw Classical CAN frames gửi bằng `cansend`; thoát sạch bằng SIGINT/SIGTERM.

Đọc trước `README.md`, `CMakeLists.txt`, `src/main.cpp`, `include/collision_warning.hpp`, tài liệu roadmap và mọi `AGENTS.md` áp dụng. Kiểm tra `git status` và branch trước khi sửa; giữ nguyên thay đổi không thuộc công việc. Nếu branch/base đã thay đổi, đánh giá trạng thái thực tế, không reset hoặc ghi đè công việc hiện có.

## Phạm vi

- Linux SocketCAN, Classical CAN với payload 0–8 byte.
- Script setup `vcan0`, receiver C++, chế độ CLI nhận CAN, hướng dẫn và kiểm tra thủ công.
- Giữ nguyên hành vi CLI Phase 1 và logic collision warning.
- Chưa làm DBC/decoder (Phase 3), GoogleTest (Phase 4), simulator, integration framework, CI/CD hoặc Jenkins.
- Không tự commit, merge hoặc push khi thực thi kế hoạch nếu chưa được yêu cầu trong phiên đó.

## Quyết định thiết kế bắt buộc

### Dữ liệu và ownership

Tạo `include/can_receiver.hpp` và `src/can_receiver.cpp`.

`CanFrame` có các trường: `std::uint32_t id`, `std::uint8_t dlc`, `std::array<std::uint8_t, 8> data`, `bool extended`. `id` là arbitration ID đã bỏ các flag SocketCAN; giới hạn 11 bit cho standard và 29 bit cho extended. Không truncate ID.

`CanReceiver` sở hữu duy nhất một file descriptor, đóng bằng RAII; cấm copy, có thể cấm luôn move để đơn giản. Nếu constructor lỗi sau khi mở socket, vẫn phải đóng descriptor. Không expose descriptor cho CLI và không đặt CAN dependency vào `adas_core`.

API gợi ý: constructor nhận tên interface, `std::optional<CanFrame> receive(int timeout_ms)`. Giá trị rỗng nghĩa là timeout, EINTR hoặc frame bị bỏ qua; lỗi thực sự được báo bằng exception có ngữ cảnh. Ghi rõ contract trong header; timeout phải hữu hạn, dùng 200 ms tại CLI.

### Chính sách frame và lỗi

- Hỗ trợ standard và extended data frames, kể cả DLC bằng 0.
- RTR frames: bỏ qua, không coi là data frame. Error frames: không bật subscription; vẫn kiểm tra và bỏ qua nếu nhận được.
- Không bật CAN FD; không dùng `canfd_frame`. Kiểm tra số byte đọc đúng `CAN_MTU` và DLC không vượt 8 trước khi copy.
- Frame có kích thước/DLC không hợp lệ: bỏ qua và ghi diagnostic ngắn trên stderr, không in thành frame hợp lệ.
- Tên interface rỗng/quá dài: reject trước khi lookup, không cắt ngắn tên. Dùng `if_nametoindex` hoặc ioctl với kiểm tra lỗi đầy đủ.
- Lỗi socket, bind, poll, read hoặc interface mất/down trong lúc nhận: diagnostic có thao tác/interface và lý do hệ thống; thoát nonzero. `POLLERR`, `POLLHUP`, `POLLNVAL` không được gây vòng lặp busy.
- Chỉ retry/bỏ qua EINTR; không nuốt lỗi khác. Không mở socket nonblocking trừ khi xử lý rõ EAGAIN.

### CLI và signal

Giữ `adas_app <speed_kmh> <distance_m> <closing_speed_mps>`, bổ sung `adas_app --can <interface>`. Kiểm tra mode CAN trước khi parse ba số; usage phải ghi cả hai chế độ.

- stdout chỉ chứa frame hợp lệ, một dòng mỗi frame; flush mỗi dòng để redirect log vẫn quan sát được ngay.
- Ví dụ standard: `CAN id=0x123 format=standard dlc=8 data=01 02 03 04 05 06 07 08`.
- Ví dụ extended: `CAN id=0x00000123 format=extended dlc=1 data=FF`.
- Zero payload: `CAN id=0x123 format=standard dlc=0 data=`.
- Hex uppercase, standard ID đủ 3 chữ số, extended đủ 8 chữ số, byte đủ 2 chữ số. DLC dùng decimal. Tránh trạng thái format hex làm ảnh hưởng trường khác.
- Dùng `sigaction` cho SIGINT/SIGTERM; handler chỉ đặt cờ `volatile std::sig_atomic_t`, không log/allocate/đóng socket trong handler.
- Vòng nhận kiểm tra cờ dừng sau mỗi lần receive; không block vô hạn và không busy-loop. Dừng bình thường trả 0; sai usage/input trả 2; lỗi CAN runtime/setup trả 1.

## Các bước triển khai

### 1. Script virtual CAN

Tạo executable `scripts/setup_vcan.sh`, Bash với `set -euo pipefail`.

1. Kiểm tra công cụ `ip`, `modprobe`; báo dependency thiếu với hướng dẫn cài `iproute2`, `kmod`.
2. Nếu chưa chạy root thì dùng `sudo` cho thao tác cần quyền, báo lỗi rõ nếu không có sudo. Không yêu cầu chạy app bằng root.
3. Load module `vcan`; nếu thất bại thì dừng và báo lỗi thật.
4. Nếu `vcan0` chưa tồn tại, tạo bằng `ip link add dev vcan0 type vcan`.
5. Nếu đã tồn tại, xác nhận đúng loại vcan; không thay đổi hoặc xóa interface khác loại.
6. Bật `vcan0` bằng `ip link set dev vcan0 up`, in trạng thái cuối.
7. Chạy lần hai phải thành công. Không dùng `|| true` để che lỗi quyền/kernel/network.

Không chạy script cài dependency toàn bộ nếu chỉ cần kiểm tra build. Không xóa interface có sẵn để test tính idempotent.

### 2. Receiver

Implement theo contract ở trên: tạo socket `PF_CAN/SOCK_RAW/CAN_RAW`, lookup interface, bind `sockaddr_can`, poll có timeout, đọc và validate `can_frame`, chuyển sang `CanFrame`.

Tách rõ giải mã metadata transport khỏi logic ADAS. Không tính TTC từ raw payload và không giả định ID VehicleState/RadarObject ở phase này.

### 3. CMake và CLI

- Thêm library `adas_can` cho receiver, include path và C++17, tắt compiler extensions, áp dụng cùng warnings như target hiện có.
- Chỉ build/link receiver và bật mode CAN khi `CMAKE_SYSTEM_NAME` là `Linux`; có thể dùng compile definition riêng cho CLI.
- Trên nền tảng khác, CLI số vẫn build; yêu cầu `--can` báo không được hỗ trợ và trả nonzero, không include Linux headers vô điều kiện.
- `adas_app` link `adas_core` và, trên Linux, `adas_can`; `adas_core` tiếp tục độc lập với CAN.
- Không thêm thư viện bên ngoài khi SocketCAN hệ thống đã đủ.

### 4. Xác minh

Build từ thư mục mới để tránh cache Phase 1:

```bash
bash -n scripts/setup_vcan.sh
cmake -S . -B build-phase2 -DCMAKE_BUILD_TYPE=Debug
cmake --build build-phase2 --parallel
bash scripts/setup_vcan.sh
bash scripts/setup_vcan.sh
ip -details link show vcan0
```

Nếu kernel không có vcan hoặc môi trường không cho CAP_NET_ADMIN, ghi rõ giới hạn; vẫn hoàn thành build và kiểm tra CLI không cần interface. Không tuyên bố CAN acceptance pass nếu chưa thực sự chạy. Cài `can-utils` trên Ubuntu VM nếu thiếu `cansend`/`candump`.

Terminal A:

```bash
./build-phase2/adas_app --can vcan0
```

Terminal B:

```bash
cansend vcan0 123#0102030405060708
cansend vcan0 123#
cansend vcan0 123#FF
cansend vcan0 00000123#FF
cansend vcan0 123#R
```

Kiểm tra các trường ID/format/DLC/payload đúng theo output contract; RTR không tạo dòng data. Gửi liên tiếp 10 frame, xác nhận nhận đủ và đúng thứ tự khi chỉ có sender này. Không dựa vào sleep cố định để suy ra receiver đã sẵn sàng; nếu dùng harness tạm, cần đợi bind thành công trước khi gửi.

| Kiểm tra | Kết quả bắt buộc |
| --- | --- |
| Setup hai lần | Cả hai trả 0, interface vẫn là vcan và UP |
| Frame 8/0/1 byte | Đúng DLC, không in byte dư |
| Extended ID | Giữ đủ ID, phân biệt với standard |
| RTR | Bỏ qua, receiver tiếp tục chạy |
| `--can nonexistent0` | Diagnostic stderr, exit 1, không treo |
| `--can` thiếu interface | Usage stderr, exit 2 |
| Ctrl+C khi idle/đang nhận | Kết thúc trong khoảng 1 giây, exit 0 |
| SIGTERM khi idle | Kết thúc trong khoảng 1 giây, exit 0 |
| Khởi động/dừng nhiều lần | Không crash; socket đóng sau mỗi lần |
| Redirect stdout sang file | Frame xuất hiện ngay sau khi nhận |

Việc xác minh malformed frame/DLC có thể cần sender đặc biệt vì kernel chặn dữ liệu không hợp lệ; không tuyên bố đã kiểm tra qua `cansend` nếu công cụ không gửi được. Review nhánh validation trong code, ghi rõ phần chưa thực nghiệm. Chỉ thử interface down trên interface test thuộc quyền quản lý của phiên; khôi phục UP sau khi kiểm tra.

Regression Phase 1: so sánh output chính xác và exit code:

| Arguments | Expected stdout | Exit |
| --- | --- | --- |
| `50 100 0` | `WarningLevel=NONE` | 0 |
| `80 20 7` | `WarningLevel=WARNING` | 0 |
| `80 10 10` | `WarningLevel=CRITICAL` | 0 |
| `80 20 10` | `WarningLevel=CRITICAL` (TTC=2) | 0 |
| `80 40 10` | `WarningLevel=WARNING` (TTC=4) | 0 |
| `301 10 1` | stderr `INVALID_INPUT` | 2 |
| `80 -1 1` | stderr `INVALID_INPUT` | 2 |
| `nan 10 1` | stderr `INVALID_INPUT` | 2 |

Không cần thêm test framework trong phase này; harness tạm để kiểm tra phải có timeout và cleanup process.

### 5. Tài liệu và bàn giao

Cập nhật `README.md`: trạng thái Phase 2, Linux dependencies, setup vcan, hai terminal gửi/nhận, output contract, exit codes, cách thoát và troubleshooting (missing vcan module, thiếu quyền setup, interface không tồn tại/down). Nhắc rõ raw frames chưa được decode và chưa gọi collision core từ CAN.

Kiểm tra `git diff --check`, review diff và `git status`. Không stage build outputs. Báo cáo file thay đổi, kết quả build/verification đã chạy, phần chưa kiểm tra cùng lý do và lệnh cần chạy tiếp trên VM.

## Chia commit khi được yêu cầu triển khai và commit

Chia thành 4 commit theo thứ tự dưới đây. Mỗi commit phải có phạm vi rõ, build được và không để lại code dở dang. Không chờ code xong toàn bộ mới commit một lần. Đây là cách chia khi phiên thực thi có yêu cầu commit; kế hoạch này không tự cấp quyền commit/merge/push.

### Commit 1 — Script setup vcan

Message: `feat: add idempotent virtual CAN setup script`

- Files: `scripts/setup_vcan.sh` (bao gồm executable bit).
- Trước commit: `bash -n`, chạy script hai lần trên Ubuntu có quyền phù hợp, xác nhận interface là vcan và UP.
- Nếu môi trường không cho setup vcan, ghi rõ phần chưa xác minh khi bàn giao; không báo script đã pass runtime.

### Commit 2 — Thư viện CAN receiver

Message: `feat: add RAII SocketCAN receiver`

- Files: `include/can_receiver.hpp`, `src/can_receiver.cpp`, phần CMake tạo target `adas_can` riêng trên Linux và cấu hình warnings/C++17.
- Chưa sửa CLI hoặc link receiver vào app; receiver là target độc lập, build được ngay trong commit này.
- Trước commit: clean configure/build, review ownership/error paths và validation; chạy regression CLI Phase 1.
- Kiểm tra nhận CAN qua CLI sẽ thực hiện ở commit 3; không tuyên bố commit này đã được kiểm tra end-to-end.

### Commit 3 — Chế độ CAN trong CLI

Message: `feat: receive and print CAN frames from CLI`

- Files: `src/main.cpp`, phần CMake link `adas_can` vào app trên Linux và compile definition cần thiết.
- Bao gồm dispatch CLI, output contract, signal handling và exit codes.
- Trước commit: build, regression Phase 1, các kiểm tra CLI/frame/shutdown trong mục xác minh. Nếu thiếu vcan, hoàn thành kiểm tra không phụ thuộc vcan và ghi rõ hạn chế.
- Nếu cần sửa receiver sau khi kiểm tra thực tế, đưa sửa liên quan vào commit này; không rewrite commit trước nếu chưa được yêu cầu.

### Commit 4 — Hướng dẫn sử dụng Phase 2

Message: `docs: document Phase 2 CAN workflow and verification`

- Files: `README.md`; chỉ thêm file kế hoạch trong `docs/` nếu được yêu cầu đưa nó vào Git.
- Ghi hướng dẫn cuối cùng khớp CLI đã triển khai, dependencies, output, exit codes và troubleshooting.
- Trước commit: đối chiếu ví dụ với kết quả thực tế, `git diff --check`, kiểm tra không stage build/log artifacts.

### Quy tắc thực hiện

- Trước mỗi commit, xem `git diff` và stage từng đường dẫn thuộc commit; không dùng `git add .` để gom thay đổi ngoài phạm vi.
- Thực hiện kiểm tra tương ứng trước khi commit; nếu lỗi thì sửa và chạy lại phần bị ảnh hưởng.
- Nếu xuất hiện thay đổi không thuộc Phase 2, giữ nguyên và không đưa vào commit.
- Sau commit cuối: working tree sạch đối với công việc Phase 2, liệt kê SHA/message và kết quả kiểm tra khi bàn giao. Thay đổi có sẵn của người dùng có thể vẫn còn và phải được báo riêng.
- Chỉ merge vào `main` hoặc push khi phiên thực thi có yêu cầu; không tự tạo lại branch/reset lịch sử.

## Checklist hoàn thành

- [ ] Script setup idempotent, kiểm tra loại interface và không che lỗi.
- [ ] Receiver RAII, không copy socket, không leak trên error path.
- [ ] Standard/extended data frames 0–8 byte được in đúng; RTR/error bị bỏ qua.
- [ ] Validation kích thước/DLC và lỗi hệ thống đầy đủ.
- [ ] SIGINT/SIGTERM kết thúc hữu hạn, không xử lý I/O trong handler.
- [ ] Linux build sạch warnings; Phase 1 regression pass.
- [ ] Đã xác minh nhận frame thực tế qua vcan trên Ubuntu VM.
- [ ] README đủ để người khác tái hiện; ghi trung thực các kiểm tra chưa chạy.

## Lưu ý Git cho file kế hoạch

Repo hiện ignore `/docs/`. File kế hoạch này được lưu local tại `docs/PHASE_2_IMPLEMENTATION_PLAN.md`; nếu được yêu cầu commit nó, dùng `git add -f docs/PHASE_2_IMPLEMENTATION_PLAN.md`. Không tự bỏ rule ignore toàn bộ docs.
