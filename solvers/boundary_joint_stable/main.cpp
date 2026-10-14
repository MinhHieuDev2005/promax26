#include "../boundary_joint/route_pool.hpp"
#include "../boundary_joint/config.hpp"
#include "../boundary_joint/boundary_search.hpp"
#include <cstdlib>
#include <iostream>
#include <iterator>

using namespace boundary_joint;

namespace {
ActionPlan parse_plan(const json::value& value) {
  ActionPlan plan;
  for (const auto& row : value.as_array()) {
    plan.emplace_back();
    for (const auto& action : row.as_array())
      plan.back().push_back(action.to_number<int>());
  }
  return plan;
}

auto official_value(const CandidateEvaluation& evaluation) {
  return std::tuple{std::get<0>(evaluation.value),
                    std::get<1>(evaluation.value),
                    std::get<2>(evaluation.value)};
}

bool better(const Candidate& challenger, const Candidate& incumbent) {
  const auto a = official_value(challenger.eval);
  const auto b = official_value(incumbent.eval);
  return a > b || (a == b && challenger.plan < incumbent.plan);
}
} // namespace

int main() {
  try {
#ifdef _WIN32
    _putenv_s("HEXUDON_THREADS", "1");
#else
    setenv("HEXUDON_THREADS", "1", 1);
#endif
    const auto started = Clock::now();
    const auto input = json::parse(std::string{std::istreambuf_iterator<char>(std::cin), {}});
    const auto& root = input.as_object();
    const auto config = parse_map_config(root.at("config"));
    validate_config(config);
    const json::object empty;
    const auto& search = root.if_contains("search") ? root.at("search").as_object() : empty;
    auto integer = [&](const char* key, int fallback) {
      const auto* value = search.if_contains(key);
      return value ? value->to_number<int>() : fallback;
    };
    const int budget = std::clamp(integer("timeLimitMs", 45000), 1, 45000);
    if (root.if_contains("op") && root.at("op").as_string() == "roles") {
      SearchLimits limits;
      limits.time_limit_ms = std::min(2000, budget);
      std::cout << json::serialize(json::object{{"ok", true},
        {"roles", to_json(select_agent_types("alns", config, limits))}}) << '\n';
      return 0;
    }
    auto encoded = root.at(root.contains("day_info") ? "day_info" : "state");
    if (!root.contains("day_info"))
      encoded.as_object()["day"] = encoded.as_object().at("day").to_number<int>() - 1;
    const auto day = parse_day_info(encoded);
    const auto history = root.if_contains("history") ? parse_history(root.at("history")) : PolicyHistory{};
    if (day.day < 0 || day.day >= int(config.day_steps.size()) ||
        day.agents.size() != config.agents.size())
      throw std::runtime_error("invalid day/agents");
    int usable_budget = budget;
    if (day.ends_at) {
      const double now = std::chrono::duration<double>(
        std::chrono::system_clock::now().time_since_epoch()).count();
      usable_budget = std::min(usable_budget, std::max(1, int((*day.ends_at - now) * 1000) - 900));
    }
    const auto deadline = started + std::chrono::milliseconds(
      std::max(1, usable_budget - std::min(3000, usable_budget / 5)));
    auto left = [&] {
      return int(std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count());
    };
    AgentTypes types;
    for (const auto& agent : day.agents) types.push_back(agent.kind);

    // Independent, reproducible starts reduce dependence on one ALNS trajectory.
    // The official tuple, never the heuristic's internal tie breakers, owns adoption.
    const int starts = std::clamp(integer("stableStarts", 3), 1, 4);
    // A stable policy uses a fixed restart portfolio. The caller's randomSeed
    // deliberately does not change the answer; stableBaseSeed is an explicit
    // opt-in for experiments with a different portfolio.
    const int seed = integer("stableBaseSeed", 1);
    const int baseline_ms = std::clamp(integer("baselineMs", 12000), 1, 20000);
    Candidate winner;
    int completed_starts = 0;
    for (int i = 0; i < starts && left() > 1500; ++i) {
      SearchLimits limits;
      limits.time_limit_ms = std::max(1, std::min(baseline_ms, left() / (starts - i + 1)));
      limits.random_seed = std::uint64_t(seed) + std::uint64_t(i) * 0x9e3779b97f4a7c15ULL;
      limits.min_iterations = 0;
      limits.max_iterations = 1000000;
      limits.stagnation_iterations = 0;
      limits.alns_restarts = 1;
      auto plan = plan_day("alns", config, day, history, types, limits);
      auto evaluation = evaluate_candidate(config, day, history, plan);
      if (!evaluation) throw std::runtime_error("ALNS returned invalid plan");
      Candidate candidate{std::move(plan), *evaluation, "alns"};
      if (!completed_starts || better(candidate, winner)) winner = std::move(candidate);
      ++completed_starts;
    }
    if (!completed_starts) throw std::runtime_error("no baseline start completed");
    const auto baseline_done = Clock::now();
    Stats stats;
    const auto profile = configuration(config.width * config.height);
    if (integer("enablePool", 1) && left() > 1500 &&
        int(config.spots.size()) <= profile.subset_target_limit) {
      const auto candidates = improve(config, day, history, winner.plan,
        deadline, stats, std::clamp(integer("poolCapacity", profile.route_capacity), 8, 128),
        false, std::clamp(integer("endpointQuota", 3), 0, 6), 0);
      for (const auto& candidate : candidates)
        if (better(candidate, winner)) winner = candidate;
    }
    BoundaryStats tail_stats;
    if (integer("enableTailSearch", 1) && left() > 2000) {
      const auto until = std::min(deadline, Clock::now() +
        std::chrono::milliseconds(std::min(3500, left() - 500)));
      const auto candidates = boundary_search(config, day, history, winner, until, tail_stats);
      for (const auto& candidate : candidates)
        if (better(candidate, winner)) winner = candidate;
    }
    std::set<int> brands;
    for (const auto& spot : config.spots) brands.insert(spot.brand);
    std::cout << json::serialize(json::object{{"ok", true}, {"plan", to_json(winner.plan)},
      {"planner_state", nullptr}, {"diagnostics", json::object{
        {"engine", "boundary_joint_stable_v1"}, {"selected", winner.origin},
        {"completed_starts", completed_starts},
        {"coverage_complete", std::get<0>(winner.eval.value) == int(brands.size()) &&
          std::get<1>(winner.eval.value) == int(brands.size())},
        {"official_c1", std::get<0>(winner.eval.value)},
        {"official_c2", std::get<1>(winner.eval.value)},
        {"official_c3", std::get<2>(winner.eval.value)},
        {"candidate_count", stats.candidate_count}, {"validated", stats.validated},
        {"tail_generated", tail_stats.generated},
        {"baseline_ms", std::chrono::duration_cast<std::chrono::milliseconds>(baseline_done - started).count()},
        {"elapsed_ms", std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - started).count()}
      }}}) << '\n';
  } catch (const std::exception& error) {
    std::cout << json::serialize(json::object{{"ok", false}, {"error", error.what()}}) << '\n';
    return 1;
  }
}
