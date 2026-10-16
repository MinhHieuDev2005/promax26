#pragma once
#include "hexa_udon/solver.hpp"

namespace duc {
// Replace only a patrol suffix. Supply schedules stay fixed and the complete
// joint plan is simulated before accepting any change.
inline void repair_tails(std::vector<std::vector<int>>& plan,
                         const std::vector<hexa_udon::solver::Agent>& agents,
                         const std::vector<int>& traffic, int steps,
                         double milliseconds, bool max_total,
                         const std::set<int>& collected) {
    namespace s = hexa_udon::solver;
    s::Timer timer;
    s::Router router(traffic);
    auto rank = [&](const s::DayResult& result) {
        int fresh = 0;
        for (int b = 0; b < s::B; ++b)
            if (result.brandHit[b] && !collected.contains(s::rawBrand[b])) ++fresh;
        return max_total ? std::make_tuple(result.balls, fresh, result.brands)
                         : std::make_tuple(fresh, result.brands, result.balls);
    };
    auto best = s::simulateDay(agents, plan, traffic, steps);
    if (!best.valid) return;
    bool changed = true;
    while (changed && timer.ms() < milliseconds) {
        changed = false;
        for (std::size_t a = 0; a < agents.size() && timer.ms() < milliseconds; ++a) {
            if (agents[a].kind != 0) continue;
            const auto original = plan[a];
            int cell = agents[a].pos, elapsed = 0;
            for (std::size_t cut = 0; cut <= original.size() && timer.ms() < milliseconds; ++cut) {
                // Preserve most of the route to limit interactions with earlier rendezvous.
                if (elapsed >= steps / 2 && elapsed < steps) {
                    for (int target = 0; target < s::S && timer.ms() < milliseconds; ++target) {
                        for (int mode = 0; mode < 2; ++mode) {
                            const auto path = router.path(cell, s::spots[target].pos, mode);
                            if (path.empty() || path.front() != cell) continue;
                            const int duration = s::pathSteps(path, traffic);
                            if (duration > steps - elapsed) continue;
                            auto candidate = plan;
                            candidate[a].assign(original.begin(), original.begin() + cut);
                            s::appendMoves(path, candidate[a]);
                            if (elapsed + duration < steps)
                                candidate[a].push_back(-(steps - elapsed - duration));
                            auto result = s::simulateDay(agents, candidate, traffic, steps);
                            if (result.valid && rank(result) > rank(best)) {
                                plan = std::move(candidate);
                                best = std::move(result);
                                changed = true;
                            }
                        }
                    }
                }
                if (cut == original.size()) break;
                const int action = original[cut];
                if (action < 0) elapsed -= action;
                else {
                    elapsed += s::stepCost(cell, traffic);
                    cell = s::neighbor(cell, action);
                }
            }
        }
    }
}
} // namespace duc
