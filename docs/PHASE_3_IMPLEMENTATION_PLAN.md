# Phase 3 — DBC và CAN Decoder

## 1. Mục tiêu và điểm bắt đầu

Phase 2 đã hoàn thành: `adas_app --can <interface>` nhận và in raw Classical CAN frames qua Linux SocketCAN. Phase 3 bổ sung đường đi:

```text
cansend → vcan0 → CanReceiver → CanFrame → CAN decoder → physical signals
```

Kết quả cần demo: gửi message `VehicleState` (`0x100`) và `RadarObject` (`0x200`), ứng dụng in đúng giá trị cùng đơn vị; frame sai được xử lý rõ ràng và không làm vòng nhận dừng.

Căn cứ: [roadmap tổng thể](ADAS_CI_CT_Implementation_Plan.md), [project specification](adas_software_integration_ci_ct_project_spec.md), [plan Phase 2](PHASE_2_IMPLEMENTATION_PLAN.md), cùng code hiện tại. Các layout, range và API bên dưới là quyết định thiết kế đề xuất cho Phase 3; spec gốc chỉ chốt tên message, ID và sáu signal.

Trước khi triển khai, đọc hướng dẫn `AGENTS.md` nếu có, kiểm tra branch và `git status`, đối chiếu lại API thực tế. Không ghi đè thay đổi đang có. Có thể dùng branch `feature/phase-3-can-decoder` theo workflow của repo.

## 2. Phạm vi và đầu ra

- [ ] Tạo `dbc/vehicle.dbc`, mô tả đầy đủ hai message và sáu signal.
- [ ] Tạo decoder C++17 độc lập với socket, interface và I/O.
- [ ] Thêm chế độ `adas_app --decode <interface>` để log physical signals.
- [ ] Giữ chế độ `--can` làm công cụ xem raw frames và giữ CLI ba số của Phase 1.
- [ ] Có bảng test vectors hex, expected output và cách kiểm tra thủ công.
- [ ] Cập nhật README khi triển khai xong, ghi trạng thái và cách chạy Phase 3.

GoogleTest/CTest thuộc Phase 4; Python CAN simulator thuộc Phase 5. Việc ghép vehicle/radar thành trạng thái chung để gọi collision core và watchdog radar 500 ms cần được triển khai trước khi nghiệm thu scenarios ở Phase 5–6. Phase 3 chỉ decode/log, chưa sinh `WarningLevel` từ CAN, chưa quản lý freshness hoặc timeout của radar. CI/Jenkins chưa thuộc phạm vi này.

## 3. Chốt CAN/DBC contract trước khi viết decoder

### 3.1. Message và layout

Cả hai message là **standard 11-bit Classical CAN**, DLC chính xác **8 byte**. Trong DBC, `BO_` dùng ID decimal: `256` và `512`. Khai báo node gửi `VehicleECU`, `RadarECU` và node nhận `ADAS`.

Tất cả signal dùng Intel little-endian, ký hiệu DBC `@1`; bit 0 là bit thấp nhất của byte 0. Hai signal 16 bit chiếm byte 0–1 và byte 2–3; cờ 1 bit nằm ở bit 0 của byte 4. Các bit còn lại là reserved: sender ghi 0, decoder bỏ qua để tránh reject do phần không mang signal.

| Message | Signal | Start bit | Length | DBC type | Factor | Offset | Physical range | Unit |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- |
| VehicleState / 0x100 | VehicleSpeed | 0 | 16 | `@1+` unsigned | 0.1 | 0 | 0 đến 300 | km/h |
| VehicleState / 0x100 | SteeringAngle | 16 | 16 | `@1-` signed | 0.1 | 0 | -720 đến 720 | deg |
| VehicleState / 0x100 | BrakeStatus | 32 | 1 | `@1+` unsigned | 1 | 0 | 0 hoặc 1 | rỗng |
| RadarObject / 0x200 | ObjectDistance | 0 | 16 | `@1+` unsigned | 0.1 | 0 | 0 đến 500 | m |
| RadarObject / 0x200 | RelativeVelocity | 16 | 16 | `@1-` signed | 0.01 | 0 | -100 đến 100 | m/s |
| RadarObject / 0x200 | ObjectValid | 32 | 1 | `@1+` unsigned | 1 | 0 | 0 hoặc 1 | rỗng |

Ví dụ dòng signal: `SG_ VehicleSpeed : 0|16@1+ (0.1,0) [0|300] "km/h" ADAS`.

Thêm mô tả bằng `CM_` và value descriptions bằng `VAL_` cho cờ: BrakeStatus `0 = Released`, `1 = Pressed`; ObjectValid `0 = Invalid`, `1 = Valid`. Ghi rõ quy ước vận tốc tương đối trong DBC: **dương là đang tiến gần vật cản**, âm là đang ra xa, phù hợp collision core Phase 1; không trừ thêm vehicle speed.

### 3.2. Quy tắc giải mã

1. Kiểm tra standard frame, ID đúng message và DLC bằng 8 trước khi truy cập payload.
2. Ghép little-endian bằng phép dịch trên số unsigned: `u16 = byte0 | (byte1 << 8)` với kiểu trung gian đủ rộng.
3. Với signal signed 16 bit, chuyển two's complement sang số có dấu trước khi scale. Cách rõ ràng trong C++17: nếu raw >= 32768 thì lấy `int32(raw) - 65536`; tránh shift số âm hoặc ép unsigned ngoài miền trực tiếp sang `int16_t`.
4. Tính `physical = raw * factor + offset` bằng `double`.
5. Lấy cờ bằng mask bit 0 của byte 4; không ép toàn byte thành bool vì có reserved bits.
6. Validate range theo raw tương ứng để ranh giới chính xác: speed 0..3000, steering -7200..7200, distance 0..5000, relative velocity -10000..10000.
7. Không clamp giá trị lỗi về biên, không dùng giá trị mặc định thay cho message lỗi.

DBC là nguồn định nghĩa format. C++ Phase 3 dùng decoder viết tay cho đúng hai layout này, không cần runtime parser hoặc code generator. Mọi thay đổi layout phải cập nhật DBC, constants/decoder và test vectors cùng nhau. Phase 5 dùng cùng `vehicle.dbc` để encode, ưu tiên thư viện đọc DBC thay vì định nghĩa format thứ hai.

## 4. API và phân lớp

### 4.1. Tái sử dụng CanFrame

`CanFrame` hiện nằm trong `include/can_receiver.hpp` và chỉ dùng kiểu C++ chuẩn. Tách nguyên struct sang `include/can_frame.hpp`; để `can_receiver.hpp` include header mới. Không đổi tên, kiểu hoặc ý nghĩa các trường `id`, `dlc`, `data`, `extended`.

Decoder include `can_frame.hpp`, không include Linux headers và không phụ thuộc `CanReceiver`. Receiver vẫn chỉ chịu trách nhiệm transport, lọc RTR/error frame và metadata không hợp lệ như Phase 2.

### 4.2. Model dữ liệu và kết quả

Trong `include/can_decoder.hpp`, định nghĩa API dự kiến:

```cpp
struct VehicleState {
    double speed_kmh;
    double steering_angle_deg;
    bool brake_pressed;
};

struct RadarObject {
    double distance_m;
    double relative_velocity_mps;
    bool object_valid;
};

enum class DecodeError {
    WrongId,
    UnsupportedFormat,
    WrongDlc,
    OutOfRange
};

using VehicleDecodeResult = std::variant<VehicleState, DecodeError>;
using RadarDecodeResult = std::variant<RadarObject, DecodeError>;

VehicleDecodeResult decodeVehicleState(const CanFrame& frame);
RadarDecodeResult decodeRadarObject(const CanFrame& frame);
```

Header cần include `<variant>`. Có thể bổ sung tên signal lỗi vào result nếu cần diagnostic, nhưng không thêm exception cho dữ liệu CAN sai thường gặp. Decoder không log, không lưu frame cũ, không mở socket và không gọi collision core.

`ObjectValid=0` là message decode thành công: trả `RadarObject` có `object_valid=false`, để consumer biết vật thể không dùng được. Vẫn validate range hai trường số dù cờ bằng 0; contract này yêu cầu sender gửi giá trị số trong miền, ví dụ 0/0 khi không có object. Không đồng nhất invalid object với input out-of-range hoặc mất message.

### 4.3. CMake

- [ ] Tạo library `adas_decoder` từ `src/can_decoder.cpp`, public include `include/`, C++17, extensions OFF.
- [ ] Tạo target decoder trên mọi nền tảng; áp dụng cùng `/W4` hoặc `-Wall -Wextra -Wpedantic` như target hiện có.
- [ ] Link `adas_app` với `adas_decoder`; giữ `adas_can` và SocketCAN compile definition chỉ trên Linux.
- [ ] `adas_core` tiếp tục chỉ chứa collision logic, không link decoder hoặc receiver.
- [ ] CLI `--decode` trên nền tảng khác báo unsupported, exit 1; sai cú pháp vẫn exit 2.

## 5. Tích hợp CLI và output

Bổ sung usage `adas_app --decode <interface>`. Tái sử dụng vòng nhận, signal handling và timeout poll hữu hạn của Phase 2; tránh copy hai vòng socket xử lý khác nhau chỉ để đổi formatter.

Dispatch theo ID và format, không dùng riêng numeric ID để nhận nhầm extended `0x00000100` thành standard `0x100`.

Contract output đề xuất, một dòng cho mỗi message decode thành công, flush ngay:

```text
VehicleState speed_kmh=80.00 steering_angle_deg=-12.50 brake_pressed=1
RadarObject distance_m=20.00 relative_velocity_mps=7.00 object_valid=1
RadarObject distance_m=0.00 relative_velocity_mps=0.00 object_valid=0
```

Dùng fixed hai chữ số thập phân và dấu chấm, locale ổn định. Cờ hiển thị `0/1`. Không làm tròn trước bước range validation. Chế độ `--decode` chỉ in decoded messages trên stdout; raw output tiếp tục dùng `--can`.

| Tình huống | Hành vi trong `--decode` |
| --- | --- |
| Standard 0x100/0x200, DLC 8, signals hợp lệ | In decoded message lên stdout |
| Standard ID khác | Không decode; diagnostic stderr `DECODE_IGNORED reason=UNKNOWN_ID id=...` |
| Extended frame, kể cả numeric ID 0x100/0x200 | Diagnostic `DECODE_IGNORED reason=UNSUPPORTED_FORMAT id=...` |
| Known standard ID, DLC khác 8 | `DECODE_ERROR reason=WRONG_DLC id=...` trên stderr; không in decoded message |
| Signal ngoài miền | `INVALID_INPUT reason=OUT_OF_RANGE id=...` trên stderr; không in decoded message |
| ObjectValid bằng 0 và số trong miền | In radar với cờ 0; không tạo cảnh báo va chạm |
| Frame bị receiver bỏ qua | Giữ hành vi Phase 2; không gọi decoder |

Frame lỗi không kết thúc process: receiver tiếp tục xử lý frame sau. Đảm bảo các nhánh lỗi `WrongId` của API và kiểm tra định dạng cũng được kiểm tra trực tiếp, dù CLI đã dispatch trước.

Exit codes tiếp tục: 0 khi SIGINT/SIGTERM dừng bình thường; 1 khi lỗi socket/interface hoặc unsupported platform; 2 khi sai usage/input CLI số. `INVALID_INPUT` do một frame CAN lỗi là diagnostic của frame, không tự đổi exit code phiên nhận.

## 6. Thứ tự triển khai

1. **Chốt DBC:** viết `vehicle.dbc`, kiểm tra ID, layout, signedness, units và range bằng bảng mục 3. Ghi comments cho reserved bits và sign convention.
2. **Tách model:** tạo `can_frame.hpp`, cập nhật include của receiver; build lại để xác nhận raw CLI không bị ảnh hưởng.
3. **Viết decoder:** thêm structs, result types, hai hàm decode và target `adas_decoder`; kiểm tra validation trước khi đọc byte, rồi signedness/scale/range.
4. **Nối CLI:** thêm `--decode`, formatter và diagnostics theo mục 5; giữ socket lifecycle, signal và raw formatter hiện có.
5. **Xác minh:** chạy các vectors ở mục 7 và regression mục 8; dùng harness tạm gọi API nếu cần kiểm tra phần không gửi được qua SocketCAN.
6. **Bàn giao:** cập nhật README với layout tóm tắt, hai terminal demo, outputs, invalid-object behavior và giới hạn Phase 3; review diff, ghi kết quả thực tế.

Nếu được yêu cầu commit trong phiên triển khai, chia theo mốc: DBC contract → shared frame + decoder/CMake → CLI decode → tài liệu. Mỗi commit phải build được; không tự commit, merge hoặc push chỉ vì kế hoạch có liệt kê các mốc này.

## 7. Test vectors và cách kiểm tra

### 7.1. Build và khởi chạy

Các lệnh sau dành cho **sau khi triển khai**, chưa phải chức năng đã có trong repo tại lúc viết plan.

```bash
cmake -S . -B build-phase3 -DCMAKE_BUILD_TYPE=Debug
cmake --build build-phase3 --parallel
bash scripts/setup_vcan.sh
```

Terminal A:

```bash
./build-phase3/adas_app --decode vcan0
```

Terminal B dùng từng lệnh `cansend` trong bảng. Chờ receiver khởi động trước khi gửi; nếu dùng harness, cần xác nhận sẵn sàng thay vì suy từ một khoảng sleep cố định.

### 7.2. Vectors hợp lệ

Payload viết theo thứ tự byte truyền trên bus. Ví dụ speed 80: raw 800 = `0x0320` → `20 03`; steering -12.5: raw -125 = `0xFF83` → `83 FF`.

| Lệnh gửi | Expected physical signals |
| --- | --- |
| `cansend vcan0 100#200383FF01000000` | speed=80.00, steering=-12.50, brake=1 |
| `cansend vcan0 100#F4017D0000000000` | speed=50.00, steering=12.50, brake=0 |
| `cansend vcan0 100#0000000000000000` | speed=0.00, steering=0.00, brake=0 |
| `cansend vcan0 100#B80B201C01000000` | speed=300.00, steering=720.00, brake=1 |
| `cansend vcan0 100#0000E0E300000000` | speed=0.00, steering=-720.00, brake=0 |
| `cansend vcan0 200#C800BC0201000000` | distance=20.00, relative=7.00, valid=1 |
| `cansend vcan0 200#6400E80301000000` | distance=10.00, relative=10.00, valid=1 |
| `cansend vcan0 200#E803000001000000` | distance=100.00, relative=0.00, valid=1 |
| `cansend vcan0 200#C80044FD01000000` | distance=20.00, relative=-7.00, valid=1 |
| `cansend vcan0 200#8813102701000000` | distance=500.00, relative=100.00, valid=1 |
| `cansend vcan0 200#0000F0D801000000` | distance=0.00, relative=-100.00, valid=1 |
| `cansend vcan0 200#0000000000000000` | distance=0.00, relative=0.00, valid=0 |
| `cansend vcan0 100#200383FF81000000` | speed=80.00, steering=-12.50, brake=1; reserved bit không đổi cờ |

Các radar vectors 100/0, 20/7 và 10/10 được tái sử dụng cho normal/warning/critical ở phase sau. Phase 3 chỉ assert decoded values, chưa assert `WarningLevel`.

### 7.3. Vectors lỗi và khả năng phục hồi

| Lệnh/kiểm tra | Expected |
| --- | --- |
| `cansend vcan0 123#0102030405060708` | UNKNOWN_ID, không có decoded stdout |
| `cansend vcan0 00000100#200383FF01000000` | UNSUPPORTED_FORMAT, không nhận nhầm standard ID |
| `cansend vcan0 100#2003` | WRONG_DLC, không đọc byte ngoài payload |
| `cansend vcan0 200#` | WRONG_DLC |
| `cansend vcan0 100#C20B000000000000` | Speed=301 ngoài miền → INVALID_INPUT |
| `cansend vcan0 100#0000211C00000000` | Steering=720.1 ngoài miền → INVALID_INPUT |
| `cansend vcan0 200#8913000001000000` | Distance=500.1 ngoài miền → INVALID_INPUT |
| `cansend vcan0 200#0000112701000000` | Relative=100.01 ngoài miền → INVALID_INPUT |
| `cansend vcan0 200#0000EFD801000000` | Relative=-100.01 ngoài miền → INVALID_INPUT |
| `cansend vcan0 200#8913000000000000` | valid=0 nhưng distance ngoài miền → INVALID_INPUT |
| Gửi frame hợp lệ ngay sau mỗi frame lỗi | Có decoded output đúng, process vẫn chạy |

Kiểm tra trực tiếp API bằng harness tạm: wrong ID cho từng hàm, `extended=true`, DLC 0..7 và >8, mọi range boundary và ngay ngoài biên, giá trị signed -1, raw signed cực trị. Kernel có thể chặn DLC >8 nên không tuyên bố case này đã được kiểm tra bằng `cansend`. Header `CanFrame` cho phép tự tạo input để kiểm tra mà không cần socket/root.

Không bổ sung framework test trong Phase 3; giữ vectors làm dữ liệu bàn giao để Phase 4 chuyển thành GoogleTest. Khi so sánh giá trị `double` trong harness, dùng tolerance nhỏ phù hợp, ví dụ `1e-9`; stdout so sánh theo contract fixed hai chữ số.

## 8. Regression và tiêu chí hoàn thành

- [ ] Build sạch trên Linux, không thêm compiler warnings.
- [ ] DBC có đủ sáu signal, không overlap, nằm trong 8 byte; DBC và decoder khớp toàn bộ vectors.
- [ ] Hai API decoder chạy độc lập socket và trả lỗi có phân loại, không trả dữ liệu mặc định khi lỗi.
- [ ] `--decode` pass vectors hợp lệ, lỗi và recovery; không nhầm extended/standard ID.
- [ ] `--can` vẫn in raw format Phase 2 với frame standard/extended, DLC 0/1/8; RTR vẫn bị bỏ qua.
- [ ] CLI số giữ đúng `50 100 0 → NONE`, `80 20 7 → WARNING`, `80 10 10 → CRITICAL`, `80 20 10 → CRITICAL` (TTC=2), `80 40 10 → WARNING` (TTC=4).
- [ ] CLI số với `301 10 1`, `80 -1 1`, `nan 10 1` vẫn báo INVALID_INPUT và exit 2.
- [ ] `--decode` thiếu/thừa interface → usage, exit 2; interface không tồn tại → diagnostic, exit 1.
- [ ] Ctrl+C và SIGTERM khi idle/đang nhận dừng sạch, exit 0; redirected stdout được flush ngay.
- [ ] README mô tả được cách gửi/nhận cả hai message và phân biệt invalid object với invalid signal.
- [ ] Review diff, chạy `git diff --check`, không đưa build outputs hoặc log vào source changes.

Nếu môi trường thiếu `vcan`/quyền setup, vẫn hoàn thành build và API verification không cần socket; ghi rõ CAN demo chưa được xác minh và cung cấp lệnh chạy trên Ubuntu VM. Không đánh dấu các checkbox CAN pass khi chưa thực sự chạy.

**Exit criteria:** từ bytes nhận qua CAN, decoder tạo được vehicle/radar structs đúng đơn vị, signedness và range; dữ liệu sai được phân loại; có đầy đủ vectors để bắt đầu Phase 4.

## 9. Bàn giao cho các phase tiếp theo

- **Phase 4:** GoogleTest/CTest cho collision core và decoder; tái sử dụng vectors, kiểm tra boundaries, flags, signedness và lỗi, không cần vcan/root.
- **Phase 5:** simulator encode theo `dbc/vehicle.dbc`; nối decoded data vào collision core trước khi demo risk state. Chốt lúc nào đủ vehicle/radar input, cách vô hiệu hóa object cũ, và watchdog radar để đáp ứng Phase 6.
- **Phase 6:** assertions end-to-end cho NONE/WARNING/CRITICAL, INVALID_INPUT và RADAR_TIMEOUT; quản lý timeout, cleanup process và log output.

Lưu ý repo hiện có `/docs/` trong `.gitignore`; file kế hoạch này được lưu local đúng thư mục yêu cầu. Nếu sau đó cần đưa tài liệu vào Git, xử lý ignore hoặc force-add đúng file được chọn trong phạm vi phiên đó; không tự thay chính sách ignore toàn bộ docs.
