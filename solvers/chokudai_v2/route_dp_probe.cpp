#include "route_dp.hpp"
#include <chrono>
#include <iostream>
#include <iterator>
using namespace hexudon;
int main() {
  try {
    const std::string text{std::istreambuf_iterator<char>(std::cin),{}};
    const auto root=json::parse(text).as_object();
    const auto c=parse_map_config(root.at("config"));
    auto day=parse_day_info(root.at("day_info"));
    const auto h=root.contains("history")?parse_history(root.at("history")):PolicyHistory{};
    AgentTypes types;
    if(root.contains("types")) for(const auto& v:root.at("types").as_array()) types.push_back(static_cast<AgentKind>(v.to_number<int>()));
    else for(const auto& a:day.agents) types.push_back(a.kind);
    if(types.size()!=day.agents.size()) throw std::invalid_argument("types size mismatch");
    for(std::size_t i=0;i<types.size();++i) day.agents[i].kind=types[i];
    auto base=wait_plan(types.size(),c.day_steps.at(day.day));
    const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(60);
    const auto plans=chokudai_v2::route_dp_proposals(c,day,types,base,deadline);
    json::array scores;std::optional<CandidateValue> best;ActionPlan best_plan;
    for(const auto& plan:plans) if(auto e=evaluate_candidate(c,day,h,plan)) {
      scores.push_back(json::array{std::get<0>(e->value),std::get<1>(e->value),std::get<2>(e->value),std::get<3>(e->value)});
      if(!best || e->value>*best) {best=e->value;best_plan=plan;}
    }
    std::cout<<json::serialize(json::object{{"plans",plans.size()},{"scores",scores},
      {"best",best?json::value(json::array{std::get<0>(*best),std::get<1>(*best),std::get<2>(*best),std::get<3>(*best)}):json::value()},
      {"plan",best?to_json(best_plan):json::value()}})<<'\n';
  } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
