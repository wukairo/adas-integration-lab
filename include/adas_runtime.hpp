#pragma once

#include "can_frame.hpp"
#include "collision_warning.hpp"

#include <chrono>
#include <optional>
#include <string>
#include <vector>

class AdasRuntime {
public:
    using Clock = std::chrono::steady_clock;
    static constexpr auto kRadarTimeout = std::chrono::milliseconds(500);
    static constexpr auto kVehicleTimeout = std::chrono::milliseconds(500);

    struct Event {
        double t_ms{};
        std::string status;
        std::string reason;
        std::optional<WarningLevel> warning_level;
        std::optional<std::string> source;
        std::optional<double> radar_age_ms;
        std::optional<double> last_radar_ms;
    };

    struct Diagnostic {
        std::string category;
        std::string reason;
        std::uint32_t id{};
    };

    struct Update {
        std::vector<Event> events;
        std::vector<Diagnostic> diagnostics;
    };

    explicit AdasRuntime(Clock::time_point started_at);
    Update onFrame(const CanFrame& frame, Clock::time_point now);
    Update tick(Clock::time_point now);

private:
    struct State {
        std::string status;
        std::string reason;
        std::optional<WarningLevel> warning_level;
        std::optional<std::string> source;

        bool operator==(const State& other) const;
    };
    Clock::time_point started_at_;
    Clock::time_point last_vehicle_at_{};
    Clock::time_point last_radar_at_{};
    bool have_vehicle_{};
    bool have_radar_{};
    std::string vehicle_error_;
    std::string radar_error_;
    double speed_kmh_{};
    double distance_m_{};
    double relative_velocity_mps_{};
    bool object_valid_{};
    std::optional<State> last_state_;

    Update evaluate(Clock::time_point now);
};

const char* warningLevelName(WarningLevel level);
