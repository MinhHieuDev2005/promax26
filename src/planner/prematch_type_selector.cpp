// 種別決め: 種別の候補ごとに全日程を回して比べる（procon2026 の solvers/meet.cpp / common.hpp から移した。処理は元のまま）
#include "hexa_udon/solver.hpp"

namespace hexa_udon::solver {

vector<vector<int>> kindsWithSupplies(int k) {
    vector<vector<int>> out;
    for (int mask = 0; mask < (1 << NA); mask++) {
        if (__builtin_popcount(mask) != k) continue;
        vector<int> kinds(NA, 0);
        for (int i = 0; i < NA; i++) if (mask >> i & 1) kinds[i] = 1;
        out.push_back(kinds);
    }
    return out;
}

vector<vector<int>> kindCandidates() {
    vector<int> status0(NC, 0);
    Router router(status0);
    vector<long long> spread(NA, 0);
    for (int i = 0; i < NA; i++)
        for (int s = 0; s < S; s++) spread[i] += router.get(agentStart[i], 0).t[spots[s].pos];
    auto spreadOf = [&](const vector<int>& kinds) {
        long long c = 0;
        for (int i = 0; i < NA; i++) if (kinds[i]) c += spread[i];
        return c;
    };
    auto byCentrality = [&](vector<vector<int>> v) {
        stable_sort(v.begin(), v.end(), [&](auto& a, auto& b) { return spreadOf(a) < spreadOf(b); });
        return v;
    };
    bool tight = *max_element(daySteps.begin(), daySteps.end()) >= FUEL_TIGHT * FUEL_LIMIT;
    vector<vector<int>> singles = byCentrality(kindsWithSupplies(1)), multi;
    for (int m = 2; m <= min(3, NA / 2); m++) {
        vector<vector<int>> combos = byCentrality(kindsWithSupplies(m));
        multi.insert(multi.end(), combos.begin(), combos.begin() + (tight ? combos.size() : 1));
    }
    vector<vector<int>> cands;
    size_t head = tight ? min<size_t>(2, singles.size()) : singles.size();
    cands.insert(cands.end(), singles.begin(), singles.begin() + head);
    cands.insert(cands.end(), multi.begin(), multi.end());
    cands.insert(cands.end(), singles.begin() + head, singles.end());
    cands.push_back(vector<int>(NA, 0));
    return cands;
}

MatchScore simulateMatch(const vector<int>& kinds, double timeMs, bool busy) {
    Timer timer;
    vector<Agent> st(NA);
    for (int i = 0; i < NA; i++) st[i] = {kinds[i], agentStart[i], FUEL_LIMIT};
    vector<char> collected(B, 0);
    vector<vector<long long>> stays;
    MatchScore ms;
    for (int d = 0; d < D; d++) {
        vector<long long> sum(NC, 0);
        for (int k = max(0, d - 2); k < d; k++) for (int p = 0; p < NC; p++) sum[p] += stays[k][p];
        vector<int> status = statusFromStay(sum, 1);
        if (busy && d > 0)
            for (int c = 0; c < NC; c++) if (cellType[c] == ROAD) status[c] = max(status[c], 1);
        today = d;
        const double remaining = timeMs - timer.ms();
        if (remaining <= 0) return {-1, -1, -1};
        auto plan = planDay(st, status, collected, daySteps[d], d == D - 1, remaining / (D - d));
        DayResult r = simulateDay(st, plan, status, daySteps[d]);
        if (!r.valid) r = simulateDay(st, allWait(daySteps[d]), status, daySteps[d]);
        for (int b = 0; b < B; b++) collected[b] |= r.brandHit[b];
        ms.dayBrands += r.brands; ms.balls += r.balls;
        stays.push_back(r.stay);
        st = r.end;
    }
    for (int b = 0; b < B; b++) ms.matchBrands += collected[b];
    return ms;
}

pair<MatchScore, MatchScore> kindEvidence(vector<MatchScore> scores) {
    if (scores.empty()) return {{-1, -1, -1}, {-1, -1, -1}};
    sort(scores.begin(), scores.end());
    return {scores[(scores.size() - 1) / 2], scores.front()};
}

vector<int> solveKind(double timeMs) {
    const auto saved_rng = rng;
    const auto saved_day = today;
    const auto saved_choosing = choosingKinds;
    choosingKinds = true;
    Timer timer;
    auto candidates = kindCandidates();
    const double screening_end = max(0.0, timeMs * 0.35);
    const double screening_slice = max(0.0, screening_end - timer.ms()) / candidates.size();
    const auto evaluate = [&](size_t candidate, double slice, uint64_t seed) {
        const double end = min(timeMs, timer.ms() + slice);
        rng.x = seed;
        const auto smooth = simulateMatch(candidates[candidate], max(0.0, end - timer.ms()) / 2);
        rng.x = seed;
        const auto heavy = simulateMatch(candidates[candidate], max(0.0, end - timer.ms()), true);
        if (smooth.matchBrands < 0 || heavy.matchBrands < 0) return MatchScore{-1, -1, -1};
        return MatchScore{min(smooth.matchBrands, heavy.matchBrands),
                          min(smooth.dayBrands, heavy.dayBrands), min(smooth.balls, heavy.balls)};
    };
    vector<pair<MatchScore, size_t>> screened;
    for (size_t candidate = 0; candidate < candidates.size(); ++candidate) {
        if (timer.ms() >= screening_end) break;
        const auto score = evaluate(candidate, min(screening_slice, screening_end - timer.ms()), saved_rng.x);
        if (score.matchBrands >= 0) screened.emplace_back(score, candidate);
        cerr << "[kind] stage=screen candidate=" << candidate << " brands=" << score.matchBrands
             << " dayBrands=" << score.dayBrands << " balls=" << score.balls << '\n';
    }
    stable_sort(screened.begin(), screened.end(), [](const auto& left, const auto& right) {
        return right.first < left.first;
    });
    if (screened.size() > 3) screened.resize(3);
    size_t selected = screened.empty() ? 0 : screened.front().second;
    vector<vector<MatchScore>> evidence(screened.size());
    const double slice = max(0.0, timeMs - timer.ms()) / max<size_t>(1, screened.size() * 3);
    for (size_t round = 0; round < 3 && !screened.empty(); ++round) {
        vector<MatchScore> scores;
        for (const auto& candidate : screened) {
            if (timer.ms() >= timeMs) break;
            const auto score = evaluate(candidate.second, slice,
                saved_rng.x ^ ((round + 1) * 0x9E3779B97F4A7C15ULL));
            if (score.matchBrands < 0) break;
            scores.push_back(score);
        }
        if (scores.size() != screened.size()) break;
        for (size_t index = 0; index < scores.size(); ++index) {
            evidence[index].push_back(scores[index]);
            cerr << "[kind] stage=verify round=" << round + 1 << " candidate=" << screened[index].second
                 << " brands=" << scores[index].matchBrands << " dayBrands=" << scores[index].dayBrands
                 << " balls=" << scores[index].balls << '\n';
        }
        size_t winner = 0;
        for (size_t index = 1; index < scores.size(); ++index)
            if (kindEvidence(evidence[winner]) < kindEvidence(evidence[index])) winner = index;
        selected = screened[winner].second;
    }
    cerr << "[kind] selected=" << selected << " rounds=" << (evidence.empty() ? 0 : evidence.front().size())
         << " elapsedMs=" << timer.ms() << '\n';
    rng = saved_rng;
    today = saved_day;
    choosingKinds = saved_choosing;
    return candidates[selected];
}

}  // namespace hexa_udon::solver
