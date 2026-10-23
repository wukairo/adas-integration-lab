#include "adas_runtime.hpp"

#include "can_decoder.hpp"

#include <iomanip>
#include <locale>
#include <sstream>
#include <variant>

bool AdasRuntime::State::operator==(const State& other) const {
    return status == other.status && reason == other.reason &&
           warning_level == other.warning_level && source == other.source;
}

namespace {
AdasRuntime::Diagnostic diagnosticFor(DecodeError error, std::uint32_t id) {
    switch (error) {
        case DecodeError::WrongDlc:
            return {"DECODE_ERROR", "WRONG_DLC", id};
        case DecodeError::OutOfRange:
            return {"INVALID_INPUT", "OUT_OF_RANGE", id};
        case DecodeError::UnsupportedFormat:
            return {"DECODE_IGNORED", "UNSUPPORTED_FORMAT", id};
        case DecodeError::WrongId:
            return {"DECODE_IGNORED", "UNKNOWN_ID", id};
    }
    return {"DECODE_IGNORED", "UNKNOWN_ID", id};
}

double milliseconds(AdasRuntime::Clock::duration duration) {
    return std::chrono::duration<double, std::milli>(duration).count();
}
}  // namespace

AdasRuntime::AdasRuntime(Clock::time_point started_at) : started_at_(started_at) {}

AdasRuntime::Update AdasRuntime::onFrame(const CanFrame& frame, Clock::time_point now) {
    Update update;
    if (frame.extended || (frame.id != 0x100 && frame.id != 0x200)) {
        return update;
    }

    if (frame.id == 0x100) {
        const auto decoded = decodeVehicleState(frame);
        if (const auto* vehicle = std::get_if<VehicleState>(&decoded)) {
            speed_kmh_ = vehicle->speed_kmh;
            have_vehicle_ = true;
            vehicle_error_.clear();
            last_vehicle_at_ = now;
        } else {
            const auto error = std::get<DecodeError>(decoded);
            update.diagnostics.push_back(diagnosticFor(error, frame.id));
            if (error == DecodeError::WrongDlc || error == DecodeError::OutOfRange) {
                vehicle_error_ = error == DecodeError::WrongDlc ? "WRONG_DLC" : "OUT_OF_RANGE";
            }
        }
    } else {
        const auto decoded = decodeRadarObject(frame);
        if (const auto* radar = std::get_if<RadarObject>(&decoded)) {
            distance_m_ = radar->distance_m;
            relative_velocity_mps_ = radar->relative_velocity_mps;
            object_valid_ = radar->object_valid;
            have_radar_ = true;
            radar_error_.clear();
            last_radar_at_ = now;
        } else {
            const auto error = std::get<DecodeError>(decoded);
            update.diagnostics.push_back(diagnosticFor(error, frame.id));
            if (error == DecodeError::WrongDlc || error == DecodeError::OutOfRange) {
                radar_error_ = error == DecodeError::WrongDlc ? "WRONG_DLC" : "OUT_OF_RANGE";
            }
        }
    }

    auto evaluated = evaluate(now);
    update.events = std::move(evaluated.events);
    update.diagnostics.insert(update.diagnostics.end(), evaluated.diagnostics.begin(),
                              evaluated.diagnostics.end());
    return update;
}

AdasRuntime::Update AdasRuntime::tick(Clock::time_point now) { return evaluate(now); }

AdasRuntime::Update AdasRuntime::evaluate(Clock::time_point now) {
    Update update;
    State state;
    const auto radar_reference = have_radar_ ? last_radar_at_ : started_at_;
    const auto radar_age = now - radar_reference;
    const bool radar_timed_out = radar_age >= kRadarTimeout;
    const bool vehicle_timed_out = have_vehicle_ && now - last_vehicle_at_ >= kVehicleTimeout;

    if (radar_timed_out) {
        state = {"RADAR_TIMEOUT", "RADAR_STALE", std::nullopt, std::nullopt};
    } else if (!vehicle_error_.empty() || !radar_error_.empty()) {
        if (!vehicle_error_.empty()) {
            state = {"INVALID_INPUT", vehicle_error_, std::nullopt, "VehicleState"};
        } else {
            state = {"INVALID_INPUT", radar_error_, std::nullopt, "RadarObject"};
        }
    } else if (vehicle_timed_out) {
        state = {"VEHICLE_TIMEOUT", "VEHICLE_STALE", std::nullopt, std::nullopt};
    } else if (!have_vehicle_ || !have_radar_) {
        state = {"WAITING_FOR_INPUT", "MISSING_INPUT", std::nullopt, std::nullopt};
    } else if (!object_valid_) {
        state = {"OK", "NO_OBJECT", WarningLevel::NONE, std::nullopt};
    } else {
        state = {"OK", "RISK_EVALUATED", evaluateCollisionRisk(
                                              speed_kmh_, distance_m_,
                                              relative_velocity_mps_), std::nullopt};
    }

    if (!last_state_ || !(state == *last_state_)) {
        Event event;
        event.t_ms = milliseconds(now - started_at_);
        event.status = state.status;
        event.reason = state.reason;
        event.warning_level = state.warning_level;
        event.source = state.source;
        if (state.status == "RADAR_TIMEOUT") {
            event.radar_age_ms = milliseconds(radar_age);
            if (have_radar_) {
                event.last_radar_ms = milliseconds(last_radar_at_ - started_at_);
            }
        }
        update.events.push_back(std::move(event));
        last_state_ = state;
    }
    return update;
}

const char* warningLevelName(WarningLevel level) {
    switch (level) {
        case WarningLevel::NONE: return "NONE";
        case WarningLevel::WARNING: return "WARNING";
        case WarningLevel::CRITICAL: return "CRITICAL";
    }
    return "NONE";
}
