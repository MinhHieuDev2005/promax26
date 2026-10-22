#include "hexa_udon/solver.hpp"
#include "hexa_udon/protocol/json_codec.hpp"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iterator>

int main(int argc, char** argv) {
    using namespace hexa_udon;
    try {
        if (argc != 2 && argc != 3) throw std::invalid_argument("Usage: round6_exact setting.json [minimum-first-day-brands]");
        int minimumFirstDay = 0;
        if (argc == 3) {
            const std::string value(argv[2]);
            if (value.size() != 1 || value[0] < '0' || value[0] > '4')
                throw std::invalid_argument("First-day minimum must be 0..4");
            minimumFirstDay = value[0] - '0';
        }
        std::ifstream input(argv[1]);
        if (!input) throw std::invalid_argument("Cannot open fixture");
        const std::string text{std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
        const auto decoded = protocol::decode_match_setting(text);
        if (!decoded) throw std::invalid_argument(decoded.error().message);
        solver::loadProblem(decoded.value());
        if (solver::NA != 2 || solver::S > 4 || solver::B > 4 || solver::NC > 64
            || solver::D > 3 || solver::FUEL_LIMIT > 4 || solver::PLAYERS != 1
            || *std::max_element(solver::daySteps.begin(), solver::daySteps.end()) > 4
            || std::any_of(solver::cellType.begin(), solver::cellType.end(),
                           [](int terrain) { return terrain != solver::PLAIN; }))
            throw std::invalid_argument("Exact reference supports tiny plain two-patrol fixtures only");
        solver::Timer timer;
        using State = std::tuple<int, int, int, int, int>;
        using Reward = std::pair<int, int>;
        std::map<State, Reward> frontier{{{solver::agentStart[0], solver::FUEL_LIMIT,
            solver::agentStart[1], solver::FUEL_LIMIT, 0}, {0, 0}}};
        const std::vector<int> status(solver::NC, 0);
        std::vector<int> sizes;
        std::vector<std::map<State, std::pair<State, std::vector<std::vector<int>>>>> history;
        long long transitions = 0;
        for (int day = 0; day < solver::D; ++day) {
            std::map<State, Reward> next;
            history.emplace_back();
            for (const auto& [state, reward] : frontier) {
                const auto [firstPosition, firstFuel, secondPosition, secondFuel, collected] = state;
                const std::vector<solver::Agent> agents{{0, firstPosition, firstFuel}, {0, secondPosition, secondFuel}};
                std::vector<std::vector<int>> plans(2);
                std::function<void(int, int, int, int)> enumerate = [&](int agent, int position, int fuel, int remaining) {
                    if (remaining == 0) {
                        if (agent == 0) {
                            enumerate(1, secondPosition, secondFuel, solver::daySteps[day]);
                            return;
                        }
                        const auto result = solver::simulateDay(agents, plans, status, solver::daySteps[day]);
                        if (!result.valid) throw std::runtime_error(result.error);
                        ++transitions;
                        int mask = collected;
                        for (int brand = 0; brand < solver::B; ++brand)
                            if (result.brandHit[brand]) mask |= 1 << brand;
                        const State endpoint{result.end[0].pos, result.end[0].fuel,
                            result.end[1].pos, result.end[1].fuel, mask};
                        const Reward candidate{reward.first + result.brands, reward.second + result.balls};
                        const auto found = next.find(endpoint);
                        if (found == next.end() || candidate > found->second) {
                            next[endpoint] = candidate;
                            history.back()[endpoint] = {state, plans};
                        }
                        return;
                    }
                    plans[agent].push_back(-1);
                    enumerate(agent, position, fuel, remaining - 1);
                    plans[agent].pop_back();
                    if (remaining < 2 || fuel == 0) return;
                    for (int direction = 0; direction < 6; ++direction) {
                        const int destination = solver::neighbor(position, direction);
                        if (!solver::passable(destination)) continue;
                        plans[agent].push_back(direction);
                        enumerate(agent, destination, fuel - 1, remaining - 2);
                        plans[agent].pop_back();
                    }
                };
                enumerate(0, firstPosition, firstFuel, solver::daySteps[day]);
            }
            if (day == 0 && minimumFirstDay > 0) {
                for (auto entry = next.begin(); entry != next.end();) {
                    if (entry->second.first < minimumFirstDay) entry = next.erase(entry);
                    else ++entry;
                }
            }
            frontier = std::move(next);
            sizes.push_back(frontier.size());
        }
        if (frontier.empty()) {
            std::cout << nlohmann::json{{"feasible", false}, {"minimum_first_day_brands", minimumFirstDay}}.dump() << '\n';
            return 0;
        }
        std::tuple<int, int, int> best{-1, -1, -1};
        State bestState;
        for (const auto& [state, reward] : frontier) {
            const auto score = std::tuple{__builtin_popcount(static_cast<unsigned>(std::get<4>(state))), reward.first, reward.second};
            if (score > best) { best = score; bestState = state; }
        }
        std::vector<nlohmann::json> witness(solver::D);
        for (int day = solver::D - 1; day >= 0; --day) {
            const auto& [previous, plans] = history[day].at(bestState);
            const auto [firstPosition, firstFuel, secondPosition, secondFuel, mask] = previous;
            const auto result = solver::simulateDay({{0, firstPosition, firstFuel}, {0, secondPosition, secondFuel}},
                plans, status, solver::daySteps[day]);
            witness[day] = {{"plan", plans}, {"positions", {result.end[0].pos, result.end[1].pos}},
                {"fuel", {result.end[0].fuel, result.end[1].fuel}}, {"hits", result.brandHit},
                {"brands", result.brands}, {"bowls", result.balls}};
            bestState = previous;
        }
        std::cout << nlohmann::json{{"score", {std::get<0>(best), std::get<1>(best), std::get<2>(best)}},
            {"states_per_day", sizes}, {"transitions", transitions}, {"elapsed_ms", timer.ms()},
            {"witness", witness}, {"exact", true}, {"feasible", true},
            {"minimum_first_day_brands", minimumFirstDay}}.dump() << '\n';
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
