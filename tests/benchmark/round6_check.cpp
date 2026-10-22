#include "hexa_udon/round6_joint.hpp"
#include <stdexcept>

int main() {
    using namespace hexa_udon;
    const auto map = core::MapDefinition::create(8, 8,
        std::vector<core::Terrain>(64, core::Terrain::Plain)).value();
    solver::loadProblem(core::MatchConfig{0, {60}, {2}, map,
        {{0, {0}, 1}}, {{0}, {0}}, 1, 1, 2, 4});
    {
        solver::Router router(std::vector<int>(64, 0));
        if (solver::jointKey({{0, 0, 1}, {0, 0, 1}}, {0}, router, 2)
            != std::vector<long long>{1, 1, 1})
            throw std::runtime_error("Shared stock was counted twice");
    }
    solver::loadProblem(core::MatchConfig{0, {60}, {2}, map,
        {{0, {1}, 1}, {1, {8}, 1}}, {{0}, {0}}, 1, 1, 2, 4});
    {
        solver::Router router(std::vector<int>(64, 0));
        if (solver::jointKey({{0, 0, 1}, {0, 0, 1}}, {0, 0}, router, 2)
            != std::vector<long long>{2, 2, 2})
            throw std::runtime_error("Distinct joint assignment failed");
        if (solver::jointKey({{0, 0, 0}, {0, 0, 0}}, {0, 0}, router, 2)
            != std::vector<long long>{0, 0, 0})
            throw std::runtime_error("Fuel infeasibility ignored");
        if (solver::jointKey({{0, 0, 0}, {1, 0, 1}}, {0, 0}, router, 2)
            != std::vector<long long>{0, 0, 0})
            throw std::runtime_error("Unplanned supply rescue assumed");
    }
    std::cout << "Round 6 joint witness checks passed\n";
}
