#include "solver.hpp"
#include <algorithm>
#include <numeric>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unordered_set>

namespace udon_chokudai {
using namespace hexudon;
using Clock = std::chrono::steady_clock;

bool admissible_improvement(const CandidateValue& next, const CandidateValue& previous) {
  return std::get<0>(next) >= std::get<0>(previous) &&
         std::get<1>(next) >= std::get<1>(previous) && next > previous;
}

namespace {
LnsSkeleton lns_skeleton_from_trace(const MapConfig& config, std::size_t agents,
                                    const SimulationTrace& trace) {
  LnsSkeleton s;
  s.routes.resize(agents);
  std::unordered_map<int, int> index;
  for (std::size_t i = 0; i < config.spots.size(); ++i)
    index.emplace(config.spots[i].pos, static_cast<int>(i));
  for (const auto& event : trace.acquisitions)
    s.routes.at(event.agent).push_back(index.at(event.spot_pos));
  return s;
}
// Exact serialized skeleton identity: no position-only state collapse or hash
// collision pruning. A decoded skeleton is a proposal, not a simulation state.
std::string signature(const LnsSkeleton& s) {
  std::string key;
  for (const auto& route : s.routes) {
    key += '|';
    for (int v : route) { key += std::to_string(v); key += ','; }
  }
  return key;
}
struct Node {
  LnsSkeleton skeleton;
  CandidateValue rank;
  std::uint64_t id;
};
struct Order {
  bool operator()(const Node& a, const Node& b) const {
    if (a.rank != b.rank) return a.rank > b.rank;
    return a.id < b.id;
  }
};
struct Insertion {
  int spot, agent, at, tier, delta;
  std::uint64_t tie;
};
}

Result solve(const MapConfig& config, const DayInfo& day,
             const PolicyHistory& history, const AgentTypes& types, const Options& options) {
  const auto start = Clock::now();
  if (options.time_ms < 1 || options.time_ms > 50000 || options.depth < 1 ||
      options.depth > 32 || options.layer_capacity < 1 || options.layer_capacity > 2048 ||
      options.branching < 1 || options.branching > 128 || options.max_expansions < 0 ||
      options.seed_percent < 0 || options.seed_percent > 80)
    throw std::invalid_argument("invalid search limits (time_ms must be 1..50000)");
  validate_config(config);
  if (day.day < 0 || day.day >= static_cast<int>(config.day_steps.size()) ||
      types.size() != day.agents.size() || types.size() != config.agents.size())
    throw std::invalid_argument("invalid day or agent count");
  for (std::size_t i = 0; i < types.size(); ++i) {
    if ((types[i] != AgentKind::Patrol && types[i] != AgentKind::Refuel) ||
        day.agents[i].kind != types[i] || day.agents[i].pos < 0 ||
        day.agents[i].pos >= static_cast<int>(config.cells.size()) ||
        config.cells[day.agents[i].pos] == Terrain::Pond || day.agents[i].fuel < 0 ||
        day.agents[i].fuel > config.fuel_limit)
      throw std::invalid_argument("invalid agent state/types");
  }
  // Leave serialization margin. Shared preprocessing is cooperative, not
  // preemptible; callers still need a process-level hard deadline.
  const auto deadline = start + std::chrono::milliseconds(
      options.time_ms - std::min(250, options.time_ms / 20));
  auto expired = [&] { return Clock::now() >= deadline; };
  Result result;
  result.actions = wait_plan(types.size(), config.day_steps[day.day]);
  auto initial = evaluate_candidate(config, day, history, result.actions);
  if (!initial) throw std::runtime_error("wait plan failed simulator validation");
  result.value = initial->value;
  CandidateEvaluation best_eval = *initial;
  auto consider = [&](const ActionPlan& plan, const CandidateEvaluation& e) {
    if (admissible_improvement(e.value, result.value)) {
      result.actions = plan;
      result.value = e.value;
      best_eval = e;
      ++result.diagnostics.improvements;
    }
  };
  auto finish = [&] {
    result.diagnostics.elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        Clock::now() - start).count();
    return result;
  };
  // Same authoritative simulator and old construction heuristics; no old source
  // changes. All seeds pass the same two-criterion guard as search candidates.
  for (const std::string policy : {"greedy", "fuel_aware", "utility_greedy"}) {
    if (expired()) break;
    auto plan = build_routing_plan(policy, config, day, history, types);
    if (auto e = evaluate_candidate(config, day, history, plan)) consider(plan, *e);
  }
  if (!expired() && options.seed_percent > 0) {
    SearchLimits limits;
    limits.time_limit_ms = std::min(12000, options.time_ms * options.seed_percent / 100);
    const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count();
    limits.time_limit_ms = std::min(limits.time_limit_ms, static_cast<int>(std::max(0LL, static_cast<long long>(remaining))));
    limits.min_iterations = 0;
    limits.max_iterations = 1000000;
    limits.stagnation_iterations = 0;
    limits.aco_ants = 4;
    limits.aco_iterations = 2;
    limits.seed_iterations = 4;
    limits.random_seed = options.seed;
    auto plan = build_alns_plan(config, day, history, types, limits,
                                kProductionAlnsFeatures, false);
    if (auto e = evaluate_candidate(config, day, history, plan)) consider(plan, *e);
  }
  result.baseline = result.value;
  if (expired() || options.max_expansions == 0) return finish();
  const auto graph = build_aco_graph(config, day);
  if (expired()) return finish();
  const auto meetings = build_aco_meeting_cache(graph, 6);
  if (expired()) return finish();
  std::mt19937_64 random(options.seed);
  std::uint64_t serial = 0;
  using Layer = std::multiset<Node, Order>;
  std::vector<Layer> layers(options.depth + 1);
  std::unordered_set<std::string> seen;
  auto push = [&](int depth, LnsSkeleton s, const CandidateValue& rank) {
    // Layer participates in the key: the same skeleton at a shallower depth
    // has more remaining repair capacity and is not an equivalent search node.
    auto key = std::to_string(depth) + ':' + signature(s);
    if (seen.size() >= 50000) return;
    if (!seen.insert(std::move(key)).second) { ++result.diagnostics.duplicates; return; }
    auto& layer = layers[depth];
    layer.insert({std::move(s), rank, serial++});
    if (layer.size() > static_cast<std::size_t>(options.layer_capacity))
      layer.erase(std::prev(layer.end()));
    int live = 0;
    for (const auto& l : layers) live += static_cast<int>(l.size());
    result.diagnostics.peak_frontier = std::max(result.diagnostics.peak_frontier, live);
  };
  auto decode = [&](const LnsSkeleton& skeleton, int strategy)
      -> std::optional<std::pair<ActionPlan, CandidateEvaluation>> {
    AlnsTravelChoices travel(types.size());
    for (std::size_t i = 0; i < types.size(); ++i)
      travel[i].assign(skeleton.routes[i].size(), static_cast<std::uint32_t>(strategy));
    auto plan = decode_lns_skeleton(config, day, types, graph, meetings, skeleton, &travel, false);
    if (!plan) return std::nullopt;
    auto e = evaluate_candidate(config, day, history, *plan);
    ++result.diagnostics.evaluated;
    if (!e) return std::nullopt;
    consider(*plan, *e);
    return std::pair{std::move(*plan), std::move(*e)};
  };
  auto restart = [&] {
    for (auto& layer : layers) layer.clear();
    seen.clear();
    ++result.diagnostics.restarts;
    auto base = lns_skeleton_from_trace(config, types.size(), best_eval.trace);
    push(0, base, result.value);
    // Small and larger ruin roots; keep missing brands eligible during repair.
    for (int r = 0; r < 6 && !expired(); ++r) {
      auto s = base;
      int count = 0;
      for (const auto& route : s.routes) count += static_cast<int>(route.size());
      const int remove = std::min(count, 1 + r % options.depth);
      for (int k = 0; k < remove; ++k) {
        int chosen = static_cast<int>(random() % count--);
        for (auto& route : s.routes) {
          if (chosen < static_cast<int>(route.size())) {
            route.erase(route.begin() + chosen); break;
          }
          chosen -= static_cast<int>(route.size());
        }
      }
      if (auto decoded = decode(s, r % 4))
        push(0, lns_skeleton_from_trace(config, types.size(), decoded->second.trace), decoded->second.value);
    }
  };
  restart();
  int epoch_expansions = 0;
  while (!expired() && result.diagnostics.expansions < options.max_expansions) {
    bool progressed = false;
    ++result.diagnostics.sweeps;
    // Chokudai: preserve EVERY layer between sweeps and revisit pending nodes
    // at earlier depths. Bounded capacity is a deliberate memory approximation.
    for (int depth = 0; depth < options.depth && !expired() &&
         result.diagnostics.expansions < options.max_expansions; ++depth) {
      if (layers[depth].empty()) continue;
      auto handle = layers[depth].extract(layers[depth].begin());
      Node node = std::move(handle.value());
      progressed = true;
      ++result.diagnostics.expansions;
      ++epoch_expansions;
      std::vector<int> assigned(config.spots.size());
      std::set<int> brands;
      for (const auto& route : node.skeleton.routes)
        for (int s : route) { ++assigned[s]; brands.insert(config.spots[s].brand); }
      std::vector<Insertion> candidates;
      for (std::size_t s = 0; s < config.spots.size() && !expired(); ++s) {
        if (assigned[s] >= config.spots[s].stocks) continue;
        const int target = graph.node_for_pos.at(config.spots[s].pos);
        const int tier = brands.contains(config.spots[s].brand) ? 0 :
            (history.distinct_brands.contains(config.spots[s].brand) ? 1 : 2);
        for (std::size_t a = 0; a < types.size(); ++a) {
          if (types[a] != AgentKind::Patrol) continue;
          const auto& route = node.skeleton.routes[a];
          if (std::find(route.begin(), route.end(), static_cast<int>(s)) != route.end()) continue;
          for (std::size_t at = 0; at <= route.size(); ++at) {
            const int from = graph.node_for_pos.at(at ? config.spots[route[at-1]].pos : day.agents[a].pos);
            const int to = at == route.size() ? -1 : graph.node_for_pos.at(config.spots[route[at]].pos);
            const int first = lns_path_time(graph, from, target);
            const int second = to < 0 ? 0 : lns_path_time(graph, target, to);
            if (first >= 100000000 || second >= 100000000) continue;
            const int old = to < 0 ? 0 : lns_path_time(graph, from, to);
            candidates.push_back({static_cast<int>(s), static_cast<int>(a), static_cast<int>(at), tier,
                                  first + second - old, random()});
          }
        }
      }
      std::sort(candidates.begin(), candidates.end(), [](const auto& a, const auto& b) {
        return std::tuple{-a.tier, a.delta, a.tie} < std::tuple{-b.tier, b.delta, b.tie};
      });
      // Reserve a quarter of expansions for other insertions. Otherwise all
      // cheap copies of one missing brand can crowd out useful alternatives.
      const auto keep = static_cast<std::size_t>(options.branching);
      if (candidates.size() > keep) {
        const auto protected_count = std::max<std::size_t>(1, keep * 3 / 4);
        std::shuffle(candidates.begin() + protected_count, candidates.end(), random);
        candidates.resize(keep);
      }
      for (const auto& c : candidates) {
        if (expired()) break;
        auto next = node.skeleton;
        next.routes[c.agent].insert(next.routes[c.agent].begin() + c.at, c.spot);
        for (int attempt = 0; attempt < 2 && !expired(); ++attempt) {
          // Time-first versus fuel-first/early-refuel travel decoding.
          const int strategy = attempt == 0 ? 0 : 1 + static_cast<int>(random() % 3);
          if (auto decoded = decode(next, strategy)) {
            auto canonical = lns_skeleton_from_trace(config, types.size(), decoded->second.trace);
            if (canonical == node.skeleton) continue;
            push(depth + 1, std::move(canonical), decoded->second.value);
          }
        }
      }
    }
    // Depth limit is intentional; all complete candidates have already been
    // scored. Restart from the best with a different ruin after bounded work.
    if (!progressed || epoch_expansions >= 128 || seen.size() >= 50000) {
      restart();
      epoch_expansions = 0;
    }
  }
  return finish();
}
}
