# Phase 4 — Unit Tests với GoogleTest và CTest

## 1. Mục tiêu và baseline

Tạo regression baseline cho collision core và CAN decoder, chạy bằng CTest mà không cần CAN interface, sudo hoặc process nền.

Căn cứ: [roadmap](ADAS_CI_CT_Implementation_Plan.md), [specification](adas_software_integration_ci_ct_project_spec.md), [plan Phase 3](PHASE_3_IMPLEMENTATION_PLAN.md), README và implementation hiện tại.

Đã kiểm tra khi viết plan ngày 18/10/2026:

- Branch hiện tại: `feature/unit-tests`; HEAD `c32ccec` (Phase 3).
- `adas_core` chứa `evaluateCollisionRisk`; `adas_decoder` chứa hai API decode thuần C++17, không phụ thuộc SocketCAN.
- `adas_can` chỉ được tạo trên Linux; `adas_app` có CLI số, `--can`, `--decode`.
- `tests/` chỉ có `.gitkeep`; CMake chưa bật testing hoặc tìm GoogleTest.
- Configure/build Debug sạch trong `/tmp/adas-phase4-baseline` thành công, không thấy compiler warning; `ctest -N` báo **Total Tests: 0**. Đây chưa phải kết quả pass unit tests.
- Môi trường hiện tại có GTest CMake package; `scripts/setup_ubuntu.sh` đã liệt kê `libgtest-dev`.

Trước khi implement: đọc `AGENTS.md` nếu có, kiểm tra lại branch/status/API; giữ nguyên các thay đổi đang có. Không tạo branch mới nếu đang đúng `feature/unit-tests`.

## 2. Phạm vi và file thay đổi

| File | Việc cần làm |
| --- | --- |
| `CMakeLists.txt` | Bật CTest, tìm GoogleTest trong nhánh BUILD_TESTING, thêm hai executable và đăng ký test |
| `tests/test_collision_warning.cpp` | Cases và boundaries cho collision API |
| `tests/test_can_decoder.cpp` | Vectors DBC, signedness, flags, range và lỗi cho cả hai decoder |
| `README.md` | Hướng dẫn dependency/build/CTest, trạng thái Phase 4 và phạm vi đã kiểm tra |

Không cần sửa production API để thuận tiện cho test. Chỉ sửa implementation nếu test phát hiện sai khác với contract đã công bố, ghi rõ nguyên nhân và thêm regression case.

Phase này chưa làm Python simulator, state aggregation, collision evaluation từ CAN, radar watchdog 500 ms, integration tests, GitHub Actions hoặc Jenkins. Coverage và sanitizer có thể bổ sung sau, không là điều kiện hoàn thành Phase 4.

## 3. CMake và dependency

- [ ] Thêm `include(CTest)` ở top level; dùng option chuẩn `BUILD_TESTING` do CTest cung cấp.
- [ ] Trong `if(BUILD_TESTING)`: dùng `find_package(GTest CONFIG REQUIRED)` và `include(GoogleTest)`.
- [ ] Tạo target `test_collision_warning`, link PRIVATE `adas_core` và `GTest::gtest_main`.
- [ ] Tạo target `test_can_decoder`, link PRIVATE `adas_decoder` và `GTest::gtest_main`.
- [ ] Dùng `gtest_discover_tests(...)` cho từng target; không đăng ký thêm cùng test bằng `add_test` gây chạy trùng.
- [ ] Áp dụng C++17, extensions OFF và compiler warnings tương tự target hiện tại cho hai target test. Nếu dùng vòng `adas_targets`, thêm targets trước vòng áp dụng options.
- [ ] Hai test executable không link `adas_can` hoặc chứa `src/main.cpp`; dùng main của GoogleTest.
- [ ] `BUILD_TESTING=OFF` vẫn configure/build application khi không cài GoogleTest.

Chọn dependency từ hệ thống cho Phase 4, phù hợp setup Ubuntu sẵn có; không thêm FetchContent hoặc tải dependency khi configure. Nếu thiếu GTest trên Ubuntu VM, chỉ cài gói cần thiết:

```bash
sudo apt-get update
sudo apt-get install libgtest-dev
```

Các lệnh build/test sau đó chạy bằng user thường. Nếu CMake không tìm thấy package đã cài ở prefix riêng, chỉ định `CMAKE_PREFIX_PATH` hoặc `GTest_DIR`; không hardcode đường dẫn của máy hiện tại vào repo.

## 4. Ma trận collision core

Contract lấy từ `collision_warning.hpp`, README và code Phase 1: tất cả input phải finite; speed trong [0,300], distance không âm. Relative velocity dương là closing speed và được dùng trực tiếp, không trừ vehicle speed. Core không áp range [-100,100] của DBC lên relative velocity.

### 4.1. Kết quả và ranh giới TTC

| Input `(speed, distance, relative)` | Expected |
| --- | --- |
| `(50,100,0)` | NONE |
| `(80,20,7)` | WARNING |
| `(80,10,10)` | CRITICAL |
| `(80,20,10)` — TTC đúng 2 | CRITICAL |
| `(80,40,10)` — TTC đúng 4 | WARNING |
| `(80,19.99,10)` / `(80,20.01,10)` | CRITICAL / WARNING |
| `(80,39.99,10)` / `(80,40.01,10)` | WARNING / NONE |
| `(80,20,-7)` | NONE |
| `(80,0,10)`, `(80,0,0)`, `(80,0,-7)` | Đều CRITICAL |
| `(0,20,7)`, `(300,20,7)` | Đều WARNING; hai biên speed hợp lệ |
| `(80,20,101)` | CRITICAL; không áp range decoder vào core |

Các case sát biên xác nhận so sánh TTC chưa làm tròn. Không cần dùng epsilon cực nhỏ khiến expected bị phụ thuộc biểu diễn float.

### 4.2. Invalid input

- [ ] Speed âm và lớn hơn 300: ném `std::invalid_argument`.
- [ ] Distance âm: ném `std::invalid_argument`.
- [ ] NaN, +infinity, -infinity ở **từng tham số**, các tham số còn lại hợp lệ: ném `std::invalid_argument`.
- [ ] Speed lỗi cùng distance=0 vẫn ném exception; validation phải xảy ra trước nhánh CRITICAL.
- [ ] Relative velocity NaN cùng distance=0 vẫn ném exception.

Dùng `<limits>` tạo nonfinite values, `EXPECT_THROW` kiểm tra đúng loại exception; không assert chuỗi exception message vì không thuộc API contract.

## 5. Ma trận CAN decoder

Tạo `CanFrame` trực tiếp trong test, không mở socket. Với result variant, dùng `ASSERT_TRUE(std::holds_alternative<T>(result))` trước khi `std::get<T>`; case lỗi phải kiểm tra đúng `DecodeError`, không chỉ kiểm tra có lỗi.

Expected physical values phải viết từ DBC/vectors độc lập; không gọi lại helper decode hoặc dùng production constants để tự tính expected. Dùng payload byte literal cho vectors chính. Có thể dùng helper tạo frame để giảm lặp; tránh xây encoder tổng quát trong test.

### 5.1. Vectors hợp lệ

Payload hex trong bảng là đúng 8 byte theo thứ tự truyền; chuyển thành `std::array<uint8_t,8>` trong test.

| API / ID | Payload | Expected |
| --- | --- | --- |
| Vehicle / 0x100 | `200383FF01000000` | speed=80, steering=-12.5, brake=true |
| Vehicle / 0x100 | `F4017D0000000000` | speed=50, steering=12.5, brake=false |
| Vehicle / 0x100 | `0000000000000000` | speed=0, steering=0, brake=false |
| Vehicle / 0x100 | `B80B201C01000000` | speed=300, steering=720, brake=true |
| Vehicle / 0x100 | `0000E0E300000000` | speed=0, steering=-720, brake=false |
| Vehicle / 0x100 | `0100FFFF00000000` | speed=0.1, steering=-0.1, brake=false |
| Radar / 0x200 | `C800BC0201000000` | distance=20, relative=7, valid=true |
| Radar / 0x200 | `6400E80301000000` | distance=10, relative=10, valid=true |
| Radar / 0x200 | `E803000001000000` | distance=100, relative=0, valid=true |
| Radar / 0x200 | `C80044FD01000000` | distance=20, relative=-7, valid=true |
| Radar / 0x200 | `8813102701000000` | distance=500, relative=100, valid=true |
| Radar / 0x200 | `0000F0D801000000` | distance=0, relative=-100, valid=true |
| Radar / 0x200 | `0100FFFF01000000` | distance=0.1, relative=-0.01, valid=true |
| Radar / 0x200 | `0000000000000000` | distance=0, relative=0, valid=false |
| Radar / 0x200 | `C800BC0200000000` | distance=20, relative=7, valid=false; vẫn decode dữ liệu |

Các vectors có hai byte khác nhau giúp bắt lỗi endianness; raw `FFFF` bắt lỗi signed conversion. Dùng `EXPECT_NEAR(value, expected, 1e-9)` cho physical doubles; bool và enum dùng `EXPECT_EQ`/`EXPECT_TRUE`/`EXPECT_FALSE`.

Tất cả offset trong DBC hiện bằng 0. Kiểm tra zero raw → zero physical tương ứng và scale hiện có; không tạo DBC với offset khác 0 hoặc tuyên bố đã test một decoder DBC tổng quát.

### 5.2. Flags và reserved bits

Cho **cả hai API**, dùng frame có số hợp lệ:

- [ ] Byte 4 lần lượt là `00`, `01`, `80`, `81`, `FE`, `FF`; expected flag tương ứng false, true, false, true, false, true.
- [ ] Byte 5–7 chứa dữ liệu khác 0, chẳng hạn `AA 55 FF`: physical signals và flag không đổi.

Nhóm này bắt lỗi ép toàn byte 4 thành bool và lỗi reject reserved bits.

### 5.3. Format, ID và DLC

Cho từng API, bắt đầu bằng frame hợp lệ rồi chỉ đổi một thuộc tính:

| Input | Expected |
| --- | --- |
| Standard ID lạ `0x123` | WrongId |
| Đưa ID radar vào vehicle API và ngược lại | WrongId |
| `extended=true`, numeric ID đúng | UnsupportedFormat |
| DLC từng giá trị 0..7, 9, 255 | WrongDlc |

DLC=8 được bao phủ bởi vectors thành công. DLC 9/255 được tạo trực tiếp qua `CanFrame`, không phụ thuộc kernel có cho gửi hay không. Không thêm RTR/error flags vào model: chúng được lọc ở receiver.

Ưu tiên lỗi hiện tại là format → ID → DLC → range. Các tests bắt buộc chỉ gây một lỗi mỗi lần để assert đúng contract; không cần khóa thứ tự ưu tiên nhiều lỗi đồng thời khi header chưa công bố điều đó.

### 5.4. Range: đúng biên và một raw step ngoài biên

Các biên hợp lệ đã có ở bảng trên. Bổ sung từng lỗi riêng, giữ các signal khác hợp lệ:

| Signal | Raw lỗi / byte little-endian | Expected |
| --- | --- | --- |
| Speed | 3001 / `B9 0B`; 65535 / `FF FF` | OutOfRange |
| Steering | 7201 / `21 1C`; -7201 / `DF E3` | OutOfRange |
| Steering signed extremes | 32767 / `FF 7F`; -32768 / `00 80` | OutOfRange |
| Distance | 5001 / `89 13`; 65535 / `FF FF` | OutOfRange |
| Relative velocity | 10001 / `11 27`; -10001 / `EF D8` | OutOfRange |
| Relative signed extremes | 32767 / `FF 7F`; -32768 / `00 80` | OutOfRange |

- [ ] Radar có `object_valid=false` nhưng distance sai vẫn OutOfRange.
- [ ] Radar có `object_valid=false` nhưng relative velocity sai vẫn OutOfRange.

Distance/speed trong frame là unsigned, không có raw âm; không dựng case “distance âm” giả cho decoder. Case distance âm thuộc collision API.

## 6. Thứ tự thực hiện

1. **Nối framework:** thêm CMake và một smoke case thật cho mỗi test file. Configure/build, dùng `ctest -N` xác nhận đã discover test và chạy CTest.
2. **Collision suite:** hoàn thành mục 4; ưu tiên thresholds và validation precedence. Chạy suite riêng khi sửa.
3. **Decoder suite:** chuyển vectors Phase 3 thành assertions, sau đó thêm boundaries, flags, format/ID/DLC và invalid object. Có thể dùng parameterized tests cho các nhóm cùng cấu trúc; tên case/SCOPED_TRACE phải giúp nhận ra input lỗi.
4. **Kiểm tra regression sensitivity:** chạy mutation thủ công có kiểm soát theo mục 7.
5. **Nghiệm thu:** build sạch Debug, chạy toàn bộ CTest; kiểm tra build khi testing OFF và CLI số; cập nhật README và review diff.

Mỗi bước phải build được trước khi chuyển tiếp. Chưa cần thêm framework mocking, fixture phức tạp hoặc helper dùng chung ở production.

## 7. Lệnh kiểm chứng và chứng minh test bắt lỗi

Các lệnh sau là hướng dẫn **sau khi implement**, chưa phải các tests đã tồn tại lúc viết plan:

```bash
cmake -S . -B build-phase4 -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON
cmake --build build-phase4 --parallel
ctest --test-dir build-phase4 -N
ctest --test-dir build-phase4 --output-on-failure
```

Danh sách test phải có cases của cả collision và decoder, tổng số lớn hơn 0. Khi cần chẩn đoán, chạy trực tiếp test executable với `--gtest_filter`, hoặc dùng `ctest -R` theo tên suite đã đặt.

Kiểm tra application build độc lập với tests bằng build directory khác:

```bash
cmake -S . -B build-phase4-no-tests -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=OFF -DCMAKE_DISABLE_FIND_PACKAGE_GTest=TRUE
cmake --build build-phase4-no-tests --parallel
./build-phase4-no-tests/adas_app 50 100 0
./build-phase4-no-tests/adas_app 80 20 7
./build-phase4-no-tests/adas_app 80 10 10
```

Expected CLI lần lượt NONE, WARNING, CRITICAL. Biến disable-find chỉ dùng để kiểm tra nhánh không phụ thuộc GTest; nếu CMake báo biến không được dùng vì không gọi find_package ở nhánh OFF thì không phải lỗi ứng dụng.

**Mutation check bắt buộc, chỉ trên bản sao làm việc tạm trong `/tmp`:**

- Đổi ngưỡng TTC `<= 2.0` thành `< 2.0`: case TTC đúng 2 phải fail.
- Khôi phục rồi đổi phép lấy flag byte 4 thành kiểm tra cả byte khác 0: case `80` hoặc `FE` phải fail ở decoder tương ứng.
- Mỗi mutation build thành công rồi CTest phải trả nonzero vì assertion fail; build fail không chứng minh unit tests bắt được regression.
- Xóa/khôi phục mutation trong bản sao, chạy suite gốc xanh. Không sửa/xóa thay đổi người dùng, không commit mutation. Không cần thêm mutation framework hay script vào repository.

## 8. Exit criteria và bàn giao

- [ ] Clean configure/build với BUILD_TESTING=ON thành công, không thêm compiler warnings.
- [ ] CTest discover cả hai nhóm, tổng tests > 0 và tất cả pass.
- [ ] Hoàn thành ma trận core và decoder ở mục 4–5; assertions kiểm tra giá trị hoặc loại lỗi cụ thể.
- [ ] Test executables không cần vcan/root/CAN traffic; không mở socket hoặc khởi chạy application.
- [ ] BUILD_TESTING=OFF build được khi GTest bị disable; CLI số giữ đúng ba scenarios gốc.
- [ ] Hai mutation checks fail đúng do assertion; source bàn giao sạch và suite gốc pass lại.
- [ ] README có dependency, câu lệnh CTest, cách đọc failure và giới hạn Phase 4.
- [ ] `git diff --check` sạch; review `git diff` và không đưa binary/build log vào source.
- [ ] Ghi lại số test và kết quả thực tế, không đánh dấu các kiểm tra chưa chạy.

Plan này nằm trong `docs/`, hiện bị `/docs/` trong `.gitignore` loại trừ. Giữ nguyên chính sách ignore; nếu cần version tài liệu, chọn xử lý riêng file này trong phiên được yêu cầu. Không tự commit/push.

Sau Phase 4, bắt đầu Phase 5 với simulator encode từ `dbc/vehicle.dbc`. Trước khi nghiệm thu end-to-end ở Phase 5–6, cần chốt và triển khai ghép vehicle/radar state, điều kiện đủ input, invalid-object handling và radar watchdog 500 ms. Unit tests Phase 4 chỉ xác nhận core/decoder độc lập, chưa xác nhận những hành vi đó.
