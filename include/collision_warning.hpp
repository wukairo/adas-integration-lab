#pragma once

#include <stdexcept>

enum class WarningLevel { NONE, WARNING, CRITICAL };

// Positive relative_velocity_mps means the vehicle is closing on the obstacle.
// Inputs must be finite; speed is in [0, 300] km/h and distance is nonnegative.
// Throws std::invalid_argument when an input is invalid.
WarningLevel evaluateCollisionRisk(double vehicle_speed_kmh,
                                   double distance_m,
                                   double relative_velocity_mps);
