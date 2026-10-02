#include "hexudon/internal.hpp"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <iterator>
#include <set>
#include <sstream>

using namespace hexudon;
using Clock=std::chrono::steady_clock;
ActionPlan parse(const json::value& v) {
  ActionPlan p;
  for(const auto& row:v.as_array()) {
    p.emplace_back();for(const auto& a:row.as_array())p.back().push_back(a.to_number<int>());
  }
  return p;
}
struct Candidate {ActionPlan plan;CandidateEvaluation eval;std::string origin;};

int main() {
 try {
#ifdef _WIN32
  _putenv_s("HEXUDON_THREADS","1");
#else
  setenv("HEXUDON_THREADS","1",1);
#endif
  auto started=Clock::now();
  auto input=json::parse(std::string{std::istreambuf_iterator<char>(std::cin),{}});
  const auto& root=input.as_object();
  auto config=parse_map_config(root.at("config")); validate_config(config);
  json::object empty;
  const auto& search=root.if_contains("search")?root.at("search").as_object():empty;
  auto integer=[&](const char* k,int fallback){auto p=search.if_contains(k);return p?p->to_number<int>():fallback;};
  int budget=std::clamp(integer("timeLimitMs",45000),1,45000), seed=integer("randomSeed",1);
  SearchLimits limits;
  if(root.if_contains("op") && root.at("op").as_string()=="roles") {
    limits.time_limit_ms=std::min(2000,budget);
    std::cout<<json::serialize(json::object{{"ok",true},{"roles",to_json(select_agent_types("alns",config,limits))}})<<'\n';return 0;
  }
  auto encoded=root.at(root.contains("day_info")?"day_info":"state");
  if(!root.contains("day_info"))encoded.as_object()["day"]=encoded.as_object().at("day").to_number<int>()-1;
  auto day=parse_day_info(encoded);
  auto history=root.if_contains("history")?parse_history(root.at("history")):PolicyHistory{};
  AgentTypes types;for(auto a:day.agents)types.push_back(a.kind);
  if(day.ends_at) {
    double now=std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    budget=std::min(budget,std::max(1,int((*day.ends_at-now)*1000)-900));
  }
  const auto deadline=started+std::chrono::milliseconds(std::max(1,budget-std::min(3000,budget/5)));
  auto left=[&]{return int(std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count());};
  std::set<int> brands;for(auto s:config.spots)brands.insert(s.brand);
  int required=int(brands.size()),today=config.day_steps.at(day.day);
  bool short_next=day.day+1<int(config.day_steps.size()) && config.day_steps[day.day+1]*5<today*4;
  auto generate=[&](const DayInfo& d,const PolicyHistory& h,int ms,int random_seed){
    SearchLimits l;l.time_limit_ms=std::max(1,std::min(ms,left()));l.random_seed=random_seed;
    l.min_iterations=0;l.max_iterations=1000000;l.stagnation_iterations=0;
    return plan_day("alns",config,d,h,types,l);
  };
  std::vector<Candidate> pool;
  std::set<std::string> seen;
  auto add=[&](ActionPlan p,const std::string& origin){
    auto sig=json::serialize(to_json(p));if(!seen.insert(sig).second)return;
    auto e=evaluate_candidate(config,day,history,p);
    if(e && std::get<0>(e->value)==required && std::get<1>(e->value)==required)
      pool.push_back({std::move(p),std::move(*e),origin});
  };
  add(generate(day,history,std::min(8000,std::max(1,left()/2)),seed),"baseline");
  auto cfg=root.at("config").as_object();cfg.erase("startsAt");auto fingerprint=json::serialize(cfg);
  if(const auto* w=root.if_contains("planner_state");w && w->is_object())try {
    const auto& o=w->as_object();
    if(o.at("fingerprint").as_string()==fingerprint && o.at("source_day").to_number<int>()==day.day-1 &&
       !history.submitted_actions.empty() && parse(o.at("committed"))==history.submitted_actions.back())
      add(parse(o.at("next_plan")),"verified_warm");
  }catch(const std::exception&){}
  if(pool.empty())throw std::runtime_error("no full-coverage incumbent");
  json::array comparisons;
  ActionPlan next_plan;
  std::size_t selected=0;
  for(std::size_t i=1;i<pool.size();++i)if(pool[i].eval.value>pool[selected].eval.value)selected=i;
  if(short_next && left()>6000) {
    // Strong alternative complete-day routes first.
    for(int k=1;k<=2 && left()>20000;++k)add(generate(day,history,4000,seed+k),"alternate");
    const auto source=pool[selected].plan;
    int baseline_bowls=std::get<2>(pool[selected].eval.value);
    // Reposition one car in the final 12/20 turns. Retain the full team plan
    // only after checking every acquisition, fuel transfer and timing event.
    std::vector<std::vector<ActionPlan>> stage_options(types.size());
    for(std::size_t a=0;a<types.size() && left()>12000;++a)for(int tail:{12,20}) {
      std::vector<int> prefix;int elapsed=0,pos=day.agents[a].pos;
      for(int action:source[a]) {
        int cost=action<0?-action:terrain_time(config,pos,day.traffics);
        if(elapsed+cost>today-tail)break;
        prefix.push_back(action);elapsed+=cost;
        if(action>=0)pos=*neighbor(config,pos,action);
      }
      for(auto target:config.spots) {
        auto path=shortest_path(config,pos,target.pos,day.traffics);
        if((pos!=target.pos && path.directions.empty()) || path.cost>today-elapsed)continue;
        auto proposed=source;proposed[a]=prefix;
        proposed[a].insert(proposed[a].end(),path.directions.begin(),path.directions.end());
        int wait=today-elapsed-path.cost;if(wait)proposed[a].push_back(-wait);
        stage_options[a].push_back(std::move(proposed));
        if(stage_options[a].size()>=24)break;
      }
    }
    auto consider_stage=[&](ActionPlan proposed,const char* origin) {
      auto e=evaluate_candidate(config,day,history,proposed);
      if(e && std::get<2>(e->value)>=baseline_bowls-3)add(std::move(proposed),origin);
    };
    for(std::size_t a=0;a<stage_options.size();++a)
      for(auto& proposed:stage_options[a])consider_stage(proposed,"tail_stage");
    // Optional two-car staging. The cap keeps the quadratic combination step
    // bounded; exact simulation remains the acceptance gate.
    if(integer("jointStage",0)) {
      for(std::size_t a=0;a<stage_options.size() && left()>8000;++a)
        for(std::size_t b=a+1;b<stage_options.size() && left()>8000;++b)
          for(auto& first:stage_options[a])for(auto& second:stage_options[b]) {
            auto proposed=source;proposed[a]=first[a];proposed[b]=second[b];
            consider_stage(std::move(proposed),"joint_tail_stage");
            if(left()<=8000)break;
          }
    }
    // Keep diverse endpoints before expensive rollout; tail candidates have
    // to survive exact full-coverage validation, not a weighted score.
    std::stable_sort(pool.begin(),pool.end(),[](const auto& a,const auto& b){return a.eval.value>b.eval.value;});
    std::vector<std::size_t> candidates;
    std::set<std::vector<int>> endpoints;
    for(std::size_t i=0;i<pool.size();++i)if(endpoints.insert(pool[i].eval.ending_positions).second)candidates.push_back(i);
    if(candidates.size()>10) {
      // Reserve rollout slots for lower-current-score boundary states too;
      // otherwise sorting today-first silently eliminates the intended trade.
      std::vector<std::size_t> shortlist(candidates.begin(),candidates.begin()+5);
      std::vector<std::size_t> tails;
      for(auto i:candidates)if(pool[i].origin=="tail_stage" &&
          std::find(shortlist.begin(),shortlist.end(),i)==shortlist.end())tails.push_back(i);
      for(std::size_t k=0;k<5 && !tails.empty();++k)
        shortlist.push_back(tails[k*(tails.size()-1)/4]);
      std::sort(shortlist.begin(),shortlist.end());
      shortlist.erase(std::unique(shortlist.begin(),shortlist.end()),shortlist.end());
      candidates=std::move(shortlist);
    }
    int slice=std::min(3500,std::max(300,(left()-1000)/int(std::max<std::size_t>(1,candidates.size()))));
    int best_total=-1; selected=0;
    for(auto i:candidates) {
      if(left()<slice+200)break;
      auto next=day;next.day++;next.ends_at.reset();next.others.clear();
      auto h=history;h.submitted_actions.push_back(pool[i].plan);h.distinct_brands=brands;
      int bowls=std::get<2>(pool[i].eval.value);h.total_servings+=bowls;h.cumulative_daily_types+=required;
      for(std::size_t a=0;a<types.size();++a)next.agents[a]={types[a],pool[i].eval.ending_positions[a],pool[i].eval.ending_fuel[a]};
      // Revealed roads today; hold them as an explicitly labelled forecast.
      auto p=generate(next,h,slice,seed);
      auto e=evaluate_candidate(config,next,h,p);
      if(!e || std::get<1>(e->value)!=required)continue;
      int tomorrow=std::get<2>(e->value),total=bowls+tomorrow;
      comparisons.push_back(json::object{{"origin",pool[i].origin},{"today",bowls},{"tomorrow",tomorrow},{"sum",total}});
      if(total>best_total) {best_total=total;selected=i;next_plan=std::move(p);}
    }
  }
  json::value state=nullptr;
  if(!next_plan.empty())state=json::object{{"fingerprint",fingerprint},{"source_day",day.day},
    {"committed",to_json(pool[selected].plan)},{"next_plan",to_json(next_plan)}};
  std::cout<<json::serialize(json::object{{"ok",true},{"plan",to_json(pool[selected].plan)},
    {"planner_state",state},{"diagnostics",json::object{{"engine","short_day"},{"short_next",short_next},
    {"forecast","hold_observed_roads"},{"pool_size",int(pool.size())},{"selected",pool[selected].origin},
    {"rollouts",comparisons},{"elapsed_ms",std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-started).count()}}}})<<'\n';
 }catch(const std::exception& e){std::cout<<json::serialize(json::object{{"ok",false},{"error",e.what()}})<<'\n';return 1;}
}
