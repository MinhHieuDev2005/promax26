#include "../src/cross_routes.hpp"
#include <stdexcept>
#include <iostream>
void check(bool value) { if (!value) throw std::runtime_error("cross route regression"); }
int main() {
    using namespace duc_routes;
    std::vector<int> a{0,1,2}, b{3,4,5};
    check(exchange_tails(a,b,1,2));
    check(a == std::vector<int>({0,5}) && b == std::vector<int>({3,4,1,2}));
    check(transfer_segment(b,a,2,2,1));
    check(a == std::vector<int>({0,1,2,5}) && b == std::vector<int>({3,4}));
    a={0,1}; b={1,2}; auto olda=a, oldb=b;
    check(!exchange_tails(a,b,2,0)); check(a==olda && b==oldb);
    check(!transfer_segment(a,b,0,2,0)); check(a==olda && b==oldb);
    a={0,-1,2}; b={3}; olda=a; oldb=b;
    check(!transfer_segment(a,b,0,2,0)); check(a==olda && b==oldb);
    check(!exchange_tails(a,a,0,0));
    check(!exchange_tails(a,b,99,0));
    check(exchange_tails(a,b,1,1)); check(b==std::vector<int>({3,-1,2}));
    std::cout << "PASS cross-route mutations\n";
}
