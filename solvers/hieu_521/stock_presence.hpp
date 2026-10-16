#pragma once
#include "hexa_udon/solver.hpp"
namespace duc {
// Eligibility on a fixed valid route. Count each patrol at each spot once.
// A moving agent occupies its origin until completion; tick zero never collects.
inline std::vector<char> stock_presence(int cell, const std::vector<int>& actions,
                                      const std::vector<int>& traffic) {
    namespace s=hexa_udon::solver;
    std::vector<char> seen(s::S,0);
    auto mark=[&](int c) { int spot=s::spotAt[c]; if (spot>=0) seen[spot]=1; };
    for (int action:actions) {
        if (action<0) { mark(cell); continue; }
        if (s::stepCost(cell,traffic)>1) mark(cell);
        cell=s::neighbor(cell,action);
        mark(cell);
    }
    return seen;
}
}
