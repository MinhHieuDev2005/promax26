"""Check subset-DP relaxation against independent permutation enumeration."""
import heapq
import itertools
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class AuditTests(unittest.TestCase):
    def test_subset_dp_matches_all_orders(self):
        cells = [[0, 1, 0, 0], [0, 2, 0, 1], [1, 0, 3, 0], [0, 0, 0, 0]]
        positions = [0, 3, 9, 15]
        config = dict(startsAt=0, daySeconds=[45], daySteps=[20],
                      map=dict(width=4, height=4, cells=cells),
                      spots=[dict(pos=p, brand=i, stocks=2) for i, p in enumerate(positions)],
                      agents=[2, 14], fuelLimits=30, players=1,
                      busyThreshold=4, jammedThreshold=10)
        result = subprocess.run([str(ROOT / 'build/horizon_portfolio/reachability_audit.exe')],
                                input=json.dumps(config), text=True, capture_output=True, check=True)
        actual = json.loads(result.stdout)
        for fuel in (False, True):
            distances = {}
            for start in positions:
                dist = [10**8] * 16
                dist[start] = 0
                todo = [(0, start)]
                while todo:
                    cost, p = heapq.heappop(todo)
                    if dist[p] != cost:
                        continue
                    r, c = divmod(p, 4)
                    offsets = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (0, -1)] if r % 2 == 0 else [(-1, -1), (-1, 0), (0, 1), (1, 0), (1, -1), (0, -1)]
                    weight = (1 if cells[r][c] == 0 else 2) if fuel else [2, 1, 3, 10**8][cells[r][c]]
                    for dr, dc in offsets:
                        nr, nc = r + dr, c + dc
                        if not (0 <= nr < 4 and 0 <= nc < 4) or cells[nr][nc] == 3:
                            continue
                        q = nr * 4 + nc
                        if cost + weight < dist[q]:
                            dist[q] = cost + weight
                            heapq.heappush(todo, (dist[q], q))
                distances[start] = dist
            expected = [0]
            for count in range(1, 5):
                expected.append(min(sum(distances[a][b] for a, b in zip(order, order[1:]))
                                    for order in itertools.permutations(positions, count)))
            self.assertEqual(expected, actual['fuel_min_by_visits' if fuel else 'time_min_by_visits'])


if __name__ == '__main__':
    unittest.main()
