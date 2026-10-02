#pragma once
#include <algorithm>
namespace boundary_joint {
// Conservative experimental presets, NOT claimed to be statistically tuned.
// Raw 25x25 inputs are supported: choose by area, never by an exact map hash.
struct SolverConfig {
  const char* profile;
  int route_capacity;
  int subset_target_limit;
};
inline SolverConfig configuration(int cells) {
  if(cells<=256)return {"small",96,20};
  if(cells<=625)return {"medium",80,20};
  return {"large",48,18};
}
}
