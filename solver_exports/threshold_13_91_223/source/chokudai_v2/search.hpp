#pragma once
#include "hexudon/internal.hpp"

namespace chokudai_v2 {
struct Options {
  int time_ms=20000, slice_ms=250, width=24, attempts=6, max_expansions=100000;
  bool use_elites=true, use_warm=true, use_route_dp=true, use_strong_seed=true;
  bool exhaust_budget=false;
  std::uint64_t seed=1;
};
struct Result {
  hexudon::ActionPlan actions;
  hexudon::json::object state, diagnostics;
};
Result solve(const hexudon::MapConfig&, const hexudon::DayInfo&,
             const hexudon::PolicyHistory&, const hexudon::AgentTypes&,
             const Options&, const hexudon::json::value* warm=nullptr);
}
