#include "can_decoder.hpp"

#include <cstddef>
#include <cstdint>

namespace {
constexpr std::uint32_t kVehicleStateId = 0x100;
constexpr std::uint32_t kRadarObjectId = 0x200;
constexpr std::uint8_t kExpectedDlc = 8;

std::uint16_t readU16(const CanFrame& frame, std::size_t offset) {
    return static_cast<std::uint16_t>(
        static_cast<std::uint32_t>(frame.data[offset]) |
        (static_cast<std::uint32_t>(frame.data[offset + 1]) << 8));
}

std::int32_t readI16(const CanFrame& frame, std::size_t offset) {
    const std::uint32_t raw = readU16(frame, offset);
    return raw >= 32768U ? static_cast<std::int32_t>(raw) - 65536
                         : static_cast<std::int32_t>(raw);
}
}  // namespace

VehicleDecodeResult decodeVehicleState(const CanFrame& frame) {
    if (frame.extended) {
        return DecodeError::UnsupportedFormat;
    }
    if (frame.id != kVehicleStateId) {
        return DecodeError::WrongId;
    }
    if (frame.dlc != kExpectedDlc) {
        return DecodeError::WrongDlc;
    }

    const std::uint16_t speed_raw = readU16(frame, 0);
    const std::int32_t steering_raw = readI16(frame, 2);
    if (speed_raw > 3000U || steering_raw < -7200 || steering_raw > 7200) {
        return DecodeError::OutOfRange;
    }

    return VehicleState{static_cast<double>(speed_raw) * 0.1,
                        static_cast<double>(steering_raw) * 0.1,
                        (frame.data[4] & 0x01U) != 0};
}

RadarDecodeResult decodeRadarObject(const CanFrame& frame) {
    if (frame.extended) {
        return DecodeError::UnsupportedFormat;
    }
    if (frame.id != kRadarObjectId) {
        return DecodeError::WrongId;
    }
    if (frame.dlc != kExpectedDlc) {
        return DecodeError::WrongDlc;
    }

    const std::uint16_t distance_raw = readU16(frame, 0);
    const std::int32_t velocity_raw = readI16(frame, 2);
    if (distance_raw > 5000U || velocity_raw < -10000 || velocity_raw > 10000) {
        return DecodeError::OutOfRange;
    }

    return RadarObject{static_cast<double>(distance_raw) * 0.1,
                       static_cast<double>(velocity_raw) * 0.01,
                       (frame.data[4] & 0x01U) != 0};
}
