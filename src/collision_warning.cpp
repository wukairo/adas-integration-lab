#include "collision_warning.hpp"

#include <cmath>

WarningLevel evaluateCollisionRisk(double vehicle_speed_kmh,
                                   double distance_m,
                                   double relative_velocity_mps) {
    if (!std::isfinite(vehicle_speed_kmh) || !std::isfinite(distance_m) ||
        !std::isfinite(relative_velocity_mps) || vehicle_speed_kmh < 0.0 ||
        vehicle_speed_kmh > 300.0 || distance_m < 0.0) {
        throw std::invalid_argument("input values are outside the valid range");
    }

    if (distance_m == 0.0) {
        return WarningLevel::CRITICAL;
    }
    if (relative_velocity_mps <= 0.0) {
        return WarningLevel::NONE;
    }

    const double time_to_collision = distance_m / relative_velocity_mps;
    if (time_to_collision <= 2.0) {
        return WarningLevel::CRITICAL;
    }
    if (time_to_collision <= 4.0) {
        return WarningLevel::WARNING;
    }
    return WarningLevel::NONE;
}
