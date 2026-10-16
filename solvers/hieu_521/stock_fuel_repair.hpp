#pragma once
#include "hexa_udon/solver.hpp"

namespace duc {
// Evaluate end states with an actual next-day construction and full simulation.
// Current-day brand coverage is a hard constraint; forecasts are not actual points.
inline int improve_terminal_state(std::vector<std::vector<int>>& plan,
    const std::vector<hexa_udon::solver::Agent>& start,
    const std::vector<int>& traffic, int steps, double budget) {
    namespace s = hexa_udon::solver;
    if (s::today + 1 >= s::D) return 0;
    s::Timer timer;
    s::Router router(traffic);
    std::vector<int> patrols, supplies;
    for (int i = 0; i < (int)start.size(); ++i)
        (start[i].kind == 0 ? patrols : supplies).push_back(i);
    if (supplies.empty()) return 0;
    std::vector<std::vector<int>> brandSpots(s::B);
    for (int i = 0; i < s::S; ++i) brandSpots[s::spots[i].brand].push_back(i);
    auto forecast = [&](const s::DayResult& today) {
        s::Day tomorrow(today.end, s::daySteps[s::today + 1], s::today + 1,
                        router, patrols, supplies, brandSpots);
        std::vector<std::vector<std::pair<int,int>>> schedule;
        for (int i : supplies) schedule.push_back({{today.end[i].pos, INT_MAX}});
        tomorrow.setSchedule(schedule);
        int missing = 0;
        auto routes = tomorrow.fill(tomorrow.assignBrands(missing), 0.0);
        return s::simulateDay(today.end, tomorrow.toPlan(routes), traffic, s::daySteps[s::today + 1]);
    };
    auto best = s::simulateDay(start, plan, traffic, steps);
    if (!best.valid) return 0;
    auto next = forecast(best);
    if (!next.valid) return 0;
    auto value = [&](const s::DayResult& a, const s::DayResult& b) {
        return std::make_tuple(b.brands, a.balls + b.balls, a.balls);
    };
    auto bestValue = value(best, next);
    int accepted = 0;
    for (int i : patrols) {
        const auto original = plan[i];
        int cell = start[i].pos, elapsed = 0;
        for (size_t cut = 0; cut < original.size() && timer.ms() < budget; ++cut) {
            if (elapsed >= steps / 2) {
                for (int supply : supplies) {
                    if (timer.ms() >= budget) break;
                    auto path = router.path(cell, best.end[supply].pos, 1);
                    if (path.empty()) continue;
                    const int duration = s::pathSteps(path, traffic);
                    if (elapsed + duration > steps) continue;
                    auto candidate = plan;
                    candidate[i].assign(original.begin(), original.begin() + cut);
                    s::appendMoves(path, candidate[i]);
                    if (elapsed + duration < steps) candidate[i].push_back(-(steps-elapsed-duration));
                    auto actual = s::simulateDay(start, candidate, traffic, steps);
                    if (!actual.valid || actual.brandHit != best.brandHit) continue;
                    auto predicted = forecast(actual);
                    if (!predicted.valid || value(actual,predicted) <= bestValue) continue;
                    plan = std::move(candidate);
                    bestValue = value(actual,predicted);
                    best = std::move(actual);
                    ++accepted;
                }
            }
            if (original[cut] < 0) elapsed -= original[cut];
            else { elapsed += s::stepCost(cell,traffic); cell = s::neighbor(cell,original[cut]); }
        }
    }
    return accepted;
}
}
