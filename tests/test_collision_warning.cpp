#include "collision_warning.hpp"

#include <gtest/gtest.h>

#include <limits>
#include <stdexcept>

TEST(CollisionWarning, TtcThresholdsAndClosingDirection) {
    struct Case {
        double speed;
        double distance;
        double relative_velocity;
        WarningLevel expected;
    };
    const Case cases[] = {
        {50, 100, 0, WarningLevel::NONE},
        {80, 20, 7, WarningLevel::WARNING},
        {80, 10, 10, WarningLevel::CRITICAL},
        {80, 20, 10, WarningLevel::CRITICAL},
        {80, 40, 10, WarningLevel::WARNING},
        {80, 19.99, 10, WarningLevel::CRITICAL},
        {80, 20.01, 10, WarningLevel::WARNING},
        {80, 39.99, 10, WarningLevel::WARNING},
        {80, 40.01, 10, WarningLevel::NONE},
        {80, 20, -7, WarningLevel::NONE},
        {0, 20, 7, WarningLevel::WARNING},
        {300, 20, 7, WarningLevel::WARNING},
        {80, 20, 101, WarningLevel::CRITICAL},
    };
    for (const auto& test_case : cases) {
        SCOPED_TRACE(::testing::Message() << "speed=" << test_case.speed
                                           << " distance=" << test_case.distance
                                           << " relative=" << test_case.relative_velocity);
        EXPECT_EQ(evaluateCollisionRisk(test_case.speed, test_case.distance,
                                        test_case.relative_velocity), test_case.expected);
    }
}

TEST(CollisionWarning, ZeroDistanceIsCriticalForEveryClosingDirection) {
    for (double relative_velocity : {10.0, 0.0, -7.0}) {
        SCOPED_TRACE(relative_velocity);
        EXPECT_EQ(evaluateCollisionRisk(80, 0, relative_velocity), WarningLevel::CRITICAL);
    }
}

TEST(CollisionWarning, RejectsOutOfRangeInputsBeforeZeroDistanceShortcut) {
    EXPECT_THROW(evaluateCollisionRisk(-0.1, 20, 7), std::invalid_argument);
    EXPECT_THROW(evaluateCollisionRisk(300.1, 20, 7), std::invalid_argument);
    EXPECT_THROW(evaluateCollisionRisk(80, -0.1, 7), std::invalid_argument);
    EXPECT_THROW(evaluateCollisionRisk(-0.1, 0, 7), std::invalid_argument);
    EXPECT_THROW(evaluateCollisionRisk(300.1, 0, 7), std::invalid_argument);
}

TEST(CollisionWarning, RejectsEveryNonfiniteInput) {
    const double values[] = {
        std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::infinity(),
        -std::numeric_limits<double>::infinity(),
    };
    for (double value : values) {
        SCOPED_TRACE(value);
        EXPECT_THROW(evaluateCollisionRisk(value, 20, 7), std::invalid_argument);
        EXPECT_THROW(evaluateCollisionRisk(80, value, 7), std::invalid_argument);
        EXPECT_THROW(evaluateCollisionRisk(80, 20, value), std::invalid_argument);
        EXPECT_THROW(evaluateCollisionRisk(80, 0, value), std::invalid_argument);
    }
}
