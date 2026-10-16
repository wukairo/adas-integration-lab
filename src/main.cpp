#include "collision_warning.hpp"

#include <exception>
#include <iostream>
#include <string>

namespace {
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
    if (argc != 4) {
        std::cerr << "Usage: adas_app <speed_kmh> <distance_m> <closing_speed_mps>\n";
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
