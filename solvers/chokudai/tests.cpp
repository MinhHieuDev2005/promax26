#include "solver.hpp"
#include <iostream>
#include <stdexcept>

using namespace hexudon;
using namespace udon_chokudai;
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
MapConfig config_for(int seed) {
  MapConfig c;
  c.width = 5; c.height = 5;
  c.cells.assign(25, Terrain::Plain);
  c.day_steps = {18, 18, 18}; c.day_seconds = {1, 1, 1};
  c.agents = {0, 20, 12}; c.fuel_limit = 7 + seed % 5;
  c.players = 1; c.busy_threshold = 3; c.jammed_threshold = 6;
  c.spots = {{0, 3, 2}, {1, 9, 2}, {2, 16, 2}, {0, 21, 1}, {1, 23, 2}};
  if (seed % 2) c.cells[7] = Terrain::Pond;
  for (int pos : {5, 10, 15}) c.cells[pos] = Terrain::Road;
  return c;
}
int main() {
  try {
    require(!admissible_improvement({2, 4, 100, 0}, {3, 3, 5, 0}), "lost criterion 1");
    require(!admissible_improvement({4, 2, 100, 0}, {3, 3, 5, 0}), "lost criterion 2");
    require(admissible_improvement({3, 3, 6, 0}, {3, 3, 5, 0}), "missed serving gain");
    require(!admissible_improvement({3, 3, 4, 100}, {3, 3, 5, 0}), "fuel beat servings");
    int days_checked = 0, expansions = 0, sweeps = 0, improved_days = 0;
    for (int seed = 0; seed < 6; ++seed) {
      auto c = config_for(seed);
      AgentTypes types{AgentKind::Patrol, AgentKind::Patrol,
                      seed % 2 ? AgentKind::Refuel : AgentKind::Patrol};
      TeamState team;
      team.id = "test";
      for (std::size_t i=0; i<types.size(); ++i) team.agents.push_back({types[i], c.agents[i], c.fuel_limit});
      std::vector<std::map<int,int>> traffic_history;
      for (int d = 0; d < 3; ++d) {
        auto roads = road_status_for_day(c, traffic_history, 1);
        DayInfo day; day.day = d; day.traffics = roads;
        for (auto a : team.agents) day.agents.push_back({a.kind,a.pos,a.fuel});
        Options options;
        options.time_ms = 2000; options.seed_percent = 0;
        options.max_expansions = 12; options.branching = 6; options.seed = seed;
        auto result = solve(c, day, team.history, types, options);
        require(std::get<0>(result.value) >= std::get<0>(result.baseline), "baseline distinct regression");
        require(std::get<1>(result.value) >= std::get<1>(result.baseline), "baseline daily regression");
        require(result.value >= result.baseline, "baseline objective regression");
        auto verified = evaluate_candidate(c, day, team.history, result.actions);
        require(verified && verified->value == result.value, "score differs from simulator");
        require(result.diagnostics.peak_frontier <= (options.depth+1)*options.layer_capacity, "frontier unbounded");
        expansions += result.diagnostics.expansions; sweeps += result.diagnostics.sweeps;
        if (std::get<2>(result.value) > std::get<2>(result.baseline)) ++improved_days;
        team.stock.clear(); team.visited_today.assign(types.size(), {}); team.daily_types.clear();
        for (auto spot : c.spots) team.stock[spot.pos] = spot.stocks;
        std::map<int,int> traffic;
        require(!simulate_team_day(c, team, result.actions, roads, traffic), "match replay invalid");
        team.cumulative_daily_types += static_cast<int>(team.daily_types.size());
        team.history.submitted_actions.push_back(result.actions);
        team.history.distinct_brands = team.distinct_types;
        team.history.cumulative_daily_types = team.cumulative_daily_types;
        team.history.total_servings = team.total_servings;
        traffic_history.push_back(traffic);
        ++days_checked;
      }
    }
    require(expansions > 0 && sweeps > 1, "Chokudai layers were never revisited");
    require(improved_days > 0, "search never improved a greedy seed on the fixtures");
    // All-refuel with zero fuel; an unreachable plain-cell spot is legal.
    auto c = config_for(0);
    c.spots = {{0, 24, 1}}; c.cells[19] = Terrain::Pond; c.cells[23] = Terrain::Pond;
    AgentTypes types(3, AgentKind::Refuel);
    DayInfo day; day.day = 2;
    for (int p : c.agents) day.agents.push_back({AgentKind::Refuel, p, 0});
    Options quick; quick.time_ms=20; quick.seed_percent=0; quick.max_expansions=1;
    require(std::get<2>(solve(c, day, {}, types, quick).value) == 0, "all-refuel served udon");
    types.assign(3, AgentKind::Patrol);
    for(auto& agent : day.agents) { agent.kind=AgentKind::Patrol; agent.fuel=0; }
    require(std::get<2>(solve(c, day, {}, types, quick).value) == 0, "zero-fuel patrol moved");
    quick.time_ms=50001;
    bool rejected=false;
    try { solve(c, day, {}, types, quick); } catch (const std::invalid_argument&) { rejected=true; }
    require(rejected, "accepted budget over 50 seconds");
    std::cout << "PASS: objective guards, " << days_checked << " replayed days, "
              << expansions << " expansions, " << sweeps << " sweeps, "
              << improved_days << " days with serving gain over greedy seeds, limits and all-refuel\n";
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
