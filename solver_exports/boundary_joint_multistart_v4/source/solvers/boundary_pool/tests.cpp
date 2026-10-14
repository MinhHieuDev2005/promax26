#include "route_pool.hpp"
#include "boundary_search.hpp"
#include <iostream>
#include <random>
#include <stdexcept>

using namespace boundary_pool;
void require(bool value,const char* message) {if(!value)throw std::runtime_error(message);}
MapConfig fixture() {
  MapConfig c;c.height=3;c.width=4;c.cells.assign(12,Terrain::Plain);
  c.day_steps={12,8};c.day_seconds={45,45};c.agents={0,10};c.fuel_limit=100;
  c.players=2;c.busy_threshold=3;c.jammed_threshold=5;
  c.spots={{0,1,2},{1,3,2},{2,7,2},{3,11,2}};return c;
}
DayInfo initial(const MapConfig& c) {
  DayInfo d;for(int pos:c.agents)d.agents.push_back({AgentKind::Patrol,pos,c.fuel_limit});return d;
}
void test_score_order() {
  require(CandidateValue{2,1,1,0}>CandidateValue{1,99,9999,9999},"global types must dominate");
  require(CandidateValue{2,2,1,0}>CandidateValue{2,1,9999,9999},"daily types must dominate");
  require(CandidateValue{2,2,2,0}>CandidateValue{2,2,1,9999},"fuel must not dominate bowls");
}
void test_paths() {
  auto c=fixture();c.cells[0]=Terrain::Road;
  auto p=shortest_path(c,0,1,{}),q=shortest_path(c,1,0,{});
  require(p.cost==1 && q.cost==2,"cost must be paid on source cell");
  require(path_fuel_cost(c,0,p.directions)==2,"road consumes two fuel");
  auto jammed=shortest_path(c,0,1,{{0,2}});require(jammed.cost==4,"jammed road time");
  c.cells[1]=Terrain::Pond;auto blocked=shortest_path(c,0,1,{});
  require(blocked.directions.empty(),"pond target must be unreachable");
}
void test_stock_and_reflection() {
  auto c=fixture();c.agents={1,1};c.spots={{0,1,1}};auto d=initial(c);
  auto e=evaluate_candidate(c,d,{},wait_plan(2,12));
  require(e && std::get<2>(e->value)==1,"shared stock must not double count");
  c.spots[0].stocks=4;e=evaluate_candidate(c,d,{},wait_plan(2,12));
  require(e && std::get<2>(e->value)==2,"one bowl per patrol/spot/day");
  d.agents[1].kind=AgentKind::Refuel;e=evaluate_candidate(c,d,{},wait_plan(2,12));
  require(e && std::get<2>(e->value)==1,"supply must not acquire");
}
void test_routes_against_exhaustive_permutations() {
  for(int horizon:{4,8,12}) {
    auto c=fixture();c.day_steps[0]=horizon;auto d=initial(c);
    auto incumbent=wait_plan(2,horizon);Stats stats;
    auto pool=routes(c,d,{},incumbent,0,Clock::now()+std::chrono::seconds(2),stats,128);
    int actual=0;for(const auto& r:pool) {
      auto p=incumbent;p[0]=r.actions;
      auto e=evaluate_candidate(c,d,{},p);require(bool(e),"DP route invalid");
      actual=std::max(actual,r.bowls);
    }
    int expected=0;std::vector<int> order{0,1,2,3};
    do {
      int pos=d.agents[0].pos,time=0;std::vector<int> actions;
      for(int target:order) {
        auto p=shortest_path(c,pos,c.spots[target].pos,{});
        if(time+p.cost>horizon)break;
        actions.insert(actions.end(),p.directions.begin(),p.directions.end());time+=p.cost;pos=c.spots[target].pos;
        auto plan=incumbent;plan[0]=actions;if(time<horizon)plan[0].push_back(time-horizon);
        auto e=evaluate_candidate(c,d,{},plan);require(bool(e),"enumerated path invalid");
        int count=0;for(auto event:e->trace.acquisitions)count+=event.agent==0;
        expected=std::max(expected,count);
      }
    }while(std::next_permutation(order.begin(),order.end()));
    require(actual==expected,"DP disagrees with exhaustive target orders on fuel-unconstrained fixture");
  }
}
void test_no_fuel_and_joint_validation() {
  auto c=fixture();auto d=initial(c);d.agents[0].fuel=0;auto incumbent=wait_plan(2,12);Stats stats;
  auto pool=routes(c,d,{},incumbent,0,Clock::now()+std::chrono::seconds(2),stats,32);
  for(auto& r:pool) {auto p=incumbent;p[0]=r.actions;require(bool(evaluate_candidate(c,d,{},p)),"zero fuel path invalid");}
  auto candidates=improve(c,d,{},incumbent,Clock::now()+std::chrono::seconds(2),stats);
  require(!candidates.empty(),"fallback incumbent lost");
  for(auto& r:candidates)require(bool(evaluate_candidate(c,d,{},r.plan)),"joint route plan invalid");
}
void test_boundary_macros_are_valid() {
  auto c=fixture();c.day_steps[0]=20;auto d=initial(c);Stats stats;
  auto roots=improve(c,d,{},wait_plan(2,20),Clock::now()+std::chrono::seconds(2),stats);
  require(!roots.empty(),"missing macro seed");BoundaryStats searched;
  auto candidates=boundary_search(c,d,{},roots.front(),Clock::now()+std::chrono::milliseconds(250),searched,4,2);
  require(searched.expanded>0,"Chokudai did not expand");
  for(auto& r:candidates) {
    auto e=evaluate_candidate(c,d,{},r.plan);require(bool(e),"boundary macro invalid");
    require(std::get<1>(e->value)==4,"macro lost required types");
    require(e->value==r.eval.value,"cached evaluation disagrees");
  }
}
void test_stock_bound_and_undo_randomized() {
  std::mt19937 random(71);
  for(int repetition=0;repetition<24;++repetition) {
    auto c=fixture();c.agents={0,6,10};c.day_steps[0]=24;
    int expected=0;for(auto& s:c.spots) {s.stocks=1+random()%4;expected+=std::min(3,s.stocks);}
    auto d=initial(c);Stats stats;
    auto results=improve(c,d,{},wait_plan(3,24),Clock::now()+std::chrono::seconds(2),stats,128);
    require(!results.empty(),"empty stock-bound result");
    require(std::get<2>(results.front().eval.value)==expected,"stock accounting / optimistic bound mismatch");
    for(auto& r:results)require(bool(evaluate_candidate(c,d,{},r.plan)),"random joint route invalid");
  }
}
void test_coverage_repair_may_reduce_bowls() {
  auto c=fixture();c.height=1;c.width=8;c.cells.assign(8,Terrain::Plain);
  c.agents={0,5};c.day_steps[0]=8;
  c.spots={{0,1,2},{0,2,2},{0,3,2},{0,4,2},{1,7,2}};
  auto d=initial(c);ActionPlan incomplete{{2,2,2,2},{5,5,5,5}};
  auto before=evaluate_candidate(c,d,{},incomplete);
  require(before && std::get<1>(before->value)==1 && std::get<2>(before->value)==8,"bad coverage regression fixture");
  Stats stats;auto result=improve(c,d,{},incomplete,Clock::now()+std::chrono::seconds(2),stats,128);
  require(std::get<0>(result.front().eval.value)==2 && std::get<1>(result.front().eval.value)==2,"bowl bound pruned coverage repair");
  require(std::get<2>(result.front().eval.value)==6,"coverage repair should prefer six feasible bowls to eight incomplete bowls");
  CandidateEvaluation tomorrow;tomorrow.value={2,2,5,10};
  require(two_day_value(result.front().eval,tomorrow)>two_day_value(*before,tomorrow),"lookahead must compare coverage before bowl sum");
}
int main() {
  try {test_score_order();test_paths();test_stock_and_reflection();
    test_routes_against_exhaustive_permutations();test_no_fuel_and_joint_validation();test_boundary_macros_are_valid();
    test_stock_bound_and_undo_randomized();
    test_coverage_repair_may_reduce_bowls();
    std::cout<<"8 test groups passed (including 24 randomized stock/undo cases)\n";
  }catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
