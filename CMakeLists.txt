cmake_minimum_required(VERSION 3.16)
project(adas_integration_lab VERSION 0.1.0 LANGUAGES CXX)
include(CTest)

add_library(adas_core src/collision_warning.cpp)
target_include_directories(adas_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_features(adas_core PUBLIC cxx_std_17)
set_target_properties(adas_core PROPERTIES CXX_EXTENSIONS OFF)

add_library(adas_decoder src/can_decoder.cpp)
target_include_directories(adas_decoder PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_features(adas_decoder PUBLIC cxx_std_17)
set_target_properties(adas_decoder PROPERTIES CXX_EXTENSIONS OFF)

add_library(adas_runtime src/adas_runtime.cpp)
target_include_directories(adas_runtime PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(adas_runtime PUBLIC adas_core adas_decoder)
target_compile_features(adas_runtime PUBLIC cxx_std_17)
set_target_properties(adas_runtime PROPERTIES CXX_EXTENSIONS OFF)

add_executable(adas_app src/main.cpp)
target_link_libraries(adas_app PRIVATE adas_core adas_decoder adas_runtime)
target_compile_features(adas_app PRIVATE cxx_std_17)
set_target_properties(adas_app PROPERTIES CXX_EXTENSIONS OFF)

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    add_library(adas_can src/can_receiver.cpp)
    target_include_directories(adas_can PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
    target_compile_features(adas_can PUBLIC cxx_std_17)
    set_target_properties(adas_can PROPERTIES CXX_EXTENSIONS OFF)

    target_link_libraries(adas_app PRIVATE adas_can)
    target_compile_definitions(adas_app PRIVATE ADAS_HAS_SOCKETCAN=1)
endif()

set(adas_targets adas_core adas_decoder adas_runtime adas_app)
if(TARGET adas_can)
    list(APPEND adas_targets adas_can)
endif()

if(BUILD_TESTING)
    find_package(GTest CONFIG REQUIRED)
    include(GoogleTest)

    add_executable(test_collision_warning tests/test_collision_warning.cpp)
    target_link_libraries(test_collision_warning PRIVATE adas_core GTest::gtest_main)
    gtest_discover_tests(test_collision_warning)

    add_executable(test_can_decoder tests/test_can_decoder.cpp)
    target_link_libraries(test_can_decoder PRIVATE adas_decoder GTest::gtest_main)
    gtest_discover_tests(test_can_decoder)

    add_executable(test_adas_runtime tests/test_adas_runtime.cpp)
    target_link_libraries(test_adas_runtime PRIVATE adas_runtime GTest::gtest_main)
    gtest_discover_tests(test_adas_runtime)

    list(APPEND adas_targets test_collision_warning test_can_decoder test_adas_runtime)
endif()

foreach(target IN LISTS adas_targets)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endforeach()
