import glob, json, os, subprocess

EXPECTED_HASHES = {
    "/home/hexa/build-release/hexa_udon": "d864d3fd2f325773cbcd594dc93063b63882ca07fa5947365944fa0e8ec7b903",
    "/home/hexa/release/solver_B": "e94acb41818450fa5d50afd2ff4af4dec4f81b9cced565d4590dcae51540bae2",
    "/home/hexa/release/solver_H2": "4a3c75ba5ea4d0150275aa92ff5e01c3afab13bcf9d2f0c455f0fcf67ea8b61b",
    "/home/hexa/release/hexa_udon_B": "feaa67c74d8b3f21ebf3ee2797d4de765924cbeb97b8d2d1bf496aed727399d1",
    "/home/hexa/release/hexa_udon_H2": "6ac30c33292aa33234c84bea757376b7b30f8cf05432d8b91e3f332464331c04"
}

def test_binary_hashes():
    for path, expected in EXPECTED_HASHES.items():
        out = subprocess.check_output(["wsl", "-d", "HexaUdon", "sha256sum", path], text=True)
        actual = out.split()[0]
        assert actual == expected, f"Hash mismatch for {path}: {actual} != {expected}"

def test_exact_fixtures():
    exact_files = glob.glob("results/solver-round7/exact/*-oracle.json")
    assert len(exact_files) == 16, f"Expected 16 exact fixtures, found {len(exact_files)}"
    for f in exact_files:
        oracle = json.load(open(f))
        h2_f = f.replace("-oracle.json", "-H2.json")
        assert os.path.exists(h2_f), f"Missing H2 result for {f}"
        h2 = json.load(open(h2_f))
        assert h2["score"] == oracle["score"], f"H2 mismatch on {f}: {h2['score']} != {oracle['score']}"

def test_benchmarks_and_regressions():
    suites = ['dev-fixed', 'dev-auto', 'held-fixed', 'held-auto', 'competition-fixed', 'competition-auto']
    total_matches = 0
    h2_wins = 0
    primary_regs = 0
    for s in suites:
        dir_p = f"results/solver-round7/{s}"
        if not os.path.exists(dir_p): continue
        for b_f in sorted(glob.glob(f"{dir_p}/*-B.json")):
            prefix = b_f.removesuffix("-B.json")
            h2_f = f"{prefix}-H2.json"
            assert os.path.exists(h2_f), f"Missing H2 match {h2_f}"
            b = json.load(open(b_f))
            h2 = json.load(open(h2_f))
            total_matches += 1
            if tuple(h2["score"]) > tuple(b["score"]): h2_wins += 1
            if h2["score"][0] < b["score"][0]: primary_regs += 1
            assert h2["valid"] and b["valid"]
    assert total_matches == 50, f"Expected 50 matches, got {total_matches}"
    assert primary_regs == 0, f"Expected 0 primary regressions, got {primary_regs}"
    assert h2_wins == 22, f"Expected 22 H2 wins, got {h2_wins}"

if __name__ == "__main__":
    test_binary_hashes()
    test_exact_fixtures()
    test_benchmarks_and_regressions()
    print("ALL RELEASE CANDIDATE CHECKS PASSED: Full application binaries, benchmark binaries, hashes, exact fixtures, and 50/50 matches verified.")
