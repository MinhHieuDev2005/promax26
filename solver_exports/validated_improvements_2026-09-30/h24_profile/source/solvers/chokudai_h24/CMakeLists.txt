cmake_minimum_required(VERSION 3.20)
project(hexudon_chokudai_h24 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
add_subdirectory(../.. legacy EXCLUDE_FROM_ALL)
add_library(chokudai_h24_search
  ../chokudai_v2/search.cpp
  ../chokudai_v2/route_dp.cpp
)
target_link_libraries(chokudai_h24_search PUBLIC hexudon_core)
target_include_directories(chokudai_h24_search PUBLIC ../chokudai_v2)
add_executable(chokudai_h24_runner main.cpp)
target_link_libraries(chokudai_h24_runner PRIVATE chokudai_h24_search)
add_executable(chokudai_h24_role_optimizer role_optimizer.cpp)
target_link_libraries(chokudai_h24_role_optimizer PRIVATE hexudon_core)
if(MINGW)
  target_link_options(chokudai_h24_runner PRIVATE -static)
  target_link_options(chokudai_h24_role_optimizer PRIVATE -static)
endif()
