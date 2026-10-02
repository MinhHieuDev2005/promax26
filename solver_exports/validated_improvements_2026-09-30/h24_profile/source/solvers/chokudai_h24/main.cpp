#include "search.hpp"
#include <algorithm>
#include <chrono>
#include <iostream>
#include <iterator>
#include <stdexcept>

using namespace hexudon;

namespace {

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
    const auto& search = root.if_contains("search") ? root.at("search").as_object() : empty;
    auto integer = [&](const char* key, int fallback) {
      const auto value = search.if_contains(key);
      return value ? value->to_number<int>() : fallback;
    };
    chokudai_v2::Options options;
    options.time_ms = integer("timeLimitMs", 20000);
    options.slice_ms = integer("sliceMs", 250);
    options.width = integer("layerCapacity", 24);
    options.attempts = integer("attempts", 6);
    options.max_expansions = integer("maxExpansions", 100000);
    const int seed = integer("randomSeed", 1);
    if (seed < 0) throw std::invalid_argument("negative seed");
    options.seed = seed;
    if (auto p = search.if_contains("useElites")) options.use_elites = p->as_bool();
    if (auto p = search.if_contains("useWarm")) options.use_warm = p->as_bool();
    if (auto p = search.if_contains("useRouteDp")) options.use_route_dp = p->as_bool();
    if (auto p = search.if_contains("useStrongSeed")) options.use_strong_seed = p->as_bool();
    if (auto p = search.if_contains("exhaustBudget")) options.exhaust_budget = p->as_bool();
    if (options.time_ms < 1 || options.time_ms > 60000)
      throw std::invalid_argument("budget must be 1..60000ms");
    if (auto p = root.if_contains("op"); p && p->as_string() == "roles") {
      const auto types = throughput_roles(config, options.time_ms);
      std::cout << json::serialize(json::object{{"ok", true}, {"roles", to_json(types)}}) << '\n';
      return 0;
    }
    if (auto p = root.if_contains("op"); p && p->as_string() != "plan")
      throw std::invalid_argument("unsupported op");
    const bool native = root.contains("day_info");
    auto state = root.at(native ? "day_info" : "state");
    if (!native) state.as_object()["day"] = state.as_object().at("day").to_number<int>() - 1;
    const auto day = parse_day_info(state);
    AgentTypes types;
    for (const auto& agent : day.agents) types.push_back(agent.kind);
    if (auto p = root.if_contains("types")) {
      AgentTypes supplied;
      for (const auto& item : p->as_array())
        supplied.push_back(static_cast<AgentKind>(item.to_number<int>()));
      if (supplied != types) throw std::invalid_argument("types mismatch");
    }
    auto history = root.if_contains("history") ? parse_history(root.at("history")) : PolicyHistory{};
    if (day.ends_at) {
      const double now = std::chrono::duration<double>(
          std::chrono::system_clock::now().time_since_epoch()).count();
      const double left = (*day.ends_at - now) * 1000 - 500;
      if (left < 1) throw std::invalid_argument("expired deadline");
      if (left < options.time_ms) options.time_ms = static_cast<int>(left);
    }
    SearchLimits limits;
    limits.time_limit_ms = options.time_ms;
    limits.min_iterations = integer("minIterations", 0);
    limits.max_iterations = integer("maxIterations", 1000000);
    limits.stagnation_iterations = integer("stagnationIterations", 0);
    limits.random_seed = static_cast<std::uint64_t>(seed);
    const auto plan = plan_day("alns", config, day, history, types, limits);
    std::cout << json::serialize(json::object{
        {"ok", true}, {"plan", to_json(plan)},
        {"planner_state", nullptr},
        {"diagnostics", json::object{{"engine", "production_alns"},
                                      {"role_policy", "at_most_one_refuel"}}},
        {"forecast", "self-traffic; future roads are predictions, not observations"}}) << '\n';
  } catch (const std::exception& error) {
    std::cout << json::serialize(json::object{{"ok", false}, {"error", error.what()}}) << '\n';
    return 1;
  }
}
