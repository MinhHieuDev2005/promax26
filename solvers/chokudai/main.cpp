#include "solver.hpp"
#include <algorithm>
#include <chrono>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

using namespace hexudon;
namespace {
int integer(const json::object& o, const char* key, int fallback) {
  const auto* v = o.if_contains(key);
  return v ? v->to_number<int>() : fallback;
}
json::array triple(const CandidateValue& v) {
  return {std::get<0>(v), std::get<1>(v), std::get<2>(v)};
}
json::object diagnostics(const udon_chokudai::Result& r) {
  const auto& d = r.diagnostics;
  return {{"baseline_score", triple(r.baseline)}, {"score", triple(r.value)},
          {"elapsed_ms", d.elapsed_ms}, {"expansions", d.expansions},
          {"evaluated", d.evaluated}, {"duplicates", d.duplicates},
          {"sweeps", d.sweeps}, {"restarts", d.restarts},
          {"improvements", d.improvements}, {"peak_frontier", d.peak_frontier}};
}
}
int main(int argc, char** argv) {
  try {
    int override_ms = -1;
    if (argc == 3 && std::string(argv[1]) == "--time-ms") override_ms = std::stoi(argv[2]);
    else if (argc != 1) throw std::invalid_argument("usage: chokudai_runner [--time-ms 1..50000]");
    std::string input{std::istreambuf_iterator<char>(std::cin), {}};
    const auto root_value = json::parse(input);
    const auto& root = root_value.as_object();
    auto config = parse_map_config(root.at("config"));
    const auto* op_value = root.if_contains("op");
    const std::string op = op_value ? std::string(op_value->as_string()) : "plan";
    const json::object empty;
    const auto* search_value = root.if_contains("search");
    const auto& search = search_value ? search_value->as_object() : empty;
    udon_chokudai::Options options;
    options.time_ms = integer(search, "timeLimitMs", integer(search, "time_limit_ms", 3000));
    if (override_ms != -1) options.time_ms = override_ms;
    options.depth = integer(search, "depth", options.depth);
    options.layer_capacity = integer(search, "layerCapacity", options.layer_capacity);
    options.branching = integer(search, "branching", options.branching);
    options.seed_percent = integer(search, "seedPercent", options.seed_percent);
    options.max_expansions = integer(search, "maxExpansions", options.max_expansions);
    options.seed = static_cast<std::uint64_t>(integer(search, "randomSeed", 1));
    if (options.time_ms < 1 || options.time_ms > 50000)
      throw std::invalid_argument("timeLimitMs must be 1..50000");
    if (op == "roles") {
      SearchLimits limits;
      limits.time_limit_ms = std::min(2500, options.time_ms);
      limits.min_iterations = 0;
      limits.max_iterations = 256;
      auto roles = select_agent_types("alns", config, limits);
      std::cout << json::serialize(json::object{{"ok", true}, {"roles", to_json(roles)}}) << '\n';
      return 0;
    }
    if (op != "plan") throw std::invalid_argument("supported operations: roles, plan");
    // Native day_info is zero-based; the GUI JSON-runner state is one-based.
    const bool runner_protocol = root.if_contains("day_info") == nullptr;
    auto day_value = root.at(runner_protocol ? "state" : "day_info");
    if (runner_protocol) {
      auto& state = day_value.as_object();
      state["day"] = state.at("day").to_number<int>() - 1;
    }
    const auto day = parse_day_info(day_value);
    AgentTypes types;
    if (const auto* supplied = root.if_contains("types")) {
      for (const auto& v : supplied->as_array()) types.push_back(static_cast<AgentKind>(v.to_number<int>()));
    } else for (const auto& a : day.agents) types.push_back(a.kind);
    const auto* h = root.if_contains("history");
    const auto history = h ? parse_history(*h) : PolicyHistory{};
    if (day.ends_at) {
      const double now = std::chrono::duration<double>(
          std::chrono::system_clock::now().time_since_epoch()).count();
      const double safe_ms = (*day.ends_at - now) * 1000.0 - 500.0;
      if (safe_ms < 1) throw std::invalid_argument("day deadline already passed or too close");
      if (safe_ms < options.time_ms) options.time_ms = static_cast<int>(safe_ms);
    }
    const auto result = udon_chokudai::solve(config, day, history, types, options);
    std::cout << json::serialize(json::object{
        {"ok", true}, {"plan", to_json(result.actions)},
        {"diagnostics", diagnostics(result)}, {"history_supplied", h != nullptr},
        {"objective", "protect_distinct_and_daily_then_maximize_servings"}}) << '\n';
  } catch (const std::exception& e) {
    std::cout << json::serialize(json::object{{"ok", false}, {"error", e.what()}}) << '\n';
    return 1;
  }
}
