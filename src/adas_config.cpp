#include "adas_config.hpp"

#include <charconv>
#include <cmath>
#include <fstream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string_view>

namespace {
std::string trim(const std::string &value) {
  const auto first = value.find_first_not_of(' ');
  if (first == std::string::npos) {
    return {};
  }
  const auto last = value.find_last_not_of(' ');
  return value.substr(first, last - first + 1);
}

bool decimalScalar(std::string_view token) {
  std::size_t index = 0;
  if (index < token.size() && (token[index] == '+' || token[index] == '-')) {
    ++index;
  }
  bool digits = false;
  while (index < token.size() && token[index] >= '0' && token[index] <= '9') {
    digits = true;
    ++index;
  }
  if (index < token.size() && token[index] == '.') {
    ++index;
    while (index < token.size() && token[index] >= '0' && token[index] <= '9') {
      digits = true;
      ++index;
    }
  }
  if (!digits) {
    return false;
  }
  if (index < token.size() && (token[index] == 'e' || token[index] == 'E')) {
    ++index;
    if (index < token.size() && (token[index] == '+' || token[index] == '-')) {
      ++index;
    }
    const auto exponent_start = index;
    while (index < token.size() && token[index] >= '0' && token[index] <= '9') {
      ++index;
    }
    if (index == exponent_start) {
      return false;
    }
  }
  return index == token.size();
}

double parseNumber(const std::string &token, const std::string &where) {
  if (!decimalScalar(token)) {
    throw std::runtime_error(where + ": expected an unquoted decimal scalar");
  }
  std::string_view view(token);
  if (!view.empty() && view.front() == '+') {
    view.remove_prefix(1);
  }
  double value{};
  const auto parsed = std::from_chars(view.data(), view.data() + view.size(), value,
                                      std::chars_format::general);
  if (parsed.ec != std::errc{} || parsed.ptr != view.data() + view.size()) {
    throw std::runtime_error(where + ": numeric scalar is out of range");
  }
  if (!std::isfinite(value)) {
    throw std::runtime_error(where + ": value must be finite");
  }
  return value;
}

std::string location(const std::string &source, std::size_t line) {
  return source + ":" + std::to_string(line);
}
} // namespace

void AdasConfig::validate() const {
  if (!std::isfinite(warning_ttc_s) || warning_ttc_s <= 0.0) {
    throw std::runtime_error("warning_ttc_s must be finite and positive");
  }
  if (!std::isfinite(critical_ttc_s) || critical_ttc_s <= 0.0) {
    throw std::runtime_error("critical_ttc_s must be finite and positive");
  }
  if (critical_ttc_s >= warning_ttc_s) {
    throw std::runtime_error("critical_ttc_s must be less than warning_ttc_s");
  }
  if (!std::isfinite(radar_timeout_ms) || radar_timeout_ms <= 0.0) {
    throw std::runtime_error("radar_timeout_ms must be finite and positive");
  }
  if (!std::isfinite(vehicle_timeout_ms) || vehicle_timeout_ms <= 0.0) {
    throw std::runtime_error("vehicle_timeout_ms must be finite and positive");
  }
}

AdasConfig parseAdasConfig(const std::string &yaml, const std::string &source) {
  AdasConfig config;
  std::set<std::string> seen;
  std::istringstream input(yaml);
  std::string line;
  std::size_t line_number = 0;
  while (std::getline(input, line)) {
    ++line_number;
    const auto where = location(source, line_number);
    if (!line.empty() && line.back() == '\r') {
      line.pop_back();
    }
    if (line.find('\t') != std::string::npos) {
      throw std::runtime_error(where + ": tabs are not supported");
    }
    const auto comment = line.find('#');
    if (comment != std::string::npos &&
        (comment == 0 || line[comment - 1] == ' ')) {
      line.erase(comment);
    }
    const auto content = trim(line);
    if (content.empty()) {
      continue;
    }
    if (line.front() == ' ') {
      throw std::runtime_error(where + ": nested or indented entries are not supported");
    }
    if (content.find(':') == std::string::npos) {
      throw std::runtime_error(where + ": expected a flat 'key: value' entry");
    }
    const auto colon = content.find(':');
    if (content.find(':', colon + 1) != std::string::npos) {
      throw std::runtime_error(where + ": expected one scalar value after ':'");
    }
    const auto key = trim(content.substr(0, colon));
    const auto scalar = trim(content.substr(colon + 1));
    if (key.empty() || key.find(' ') != std::string::npos || scalar.empty()) {
      throw std::runtime_error(where + ": expected a flat 'key: value' entry");
    }
    if (!seen.insert(key).second) {
      throw std::runtime_error(where + ": duplicate key '" + key + "'");
    }
    const double value = parseNumber(scalar, where + " " + key);
    if (key == "warning_ttc_s") {
      config.warning_ttc_s = value;
    } else if (key == "critical_ttc_s") {
      config.critical_ttc_s = value;
    } else if (key == "radar_timeout_ms") {
      config.radar_timeout_ms = value;
    } else if (key == "vehicle_timeout_ms") {
      config.vehicle_timeout_ms = value;
    } else {
      throw std::runtime_error(where + ": unknown key '" + key + "'");
    }
  }
  for (const auto *key : {"warning_ttc_s", "critical_ttc_s", "radar_timeout_ms",
                          "vehicle_timeout_ms"}) {
    if (seen.count(key) == 0) {
      throw std::runtime_error(source + ": missing required key '" + key + "'");
    }
  }
  config.validate();
  return config;
}

AdasConfig loadAdasConfig(const std::string &path) {
  std::ifstream input(path);
  if (!input) {
    throw std::runtime_error("unable to open config file '" + path + "'");
  }
  std::ostringstream contents;
  contents << input.rdbuf();
  if (input.bad()) {
    throw std::runtime_error("unable to read config file '" + path + "'");
  }
  return parseAdasConfig(contents.str(), path);
}
