#pragma once
#include "hexudon/internal.hpp"
#include <algorithm>
#include <bit>
#include <chrono>
#include <cstdint>
#include <numeric>

namespace boundary_pool {
using namespace hexudon;
using Clock = std::chrono::steady_clock;
struct Route {
  std::vector<int> actions;
  std::uint64_t brands{};
  unsigned spots{};
  int bowls{}, fuel{}, end{};
};
struct Stats {
  std::int64_t labels{}, transitions{}, combinations{}, validated{};
  std::int64_t expanded{}, candidate_count{}, duplicates{}, heuristic_label_rejects{};
  std::int64_t bound_prunes{};
  std::int64_t precompute_us{}, dp_us{}, packing_us{};
  int route_count{}, improvements{}, accepted_candidates{}, pool_bowl_gain{};
};
struct Candidate { ActionPlan plan; CandidateEvaluation eval; std::string origin; };
inline CandidateValue two_day_value(const CandidateEvaluation& today,const CandidateEvaluation& tomorrow) {
  return {std::get<0>(tomorrow.value),std::get<1>(today.value)+std::get<1>(tomorrow.value),
          std::get<2>(today.value)+std::get<2>(tomorrow.value),std::get<3>(tomorrow.value)};
}

// Single time-first resource label per (visited targets, last target).
// This is a bounded heuristic proposal generator, not an exact RCSP oracle.
inline std::vector<Route> routes(const MapConfig& c, const DayInfo& d,
    const PolicyHistory& h, const ActionPlan& incumbent, int agent,
    Clock::time_point deadline, Stats& stats, int capacity=80) {
  const int n=int(c.spots.size()), horizon=c.day_steps.at(d.day);
  const int start=d.agents[agent].pos, tank=d.agents[agent].fuel;
  std::map<int,int> brand_index;
  for(auto s:c.spots) if(!brand_index.contains(s.brand)) {
    int index=int(brand_index.size()); brand_index[s.brand]=index;
  }
  std::vector<Route> result;
  if(n<1 || n>20 || brand_index.size()>64 || tank>65534 || horizon>65534) return result;
  std::set<std::vector<int>> action_keys;
  auto materialize=[&](std::vector<int> actions) {
    ++stats.candidate_count;
    if(!action_keys.insert(actions).second) {++stats.duplicates;return;}
    // Measure an independent patrol route: other parked patrols must not
    // consume shared stock, and a parked supplier must not make an infeasible
    // no-refuel proposal appear feasible.
    auto isolated=d;isolated.agents={d.agents[agent]};
    auto e=evaluate_candidate(c,isolated,h,ActionPlan{actions});
    if(!e) return;
    Route r; r.actions=std::move(actions); r.end=e->ending_positions[0];
    r.fuel=e->ending_fuel[0];
    for(const auto& event:e->trace.acquisitions)
      for(int j=0;j<n;++j) if(c.spots[j].pos==event.spot_pos) {
        r.spots|=1u<<j; r.brands|=std::uint64_t(1)<<brand_index[c.spots[j].brand];
      }
    r.bowls=std::popcount(r.spots); result.push_back(std::move(r));
  };
  // An incumbent route may rely on the supplier, so don't mislabel it as an
  // independently feasible patrol route. The full incumbent stays elsewhere.
  materialize(incumbent[agent]);
  if(n<1 || n>20 || brand_index.size()>64 || tank>65534 || horizon>65534) return result;
  auto expired=[&]{return Clock::now()>=deadline;};
  auto phase_started=Clock::now();
  std::vector<std::vector<PathResult>> path(n+1,std::vector<PathResult>(n));
  std::vector<std::vector<int>> fuel(n+1,std::vector<int>(n));
  for(int i=0;i<=n;++i) for(int j=0;j<n;++j) {
    int pos=i==n?start:c.spots[i].pos;
    path[i][j]=shortest_path(c,pos,c.spots[j].pos,d.traffics);
    fuel[i][j]=path_fuel_cost(c,pos,path[i][j].directions);
  }
  stats.precompute_us+=std::chrono::duration_cast<std::chrono::microseconds>(Clock::now()-phase_started).count();
  phase_started=Clock::now();
  const unsigned count=1u<<n, all=count-1;
  constexpr std::uint32_t inf=0xffffffffu;
  std::vector<std::uint32_t> dp(std::size_t(count)*n,inf);
  std::vector<std::uint8_t> parent(std::size_t(count)*n,255);
  std::vector<std::vector<unsigned>> layers(n+1);
  for(unsigned mask=1;mask<count;++mask) layers[std::popcount(mask)].push_back(mask);
  for(int i=0;i<n;++i) if(path[n][i].cost<=horizon && fuel[n][i]<=tank)
    dp[(std::size_t(1)<<i)*n+i]=(std::uint32_t(path[n][i].cost)<<16)|fuel[n][i];
  struct End {unsigned mask;int last,visits,time,fuel;};
  std::vector<End> candidates;
  int maximum=0;
  bool stop=false;
  for(int depth=1;depth<=n && !stop;++depth) for(unsigned mask:layers[depth]) {
    if((++stats.labels&4095)==0 && expired()) {stop=true;break;}
    int chosen=-1,best_fuel=65535,best_time=65535;
    for(unsigned ends=mask;ends;ends&=ends-1) {
      int i=std::countr_zero(ends);auto v=dp[std::size_t(mask)*n+i];
      if(v==inf) continue;
      ++stats.expanded;
      int t=v>>16,f=v&65535u;
      if(std::pair{f,t}<std::pair{best_fuel,best_time}) {chosen=i;best_fuel=f;best_time=t;}
      for(unsigned rest=all^mask;rest;rest&=rest-1) {
        int j=std::countr_zero(rest);
        if(path[i][j].cost>horizon-t || fuel[i][j]>tank-f) continue;
        ++stats.transitions;
        auto val=(std::uint32_t(t+path[i][j].cost)<<16)|(f+fuel[i][j]);
        auto at=std::size_t(mask|(1u<<j))*n+j;
        if(val<dp[at]) {dp[at]=val;parent[at]=std::uint8_t(i);}
        else ++stats.heuristic_label_rejects;
      }
    }
    if(chosen>=0) {
      maximum=std::max(maximum,depth);
      candidates.push_back({mask,chosen,depth,best_time,best_fuel});
    }
  }
  std::stable_sort(candidates.begin(),candidates.end(),[](const End& a,const End& b){
    return std::tuple{a.visits,-a.fuel,-a.time}>std::tuple{b.visits,-b.fuel,-b.time};
  });
  std::vector<std::size_t> chosen;
  std::set<std::pair<unsigned,int>> signatures;
  auto keep=[&](std::size_t i) {
    if(signatures.insert({candidates[i].mask,candidates[i].last}).second) chosen.push_back(i);
  };
  // Preserve routes responsible for difficult individual types and endpoints,
  // even when they visit fewer spots than the densest cluster.
  for(auto [brand,index]:brand_index) for(std::size_t k=0;k<candidates.size();++k) {
    bool found=false;
    for(int i=0;i<n;++i) if(c.spots[i].brand==brand && (candidates[k].mask&(1u<<i))) found=true;
    if(found) {keep(k);break;}
  }
  for(int endpoint=0;endpoint<n;++endpoint) for(std::size_t k=0;k<candidates.size();++k)
    if(candidates[k].last==endpoint) {keep(k);break;}
  // Coverage-mask diversity prevents all pool members representing the same
  // convenient cluster. Official objectives are never a weighted sum.
  std::set<std::uint64_t> coverages;
  for(auto i:chosen) {
    std::uint64_t b=0;for(int j=0;j<n;++j)if(candidates[i].mask&(1u<<j))b|=std::uint64_t(1)<<brand_index[c.spots[j].brand];
    coverages.insert(b);
  }
  for(std::size_t k=0;k<candidates.size() && int(chosen.size())<capacity;++k) {
    if(candidates[k].visits<maximum-2) break;
    std::uint64_t b=0;for(int j=0;j<n;++j)if(candidates[k].mask&(1u<<j))b|=std::uint64_t(1)<<brand_index[c.spots[j].brand];
    if(coverages.insert(b).second) keep(k);
  }
  for(auto i:chosen) {
    auto cand=candidates[i];unsigned mask=cand.mask;int last=cand.last;
    std::vector<int> order;
    while(mask) {
      order.push_back(last);int previous=parent[std::size_t(mask)*n+last];
      mask^=1u<<last;last=previous;
    }
    std::reverse(order.begin(),order.end());
    std::vector<int> actions;int previous=n,used=0;
    for(int j:order) {
      const auto& p=path[previous][j];
      actions.insert(actions.end(),p.directions.begin(),p.directions.end());
      used+=p.cost;previous=j;
    }
    if(used<horizon) actions.push_back(used-horizon);
    materialize(std::move(actions));
  }
  stats.route_count+=int(result.size());
  stats.dp_us+=std::chrono::duration_cast<std::chrono::microseconds>(Clock::now()-phase_started).count();
  return result;
}

inline std::vector<Candidate> improve(const MapConfig& c,const DayInfo& d,
    const PolicyHistory& h,const ActionPlan& incumbent,Clock::time_point deadline,
    Stats& stats,int capacity=80,bool boundary_trade=false) {
  std::vector<Candidate> result;
  auto base=evaluate_candidate(c,d,h,incumbent);if(!base)return result;
  result.push_back({incumbent,*base,"alns"});
  std::set<int> brands;for(auto s:c.spots)brands.insert(s.brand);
  const int required=int(brands.size()), n=int(c.spots.size());
  if(n>20 || required>64) return result;
  std::vector<int> patrols;
  for(std::size_t a=0;a<d.agents.size();++a)if(d.agents[a].kind==AgentKind::Patrol)patrols.push_back(int(a));
  if(patrols.empty())return result;
  std::vector<std::vector<Route>> pools;
  for(std::size_t i=0;i<patrols.size();++i) {
    auto now=Clock::now();auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-now).count();
    if(remaining<600)return result;
    auto until=now+std::chrono::milliseconds((remaining-500)/int(patrols.size()-i));
    int route_cap=std::min(capacity,patrols.size()>=5?24:patrols.size()==4?40:128);
    pools.push_back(routes(c,d,h,incumbent,patrols[i],until,stats,route_cap));
    if(pools.back().empty())return result;
    std::stable_sort(pools.back().begin(),pools.back().end(),[](const auto& x,const auto& y){
      return std::tuple{x.bowls,std::popcount(x.brands),x.fuel}>std::tuple{y.bowls,std::popcount(y.brands),y.fuel};
    });
  }
  struct Combination {std::vector<int> ids;int bowls,fuel;};
  auto packing_started=Clock::now();
  std::vector<Combination> finalists;
  std::vector<int> ids(patrols.size());
  std::vector<int> stock_used(n,0),remaining_max(pools.size()+1,0);
  std::vector<std::uint64_t> remaining_types(pools.size()+1,0);
  for(int a=int(pools.size())-1;a>=0;--a) {
    int maximum=0;std::uint64_t mask=0;
    for(const auto& r:pools[a]) {maximum=std::max(maximum,r.bowls);mask|=r.brands;}
    remaining_max[a]=remaining_max[a+1]+maximum;remaining_types[a]=remaining_types[a+1]|mask;
  }
  bool base_complete=std::get<0>(base->value)==required && std::get<1>(base->value)==required;
  int best_count=base_complete?std::get<2>(base->value):0,visit_limit=2000000;
  auto enumerate=[&](auto&& self,std::size_t a,int bowls,int fuel,std::uint64_t mask)->void {
    if(stats.combinations>=visit_limit || Clock::now()>=deadline)return;
    // Safe within this fixed pool of independent, no-refuel routes. Future
    // stock conflicts are relaxed, so the bowl bound can only be optimistic.
    if(bowls+remaining_max[a]<best_count || std::popcount(mask|remaining_types[a])<required) {
      ++stats.bound_prunes;return;
    }
    if(a==pools.size()) {
      ++stats.combinations;
      if(std::popcount(mask)!=required || bowls<best_count)return;
      if(bowls>best_count) {best_count=bowls;finalists.clear();}
      finalists.push_back({ids,bowls,fuel});
      if(finalists.size()>4096) {
        std::sort(finalists.begin(),finalists.end(),[](auto& x,auto& y){return x.fuel>y.fuel;});
        finalists.resize(1024);
      }
      return;
    }
    for(std::size_t i=0;i<pools[a].size();++i) {
      ids[a]=int(i);auto& r=pools[a][i];int gain=0;
      for(unsigned bits=r.spots;bits;bits&=bits-1) {
        int j=std::countr_zero(bits);gain+=stock_used[j]<c.spots[j].stocks;++stock_used[j];
      }
      self(self,a+1,bowls+gain,fuel+r.fuel,mask|r.brands);
      for(unsigned bits=r.spots;bits;bits&=bits-1)--stock_used[std::countr_zero(bits)];
    }
  };
  enumerate(enumerate,0,0,0,0);
  if(std::any_of(stock_used.begin(),stock_used.end(),[](int used){return used!=0;}))
    throw std::logic_error("route-combination stock undo did not restore state");
  std::sort(finalists.begin(),finalists.end(),[](auto& a,auto& b){return a.fuel>b.fuel;});
  std::set<std::vector<int>> endpoints;
  for(auto& f:finalists) {
    if(Clock::now()>=deadline || result.size()>=16)break;
    auto plan=incumbent;std::vector<int> ends;
    for(std::size_t a=0;a<patrols.size();++a) {
      auto& r=pools[a][f.ids[a]];plan[patrols[a]]=r.actions;ends.push_back(r.end);
    }
    if(!endpoints.insert(ends).second)continue;
    auto e=evaluate_candidate(c,d,h,plan);++stats.validated;
    if(e && std::get<0>(e->value)==required && std::get<1>(e->value)==required &&
       (e->value>base->value || (boundary_trade && std::get<2>(e->value)>=std::get<2>(base->value)))) {
      ++stats.accepted_candidates;
      int gain=std::get<2>(e->value)-std::get<2>(base->value);
      stats.improvements+=gain>0;stats.pool_bowl_gain=std::max(stats.pool_bowl_gain,gain);
      result.push_back({std::move(plan),std::move(*e),"free_endpoint_pool"});
    }
  }
  std::stable_sort(result.begin(),result.end(),[](const auto& a,const auto& b){return a.eval.value>b.eval.value;});
  stats.packing_us+=std::chrono::duration_cast<std::chrono::microseconds>(Clock::now()-packing_started).count();
  return result;
}
}
