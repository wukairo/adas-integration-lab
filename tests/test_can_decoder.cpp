#include "can_decoder.hpp"

#include <gtest/gtest.h>

#include <array>
#include <cstdint>
#include <variant>

namespace {
CanFrame frame(std::uint32_t id, std::array<std::uint8_t, 8> data) {
    return CanFrame{id, 8, data, false};
}

template <typename Result>
void expectError(const Result& result, DecodeError expected) {
    ASSERT_TRUE(std::holds_alternative<DecodeError>(result));
    EXPECT_EQ(std::get<DecodeError>(result), expected);
}

const CanFrame kVehicle = frame(0x100, {0x20, 0x03, 0x83, 0xFF, 0x01, 0, 0, 0});
const CanFrame kRadar = frame(0x200, {0xC8, 0, 0xBC, 0x02, 0x01, 0, 0, 0});
}  // namespace

TEST(CanDecoder, VehicleVectorsDecodePhysicalSignals) {
    struct Case {
        std::array<std::uint8_t, 8> payload;
        double speed;
        double steering;
        bool brake;
    };
    const Case cases[] = {
        {{0x20, 0x03, 0x83, 0xFF, 0x01, 0, 0, 0}, 80, -12.5, true},
        {{0xF4, 0x01, 0x7D, 0, 0, 0, 0, 0}, 50, 12.5, false},
        {{0, 0, 0, 0, 0, 0, 0, 0}, 0, 0, false},
        {{0xB8, 0x0B, 0x20, 0x1C, 0x01, 0, 0, 0}, 300, 720, true},
        {{0, 0, 0xE0, 0xE3, 0, 0, 0, 0}, 0, -720, false},
        {{0x01, 0, 0xFF, 0xFF, 0, 0, 0, 0}, 0.1, -0.1, false},
    };
    for (const auto& test_case : cases) {
        SCOPED_TRACE(::testing::PrintToString(test_case.payload));
        const auto result = decodeVehicleState(frame(0x100, test_case.payload));
        ASSERT_TRUE(std::holds_alternative<VehicleState>(result));
        const auto& state = std::get<VehicleState>(result);
        EXPECT_NEAR(state.speed_kmh, test_case.speed, 1e-9);
        EXPECT_NEAR(state.steering_angle_deg, test_case.steering, 1e-9);
        EXPECT_EQ(state.brake_pressed, test_case.brake);
    }
}

TEST(CanDecoder, RadarVectorsDecodePhysicalSignals) {
    struct Case {
        std::array<std::uint8_t, 8> payload;
        double distance;
        double relative_velocity;
        bool valid;
    };
    const Case cases[] = {
        {{0xC8, 0, 0xBC, 0x02, 0x01, 0, 0, 0}, 20, 7, true},
        {{0x64, 0, 0xE8, 0x03, 0x01, 0, 0, 0}, 10, 10, true},
        {{0xE8, 0x03, 0, 0, 0x01, 0, 0, 0}, 100, 0, true},
        {{0xC8, 0, 0x44, 0xFD, 0x01, 0, 0, 0}, 20, -7, true},
        {{0x88, 0x13, 0x10, 0x27, 0x01, 0, 0, 0}, 500, 100, true},
        {{0, 0, 0xF0, 0xD8, 0x01, 0, 0, 0}, 0, -100, true},
        {{0x01, 0, 0xFF, 0xFF, 0x01, 0, 0, 0}, 0.1, -0.01, true},
        {{0, 0, 0, 0, 0, 0, 0, 0}, 0, 0, false},
        {{0xC8, 0, 0xBC, 0x02, 0, 0, 0, 0}, 20, 7, false},
    };
    for (const auto& test_case : cases) {
        SCOPED_TRACE(::testing::PrintToString(test_case.payload));
        const auto result = decodeRadarObject(frame(0x200, test_case.payload));
        ASSERT_TRUE(std::holds_alternative<RadarObject>(result));
        const auto& object = std::get<RadarObject>(result);
        EXPECT_NEAR(object.distance_m, test_case.distance, 1e-9);
        EXPECT_NEAR(object.relative_velocity_mps, test_case.relative_velocity, 1e-9);
        EXPECT_EQ(object.object_valid, test_case.valid);
    }
}

TEST(CanDecoder, FlagsUseOnlyBitZeroAndReservedBytesAreIgnored) {
    const std::uint8_t flags[] = {0x00, 0x01, 0x80, 0x81, 0xFE, 0xFF};
    for (std::uint8_t flag : flags) {
        SCOPED_TRACE(static_cast<unsigned>(flag));
        auto vehicle = kVehicle;
        auto radar = kRadar;
        vehicle.data[4] = radar.data[4] = flag;
        vehicle.data[5] = radar.data[5] = 0xAA;
        vehicle.data[6] = radar.data[6] = 0x55;
        vehicle.data[7] = radar.data[7] = 0xFF;

        const auto vehicle_result = decodeVehicleState(vehicle);
        ASSERT_TRUE(std::holds_alternative<VehicleState>(vehicle_result));
        const auto& state = std::get<VehicleState>(vehicle_result);
        EXPECT_NEAR(state.speed_kmh, 80, 1e-9);
        EXPECT_NEAR(state.steering_angle_deg, -12.5, 1e-9);
        EXPECT_EQ(state.brake_pressed, (flag & 1U) != 0);

        const auto radar_result = decodeRadarObject(radar);
        ASSERT_TRUE(std::holds_alternative<RadarObject>(radar_result));
        const auto& object = std::get<RadarObject>(radar_result);
        EXPECT_NEAR(object.distance_m, 20, 1e-9);
        EXPECT_NEAR(object.relative_velocity_mps, 7, 1e-9);
        EXPECT_EQ(object.object_valid, (flag & 1U) != 0);
    }
}

TEST(CanDecoder, VehicleRejectsWrongIdFormatAndDlc) {
    auto input = kVehicle;
    input.id = 0x123;
    expectError(decodeVehicleState(input), DecodeError::WrongId);
    input = kVehicle;
    input.id = 0x200;
    expectError(decodeVehicleState(input), DecodeError::WrongId);
    input = kVehicle;
    input.extended = true;
    expectError(decodeVehicleState(input), DecodeError::UnsupportedFormat);
    for (int dlc : {0, 1, 2, 3, 4, 5, 6, 7, 9, 255}) {
        SCOPED_TRACE(dlc);
        input = kVehicle;
        input.dlc = static_cast<std::uint8_t>(dlc);
        expectError(decodeVehicleState(input), DecodeError::WrongDlc);
    }
}

TEST(CanDecoder, RadarRejectsWrongIdFormatAndDlc) {
    auto input = kRadar;
    input.id = 0x123;
    expectError(decodeRadarObject(input), DecodeError::WrongId);
    input = kRadar;
    input.id = 0x100;
    expectError(decodeRadarObject(input), DecodeError::WrongId);
    input = kRadar;
    input.extended = true;
    expectError(decodeRadarObject(input), DecodeError::UnsupportedFormat);
    for (int dlc : {0, 1, 2, 3, 4, 5, 6, 7, 9, 255}) {
        SCOPED_TRACE(dlc);
        input = kRadar;
        input.dlc = static_cast<std::uint8_t>(dlc);
        expectError(decodeRadarObject(input), DecodeError::WrongDlc);
    }
}

TEST(CanDecoder, VehicleRejectsEachOutOfRangeSignal) {
    const std::array<std::uint8_t, 8> payloads[] = {
        {0xB9, 0x0B, 0, 0, 0, 0, 0, 0},       // speed 3001
        {0xFF, 0xFF, 0, 0, 0, 0, 0, 0},       // speed 65535
        {0, 0, 0x21, 0x1C, 0, 0, 0, 0},       // steering 7201
        {0, 0, 0xDF, 0xE3, 0, 0, 0, 0},       // steering -7201
        {0, 0, 0xFF, 0x7F, 0, 0, 0, 0},       // steering 32767
        {0, 0, 0, 0x80, 0, 0, 0, 0},          // steering -32768
    };
    for (const auto& payload : payloads) {
        SCOPED_TRACE(::testing::PrintToString(payload));
        expectError(decodeVehicleState(frame(0x100, payload)), DecodeError::OutOfRange);
    }
}

TEST(CanDecoder, RadarRejectsEachOutOfRangeSignalEvenWhenInvalid) {
    const std::array<std::uint8_t, 8> payloads[] = {
        {0x89, 0x13, 0, 0, 0x01, 0, 0, 0},  // distance 5001
        {0xFF, 0xFF, 0, 0, 0x01, 0, 0, 0},  // distance 65535
        {0, 0, 0x11, 0x27, 0x01, 0, 0, 0},  // relative 10001
        {0, 0, 0xEF, 0xD8, 0x01, 0, 0, 0},  // relative -10001
        {0, 0, 0xFF, 0x7F, 0x01, 0, 0, 0},  // relative 32767
        {0, 0, 0, 0x80, 0x01, 0, 0, 0},     // relative -32768
        {0x89, 0x13, 0, 0, 0, 0, 0, 0},     // invalid object, distance 5001
        {0, 0, 0x11, 0x27, 0, 0, 0, 0},     // invalid object, relative 10001
    };
    for (const auto& payload : payloads) {
        SCOPED_TRACE(::testing::PrintToString(payload));
        expectError(decodeRadarObject(frame(0x200, payload)), DecodeError::OutOfRange);
    }
}
