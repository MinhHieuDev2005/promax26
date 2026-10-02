#pragma once
#include "search.hpp"
#include <chrono>
namespace chokudai_v2 {
std::vector<hexudon::ActionPlan> route_dp_proposals(
 const hexudon::MapConfig&,const hexudon::DayInfo&,const hexudon::AgentTypes&,
 const hexudon::ActionPlan&, std::chrono::steady_clock::time_point deadline);
}
