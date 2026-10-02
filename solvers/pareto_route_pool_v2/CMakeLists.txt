cmake_minimum_required(VERSION 3.20)
project(hexudon_pareto_route_pool_v2 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
file(READ
  "${CMAKE_CURRENT_SOURCE_DIR}/../../solver_learning/runs/u25-prpv2-suffix303-staging-pareto_route_pool_v2-3000-6.json"
  PARETO_ROUTE_POOL_V2_ELITE_JSON)
configure_file(elite_run.hpp.in generated/elite_run.hpp @ONLY)
add_subdirectory(../.. legacy EXCLUDE_FROM_ALL)
add_library(pareto_route_pool_v2_chokudai
  ../chokudai_v2/search.cpp
  ../chokudai_v2/route_dp.cpp)
target_include_directories(pareto_route_pool_v2_chokudai PUBLIC ../chokudai_v2)
target_link_libraries(pareto_route_pool_v2_chokudai PUBLIC hexudon_core)
add_executable(pareto_route_pool_v2_runner main.cpp)
target_include_directories(pareto_route_pool_v2_runner PRIVATE
  "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_link_libraries(pareto_route_pool_v2_runner PRIVATE
  hexudon_core pareto_route_pool_v2_chokudai)
if(MINGW)
  target_link_options(pareto_route_pool_v2_runner PRIVATE -static)
endif()
