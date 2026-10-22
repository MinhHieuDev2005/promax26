#pragma once
#include "hexa_udon/solver.hpp"
#include <cstdlib>
#include <nlohmann/json.hpp>

namespace hexa_udon::solver {
inline vector<long long> jointKey(const vector<Agent>& agents, const vector<char>& collected,
                                  Router& router, int steps) {
    vector<int> patrols;
    for (int agent = 0; agent < NA; ++agent) if (agents[agent].kind == 0) patrols.push_back(agent);
    const int count = static_cast<int>(patrols.size());
    vector<vector<int>> goal(count, vector<int>(B, -1)), mode(count, vector<int>(B)), cost(count, vector<int>(B, INT_MAX));
    vector<int> degree(B), order(B), owner(count, -1);
    for (int patrol = 0; patrol < count; ++patrol) {
        const auto& state = agents[patrols[patrol]];
        for (int routeMode = 0; routeMode < 2; ++routeMode) {
            const auto& table = router.get(state.pos, routeMode);
            for (int spot = 0; spot < S; ++spot) {
                const auto& target = spots[spot];
                if (target.stock <= 0 || table.t[target.pos] > steps || table.f[target.pos] > state.fuel) continue;
                if (table.t[target.pos] < cost[patrol][target.brand]) {
                    goal[patrol][target.brand] = target.pos;
                    mode[patrol][target.brand] = routeMode;
                    cost[patrol][target.brand] = table.t[target.pos];
                }
            }
        }
        for (int brand = 0; brand < B; ++brand) degree[brand] += goal[patrol][brand] >= 0;
    }
    iota(order.begin(), order.end(), 0);
    stable_sort(order.begin(), order.end(), [&](int left, int right) {
        return make_pair(collected[left], degree[left]) < make_pair(collected[right], degree[right]);
    });
    for (int brand : order) {
        vector<char> seen(count);
        function<bool(int)> augment = [&](int target) {
            for (int patrol = 0; patrol < count; ++patrol) {
                if (seen[patrol] || goal[patrol][target] < 0) continue;
                seen[patrol] = 1;
                if (owner[patrol] < 0 || augment(owner[patrol])) {
                    owner[patrol] = target;
                    return true;
                }
            }
            return false;
        };
        augment(brand);
    }
    auto plan = allWait(steps);
    for (int patrol = 0; patrol < count; ++patrol) if (owner[patrol] >= 0) {
        const int brand = owner[patrol], agent = patrols[patrol];
        auto& actions = plan[agent];
        actions.clear();
        appendMoves(router.path(agents[agent].pos, goal[patrol][brand], mode[patrol][brand]), actions);
        if (cost[patrol][brand] < steps) actions.push_back(-(steps - cost[patrol][brand]));
    }
    const auto result = simulateDay(agents, plan, router.status, steps);
    if (!result.valid) return {-1};
    int coverage = 0;
    for (int brand = 0; brand < B; ++brand) coverage += collected[brand] || result.brandHit[brand];
    if (getenv("HEXA_JOINT_TRACE")) {
        vector<int> positions, fuel;
        for (const auto& state : agents) { positions.push_back(state.pos); fuel.push_back(state.fuel); }
        cerr << "[joint-assignment] " << nlohmann::json({{"positions", positions}, {"fuel", fuel},
            {"owners", owner}, {"patrols", patrols}, {"steps", steps}, {"collected", collected},
            {"hits", result.brandHit}, {"coverage", coverage}, {"plan", plan}}).dump() + "\n";
    }
    return {coverage, result.brands, result.balls};
}
}
