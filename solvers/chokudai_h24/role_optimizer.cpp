#include "hexudon/internal.hpp"

#include <algorithm>
#include <bit>
#include <chrono>
#include <fstream>
#include <future>
#include <iostream>
#include <iterator>
#include <set>
#include <stdexcept>
#include <tuple>
#include <vector>

using namespace hexudon;

namespace {

struct Result {
  AgentTypes roles;
  int distinct{};
  int daily{};
  int servings{};
  std::vector<int> daily_types;
  std::vector<int> daily_servings;
  long long elapsed_ms{};
};

Result forecast(const MapConfig& config, AgentTypes roles, int per_day_ms,
                std::uint64_t seed) {
  const auto started = std::chrono::steady_clock::now();
  TeamState team;
  team.id = "role-forecast";
  for (std::size_t i = 0; i < roles.size(); ++i)
    team.agents.push_back({roles[i], config.agents[i], config.fuel_limit});
  std::vector<std::map<int, int>> traffic_history;
  Result result;
  result.roles = roles;
  for (int day_index = 0; day_index < static_cast<int>(config.day_steps.size()); ++day_index) {
    const auto roads = road_status_for_day(config, traffic_history, 1);
    DayInfo day;
    day.day = day_index;
    day.traffics = roads;
    for (const auto& agent : team.agents)
      day.agents.push_back({agent.kind, agent.pos, agent.fuel});
    SearchLimits limits;
    limits.time_limit_ms = per_day_ms;
    limits.min_iterations = 0;
    limits.max_iterations = 1000000;
    limits.stagnation_iterations = 0;
    limits.random_seed = seed;
    const auto plan = plan_day("alns", config, day, team.history, roles, limits);
    team.stock.clear();
    team.visited_today.assign(roles.size(), {});
    team.daily_types.clear();
    for (const auto& spot : config.spots) team.stock[spot.pos] = spot.stocks;
    std::map<int, int> traffic;
    const int before = team.total_servings;
    if (auto error = simulate_team_day(config, team, plan, roads, traffic))
      throw std::runtime_error(*error);
    team.cumulative_daily_types += static_cast<int>(team.daily_types.size());
    team.history.submitted_actions.push_back(plan);
    team.history.distinct_brands = team.distinct_types;
    team.history.cumulative_daily_types = team.cumulative_daily_types;
    team.history.total_servings = team.total_servings;
    traffic_history.push_back(std::move(traffic));
    result.daily_types.push_back(static_cast<int>(team.daily_types.size()));
    result.daily_servings.push_back(team.total_servings - before);
  }
  result.distinct = static_cast<int>(team.distinct_types.size());
  result.daily = team.cumulative_daily_types;
  result.servings = team.total_servings;
  result.elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now() - started).count();
  return result;
}

json::array integer_array(const std::vector<int>& values) {
  json::array output;
  for (int value : values) output.push_back(value);
  return output;
}

json::object to_json_result(const Result& result, int required) {
  return {{"roles", to_json(result.roles)},
          {"score", json::array{result.distinct, result.daily, result.servings}},
          {"coverage", result.distinct == required &&
                           result.daily == required * static_cast<int>(result.daily_types.size())},
          {"daily_types", integer_array(result.daily_types)},
          {"daily_servings", integer_array(result.daily_servings)},
          {"elapsed_ms", result.elapsed_ms}};
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 3 || argc > 6)
      throw std::invalid_argument(
          "usage: role_optimizer scenario.json per_day_ms [output.json] [seed] [profile|shortlist|exhaustive|sequential]");
    std::ifstream stream(argv[1]);
    if (!stream) throw std::invalid_argument("scenario not readable");
    const std::string contents{std::istreambuf_iterator<char>(stream), {}};
    const auto root = json::parse(contents).as_object();
    const auto config = parse_map_config(root.contains("config") ? root.at("config") : root);
    const int per_day_ms = std::stoi(argv[2]);
    if (per_day_ms < 1 || per_day_ms > 60000)
      throw std::invalid_argument("per_day_ms must be 1..60000");
    const std::uint64_t seed = argc >= 5 ? std::stoull(argv[4]) : 1;
    const std::string mode = argc == 6 ? argv[5] : "shortlist";
    if (mode != "profile" && mode != "shortlist" && mode != "exhaustive" &&
        mode != "sequential")
      throw std::invalid_argument("unknown optimization mode");
    if (config.agents.size() > 16)
      throw std::invalid_argument("exhaustive role optimization supports at most 16 agents");

    std::vector<AgentTypes> candidates;
    const std::uint64_t combinations = std::uint64_t{1} << config.agents.size();
    auto append_mask = [&](std::uint64_t mask) {
      AgentTypes roles(config.agents.size(), AgentKind::Patrol);
      for (std::size_t i = 0; i < roles.size(); ++i)
        if (mask & (std::uint64_t{1} << i)) roles[i] = AgentKind::Refuel;
      if (std::find(candidates.begin(), candidates.end(), roles) == candidates.end())
        candidates.push_back(std::move(roles));
    };
    if (mode == "profile") {
      if (config.width != config.height ||
          (config.width != 16 && config.width != 24 && config.width != 32))
        throw std::invalid_argument("profile mode requires a 16x16, 24x24, or 32x32 board");
      const int refuel_cap = config.width == 16 ? 1 : (config.width == 24 ? 2 : 3);
      for (std::uint64_t mask = 0; mask + 1 < combinations; ++mask)
        if (std::popcount(mask) <= refuel_cap) append_mask(mask);
    } else if (mode == "exhaustive") {
      for (std::uint64_t mask = 0; mask + 1 < combinations; ++mask) append_mask(mask);
    } else {
      append_mask(0);
      for (std::size_t i = 0; i < config.agents.size(); ++i)
        append_mask(std::uint64_t{1} << i);
      SearchLimits role_limits;
      role_limits.time_limit_ms = std::min(800, per_day_ms);
      const auto legacy = select_agent_types("alns", config, role_limits);
      std::uint64_t legacy_mask = 0;
      for (std::size_t i = 0; i < legacy.size(); ++i)
        if (legacy[i] == AgentKind::Refuel) legacy_mask |= std::uint64_t{1} << i;
      append_mask(legacy_mask);
    }
    std::vector<Result> results;
    if (mode == "profile") {
      const int screen_ms = std::max(100, std::min(500, per_day_ms / 4));
      std::vector<std::future<Result>> screens;
      for (const auto& roles : candidates)
        screens.push_back(std::async(std::launch::async, forecast, std::cref(config),
                                     roles, screen_ms, seed));
      std::vector<Result> screened;
      for (auto& future : screens) screened.push_back(future.get());
      std::sort(screened.begin(), screened.end(), [](const Result& left, const Result& right) {
        return std::tie(left.distinct, left.daily, left.servings) >
               std::tie(right.distinct, right.daily, right.servings);
      });
      std::vector<AgentTypes> finalists;
      auto retain = [&](const AgentTypes& roles) {
        if (std::find(finalists.begin(), finalists.end(), roles) == finalists.end())
          finalists.push_back(roles);
      };
      std::map<int, int> retained_by_count;
      for (const auto& candidate : screened) {
        const int refuelers = static_cast<int>(std::count(
            candidate.roles.begin(), candidate.roles.end(), AgentKind::Refuel));
        if (refuelers == 1 || retained_by_count[refuelers] < 2) {
          retain(candidate.roles);
          ++retained_by_count[refuelers];
        }
      }
      for (const auto& roles : finalists) {
        results.push_back(forecast(config, roles, per_day_ms, seed));
        std::cerr << "verified " << json::serialize(to_json(roles)) << " score="
                  << results.back().distinct << '/' << results.back().daily << '/'
                  << results.back().servings << '\n';
      }
    } else if (mode == "sequential") {
      for (const auto& roles : candidates) {
        results.push_back(forecast(config, roles, per_day_ms, seed));
        std::cerr << "verified " << json::serialize(to_json(roles)) << " score="
                  << results.back().distinct << '/' << results.back().daily << '/'
                  << results.back().servings << '\n';
      }
    } else {
      std::vector<std::future<Result>> futures;
      for (const auto& roles : candidates)
        futures.push_back(std::async(std::launch::async, forecast, std::cref(config),
                                     roles, per_day_ms, seed));
      for (auto& future : futures) results.push_back(future.get());
    }
    std::sort(results.begin(), results.end(), [](const Result& left, const Result& right) {
      return std::tie(left.distinct, left.daily, left.servings) >
             std::tie(right.distinct, right.daily, right.servings);
    });
    std::set<int> brands;
    for (const auto& spot : config.spots) brands.insert(spot.brand);
    json::array rows;
    for (const auto& result : results)
      rows.push_back(to_json_result(result, static_cast<int>(brands.size())));
    const auto output = json::object{
        {"ok", true}, {"algorithm", mode == "profile"
            ? "board-profile screen + sequential full-match ALNS verification"
            : (mode == "exhaustive"
            ? "exhaustive role masks + full-match ALNS forecast"
            : (mode == "sequential"
                ? "sequential fair verification of one-refuel masks + guards"
                : "all one-refuel masks + all-patrol + legacy guard; full-match ALNS forecast"))},
        {"mode", mode},
        {"per_day_ms", per_day_ms}, {"seed", seed},
        {"roles", to_json(results.front().roles)},
        {"best_score", json::array{results.front().distinct, results.front().daily,
                                    results.front().servings}},
        {"candidates", std::move(rows)}};
    const auto serialized = json::serialize(output) + "\n";
    if (argc >= 4) {
      std::ofstream file(argv[3]);
      if (!file) throw std::runtime_error("cannot write output");
      file << serialized;
    }
    std::cout << serialized;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
