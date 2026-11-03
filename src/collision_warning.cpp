#include "collision_warning.hpp"

#include <cmath>

WarningLevel evaluateCollisionRisk(double vehicle_speed_kmh, double distance_m,
                                   double relative_velocity_mps) {
  return evaluateCollisionRisk(vehicle_speed_kmh, distance_m,
                               relative_velocity_mps, 2.0, 4.0);
}

WarningLevel evaluateCollisionRisk(double vehicle_speed_kmh, double distance_m,
                                   double relative_velocity_mps,
                                   double critical_ttc_s,
                                   double warning_ttc_s) {
  if (!std::isfinite(vehicle_speed_kmh) || !std::isfinite(distance_m) ||
      !std::isfinite(relative_velocity_mps) || !std::isfinite(critical_ttc_s) ||
      !std::isfinite(warning_ttc_s) || vehicle_speed_kmh < 0.0 ||
      vehicle_speed_kmh > 300.0 || distance_m < 0.0 || critical_ttc_s <= 0.0 ||
      warning_ttc_s <= 0.0 || critical_ttc_s >= warning_ttc_s) {
    throw std::invalid_argument("input values are outside the valid range");
  }

  if (distance_m == 0.0) {
    return WarningLevel::CRITICAL;
  }
  if (relative_velocity_mps <= 0.0) {
    return WarningLevel::NONE;
  }

  const double time_to_collision = distance_m / relative_velocity_mps;
  if (time_to_collision <= critical_ttc_s) {
    return WarningLevel::CRITICAL;
  }
  if (time_to_collision <= warning_ttc_s) {
    return WarningLevel::WARNING;
  }
  return WarningLevel::NONE;
}
