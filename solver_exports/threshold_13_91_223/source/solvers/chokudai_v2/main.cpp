#include "search.hpp"
#include <chrono>
#include <iostream>
#include <iterator>
#include <stdexcept>
using namespace hexudon;
int main() {
  try {
    const std::string input{std::istreambuf_iterator<char>(std::cin),{}};
    const auto value=json::parse(input); const auto& root=value.as_object();
    const auto config=parse_map_config(root.at("config"));
    const json::object empty;
    const auto& search=root.if_contains("search")?root.at("search").as_object():empty;
    auto integer=[&](const char* k,int fallback) {auto p=search.if_contains(k);return p?p->to_number<int>():fallback;};
    chokudai_v2::Options o;
    o.time_ms=integer("timeLimitMs",20000); o.slice_ms=integer("sliceMs",250);
    o.width=integer("layerCapacity",24); o.attempts=integer("attempts",6);
    o.max_expansions=integer("maxExpansions",100000);
    const int seed=integer("randomSeed",1); if(seed<0) throw std::invalid_argument("negative seed"); o.seed=seed;
    if(auto p=search.if_contains("useElites")) o.use_elites=p->as_bool();
    if(auto p=search.if_contains("useWarm")) o.use_warm=p->as_bool();
    if(auto p=search.if_contains("useRouteDp")) o.use_route_dp=p->as_bool();
    if(auto p=search.if_contains("useStrongSeed")) o.use_strong_seed=p->as_bool();
    if(auto p=search.if_contains("exhaustBudget")) o.exhaust_budget=p->as_bool();
    if(o.time_ms<1 || o.time_ms>60000) throw std::invalid_argument("budget must be 1..60000ms");
    if(auto p=root.if_contains("op");p && p->as_string()=="roles") {
      SearchLimits l; l.time_limit_ms=std::min(2500,o.time_ms);
      auto types=select_agent_types("alns",config,l);
      std::cout<<json::serialize(json::object{{"ok",true},{"roles",to_json(types)}})<<'\n'; return 0;
    }
    if(auto p=root.if_contains("op");p && p->as_string()!="plan") throw std::invalid_argument("unsupported op");
    const bool native=root.contains("day_info");
    auto state=root.at(native?"day_info":"state");
    if(!native) state.as_object()["day"]=state.as_object().at("day").to_number<int>()-1;
    const auto day=parse_day_info(state);
    AgentTypes types; for(const auto& a:day.agents) types.push_back(a.kind);
    if(auto p=root.if_contains("types")) {
      AgentTypes supplied;for(const auto& x:p->as_array()) supplied.push_back(static_cast<AgentKind>(x.to_number<int>()));
      if(supplied!=types) throw std::invalid_argument("types mismatch");
    }
    auto history=root.if_contains("history")?parse_history(root.at("history")):PolicyHistory{};
    if(day.ends_at) {
      const double now=std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
      const double left=(*day.ends_at-now)*1000-500;
      if(left<1) throw std::invalid_argument("expired deadline");
      if(left<o.time_ms) o.time_ms=static_cast<int>(left);
    }
    auto result=chokudai_v2::solve(config,day,history,types,o,root.if_contains("planner_state"));
    std::cout<<json::serialize(json::object{{"ok",true},{"plan",to_json(result.actions)},
              {"planner_state",result.state},{"diagnostics",result.diagnostics},
              {"forecast","self-traffic; future roads are predictions, not observations"}})<<'\n';
  } catch(const std::exception& e) {
    std::cout<<json::serialize(json::object{{"ok",false},{"error",e.what()}})<<'\n';return 1;
  }
}
