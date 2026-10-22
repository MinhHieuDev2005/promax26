# Algorithm Research Round 4: Structural Overnight Search

## 1. Executive Summary & Core Results

Round 4 investigated the structural limitation identified in Round 3:
**The existing solver cannot naturally plan multi-day traversals because routes terminate at stores or refueling nodes within the day, causing idle patrols to remain stationary when bridging movement across day boundaries is required.**

Four independent variants were constructed and evaluated under strictly controlled conditions (WSL HexaUdon Ubuntu, GCC 13.3 Release, identical CPU affinity 0-7, 1000 ms/day budget, 1 worker or 8 workers, official lexicographic objective `(match brands, cumulative daily brands, bowls)`):

- **A (Baseline)**: Frozen production baseline (`219b544`, with collected-brand history).
- **B (Round 3 Relocation)**: Greedy idle-only relocation to nearest uncollected brand in `toPlan`.
- **C (Explicit Waypoint Search)**: Optimization decision over bounded candidate overnight waypoints (WAIT, partial path midway, full path) scored by multi-day accessibility profile and fuel conservation.
- **D (Two-Day Rollout)**: Shortlisted top candidates from C evaluated via an approximate next-day simulation (`today + 1`).

### Exact Reference & Toy Scenario Validation

A small-instance exact brute-force solver (`tests/benchmark/round4_exact.cpp`) was built to establish ground truth on 8x8 plain maps with 1 patrol:
- `check-unreachable.json` (7 steps away, fuel 2, 4 days): Exact = `[0, 0, 0]`. Proven unreachable.
- `check-wait.json` (at store, fuel 12, 4 days): Exact = `[1, 4, 4]`. Proven optimal to WAIT.
- `check-bridge.json` (7 steps away, fuel 12, 4 days): Exact = `[1, 1, 1]`. Baseline A gets `[0, 0, 0]` (fails completely). Variants B, C, D all score `[1, 1, 1]`, matching the exact theoretical optimum.

### Benchmark Suite Overview (66 Matches Total)

- **Development Set (Map 701, Seed 21, 12 paired matches)**:
  * **C vs A**: 7 wins / 4 ties / 1 loss (Mean brands: 8.25 vs 6.42)
  * **B vs A**: 6 wins / 5 ties / 1 loss (Mean brands: 8.00 vs 6.42)
  * **C vs B**: 3 wins / 6 ties / 3 losses (Mean brands: 8.25 vs 8.00)
- **Held-out Set (Maps 811 & 1201, Seed 22, 24 paired matches)**:
  * **C vs A**: 8 wins / 12 ties / 4 losses (Mean brands: 8.21 vs 6.71)
  * **B vs A**: 9 wins / 10 ties / 5 losses (Mean brands: 8.00 vs 6.71)
  * **C vs B**: 7 wins / 11 ties / 6 losses (Mean brands: 8.21 vs 8.00)
  * **D vs C**: 4 wins / 16 ties / 4 losses (Exact parity in W/L)
- **Auto-Lineup Set (Map 919, Seed 23, 8 workers, 2500 ms selection budget, 6 matches)**:
  * **B vs A**: 4 wins / 2 ties / 0 losses
  * **C vs A**: 2 wins / 4 ties / 0 losses
  * **C vs B**: 1 win / 3 ties / 2 losses

Production source code and GUI binary (`/home/hexa/build-release/hexa_udon`) were **strictly preserved** and not modified. 100% of unit tests and simulator validity checks passed across all versions.

---

## 2. Root-Cause Analysis of Round 3 Regressions

In Round 3, the prototype `relocation.patch` improved `tight16` from 10 to 12 brands, but caused regressions on `tight32` and other instances. Analysis of the logs and state transitions reveals the following root causes:

1. **Absence of a WAIT Decision**:
   In Round 3, `relocation.patch` hardcoded a greedy rule in `Day::toPlan`: if an idle patrol had no route and was not at a spot, it *always* moved toward the closest spot of an uncollected brand. There was no mechanism to decide that remaining in place (WAIT) was superior, for instance when tomorrow's fuel reservation or traffic made waiting at the current road/hub cell better.
2. **Greedy Spatial Clustering / Interference**:
   When multiple patrols were idle, Round 3 assigned them sequentially to the nearest uncollected brand without checking if they were converging on the same geographic quadrant or competing for the same multi-day corridor. In `fork` scenarios (where targets lie in 4 separate corners), Round 3 clustered patrols toward one side, leaving other corners unvisited.
3. **Lack of Multi-Day Opportunity Cost**:
   Moving 5 steps today burns fuel and positions the agent at an arbitrary cell. If tomorrow's required reachability needs a full tank from an accessible road, that spent fuel permanently closes future options.

---

## 3. Architecture & Design of Candidate Generator (Variant C)

Variant C formalizes overnight waypoint selection as a post-LNS decision problem for idle patrols:

### Candidate Generation

For each idle patrol $p$ that does not currently have planned actions:
1. **WAIT Candidate**: Retain the incumbent plan (waiting at current position $s_0$).
2. **Directional Waypoint Candidates**:
   - For every brand $b \notin \text{before}$ not visited today:
     - For mode $\in \{0 \text{ (fast)}, 1 \text{ (cheap)}\}$:
       - Check if total distance to spot fits $p$'s total remaining fuel.
       - Trace path cells $P = \langle c_0, c_1, \dots, c_k \rangle$.
       - Truncate $P$ at the maximum allowable fuel and time for today:
         $\text{fuel} \le \text{allowance}(p), \quad \text{time} \le \text{steps}$.
       - Generate candidate prefixes at intermediate waypoints (e.g., halfway and terminal reachable point).
3. **Pruning & Deduplication**:
   - Hash each candidate's exact action sequence to eliminate duplicates.
   - Discard invalid candidates or candidates that reduce today's immediate reward.
   - Bounded candidate pool: Sort candidates by projected score and retain top $K = 4$.

### Evaluation Function (Opportunity-Cost Aware)

Each shortlisted candidate is evaluated via a lexicographic key:
$$\text{Key} = \Big(\text{Today Brands}, \text{Horizon Unique Brands}, \text{Next Day Potential}, \text{Bowls}, \text{Fuel Reserve}\Big)$$
where:
- **Horizon Unique Brands**: A forward reachability vector tracking how many distinct uncollected brands can be reached across days $d \in \{today+1, \dots, D-1\}$ under fuel conservation constraints.
- **Next Day Potential**: Immediate 1-day brand accessibility from the overnight resting position.
- If no candidate strictly exceeds WAIT on this multi-day key, the solver **preserves WAIT**.

---

## 4. Two-Day Rollout Evaluator (Variant D)

Variant D implemented an experimental two-day rollout on top of Variant C:
- For each shortlisted candidate (including WAIT):
  1. Apply today's plan and obtain endpoint state $(x, \text{fuel}, \text{stay})$.
  2. Compute traffic forecast for tomorrow combining `Planner::predicted(status)` and today's own traffic.
  3. Instantiate a lightweight `Day` planner for day $today + 1$ with the resulting persistent state and brand history.
  4. Run greedy regret assignment (`assignBrands` + `fill`) to simulate tomorrow's outcome.
  5. Combine today's official score with tomorrow's simulated score.

### Empirical Findings on Rollout (D vs C)

- **CPU Overhead**: Rollout added an average of 0.58 ms (max 7.57 ms) per evaluated candidate. In total, 68 rollouts ran in development and 178 in held-out.
- **Solution Quality**:
  * Development: 1 win / 9 ties / 2 losses vs C.
  * Held-out: 4 wins / 16 ties / 4 losses vs C (exact 50% split).
- **Why Rollout Did Not Beat C**:
  Tomorrow's traffic is only an approximation, and a single greedy construction without local search often misjudges what LNS can achieve on day 2. In `bridge-701-supply-21`, rollout rejected a valuable bridging move because the greedy 1-day lookahead failed to find the subsequent route that LNS easily discovers.
- **Conclusion on Rollout**: The lightweight accessibility profile in C is both faster and more robust than an unannealed next-day simulation.

---

## 5. Comparative Benchmark Matrix (A / B / C / D)

All metrics recorded with identical random seeds, wall-clock budget (1000 ms/day), 1 worker (8 workers for auto):

| Metric | A (Baseline) | B (R3 Reloc) | C (Waypoint) | D (Rollout) |
|---|---:|---:|---:|---:|
| **Dev Mean Brands** | 6.42 | 8.00 | **8.25** | 8.00 |
| **Dev Mean Bowls** | 18.33 | **23.58** | 22.92 | 23.00 |
| **Dev P95 Time (ms)** | 873.12 | 879.46 | 862.59 | 861.26 |
| **Held-out Mean Brands** | 6.71 | 8.00 | **8.21** | 8.17 |
| **Held-out Mean Bowls** | 18.75 | **23.42** | 23.38 | 23.88 |
| **Held-out P95 Time (ms)** | 889.88 | 890.63 | 861.93 | 863.77 |
| **Valid Matches** | 36/36 | 36/36 | 36/36 | 36/36 |
| **Deadline Success Rate** | 100% | 100% | 100% | 100% |

### Head-to-Head Win / Tie / Loss Summary

| Comparison | Development (12 matches) | Held-out (24 matches) | Total Paired (36 matches) |
|---|:---:|:---:|:---:|
| **B vs A** | 6 / 5 / 1 | 9 / 10 / 5 | **15 / 15 / 6** |
| **C vs A** | 7 / 4 / 1 | 8 / 12 / 4 | **15 / 16 / 5** |
| **C vs B** | 3 / 6 / 3 | 7 / 11 / 6 | **10 / 17 / 9** |
| **D vs C** | 1 / 9 / 2 | 4 / 16 / 4 | **5 / 25 / 6** |

---

## 6. Analysis of Remaining Losses & Failure Modes

Examining the instances where C lost against B:

1. **Prematch Vehicle Selection Interaction (`bridge-919-auto-23`)**:
   - In B, `solveKind` selected `[0, 0, 0]` (all patrols) and achieved `(10, 23, 23)`.
   - In C, `solveKind` selected `[0, 0, 1]` (one supply car) and achieved `(9, 16, 16)`.
   - *Cause*: In prematch selection, `simulateMatch` uses a very small time budget per candidate. Variant C's waypoint evaluation altered the tie-breaking scores of intermediate candidate matches, causing the selector to prefer a supply car that remained idle on Day 0.
2. **Over-Conservative Fuel Pruning (`bridge-811-supply-22`)**:
   - In B, patrol 1 moved aggressively to cell 134 on day 0, enabling 5 brands on day 1 and 10 brands overall `[10, 20, 20]`.
   - In C, the multi-day horizon score gave higher weight to staying near cell 103 to guard an alternative brand, resulting in `[9, 17, 18]`.
   - *Lesson*: When multiple brands have identical future distance, static reachability counts do not differentiate between isolated brands and brand clusters.

---

## 7. Decision & Research Recommendations

### Scientific Status: **EXPERIMENTAL CANDIDATE (DO NOT DEPLOY YET)**

- **Baseline A** remains the production version in the repository.
- **Variant C** is the strongest algorithmic formulation found: it outperforms Baseline A by **+1.50 primary brands** on held-out tests and outperforms B on `fork`, `fuel`, and `rendezvous` cases.
- However, Variant C does not achieve universal dominance over B (10 wins, 9 losses head-to-head), and its interaction with `solveKind` in prematch vehicle selection requires further stabilization.
- **Variant D (Two-Day Rollout)** is **REJECTED**: the CPU overhead and greedy simulation noise do not justify replacing C's analytic reachability profile.

### Recommended Next Steps for Round 5:

1. **Cluster-Aware Waypoint Heuristic**: Weight target brand reachability by local density (favoring moves that open access to multiple unvisited stores rather than a single isolated store).
2. **Integrated LNS Move**: Move waypoint optimization directly inside LNS/SA as a destroy-and-repair move rather than a sequential post-processing step.
3. **Vehicle Selector Harmonization**: Ensure `solveKind` evaluates matches using the identical candidate generation policy without budget-induced score distortion.
