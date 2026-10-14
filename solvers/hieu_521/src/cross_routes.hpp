#pragma once
#include <algorithm>
#include <vector>

namespace duc_routes {
inline bool unique_spots(const std::vector<int>& route) {
    for (size_t i = 0; i < route.size(); ++i)
        if (route[i] >= 0 && std::find(route.begin() + i + 1, route.end(), route[i]) != route.end())
            return false;
    return true;
}

// Negative entries are refueling appointments. Keep them intact; the caller
// must repair and simulate the complete joint plan before accepting it.
inline bool exchange_tails(std::vector<int>& a, std::vector<int>& b, size_t i, size_t j) {
    if (&a == &b || i > a.size() || j > b.size()) return false;
    std::vector<int> x(a.begin(), a.begin() + i), y(b.begin(), b.begin() + j);
    x.insert(x.end(), b.begin() + j, b.end());
    y.insert(y.end(), a.begin() + i, a.end());
    if ((x == a && y == b) || !unique_spots(x) || !unique_spots(y)) return false;
    a.swap(x); b.swap(y);
    return true;
}

inline bool transfer_segment(std::vector<int>& a, std::vector<int>& b,
                             size_t start, size_t length, size_t at) {
    if (&a == &b || length < 2 || start > a.size() || length > a.size() - start || at > b.size()) return false;
    // Do not detach refueling appointments from their route in this operator.
    for (size_t i = start; i < start + length; ++i)
        if (a[i] < 0 || std::find(b.begin(), b.end(), a[i]) != b.end()) return false;
    b.insert(b.begin() + at, a.begin() + start, a.begin() + start + length);
    a.erase(a.begin() + start, a.begin() + start + length);
    return true;
}

}
