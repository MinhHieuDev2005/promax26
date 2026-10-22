#include "hexa_udon/solver.hpp"
#include "hexa_udon/protocol/json_codec.hpp"
#include <nlohmann/json.hpp>
#include <fstream>
#include <sys/resource.h>

namespace hexa_udon::solver {
vector<vector<int>> chooseOvernight(vector<vector<int>>, const vector<Agent>&,
    const vector<int>&, const vector<char>&, int, Timer&, double);
}

int main(int argc, char** argv) {
    using namespace hexa_udon;
    try {
        if (argc != 4) throw std::invalid_argument("Usage: round7_probe fixture baseline allowance_ms");
        std::ifstream input(argv[1]), baseline(argv[2]);
        if (!input || !baseline) throw std::invalid_argument("Cannot open probe inputs");
        const std::string text{std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
        const auto decoded = protocol::decode_match_setting(text);
        if (!decoded) throw std::invalid_argument(decoded.error().message);
        solver::loadProblem(decoded.value());
        const auto saved = nlohmann::json::parse(baseline);
        const std::string argument(argv[3]);
        size_t parsed = 0;
        const int allowance = std::stoi(argument, &parsed);
        if (parsed != argument.size() || allowance < 0 || allowance > 10000)
            throw std::invalid_argument("Invalid allowance");
        std::vector<solver::Agent> agents;
        for (int agent = 0; agent < solver::NA; ++agent)
            agents.push_back({saved.at("kinds").at(agent).get<int>(), solver::agentStart[agent], solver::FUEL_LIMIT});
        const auto incumbent = saved.at("days").at(0).at("plan").get<std::vector<std::vector<int>>>();
        solver::today = 0;
        solver::yesterdayDay = -1;
        solver::rng.x = 101;
        const auto rngBefore = solver::rng.x;
        const std::vector<int> status(solver::NC, 0);
        solver::Timer timer;
        const auto plan = solver::chooseOvernight(incumbent, agents, status, std::vector<char>(solver::B, 0),
            solver::daySteps[0], timer, allowance);
        const double elapsed = timer.ms();
        const auto result = solver::simulateDay(agents, plan, status, solver::daySteps[0]);
        struct rusage usage{};
        if (getrusage(RUSAGE_SELF, &usage) != 0) throw std::runtime_error("getrusage failed");
        std::cout << nlohmann::json{{"valid", result.valid}, {"changed", plan != incumbent}, {"plan", plan},
            {"baseline", incumbent}, {"elapsed_ms", elapsed}, {"rng_unchanged", rngBefore == solver::rng.x},
            {"rss_kib", usage.ru_maxrss}, {"today_brands", result.brands}, {"today_bowls", result.balls}}.dump() << '\n';
        return result.valid ? 0 : 1;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
