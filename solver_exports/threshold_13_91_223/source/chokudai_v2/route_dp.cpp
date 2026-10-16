#include "route_dp.hpp"
#include <algorithm>
#include <bit>
#include <limits>
#include <map>
#include <numeric>

namespace chokudai_v2 {
using namespace hexudon;
namespace {
struct Route {std::vector<int> actions,base_actions; unsigned mask=0, brands=0; int end=0, count=0, time=0, fuel=0;};
struct Label {int time=1000000000, fuel=1000000000; signed char prev=-2;};
}
std::vector<ActionPlan> route_dp_proposals(const MapConfig& c,const DayInfo& day,
 const AgentTypes& types,const ActionPlan& base,std::chrono::steady_clock::time_point deadline) {
  const int n=static_cast<int>(c.spots.size());
  if(n==0 || n>19) return {};
  const int horizon=c.day_steps[day.day];
  std::map<int,int> brand_index;
  for(const auto& spot:c.spots) if(!brand_index.contains(spot.brand))
    brand_index[spot.brand]=static_cast<int>(brand_index.size());
  const unsigned all_brands=(1U<<brand_index.size())-1U;
  std::vector<std::vector<PathResult>> paths(n,std::vector<PathResult>(n));
  std::vector<std::vector<int>> fuel(n,std::vector<int>(n));
  for(int i=0;i<n;++i) for(int j=0;j<n;++j) {
    if(std::chrono::steady_clock::now()>=deadline) return {};
    paths[i][j]=shortest_path(c,c.spots[i].pos,c.spots[j].pos,day.traffics);
    if(paths[i][j].cost<100000000) fuel[i][j]=path_fuel_cost(c,c.spots[i].pos,paths[i][j].directions);
  }
  std::vector<std::vector<Route>> all(types.size());
  const bool all_patrol=std::none_of(types.begin(),types.end(),[](AgentKind k){return k==AgentKind::Refuel;});
  const int remaining_days=static_cast<int>(c.day_steps.size())-day.day;
  for(std::size_t a=0;a<types.size();++a) {
    if(types[a]!=AgentKind::Patrol) continue;
    if(std::chrono::steady_clock::now()>=deadline) return {};
    std::vector<PathResult> starts(n); std::vector<int> starts_fuel(n);
    for(int j=0;j<n;++j) {
      starts[j]=shortest_path(c,day.agents[a].pos,c.spots[j].pos,day.traffics);
      if(starts[j].cost<100000000) starts_fuel[j]=path_fuel_cost(c,day.agents[a].pos,starts[j].directions);
    }
    const int fuel_budget=all_patrol?std::max(1,day.agents[a].fuel/std::max(1,remaining_days)):day.agents[a].fuel;
    const unsigned masks=1U<<n;
    std::vector<Label> dp(static_cast<std::size_t>(masks)*n);
    for(int j=0;j<n;++j) if(starts[j].cost<=horizon && starts_fuel[j]<=fuel_budget) {
      // One wait when already on the first spot guarantees acquisition before departing.
      dp[(1U<<j)*n+j]={std::max(1,starts[j].cost),starts_fuel[j],-1};
    }
    struct End {unsigned mask=0;int count=-1,time=1000000000,fuel=1000000000;};
    std::vector<End> ends(n);
    for(unsigned mask=1;mask<masks;++mask) {
      if((mask&4095U)==0 && std::chrono::steady_clock::now()>=deadline) return {};
      const int count=std::popcount(mask);
      unsigned bits=mask;
      while(bits) {
        const int last=std::countr_zero(bits); bits&=bits-1;
        const auto label=dp[static_cast<std::size_t>(mask)*n+last];
        if(label.time>horizon) continue;
        if(std::tuple{count,-label.time,-label.fuel}>std::tuple{ends[last].count,-ends[last].time,-ends[last].fuel})
          ends[last]={mask,count,label.time,label.fuel};
        unsigned rest=(masks-1)^mask;
        while(rest) {
          const int next=std::countr_zero(rest);rest&=rest-1;
          if(paths[last][next].cost>=100000000) continue;
          const int t=label.time+paths[last][next].cost;
          const int f=label.fuel+fuel[last][next];
          if(t>horizon || f>fuel_budget) continue;
          auto& target=dp[static_cast<std::size_t>(mask|(1U<<next))*n+next];
          // This is heuristic label compression, never used as a safe pruning bound.
          if(std::tie(t,f)<std::tie(target.time,target.fuel)) target={t,f,static_cast<signed char>(last)};
        }
      }
    }
    // Keep high-count routes for many different visited subsets, not merely
    // one route per endpoint. This makes joint patrol allocation meaningful.
    std::vector<End> route_ends;
    route_ends.reserve(masks/4);
    for(unsigned mask=1;mask<masks;++mask) {
      End best;
      unsigned bits=mask;
      while(bits) {
        const int last=std::countr_zero(bits);bits&=bits-1;
        const auto& label=dp[static_cast<std::size_t>(mask)*n+last];
        if(label.time<=horizon && std::tie(label.time,label.fuel)<std::tie(best.time,best.fuel))
          best={mask,std::popcount(mask),label.time,label.fuel}, best.mask=(mask|(static_cast<unsigned>(last)<<24));
      }
      if(best.count>=0) route_ends.push_back(best);
    }
    std::sort(route_ends.begin(),route_ends.end(),[](const End& l,const End& r) {
      return std::tuple{l.count,-l.time,-l.fuel,l.mask}>std::tuple{r.count,-r.time,-r.fuel,r.mask};
    });
    if(route_ends.size()>256) route_ends.resize(256);
    for(const auto& encoded:route_ends) {
      const int end=static_cast<int>(encoded.mask>>24);
      const unsigned visited=encoded.mask&((1U<<n)-1U);
      std::vector<int> order;
      unsigned mask=visited; int last=end;
      while(last>=0) {
        order.push_back(last);
        const auto prev=dp[static_cast<std::size_t>(mask)*n+last].prev;
        mask^=1U<<last;last=prev;
      }
      std::reverse(order.begin(),order.end());
      Route route;route.mask=visited;route.end=c.spots[end].pos;
      route.time=encoded.time;route.fuel=encoded.fuel;
      for(int s=0;s<n;++s) if((visited&(1U<<s))!=0)
        route.brands|=1U<<brand_index.at(c.spots[s].brand);
      int slack=horizon-route.time;
      auto add_extra_wait=[&](int spot) {
        const int extra=std::min({2,slack,std::max(0,c.spots[spot].stocks-1)});
        if(extra>0) {route.actions.push_back(-extra);slack-=extra;}
        return extra;
      };
      int planned=0;
      if(starts[order[0]].directions.empty()) {route.actions.push_back(-1);planned=1;}
      else {route.actions=starts[order[0]].directions;planned=1;}
      planned+=add_extra_wait(order[0]);
      for(std::size_t j=1;j<order.size();++j) {
        const auto& p=paths[order[j-1]][order[j]].directions;
        route.actions.insert(route.actions.end(),p.begin(),p.end());
        ++planned;planned+=add_extra_wait(order[j]);
      }
      if(slack>0) route.actions.push_back(-slack);
      route.count=planned;
      if(starts[order[0]].directions.empty()) route.base_actions.push_back(-1);
      else route.base_actions=starts[order[0]].directions;
      for(std::size_t j=1;j<order.size();++j) {
        const auto& p=paths[order[j-1]][order[j]].directions;
        route.base_actions.insert(route.base_actions.end(),p.begin(),p.end());
      }
      if(horizon>route.time) route.base_actions.push_back(-(horizon-route.time));
      all[a].push_back(std::move(route));
    }
    std::sort(all[a].begin(),all[a].end(),[](const Route& l,const Route& r) {
      return std::tuple{l.count,-l.time,-l.fuel}>std::tuple{r.count,-r.time,-r.fuel};
    });
  }
  std::vector<ActionPlan> result;
  std::vector<std::size_t> patrols;
  for(std::size_t a=0;a<types.size();++a) if(types[a]==AgentKind::Patrol) patrols.push_back(a);
  std::vector<std::pair<int,int>> selections;
  if(patrols.size()==2 && !all[patrols[0]].empty() && !all[patrols[1]].empty()) {
    struct Pair {int i,j,coverage,count,visits,fuel,time;};
    std::vector<Pair> pairs;
    for(int i=0;i<static_cast<int>(all[patrols[0]].size());++i)
      for(int j=0;j<static_cast<int>(all[patrols[1]].size());++j) {
        const auto& x=all[patrols[0]][i];const auto& y=all[patrols[1]][j];
        pairs.push_back({i,j,std::popcount(x.brands|y.brands),x.count+y.count,
                         std::popcount(x.mask)+std::popcount(y.mask),x.fuel+y.fuel,x.time+y.time});
      }
    std::sort(pairs.begin(),pairs.end(),[&](const Pair& l,const Pair& r) {
      return std::tuple{l.coverage==static_cast<int>(brand_index.size()),l.count,l.coverage,-l.fuel,-l.time}>
             std::tuple{r.coverage==static_cast<int>(brand_index.size()),r.count,r.coverage,-r.fuel,-r.time};
    });
    for(const auto& p:pairs) {
      if(selections.size()>=48) break;
      if((all[patrols[0]][p.i].brands|all[patrols[1]][p.j].brands)!=all_brands && !selections.empty()) continue;
      selections.emplace_back(p.i,p.j);
    }
    std::sort(pairs.begin(),pairs.end(),[](const Pair& l,const Pair& r) {
      return std::tuple{l.coverage,l.visits,-l.fuel,-l.time}>
             std::tuple{r.coverage,r.visits,-r.fuel,-r.time};
    });
    for(const auto& p:pairs) {
      if(selections.size()>=96) break;
      const auto key=std::pair{p.i,p.j};
      if(std::find(selections.begin(),selections.end(),key)==selections.end()) selections.push_back(key);
    }
  } else {
    const int count=patrols.empty()?0:static_cast<int>(all[patrols.front()].size());
    for(int i=0;i<std::min(64,count);++i) selections.emplace_back(i,i);
  }
  // Joint stock/coverage and incidental pass-through acquisitions remain
  // authoritative-simulator concerns in the caller.
  for(const auto [first,second]:selections) {
    ActionPlan plan=base;bool changed=false;
    std::vector<int> endpoints(types.size(),-1);
    for(std::size_t k=0;k<patrols.size();++k) {
      const auto a=patrols[k];
      const int chosen=k==0?first:second;
      const auto& r=all[a][chosen%all[a].size()];
      plan[a]=r.actions;endpoints[a]=r.end;changed=true;
    }
    if(changed) result.push_back(plan);
    auto unpadded=plan;
    for(std::size_t k=0;k<patrols.size();++k) {
      const auto a=patrols[k];const int chosen=k==0?first:second;
      unpadded[a]=all[a][chosen%all[a].size()].base_actions;
    }
    if(changed) result.push_back(std::move(unpadded));
    // Finish refuel cars at patrol endpoints, preserving feasible no-refuel routes.
    for(std::size_t patrol=0;patrol<types.size();++patrol) if(endpoints[patrol]>=0) {
      auto staged=plan;
      for(std::size_t r=0;r<types.size();++r) if(types[r]==AgentKind::Refuel) {
        const auto p=shortest_path(c,day.agents[r].pos,endpoints[patrol],day.traffics);
        if(p.cost>=horizon) continue;
        staged[r]=p.directions;staged[r].push_back(-(horizon-p.cost));
      }
      result.push_back(std::move(staged));
    }
  }
  return result;
}
}
