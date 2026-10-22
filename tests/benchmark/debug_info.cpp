#include "hexa_udon/solver.hpp"
#include "hexa_udon/protocol/json_codec.hpp"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>

using namespace hexa_udon;

int main(int argc, char** argv) {
    if (argc != 2) return 1;
    std::ifstream file(argv[1]);
    const std::string text{std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
    const auto decoded = protocol::decode_match_setting(text);
    solver::loadProblem(decoded.value());
    std::cout << "NA=" << solver::NA << " S=" << solver::S << " B=" << solver::B << " D=" << solver::D << "\n";
    for (int s = 0; s < solver::S; ++s) {
        std::cout << "Spot " << s << ": brand=" << solver::spots[s].brand << " pos=" << solver::spots[s].pos << " stock=" << solver::spots[s].stock << "\n";
    }
    for (int a = 0; a < solver::NA; ++a) {
        std::cout << "Agent " << a << ": start=" << solver::agentStart[a] << "\n";
    }
    return 0;
}
