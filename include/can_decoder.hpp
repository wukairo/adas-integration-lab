#pragma once

#include "can_frame.hpp"

#include <variant>

struct VehicleState {
    double speed_kmh{};
    double steering_angle_deg{};
    bool brake_pressed{};
};

struct RadarObject {
    double distance_m{};
    double relative_velocity_mps{};
    bool object_valid{};
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
