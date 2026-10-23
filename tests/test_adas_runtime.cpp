#include "adas_runtime.hpp"

#include <gtest/gtest.h>

#include <array>
#include <chrono>

namespace {
using Clock = AdasRuntime::Clock;
const Clock::time_point kStart{};

CanFrame vehicle(std::uint16_t speed_raw = 800) {
    CanFrame frame{};
    frame.id = 0x100;
    frame.dlc = 8;
    frame.data = {static_cast<std::uint8_t>(speed_raw & 0xff),
                  static_cast<std::uint8_t>(speed_raw >> 8), 0, 0, 0, 0, 0, 0};
    return frame;
}

CanFrame radar(std::uint16_t distance_raw = 200, std::int16_t velocity_raw = 700,
               bool valid = true) {
    CanFrame frame{};
    frame.id = 0x200;
    frame.dlc = 8;
    const auto bits = static_cast<std::uint16_t>(velocity_raw);
    frame.data = {static_cast<std::uint8_t>(distance_raw & 0xff),
                  static_cast<std::uint8_t>(distance_raw >> 8),
                  static_cast<std::uint8_t>(bits & 0xff),
                  static_cast<std::uint8_t>(bits >> 8),
                  static_cast<std::uint8_t>(valid ? 1 : 0), 0, 0, 0};
    return frame;
}

std::string lastStatus(const AdasRuntime::Update& update) {
    return update.events.empty() ? "" : update.events.back().status;
}
}  // namespace

TEST(AdasRuntime, AggregatesFramesInEitherOrderAndComputesRisk) {
    AdasRuntime runtime(kStart);
    auto update = runtime.onFrame(radar(), kStart + std::chrono::milliseconds(10));
    EXPECT_EQ(lastStatus(update), "WAITING_FOR_INPUT");
    update = runtime.onFrame(vehicle(), kStart + std::chrono::milliseconds(20));
    ASSERT_EQ(update.events.size(), 1U);
    EXPECT_EQ(update.events[0].status, "OK");
    ASSERT_TRUE(update.events[0].warning_level);
    EXPECT_EQ(*update.events[0].warning_level, WarningLevel::WARNING);
}

TEST(AdasRuntime, RadarTimeoutBoundaryAndNoTrafficStartup) {
    AdasRuntime runtime(kStart);
    EXPECT_EQ(lastStatus(runtime.tick(kStart)), "WAITING_FOR_INPUT");
    EXPECT_TRUE(runtime.tick(kStart + std::chrono::milliseconds(499)).events.empty());
    auto update = runtime.tick(kStart + std::chrono::milliseconds(500));
    ASSERT_EQ(update.events.size(), 1U);
    EXPECT_EQ(update.events[0].status, "RADAR_TIMEOUT");
    EXPECT_EQ(update.events[0].radar_age_ms.value(), 500.0);
    EXPECT_FALSE(update.events[0].last_radar_ms);
}

TEST(AdasRuntime, RadarObjectInvalidStillRefreshesAndMeansNoObject) {
    AdasRuntime runtime(kStart);
    runtime.onFrame(vehicle(), kStart);
    auto update = runtime.onFrame(radar(200, 700, false), kStart + std::chrono::milliseconds(10));
    ASSERT_EQ(update.events.size(), 1U);
    EXPECT_EQ(update.events[0].reason, "NO_OBJECT");
    EXPECT_EQ(*update.events[0].warning_level, WarningLevel::NONE);
    runtime.onFrame(vehicle(), kStart + std::chrono::milliseconds(450));
    EXPECT_TRUE(runtime.tick(kStart + std::chrono::milliseconds(509)).events.empty());
    EXPECT_EQ(lastStatus(runtime.tick(kStart + std::chrono::milliseconds(510))), "RADAR_TIMEOUT");
}

TEST(AdasRuntime, InvalidVehicleDoesNotReuseCachedValueAndCanRecover) {
    AdasRuntime runtime(kStart);
    runtime.onFrame(vehicle(), kStart);
    runtime.onFrame(radar(), kStart);
    auto invalid = vehicle(3010);
    auto update = runtime.onFrame(invalid, kStart + std::chrono::milliseconds(20));
    ASSERT_EQ(update.events.size(), 1U);
    EXPECT_EQ(update.events[0].status, "INVALID_INPUT");
    EXPECT_EQ(update.events[0].reason, "OUT_OF_RANGE");
    EXPECT_EQ(update.events[0].source.value(), "VehicleState");
    EXPECT_EQ(update.diagnostics[0].id, 0x100U);
    update = runtime.onFrame(vehicle(), kStart + std::chrono::milliseconds(30));
    ASSERT_EQ(update.events.size(), 1U);
    EXPECT_EQ(update.events[0].status, "OK");
}

TEST(AdasRuntime, WrongDlcInvalidatesSourceUntilValidReplacement) {
    AdasRuntime runtime(kStart);
    runtime.onFrame(vehicle(), kStart);
    runtime.onFrame(radar(), kStart);
    auto malformed = vehicle();
    malformed.dlc = 7;
    auto update = runtime.onFrame(malformed, kStart + std::chrono::milliseconds(5));
    ASSERT_EQ(update.events.size(), 1U);
    EXPECT_EQ(update.events[0].status, "INVALID_INPUT");
    EXPECT_EQ(update.events[0].reason, "WRONG_DLC");
    EXPECT_EQ(update.diagnostics[0].reason, "WRONG_DLC");
}

TEST(AdasRuntime, UnknownFramesDoNotRefreshRadarWatchdog) {
    AdasRuntime runtime(kStart);
    runtime.onFrame(vehicle(), kStart);
    runtime.onFrame(radar(), kStart + std::chrono::milliseconds(10));
    CanFrame unknown{};
    unknown.id = 0x555;
    unknown.dlc = 8;
    EXPECT_TRUE(runtime.onFrame(unknown, kStart + std::chrono::milliseconds(400)).events.empty());
    auto update = runtime.tick(kStart + std::chrono::milliseconds(510));
    EXPECT_EQ(lastStatus(update), "RADAR_TIMEOUT");
    EXPECT_EQ(update.events.back().last_radar_ms.value(), 10.0);
}

TEST(AdasRuntime, VehicleFreshnessPreventsUsingStaleRisk) {
    AdasRuntime runtime(kStart);
    runtime.onFrame(vehicle(), kStart);
    runtime.onFrame(radar(), kStart + std::chrono::milliseconds(450));
    auto update = runtime.tick(kStart + std::chrono::milliseconds(500));
    EXPECT_EQ(lastStatus(update), "VEHICLE_TIMEOUT");
}

TEST(AdasRuntime, TimeoutOverridesInvalidInputAndRecoveryReevaluatesLatestFrames) {
    AdasRuntime runtime(kStart);
    runtime.onFrame(vehicle(), kStart);
    runtime.onFrame(radar(), kStart);
    auto malformed = vehicle(3010);
    auto update = runtime.onFrame(malformed, kStart + std::chrono::milliseconds(10));
    ASSERT_EQ(lastStatus(update), "INVALID_INPUT");
    update = runtime.tick(kStart + std::chrono::milliseconds(500));
    ASSERT_EQ(lastStatus(update), "RADAR_TIMEOUT");
    update = runtime.onFrame(radar(), kStart + std::chrono::milliseconds(510));
    ASSERT_EQ(lastStatus(update), "INVALID_INPUT");
    update = runtime.onFrame(vehicle(), kStart + std::chrono::milliseconds(520));
    ASSERT_EQ(lastStatus(update), "OK");
    EXPECT_EQ(*update.events.back().warning_level, WarningLevel::WARNING);
}

TEST(AdasRuntime, RepeatedStateIsQuietAndTimeoutRecoveryCanTimeoutAgain) {
    AdasRuntime runtime(kStart);
    runtime.onFrame(vehicle(), kStart);
    auto update = runtime.onFrame(radar(), kStart);
    ASSERT_EQ(lastStatus(update), "OK");
    EXPECT_TRUE(runtime.onFrame(radar(), kStart + std::chrono::milliseconds(100)).events.empty());
    update = runtime.tick(kStart + std::chrono::milliseconds(600));
    ASSERT_EQ(lastStatus(update), "RADAR_TIMEOUT");
    runtime.onFrame(vehicle(), kStart + std::chrono::milliseconds(610));
    update = runtime.onFrame(radar(), kStart + std::chrono::milliseconds(610));
    ASSERT_EQ(lastStatus(update), "OK");
    update = runtime.tick(kStart + std::chrono::milliseconds(1110));
    EXPECT_EQ(lastStatus(update), "RADAR_TIMEOUT");
}

