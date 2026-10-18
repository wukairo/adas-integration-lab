#pragma once

#include "can_frame.hpp"

#include <optional>
#include <string>

// Receives Classical CAN data frames from a Linux SocketCAN interface.
// receive() returns an empty optional on timeout, EINTR, RTR/error frames, or
// malformed frames. Other system failures throw std::runtime_error with context.
// timeout_ms must be nonnegative; zero performs a nonblocking poll.
class CanReceiver {
public:
    explicit CanReceiver(const std::string& interface_name);
    ~CanReceiver();

    CanReceiver(const CanReceiver&) = delete;
    CanReceiver& operator=(const CanReceiver&) = delete;
    CanReceiver(CanReceiver&&) = delete;
    CanReceiver& operator=(CanReceiver&&) = delete;

    std::optional<CanFrame> receive(int timeout_ms);

private:
    int socket_fd_{-1};
    unsigned int interface_index_{};
    std::string interface_name_;
};
