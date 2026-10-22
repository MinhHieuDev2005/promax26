#include "hexa_udon/solver.hpp"
#include "hexa_udon/protocol/json_codec.hpp"
#include "hexa_udon/simulator/simulator.hpp"
#include <nlohmann/json.hpp>
#include <charconv>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <sys/resource.h>

namespace {
using namespace hexa_udon;
using Json = nlohmann::json;

long long number(const char* text, long long minimum, long long maximum) {
    long long value = 0;
    const std::string input(text);
    const auto parsed = std::from_chars(input.data(), input.data() + input.size(), value);
    if (parsed.ec != std::errc{} || parsed.ptr != input.data() + input.size()
        || value < minimum || value > maximum) throw std::invalid_argument("Invalid numeric argument");
    return value;
}

Json run(int argc, char** argv) {
    if (argc != 7) throw std::invalid_argument("Usage: solver_bench setting.json seed day_ms threads lineup|auto selection_ms");
    const auto seed = number(argv[2], 1, 1000000000);
    const auto budget = number(argv[3], 1, 60000);
    const auto worker_count = number(argv[4], 1, 8);
    const auto selection_budget = number(argv[6], 1, 60000);
    std::ifstream file(argv[1]);
    if (!file) throw std::invalid_argument("Cannot read setting");
    const std::string text{std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
    const auto decoded = protocol::decode_match_setting(text);
    if (!decoded) throw std::invalid_argument(decoded.error().message);
    const auto& match = decoded.value();
    if (match.players != 1 || match.spots.empty() || match.initial_agent_positions.empty()
        || match.initial_agent_positions.size() > 12 || match.day_steps.size() > 64)
        throw std::invalid_argument("Benchmark requires one team, 1-12 agents, spots and at most 64 days");
    std::set<int> positions;
    for (const auto& spot : match.spots) {
        if (!positions.insert(spot.position.value).second
            || match.map.terrain_at(spot.position) == core::Terrain::Pond)
            throw std::invalid_argument("Duplicate or impassable spot");
    }
    for (const auto& position : match.initial_agent_positions)
        if (match.map.terrain_at(position) == core::Terrain::Pond)
            throw std::invalid_argument("Impassable agent start");
    solver::loadProblem(match);
    solver::threads = static_cast<int>(worker_count);
    solver::rng.x = static_cast<uint64_t>(seed);
    solver::interimSec = 0;
    solver::yesterdayDay = -1;
    solver::yesterdayStatus.clear();
    std::vector<int> kinds;
    const std::string lineup(argv[5]);
    double selection_ms = 0;
    if (lineup == "auto") {
        solver::Timer timer;
        kinds = solver::solveKind(static_cast<double>(selection_budget));
        selection_ms = timer.ms();
    } else {
        if (lineup.size() != match.initial_agent_positions.size())
            throw std::invalid_argument("Lineup size mismatch");
        for (const char kind : lineup) {
            if (kind != '0' && kind != '1') throw std::invalid_argument("Invalid lineup kind");
            kinds.push_back(kind - '0');
        }
    }
    if (std::count(kinds.begin(), kinds.end(), 0) == 0)
        throw std::invalid_argument("At least one patrol required");
    solver::choosingKinds = false;
    std::vector<solver::Agent> agents;
    for (int index = 0; index < solver::NA; ++index)
        agents.push_back({kinds[index], solver::agentStart[index], solver::FUEL_LIMIT});
    std::vector<char> collected(solver::B, 0);
    std::vector<std::vector<long long>> stays;
    simulator::MatchProgress progress;
    Json days = Json::array();
    bool all_valid = true;
    for (int day = 0; day < solver::D; ++day) {
        std::vector<long long> total_stay(solver::NC, 0);
        for (int previous = std::max(0, day - 2); previous < day; ++previous)
            for (int cell = 0; cell < solver::NC; ++cell) total_stay[cell] += stays[previous][cell];
        const auto status = solver::statusFromStay(total_stay, 1);
        solver::today = day;
        solver::Timer timer;
        const auto plan = solver::planDay(agents, status, collected, solver::daySteps[day],
                                         day == solver::D - 1, static_cast<double>(budget) * 0.85);
        const double elapsed = timer.ms();
        const auto result = solver::simulateDay(agents, plan, status, solver::daySteps[day]);
        if (!result.valid) {
            all_valid = false;
            days.push_back({{"day", day}, {"valid", false}, {"elapsed_ms", elapsed}, {"error", result.error}});
            break;
        }
        simulator::DaySimulationResult official_day;
        official_day.total_balls = result.balls;
        for (int brand = 0; brand < solver::B; ++brand) {
            if (result.brandHit[brand]) official_day.distinct_brands.insert(solver::rawBrand[brand]);
            collected[brand] |= result.brandHit[brand];
        }
        progress = simulator::accumulate_progress(progress, official_day);
        std::vector<int> fuel, positions;
        for (const auto& agent : result.end) { fuel.push_back(agent.fuel); positions.push_back(agent.pos); }
        days.push_back({{"day", day}, {"valid", true}, {"elapsed_ms", elapsed},
                        {"brands", result.brands}, {"bowls", result.balls}, {"fuel", fuel},
                        {"positions", positions}, {"hits", result.brandHit}, {"collected", collected},
                        {"plan", plan}, {"status", status}, {"stay", result.stay}});
        agents = result.end;
        stays.push_back(result.stay);
    }
    struct rusage usage{};
    if (getrusage(RUSAGE_SELF, &usage) != 0) throw std::runtime_error("getrusage failed");
    return {{"score", {progress.acquired_brands.size(),
                       std::accumulate(progress.daily_distinct_brand_counts.begin(), progress.daily_distinct_brand_counts.end(), 0LL),
                       progress.total_balls}},
            {"valid", all_valid}, {"days", days}, {"kinds", kinds}, {"seed", seed},
            {"budget_ms", budget}, {"threads", worker_count}, {"selection_ms", selection_ms},
            {"selection_budget_ms", selection_budget}, {"peak_rss_kib", usage.ru_maxrss}};
}
}

int main(int argc, char** argv) {
    try {
        const auto result = run(argc, argv);
        std::cout << result.dump() << '\n';
        return result.at("valid").get<bool>() ? 0 : 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
