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
inline int restart_slice_ms(int width,int height) {
  if(width!=height)return 0;
  if(width==16)return 2500;
  if(width==24)return 4500;
  // 32x32 multi-start regressed the full-match baseline; keep proven ALNS.
  if(width==32)return 0;
  return 0;
}
}
