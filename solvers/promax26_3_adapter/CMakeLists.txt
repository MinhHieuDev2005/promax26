cmake_minimum_required(VERSION 3.20)
project(promax26_3_adapter LANGUAGES CXX)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../../../promax26-3"
                 "${CMAKE_BINARY_DIR}/promax26_3" EXCLUDE_FROM_ALL)

add_executable(promax26_3_runner ../hieu_521/offline_runner.cpp)
target_link_libraries(promax26_3_runner PRIVATE
    hexa_udon_json hexa_udon_prematch_selector)
target_compile_features(promax26_3_runner PRIVATE cxx_std_20)
target_compile_definitions(promax26_3_runner PRIVATE HEXUDON_TARGET530=1)
set_target_properties(promax26_3_runner PROPERTIES
    OUTPUT_NAME promax26_3_history_runner
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/../../build-promax26-3")
