#pragma once

#include <array>
#include <cstdint>

// Arbitration ID without SocketCAN flag bits (11-bit standard / 29-bit extended).
struct CanFrame {
    std::uint32_t id{};
    std::uint8_t dlc{};
    std::array<std::uint8_t, 8> data{};
    bool extended{};
};
