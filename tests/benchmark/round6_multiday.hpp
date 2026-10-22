#pragma once

vector<vector<int>> chooseOvernight(vector<vector<int>> plan, const vector<Agent>& initial,
        const vector<int>& status, const vector<char>& before, int steps, Timer& budget, double timeMs) {
    struct Node {
        vector<Agent> agents;
        vector<char> collected;
        vector<int> traffic;
        vector<long long> stay;
        vector<vector<int>> first;
        int daily = 0, bowls = 0;
        vector<long long> rank;
    };
    vector<int> patrols, supplies;
    vector<vector<int>> brandSpots(B);
    for (int agent = 0; agent < NA; ++agent)
        (initial[agent].kind == 0 ? patrols : supplies).push_back(agent);
    for (int spot = 0; spot < S; ++spot) brandSpots[spots[spot].brand].push_back(spot);
    if (patrols.size() < 2) return plan;
    const int horizon = min(D - today, HEXA_JOINT_HORIZON);
    const auto forecast = Planner::predicted(status);
    Node root{initial, before, status, vector<long long>(NC), {}, 0, 0, {}};
    vector<Node> beam{root};
    long long generated = 0, valid = 0;
    int completed = 0;
    Timer phase;
    auto reward = [&](const Node& node) {
        return vector<long long>{count(node.collected.begin(), node.collected.end(), 1), node.daily, node.bowls};
    };
    auto moves = [&](const Node& node, int agent, int length, Router& router, const vector<int>& incumbent) {
        vector<vector<int>> options;
        set<vector<int>> seen;
        auto add = [&](vector<int> actions) {
            if (options.size() < 24 && seen.insert(actions).second) options.push_back(move(actions));
        };
        add(incumbent);
        add({-length});
        const auto& state = node.agents[agent];
        for (int direction = 0; direction < 6; ++direction) {
            if (!passable(neighbor(state.pos, direction))) continue;
            const int cost = stepCost(state.pos, node.traffic);
            if (cost > length || fuelCost(state.pos) > state.fuel) continue;
            vector<int> actions{direction};
            if (cost < length) actions.push_back(-(length - cost));
            add(move(actions));
        }
        vector<int> order(S);
        iota(order.begin(), order.end(), 0);
        stable_sort(order.begin(), order.end(), [&](int left, int right) {
            return node.collected[spots[left].brand] < node.collected[spots[right].brand];
        });
        for (int spot : order) {
            if (budget.ms() >= timeMs || options.size() >= 24) break;
            if (spots[spot].stock <= 0) continue;
            for (int mode = 0; mode < 2; ++mode) {
                const auto path = router.path(state.pos, spots[spot].pos, mode);
                vector<int> actions, arrival{0};
                int elapsed = 0, fuel = 0;
                for (size_t index = 1; index < path.size(); ++index) {
                    elapsed += stepCost(path[index - 1], node.traffic);
                    fuel += fuelCost(path[index - 1]);
                    if (elapsed > length || fuel > state.fuel) break;
                    actions.push_back(dirTo(path[index - 1], path[index]));
                    arrival.push_back(elapsed);
                }
                for (size_t count : {actions.size(), actions.size() / 2}) {
                    if (!count) continue;
                    vector<int> prefix(actions.begin(), actions.begin() + count);
                    if (arrival[count] < length) prefix.push_back(-(length - arrival[count]));
                    add(move(prefix));
                }
            }
        }
        return options;
    };
    auto identity = [&](const Node& node) {
        vector<long long> key(node.collected.begin(), node.collected.end());
        for (const auto& agent : node.agents) { key.push_back(agent.pos); key.push_back(agent.fuel); }
        key.insert(key.end(), node.traffic.begin(), node.traffic.end());
        key.insert(key.end(), node.stay.begin(), node.stay.end());
        return key;
    };
    for (int depth = 0; depth < horizon && budget.ms() < timeMs; ++depth) {
        const int length = depth == 0 ? steps : daySteps[today + depth];
        map<vector<long long>, Node> pool;
        auto trim = [&] {
            vector<Node> ordered;
            for (auto& entry : pool) ordered.push_back(move(entry.second));
            stable_sort(ordered.begin(), ordered.end(), [](const Node& left, const Node& right) { return left.rank > right.rank; });
            if (ordered.size() > 64) ordered.resize(64);
            pool.clear();
            for (auto& node : ordered) { auto key = identity(node); pool.emplace(move(key), move(node)); }
        };
        bool exhausted = false;
        for (const auto& node : beam) {
            if (budget.ms() >= timeMs || generated >= 24000) { exhausted = true; break; }
            Router router(node.traffic);
            auto base = plan;
            if (depth > 0) {
                Day next(node.agents, length, today + depth, router, patrols, supplies, brandSpots, node.collected);
                vector<vector<pair<int, int>>> schedule;
                for (int agent : supplies) schedule.push_back({{node.agents[agent].pos, INT_MAX}});
                next.setSchedule(schedule);
                int missing = 0;
                base = next.toPlan(next.fill(next.assignBrands(missing), 0));
            }
            vector<vector<vector<int>>> options;
            for (int agent : patrols) options.push_back(moves(node, agent, length, router, base[agent]));
            auto evaluate = [&](const vector<vector<int>>& actions) {
                if (budget.ms() >= timeMs || generated >= 24000) { exhausted = true; return; }
                ++generated;
                const auto result = simulateDay(node.agents, actions, node.traffic, length);
                if (!result.valid) return;
                ++valid;
                Node child{result.end, node.collected, {}, result.stay,
                    depth == 0 ? actions : node.first, node.daily + result.brands, node.bowls + result.balls, {}};
                for (int brand = 0; brand < B; ++brand) child.collected[brand] |= result.brandHit[brand];
                auto totalStay = result.stay;
                for (int cell = 0; cell < NC; ++cell) totalStay[cell] += node.stay[cell];
                child.traffic = statusFromStay(totalStay, PLAYERS);
                for (int cell = 0; cell < NC; ++cell) child.traffic[cell] = max(child.traffic[cell], forecast[cell]);
                child.rank = reward(child);
                if (depth + 1 < horizon) {
                    int remaining = 0, possible = 0;
                    for (int future = depth + 1; future < horizon; ++future) remaining += daySteps[today + future];
                    for (int brand = 0; brand < B; ++brand) {
                        bool reachable = child.collected[brand];
                        for (int agent : patrols) {
                            const auto& table = router.get(child.agents[agent].pos, 1);
                            for (int spot : brandSpots[brand])
                                if (spots[spot].stock > 0 && table.t[spots[spot].pos] <= remaining
                                    && table.f[spots[spot].pos] <= child.agents[agent].fuel) reachable = true;
                        }
                        possible += reachable;
                    }
                    child.rank.insert(child.rank.begin(), possible);
                }
                long long fuel = 0;
                for (int agent : patrols) fuel += child.agents[agent].fuel;
                child.rank.push_back(fuel);
                auto key = identity(child);
                auto found = pool.find(key);
                if (found == pool.end()) pool.emplace(move(key), move(child));
                else if (child.rank > found->second.rank) found->second = move(child);
                if (pool.size() >= 512) trim();
            };
            evaluate(base);
            for (size_t first = 0; first < patrols.size() && !exhausted; ++first)
                for (size_t second = first + 1; second < patrols.size() && !exhausted; ++second)
                    for (const auto& left : options[first]) {
                        if (exhausted) break;
                        for (const auto& right : options[second]) {
                            if (exhausted) break;
                            auto actions = base;
                            actions[patrols[first]] = left;
                            actions[patrols[second]] = right;
                            evaluate(actions);
                        }
                    }
            if (exhausted) break;
        }
        if (pool.empty() || exhausted) break;
        trim();
        beam.clear();
        for (auto& entry : pool) beam.push_back(move(entry.second));
        completed = depth + 1;
    }
    if (completed == horizon) {
        const auto best = max_element(beam.begin(), beam.end(), [](const Node& left, const Node& right) { return left.rank < right.rank; });
        plan = best->first;
    }
    cerr << "[multiday] horizon=" << horizon << " completed=" << completed << " generated=" << generated
         << " valid=" << valid << " elapsed_ms=" << phase.ms() << '\n';
    return plan;
}
