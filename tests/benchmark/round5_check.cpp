#include "hexa_udon/solver.hpp"

#include <iostream>
#include <stdexcept>

int main() {
    using namespace hexa_udon;
    const auto map = core::MapDefinition::create(8, 8,
        std::vector<core::Terrain>(64, core::Terrain::Plain)).value();
    solver::loadProblem(core::MatchConfig{0, {60}, {4}, map,
        {{0, {2}, 1}}, {{0}, {9}}, 1, 1, 2, 4});
    const std::vector<int> status(solver::NC, 0);
    solver::Router router(status);
    for (int start : {0, 9})
        if (router.get(start, 1).f[2] <= 1)
            throw std::runtime_error("All-patrol impossibility bound failed");
    const std::vector<solver::Agent> mixed{{0, 0, 1}, {1, 9, 1}};
    const auto feasible = solver::simulateDay(mixed, {{2, 2}, {1, -2}}, status, 4);
    if (!feasible.valid || feasible.brands != 1 || feasible.balls != 1)
        throw std::runtime_error("Supply rendezvous feasibility witness failed");
    solver::today = 0;
    solver::interimSec = 0;
    solver::choosingKinds = true;
    for (int workers : {1, 8}) {
        solver::threads = workers;
        solver::rng.x = 123;
        const auto plan = solver::planDay(mixed, status, {0}, 4, true, 50);
        if (!solver::simulateDay(mixed, plan, status, 4).valid)
            throw std::runtime_error("Invalid selection plan");
        if (solver::rng.x != 123 || solver::threads != workers)
            throw std::runtime_error("N leaked selection RNG or worker configuration");
    }
    solver::choosingKinds = false;
    std::cout << "Round 5 feasibility and selector RNG checks passed\n";
}
