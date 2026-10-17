#include "collision_warning.hpp"

#include <exception>
#include <iomanip>
#include <iostream>
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

void printFrame(const CanFrame& frame) {
    std::ostringstream output;
    output << "CAN id=0x" << std::uppercase << std::hex << std::setfill('0')
           << std::setw(frame.extended ? 8 : 3) << frame.id << " format="
           << (frame.extended ? "extended" : "standard") << " dlc="
           << std::dec << static_cast<unsigned int>(frame.dlc) << " data=";
    for (std::size_t index = 0; index < frame.dlc; ++index) {
        if (index != 0) {
            output << ' ';
        }
        output << std::uppercase << std::hex << std::setw(2)
               << static_cast<unsigned int>(frame.data[index]);
    }
    std::cout << output.str() << '\n' << std::flush;
}

int runCanReceiver(const std::string& interface_name) {
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
                printFrame(*frame);
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
#endif

const char* warningLevelName(WarningLevel level) {
    switch (level) {
        case WarningLevel::NONE:
            return "NONE";
        case WarningLevel::WARNING:
            return "WARNING";
        case WarningLevel::CRITICAL:
            return "CRITICAL";
    }
    return "NONE";
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
}  // namespace

int main(int argc, char* argv[]) {
#ifdef ADAS_HAS_SOCKETCAN
    if (argc >= 2 && std::string(argv[1]) == "--can") {
        if (argc != 3) {
            std::cerr << "Usage: adas_app <speed_kmh> <distance_m> <closing_speed_mps>\n"
                         "       adas_app --can <interface>\n";
            return 2;
        }
        stop_requested = 0;
        return runCanReceiver(argv[2]);
    }
#else
    if (argc >= 2 && std::string(argv[1]) == "--can") {
        if (argc != 3) {
            std::cerr << "Usage: adas_app <speed_kmh> <distance_m> <closing_speed_mps>\n"
                         "       adas_app --can <interface>\n";
            return 2;
        }
        std::cerr << "CAN mode is not supported on this platform\n";
        return 1;
    }
#endif

    if (argc != 4) {
        std::cerr << "Usage: adas_app <speed_kmh> <distance_m> <closing_speed_mps>\n"
                     "       adas_app --can <interface>\n";
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
