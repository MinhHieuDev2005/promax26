#include "hexudon/internal.hpp"
#ifdef SUBSET_REPAIR
#include "subset_repair.hpp"
#endif
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <iterator>
#include <memory>
#include <random>
#include <sstream>
#include <unordered_map>

using namespace hexudon;
using Clock = std::chrono::steady_clock;
namespace {
ActionPlan parse_plan(const json::value& encoded) {
  ActionPlan plan;
  for (const auto& row : encoded.as_array()) {
    plan.emplace_back();
    for (const auto& a : row.as_array()) plan.back().push_back(a.to_number<int>());
  }
  return plan;
}
struct Node {
  DayInfo day;
  PolicyHistory history;
  std::vector<ActionPlan> plans;
  std::vector<std::map<int, int>> traffic;
  int attempts = 0, fuel = 0;
};
std::string key(const Node& n) {
  std::ostringstream s;
  s << n.day.day << ':' << n.history.cumulative_daily_types;
  for (auto b : n.history.distinct_brands) s << 'b' << b;
  for (auto a : n.day.agents) s << 'a' << a.pos << ',' << a.fuel << ',' << int(a.kind);
  for (auto [p, v] : n.day.traffics) s << 'r' << p << ',' << v;
  for (const auto& t : n.traffic) {
    s << 'h';
    for (auto [p, v] : t) s << p << ',' << v << ';';
  }
  return s.str();
}
std::string geometry(const Node& n) {
  std::ostringstream s;
  for (auto a : n.day.agents) s << a.pos << ',';
  return s.str();
}
}

int main() {
  try {
#ifdef _WIN32
    _putenv_s("HEXUDON_THREADS", "1");
#else
    setenv("HEXUDON_THREADS", "1", 1);
#endif
    const auto begin = Clock::now();
    const auto input = json::parse(std::string{std::istreambuf_iterator<char>(std::cin), {}});
    const auto& root = input.as_object();
    const auto config = parse_map_config(root.at("config"));
    validate_config(config);
    const json::object empty;
    const auto& search = root.if_contains("search") ? root.at("search").as_object() : empty;
    auto integer = [&](const char* name, int fallback) {
      const auto* p = search.if_contains(name); return p ? p->to_number<int>() : fallback;
    };
    int budget = std::clamp(integer("timeLimitMs", 45000), 1, 45000);
    SearchLimits limits;
    limits.time_limit_ms = std::min(2000, budget);
    if (root.if_contains("op") && root.at("op").as_string() == "roles") {
      std::cout << json::serialize(json::object{{"ok", true}, {"roles", to_json(select_agent_types("alns", config, limits))}}) << '\n';
      return 0;
    }
    auto encoded = root.at(root.contains("day_info") ? "day_info" : "state");
    if (!root.contains("day_info")) encoded.as_object()["day"] = encoded.as_object().at("day").to_number<int>() - 1;
    Node initial;
    initial.day = parse_day_info(encoded);
    if (root.if_contains("history")) initial.history = parse_history(root.at("history"));
    AgentTypes types;
    for (auto a : initial.day.agents) types.push_back(a.kind);
    if (initial.day.ends_at) {
      double now = std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
      budget = std::min(budget, std::max(1, int((*initial.day.ends_at - now) * 1000 - 800)));
    }
    if (initial.day.day < 0 || initial.day.day >= int(config.day_steps.size())) throw std::runtime_error("invalid day");
    std::set<int> brands;
    for (auto s : config.spots) brands.insert(s.brand);
    const int required = int(brands.size());
#ifdef DAY_PORTFOLIO
    const int days = 1;
    const char* engine_name = "day_portfolio";
    const int default_slice = 6000;
#else
    const int days = int(config.day_steps.size()) - initial.day.day;
    const char* engine_name = "horizon_portfolio";
    const int default_slice = 800;
#endif
    const int width = std::clamp(integer("layerCapacity", 12), 1, 64);
    const int slice = std::clamp(integer("sliceMs", default_slice), 100, 8000);
    const std::string forecast = search.if_contains("trafficForecast") ? std::string(search.at("trafficForecast").as_string()) : "observed";
    if (forecast != "observed" && forecast != "mirror" && forecast != "idle") throw std::runtime_error("unknown traffic forecast");
    const auto deadline = begin + std::chrono::milliseconds(std::max(1, budget - std::min(3000, budget / 5)));
#ifdef SUBSET_REPAIR
    const auto generator_deadline = deadline - std::chrono::milliseconds(std::min(9000, budget / 3));
#else
    const auto generator_deadline = deadline;
#endif
    auto remaining = [&] { return int(std::chrono::duration_cast<std::chrono::milliseconds>(generator_deadline - Clock::now()).count()); };
    std::mt19937_64 rng(integer("randomSeed", 1));
    int evaluated = 0, rejected = 0, duplicates = 0, expanded = 0, mixed = 0;
    std::map<std::string, int> engine_calls;
    std::optional<Node> best;
    std::vector<std::vector<std::shared_ptr<Node>>> layers(days);
    std::unordered_map<std::string, int> seen;
    int cap = 0;
    const int patrols = int(std::count(types.begin(), types.end(), AgentKind::Patrol));
    for (auto s : config.spots) cap += std::min(s.stocks, patrols);
    auto advance = [&](const Node& parent, const ActionPlan& plan) -> std::optional<Node> {
      ++evaluated;
      const auto e = evaluate_candidate(config, parent.day, parent.history, plan);
      if (!e || std::get<1>(e->value) != required || std::get<0>(e->value) != required) { ++rejected; return {}; }
      Node n = parent;
      n.attempts = 0;
      n.plans.push_back(plan);
      n.history.submitted_actions.push_back(plan);
      n.history.distinct_brands = brands;
      n.history.cumulative_daily_types += required;
      n.history.total_servings += std::get<2>(e->value);
      n.day.day++;
      n.day.ends_at.reset();
      n.day.others.clear();
      n.traffic.push_back(e->road_traffic);
      if (n.traffic.size() > 2) n.traffic.erase(n.traffic.begin());
      if (forecast != "observed") n.day.traffics = road_status_for_day(config, n.traffic, forecast == "idle" ? config.players : 1);
      n.fuel = 0;
      for (std::size_t i = 0; i < types.size(); ++i) {
        n.day.agents[i] = {types[i], e->ending_positions[i], e->ending_fuel[i]};
        if (types[i] == AgentKind::Patrol) n.fuel += e->ending_fuel[i];
      }
      return n;
    };
    auto rank = [](const auto& a, const auto& b) {
      return std::tuple{a->history.total_servings - a->attempts, a->fuel} >
             std::tuple{b->history.total_servings - b->attempts, b->fuel};
    };
    auto push = [&](Node n) {
      const int depth = int(n.plans.size());
      if (depth == days) {
        if (!best || n.history.total_servings > best->history.total_servings) best = std::move(n);
        return;
      }
      if (best && n.history.total_servings + cap * (days - depth) <= best->history.total_servings) return;
      auto k = key(n);
      const auto it = seen.find(k);
      if (it != seen.end() && it->second >= n.history.total_servings) { ++duplicates; return; }
      if (seen.size() > 32768) seen.clear();
      seen[k] = n.history.total_servings;
      auto& layer = layers[depth];
      layer.push_back(std::make_shared<Node>(std::move(n)));
      std::sort(layer.begin(), layer.end(), rank);
      std::map<std::string, int> buckets;
      std::erase_if(layer, [&](const auto& p) { return ++buckets[geometry(*p)] > 2; });
      if (layer.size() > std::size_t(width)) layer.resize(width);
    };
    auto generate = [&](const Node& n, const std::string& engine, int ms, std::vector<ActionPlan>* elites = nullptr) {
      SearchLimits l;
      l.time_limit_ms = std::max(1, std::min(ms, remaining()));
      l.min_iterations = 0; l.max_iterations = 1000000; l.stagnation_iterations = 0;
      l.random_seed = rng(); l.use_lns_dp_proposals = false;
      l.exact_nodes = 0; l.final_exact_nodes = 0;
      ++engine_calls[engine];
      if (engine == "alns_elites")
        return build_alns_plan(config, n.day, n.history, types, l, kProductionAlnsFeatures, false, 0, nullptr, elites);
      return plan_day(engine, config, n.day, n.history, types, l);
    };
    // Online state only: the returned suffix is generated from this input.
    // Equality of config/history is checked; every warm action is resimulated.
    json::object normalized_config = root.at("config").as_object();
    normalized_config.erase("startsAt");
    const std::string fingerprint = json::serialize(normalized_config);
    if (const auto* warm = root.if_contains("planner_state"); warm && warm->is_object()) {
      try {
        const auto& w = warm->as_object();
        if (w.at("fingerprint").as_string() == fingerprint &&
            w.at("source_day").to_number<int>() == initial.day.day - 1 &&
            !initial.history.submitted_actions.empty() &&
            parse_plan(w.at("committed")) == initial.history.submitted_actions.back()) {
          Node n = initial;
          for (const auto& p : w.at("suffix").as_array()) {
            if (int(n.plans.size()) >= days) break;
            auto next = advance(n, parse_plan(p));
            if (!next) break;
            n = *next; push(n);
          }
        }
      } catch (const std::exception&) {}
    }
    push(initial);
    std::vector<ActionPlan> root_routes;
    Node seed = initial;
    const int seed_slice = std::max(200, std::min(days == 1 ? 8000 : 4000, remaining() / std::max(2, days * 2)));
    for (int d = 0; d < days && remaining() > 150; ++d) {
      auto plan = generate(seed, "alns", seed_slice);
      if (d == 0) root_routes.push_back(plan);
      auto child = advance(seed, plan);
      if (!child) break;
      seed = *child; push(seed);
    }
    while (remaining() > 200) {
      bool progress = false;
      for (int depth = 0; depth < days && remaining() > 200; ++depth) {
        auto& layer = layers[depth];
        if (layer.empty()) continue;
        std::sort(layer.begin(), layer.end(), rank);
        auto parent = layer.front(); layer.erase(layer.begin());
        if (parent->attempts >= 8) continue;
        progress = true; ++expanded; ++parent->attempts;
        std::vector<ActionPlan> proposals;
        const std::string engine = parent->attempts % 3 == 1 ? (days == 1 ? "alns" : "alns_elites") : parent->attempts % 3 == 2 ? "aco_ls" : "lns";
        auto plan = generate(*parent, engine, slice, &proposals);
        proposals.insert(proposals.begin(), std::move(plan));
        if (depth == 0) {
          auto fresh = proposals.front();
          for (const auto& old : root_routes) proposals.push_back(old);
          root_routes.push_back(std::move(fresh));
          if (root_routes.size() > 6) root_routes.erase(root_routes.begin());
        }
        if (proposals.size() > 8) proposals.resize(8);
        // Local coordinate set packing; simulation includes rendezvous and
        // stock conflicts, so incompatible combinations are never accepted.
        if (proposals.size() > 1 && remaining() > 800) {
          auto combined = improve_with_route_substitutions(config, parent->day,
              parent->history, proposals.front(), proposals, 2, false);
          proposals.push_back(std::move(combined)); ++mixed;
        }
        if (parent->attempts < 8) layer.push_back(parent);
        for (const auto& plan : proposals) {
          if (remaining() < 50) break;
          if (auto child = advance(*parent, plan)) push(std::move(*child));
        }
      }
      if (!progress) break;
    }
    if (!best) throw std::runtime_error("no complete full-coverage suffix found within budget");
#ifdef SUBSET_REPAIR
    best->plans.front() = horizon_repair::improve(config, initial.day,
        initial.history, types, best->plans.front(), deadline);
    if (auto verified = evaluate_candidate(config, initial.day, initial.history, best->plans.front()))
      best->history.total_servings = initial.history.total_servings + std::get<2>(verified->value);
#endif
    json::array suffix;
    for (std::size_t i = 1; i < best->plans.size(); ++i) suffix.push_back(to_json(best->plans[i]));
    json::object calls;
    for (auto [name, count] : engine_calls) calls[name] = count;
    std::cout << json::serialize(json::object{
      {"ok", true}, {"plan", to_json(best->plans.front())},
      {"planner_state", json::object{{"fingerprint", fingerprint}, {"source_day", initial.day.day},
         {"committed", to_json(best->plans.front())}, {"suffix", suffix}}},
      {"diagnostics", json::object{{"engine", engine_name}, {"forecast", forecast}, {"horizon_days", days},
        {"projected_bowls", best->history.total_servings}, {"expansions", expanded},
        {"evaluated", evaluated}, {"rejected", rejected}, {"duplicates", duplicates},
        {"route_pool_calls", mixed}, {"engine_calls", calls},
        {"elapsed_ms", std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-begin).count()}}}}) << '\n';
  } catch (const std::exception& e) {
    std::cout << json::serialize(json::object{{"ok", false}, {"error", e.what()}}) << '\n';
    return 1;
  }
}
