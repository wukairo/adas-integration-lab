#include "collision_warning.hpp"
#include "can_decoder.hpp"
#include "adas_runtime.hpp"

#include <exception>
#include <iomanip>
#include <iostream>
#include <locale>
#include <sstream>
#include <string>

#ifdef ADAS_HAS_SOCKETCAN
#include "can_receiver.hpp"
#include <csignal>
#endif

namespace {
#ifdef ADAS_HAS_SOCKETCAN
volatile std::sig_atomic_t stop_requested = 0;

void requestStop(int) {
    stop_requested = 1;
}

std::ostringstream formatCanId(const CanFrame& frame) {
    std::ostringstream output;
    output.imbue(std::locale::classic());
    output << "CAN id=0x" << std::uppercase << std::hex << std::setfill('0')
           << std::setw(frame.extended ? 8 : 3) << frame.id << " format="
           << (frame.extended ? "extended" : "standard") << " dlc="
           << std::dec << static_cast<unsigned int>(frame.dlc) << " data=";
    return output;
}

void printFrame(const CanFrame& frame) {
    std::ostringstream output = formatCanId(frame);
    for (std::size_t index = 0; index < frame.dlc; ++index) {
        if (index != 0) {
            output << ' ';
        }
        output << std::uppercase << std::hex << std::setw(2)
               << static_cast<unsigned int>(frame.data[index]);
    }
    std::cout << output.str() << '\n' << std::flush;
}

std::string canId(const CanFrame& frame) {
    std::ostringstream output;
    output.imbue(std::locale::classic());
    output << "0x" << std::uppercase << std::hex << std::setfill('0')
           << std::setw(frame.extended ? 8 : 3) << frame.id;
    return output.str();
}

void printDecodeDiagnostic(const char* category, const char* reason,
                           const CanFrame& frame) {
    std::cerr << category << " reason=" << reason << " id=" << canId(frame)
              << '\n';
}

void printDecodedFrame(const CanFrame& frame) {
    if (frame.extended) {
        printDecodeDiagnostic("DECODE_IGNORED", "UNSUPPORTED_FORMAT", frame);
        return;
    }
    if (frame.id != 0x100 && frame.id != 0x200) {
        printDecodeDiagnostic("DECODE_IGNORED", "UNKNOWN_ID", frame);
        return;
    }

    std::ostringstream output;
    output.imbue(std::locale::classic());
    output << std::fixed << std::setprecision(2);
    if (frame.id == 0x100) {
        const auto result = decodeVehicleState(frame);
        if (const auto* state = std::get_if<VehicleState>(&result)) {
            output << "VehicleState speed_kmh=" << state->speed_kmh
                   << " steering_angle_deg=" << state->steering_angle_deg
                   << " brake_pressed=" << (state->brake_pressed ? 1 : 0);
            std::cout << output.str() << '\n' << std::flush;
            return;
        }
        const auto error = std::get<DecodeError>(result);
        if (error == DecodeError::WrongDlc) {
            printDecodeDiagnostic("DECODE_ERROR", "WRONG_DLC", frame);
        } else if (error == DecodeError::OutOfRange) {
            printDecodeDiagnostic("INVALID_INPUT", "OUT_OF_RANGE", frame);
        } else if (error == DecodeError::UnsupportedFormat) {
            printDecodeDiagnostic("DECODE_IGNORED", "UNSUPPORTED_FORMAT", frame);
        } else {
            printDecodeDiagnostic("DECODE_IGNORED", "UNKNOWN_ID", frame);
        }
        return;
    }

    const auto result = decodeRadarObject(frame);
    if (const auto* object = std::get_if<RadarObject>(&result)) {
        output << "RadarObject distance_m=" << object->distance_m
               << " relative_velocity_mps=" << object->relative_velocity_mps
               << " object_valid=" << (object->object_valid ? 1 : 0);
        std::cout << output.str() << '\n' << std::flush;
        return;
    }
    const auto error = std::get<DecodeError>(result);
    if (error == DecodeError::WrongDlc) {
        printDecodeDiagnostic("DECODE_ERROR", "WRONG_DLC", frame);
    } else if (error == DecodeError::OutOfRange) {
        printDecodeDiagnostic("INVALID_INPUT", "OUT_OF_RANGE", frame);
    } else if (error == DecodeError::UnsupportedFormat) {
        printDecodeDiagnostic("DECODE_IGNORED", "UNSUPPORTED_FORMAT", frame);
    } else {
        printDecodeDiagnostic("DECODE_IGNORED", "UNKNOWN_ID", frame);
    }
}

int runCanReceiver(const std::string& interface_name, bool decode_mode) {
    struct sigaction action{};
    action.sa_handler = requestStop;
    sigemptyset(&action.sa_mask);
    action.sa_flags = 0;
    if (sigaction(SIGINT, &action, nullptr) < 0 ||
        sigaction(SIGTERM, &action, nullptr) < 0) {
        std::cerr << "Unable to install signal handlers\n";
        return 1;
    }

    try {
        CanReceiver receiver(interface_name);
        while (stop_requested == 0) {
            const auto frame = receiver.receive(200);
            if (frame.has_value()) {
                if (decode_mode) {
                    printDecodedFrame(*frame);
                } else {
                    printFrame(*frame);
                }
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
#endif

void printUsage() {
    std::cerr << "Usage: adas_app <speed_kmh> <distance_m> <closing_speed_mps>\n"
                 "       adas_app --can <interface>\n"
                 "       adas_app --decode <interface>\n"
                 "       adas_app --adas <interface>\n";
}

bool parseNumber(const std::string& token, double& value) {
    try {
        std::size_t parsed_chars = 0;
        value = std::stod(token, &parsed_chars);
        return parsed_chars == token.size();
    } catch (const std::exception&) {
        return false;
    }
}

#ifdef ADAS_HAS_SOCKETCAN
void printRuntimeUpdate(const AdasRuntime::Update& update) {
    for (const auto& diagnostic : update.diagnostics) {
        CanFrame frame{};
        frame.id = diagnostic.id;
        std::cerr << diagnostic.category << " reason=" << diagnostic.reason
                  << " id=" << canId(frame) << '\n' << std::flush;
    }
    for (const auto& event : update.events) {
        std::cout << std::fixed << std::setprecision(3) << "ADAS_STATE t_ms="
                  << event.t_ms << " status=" << event.status;
        if (event.warning_level) {
            std::cout << " WarningLevel=" << warningLevelName(*event.warning_level);
        }
        std::cout << " reason=" << event.reason;
        if (event.source) std::cout << " source=" << *event.source;
        if (event.radar_age_ms) {
            std::cout << " radar_age_ms=" << *event.radar_age_ms;
            if (event.last_radar_ms) std::cout << " last_radar_ms=" << *event.last_radar_ms;
            else std::cout << " radar_seen=0";
        }
        std::cout << '\n' << std::flush;
    }
}

int runAdas(const std::string& interface_name) {
    struct sigaction action{};
    action.sa_handler = requestStop;
    sigemptyset(&action.sa_mask);
    action.sa_flags = 0;
    if (sigaction(SIGINT, &action, nullptr) < 0 ||
        sigaction(SIGTERM, &action, nullptr) < 0) {
        std::cerr << "Unable to install signal handlers\n";
        return 1;
    }
    try {
        CanReceiver receiver(interface_name);
        const auto started_at = AdasRuntime::Clock::now();
        AdasRuntime runtime(started_at);
        std::cout << "ADAS_READY interface=" << interface_name
                  << " radar_timeout_ms=500 vehicle_timeout_ms=500\n" << std::flush;
        printRuntimeUpdate(runtime.tick(started_at));
        while (stop_requested == 0) {
            printRuntimeUpdate(runtime.tick(AdasRuntime::Clock::now()));
            if (stop_requested != 0) break;
            const auto frame = receiver.receive(50);
            const auto now = AdasRuntime::Clock::now();
            if (frame) printRuntimeUpdate(runtime.onFrame(*frame, now));
            else printRuntimeUpdate(runtime.tick(now));
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
#endif
}  // namespace

int main(int argc, char* argv[]) {
#ifdef ADAS_HAS_SOCKETCAN
    if (argc >= 2 && std::string(argv[1]) == "--can") {
        if (argc != 3) {
            printUsage();
            return 2;
        }
        stop_requested = 0;
        return runCanReceiver(argv[2], false);
    }
    if (argc >= 2 && std::string(argv[1]) == "--decode") {
        if (argc != 3) {
            printUsage();
            return 2;
        }
        stop_requested = 0;
        return runCanReceiver(argv[2], true);
    }
    if (argc >= 2 && std::string(argv[1]) == "--adas") {
        if (argc != 3) { printUsage(); return 2; }
        stop_requested = 0;
        return runAdas(argv[2]);
    }
#else
    if (argc >= 2 && std::string(argv[1]) == "--can") {
        if (argc != 3) {
            printUsage();
            return 2;
        }
        std::cerr << "CAN mode is not supported on this platform\n";
        return 1;
    }
    if (argc >= 2 && std::string(argv[1]) == "--decode") {
        if (argc != 3) {
            printUsage();
            return 2;
        }
        std::cerr << "CAN decode mode is not supported on this platform\n";
        return 1;
    }
    if (argc >= 2 && std::string(argv[1]) == "--adas") {
        if (argc != 3) { printUsage(); return 2; }
        std::cerr << "ADAS mode is not supported on this platform\n";
        return 1;
    }
#endif

    if (argc != 4) {
        printUsage();
        return 2;
    }

    double values[3]{};
    for (int i = 0; i < 3; ++i) {
        if (!parseNumber(argv[i + 1], values[i])) {
            std::cerr << "INVALID_INPUT\n";
            return 2;
        }
    }

    try {
        const auto level = evaluateCollisionRisk(values[0], values[1], values[2]);
        std::cout << "WarningLevel=" << warningLevelName(level) << '\n';
        return 0;
    } catch (const std::invalid_argument&) {
        std::cerr << "INVALID_INPUT\n";
        return 2;
    }
}
