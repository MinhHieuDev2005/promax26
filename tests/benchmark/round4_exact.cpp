#include "hexa_udon/solver.hpp"
#include "hexa_udon/protocol/json_codec.hpp"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iterator>

int main(int argc, char** argv) {
    using namespace hexa_udon;
    try {
        if (argc != 2) throw std::invalid_argument("Usage: round4_exact setting.json");
        std::ifstream input(argv[1]);
        if (!input) throw std::invalid_argument("Cannot open fixture");
        const std::string text{std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
        const auto decoded = protocol::decode_match_setting(text);
        if (!decoded) throw std::invalid_argument(decoded.error().message);
        solver::loadProblem(decoded.value());
        if (solver::NA != 1 || solver::S > 4 || solver::B > 4 || solver::NC > 64
            || solver::D > 5 || solver::FUEL_LIMIT > 16 || solver::PLAYERS != 1
            || *std::max_element(solver::daySteps.begin(), solver::daySteps.end()) > 4
            || std::any_of(solver::cellType.begin(), solver::cellType.end(),
                           [](int terrain) { return terrain != solver::PLAIN; }))
            throw std::invalid_argument("Exact reference supports only tiny plain single-patrol fixtures");
        solver::Timer timer;
        using State = std::tuple<int, int, int>;
        using Reward = std::pair<int, int>;
        std::map<State, Reward> frontier{{{solver::agentStart[0], solver::FUEL_LIMIT, 0}, {0, 0}}};
        const std::vector<int> status(solver::NC, 0);
        std::vector<int> sizes;
        for (int day = 0; day < solver::D; ++day) {
            std::map<State, Reward> next;
            for (const auto& [state, reward] : frontier) {
                const auto [origin, fuel, collected] = state;
                const std::vector<solver::Agent> agents{{0, origin, fuel}};
                std::vector<int> actions;
                std::function<void(int, int, int)> enumerate = [&](int position, int remainingFuel, int remainingTime) {
                    if (remainingTime == 0) {
                        const auto result = solver::simulateDay(agents, {actions}, status, solver::daySteps[day]);
                        if (!result.valid) throw std::runtime_error(result.error);
                        int mask = collected;
                        for (int brand = 0; brand < solver::B; ++brand)
                            if (result.brandHit[brand]) mask |= 1 << brand;
                        const State endpoint{result.end[0].pos, result.end[0].fuel, mask};
                        const Reward candidate{reward.first + result.brands, reward.second + result.balls};
                        const auto found = next.find(endpoint);
                        if (found == next.end() || candidate > found->second) next[endpoint] = candidate;
                        return;
                    }
                    actions.push_back(-1);
                    enumerate(position, remainingFuel, remainingTime - 1);
                    actions.pop_back();
                    if (remainingTime < 2 || remainingFuel == 0) return;
                    for (int direction = 0; direction < 6; ++direction) {
                        const int destination = solver::neighbor(position, direction);
                        if (!solver::passable(destination)) continue;
                        actions.push_back(direction);
                        enumerate(destination, remainingFuel - 1, remainingTime - 2);
                        actions.pop_back();
                    }
                };
                enumerate(origin, fuel, solver::daySteps[day]);
            }
            frontier = std::move(next);
            sizes.push_back(frontier.size());
        }
        std::tuple<int, int, int> best{-1, -1, -1};
        for (const auto& [state, reward] : frontier)
            best = std::max(best, std::tuple{__builtin_popcount(static_cast<unsigned>(std::get<2>(state))), reward.first, reward.second});
        std::cout << nlohmann::json{{"score", {std::get<0>(best), std::get<1>(best), std::get<2>(best)}},
            {"states_per_day", sizes}, {"elapsed_ms", timer.ms()}, {"exact", true}}.dump() << '\n';
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
