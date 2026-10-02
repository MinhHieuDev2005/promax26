# Historical H08 checkpoint: 13/91/225

`bin/chokudai_v2_h08_runner.exe` produced the replayable
`evidence/h08-v2h08-60000-1.json` result (C1=13, C2=91, C3=225), improving
the earlier 223 baseline. It is retained as the historical binary for testing.

The current `solvers/chokudai_v2/search.cpp` was modified **after** this binary
and checkpoint were built. No exact source snapshot from the H08 build time
exists here, so this folder intentionally does not claim to contain matching
C++ source. Do not rebuild the current v2 source and call it H08 without
revalidating the result.
