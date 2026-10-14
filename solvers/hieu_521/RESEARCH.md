# Research for the 530-udon target

Date: 2026-10-14. Work in progress; no 530 result has been established.

## Verified sources

- [Official competition page](https://www.procon.gr.jp/) confirms HEXUDON and the October 10–11 final. Its download section contains the rules, action clarifications and API format. Its livestream links are leads, not evidence of any team's algorithm.
- [Official results and problem data](https://www.procon.gr.jp/news/2026/10/10/125/) were accessible during this investigation.
- [taiki288/test](https://github.com/taiki288/test), local commit `d8f2c9a1a30b9380000c0f5585894a9bc173ba46`.
- [yoshikawar/30013-o-udon](https://github.com/yoshikawar/30013-o-udon), local commit `2c2c2dde0adbd69c60113ba0bf433b8fe054f8f2`.
- [HIT_Procon_2026, khanh](https://github.com/nddKhanh/HIT_Procon_2026/tree/khanh), retrieved commit `a41b875196304f77f75cc15a5c83ab71069a1a2e`. Web rendering failed, but Git access succeeded. No supplied binary or build script was executed.

## Algorithms verified in source

The Hieu planner has nine LNS operators: random removal, whole-patrol removal, spatial removal, relocation between patrols, reversal, short-segment relocation, refueling insertion/removal, station mutation and station splitting. The temperature decays exponentially from 2.0 to 0.02. Stagnation triggers destruction of two patrol routes. Each worker runs an independent RNG stream. Routes and insertion calculations are cached; candidate evaluation still simulates a full day.

Refueling schedules contain station positions and occupancy windows. Greedy construction assigns missing brands, then fills remaining capacity. A next-day heuristic penalizes missing brands under current and predicted traffic. This is not a full multi-day optimizer. The adapter discards previous traffic history on each invocation, reducing prediction quality.

The role selector forecasts the complete match under smooth and busy traffic. It allows cumulative-brand tolerance of 1.5% (at least one brand) before preferring fewer supply vehicles. **This does not impose the user's hard full-coverage constraint.** The previous statement that this selector uses strict final lexicographic comparison was inaccurate. The 521 result used manually fixed roles.

Khanh `HexaUdon2/src/solver/Solver.cpp` contains simulator-ranked route candidates, different patrol orders, optional spatial regions, explicit assignments for missing brands, and route detours. Its short list can be reranked by a real next-day rollout. `SupplyPlanner.cpp` searches refueling rendezvous and extends patrol suffixes. Beam/SA claims must distinguish these concrete bounded candidate searches from an unverified general optimizer. Some comments describe future work, not implemented features.

## Engineering findings and next experiments

1. Correct protocol indexing before comparing algorithms: benchmark `day_info.day` is zero-based; GUI `state.day` is one-based. Infer neither from repeated schedule lengths.
2. Honor explicit random seeds. The old adapter ignored `randomSeed`, so changing it did not change the intended RNG initialization.
3. Honor up to 55 seconds requested by the GUI, retaining the existing 8% search margin. Compare algorithms at the same requested budget; extra time alone is not algorithmic improvement.
4. Preserve previous traffic in planner state, then A/B test next-day prediction.
5. Evaluate endpoint and fuel choices with an actual next-day rollout, inspired by the Khanh implementation. Keep current-day full coverage as a hard filter for this target.

The user's map has 32 spots and 116 stock units per day over six days: the stock-only upper bound is 696. This loose bound neither proves 530 reachable nor excludes it. Routing, per-patrol visits and fuel tighten it.

With the fixed six patrols, each patrol can collect at most once per spot per
day in the inspected simulator. Capping each spot's stock at six tightens the
bound to `6 * sum(min(stock, 6)) = 678`, still above 530.

The [official final result PDF](https://www.procon.gr.jp/uploads/media/BfgqIvSwVAA)
was checked again: Tokyo 25/159/171, Akashi 25/156/172, Sendai-Hirose 25/148/163.
The official action-detail and rules download endpoints returned an unsupported
octet-stream content type through the browser tool; they still need local PDF
inspection before claiming a fresh complete rule audit.

Searches did not establish an attributable public algorithm for Tokyo, Akashi, Sendai, Hachinohe or Nagaoka, nor the reported six-solver system of `@define_LOCAL`. Do not assign repository ownership to a team from usernames. The arena labels itself unofficial; it must not be presented as an official reference implementation.

All modifications and build outputs are in `promax26-duc`. The Hieu checkout
is read-only. Its optimizer has also been copied to `src/optimizer.cpp` for
local next-day evaluation experiments; the other modules are linked as
read-only dependencies. This local experiment does not establish public
redistribution rights for upstream source.

## Rules checked in the local document extraction

`external/taiki288-test/tmp/pdfs/募集要項.txt`, spot and result sections,
states that a patrol collects at most one bowl from each spot each day; stock
is independent per team and replenishes daily. Vehicle position and patrol fuel
carry into the next day. Traffic uses the previous two days of occupancy.
The four ranking criteria are total distinct types, sum of daily distinct types,
total bowls, then lower sum of valid final-answer response times.
Vehicles may share cells; a universal collision-avoidance constraint would be
incorrect. Refueling requires sharing a cell for at least one step.
These observations agree with the inspected local simulator. A full independent
official-server conformance suite has not yet been completed.
