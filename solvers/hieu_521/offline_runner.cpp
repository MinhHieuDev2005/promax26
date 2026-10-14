#include "hexa_udon/protocol/json_codec.hpp"
#include "hexa_udon/solver.hpp"

#include <algorithm>
#include <atomic>
#include <iostream>
#include <iterator>
#include <nlohmann/json.hpp>
#include <string>
#include <thread>
#ifdef HEXUDON_TARGET530
#include "tail_repair.hpp"
#endif

#ifdef HEXUDON_LOOKAHEAD
namespace hexa_udon::solver {
extern double ducFutureWeight;
extern int ducCrossMoves;
extern bool ducMaxTotal;
extern std::atomic<std::uint64_t> ducIterations, ducEvaluated, ducValid;
}
#endif

int main() {
    using nlohmann::json;
    namespace solver = hexa_udon::solver;
    try {
        const auto root = json::parse(std::string{
            std::istreambuf_iterator<char>(std::cin), {}});
        auto config = hexa_udon::protocol::decode_match_setting(
            root.at("config").dump());
        if (!config) throw std::runtime_error(config.error().message);
        if (root.value("op", std::string{}) == "roles") {
            solver::loadProblem(config.value());
            const auto search = root.value("search", json::object());
            const int default_threads =
                std::max(1u, std::thread::hardware_concurrency() / 2);
            solver::threads =
                std::clamp(search.value("threads", default_threads), 1, 32);
            const double time_ms = std::clamp(
                search.value("timeLimitMs", 4000), 100, 55000);
            const std::vector<int> roles = solver::solveKind(time_ms * 0.90);
            std::cout << json{{"ok", true}, {"roles", roles}}.dump() << '\n';
            return 0;
        }
        auto daily_json = root.at(root.contains("day_info") ? "day_info" : "state");
        if (!daily_json.contains("endsAt")) daily_json["endsAt"] = 0;
        if (!daily_json.contains("others")) daily_json["others"] = json::array();
        if (!daily_json.contains("traffics")) daily_json["traffics"] = json::array();
        auto state = hexa_udon::protocol::decode_match_state(
            daily_json.dump(), config.value());
        if (!state) throw std::runtime_error(state.error().message);

        solver::loadProblem(config.value());
        const auto& day_steps = config.value().day_steps;
        const int wire_day = state.value().day;
        const int requested_steps = daily_json.value("stepsCount", 0);
        // Native benchmark day_info is zero-based; GUI state is one-based.
        const int day_index = root.contains("day_info") ? wire_day : wire_day - 1;
        if (day_index < 0 || day_index >= static_cast<int>(day_steps.size()))
            throw std::runtime_error("day is outside configured schedule");
        const int steps = requested_steps > 0 ? requested_steps
                                              : day_steps[day_index];
        solver::today = day_index;
        solver::choosingKinds = false;
        solver::interimSec = 0;
        solver::yesterdayStatus.clear();
        solver::yesterdayDay = -1;
        const auto search = root.value("search", json::object());
#ifdef HEXUDON_LOOKAHEAD
        solver::ducFutureWeight = std::clamp(search.value("futureWeight", 0.0), 0.0, 1.0);
#ifdef HEXUDON_CROSS
        constexpr int defaultCrossMoves = 3;
#else
        constexpr int defaultCrossMoves = 0;
#endif
        solver::ducCrossMoves = std::clamp(search.value("crossMoves", defaultCrossMoves), 0, 3);
        solver::ducMaxTotal = search.value("objectiveMode", std::string{}) == "MAX_TOTAL_UDON";
#endif
#ifdef HEXUDON_TARGET530
        const auto saved = root.value("planner_state", json::object());
        if (search.value("preserveTraffic", false) &&
            saved.value("day_index", -2) == day_index - 1 &&
            saved.contains("traffic") && saved["traffic"].size() ==
                static_cast<std::size_t>(solver::NC)) {
            solver::yesterdayStatus = saved["traffic"].get<std::vector<int>>();
            solver::yesterdayDay = day_index - 1;
        }
        const auto seed = search.value("randomSeed", std::uint64_t{1});
        solver::rng.x ^= seed * 0x9E3779B97F4A7C15ULL;
        if (solver::rng.x == 0) solver::rng.x = 88172645463325252ULL;
#endif
        const int default_threads =
            std::max(1u, std::thread::hardware_concurrency() / 2);
        solver::threads =
            std::clamp(search.value("threads", default_threads), 1, 32);
        const double time_ms = std::clamp(
            search.value("timeLimitMs", 45000), 100,
#ifdef HEXUDON_TARGET530
            55000);
#else
            45000);
#endif
        std::vector<char> before(solver::B, 0);
        if (root.contains("history")) {
            const auto brands = root["history"].value("distinct_brands", std::vector<int>{});
            for (int b = 0; b < solver::B; ++b)
                before[b] = std::find(brands.begin(), brands.end(), solver::rawBrand[b]) != brands.end();
        }
        auto plan = solver::planDay(
            solver::agentsOf(state.value().own_agents),
            solver::statusOf(state.value().traffic), before,
            steps, day_index + 1 == static_cast<int>(day_steps.size()),
            time_ms * 0.92);
#ifdef HEXUDON_TARGET530
        if (search.value("tailRepair", false)) {
            std::set<int> collected;
            if (root.contains("history")) {
                for (int brand : root["history"].value("distinct_brands", std::vector<int>{}))
                    collected.insert(brand);
            }
            duc::repair_tails(plan, solver::agentsOf(state.value().own_agents),
                solver::statusOf(state.value().traffic), steps, time_ms * 0.03,
                search.value("objectiveMode", std::string{}) == "MAX_TOTAL_UDON", collected);
        }
#endif
        const auto checked = solver::simulateDay(
            solver::agentsOf(state.value().own_agents), plan,
            solver::statusOf(state.value().traffic), steps);
        if (!checked.valid) throw std::runtime_error(checked.error);
        json response{{"ok", true}, {"plan", plan},
                          {"planner_state", {{"day_index", day_index},
                              {"traffic", solver::statusOf(state.value().traffic)}}},
                          {"diagnostics", {{"engine", "pro26_hieu_lns_sa"},
                                           {"threads", solver::threads},
                                           {"day_index", day_index},
                                           {"steps", steps},
                                           {"daily_types", checked.brands},
                                           {"total_udon_today", checked.balls},
                                           {"validated", true}}}};
#ifdef HEXUDON_LOOKAHEAD
        response["diagnostics"]["search_iterations"] = solver::ducIterations.load();
        response["diagnostics"]["evaluated_day_plans"] = solver::ducEvaluated.load();
        response["diagnostics"]["valid_day_evaluations"] = solver::ducValid.load();
        response["diagnostics"]["objective_mode"] = solver::ducMaxTotal ? "MAX_TOTAL_UDON" : "OFFICIAL_LEXICOGRAPHIC";
        response["diagnostics"]["cross_moves"] = solver::ducCrossMoves;
#endif
        std::cout << response.dump() << '\n';
    } catch (const std::exception& error) {
        std::cout << json{{"ok", false}, {"error", error.what()}}.dump()
                  << '\n';
        return 1;
    }
}
