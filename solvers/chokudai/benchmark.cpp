#include "solver.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

using namespace hexudon;
json::array score_array(const CandidateValue& v) {
  return {std::get<0>(v), std::get<1>(v), std::get<2>(v)};
}
json::object run_match(const MapConfig& config, const AgentTypes& types,
                       int time_ms, int days, bool hybrid) {
  TeamState team;
  team.id = "isolated-benchmark";
  for (std::size_t i=0;i<types.size();++i)
    team.agents.push_back({types[i],config.agents[i],config.fuel_limit});
  std::vector<std::map<int,int>> traffic_history;
  json::array scores;
  for (int day_index=0;day_index<days;++day_index) {
    const auto roads=road_status_for_day(config,traffic_history,1);
    DayInfo day; day.day=day_index; day.traffics=roads;
    for (const auto& a:team.agents) day.agents.push_back({a.kind,a.pos,a.fuel});
    const auto started=std::chrono::steady_clock::now();
    ActionPlan plan;
    json::object detail;
    if(hybrid) {
      udon_chokudai::Options options;
      options.time_ms=time_ms;
      auto result=udon_chokudai::solve(config,day,team.history,types,options);
      plan=std::move(result.actions);
      detail["seed_score"]=score_array(result.baseline);
      detail["expansions"]=result.diagnostics.expansions;
      detail["sweeps"]=result.diagnostics.sweeps;
      detail["evaluated"]=result.diagnostics.evaluated;
      if(std::get<0>(result.value)<std::get<0>(result.baseline) ||
         std::get<1>(result.value)<std::get<1>(result.baseline) || result.value<result.baseline)
        throw std::runtime_error("seed guard regression");
    } else {
      SearchLimits limits;
      limits.time_limit_ms=time_ms;
      limits.min_iterations=0; limits.max_iterations=1000000; limits.stagnation_iterations=0;
      limits.random_seed=1;
      plan=plan_day("alns",config,day,team.history,types,limits);
    }
    const auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now()-started).count();
    auto e=evaluate_candidate(config,day,team.history,plan);
    if(!e) throw std::runtime_error("invalid benchmark plan");
    detail["day"]=day_index;
    detail["score"]=score_array(e->value);
    detail["elapsed_ms"]=elapsed;
    scores.push_back(detail);
    team.stock.clear(); team.visited_today.assign(types.size(),{}); team.daily_types.clear();
    for(auto spot:config.spots) team.stock[spot.pos]=spot.stocks;
    std::map<int,int> traffic;
    if(auto error=simulate_team_day(config,team,plan,roads,traffic)) throw std::runtime_error(*error);
    team.cumulative_daily_types+=static_cast<int>(team.daily_types.size());
    team.history.submitted_actions.push_back(plan);
    team.history.distinct_brands=team.distinct_types;
    team.history.cumulative_daily_types=team.cumulative_daily_types;
    team.history.total_servings=team.total_servings;
    traffic_history.push_back(std::move(traffic));
    std::cerr<<(hybrid?"chokudai":"alns")<<" day="<<day_index
             <<" score="<<json::serialize(detail.at("score"))<<" ms="<<elapsed<<'\n';
  }
  return {{"days",scores},{"total",json::array{team.distinct_types.size(),
            team.cumulative_daily_types,team.total_servings}}};
}
int main(int argc,char** argv) {
  try {
    if(argc!=5) throw std::invalid_argument("usage: benchmark scenario.json time_ms days output.json");
    std::ifstream file(argv[1]);
    if(!file) throw std::invalid_argument("scenario not readable");
    std::string contents{std::istreambuf_iterator<char>(file),{}};
    auto input=json::parse(contents);
    auto config=parse_map_config(input.as_object().at("config"));
    const int time_ms=std::stoi(argv[2]);
    if(time_ms<1 || time_ms>50000) throw std::invalid_argument("budget out of range");
    const int days=std::min(std::stoi(argv[3]),static_cast<int>(config.day_steps.size()));
    if(days<1) throw std::invalid_argument("days must be positive");
    // Same roles for both algorithms. This is self-traffic-only replay, not a
    // claim to reproduce an online opponent or its unknown future actions.
    SearchLimits role_limits; role_limits.time_limit_ms=800;
    auto types=select_agent_types("alns",config,role_limits);
    auto baseline=run_match(config,types,time_ms,days,false);
    auto challenger=run_match(config,types,time_ms,days,true);
    const auto& a=baseline.at("total").as_array();
    const auto& b=challenger.at("total").as_array();
    bool daily_non_regression=true;
    const auto& ad=baseline.at("days").as_array();
    const auto& bd=challenger.at("days").as_array();
    for(std::size_t i=0;i<ad.size();++i)
      if(bd[i].as_object().at("score").as_array()[1].to_number<int>() <
         ad[i].as_object().at("score").as_array()[1].to_number<int>()) daily_non_regression=false;
    json::object report{{"scenario",argv[1]}, {"budget_ms_per_day",time_ms},
      {"simulation","self-traffic only; identical fixed roles; separate match trajectories"},
      {"types",to_json(types)}, {"alns",baseline},{"chokudai",challenger},
      {"distinct_non_regression",b[0].to_number<int>()>=a[0].to_number<int>()},
      {"daily_non_regression",daily_non_regression},
      {"servings_delta",b[2].to_number<int>()-a[2].to_number<int>()}};
    std::ofstream output(argv[4]);
    if(!output) throw std::runtime_error("cannot write benchmark report");
    output<<json::serialize(report)<<'\n';
    std::cout<<json::serialize(report)<<'\n';
  } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
