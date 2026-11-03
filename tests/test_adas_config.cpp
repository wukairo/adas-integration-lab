#include "adas_config.hpp"

#include <gtest/gtest.h>

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>

#if defined(__unix__) || defined(__APPLE__)
#include <sys/wait.h>
#endif

namespace {
const std::string kConfig =
    "warning_ttc_s: 4.0\n"
    "critical_ttc_s: 2.0\n"
    "radar_timeout_ms: 500\n"
    "vehicle_timeout_ms: 500\n";

std::string shellQuote(const std::string &value) {
  std::string quoted = "'";
  for (char character : value) {
    if (character == '\'') {
      quoted += "'\\''";
    } else {
      quoted += character;
    }
  }
  quoted += "'";
  return quoted;
}
} // namespace

TEST(AdasConfig, ParsesTheFlatScalarSubsetAndDefaults) {
  const auto config = parseAdasConfig("# ADAS settings\n" + kConfig +
                                      "  # trailing comment\n");
  EXPECT_DOUBLE_EQ(config.warning_ttc_s, 4.0);
  EXPECT_DOUBLE_EQ(config.critical_ttc_s, 2.0);
  EXPECT_DOUBLE_EQ(config.radar_timeout_ms, 500.0);
  EXPECT_DOUBLE_EQ(config.vehicle_timeout_ms, 500.0);
  const AdasConfig defaults;
  EXPECT_DOUBLE_EQ(defaults.warning_ttc_s, 4.0);
  EXPECT_DOUBLE_EQ(defaults.critical_ttc_s, 2.0);
  EXPECT_DOUBLE_EQ(defaults.radar_timeout_ms, 500.0);
  EXPECT_DOUBLE_EQ(defaults.vehicle_timeout_ms, 500.0);
}

#ifdef ADAS_CONFIG_PATH
TEST(AdasConfig, ShippedYamlIsTheRuntimeConfigurationDocument) {
  const auto config = loadAdasConfig(ADAS_CONFIG_PATH);
  EXPECT_DOUBLE_EQ(config.warning_ttc_s, 4.0);
  EXPECT_DOUBLE_EQ(config.critical_ttc_s, 2.0);
  EXPECT_DOUBLE_EQ(config.radar_timeout_ms, 500.0);
  EXPECT_DOUBLE_EQ(config.vehicle_timeout_ms, 500.0);
}
#endif

TEST(AdasConfig, RejectsUnknownDuplicateMissingAndStructuredEntries) {
  EXPECT_THROW(parseAdasConfig(kConfig + "extra: 1\n"), std::runtime_error);
  EXPECT_THROW(parseAdasConfig(kConfig + "warning_ttc_s: 5\n"),
               std::runtime_error);
  EXPECT_THROW(parseAdasConfig("warning_ttc_s: 4\n"), std::runtime_error);
  const auto remainder = kConfig.substr(kConfig.find("critical_ttc_s"));
  EXPECT_THROW(parseAdasConfig("warning_ttc_s: [4]\n" + remainder),
               std::runtime_error);
  EXPECT_THROW(parseAdasConfig("  warning_ttc_s: 4\n" + remainder),
               std::runtime_error);
}

TEST(AdasConfig, RejectsNonfiniteNonpositiveAndMisorderedValues) {
  for (const auto &bad : {"nan", ".inf", "1e999", "0", "-1"}) {
    auto invalid = kConfig;
    invalid.replace(invalid.find("warning_ttc_s: 4.0"),
                    std::string("warning_ttc_s: 4.0").size(),
                    "warning_ttc_s: " + std::string(bad));
    EXPECT_THROW(parseAdasConfig(invalid), std::runtime_error) << bad;
  }
  for (const auto &bad : {"nan", "0", "-1"}) {
    auto invalid = kConfig;
    invalid.replace(invalid.find("radar_timeout_ms: 500"),
                    std::string("radar_timeout_ms: 500").size(),
                    "radar_timeout_ms: " + std::string(bad));
    EXPECT_THROW(parseAdasConfig(invalid), std::runtime_error) << bad;
  }
  for (const auto &entry : {std::pair<std::string, std::string>{
                                "critical_ttc_s: 2.0", "critical_ttc_s: 0"},
                            {"critical_ttc_s: 2.0", "critical_ttc_s: nan"},
                            {"vehicle_timeout_ms: 500", "vehicle_timeout_ms: 0"},
                            {"vehicle_timeout_ms: 500", "vehicle_timeout_ms: .inf"}}) {
    auto invalid = kConfig;
    invalid.replace(invalid.find(entry.first), entry.first.size(), entry.second);
    EXPECT_THROW(parseAdasConfig(invalid), std::runtime_error) << entry.second;
  }
  EXPECT_THROW(parseAdasConfig(
                   "warning_ttc_s: 2\ncritical_ttc_s: 2\n"
                   "radar_timeout_ms: 500\nvehicle_timeout_ms: 500\n"),
               std::runtime_error);
}

#ifdef ADAS_APP_PATH
TEST(AdasConfig, InvalidCliConfigExitsBeforeOpeningCanInterface) {
  const auto unique = std::chrono::steady_clock::now().time_since_epoch().count();
  const auto directory = std::filesystem::temp_directory_path() /
                         ("adas-config-cli-" + std::to_string(unique));
  std::filesystem::create_directories(directory);
  const auto config_path = directory / "invalid.yaml";
  const auto output_path = directory / "output.txt";
  {
    std::ofstream config(config_path);
    config << kConfig << "unknown_option: 1\n";
  }
  const std::string command =
      shellQuote(ADAS_APP_PATH) + " --adas no_such_can_interface --config " +
      shellQuote(config_path.string()) + " > " + shellQuote(output_path.string()) +
      " 2>&1";
  const int status = std::system(command.c_str());
  std::ifstream output_file(output_path);
  const std::string output((std::istreambuf_iterator<char>(output_file)),
                           std::istreambuf_iterator<char>());
  std::filesystem::remove_all(directory);

#if defined(__unix__) || defined(__APPLE__)
  ASSERT_NE(status, -1);
  ASSERT_TRUE(WIFEXITED(status));
  EXPECT_EQ(WEXITSTATUS(status), 2);
#else
  GTEST_SKIP() << "subprocess exit inspection is only implemented on POSIX";
#endif
  EXPECT_NE(output.find("Invalid ADAS config:"), std::string::npos) << output;
  EXPECT_NE(output.find("unknown key"), std::string::npos) << output;
  EXPECT_EQ(output.find("no_such_can_interface"), std::string::npos) << output;
}

TEST(AdasConfig, EmptyConfigPathIsAUsageError) {
  const auto unique = std::chrono::steady_clock::now().time_since_epoch().count();
  const auto output_path = std::filesystem::temp_directory_path() /
                           ("adas-empty-config-" + std::to_string(unique) + ".txt");
  const std::string command = shellQuote(ADAS_APP_PATH) +
                              " --adas vcan0 --config '' > " +
                              shellQuote(output_path.string()) + " 2>&1";
  const int status = std::system(command.c_str());
  std::ifstream output_file(output_path);
  const std::string output((std::istreambuf_iterator<char>(output_file)),
                           std::istreambuf_iterator<char>());
  std::filesystem::remove(output_path);

#if defined(__unix__) || defined(__APPLE__)
  ASSERT_NE(status, -1);
  ASSERT_TRUE(WIFEXITED(status));
  EXPECT_EQ(WEXITSTATUS(status), 2);
#else
  GTEST_SKIP() << "subprocess exit inspection is only implemented on POSIX";
#endif
  EXPECT_NE(output.find("Usage: adas_app"), std::string::npos) << output;
  EXPECT_EQ(output.find("ADAS mode is not supported"), std::string::npos) << output;
}
#endif
