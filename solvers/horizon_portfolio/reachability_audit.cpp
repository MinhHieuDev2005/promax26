// Optimistic bounds computed from the unchanged C++ movement primitives.
// This is diagnostic evidence about this input/model, never a solver score.
#include "hexudon/core.hpp"
#include <algorithm>
#include <bit>
#include <iostream>
#include <iterator>
#include <queue>
#include <limits>
using namespace hexudon;
constexpr int INF = 100000000;

std::vector<int> distance(const MapConfig& c, int start, bool fuel) {
  std::vector<int> d(c.cells.size(), INF);
  std::priority_queue<std::pair<int,int>, std::vector<std::pair<int,int>>, std::greater<>> q;
  d[start] = 0; q.push({0,start});
  while (!q.empty()) {
    auto [v,p] = q.top(); q.pop(); if (v != d[p]) continue;
    int w = fuel ? terrain_fuel(c,p) : terrain_time(c,p,{});
    for (int dir=0;dir<6;++dir) {
      auto n = neighbor(c,p,dir);
      if (!n || c.cells[*n] == Terrain::Pond) continue;
      if (v+w < d[*n]) {d[*n]=v+w;q.push({v+w,*n});}
    }
  }
  return d;
}
std::vector<int> min_cost(const MapConfig& c, bool fuel, int start = -1) {
  int n = int(c.spots.size());
  if (n > 21 || n == 0) throw std::runtime_error("audit supports 1..21 spots");
  std::vector<std::vector<int>> costs;
  for (auto s:c.spots) costs.push_back(distance(c,s.pos,fuel));
  std::vector<int> dp((std::size_t(1)<<n)*n, INF), best(n+1,INF);
  best[0]=0;
  const auto origin = start < 0 ? std::vector<int>() : distance(c,start,fuel);
  for (int i=0;i<n;++i) dp[(std::size_t(1)<<i)*n+i]=start<0?0:origin[c.spots[i].pos];
  unsigned all=(1u<<n)-1;
  for (unsigned mask=1;mask<=all;++mask) {
    int count=std::popcount(mask);
    for (unsigned ends=mask;ends;ends&=ends-1) {
      int i=std::countr_zero(ends), current=dp[std::size_t(mask)*n+i];
      best[count]=std::min(best[count],current);
      if (current==INF) continue;
      for (unsigned rest=all^mask;rest;rest&=rest-1) {
        int j=std::countr_zero(rest);
        auto& next=dp[std::size_t(mask|(1u<<j))*n+j];
        next=std::min(next,current+costs[i][c.spots[j].pos]);
      }
    }
  }
  return best;
}
int main() {
  try {
    auto raw=json::parse(std::string{std::istreambuf_iterator<char>(std::cin),{}});
    auto c=parse_map_config(raw.as_object().contains("config")?raw.as_object().at("config"):raw);
    auto time=min_cost(c,false), fuel=min_cost(c,true);
    json::array bounds;
    int agents=int(c.agents.size()), days=int(c.day_steps.size());
    for (int patrols=1;patrols<=agents;++patrols) {
      json::array daily;
      int total=0;
      for (int horizon:c.day_steps) {
        int max_visits=0;
        for (int k=0;k<int(time.size());++k) if(time[k]<=horizon) max_visits=k;
        int stock=0;for(auto s:c.spots) stock+=std::min(s.stocks,patrols);
        int bound=std::min(stock,patrols*max_visits);
        daily.push_back(bound);total+=bound;
      }
      if(patrols==agents) {
        int budget=agents*c.fuel_limit;
        std::vector<int> dp(budget+1,-INF);dp[0]=0;
        for(int route=0;route<agents*days;++route) {
          std::vector<int> next(budget+1,-INF);
          for(int b=0;b<=budget;++b) if(dp[b]>=0)
            for(int k=0;k<int(fuel.size());++k) if(fuel[k]<=budget-b)
              next[b+fuel[k]]=std::max(next[b+fuel[k]],dp[b]+k);
          dp=std::move(next);
        }
        total=std::min(total,*std::max_element(dp.begin(),dp.end()));
      }
      bounds.push_back(json::object{{"patrols",patrols},{"free_start_daily_bounds",daily},{"match_bound",total}});
    }
    json::array t,f;for(auto x:time)t.push_back(x);for(auto x:fuel)f.push_back(x);
    std::cout<<json::serialize(json::object{{"kind","optimistic_model_bound"},{"time_min_by_visits",t},{"fuel_min_by_visits",f},{"roles",bounds}})<<'\n';
  } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
