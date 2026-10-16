#include "search.hpp"
#include "route_dp.hpp"
#include <algorithm>
#include <chrono>
#include <memory>
#include <random>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

namespace chokudai_v2 {
using namespace hexudon;
using Clock=std::chrono::steady_clock;
using Traffic=std::vector<std::map<int,int>>;
namespace {
ActionPlan parse_plan(const json::value& v) {
  ActionPlan p;
  for(const auto& a:v.as_array()) {
    p.emplace_back();
    for(const auto& x:a.as_array()) p.back().push_back(x.to_number<int>());
  }
  return p;
}
std::string fingerprint(const MapConfig& c,const AgentTypes& types) {
  std::ostringstream s;
  s<<c.width<<','<<c.height<<','<<c.fuel_limit<<','<<c.players<<','<<c.busy_threshold<<','<<c.jammed_threshold;
  for(auto x:c.cells) s<<':'<<static_cast<int>(x);
  for(auto x:c.spots) s<<'s'<<x.pos<<','<<x.brand<<','<<x.stocks;
  for(auto x:c.day_steps) s<<'d'<<x;
  for(auto x:c.agents) s<<'a'<<x;
  for(auto x:types) s<<'t'<<static_cast<int>(x);
  return s.str();
}
struct Node {
  DayInfo day;
  PolicyHistory history;
  Traffic traffic;
  std::vector<ActionPlan> plans;
  int attempts=0, fuel=0;
  std::uint64_t id=0;
};
std::string state_key(const Node& n) {
  std::ostringstream s;
  s<<n.day.day;
  for(const auto& a:n.day.agents) s<<'a'<<static_cast<int>(a.kind)<<','<<a.pos<<','<<a.fuel;
  for(auto [p,v]:n.day.traffics) s<<'r'<<p<<','<<v;
  // The previous two dwell maps are essential: equal revealed roads alone
  // are not equivalent future traffic states.
  for(std::size_t i=n.traffic.size()>2?n.traffic.size()-2:0;i<n.traffic.size();++i) {
    s<<'h'; for(auto [p,v]:n.traffic[i]) s<<p<<','<<v<<';';
  }
  for(auto b:n.history.distinct_brands) s<<'b'<<b;
  s<<'c'<<n.history.cumulative_daily_types;
  return s.str();
}
std::string bucket(const Node& n) {
  std::ostringstream s;
  for(const auto& a:n.day.agents) s<<a.pos<<',';
  return s.str();
}
// This single acceptance comparator is for COMPLETE, feasibility-checked
// suffixes only. No fuel or soft-weight tradeoff can reduce coverage/servings.
bool better_complete(const Node& a,const Node& b) {
  return a.history.total_servings>b.history.total_servings;
}
}

Result solve(const MapConfig& c,const DayInfo& day,const PolicyHistory& history,
             const AgentTypes& types,const Options& o,const json::value* warm) {
  const auto start=Clock::now();
  if(o.time_ms<1 || o.time_ms>60000 || o.slice_ms<1 || o.width<1 || o.width>256 || o.attempts<1 || o.attempts>32 || o.max_expansions<0)
    throw std::invalid_argument("invalid v2 search limits");
  validate_config(c);
  if(day.day<0 || day.day>=static_cast<int>(c.day_steps.size()) || types.size()!=day.agents.size() || types.size()!=c.agents.size())
    throw std::invalid_argument("invalid day/agents");
  for(std::size_t i=0;i<types.size();++i)
    if(types[i]!=day.agents[i].kind || (types[i]!=AgentKind::Patrol && types[i]!=AgentKind::Refuel))
      throw std::invalid_argument("invalid role");
  std::set<int> brands;
  for(auto s:c.spots) brands.insert(s.brand);
  const int required=static_cast<int>(brands.size());
  if(history.submitted_actions.size()!=static_cast<std::size_t>(day.day) || history.cumulative_daily_types!=day.day*required)
    throw std::invalid_argument("complete maximum-coverage history is required");
  const int days=static_cast<int>(c.day_steps.size())-day.day;
  const int patrols=static_cast<int>(std::count(types.begin(),types.end(),AgentKind::Patrol));
  int daily_bound=0;
  for(auto s:c.spots) daily_bound+=std::min(s.stocks,patrols);
  const auto deadline=start+std::chrono::milliseconds(o.time_ms-std::min(1000,o.time_ms/10));
  auto remaining=[&] { return static_cast<int>(std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count()); };
  Node root; root.day=day; root.history=history;
  // Reconstruct past self-dwell from accepted actions. Future forecast is
  // self-traffic; the actual current day always uses the caller's roads.
  TeamState past;
  for(std::size_t i=0;i<types.size();++i) past.agents.push_back({types[i],c.agents[i],c.fuel_limit});
  for(int d=0;d<day.day;++d) {
    past.stock.clear(); past.visited_today.assign(types.size(),{}); past.daily_types.clear();
    for(auto s:c.spots) past.stock[s.pos]=s.stocks;
    std::map<int,int> dwell;
    const auto roads=road_status_for_day(c,root.traffic,1);
    // Past observed roads are not part of PolicyHistory. Replaying an accepted
    // plan under inferred roads can therefore run slower and cross its old
    // horizon. This traffic reconstruction is forecast-only: keep a neutral
    // estimate instead of rejecting the authoritative revealed current state.
    if(auto error=simulate_team_day(c,past,history.submitted_actions[d],roads,dwell))
      dwell.clear();
    root.traffic.push_back(dwell);
    past.history.submitted_actions.push_back(history.submitted_actions[d]);
  }
  for(const auto& a:day.agents) if(a.kind==AgentKind::Patrol) root.fuel+=a.fuel;
  int evaluations=0, rejected=0, duplicates=0, expansions=0, sweeps=0, updates=0, peak=0, bound_prunes=0;
  std::uint64_t serial=1;
  std::mt19937_64 random(o.seed);
  auto advance=[&](const Node& n,const ActionPlan& plan)->std::optional<Node> {
    ++evaluations;
    const auto e=evaluate_candidate(c,n.day,n.history,plan);
    if(!e || std::get<0>(e->value)!=required || std::get<1>(e->value)!=required) { ++rejected; return std::nullopt; }
    Node next=n; next.attempts=0; next.id=serial++;
    next.plans.push_back(plan);
    next.history.submitted_actions.push_back(plan);
    next.history.distinct_brands=brands;
    next.history.cumulative_daily_types+=required;
    next.history.total_servings+=std::get<2>(e->value);
    next.traffic.push_back(e->road_traffic);
    next.day.day=n.day.day+1; next.day.ends_at.reset(); next.day.others.clear();
    next.day.traffics=road_status_for_day(c,next.traffic,1);
    next.fuel=0;
    for(std::size_t i=0;i<types.size();++i) {
      next.day.agents[i]={types[i],e->ending_positions[i],e->ending_fuel[i]};
      if(types[i]==AgentKind::Patrol) next.fuel+=e->ending_fuel[i];
    }
    return next;
  };
  std::optional<Node> best;
  std::vector<std::vector<std::shared_ptr<Node>>> layers(days);
  std::unordered_map<std::string,int> seen;
  json::array improvements;
  auto rank=[](const std::shared_ptr<Node>& a,const std::shared_ptr<Node>& b) {
    // Attempts penalize repeated expansion, not the objective of final plans.
    return std::tuple{a->history.total_servings-a->attempts/2,a->fuel,-static_cast<long long>(a->id)} >
           std::tuple{b->history.total_servings-b->attempts/2,b->fuel,-static_cast<long long>(b->id)};
  };
  auto push=[&](Node node) {
    const int depth=static_cast<int>(node.plans.size());
    if(depth==days) {
      if(!best || better_complete(node,*best)) {
        best=node; ++updates;
        improvements.push_back(json::object{{"ms",o.time_ms-remaining()},{"servings",node.history.total_servings}});
      }
      return;
    }
    const int upper=node.history.total_servings+(days-depth)*daily_bound;
    if(best && (upper<best->history.total_servings ||
       (!o.exhaust_budget && upper==best->history.total_servings))) {++bound_prunes;return;}
    auto key=state_key(node);
    auto found=seen.find(key);
    if(found!=seen.end() && found->second>=node.history.total_servings) {++duplicates;return;}
    seen[key]=node.history.total_servings;
    auto& layer=layers[depth];
    layer.push_back(std::make_shared<Node>(std::move(node)));
    std::sort(layer.begin(),layer.end(),rank);
    // Approximate diversity/capacity selection, NOT a mathematical dominance claim.
    std::unordered_map<std::string,int> buckets;
    const int bucket_quota=o.width>=64?8:3;
    std::erase_if(layer,[&](const auto& n) {return ++buckets[bucket(*n)]>bucket_quota;});
    if(layer.size()>static_cast<std::size_t>(o.width)) layer.resize(o.width);
    int live=0; for(const auto& l:layers) live+=static_cast<int>(l.size());
    peak=std::max(peak,live);
  };
  auto propose=[&](const Node& n,int ms,bool elites) {
    SearchLimits limits;
    limits.time_limit_ms=std::max(1,std::min(ms,remaining()));
    limits.min_iterations=0; limits.max_iterations=1000000; limits.stagnation_iterations=0;
    limits.seed_iterations=4; limits.aco_ants=4; limits.aco_iterations=2;
    limits.use_legacy_seed=false; limits.alns_restarts=1;
    limits.random_seed=random(); limits.exact_nodes=0; limits.final_exact_nodes=0;
    std::vector<ActionPlan> proposals;
    auto p=build_alns_plan(c,n.day,n.history,types,limits,kProductionAlnsFeatures,false,0,nullptr,elites?&proposals:nullptr);
    proposals.insert(proposals.begin(),std::move(p));
    // Subset-DP is an additive current-day branch. Calling it only at this
    // solve's revealed root keeps its exponential cost bounded; descendants
    // continue to use ALNS and are still evaluated as a complete suffix.
    const bool all_patrol=std::none_of(types.begin(),types.end(),[](AgentKind k){return k==AgentKind::Refuel;});
    if(o.use_route_dp && (n.plans.empty() || all_patrol) && remaining()>20) {
      // The subset-diverse pair generator needs about 3s on Q06.  A 2x
      // micro-slice cap silently discarded every proposal before pairing.
      const auto dp_deadline=std::min(deadline,Clock::now()+std::chrono::milliseconds(
        std::max(1,std::min(std::max(ms*5,4000),remaining()))));
      auto extra=route_dp_proposals(c,n.day,types,proposals.front(),dp_deadline);
      proposals.insert(proposals.end(),std::make_move_iterator(extra.begin()),std::make_move_iterator(extra.end()));
    }
    return proposals;
  };
  auto strong_propose=[&](const Node& n,int ms,std::uint64_t proposal_seed) {
    SearchLimits limits;
    limits.time_limit_ms=std::max(1,std::min(ms,remaining()));
    limits.min_iterations=0; limits.max_iterations=1000000;
    limits.stagnation_iterations=0; limits.random_seed=proposal_seed;
    limits.alns_restarts=3; limits.exact_nodes=0; limits.final_exact_nodes=0;
    return build_alns_multirestart_plan(c,n.day,n.history,types,limits,kProductionAlnsFeatures);
  };
  push(root);
  bool warm_valid=false;
  if(o.use_warm && warm && warm->is_object()) {
    try {
      const auto& w=warm->as_object();
      if(w.at("policy").as_string()=="chokudai_v2" && w.at("fingerprint").as_string()==fingerprint(c,types) &&
         w.at("source_day").to_number<int>()==day.day-1 && !history.submitted_actions.empty() &&
         parse_plan(w.at("committed_actions"))==history.submitted_actions.back()) {
        Node n=root;
        for(const auto& p:w.at("suffix").as_array()) {
          if(n.plans.size()>=static_cast<std::size_t>(days)) break;
          auto next=advance(n,parse_plan(p));
          if(!next) break;
          n=*next; push(n);
        }
        warm_valid=n.plans.size()==static_cast<std::size_t>(days);
      }
    } catch(const std::exception&) { /* external warm states are hints only */ }
  }
  // Obtain a complete feasible incumbent before widening the macro search.
  // Even if a later sweep is interrupted, the entire suffix remains available.
  Node seed_node=root;
  for(int d=0;d<days && remaining()>0;++d) {
    const int seed_ms=std::min(o.slice_ms*3,std::max(1,remaining()/(days-d)));
    ActionPlan candidate=o.use_strong_seed?strong_propose(seed_node,seed_ms,o.seed):
        propose(seed_node,std::min(o.slice_ms*2,seed_ms),false).front();
    auto next=advance(seed_node,candidate);
    if(!next && o.use_strong_seed && remaining()>0) {
      auto fallback=propose(seed_node,std::min(o.slice_ms,remaining()),false);
      next=advance(seed_node,fallback.front());
    }
    if(!next) break;
    seed_node=*next; push(seed_node);
  }
  const int seed_score=best?best->history.total_servings:-1;
  while(remaining()>10 && expansions<o.max_expansions) {
    bool progressed=false; ++sweeps;
    for(int depth=0;depth<days && remaining()>10 && expansions<o.max_expansions;++depth) {
      auto& layer=layers[depth];
      if(layer.empty()) continue;
      std::sort(layer.begin(),layer.end(),rank);
      auto node=layer.front(); layer.erase(layer.begin());
      if(node->attempts>=o.attempts) continue;
      const int upper=node->history.total_servings+(days-depth)*daily_bound;
      if(best && (upper<best->history.total_servings ||
         (!o.exhaust_budget && upper==best->history.total_servings))) {++bound_prunes;continue;}
      progressed=true; ++expansions; ++node->attempts;
      auto proposals=propose(*node,o.slice_ms,o.use_elites);
      if(o.use_strong_seed && depth==0) {
        for(int k=0;k<2 && remaining()>o.slice_ms;++k)
          proposals.push_back(strong_propose(*node,o.slice_ms,o.seed+1+node->attempts*2+k));
      }
      if(node->attempts<o.attempts) layer.push_back(node);
      for(const auto& p:proposals) {
        if(remaining()<=0) break;
        if(auto child=advance(*node,p)) push(std::move(*child));
      }
    }
    if(!progressed) break;
  }
  if(!best || best->plans.empty()) throw std::runtime_error("no complete maximum-coverage suffix found; refusing infeasible output");
  json::array suffix;
  for(std::size_t i=1;i<best->plans.size();++i) suffix.push_back(to_json(best->plans[i]));
  json::object state{{"policy","chokudai_v2"},{"fingerprint",fingerprint(c,types)},
                     {"source_day",day.day},{"committed_actions",to_json(best->plans.front())},{"suffix",suffix}};
  const auto current=evaluate_candidate(c,day,history,best->plans.front());
  json::object diag{{"score",json::array{std::get<0>(current->value),std::get<1>(current->value),std::get<2>(current->value)}},
                    {"projected_final",json::array{required,required*static_cast<int>(c.day_steps.size()),best->history.total_servings}},
                    {"seed_projected_servings",seed_score},{"warm_valid",warm_valid},
                    {"expansions",expansions},{"evaluated",evaluations},{"rejected_coverage_or_invalid",rejected},
                    {"duplicates",duplicates},{"sweeps",sweeps},{"updates",updates},{"peak_frontier",peak},
                    {"safe_bound_prunes",bound_prunes},{"improvements",improvements},
                    {"exhaust_budget",o.exhaust_budget},
                    {"elapsed_ms",std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-start).count()}};
  return {best->plans.front(),state,diag};
}
}
