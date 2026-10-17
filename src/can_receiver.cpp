#include "can_receiver.hpp"

#include <cerrno>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>

#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

namespace {
std::runtime_error systemError(const std::string& operation,
                               const std::string& interface_name,
                               int error_number) {
    return std::runtime_error(operation + " on interface '" + interface_name +
                               "': " + std::strerror(error_number));
}

void discardFrame(const char* reason, const std::string& interface_name) {
    std::cerr << "Ignoring CAN frame on interface '" << interface_name << "': "
              << reason << '\n';
}
}  // namespace

CanReceiver::CanReceiver(const std::string& interface_name)
    : interface_name_(interface_name) {
    if (interface_name.empty()) {
        throw std::invalid_argument("CAN interface name must not be empty");
    }
    if (interface_name.size() >= IFNAMSIZ) {
        throw std::invalid_argument("CAN interface name is too long");
    }

    const unsigned int interface_index = if_nametoindex(interface_name.c_str());
    if (interface_index == 0) {
        throw systemError("if_nametoindex", interface_name, errno);
    }

    const int fd = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (fd < 0) {
        throw systemError("socket", interface_name, errno);
    }

    sockaddr_can address{};
    address.can_family = AF_CAN;
    address.can_ifindex = static_cast<int>(interface_index);
    if (bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) {
        const int error_number = errno;
        close(fd);
        throw systemError("bind", interface_name, error_number);
    }

    socket_fd_ = fd;
    interface_index_ = interface_index;
}

CanReceiver::~CanReceiver() {
    if (socket_fd_ >= 0) {
        close(socket_fd_);
    }
}

std::optional<CanFrame> CanReceiver::receive(int timeout_ms) {
    if (timeout_ms < 0) {
        throw std::invalid_argument("CAN receive timeout must be nonnegative");
    }

    const unsigned int current_index = if_nametoindex(interface_name_.c_str());
    if (current_index == 0) {
        throw systemError("if_nametoindex", interface_name_, errno);
    }
    if (current_index != interface_index_) {
        throw std::runtime_error("CAN interface '" + interface_name_ +
                                 "' changed while receiving");
    }
    ifreq interface_request{};
    std::memcpy(interface_request.ifr_name, interface_name_.c_str(),
                interface_name_.size() + 1);
    if (ioctl(socket_fd_, SIOCGIFFLAGS, &interface_request) < 0) {
        throw systemError("ioctl(SIOCGIFFLAGS)", interface_name_, errno);
    }
    if ((interface_request.ifr_flags & IFF_UP) == 0) {
        throw std::runtime_error("CAN interface '" + interface_name_ +
                                 "' is down");
    }

    pollfd descriptor{};
    descriptor.fd = socket_fd_;
    descriptor.events = POLLIN;
    const int poll_result = poll(&descriptor, 1, timeout_ms);
    if (poll_result < 0) {
        if (errno == EINTR) {
            return std::nullopt;
        }
        throw systemError("poll", interface_name_, errno);
    }
    if (poll_result == 0) {
        return std::nullopt;
    }
    if ((descriptor.revents & (POLLERR | POLLHUP | POLLNVAL)) != 0) {
        int socket_error = 0;
        socklen_t error_size = sizeof(socket_error);
        if (getsockopt(socket_fd_, SOL_SOCKET, SO_ERROR, &socket_error,
                       &error_size) < 0) {
            throw systemError("getsockopt(SO_ERROR)", interface_name_, errno);
        }
        if (socket_error != 0) {
            throw systemError("poll", interface_name_, socket_error);
        }
        throw std::runtime_error("poll on interface '" + interface_name_ +
                                 "' reported socket events " +
                                 std::to_string(descriptor.revents));
    }
    if ((descriptor.revents & POLLIN) == 0) {
        throw std::runtime_error("poll returned without readable CAN data on interface '" +
                                 interface_name_ + "'");
    }

    can_frame raw_frame{};
    const ssize_t bytes_read = read(socket_fd_, &raw_frame, sizeof(raw_frame));
    if (bytes_read < 0) {
        if (errno == EINTR) {
            return std::nullopt;
        }
        throw systemError("read", interface_name_, errno);
    }
    if (bytes_read != CAN_MTU) {
        discardFrame("unexpected frame size", interface_name_);
        return std::nullopt;
    }
    if (raw_frame.can_dlc > CAN_MAX_DLEN) {
        discardFrame("DLC exceeds Classical CAN maximum of 8", interface_name_);
        return std::nullopt;
    }
    if (raw_frame.len8_dlc != 0 &&
        (raw_frame.can_dlc != CAN_MAX_DLEN ||
         raw_frame.len8_dlc <= CAN_MAX_DLC ||
         raw_frame.len8_dlc > CAN_MAX_RAW_DLC)) {
        discardFrame("invalid len8_dlc metadata", interface_name_);
        return std::nullopt;
    }
    if ((raw_frame.can_id & CAN_ERR_FLAG) != 0 ||
        (raw_frame.can_id & CAN_RTR_FLAG) != 0) {
        return std::nullopt;
    }

    CanFrame frame{};
    frame.extended = (raw_frame.can_id & CAN_EFF_FLAG) != 0;
    frame.id = frame.extended ? (raw_frame.can_id & CAN_EFF_MASK)
                              : (raw_frame.can_id & CAN_SFF_MASK);
    frame.dlc = raw_frame.can_dlc;
    for (std::size_t index = 0; index < frame.dlc; ++index) {
        frame.data[index] = raw_frame.data[index];
    }
    return frame;
}
