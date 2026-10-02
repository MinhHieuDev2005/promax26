import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("bench", Path(__file__).with_name("benchmark.py"))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class BenchmarkTests(unittest.TestCase):
    def test_absent_metrics_are_unknown(self):
        value = bench.metrics({})
        self.assertIsNone(value["tt_hit_rate"])
        self.assertIsNone(value["expanded"])

    def test_rates(self):
        value = bench.metrics({"expanded": 50, "elapsed_ms": 10, "tt_hits": 5, "tt_lookups": 20})
        self.assertEqual(value["expansions_per_ms"], 5)
        self.assertEqual(value["tt_hit_rate"], .25)

    def test_case_config_and_roles(self):
        p = bench.initial_state(bench.ROOT / "cases/user-input-25x25.json", "1,0,0,0")
        self.assertEqual(p["day_info"]["day"], 0)
        self.assertEqual(p["types"], [1, 0, 0, 0])
        self.assertEqual(p["config"]["daySteps"], [126, 110, 130, 63, 97, 66, 131])
        with self.assertRaises(ValueError):
            bench.initial_state(bench.ROOT / "cases/user-input-25x25.json", "1,0")

    def test_summary_keeps_maps_separate(self):
        rows = [{"case_path": path, "verified": True, "deadline_pass": True, "full_coverage": True,
                 "days": [{"servings": n}]} for path, n in [("a", 20), ("a", 22), ("b", 100)]]
        summary = bench.summarize(rows)
        self.assertEqual(summary["a"]["mean"], 21)
        self.assertEqual(summary["a"]["stddev"], 1)
        self.assertEqual(summary["b"]["mean"], 100)


if __name__ == "__main__":
    unittest.main()
