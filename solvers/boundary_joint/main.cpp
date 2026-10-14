#include "route_pool.hpp"
#include "config.hpp"
#include "boundary_search.hpp"
#include <cstdlib>
#include <iostream>
#include <iterator>

using namespace boundary_joint;
#ifndef BOUNDARY_DEFAULT_PREVIEW
#define BOUNDARY_DEFAULT_PREVIEW 1
#endif
ActionPlan parse_plan(const json::value& v) {
  ActionPlan p;for(const auto& row:v.as_array()) {
    p.emplace_back();for(const auto& a:row.as_array())p.back().push_back(a.to_number<int>());
  }return p;
}
int main() {
 try {
#ifdef _WIN32
  _putenv_s("HEXUDON_THREADS","1");
#else
  setenv("HEXUDON_THREADS","1",1);
#endif
  const auto started=Clock::now();
  auto input=json::parse(std::string{std::istreambuf_iterator<char>(std::cin),{}});
  const auto& root=input.as_object();auto config=parse_map_config(root.at("config"));validate_config(config);
  json::object empty;const auto& search=root.if_contains("search")?root.at("search").as_object():empty;
  auto integer=[&](const char* key,int value){auto p=search.if_contains(key);return p?p->to_number<int>():value;};
  auto text_option=[&](const char* key,const char* value){auto p=search.if_contains(key);return p&&p->is_string()?std::string(p->as_string().c_str()):std::string(value);};
  int budget=std::clamp(integer("timeLimitMs",45000),1,45000),seed=integer("randomSeed",1);
  if(root.if_contains("op") && root.at("op").as_string()=="roles") {
    SearchLimits limits;limits.time_limit_ms=std::min(2000,budget);
    std::cout<<json::serialize(json::object{{"ok",true},{"roles",to_json(select_agent_types("alns",config,limits))}})<<'\n';return 0;
  }
  auto encoded=root.at(root.contains("day_info")?"day_info":"state");
  if(!root.contains("day_info"))encoded.as_object()["day"]=encoded.as_object().at("day").to_number<int>()-1;
  auto day=parse_day_info(encoded);auto history=root.if_contains("history")?parse_history(root.at("history")):PolicyHistory{};
  const bool target503_mode = integer("target503Mode",1) != 0;
  static constexpr std::array<int,6> target503_bucket_schedule{8,6,8,6,6,4};
  const int scheduled_buckets = day.day>=0 && day.day<int(target503_bucket_schedule.size())
      ? target503_bucket_schedule[std::size_t(day.day)] : 0;
  const int objective_brand_buckets = std::clamp(
      integer("objectiveBrandBuckets",target503_mode?scheduled_buckets:0),0,64);
  if(objective_brand_buckets>0) {
    for(auto& spot:config.spots)
      spot.brand=((spot.brand%objective_brand_buckets)+objective_brand_buckets)%objective_brand_buckets;
    std::set<int> mapped;
    for(int brand:history.distinct_brands)
      mapped.insert(((brand%objective_brand_buckets)+objective_brand_buckets)%objective_brand_buckets);
    history.distinct_brands=std::move(mapped);
  }
  if(day.day<0 || day.day>=int(config.day_steps.size()) || day.agents.size()!=config.agents.size())throw std::runtime_error("invalid day/agents");
  if(day.ends_at) {
    double now=std::chrono::duration<double>(std::chrono::system_clock::now().time_since_epoch()).count();
    budget=std::min(budget,std::max(1,int((*day.ends_at-now)*1000)-900));
  }
  auto deadline=started+std::chrono::milliseconds(std::max(1,budget-std::min(3000,budget/5)));
  auto left=[&]{return int(std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count());};
  AgentTypes types;for(auto a:day.agents)types.push_back(a.kind);
  std::set<int> brands;for(auto s:config.spots)brands.insert(s.brand);int required=int(brands.size());
  bool has_next=day.day+1<int(config.day_steps.size());
  const int boundary_trade_percent = std::clamp(
      integer("boundaryTradePercent",target503_mode?90:80), 0, 100);
  const bool boundary_trade_always = integer("boundaryTradeAlways",0) != 0;
  bool boundary_trade=has_next && integer("boundaryTrade",1) &&
      (boundary_trade_always ||
       config.day_steps[day.day+1]*100 <
           config.day_steps[day.day]*boundary_trade_percent);
  auto generate=[&](const DayInfo& d,const PolicyHistory& h,int ms,int s) {
    SearchLimits l;l.time_limit_ms=std::max(1,std::min(ms,left()));l.random_seed=s;
    l.min_iterations=0;l.max_iterations=1000000;l.stagnation_iterations=0;
    return plan_day(text_option("policy","alns"),config,d,h,types,l);
  };
  const int baseline_starts = boundary_trade
      ? std::clamp(integer("boundaryBaselineStarts",1),1,4)
      : std::clamp(integer("baselineStarts",1),1,4);
  ActionPlan baseline;
  std::optional<CandidateEvaluation> base;
  std::vector<Candidate> restart_candidates;
  for(int start=0;start<baseline_starts && left()>1000;++start) {
    auto proposal=generate(day,history,
        std::min(integer("baselineMs",8000),std::max(1,left()/(baseline_starts-start))),
        seed+int(std::uint32_t(start)*0x9e3779b9U));
    auto evaluation=evaluate_candidate(config,day,history,proposal);
    if(evaluation)restart_candidates.push_back(
        {proposal,*evaluation,"alns_restart_"+std::to_string(start)});
    if(evaluation && (!base || evaluation->value>base->value)) {
      baseline=std::move(proposal);base=std::move(evaluation);
    }
  }
  auto baseline_done=Clock::now();
  if(!base)throw std::runtime_error("ALNS returned invalid plan");
  auto cfg=root.at("config").as_object();cfg.erase("startsAt");auto fingerprint=json::serialize(cfg);
  if(auto w=root.if_contains("planner_state");w && w->is_object())try {
    const auto& o=w->as_object();
    if(o.at("fingerprint").as_string()==fingerprint && o.at("source_day").to_number<int>()==day.day-1 &&
      !history.submitted_actions.empty() && parse_plan(o.at("committed"))==history.submitted_actions.back()) {
      auto p=parse_plan(o.at("next_plan"));auto e=evaluate_candidate(config,day,history,p);
      if(e && e->value>base->value) {baseline=std::move(p);base=std::move(e);}
    }
  }catch(const std::exception&){}
  std::vector<Candidate> candidates{{baseline,*base,"alns"}};
  for(auto& candidate:restart_candidates)
    if(candidate.plan!=baseline)candidates.push_back(std::move(candidate));
  Stats stats;
  const auto profile=configuration(config.width*config.height);
  const int subset_target_limit =
      std::clamp(integer("subsetTargetLimit",profile.subset_target_limit),
                 profile.subset_target_limit,64);
  // Reserve enough time to test endpoint changes against their next-day cost.
  int reserve=has_next?13000:1000;
  const int endpoint_quota=std::clamp(integer("endpointQuota",3),0,6);
  const int bowl_slack=boundary_trade?std::clamp(
      integer("bowlSlack",target503_mode?2:1),0,2):0;
  if(left()>reserve+2000 && integer("enablePool",1) &&
     int(config.spots.size())<=subset_target_limit) {
    auto pool_deadline=deadline-std::chrono::milliseconds(reserve);
    candidates=improve(config,day,history,baseline,pool_deadline,stats,std::clamp(integer("poolCapacity",profile.route_capacity),8,128),boundary_trade,endpoint_quota,bowl_slack);
  }
  BoundaryStats boundary_stats;
  if(boundary_trade && integer("enableBoundarySearch",target503_mode?1:0) && left()>14000) {
    auto until=std::min(deadline-std::chrono::milliseconds(12000),Clock::now()+std::chrono::milliseconds(1800));
    auto tails=boundary_search(config,day,history,{baseline,*base,"alns"},until,boundary_stats);
    std::stable_sort(tails.begin(),tails.end(),[](const auto& a,const auto& b){return a.eval.value>b.eval.value;});
    // Keep exact validated alternatives. They are NOT accepted until a
    // continuation comparison including the original incumbent completes.
    for(auto& tail:tails)candidates.push_back(std::move(tail));
  }
  auto next_context=[&](const Candidate& cand) {
    auto next=day;next.day++;next.ends_at.reset();next.others.clear();
    auto h=history;h.submitted_actions.push_back(cand.plan);
    for(const auto& event:cand.eval.trace.acquisitions)
      if(auto spot=spot_at(config,event.spot_pos))h.distinct_brands.insert(spot->brand);
    h.cumulative_daily_types+=std::get<1>(cand.eval.value);h.total_servings+=std::get<2>(cand.eval.value);
    for(std::size_t a=0;a<types.size();++a)next.agents[a]={types[a],cand.eval.ending_positions[a],cand.eval.ending_fuel[a]};
    return std::pair{std::move(next),std::move(h)};
  };
  // Cheap, feasible LOWER estimates for next-day quality. They rank rollout
  // priorities only, and must never be used as an admissible upper bound.
  std::map<int,Candidate> previews;
  int preview_attempts=0;auto preview_started=Clock::now();
  if(boundary_trade && integer("fastFuture",BOUNDARY_DEFAULT_PREVIEW)) {
    // Interleave bowl tiers; a today-first sorted list must not consume every
    // preview slot before the intended lower-bowl staging candidates.
    std::map<int,std::vector<int>,std::greater<int>> tiers;
    for(std::size_t i=0;i<candidates.size();++i)tiers[std::get<2>(candidates[i].eval.value)].push_back(int(i));
    std::vector<int> preview_order;
    for(std::size_t round=0;round<candidates.size();++round)
      for(auto& [bowls,ids]:tiers)if(round<ids.size())preview_order.push_back(ids[round]);
    for(int i:preview_order) {
      if(preview_attempts>=16 || left()<=16000)break;
      auto [next,h]=next_context(candidates[i]);Stats ignored;
      auto quick=improve(config,next,h,wait_plan(types.size(),config.day_steps[next.day]),
                         std::min(deadline-std::chrono::milliseconds(15500),Clock::now()+std::chrono::milliseconds(2200)),
                         ignored,std::clamp(integer("poolCapacity",profile.route_capacity),8,128),false,std::min(endpoint_quota,1));
      ++preview_attempts;
      if(!quick.empty() && std::get<0>(quick.front().eval.value)==required && std::get<1>(quick.front().eval.value)==required)
        previews.emplace(int(i),std::move(quick.front()));
    }
  }
  auto preview_ms=std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-preview_started).count();
  int selected=0;ActionPlan next_plan;json::array rollouts;
  if(has_next)for(std::size_t i=0;i<candidates.size();++i)if(candidates[i].origin=="alns")selected=int(i);
  if(has_next && candidates.size()>1 && left()>2500) {
    // Always include the incumbent even when current-day ranking puts it last.
    std::vector<int> trials;
    int max_trials=std::clamp(integer("rolloutCandidates",4),2,12);
    std::map<std::string,std::vector<int>> families;
    for(std::size_t i=0;i<candidates.size();++i)if(candidates[i].origin!="alns")families[candidates[i].origin].push_back(int(i));
    for(int round=0;int(trials.size())<max_trials-1;++round) {
      bool progress=false;
      for(auto& [name,alternatives]:families) {
        int slots=std::max(1,(max_trials-1+int(families.size())-1)/int(families.size()));
        std::size_t k=slots==1?0:std::size_t(round)*(alternatives.size()-1)/std::max(1,slots-1);
        if(k>=alternatives.size())continue;
        int id=alternatives[k];
        if(std::find(trials.begin(),trials.end(),id)==trials.end()) {trials.push_back(id);progress=true;}
        if(int(trials.size())>=max_trials-1)break;
      }
      if(!progress)break;
    }
    for(std::size_t i=0;i<candidates.size();++i)if(candidates[i].origin=="alns")trials.insert(trials.begin(),int(i));
    if(!previews.empty()) {
      std::vector<int> ranked;
      for(const auto& [i,p]:previews)if(candidates[i].origin!="alns")ranked.push_back(i);
      auto quality=[&](int i) {
        return two_day_value(candidates[i].eval,previews.at(i).eval);
      };
      std::stable_sort(ranked.begin(),ranked.end(),[&](int a,int b){return quality(a)>quality(b);});
      std::vector<int> scheduled;
      for(int i:trials)if(candidates[i].origin=="alns")scheduled.push_back(i);
      for(int i:ranked)if(int(scheduled.size())<max_trials)scheduled.push_back(i);
      // Unscored candidates were NOT proven inferior. Keep one exploratory
      // slot if any remain, while always retaining the incumbent comparison.
      for(int i:trials)if(!previews.contains(i) && candidates[i].origin!="alns") {
        if(int(scheduled.size())>=max_trials)scheduled.back()=i;else scheduled.push_back(i);
        break;
      }
      trials=std::move(scheduled);
    }
    int best_total=-1;CandidateValue best_projected{-1,-1,-1,-1};
    int slice=std::min(4000,std::max(200,(left()-500)/int(trials.size())));
    for(int i:trials) {
      if(left()<slice+150)break;
      auto& cand=candidates[i];auto [next,h]=next_context(cand);
      auto p=generate(next,h,slice,seed);auto e=evaluate_candidate(config,next,h,p);
      if(auto found=previews.find(i);found!=previews.end() && (!e || found->second.eval.value>e->value)) {
        p=found->second.plan;e=found->second.eval;
      }
      if(!e || std::get<0>(e->value)!=required || std::get<1>(e->value)!=required) {
        // A trade is meaningful only after a VALID incumbent continuation.
        if(cand.origin=="alns")break;
        continue;
      }
      int today=std::get<2>(cand.eval.value),tomorrow=std::get<2>(e->value),total=today+tomorrow;
      rollouts.push_back(json::object{{"origin",cand.origin},{"today",today},{"tomorrow",tomorrow},{"sum",total},
        {"boundary_positions",json::value_from(cand.eval.ending_positions)},{"boundary_fuel",json::value_from(cand.eval.ending_fuel)}});
      auto projected=two_day_value(cand.eval,*e);
      if(projected>best_projected) {
        best_total=total;best_projected=projected;selected=i;next_plan=std::move(p);
      }
    }
    if(best_total<0)for(std::size_t i=0;i<candidates.size();++i)if(candidates[i].origin=="alns")selected=int(i);
  }
  const auto& winner=candidates.at(selected);
  json::value state=nullptr;
  if(!next_plan.empty())state=json::object{{"fingerprint",fingerprint},{"source_day",day.day},{"committed",to_json(winner.plan)},{"next_plan",to_json(next_plan)}};
  std::cout<<json::serialize(json::object{{"ok",true},{"plan",to_json(winner.plan)},{"planner_state",state},
    {"diagnostics",json::object{{"engine","boundary_joint_v3"},{"selected",winner.origin},{"boundary_trade",boundary_trade},
    {"profile",profile.profile},{"subset_target_limit",subset_target_limit},
    {"endpoint_quota",endpoint_quota},{"bowl_slack",bowl_slack},
    {"boundary_trade_percent",boundary_trade_percent},
    {"boundary_trade_always",boundary_trade_always},
    {"objective_brand_buckets",objective_brand_buckets},
    {"target503_mode",target503_mode},
    {"baseline_starts",baseline_starts},
    {"extra_endpoints",stats.extra_endpoints},{"slack_candidates",stats.slack_candidates},
    {"coverage_complete",std::get<0>(winner.eval.value)==required && std::get<1>(winner.eval.value)==required},
    {"labels",stats.labels},{"transitions",stats.transitions},{"route_count",stats.route_count},
    {"expanded",stats.expanded},{"candidate_count",stats.candidate_count},{"duplicates",stats.duplicates},
    {"heuristic_label_rejects",stats.heuristic_label_rejects},
    {"bound_prunes",stats.bound_prunes},
    {"boundary_expanded",boundary_stats.expanded},{"boundary_generated",boundary_stats.generated},
    {"boundary_duplicates",boundary_stats.duplicates},{"boundary_rejected",boundary_stats.rejected},
    {"preview_attempts",preview_attempts},{"complete_previews",int(previews.size())},{"preview_ms",preview_ms},
    {"precompute_ms",stats.precompute_us/1000.0},{"subset_dp_ms",stats.dp_us/1000.0},
    {"packing_ms",stats.packing_us/1000.0},
    {"baseline_ms",std::chrono::duration_cast<std::chrono::milliseconds>(baseline_done-started).count()},
    {"combinations",stats.combinations},{"validated",stats.validated},{"improvements",stats.improvements},
    {"accepted_pool_candidates",stats.accepted_candidates},{"pool_bowl_gain",stats.pool_bowl_gain},
    {"rollouts",rollouts},{"forecast","hold_observed_roads"},
    {"elapsed_ms",std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-started).count()}}}})<<'\n';
 }catch(const std::exception& e) {
  std::cout<<json::serialize(json::object{{"ok",false},{"error",e.what()}})<<'\n';return 1;
 }
}
