#include "hexa_udon/solver.hpp"

#include <iostream>
#include <stdexcept>

int main() {
    using namespace hexa_udon;
    auto map = core::MapDefinition::create(8, 8,
        std::vector<core::Terrain>(64, core::Terrain::Plain)).value();
    const core::MatchConfig match{0, {60, 60}, {2, 2}, map,
        {{7, {1}, 1}, {11, {8}, 1}}, {{0}}, 20, 1, 1, 2};
    solver::loadProblem(match);
    solver::today = 1;
    const std::vector<solver::Agent> agents{{0, 0, 20}};
    const std::vector<int> patrols{0}, supplies;
    const std::vector<std::vector<int>> brand_spots{{0}, {1}};
    solver::Router router(std::vector<int>(solver::NC, 0));
    solver::Day day(agents, 2, 1, router, patrols, supplies, brand_spots, {1, 0});
    day.setSchedule({});
    const auto old_score = day.evaluate({{0}}).score;
    const auto new_score = day.evaluate({{1}}).score;
    if (!(old_score > -1e17 && new_score > old_score))
        throw std::runtime_error("Counterexample must have a valid superior alternative");
    std::vector<std::vector<int>> replacement{{1}};
    const bool accepted = day.repair(replacement, {1, 0}, true, 0);
    std::cout << "old_score=" << old_score << " new_score=" << new_score
              << " repair_accepts=" << accepted << '\n';
    if (accepted) throw std::runtime_error("Baseline no longer exhibits the brand lock");
    if (!day.repair(replacement, {0, 1}, true, 0)
        || day.evaluate(replacement).score <= old_score)
        throw std::runtime_error("Explicit exchange must preserve the superior candidate");
}
