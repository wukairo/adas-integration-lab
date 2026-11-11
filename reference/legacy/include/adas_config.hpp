#pragma once

#include <string>

// Supported document shape is a flat mapping of four decimal scalar values:
// key: value. Blank lines and YAML comments are accepted; collections,
// quoted scalars, aliases, tags, and nested mappings are intentionally not.
struct AdasConfig {
  double warning_ttc_s{4.0};
  double critical_ttc_s{2.0};
  double radar_timeout_ms{500.0};
  double vehicle_timeout_ms{500.0};

  void validate() const;
};

AdasConfig parseAdasConfig(const std::string &yaml,
                           const std::string &source = "<memory>");
AdasConfig loadAdasConfig(const std::string &path);
