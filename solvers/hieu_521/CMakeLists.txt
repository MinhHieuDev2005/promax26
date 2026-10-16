cmake_minimum_required(VERSION 3.20)
project(hieu_521_runner LANGUAGES CXX)
set(DUC_RUNNER_OUTPUT "${CMAKE_CURRENT_LIST_DIR}/../../build-pro26-hieu" CACHE PATH "Runner output directory")
find_package(Threads REQUIRED)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../../../pro26-hieu/promax26"
                 "${CMAKE_BINARY_DIR}/hieu" EXCLUDE_FROM_ALL)

add_executable(hieu_521_runner offline_runner.cpp)
target_link_libraries(hieu_521_runner PRIVATE
    hexa_udon_json hexa_udon_prematch_selector)
target_compile_features(hieu_521_runner PRIVATE cxx_std_20)
set_target_properties(hieu_521_runner PROPERTIES
    OUTPUT_NAME hexa_udon_hieu_runner_v2
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/../../build-pro26-hieu")

add_executable(udon530_runner offline_runner.cpp)
target_link_libraries(udon530_runner PRIVATE hexa_udon_json hexa_udon_prematch_selector)
target_compile_features(udon530_runner PRIVATE cxx_std_20)
target_compile_definitions(udon530_runner PRIVATE HEXUDON_TARGET530=1)
set_target_properties(udon530_runner PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/../../build-pro26-hieu")

add_executable(udon530_tail_runner offline_runner.cpp)
target_link_libraries(udon530_tail_runner PRIVATE hexa_udon_json hexa_udon_prematch_selector)
target_compile_features(udon530_tail_runner PRIVATE cxx_std_20)
target_compile_definitions(udon530_tail_runner PRIVATE HEXUDON_TARGET530=1)
set_target_properties(udon530_tail_runner PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/../../build-pro26-hieu")

add_library(duc530_optimizer src/optimizer.cpp)
add_executable(udon_stock_fuel_runner offline_runner.cpp)
target_link_libraries(udon_stock_fuel_runner PRIVATE hexa_udon_json duc530_selector)
target_compile_features(udon_stock_fuel_runner PRIVATE cxx_std_20)
target_compile_definitions(udon_stock_fuel_runner PRIVATE HEXUDON_TARGET530=1 HEXUDON_LOOKAHEAD=1 HEXUDON_CROSS=1 HEXUDON_STOCK_FUEL=1)
set_target_properties(udon_stock_fuel_runner PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/../../build-stock-fuel")
add_executable(cross_routes_test tests/cross_routes_test.cpp)
target_compile_features(cross_routes_test PRIVATE cxx_std_20)
add_executable(udon530_cross_runner offline_runner.cpp)
target_link_libraries(udon530_cross_runner PRIVATE hexa_udon_json duc530_selector)
target_compile_features(udon530_cross_runner PRIVATE cxx_std_20)
target_compile_definitions(udon530_cross_runner PRIVATE HEXUDON_TARGET530=1 HEXUDON_LOOKAHEAD=1 HEXUDON_CROSS=1)
set_target_properties(udon530_cross_runner PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${DUC_RUNNER_OUTPUT}")
add_library(duc530_planner src/day_planner.cpp)
target_link_libraries(duc530_planner PUBLIC hexa_udon_core hexa_udon_pathfinding hexa_udon_simulator)
target_compile_features(duc530_planner PUBLIC cxx_std_20)
target_link_libraries(duc530_optimizer PUBLIC duc530_planner Threads::Threads)
target_compile_features(duc530_optimizer PUBLIC cxx_std_20)
add_library(duc530_selector
    "${CMAKE_CURRENT_LIST_DIR}/../../../pro26-hieu/promax26/src/planner/prematch_type_selector.cpp")
target_link_libraries(duc530_selector PUBLIC duc530_optimizer)
target_compile_features(duc530_selector PUBLIC cxx_std_20)
add_executable(udon530_lookahead_runner offline_runner.cpp)
target_link_libraries(udon530_lookahead_runner PRIVATE hexa_udon_json duc530_selector)
target_compile_features(udon530_lookahead_runner PRIVATE cxx_std_20)
target_compile_definitions(udon530_lookahead_runner PRIVATE HEXUDON_TARGET530=1 HEXUDON_LOOKAHEAD=1)
set_target_properties(udon530_lookahead_runner PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/../../build-pro26-hieu")
