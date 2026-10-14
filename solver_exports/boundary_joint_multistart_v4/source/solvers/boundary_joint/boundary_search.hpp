#pragma once
#include "route_pool.hpp"
#include <queue>

namespace boundary_joint {
struct BoundaryStats {int expanded{}, generated{}, duplicates{}, rejected{}, queued{};};

// Bounded Chokudai over complete-plan tail macros. Layers mean the number of
// different vehicles modified, NOT individual movement depth. Unexpanded
// nodes survive sweeps; queue caps and endpoint buckets are heuristic pruning.
// Only the exact full action sequence establishes feasibility/official score.
inline std::vector<Candidate> boundary_search(const MapConfig& c,const DayInfo& d,
    const PolicyHistory& h,const Candidate& incumbent,Clock::time_point deadline,
    BoundaryStats& stats,int width=12,int max_depth=2) {
  struct Node {Candidate candidate;unsigned changed{};};
  const int horizon=c.day_steps[d.day],count=int(d.agents.size());
  if(count>16)return {};
  std::set<int> brands;for(auto s:c.spots)brands.insert(s.brand);
  bool base_complete=std::get<0>(incumbent.eval.value)==int(brands.size()) &&
                     std::get<1>(incumbent.eval.value)==int(brands.size());
  std::vector<std::vector<Node>> layers(max_depth+1);
  layers[0].push_back({incumbent,0});
  std::set<ActionPlan> seen{incumbent.plan};
  std::vector<Candidate> archive;
  std::set<std::vector<int>> endpoints;
  auto rank=[](const Node& a,const Node& b){return a.candidate.eval.value>b.candidate.eval.value;};
  auto expired=[&]{return Clock::now()>=deadline;};
  bool progress=true;
  while(progress && !expired()) {
    progress=false;
    for(int depth=0;depth<max_depth && !expired();++depth) {
      if(layers[depth].empty())continue;
      std::stable_sort(layers[depth].begin(),layers[depth].end(),rank);
      Node node=std::move(layers[depth].front());layers[depth].erase(layers[depth].begin());
      ++stats.expanded;progress=true;
      // Supply-first is move ordering, not a forced role assignment.
      std::vector<int> vehicles(count);std::iota(vehicles.begin(),vehicles.end(),0);
      std::stable_sort(vehicles.begin(),vehicles.end(),[&](int a,int b){return int(d.agents[a].kind)>int(d.agents[b].kind);});
      for(int a:vehicles) {
        if(node.changed&(1u<<a))continue;
        for(int tail:{12,20,28}) {
          if(expired())break;
          int elapsed=0,pos=d.agents[a].pos;std::vector<int> prefix;
          for(int action:node.candidate.plan[a]) {
            int cost=action<0?-action:terrain_time(c,pos,d.traffics);
            if(elapsed+cost>std::max(0,horizon-tail)) {
              // Split a wait, preserving the prefix up to the cut turn.
              if(action<0 && elapsed<horizon-tail) {prefix.push_back(elapsed-(horizon-tail));elapsed=horizon-tail;}
              break;
            }
            prefix.push_back(action);elapsed+=cost;
            if(action>=0)pos=*neighbor(c,pos,action);
          }
          for(auto target:c.spots) {
            if(expired())break;
            auto path=shortest_path(c,pos,target.pos,d.traffics);
            if(path.cost>horizon-elapsed)continue;
            auto plan=node.candidate.plan;plan[a]=prefix;
            plan[a].insert(plan[a].end(),path.directions.begin(),path.directions.end());
            if(elapsed+path.cost<horizon)plan[a].push_back(elapsed+path.cost-horizon);
            ++stats.generated;
            if(!seen.insert(plan).second) {++stats.duplicates;continue;}
            auto e=evaluate_candidate(c,d,h,plan);
            if(!e || std::get<0>(e->value)!=int(brands.size()) || std::get<1>(e->value)!=int(brands.size()) ||
                (base_complete && std::get<2>(e->value)<std::get<2>(incumbent.eval.value)-1)) {++stats.rejected;continue;}
            Candidate cand{std::move(plan),std::move(*e),depth==0?"tail_macro":"joint_tail_macro"};
            if(endpoints.insert(cand.eval.ending_positions).second)archive.push_back(cand);
            layers[depth+1].push_back({std::move(cand),node.changed|(1u<<a)});++stats.queued;
          }
        }
      }
      auto& next=layers[depth+1];
      std::stable_sort(next.begin(),next.end(),rank);
      std::set<std::vector<int>> diverse;
      std::vector<Node> bounded;
      for(auto& x:next)if(diverse.insert(x.candidate.eval.ending_positions).second) {
        bounded.push_back(std::move(x));if(int(bounded.size())==width)break;
      }
      next=std::move(bounded);
    }
  }
  return archive;
}
}
