#include "hexudon/core.hpp"

#include <algorithm>
#include <chrono>
#include <iostream>
#include <iterator>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace hexudon;

namespace {

struct Candidate {
  ActionPlan plan;
  int daily_types{-1};
  int servings{-1};
  int ending_fuel{-1};
  int seed{};
};

bool better(const Candidate& left, const Candidate& right, int required_types) {
  const bool left_feasible = left.daily_types == required_types;
  const bool right_feasible = right.daily_types == required_types;
  if (left_feasible != right_feasible) return left_feasible;
  if (left.daily_types != right.daily_types) return left.daily_types > right.daily_types;
  if (left.servings != right.servings) return left.servings > right.servings;
  if (left.ending_fuel != right.ending_fuel) return left.ending_fuel > right.ending_fuel;
  return left.seed < right.seed;
}

int ending_patrol_fuel(const json::value& trace) {
  const auto& root = trace.as_object();
  if (!root.at("valid").as_bool()) return -1;
  const auto& frames = root.at("frames").as_array();
  if (frames.empty()) return -1;
  int total = 0;
  for (const auto& encoded : frames.back().as_object().at("agents").as_array()) {
    const auto& agent = encoded.as_object();
    if (agent.at("type").to_number<int>() == static_cast<int>(AgentKind::Patrol))
      total += agent.at("fuel").to_number<int>();
  }
  return total;
}

AgentTypes throughput_roles(const MapConfig& config, int time_ms) {
  SearchLimits limits;
  limits.time_limit_ms = std::min(2500, time_ms);
  auto types = select_agent_types("alns", config, limits);
  bool retained_refuel = false;
  for (auto& type : types) {
    if (type != AgentKind::Refuel) continue;
    if (!retained_refuel) retained_refuel = true;
    else type = AgentKind::Patrol;
  }
  return types;
}

}  // namespace

int main() {
  try {
    const std::string input{std::istreambuf_iterator<char>(std::cin), {}};
    const auto value = json::parse(input);
    const auto& root = value.as_object();
    const auto config = parse_map_config(root.at("config"));
    const json::object empty;
    const auto& search = root.if_contains("search")
                             ? root.at("search").as_object()
                             : empty;
    auto integer = [&](const char* key, int fallback) {
      const auto* encoded = search.if_contains(key);
      return encoded ? encoded->to_number<int>() : fallback;
    };
    int time_ms = integer("timeLimitMs", 45000);
    const int base_seed = integer("randomSeed", 1);
    int starts = std::clamp(integer("portfolioStarts", 4), 1, 12);
    if (time_ms < 1 || time_ms > 45000)
      throw std::invalid_argument("budget must be 1..45000ms");
    if (base_seed < 0) throw std::invalid_argument("negative seed");

    if (const auto* op = root.if_contains("op"); op && op->as_string() == "roles") {
      const auto types = throughput_roles(config, time_ms);
      std::cout << json::serialize(json::object{{"ok", true},
                                                {"roles", to_json(types)}})
                << '\n';
      return 0;
    }
    if (const auto* op = root.if_contains("op"); op && op->as_string() != "plan")
      throw std::invalid_argument("unsupported op");

    const bool native = root.contains("day_info");
    auto state = root.at(native ? "day_info" : "state");
    if (!native)
      state.as_object()["day"] = state.as_object().at("day").to_number<int>() - 1;
    const auto day = parse_day_info(state);
    AgentTypes types;
    for (const auto& agent : day.agents) types.push_back(agent.kind);
    if (const auto* supplied = root.if_contains("types")) {
      AgentTypes requested;
      for (const auto& item : supplied->as_array())
        requested.push_back(static_cast<AgentKind>(item.to_number<int>()));
      if (requested != types) throw std::invalid_argument("types mismatch");
    }
    const auto history = root.if_contains("history")
                             ? parse_history(root.at("history"))
                             : PolicyHistory{};
    if (day.ends_at) {
      const double now = std::chrono::duration<double>(
          std::chrono::system_clock::now().time_since_epoch()).count();
      time_ms = std::min(time_ms,
                         std::max(1, static_cast<int>((*day.ends_at - now) * 1000 - 700)));
    }
    if (time_ms < 1200) starts = 1;
    else starts = std::min(starts, std::max(1, time_ms / 1200));
    const int reserve_ms = std::min(700, std::max(100, time_ms / 20));
    const int usable_ms = std::max(1, time_ms - reserve_ms);
    const int required_types = static_cast<int>(
        [&] { std::set<int> brands; for (const auto& spot : config.spots)
              brands.insert(spot.brand); return brands; }().size());

    Candidate best;
    json::array diagnostics;
    const auto started = std::chrono::steady_clock::now();
    for (int index = 0; index < starts; ++index) {
      const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now() - started).count();
      const int remaining = usable_ms - static_cast<int>(elapsed);
      if (remaining <= 0) break;
      SearchLimits limits;
      // Preserve one production-strength incumbent. Equal splitting made all
      // starts too weak on coverage-constrained maps; later starts are the
      // exploration budget, not replacements for the strong floor.
      if (index == 0 && starts > 1)
        limits.time_limit_ms = std::max(1, usable_ms * 70 / 100);
      else
        limits.time_limit_ms = std::max(1, remaining / (starts - index));
      limits.min_iterations = 0;
      limits.max_iterations = 1000000;
      limits.stagnation_iterations = 0;
      limits.random_seed = static_cast<std::uint64_t>(base_seed + index * 104729);
      Candidate candidate;
      candidate.seed = static_cast<int>(limits.random_seed);
      candidate.plan = plan_day("alns", config, day, history, types, limits);
      const auto score = score_action_plan(config, day, history, candidate.plan);
      if (!score) continue;
      candidate.daily_types = score->cumulative_daily_types;
      candidate.servings = score->total_servings;
      candidate.ending_fuel = ending_patrol_fuel(
          trace_action_plan(config, day, history, candidate.plan));
      diagnostics.push_back(json::object{{"seed", candidate.seed},
                                         {"daily_types", candidate.daily_types},
                                         {"servings", candidate.servings},
                                         {"ending_fuel", candidate.ending_fuel},
                                         {"slice_ms", limits.time_limit_ms}});
      if (best.daily_types < 0 || better(candidate, best, required_types))
        best = std::move(candidate);
    }
    if (best.daily_types < 0) throw std::runtime_error("portfolio found no valid plan");
    std::cout << json::serialize(json::object{
        {"ok", true}, {"plan", to_json(best.plan)}, {"planner_state", nullptr},
        {"diagnostics", json::object{{"engine", "feasibility_first_alns_portfolio"},
                                      {"selected_seed", best.seed},
                                      {"daily_types", best.daily_types},
                                      {"servings", best.servings},
                                      {"ending_fuel", best.ending_fuel},
                                      {"candidates", std::move(diagnostics)}}},
        {"forecast", "portfolio is current-day exact; cross-day diversity is experimental"}})
              << '\n';
  } catch (const std::exception& error) {
    std::cout << json::serialize(json::object{{"ok", false}, {"error", error.what()}})
              << '\n';
    return 1;
  }
}
