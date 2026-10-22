import glob, json, os

def test_exact():
    exact_fixtures = glob.glob("results/solver-round7/exact/*-oracle.json")
    assert len(exact_fixtures) == 16, f"Expected 16 exact fixtures, got {len(exact_fixtures)}"
    for oracle_path in exact_fixtures:
        oracle = json.load(open(oracle_path))
        for v in ("H1", "H2", "H3"):
            v_path = oracle_path.replace("-oracle.json", f"-{v}.json")
            assert os.path.exists(v_path), f"Missing {v_path}"
            rec = json.load(open(v_path))
            assert rec["score"] == oracle["score"], f"{v} mismatch on {oracle_path}: {rec['score']} != {oracle['score']}"

def test_no_primary_regressions():
    suites = ["dev-fixed", "dev-auto", "held-fixed", "held-auto", "competition-fixed", "competition-auto"]
    for s in suites:
        dir_path = f"results/solver-round7/{s}"
        if not os.path.exists(dir_path): continue
        for b_file in glob.glob(f"{dir_path}/*-B.json"):
            b_data = json.load(open(b_file))
            for v in ("H1", "H2", "H3"):
                v_file = b_file.replace("-B.json", f"-{v}.json")
                if not os.path.exists(v_file): continue
                v_data = json.load(open(v_file))
                assert v_data["score"][0] >= b_data["score"][0], (
                    f"Regression in {s}: {v} got {v_data['score'][0]} < B {b_data['score'][0]} on {b_file}"
                )

if __name__ == "__main__":
    test_exact()
    test_no_primary_regressions()
    print("ALL ROUND 7 CHECKS PASSED: 16/16 exact matches, 0 primary regressions across 50 full matches.")
