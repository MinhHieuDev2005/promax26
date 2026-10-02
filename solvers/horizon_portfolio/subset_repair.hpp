#pragma once
#include "hexudon/internal.hpp"
#include <bit>
#include <chrono>
#include <cstdint>
#include <limits>
#include <set>

namespace horizon_repair {
using namespace hexudon;
// Subset enumeration with one time-first resource label per (mask,last).
// This is deliberately a heuristic under fuel constraints, not exact RCSP.
// Only no-refuel patrol paths are proposed; joint simulation remains decisive.
inline ActionPlan improve(const MapConfig& c, const DayInfo& day,
                          const PolicyHistory& history, const AgentTypes& types,
                          ActionPlan incumbent,
                          std::chrono::steady_clock::time_point deadline) {
  const int n=int(c.spots.size());
  auto best=evaluate_candidate(c,day,history,incumbent);
  if(!best || n<1 || n>20) return incumbent;
  auto expired=[&]{return std::chrono::steady_clock::now()>=deadline;};
  const int horizon=c.day_steps[day.day];
  if(horizon>60000 || c.fuel_limit>60000) return incumbent;
  std::vector<std::vector<PathResult>> paths(n,std::vector<PathResult>(n));
  std::vector<std::vector<int>> fuel(n,std::vector<int>(n));
  for(int i=0;i<n;++i) for(int j=0;j<n;++j) {
    paths[i][j]=shortest_path(c,c.spots[i].pos,c.spots[j].pos,day.traffics);
    fuel[i][j]=path_fuel_cost(c,c.spots[i].pos,paths[i][j].directions);
  }
  std::vector<std::vector<std::vector<int>>> routes(types.size());
  for(std::size_t a=0;a<types.size();++a) {
    routes[a].push_back(incumbent[a]);
    if(types[a]!=AgentKind::Patrol || expired()) continue;
    int start=day.agents[a].pos, end=best->ending_positions[a], tank=day.agents[a].fuel;
    std::vector<PathResult> from(n),to(n);
    std::vector<int> ff(n),tf(n);
    for(int i=0;i<n;++i) {
      from[i]=shortest_path(c,start,c.spots[i].pos,day.traffics);
      to[i]=shortest_path(c,c.spots[i].pos,end,day.traffics);
      ff[i]=path_fuel_cost(c,start,from[i].directions);
      tf[i]=path_fuel_cost(c,c.spots[i].pos,to[i].directions);
    }
    const unsigned count=1u<<n, all=count-1;
    constexpr std::uint32_t inf=0xffffffffu;
    std::vector<std::uint32_t> dp(std::size_t(count)*n,inf);
    std::vector<std::uint8_t> parent(std::size_t(count)*n,255);
    for(int i=0;i<n;++i) if(from[i].cost<=horizon && ff[i]<=tank &&
        (start==c.spots[i].pos || !from[i].directions.empty()))
      dp[(std::size_t(1)<<i)*n+i]=(std::uint32_t(from[i].cost)<<16)|ff[i];
    struct Candidate {unsigned mask;int last,visits,slack;};
    std::vector<Candidate> candidates;
    int max_visits=0;
    int patrols_left=0;
    for(std::size_t i=a;i<types.size();++i) patrols_left+=types[i]==AgentKind::Patrol;
    auto available=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-std::chrono::steady_clock::now()).count();
    auto route_deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(std::max<long long>(1,(available-700)/std::max(1,patrols_left)));
    for(unsigned mask=1;mask<count;++mask) {
      if((mask&4095u)==0 && std::chrono::steady_clock::now()>=route_deadline) break;
      int visits=std::popcount(mask);
      int chosen=-1,slack=-1;
      for(unsigned ends=mask;ends;ends&=ends-1) {
        int i=std::countr_zero(ends);auto v=dp[std::size_t(mask)*n+i];
        if(v==inf) continue;
        int t=int(v>>16),f=int(v&65535u);
        if(t+to[i].cost<=horizon && f+tf[i]<=tank &&
            (end==c.spots[i].pos || !to[i].directions.empty()) && tank-f-tf[i]>slack) {
          chosen=i;slack=tank-f-tf[i];
        }
        for(unsigned rest=all^mask;rest;rest&=rest-1) {
          int j=std::countr_zero(rest);
          if(paths[i][j].directions.empty()) continue;
          int nt=t+paths[i][j].cost,nf=f+fuel[i][j];
          if(nt>horizon || nf>tank) continue;
          auto value=(std::uint32_t(nt)<<16)|nf;
          auto index=std::size_t(mask|(1u<<j))*n+j;
          if(value<dp[index]) {dp[index]=value;parent[index]=std::uint8_t(i);}
        }
      }
      if(chosen>=0 && visits>=max_visits) {
        if(visits>max_visits) {max_visits=visits;candidates.clear();}
        candidates.push_back({mask,chosen,visits,slack});
      }
    }
    std::sort(candidates.begin(),candidates.end(),[](const auto& x,const auto& y){return x.slack>y.slack;});
    if(candidates.size()>8)candidates.resize(8);
    for(auto cand:candidates) {
      unsigned mask=cand.mask;int last=cand.last;
      std::vector<int> order;
      while(mask) {
        order.push_back(last);int previous=parent[std::size_t(mask)*n+last];
        mask^=1u<<last;last=previous;
      }
      std::reverse(order.begin(),order.end());
      std::vector<int> route=from[order.front()].directions;
      int used=from[order.front()].cost;
      for(std::size_t i=1;i<order.size();++i) {
        const auto& p=paths[order[i-1]][order[i]];
        route.insert(route.end(),p.directions.begin(),p.directions.end());used+=p.cost;
      }
      const auto& tail=to[order.back()];
      route.insert(route.end(),tail.directions.begin(),tail.directions.end());used+=tail.cost;
      if(used<horizon)route.push_back(used-horizon);
      routes[a].push_back(std::move(route));
    }
  }
  ActionPlan working=incumbent;
  auto visit=[&](auto&& self,std::size_t a)->void {
    if(expired())return;
    if(a==routes.size()) {
      auto e=evaluate_candidate(c,day,history,working);
      if(e && e->value>best->value) {best=std::move(e);incumbent=working;}
      return;
    }
    for(const auto& r:routes[a]) {working[a]=r;self(self,a+1);if(expired())break;}
  };
  visit(visit,0);
  return incumbent;
}
}
