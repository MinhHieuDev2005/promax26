#pragma once
#include "hexa_udon/solver.hpp"
namespace duc {
// Eliminate only closed detours with a full-plan dominance certificate.
// Equal duration preserves all later arrivals. Transit through empty spots is legal.
inline int remove_dominated_loops(std::vector<std::vector<int>>& plan,
    const std::vector<hexa_udon::solver::Agent>& start,
    const std::vector<int>& traffic, int steps, double budget, bool reinvest=false) {
    namespace s = hexa_udon::solver;
    s::Timer timer;
    auto best = s::simulateDay(start,plan,traffic,steps);
    if (!best.valid) return 0;
    const auto boundaryFloor = best.end;
    int saved = 0;
    for (size_t a=0; a<plan.size() && timer.ms()<budget; ++a) {
        if (start[a].kind!=0) continue;
        bool changed=true;
        while (changed && timer.ms()<budget) {
            changed=false;
            std::vector<int> cells{start[a].pos}, ticks{0};
            for (int action : plan[a]) {
                ticks.push_back(ticks.back()+(action<0 ? -action : s::stepCost(cells.back(),traffic)));
                cells.push_back(action<0 ? cells.back() : s::neighbor(cells.back(),action));
            }
            for (size_t left=0; left<plan[a].size() && !changed && timer.ms()<budget; ++left) {
                for (size_t right=left+2; right<cells.size() && timer.ms()<budget; ++right) {
                    if (cells[left]!=cells[right]) continue;
                    int movingTicks=0;
                    for (size_t k=left;k<right;++k)
                        if (plan[a][k]>=0) movingTicks+=ticks[k+1]-ticks[k];
                    if (!movingTicks) continue;
                    auto candidate=plan;
                    auto& route=candidate[a];
                    route.erase(route.begin()+left,route.begin()+right);
                    route.insert(route.begin()+left,-(ticks[right]-ticks[left]));
                    auto actual=s::simulateDay(start,candidate,traffic,steps);
                    if (!actual.valid || actual.brandHit!=best.brandHit || actual.balls<best.balls) continue;
                    bool dominates=true;
                    for (size_t i=0;i<start.size();++i)
                        if (actual.end[i].pos!=best.end[i].pos || actual.end[i].fuel<best.end[i].fuel) dominates=false;
                    if (!dominates) continue;
                    saved+=movingTicks;
                    plan=std::move(candidate);
                    best=std::move(actual);
                    changed=true;
                    break;
                }
            }
        }
    }
    if (!reinvest) return saved;
    // Spend idle windows on collection, returning before the unchanged suffix.
    // Compare fuel against the original plan, so saved fuel can actually be used.
    s::Router router(traffic);
    bool improved = true;
    while (improved && timer.ms() < budget) {
        improved = false;
        for (size_t a=0; a<plan.size() && timer.ms()<budget; ++a) {
            if (start[a].kind != 0) continue;
            int cell = start[a].pos;
            for (size_t k=0; k<plan[a].size() && !improved && timer.ms()<budget; ++k) {
                const int action = plan[a][k];
                if (action >= 0) { cell=s::neighbor(cell,action); continue; }
                const int window = -action;
                for (int target=0; target<s::S && !improved && timer.ms()<budget; ++target) {
                    if (s::spots[target].pos == cell) continue;
                    for (int mode=0; mode<2 && timer.ms()<budget; ++mode) {
                        const auto outward=router.path(cell,s::spots[target].pos,mode);
                        const auto inward=router.path(s::spots[target].pos,cell,mode);
                        if (outward.empty() || inward.empty()) continue;
                        const int duration=s::pathSteps(outward,traffic)+s::pathSteps(inward,traffic);
                        if (duration>window) continue;
                        std::vector<int> insertion;
                        s::appendMoves(outward,insertion);
                        s::appendMoves(inward,insertion);
                        if (duration<window) insertion.push_back(-(window-duration));
                        auto candidate=plan;
                        auto& route=candidate[a];
                        route.erase(route.begin()+k);
                        route.insert(route.begin()+k,insertion.begin(),insertion.end());
                        auto actual=s::simulateDay(start,candidate,traffic,steps);
                        if (!actual.valid || actual.brandHit!=best.brandHit || actual.balls<=best.balls) continue;
                        bool safe=true;
                        for (size_t i=0;i<start.size();++i)
                            if (actual.end[i].pos!=boundaryFloor[i].pos || actual.end[i].fuel<boundaryFloor[i].fuel) safe=false;
                        if (!safe) continue;
                        plan=std::move(candidate);
                        best=std::move(actual);
                        improved=true;
                        break;
                    }
                }
            }
        }
    }
    // Reconstruct short windows, not just round trips from a stationary cell.
    // Preserve suffix timing and certify shared stock/refueling by joint replay.
    for (size_t a=0; a<plan.size() && timer.ms()<budget; ++a) {
        if (start[a].kind != 0) continue;
        const auto original=plan[a];
        std::vector<int> cells{start[a].pos}, ticks{0};
        for (int action:original) {
            ticks.push_back(ticks.back()+(action<0 ? -action:s::stepCost(cells.back(),traffic)));
            cells.push_back(action<0 ? cells.back():s::neighbor(cells.back(),action));
        }
        bool accepted=false;
        for (size_t left=0; left<original.size() && !accepted && timer.ms()<budget; ++left) {
            for (size_t right=left+1; right<cells.size() && right<=left+12 && !accepted && timer.ms()<budget; ++right) {
                const int window=ticks[right]-ticks[left];
                for (int target=0; target<s::S && !accepted && timer.ms()<budget; ++target) {
                    for (int mode=0; mode<2 && timer.ms()<budget; ++mode) {
                        auto first=router.path(cells[left],s::spots[target].pos,mode);
                        auto second=router.path(s::spots[target].pos,cells[right],mode);
                        if (first.empty() || second.empty()) continue;
                        int duration=s::pathSteps(first,traffic)+s::pathSteps(second,traffic);
                        if (duration>window) continue;
                        std::vector<int> insertion;
                        s::appendMoves(first,insertion);
                        s::appendMoves(second,insertion);
                        if (duration<window) insertion.push_back(-(window-duration));
                        auto candidate=plan;
                        auto& route=candidate[a];
                        route.erase(route.begin()+left,route.begin()+right);
                        route.insert(route.begin()+left,insertion.begin(),insertion.end());
                        auto actual=s::simulateDay(start,candidate,traffic,steps);
                        if (!actual.valid || actual.brandHit!=best.brandHit || actual.balls<=best.balls) continue;
                        bool safe=true;
                        for (size_t i=0;i<start.size();++i)
                            if (actual.end[i].pos!=boundaryFloor[i].pos || actual.end[i].fuel<boundaryFloor[i].fuel) safe=false;
                        if (!safe) continue;
                        plan=std::move(candidate);
                        best=std::move(actual);
                        accepted=true;
                        break;
                    }
                }
            }
        }
    }
    return saved;
}
}
