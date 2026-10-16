// Planner: 1 日の計画（初期解 → LNS ＋ 焼きなまし）（procon2026 の solvers/meet.cpp / common.hpp から移した。処理は元のまま）
#include "hexa_udon/solver.hpp"
#include <atomic>
#include "cross_routes.hpp"
#include "../stock_presence.hpp"

namespace hexa_udon::solver {

double ducFutureWeight = 0.0;
// Negative means adaptive: end-position guidance is useful before a changing
// horizon, but becomes a misleading surrogate on a flat repeated tail.
double ducEndSpotWeight = -1.0;
double ducTerminalAccessWeight = 0.0;
bool ducStockRepair = false;
bool ducMarginalStock = false;
bool ducPathStock = false;
bool ducMobileForecast = false;
bool ducIdleForecast = false;
bool ducActualRuin = false;
bool ducBoundarySelect = false;
bool ducClusterRuin = false;
bool ducDirectStockInsert = false;
bool ducTwoDaySelect = false;
bool ducHardFullMax = false;
bool ducDualHubSeeds = false;
bool ducStockBuildSeeds = false;
int ducCrossMoves = 0;
bool ducMaxTotal = false;
std::atomic<std::uint64_t> ducIterations{0}, ducEvaluated{0}, ducValid{0};
vector<char> ducBefore;

struct Planner {
    const vector<Agent>& st;
    int steps;
    bool lastDay;
    Router router;
    Router heavyRouter;
    static vector<int> predicted(const vector<int>& status) {
        if (ducIdleForecast) return status;
        vector<int> out = status;
        if (today == 0) {
            for (int c = 0; c < NC; c++) if (cellType[c] == ROAD) out[c] = max(out[c], 1);
            return out;
        }
        const bool hasYesterday = yesterdayDay == today - 1 && (int)yesterdayStatus.size() == NC;
        for (int c = 0; c < NC; c++) {
            if (cellType[c] != ROAD) continue;
            int nb = 0;
            for (int d = 0; d < 6; d++) {
                int q = neighbor(c, d);
                if (q >= 0 && cellType[q] == ROAD) nb = max(nb, status[q]);
            }
            const int s = status[c], y = hasYesterday ? yesterdayStatus[c] : 0;
            if (today == 1) {
                out[c] = s > 0 ? 2 : nb;
            } else if (s == 0) {
                out[c] = y == 2 ? (nb == 2 ? 2 : 1) : y == 1 ? (nb == 0 ? 0 : 1) : (nb == 2 ? 1 : 0);
            } else if (s == 1) {
                out[c] = y == 2 ? 2 : y == 1 ? 1 : (nb == 2 ? 2 : 1);
            } else {
                out[c] = y == 2 && nb <= 1 ? 1 : 2;
            }
        }
        return out;
    }
    vector<int> patrols, supplies;
    vector<vector<int>> brandSpots;
    vector<int> hubJump, hubCells;
    map<vector<int>, int> tomorrowMemo;
    map<vector<int>, int> tomorrowBallsMemo;
    // 出し直した計画。スレッドで並列に解くときは全スレッドで 1 つを共有する
    struct Emitted {
        mutex lock;
        double lasting = -1e18;
        vector<vector<int>> plan;
    };
    Emitted ownEmitted;
    Emitted* emitted = &ownEmitted;
    bool verbose = true;

    Planner(const vector<Agent>& st_, const vector<int>& status, int steps_, bool last)
        : st(st_), steps(steps_), lastDay(last), router(status), heavyRouter(predicted(status)), brandSpots(B) {
        for (int i = 0; i < NA; i++) (st[i].kind == 0 ? patrols : supplies).push_back(i);
        for (int s = 0; s < S; s++) brandSpots[spots[s].brand].push_back(s);
        for (int i : patrols) hubJump.push_back(st[i].pos);
        for (int s = 0; s < S; s++) hubJump.push_back(spots[s].pos);
        for (int c = 0; c < NC; c++) if (passable(c) && cellType[c] != ROAD) hubCells.push_back(c);
    }

    // 明日の朝の割り当てで入らない系列の数（道路の状態は今日のまま、補給車は今日の終わりの位置で待つとみなす）
    int tomorrowMisses(const vector<Agent>& end) {
        if (lastDay) return 0;
        vector<int> key;
        for (const Agent& a : end) { key.push_back(a.pos); key.push_back(a.fuel); }
        if (auto it = tomorrowMemo.find(key); it != tomorrowMemo.end()) return it->second;
        Day next(end, daySteps[today + 1], today + 1, router, patrols, supplies, brandSpots);
        vector<vector<pair<int, int>>> sch;
        for (int j : supplies) sch.push_back({{end[j].pos, INT_MAX}});
        next.setSchedule(sch);
        int missing;
        next.assignBrands(missing);
        Day heavy(end, daySteps[today + 1], today + 1, heavyRouter, patrols, supplies, brandSpots);
        heavy.setSchedule(sch);
        int heavyMissing;
        heavy.assignBrands(heavyMissing);
        return tomorrowMemo[key] = missing * 1000 + max(0, heavyMissing - missing);
    }

    double tomorrowPenalty(const vector<Agent>& end) {
        const int misses = tomorrowMisses(end);
        double penalty = ducMaxTotal ? 0.0 : E_TOMORROW * (misses / 1000) + E_TOMORROW_HEAVY * (misses % 1000);
        if (lastDay || ducFutureWeight <= 0.0) return penalty;
        vector<int> key;
        for (const auto& a : end) { key.push_back(a.pos); key.push_back(a.fuel); }
        auto cached = tomorrowBallsMemo.find(key);
        if (cached == tomorrowBallsMemo.end()) {
            Day next(end, daySteps[today + 1], today + 1, router, patrols, supplies, brandSpots);
            vector<vector<pair<int, int>>> schedule;
            for (int supply : supplies) schedule.push_back({{end[supply].pos, INT_MAX}});
            next.setSchedule(schedule);
            int missing = 0;
            auto routes = next.fill(next.assignBrands(missing), 0.0);
            auto evaluation = next.evaluate(routes);
            auto simulated = simulateDay(end, evaluation.plan, router.status, daySteps[today + 1]);
            int balls = simulated.valid ? simulated.balls : 0;
            int brands = simulated.valid ? simulated.brands : 0;
            // Rebuild patrol routes together with a relocated supply hub.
            // Forecast only: this never substitutes for actual next-day validation.
            if (ducMobileForecast && !supplies.empty()) {
                vector<pair<int,int>> hubs;
                for (int spot=0; spot<S; ++spot) {
                    int distance=router.get(end[supplies.front()].pos,0).t[spots[spot].pos];
                    if (distance!=INT_MAX) hubs.push_back({distance,spots[spot].pos});
                }
                sort(hubs.begin(),hubs.end());
                for (size_t h=0; h<min<size_t>(3,hubs.size()); ++h) {
                    auto alternative=schedule;
                    alternative[0]={{hubs[h].second,INT_MAX}};
                    next.setSchedule(alternative);
                    int misses=0;
                    auto trial=next.fill(next.assignBrands(misses),0.0);
                    auto result=simulateDay(end,next.toPlan(trial),router.status,daySteps[today+1]);
                    if (result.valid && make_pair(result.brands,result.balls)>make_pair(brands,balls)) {
                        brands=result.brands; balls=result.balls;
                    }
                }
            }
            if (tomorrowBallsMemo.size() >= 2048) tomorrowBallsMemo.clear();
            cached = tomorrowBallsMemo.emplace(std::move(key), balls).first;
        }
        return penalty - ducFutureWeight * cached->second;
    }

    double total(const Day::Eval& e) { return e.score < -1e17 ? e.score : e.score - tomorrowPenalty(e.end); }
    double lastingTotal(const Day::Eval& e) { return e.lasting < -1e17 ? e.lasting : e.lasting - tomorrowPenalty(e.end); }

    // 動き終えた時刻の項を除いた評価が良くなったときだけ出し直すのは、今日の玉にも翌日にも効かない改善で出し直すと回答時間で負けるため
    void emit(const vector<vector<int>>& plan, double lasting) {
        lock_guard<mutex> g(emitted->lock);
        if (lasting < emitted->lasting + EMIT_MIN_GAIN || lasting < -1e17) return;
        emitInterim(plan);
        emitted->lasting = lasting;
        emitted->plan = plan;
    }

    // 補給車の予定の候補: 今の位置、密度の高いスポット、巡回車の位置で一日中待つ
    vector<vector<vector<pair<int, int>>>> scheduleCandidates() {
        vector<vector<vector<pair<int, int>>>> out;
        if (supplies.empty()) return {{}};
        vector<double> density(S, 0);
        int np = max<int>(1, patrols.size());
        for (int s = 0; s < S; s++) {
            const PathTable& pt = router.get(spots[s].pos, 0);
            for (int u = 0; u < S; u++)
                if (pt.t[spots[u].pos] != INT_MAX) density[s] += min(spots[u].stock, np) / (1.0 + pt.t[spots[u].pos] / 8.0);
        }
        vector<int> order(S);
        iota(order.begin(), order.end(), 0);
        sort(order.begin(), order.end(), [&](int a, int b) { return density[a] > density[b]; });
        vector<int> cells;
        for (int j : supplies) cells.push_back(st[j].pos);
        for (int s : order) cells.push_back(spots[s].pos);
        for (int i : patrols) cells.push_back(st[i].pos);
        vector<vector<pair<int, int>>> base;
        for (int j : supplies) base.push_back({{st[j].pos, INT_MAX}});
        out.push_back(base);
        if (ducDualHubSeeds && !supplies.empty()) {
            const int shortlist=min<int>(8,order.size());
            struct Pair { double key; int first,second; };
            vector<Pair> pairs;
            for (int x=0;x<shortlist;++x) for (int y=x+1;y<shortlist;++y) {
                const int a=order[x],b=order[y];
                const int travel=router.get(spots[a].pos,0).t[spots[b].pos];
                if (travel==INT_MAX || travel>steps*2/3) continue;
                pairs.push_back({density[a]+density[b]+0.02*travel,a,b});
            }
            sort(pairs.begin(),pairs.end(),[](auto a,auto b){return a.key>b.key;});
            if (pairs.size()>12) pairs.resize(12);
            for (auto pair:pairs) {
                for (int reverseOrder=0;reverseOrder<2;++reverseOrder) {
                    auto schedule=base;
                    const int a=reverseOrder?pair.second:pair.first;
                    const int b=reverseOrder?pair.first:pair.second;
                    schedule[0]={{spots[a].pos,steps/2},{spots[b].pos,INT_MAX}};
                    out.push_back(std::move(schedule));
                }
            }
        }
        for (size_t j = 0; j < supplies.size(); j++)
            for (int c : cells) {
                if (c == st[supplies[j]].pos) continue;
                auto sch = base;
                sch[j] = {{c, INT_MAX}};
                out.push_back(sch);
            }
        return out;
    }

    struct Solution { vector<vector<pair<int, int>>> schedule; vector<vector<int>> routes; double score = -1e18; vector<vector<int>> plan; double lasting = -1e18; };

    Solution build(Day& day, const vector<vector<pair<int, int>>>& sch) {
        Solution s{sch};
        day.setSchedule(sch);
        int missing;
        s.routes = day.fill(day.assignBrands(missing), 0);
        Day::Eval e = day.evaluate(s.routes);
        s.score = total(e);
        s.plan = e.plan;
        s.lasting = lastingTotal(e);
        if (ducStockBuildSeeds) {
            vector<int> order(S);
            iota(order.begin(),order.end(),0);
            sort(order.begin(),order.end(),[&](int a,int b) {
                if (spots[a].stock!=spots[b].stock) return spots[a].stock>spots[b].stock;
                int da=INT_MAX,db=INT_MAX;
                for (int patrol:patrols) {
                    da=min(da,router.get(st[patrol].pos,0).t[spots[a].pos]);
                    db=min(db,router.get(st[patrol].pos,0).t[spots[b].pos]);
                }
                return da>db;
            });
            const int limit=min<int>(6,order.size());
            vector<vector<int>> seedSets;
            for (int i=0;i<limit;++i) seedSets.push_back({order[i]});
            for (int i=0;i<limit;++i) for (int j=i+1;j<limit;++j)
                if (router.get(spots[order[i]].pos,0).t[spots[order[j]].pos]>=steps/3)
                    seedSets.push_back({order[i],order[j]});
            if (seedSets.size()>12) seedSets.resize(12);
            for (const auto& seeds:seedSets) {
                vector<vector<int>> routes(patrols.size());
                vector<char> used(patrols.size(),0);
                for (int spot:seeds) {
                    const int demand=min(2,spots[spot].stock);
                    for (int unit=0;unit<demand;++unit) {
                        pair<int,int> nearest{INT_MAX,-1};
                        for (int pi=0;pi<(int)patrols.size();++pi) if (!used[pi])
                            nearest=min(nearest,make_pair(
                                router.get(st[patrols[pi]].pos,0).t[spots[spot].pos],pi));
                        if (nearest.first==INT_MAX) break;
                        used[nearest.second]=1;
                        routes[nearest.second].push_back(spot);
                    }
                }
                vector<char> required(B,1);
                if (!day.repair(routes,required,true,0.0,nullptr)) continue;
                Day::Eval candidate=day.evaluate(routes);
                const double score=total(candidate);
                if (score>s.score) {
                    s.routes=std::move(routes); s.score=score;
                    s.plan=std::move(candidate.plan); s.lasting=lastingTotal(candidate);
                }
            }
        }
        return s;
    }

    // 補給車の待機場所を動かす: 半分は近くへ 1〜3 歩（道路は避ける）、残りは巡回車の位置かスポット、ランダムな平地・山地
    int movedCell(int c) {
        int r = rng.nextInt(4);
        if (r < 2) {
            for (int k = 1 + rng.nextInt(3); k > 0; k--) {
                int nx = neighbor(c, rng.nextInt(6));
                if (passable(nx) && cellType[nx] != ROAD) c = nx;
            }
            return c;
        }
        if (r == 2) return hubJump[rng.nextInt(hubJump.size())];
        return hubCells[rng.nextInt(hubCells.size())];
    }

    static const int OPS = 11;
    static constexpr const char* OP_NAMES[OPS] = {"remove", "patrol", "near", "relocate", "reverse", "orOpt", "refuel", "station", "split", "tailSwap", "segmentTransfer"};

    // 経路か補給車の予定を変える。何も変えられなければ false
    bool perturb(Day& day, vector<vector<int>>& routes, vector<vector<pair<int, int>>>& sch, int op) {
        int P = routes.size();
        vector<pair<int, int>> visits;
        for (int pi = 0; pi < P; pi++)
            for (int k = 0; k < (int)routes[pi].size(); k++) visits.push_back({pi, k});
        if (op >= 9) {
            if (P < 2) return false;
            int a = rng.nextInt(P), b = (a + 1 + rng.nextInt(P - 1)) % P;
            if (op == 9)
                return duc_routes::exchange_tails(routes[a], routes[b],
                    rng.nextInt(routes[a].size() + 1), rng.nextInt(routes[b].size() + 1));
            if (routes[a].size() < 2) return false;
            int length = std::min<int>(2 + rng.nextInt(2), routes[a].size());
            return duc_routes::transfer_segment(routes[a], routes[b],
                rng.nextInt(routes[a].size() - length + 1), length,
                rng.nextInt(routes[b].size() + 1));
        }
        if (op <= 5 && visits.empty()) return false;
        if (op == 0) {
            int remove = 1 + rng.nextInt(max<int>(1, visits.size() / 5));
            for (int x = 0; x < remove; x++) swap(visits[x], visits[x + rng.nextInt(visits.size() - x)]);
            sort(visits.begin(), visits.begin() + remove, greater<>());
            for (int x = 0; x < remove; x++) routes[visits[x].first].erase(routes[visits[x].first].begin() + visits[x].second);
            return true;
        }
        auto [pi, k] = op <= 5 ? visits[rng.nextInt(visits.size())] : make_pair(rng.nextInt(max(1, P)), 0);
        if (op == 1) { routes[pi].clear(); return true; }
        if (op == 2) {
            const PathTable& pt = router.get(day.cellOf(routes[pi][k]), 0);
            int radius = steps / 16 + rng.nextInt(steps / 8 + 1);
            for (auto& r : routes) r.erase(remove_if(r.begin(), r.end(), [&](int v) { return v >= 0 && pt.t[spots[v].pos] <= radius; }), r.end());
            return true;
        }
        if (op == 3) {
            int v = routes[pi][k];
            if (P < 2 || v < 0) return false;
            int qi = (pi + 1 + rng.nextInt(P - 1)) % P;
            if (count(routes[qi].begin(), routes[qi].end(), v)) return false;
            routes[pi].erase(routes[pi].begin() + k);
            routes[qi].insert(routes[qi].begin() + rng.nextInt(routes[qi].size() + 1), v);
            return true;
        }
        if (op == 4) {
            if (routes[pi].size() < 2) return false;
            int j = rng.nextInt(routes[pi].size());
            reverse(routes[pi].begin() + min(k, j), routes[pi].begin() + max(k, j) + 1);
            return true;
        }
        if (op == 5) {
            vector<int>& r = routes[pi];
            int len = min<int>(1 + rng.nextInt(3), r.size() - k);
            vector<int> seg(r.begin() + k, r.begin() + k + len);
            r.erase(r.begin() + k, r.begin() + k + len);
            r.insert(r.begin() + rng.nextInt(r.size() + 1), seg.begin(), seg.end());
            return true;
        }
        if (P == 0) return false;
        if (op == 6) {
            vector<int>& r = routes[pi];
            auto it = find_if(r.begin(), r.end(), isRefuel);
            if (it != r.end() && rng.nextInt(2)) { r.erase(it); return true; }
            if (sch.empty()) return false;
            int j = rng.nextInt(sch.size()), kk = rng.nextInt(sch[j].size());
            r.insert(r.begin() + rng.nextInt(r.size() + 1), refuelNode(j, kk));
            return true;
        }
        if (sch.empty()) return false;
        int j = rng.nextInt(sch.size());
        if (op == 7) {
            int kk = rng.nextInt(sch[j].size());
            if (rng.nextInt(2) || sch[j].size() == 1) sch[j][kk].first = movedCell(sch[j][kk].first);
            else sch[j][kk].second = max(0, min(steps, sch[j][kk].second + (rng.nextInt(2) ? 1 : -1) * (1 + rng.nextInt(steps / 6 + 1))));
            return true;
        }
        // op == 8: 待機場所を足す（前半をどこかで待ってから今の場所へ）か、2 つ以上あれば 1 つ消す
        if (sch[j].size() >= 2 && rng.nextInt(2)) {
            int kk = rng.nextInt(sch[j].size());
            sch[j].erase(sch[j].begin() + kk);
            for (auto& r : routes) r.erase(remove_if(r.begin(), r.end(), [&](int v) { return isRefuel(v); }), r.end());
            return true;
        }
        if ((int)sch[j].size() >= MAX_STATIONS) return false;
        int c = hubJump[rng.nextInt(hubJump.size())];
        sch[j].insert(sch[j].begin(), {c, 1 + rng.nextInt(max(1, steps / 2))});
        for (auto& r : routes)
            for (int& v : r)
                if (isRefuel(v)) { int x = -1 - v; if (x / MAX_STATIONS == j) v = refuelNode(j, x % MAX_STATIONS + 1); }
        return true;
    }

    // 焼きなまし
    Solution improve(Solution cur, double timeMs) {
        Timer tm;
        Day day(st, steps, today, router, patrols, supplies, brandSpots);
        day.setSchedule(cur.schedule);
        Solution best = cur;
        double curScore = day.evaluate(cur.routes).score, bestRaw = curScore;
        vector<char> need = ducMaxTotal ? vector<char>(B, 0) : day.brandsOf(cur.routes);
        long long iter = 0, accepted = 0, tries[OPS] = {}, gains[OPS] = {};
        double lastEmit = 0, lastBest = 0;
        while (tm.ms() < timeMs) {
            if (interimSec > 0 && tm.ms() - lastEmit >= interimSec * 1000) { lastEmit = tm.ms(); emit(best.plan, best.lasting); }
            iter++;
            ducIterations.fetch_add(1, std::memory_order_relaxed);
            vector<vector<int>> next = cur.routes;
            auto sch = cur.schedule;
            vector<int> enabledOps{0, 1, 2, 3, 4, 5, 6, 7, 8};
            if (ducCrossMoves & 1) enabledOps.push_back(9);
            if (ducCrossMoves & 2) enabledOps.push_back(10);
            int op = enabledOps[rng.nextInt(enabledOps.size())];
            // しばらく一番良い解が更新されなければ、一番良い解から巡回車 2 台ぶんを壊してやり直す
            if (tm.ms() - lastBest > timeMs * (ducClusterRuin ? 0.07 : 0.15)) {
                cur = best;
                curScore = bestRaw;
                next = cur.routes;
                sch = cur.schedule;
                bool targeted = false;
                if ((ducCrossMoves & 4) && !next.empty()) {
                    auto reserved = day.reservedOf(next);
                    vector<vector<char>> seen;
                    if (ducActualRuin) {
                        reserved.assign(S,0);
                        for (int pi=0;pi<(int)next.size();++pi) {
                            seen.push_back(duc::stock_presence(st[patrols[pi]].pos,cur.plan[patrols[pi]],router.status));
                            for (int spot=0;spot<S;++spot) reserved[spot]+=seen.back()[spot];
                        }
                    }
                    int target = -1, bestTargetScore = -1;
                    for (int s = 0; s < S; ++s) {
                        const int missing = spots[s].stock - reserved[s];
                        if (missing <= 0) continue;
                        vector<int> distances;
                        for (int pi = 0; pi < (int)next.size(); ++pi) {
                            if (ducActualRuin && seen[pi][s]) continue;
                            const int distance = router.get(st[patrols[pi]].pos, 0).t[spots[s].pos];
                            if (distance != INT_MAX) distances.push_back(distance);
                        }
                        if (distances.empty()) continue;
                        sort(distances.begin(), distances.end());
                        const int difficulty = distances[min<int>(missing - 1, distances.size() - 1)];
                        const int targetScore = missing * 100000 + difficulty;
                        if (targetScore > bestTargetScore) {
                            target = s;
                            bestTargetScore = targetScore;
                        }
                    }
                    if (target >= 0) {
                        const int mostMissing = spots[target].stock - reserved[target];
                        if (ducDirectStockInsert) {
                            int inserted=0;
                            for (int unit=0;unit<min(2,mostMissing);++unit) {
                                Insertion bestInsertion;
                                int bestPatrol=-1;
                                for (int pi=0;pi<(int)next.size();++pi) {
                                    if (!seen.empty() && seen[pi][target]) continue;
                                    auto insertion=day.cheapestSpot(pi,next[pi],vector<int>{target},
                                        day.inRouteOf(next[pi]),reserved);
                                    if (insertion.cost<bestInsertion.cost) {
                                        bestInsertion=insertion;
                                        bestPatrol=pi;
                                    }
                                }
                                if (bestPatrol<0 || bestInsertion.cost==INT_MAX) break;
                                next[bestPatrol].insert(next[bestPatrol].begin()+bestInsertion.pos,target);
                                reserved[target]++;
                                if (!seen.empty()) seen[bestPatrol][target]=1;
                                ++inserted;
                            }
                            targeted=inserted>0;
                        }
                        if (targeted) {
                            // Keep current refueling schedule and every existing visit.
                        } else {
                        if (!sch.empty()) {
                            const int supply = rng.nextInt(sch.size());
                            if (ducActualRuin && !sch[supply].empty()) {
                                // Retain early refill hub, then move toward missing stock.
                                sch[supply].resize(1);
                                sch[supply][0].second=steps/2;
                                sch[supply].push_back({spots[target].pos,INT_MAX});
                                for (auto& route:next)
                                    route.erase(remove_if(route.begin(),route.end(),[&](int v) {
                                        return isRefuel(v) && v!=refuelNode(supply,0);
                                    }),route.end());
                            } else {
                                sch[supply] = {{spots[target].pos, INT_MAX}};
                                for (auto& route : next)
                                    route.erase(remove_if(route.begin(), route.end(), isRefuel), route.end());
                            }
                        }
                        vector<pair<int, int>> order;
                        for (int pi = 0; pi < (int)next.size(); ++pi) {
                            if (ducActualRuin && seen[pi][target]) continue;
                            // An existing visitor cannot supply another bowl at this spot.
                            if (ducStockRepair && (st[patrols[pi]].pos == spots[target].pos
                                || find(next[pi].begin(), next[pi].end(), target) != next[pi].end())) continue;
                            const auto& pt = router.get(st[patrols[pi]].pos, 0);
                            order.push_back({pt.t[spots[target].pos], pi});
                        }
                        sort(order.begin(), order.end());
                        int seeded = 0;
                        for (auto [distance, pi] : order) {
                            if (distance == INT_MAX || seeded >= min(2, mostMissing)) break;
                            next[pi] = {target};
                            ++seeded;
                        }
                        targeted = seeded > 0;
                        }
                    }
                    if (ducClusterRuin) {
                        struct Candidate { int score, spot; };
                        vector<Candidate> candidates;
                        for (int s=0;s<S;++s) {
                            int missing=spots[s].stock-reserved[s];
                            if (missing<=0) continue;
                            int nearest=INT_MAX;
                            for (int pi=0;pi<(int)next.size();++pi) {
                                if (!seen.empty() && seen[pi][s]) continue;
                                nearest=min(nearest,router.get(st[patrols[pi]].pos,0).t[spots[s].pos]);
                            }
                            if (nearest!=INT_MAX) candidates.push_back({missing*100000+nearest,s});
                        }
                        sort(candidates.begin(),candidates.end(),[](auto a,auto b){ return a.score>b.score; });
                        vector<int> chosen;
                        for (auto candidate:candidates) {
                            bool separated=true;
                            for (int other:chosen)
                                if (router.get(spots[other].pos,0).t[spots[candidate.spot].pos]<steps/3)
                                    separated=false;
                            if (separated) chosen.push_back(candidate.spot);
                            if (chosen.size()==2) break;
                        }
                        vector<char> used(next.size(),0);
                        int seeded=0;
                        for (int s:chosen) {
                            const int demand=min(2,spots[s].stock-reserved[s]);
                            for (int unit=0;unit<demand;++unit) {
                                pair<int,int> bestPatrol{INT_MAX,-1};
                                for (int pi=0;pi<(int)next.size();++pi) {
                                    if (used[pi] || (!seen.empty() && seen[pi][s])) continue;
                                    bestPatrol=min(bestPatrol,make_pair(
                                        router.get(st[patrols[pi]].pos,0).t[spots[s].pos],pi));
                                }
                                if (bestPatrol.first==INT_MAX) break;
                                used[bestPatrol.second]=1;
                                next[bestPatrol.second]={s};
                                ++seeded;
                            }
                        }
                        targeted=seeded>0;
                    }
                }
                if (!targeted)
                    for (int x = 0; x < 2 && !next.empty(); x++) next[rng.nextInt(next.size())].clear();
                lastBest = tm.ms();
                op = 1;
            } else if (!perturb(day, next, sch, op)) continue;
            bool schChanged = sch != day.schedule;
            if (schChanged) day.setSchedule(sch);
            bool ok = day.repair(next, need, iter % 10 == 0, rng.nextInt(2) ? LNS_NOISE : 0, schChanged ? nullptr : &cur.routes);
            double v = -1e18;
            Day::Eval e;
            if (ok) { e = day.evaluate(next); v = e.score; }
            if (v > -1e17) { tries[op]++; if (v > curScore + 1e-9) gains[op]++; }
            double temp = LNS_T0 * pow(LNS_T1 / LNS_T0, tm.ms() / timeMs);
            if (v > -1e17 && (v >= curScore || rng.nextDouble() < exp((v - curScore) / temp))) {
                cur.routes = next; cur.schedule = sch; curScore = v; accepted++;
                need = ducMaxTotal ? vector<char>(B, 0) : day.brandsOf(cur.routes);
                if (ducFutureWeight > 0.0 || v > best.score) {
                    double t = total(e);
                    if (t > best.score) { best = {sch, next, t, e.plan, lastingTotal(e)}; bestRaw = v; lastBest = tm.ms(); }
                }
            } else if (schChanged) day.setSchedule(cur.schedule);
        }
        if (verbose) {
            cerr << "[solver] iter=" << iter << " accepted=" << accepted << " score=" << best.score;
            for (int op = 0; op < OPS; op++) cerr << " " << OP_NAMES[op] << "=" << gains[op] << "/" << tries[op];
            cerr << "\n";
        }
        return best;
    }

    optional<Solution> warm;  // 1 日目が始まる前に作っておいた解（あればここから改善する）
    Solution result;

    vector<vector<int>> plan(double timeMs) {
        Timer tm;
        Day day(st, steps, today, router, patrols, supplies, brandSpots);
        Solution best;
        if (warm) {
            day.setSchedule(warm->schedule);
            Day::Eval e = day.evaluate(warm->routes);
            if (e.score > -1e17) best = {warm->schedule, warm->routes, total(e), e.plan, lastingTotal(e)};
        }
        // 作っておいた解は予定の候補を一通り試したあとのものなので、候補から作り直さずに改善へ進む
        if (best.score < -1e17) {
            auto cands = scheduleCandidates();
            if (choosingKinds && cands.size() > 8) cands.resize(8);
            for (auto& sch : cands) {
                if (best.score > -1e17 && tm.ms() > timeMs * 0.3) break;
                Solution s = build(day, sch);
                if (s.score > best.score) best = s;
            }
        }
        if (best.score < -1e17) return allWait(steps);
        if (!choosingKinds) emit(best.plan, best.lasting);
        best = improve(best, timeMs - tm.ms());
        result = best;
        if (!choosingKinds && interimSec > 0 && emitted->lasting + EMIT_MIN_GAIN > best.lasting) return emitted->plan;
        return best.plan;
    }
};

namespace {

// 乱数の種だけを変えた焼きなましを threads 本同時に回し、一番良い解と、提出する計画を返す。
// 焼きなましは時間内に収束していても、種によって行き着く解が違い、良い方を選ぶと玉が増えるため。
// スレッド 0 は 1 本で解くときと同じ種を使う
pair<Planner::Solution, vector<vector<int>>> solveDay(const vector<Agent>& st, const vector<int>& status, int steps,
                                                      bool lastDay, double timeMs, const optional<Planner::Solution>& warm) {
    int T = max(1, threads);
    if (T == 1) {
        Planner p(st, status, steps, lastDay);
        p.warm = warm;
        auto plan = p.plan(timeMs);
        return {p.result, plan};
    }
    Planner::Emitted emitted;
    vector<Planner::Solution> results(T);
    vector<vector<vector<int>>> plans(T);
    Rng base = rng;
    vector<thread> workers;
    for (int k = 0; k < T; k++)
        workers.emplace_back([&, k] {
            rng = base;
            rng.x ^= (uint64_t)k * 0x9E3779B97F4A7C15ULL;
            Planner p(st, status, steps, lastDay);
            p.emitted = &emitted;
            p.verbose = k == 0;
            p.warm = warm;
            plans[k] = p.plan(timeMs);
            results[k] = p.result;
        });
    for (auto& w : workers) w.join();
    int bestK = 0;
    auto officialRank = [&](int k) {
        const auto simulated = simulateDay(st, plans[k], status, steps);
        if (!simulated.valid) return make_tuple(-1, -1, -1);
        int fresh = 0;
        for (int b = 0; b < B; ++b)
            if (simulated.brandHit[b] && (ducBefore.empty() || !ducBefore[b])) ++fresh;
        return ducMaxTotal ? make_tuple(simulated.balls, fresh, simulated.brands)
                           : make_tuple(fresh, simulated.brands, simulated.balls);
    };
    auto bestRank = officialRank(0);
    auto boundaryRank = [&](int k) {
        if (!ducBoundarySelect || lastDay) return make_pair(0,0);
        auto actual=simulateDay(st,plans[k],status,steps);
        if (!actual.valid) return make_pair(-1,-1);
        Router forecastRouter(status);
        vector<int> patrols,supplies;
        vector<vector<int>> brandSpots(B);
        for (int i=0;i<NA;++i) (st[i].kind==0?patrols:supplies).push_back(i);
        for (int s=0;s<S;++s) brandSpots[spots[s].brand].push_back(s);
        Day next(actual.end,daySteps[today+1],today+1,forecastRouter,patrols,supplies,brandSpots);
        vector<vector<pair<int,int>>> schedule;
        for (int i:supplies) schedule.push_back({{actual.end[i].pos,INT_MAX}});
        auto result=make_pair(-1,-1);
        vector<int> hubs{-1};
        if (!supplies.empty()) {
            vector<pair<int,int>> nearby;
            const auto& pt=forecastRouter.get(actual.end[supplies[0]].pos,0);
            for (int s=0;s<S;++s) if (pt.t[spots[s].pos]!=INT_MAX)
                nearby.push_back({pt.t[spots[s].pos],spots[s].pos});
            sort(nearby.begin(),nearby.end());
            for (int j=0;j<min<int>(3,nearby.size());++j) hubs.push_back(nearby[j].second);
        }
        // Fair comparisons: identical random stream for each boundary candidate.
        const auto savedRng=rng;
        for (int hub:hubs) {
            rng=savedRng;
            auto trialSchedule=schedule;
            if (hub>=0) trialSchedule[0]={{hub,INT_MAX}};
            next.setSchedule(trialSchedule);
            int missing=0;
            auto routes=next.fill(next.assignBrands(missing),0.0);
            auto predicted=simulateDay(actual.end,next.toPlan(routes),status,daySteps[today+1]);
            if (predicted.valid) result=max(result,make_pair(predicted.brands,predicted.balls));
        }
        rng=savedRng;
        return result;
    };
    vector<optional<pair<int,int>>> boundaryCache(T);
    auto futureRank=[&](int k) {
        if (!boundaryCache[k]) boundaryCache[k]=boundaryRank(k);
        return *boundaryCache[k];
    };
    auto twoDayRank=[&](int k) {
        auto current=officialRank(k);
        auto future=futureRank(k);
        return make_tuple(get<0>(current),get<1>(current),get<2>(current)+future.second,
                          future.first,get<2>(current));
    };
    for (int k = 1; k < T; k++) {
        auto rank = officialRank(k);
        const bool twoDayBetter=ducTwoDaySelect && twoDayRank(k)>twoDayRank(bestK);
        const bool tiedBetter=!ducTwoDaySelect && rank==bestRank &&
            (futureRank(k)>futureRank(bestK) ||
             (futureRank(k)==futureRank(bestK) && results[k].score>results[bestK].score));
        if (twoDayBetter || (!ducTwoDaySelect && rank > bestRank) || tiedBetter) {
            bestK = k;
            bestRank = rank;
        }
    }
    cerr << "[solver] threads=" << T << " best=" << bestK << " score=" << results[bestK].score << "\n";
    if (results[bestK].score < -1e17) return {results[bestK], plans[0]};
    // 出し直した計画より良くなっていなければ、出し直した計画をそのまま返す（回答時間で負けないため）
    if (interimSec > 0 && emitted.lasting + EMIT_MIN_GAIN > results[bestK].lasting) return {results[bestK], emitted.plan};
    return {results[bestK], results[bestK].plan};
}

// planDay0 が作った 1 日目の解と、そのときの朝の状態
struct Day0Plan {
    vector<Agent> st;
    Planner::Solution solution;
};
optional<Day0Plan> day0Plan;
mutex day0Lock;

bool sameAgents(const vector<Agent>& a, const vector<Agent>& b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); i++)
        if (a[i].kind != b[i].kind || a[i].pos != b[i].pos || a[i].fuel != b[i].fuel) return false;
    return true;
}

}  // namespace

vector<vector<int>> planDay(const vector<Agent>& st, const vector<int>& status, const vector<char>& before,
                            int steps, bool lastDay, double timeMs) {
    ducBefore = before.size() == static_cast<size_t>(B) ? before : vector<char>(B, 0);
    optional<Planner::Solution> warm;
    if (today == 0 && !choosingKinds) {
        lock_guard<mutex> g(day0Lock);
        if (day0Plan && sameAgents(day0Plan->st, st)) warm = day0Plan->solution;
        day0Plan.reset();
    }
    if (warm) cerr << "[solver] 1 日目が始まる前に作った解から始める\n";
    auto plan = solveDay(st, status, steps, lastDay, timeMs, warm).second;
    if (!choosingKinds) { yesterdayStatus = status; yesterdayDay = today; }
    return plan;
}

void planDay0(const vector<int>& kinds, double timeMs) {
    if (timeMs <= 0) return;
    vector<Agent> st(NA);
    for (int i = 0; i < NA; i++) st[i] = {kinds[i], agentStart[i], FUEL_LIMIT};
    today = 0;
    // 1 日目の道路は全部空いている（ルール）
    auto solution = solveDay(st, vector<int>(NC, 0), daySteps[0], D == 1, timeMs, nullopt).first;
    cerr << "[solver] 1 日目を " << (int)timeMs << "ms 計画しておいた score=" << solution.score << "\n";
    if (solution.score < -1e17) return;
    lock_guard<mutex> g(day0Lock);
    day0Plan = Day0Plan{st, solution};
}

}  // namespace hexa_udon::solver
