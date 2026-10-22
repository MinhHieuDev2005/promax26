#include "hexa_udon/solver.hpp"

#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) {
    using namespace hexa_udon;
    if (argc != 2 || (std::string(argv[1]) != "0" && std::string(argv[1]) != "1"))
        throw std::invalid_argument("Expected acquired brand count: 0 or 1");
    auto map = core::MapDefinition::create(8, 8,
        std::vector<core::Terrain>(64, core::Terrain::Plain)).value();
    solver::loadProblem(core::MatchConfig{0, {60, 60, 60, 60}, {4, 4, 4, 4}, map,
        {{7, {7}, 1}}, {{0}}, 20, 1, 1, 2});
    solver::threads = 1;
    solver::interimSec = 0;
    std::vector<solver::Agent> agents{{0, 0, 20}};
    std::vector<char> collected(1, 0);
    const std::vector<int> status(solver::NC, 0);
    for (int day = 0; day < 4; ++day) {
        solver::today = day;
        const auto plan = solver::planDay(agents, status, collected, 4, day == 3, 100);
        const auto result = solver::simulateDay(agents, plan, status, 4);
        if (!result.valid) throw std::runtime_error(result.error);
        collected[0] |= result.brandHit[0];
        agents = result.end;
        std::cout << "day=" << day << " pos=" << agents[0].pos
                  << " fuel=" << agents[0].fuel << " brands=" << int(collected[0]) << '\n';
    }
    if (int(collected[0]) != argv[1][0] - '0')
        throw std::runtime_error("Unexpected multi-day reachability");
}
