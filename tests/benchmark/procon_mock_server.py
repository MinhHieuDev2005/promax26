import argparse, json, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

DX_EVEN = [0, 1, 1, 1, 0, -1]
DX_ODD  = [-1, 0, 1, 0, -1, -1]
DY      = [-1, -1, 0, 1, 1, 0]

# ponytail: simple single-fixture mock server for full match validation; add multi-match table before supporting HAUI tournament pool.
class ProconMockServer:
    def __init__(self, fixture_path, kind_delay_sec=1, day_sec=5, artificial_delay_ms=0):
        with open(fixture_path, 'r', encoding='utf-8') as f:
            self.fixture = json.load(f)
        self.H = self.fixture['map']['height']
        self.W = self.fixture['map']['width']
        self.NC = self.H * self.W
        self.cells = [cell for row in self.fixture['map']['cells'] for cell in row]
        self.spots = self.fixture['spots']
        self.spot_at = [-1] * self.NC
        for idx, sp in enumerate(self.spots):
            self.spot_at[sp['pos']] = idx
        self.fuel_limit = self.fixture['fuelLimits']
        if self.fixture['players'] != 1:
            raise ValueError('Opponent arbitration is not verified')
        self.total_days = len(self.fixture['daySteps'])
        self.fixture['daySeconds'] = [day_sec] * self.total_days
        self.kind_delay_sec = kind_delay_sec
        self.day_sec = day_sec
        self.artificial_delay_sec = artificial_delay_ms / 1000.0

        self.lock = threading.Lock()
        self.token = 'procon-secret-token'
        self.starts_at = 0
        self.current_day = 0
        self.current_ends_at = 0
        self.submitted_kinds = None
        self.day_plans = {}
        self.day_revisions = {}
        self.stays = []
        self.agents = []
        self.match_started = False
        self.match_completed = False
        self.history = []
        self.acquired_brands = set()
        self.total_balls = 0
        self.daily_distinct_brand_counts = []
        self.request_log = []

    def neighbor(self, p, d):
        x, y = p % self.W, p // self.W
        nx = x + (DX_EVEN[d] if y % 2 == 0 else DX_ODD[d])
        ny = y + DY[d]
        if 0 <= nx < self.W and 0 <= ny < self.H and self.cells[ny * self.W + nx] != 3:
            return ny * self.W + nx
        return -1

    def step_cost(self, p, status):
        t = self.cells[p]
        if t == 0: return 2
        if t == 2: return 3
        if t == 1:
            s = status[p]
            return 1 if s == 0 else (2 if s == 1 else 4)
        return 1000000

    def fuel_cost(self, p):
        return 1 if self.cells[p] == 0 else 2

    def current_traffic_status(self):
        tot = [0] * self.NC
        for prev in range(max(0, self.current_day - 2), self.current_day):
            for c in range(self.NC):
                tot[c] += self.stays[prev][c]
        busy = self.fixture['busyThreshold']
        jam = self.fixture['jammedThreshold']
        return [0 if self.cells[c] != 1 or tot[c] < busy else (1 if tot[c] < jam else 2) for c in range(self.NC)]

    def simulate_day(self, agents, plan, status, steps):
        n = len(agents)
        a = [dict(ag) for ag in agents]
        ptr, done_at, target, fcost = [0] * n, [10**9] * n, [-1] * n, [0] * n
        got = [[0] * len(self.spots) for _ in range(n)]
        stay = [0] * self.NC
        brand_hit = [0] * (max(sp['brand'] for sp in self.spots) + 1)
        balls = 0
        stock = [sp['stocks'] for sp in self.spots]

        def start_action(i, t):
            if ptr[i] >= len(plan[i]):
                done_at[i] = 10**9; target[i] = -1; return
            x = plan[i][ptr[i]]
            ptr[i] += 1
            if x < 0:
                done_at[i] = t - x; target[i] = -1
            else:
                target[i] = self.neighbor(a[i]['pos'], x)
                if target[i] < 0: raise ValueError('Impassable movement')
                fcost[i] = self.fuel_cost(a[i]['pos'])
                done_at[i] = t + self.step_cost(a[i]['pos'], status)

        for i in range(n): start_action(i, 0)
        for t in range(1, steps + 1):
            for i in range(n):
                if done_at[i] == t and target[i] >= 0 and a[i]['kind'] == 0:
                    if a[i]['fuel'] < fcost[i]: raise ValueError('Insufficient fuel')
                    a[i]['fuel'] -= fcost[i]
            for i in range(n):
                if done_at[i] == t and target[i] >= 0:
                    a[i]['pos'] = target[i]
            for i in range(n):
                if a[i]['kind'] != 0: continue
                s = self.spot_at[a[i]['pos']]
                if s >= 0 and not got[i][s] and stock[s] > 0:
                    got[i][s] = 1; stock[s] -= 1; balls += 1
                    brand_hit[self.spots[s]['brand']] = 1
            for i in range(n):
                if a[i]['kind'] != 0: continue
                for j in range(n):
                    if a[j]['kind'] == 1 and a[j]['pos'] == a[i]['pos']:
                        a[i]['fuel'] = self.fuel_limit
                        break
            for i in range(n):
                if self.cells[a[i]['pos']] == 1:
                    stay[a[i]['pos']] += 1
            if t < steps:
                for i in range(n):
                    if done_at[i] == t: start_action(i, t)
        self.last_stock = stock
        return a, stay, brand_hit, balls

    def step_day_if_needed(self):
        now = time.time()
        if not self.match_started or self.match_completed:
            return
        while self.current_day < self.total_days and now >= self.current_ends_at:
            # Advance day
            steps = self.fixture['daySteps'][self.current_day]
            plan = self.day_plans.get(self.current_day, [[-steps] for agent in self.agents])
            status = self.current_traffic_status()
            end_agents, stay, hits, balls = self.simulate_day(self.agents, plan, status, steps)
            self.stays.append(stay)
            self.agents = end_agents
            distinct_brands = set()
            for b_idx, hit in enumerate(hits):
                if hit:
                    distinct_brands.add(b_idx)
                    self.acquired_brands.add(b_idx)
            self.total_balls += balls
            self.daily_distinct_brand_counts.append(len(distinct_brands))
            self.history.append({'day': self.current_day, 'hits': hits, 'balls': balls,
                                 'agents': [dict(ag) for ag in end_agents], 'traffic': status, 'plan': plan, 'stay': stay, 'stock': self.last_stock, 'revision': self.day_revisions.get(self.current_day, 0)})
            self.current_day += 1
            if self.current_day >= self.total_days:
                self.match_completed = True
            else:
                self.current_ends_at += self.day_sec

    def handle_get_setting(self):
        with self.lock:
            now = int(time.time())
            if not self.starts_at: self.starts_at = now + self.kind_delay_sec
            resp = dict(self.fixture)
            resp['startsAt'] = self.starts_at
            return 200, resp

    def handle_post_agent(self, data):
        with self.lock:
            if (not isinstance(data, list) or len(data) != len(self.fixture['agents'])
                    or any(type(kind) is not int or kind not in (0, 1) for kind in data)):
                return 400, {'error': 'Invalid lineup'}
            if time.time() >= self.starts_at or self.submitted_kinds is not None:
                return 403, {'error': 'Registration closed'}
            self.submitted_kinds = data
            self.agents = [{'kind': k, 'pos': self.fixture['agents'][i], 'fuel': self.fuel_limit} for i, k in enumerate(data)]
            now = time.time()
            start_time = self.starts_at
            self.current_ends_at = int(start_time) + self.day_sec
            self.match_started = True
            return 200, {'status': 'ok'}

    def handle_get_state(self):
        with self.lock:
            self.step_day_if_needed()
            if not self.match_started or time.time() < self.starts_at or self.match_completed:
                return 403, {'error': 'State unavailable'}
            day_idx = self.current_day
            traffics = [{'pos': c, 'status': s} for c, s in enumerate(self.current_traffic_status()) if self.cells[c] == 1]
            return 200, {
                'day': day_idx,
                'endsAt': self.current_ends_at,
                'agents': self.agents,
                'others': [],
                'traffics': traffics
            }

    def handle_post_actions(self, data):
        with self.lock:
            if (not self.match_started or self.match_completed or time.time() < self.starts_at
                    or time.time() >= self.current_ends_at):
                return 403, {'error': 'Submission window closed'}
            try:
                self.validate_plan(data)
            except ValueError as error:
                return 200, {'revision': -1, 'valid': False, 'error': str(error)}
            if time.time() >= self.current_ends_at:
                return 403, {'error': 'Validation exceeded deadline'}
            rev = self.day_revisions.get(self.current_day, 0) + 1
            self.day_revisions[self.current_day] = rev
            self.day_plans[self.current_day] = data
            return 200, {'revision': rev, 'valid': True}


    def validate_plan(self, plan):
        if not isinstance(plan, list) or len(plan) != len(self.agents):
            raise ValueError('Action count mismatch')
        status = self.current_traffic_status()
        steps = self.fixture['daySteps'][self.current_day]
        for agent, row in zip(self.agents, plan):
            if not isinstance(row, list) or not row or len(row) > steps:
                raise ValueError('Invalid action row')
            position, elapsed = agent['pos'], 0
            for action in row:
                if type(action) is not int or action < -2147483647 or action > 5:
                    raise ValueError('Invalid action value')
                if action < 0:
                    elapsed -= action
                else:
                    elapsed += self.step_cost(position, status)
                    position = self.neighbor(position, action)
                    if position < 0:
                        raise ValueError('Impassable movement')
            if elapsed != steps:
                raise ValueError('Step budget mismatch')
        return self.simulate_day(self.agents, plan, status, steps)

class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def dispatch(self):
        app = self.server.app
        receipt = time.time_ns()
        receipt_monotonic = time.monotonic_ns()
        parsed = urlsplit(self.path)
        path = parsed.path
        payload = None
        with app.lock:
            day = app.current_day
            deadline = app.current_ends_at
        time.sleep(app.artificial_delay_sec)
        try:
            if parse_qs(parsed.query).get('token') != [app.token]:
                status, body = 401, {'error': 'Unauthorized'}
            elif self.command == 'GET':
                status, body = (app.handle_get_setting() if path == '/setting' else
                                app.handle_get_state() if path == '/' else (404, {}))
            else:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1048576:
                    raise ValueError('Invalid body length')
                payload = json.loads(self.rfile.read(length))
                status, body = (app.handle_post_agent(payload) if path == '/agent' else
                                app.handle_post_actions(payload) if path == '/' else (404, {}))
        except (ValueError, UnicodeError, TypeError) as error:
            status, body = 400, {'error': str(error)}
        validated = time.time_ns()
        data = json.dumps(body).encode('utf-8')
        delivered = True
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            delivered = False
        completed = time.time_ns()
        completed_monotonic = time.monotonic_ns()
        with app.lock:
            app.request_log.append(dict(method=self.command, path=path, status=status,
                receipt_ns=receipt, validation_ns=validated, response_ns=completed,
                elapsed_ms=(completed_monotonic-receipt_monotonic)/1e6,
                receipt_monotonic_ns=receipt_monotonic, deadline=deadline, day=day,
                request=payload, response=body, delivered=delivered))

def run_mock_server(port, fixture_path, kind_delay_sec=1, day_sec=5, artificial_delay_ms=0):
    app = ProconMockServer(fixture_path, kind_delay_sec, day_sec, artificial_delay_ms)
    server = ThreadingHTTPServer(('127.0.0.1', port), MockHandler)
    server.app = app
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, app

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18080)
    parser.add_argument('--fixture', type=str, default='results/solver-round7/dev-fixed/bridge-12100-s201.fixture.json')
    parser.add_argument('--day-sec', type=int, default=5)
    parser.add_argument('--kind-sec', type=int, default=1)
    parser.add_argument('--delay-ms', type=int, default=0)
    args = parser.parse_args()
    server, app = run_mock_server(args.port, args.fixture, args.kind_sec, args.day_sec, args.delay_ms)
    print(f'Mock server running on port {args.port}...')
    try:
        while True:
            time.sleep(1)
            with app.lock:
                app.step_day_if_needed()
                if app.match_completed:
                    print('Match completed. Final score:', len(app.acquired_brands), sum(app.daily_distinct_brand_counts), app.total_balls)
                    break
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
