# Offline solver experiments (Linux / WSL)

This harness never connects to a competition server and does not replace the GUI binary.
It scores complete synthetic single-team matches using the existing simulator.

## Build and check

```sh
cmake -S tests/benchmark -B /tmp/hexa-bench -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/hexa-bench --target solver_bench solver_bench_checks --parallel 4
/tmp/hexa-bench/solver_bench_checks
python3 -B tests/benchmark/run.py --self-test
```

To build against a baseline snapshot, additionally set
`-DSOLVER_SOURCE_ROOT=/absolute/path/to/baseline` during configuration.
The app checks come from that source root, not from the candidate checkout.

## Run paired trials

```sh
taskset -c 0-7 python3 -B tests/benchmark/run.py   --binary /tmp/hexa-bench/solver_bench --output results/baseline-discovery   --map-seeds 29 --seeds 1 2 --day-ms 400 --threads 1
```

The output directory must not already exist. Use the same arguments and another output
path for each candidate binary. Default modes fix all-patrol and one-supply lineups.
Use `--modes auto --selection-ms 2500` to include vehicle selection. Do not mix these
with fixed-lineup results in a paired comparison.

```sh
python3 -B tests/benchmark/run.py --compare   results/baseline-discovery/results.jsonl results/candidate-discovery/results.jsonl
```

Use different map and search seeds for held-out validation (round 2 uses map 71,
search seeds 3 and 4). Full-match wall-clock search is not bit-reproducible even with
identical seeds. Repeat close results and unchanged-control cases.

## What the numbers mean

- Compare `(match brands, cumulative daily brands, bowls)` lexicographically.
- The real rules also use submission time as a later tiebreak; this offline harness
  does not measure it. Component means are descriptive, not a scalar official score.
- `day-ms` is the local day allowance; search receives 85% like the application.
- Local deadline rate includes unfinished days as failures. It is not HTTP deadline success.
- Peak RSS is the Linux child-process high-water mark, not the GUI/service memory usage.
- Logged iterations include skipped/no-op moves and, with multiple threads, only the
  worker(s) that log. They are not unique states or total multithread search throughput.
- Metadata includes binary/harness hashes and CPU affinity. Raw fixtures and their hashes,
  stdout records and stderr logs are retained. Save the source patch next to experiment data.
- The fixtures contain plain/road/mountain terrain, not ponds or other teams. Simulator
  validity is not an independent check against a live HAUI implementation.
- Results/patches live under ignored `results/solver-optimization/`; production source is
  restored between independent pilots. No result alone authorizes deployment or a commit.
