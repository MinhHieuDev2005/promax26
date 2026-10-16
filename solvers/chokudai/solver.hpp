#pragma once
#include "hexudon/internal.hpp"
#include <chrono>

namespace udon_chokudai {
struct Options {
  int time_ms{3000};
  int seed_percent{30};
  int depth{6};
  int layer_capacity{96};
  int branching{18};
  int max_expansions{1000000};
  std::uint64_t seed{1};
};
struct Diagnostics {
  int expansions{}, evaluated{}, duplicates{}, sweeps{}, restarts{}, improvements{};
  int peak_frontier{};
  long long elapsed_ms{};
};
struct Result {
  hexudon::ActionPlan actions;
  hexudon::CandidateValue value, baseline;
  Diagnostics diagnostics;
};
// Componentwise protection of criteria 1 and 2, followed by official ordering.
bool admissible_improvement(const hexudon::CandidateValue& next,
                            const hexudon::CandidateValue& previous);
Result solve(const hexudon::MapConfig&, const hexudon::DayInfo&,
             const hexudon::PolicyHistory&, const hexudon::AgentTypes&,
             const Options& = {});
}
