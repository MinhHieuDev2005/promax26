#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAUI Procon 2026 - Showdown: D:\hex (ALNS / MLNS) VS D:\Procon26 (Sample Solver)
So sánh trực tiếp hiệu năng giữa:
- Solver D:\hex (Thuật toán ALNS / MLNS tối ưu bậc cao)
- Solver D:\Procon26 (Solver Greedy & Role Evaluator mặc định)
"""

import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.request
import http.cookiejar
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

ROOT_HEX = Path(__file__).resolve().parent

if (ROOT_HEX / "bin" / "hexudon.exe").exists():
    HEX_BINARY = ROOT_HEX / "bin" / "hexudon.exe"
else:
    HEX_BINARY = ROOT_HEX / "build" / "hexudon.exe"

if (ROOT_HEX / "bin" / "hexudon_runner.exe").exists():
    PROCON26_RUNNER = ROOT_HEX / "bin" / "hexudon_runner.exe"
    ROOT_PROCON26 = ROOT_HEX
elif Path("D:/Procon26/out/build/haui-practice-release/hexudon_runner.exe").exists():
    PROCON26_RUNNER = Path("D:/Procon26/out/build/haui-practice-release/hexudon_runner.exe")
    ROOT_PROCON26 = Path("D:/Procon26").resolve()
else:
    PROCON26_RUNNER = ROOT_HEX / "bin" / "hexudon_runner.exe"
    ROOT_PROCON26 = ROOT_HEX

DEFAULT_HOST = "procon26.haui.ac.vn"
DEFAULT_USER = "mhieu"
DEFAULT_PASS = "Hieu123456@"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


class HauiClient:
    def __init__(self, host=DEFAULT_HOST):
        self.host = host
        self.base_url = f"https://{host}"
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ctx)
        )

    def login(self, username, password):
        url = f"{self.base_url}/api/auth/login"
        payload = json.dumps({"username": username, "password": password}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "hexudon-client/1.0"})
        with self.opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_match(self, match_id):
        url = f"{self.base_url}/api/admin/matches/{match_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "hexudon-client/1.0"})
        with self.opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def create_match(self, name, map_config):
        url = f"{self.base_url}/api/admin/matches"
        payload = json.dumps({"name": name, "mapConfig": map_config}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json", "User-Agent": "hexudon-client/1.0"})
        with self.opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def add_team(self, match_id, team_id):
        url = f"{self.base_url}/api/admin/matches/{match_id}/teams"
        payload = json.dumps({"teamId": team_id}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json", "User-Agent": "hexudon-client/1.0"})
        with self.opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def match_action(self, match_id, action):
        url = f"{self.base_url}/api/admin/matches/{match_id}"
        payload = json.dumps({"action": action}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="PUT", headers={"Content-Type": "application/json", "User-Agent": "hexudon-client/1.0"})
        with self.opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_teams(self):
        url = f"{self.base_url}/api/admin/teams"
        req = urllib.request.Request(url, headers={"User-Agent": "hexudon-client/1.0"})
        with self.opener.open(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8")).get("teams", [])

    def submit_roles(self, match_id, token, roles):
        url = f"{self.base_url}/api/game/matches/{match_id}/agents"
        payload = json.dumps(roles).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "x-api-token": token, "User-Agent": "hexudon-client/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_game_status(self, match_id, token):
        url = f"{self.base_url}/api/game/matches/{match_id}/status"
        req = urllib.request.Request(url, headers={"x-api-token": token, "User-Agent": "hexudon-client/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def submit_actions(self, match_id, token, actions):
        url = f"{self.base_url}/api/game/matches/{match_id}/answer"
        payload = json.dumps(actions).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "x-api-token": token, "User-Agent": "hexudon-client/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))


# --- SOLVER 1: D:\hex (ALNS / MLNS) ---
def run_hex_solver(command, policy, payload, timeout=60):
    cmd = [str(HEX_BINARY), command, policy]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
        cwd=ROOT_HEX
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Hex solver {policy} failed ({proc.returncode}): {proc.stderr.strip()}")
    return json.loads(proc.stdout)


# --- SOLVER 2: D:\Procon26 (Runner) ---
def run_procon26_roles(map_config):
    payload = {"op": "roles", "config": map_config}
    proc = subprocess.run(
        [str(PROCON26_RUNNER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=30,
        cwd=ROOT_PROCON26
    )
    res = json.loads(proc.stdout)
    if not res.get("ok"):
        raise RuntimeError(f"Procon26 roles error: {res.get('error')}")
    return res["roles"]


def run_procon26_plan(map_config, raw_status, roles, day_num=1):
    W = map_config['map']['width']
    H = map_config['map']['height']
    cells = map_config['map']['cells']
    road_cells = [y * W + x for y in range(H) for x in range(W) if cells[y][x] == 1]
    
    traffic_map = {t['pos']: t['status'] for t in raw_status.get('traffics', [])}
    traffics = [{'pos': pos, 'status': traffic_map.get(pos, 0)} for pos in road_cells]
    
    agents = []
    raw_agents = raw_status.get('agents', [])
    for i in range(len(map_config['agents'])):
        if i < len(raw_agents):
            kind = roles[i] if raw_agents[i].get('kind') is None else raw_agents[i].get('kind')
            pos = raw_agents[i].get('pos', map_config['agents'][i])
            fuel = map_config['fuelLimits'] if raw_agents[i].get('fuel') is None else raw_agents[i].get('fuel')
        else:
            kind = roles[i]
            pos = map_config['agents'][i]
            fuel = map_config['fuelLimits']
        agents.append({'kind': kind, 'pos': pos, 'fuel': fuel})
        
    state = {
        'day': day_num,
        'startsAt': raw_status.get('startsAt', int(time.time())),
        'endsAt': raw_status.get('endsAt', int(time.time()) + 60),
        'stepsCount': raw_status.get('stepsCount', 44),
        'agents': agents,
        'others': raw_status.get('others', []),
        'traffics': traffics
    }
    
    payload = {
        'op': 'plan',
        'config': map_config,
        'state': state,
        'stock': [s['stocks'] for s in map_config.get('spots', [])]
    }
    
    proc = subprocess.run(
        [str(PROCON26_RUNNER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=30,
        cwd=ROOT_PROCON26
    )
    res = json.loads(proc.stdout)
    if not res.get("ok"):
        raise RuntimeError(f"Procon26 plan error: {res.get('error')}")
    return res["plan"]


def play_showdown(hex_policy="alns"):
    client = HauiClient()
    client.login(DEFAULT_USER, DEFAULT_PASS)
    teams = client.get_teams()

    HEX_TEAMS = {
        "alns": "Team-ALNS",
        "mlns": "Team-MLNS",
        "aco_ls": "Team-ACO",
        "local_search": "Team-LocalSearch",
        "greedy": "Team-Greedy",
    }

    team_hex_name = HEX_TEAMS.get(hex_policy, "Team-ALNS")
    team_hex = next((t for t in teams if t["name"] == team_hex_name), None)
    team_procon = next((t for t in teams if t["name"] == "Procon26-Bot"), None)

    if not team_hex:
        raise ValueError(f"Không tìm thấy đội {team_hex_name}")
    if not team_procon:
        raise ValueError(f"Không tìm thấy đội Procon26-Bot")

    print("\n" + "=" * 80)
    print(f"⚔️⚔️⚔️ SO TÀI: {team_hex['name']} (d:\\hex - {hex_policy.upper()})  VS  Procon26-Bot (D:\\Procon26) ⚔️⚔️⚔️")
    print("=" * 80)

    with open(ROOT_HEX / "map_22x22.json", "r", encoding="utf-8") as f:
        map_config = json.load(f)

    map_config["players"] = 2
    map_config["startsAt"] = int(time.time()) + 90
    map_config["daySeconds"] = [60, 60, 60, 60]

    match_name = f"Hex-{hex_policy.upper()}-vs-Procon26-{int(time.time())}"
    new_match = client.create_match(match_name, map_config)
    match_id = new_match["match"]["id"]
    match_url = f"https://procon26.haui.ac.vn/matches/{match_id}"
    print(f"[+] Trận đấu đã tạo: {match_url}")

    client.add_team(match_id, team_hex["id"])
    client.add_team(match_id, team_procon["id"])
    client.match_action(match_id, "start_agent_select")
    print(f"[+] Đã thêm cả 2 đội vào trận và mở chọn vai trò xe!")

    # BƯỚC 1: Chọn vai trò xe
    try:
        roles_hex = run_hex_solver("types", hex_policy, {"config": map_config})
    except Exception as e:
        print(f"[!] Hex types lỗi ({e}), fallback sang greedy...")
        roles_hex = run_hex_solver("types", "greedy", {"config": map_config})
    print(f"[{team_hex['name']} - d:\\hex]: Chọn vai trò: {roles_hex}")
    client.submit_roles(match_id, team_hex["token"], roles_hex)

    roles_procon = run_procon26_roles(map_config)
    print(f"[Procon26-Bot - D:\\Procon26]: Chọn vai trò: {roles_procon}")
    client.submit_roles(match_id, team_procon["token"], roles_procon)

    client.match_action(match_id, "start")

    # BƯỚC 2: Thi đấu từng ngày
    total_days = len(map_config.get("daySteps", []))
    for day_num in range(1, total_days + 1):
        day_idx = day_num - 1
        steps = map_config["daySteps"][day_idx]
        print(f"   >>> Ngày {day_num}/{total_days} (Số bước: {steps})")

        # Đợi đồng bộ trạng thái
        st_hex, st_procon = None, None
        for _ in range(25):
            try:
                s1 = client.get_game_status(match_id, team_hex["token"])
                s2 = client.get_game_status(match_id, team_procon["token"])
                if s1.get("currentDay") == day_num and s2.get("currentDay") == day_num:
                    st_hex, st_procon = s1, s2
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not st_hex:
            st_hex = client.get_game_status(match_id, team_hex["token"])
        if not st_procon:
            st_procon = client.get_game_status(match_id, team_procon["token"])

        traffics = st_hex.get("traffics", [])

        # 1. Đội d:\hex tính toán và nộp
        built_hex_agents = []
        raw_hex = st_hex.get("agents", [])
        for i in range(len(map_config["agents"])):
            if i < len(raw_hex):
                kind = roles_hex[i] if raw_hex[i].get("kind") is None else raw_hex[i].get("kind")
                pos = raw_hex[i].get("pos", map_config["agents"][i])
                fuel = map_config["fuelLimits"] if raw_hex[i].get("fuel") is None else raw_hex[i].get("fuel")
            else:
                kind = roles_hex[i]
                pos = map_config["agents"][i]
                fuel = map_config["fuelLimits"]
            built_hex_agents.append({"kind": kind, "pos": pos, "fuel": fuel})

        day_info_hex = {
            "day": day_idx,
            "steps": steps,
            "agents": built_hex_agents,
            "traffics": [{"pos": item["pos"], "status": item["status"]} for item in traffics]
        }
        t0 = time.time()
        try:
            plan_hex = run_hex_solver("plan", hex_policy, {"config": map_config, "day_info": day_info_hex, "types": roles_hex, "search": {"time_limit_ms": 5000}})
        except Exception as e:
            print(f"       [!] Hex {hex_policy} lỗi ({e}), fallback sang greedy...")
            plan_hex = run_hex_solver("plan", "greedy", {"config": map_config, "day_info": day_info_hex, "types": roles_hex, "search": {"time_limit_ms": 1000}})
        t_hex = time.time() - t0
        client.submit_actions(match_id, team_hex["token"], plan_hex)

        # 2. Đội D:\Procon26 tính toán và nộp
        t0 = time.time()
        plan_procon = run_procon26_plan(map_config, st_procon, roles_procon, day_num=day_num)
        t_procon = time.time() - t0
        client.submit_actions(match_id, team_procon["token"], plan_procon)
        print(f"       [+] Nộp bài: {team_hex['name']} ({t_hex:.2f}s) | Procon26-Bot ({t_procon:.2f}s)")

        # Chuyển ngày
        if day_num < total_days:
            time.sleep(0.5)
            try:
                client.match_action(match_id, "next_day")
            except Exception:
                pass

    # BƯỚC 3: Tổng kết tỉ số
    time.sleep(1.5)
    final_match = client.get_match(match_id)
    teams_res = final_match.get("teams", [])

    hex_stat = next((t for t in teams_res if t.get("team_id") == team_hex["id"]), {})
    procon_stat = next((t for t in teams_res if t.get("team_id") == team_procon["id"]), {})

    s_hex = hex_stat.get("total_udon_servings", 0)
    t_hex_types = hex_stat.get("total_udon_types", 0)
    d_hex = hex_stat.get("total_udon_daily_types", 0)
    time_hex = hex_stat.get("total_response_time_ms", 0)

    s_procon = procon_stat.get("total_udon_servings", 0)
    t_procon_types = procon_stat.get("total_udon_types", 0)
    d_procon = procon_stat.get("total_udon_daily_types", 0)
    time_procon = procon_stat.get("total_response_time_ms", 0)

    if s_hex > s_procon:
        winner = f"{team_hex['name']} THẮNG"
    elif s_hex < s_procon:
        winner = "Procon26-Bot THẮNG"
    else:
        winner = "HÒA NHAU"

    print(f"[+] KẾT QUẢ: {team_hex['name']} ({s_hex} bát) vs Procon26-Bot ({s_procon} bát) -> {winner}!")
    print(f"    Replay: {match_url}")

    return {
        "policy": hex_policy,
        "hex_team": team_hex_name,
        "match_url": match_url,
        "hex_servings": s_hex,
        "hex_types": t_hex_types,
        "hex_daily": d_hex,
        "hex_time": time_hex,
        "procon_servings": s_procon,
        "procon_types": t_procon_types,
        "procon_daily": d_procon,
        "procon_time": time_procon,
        "winner": winner
    }


def run_all_comparisons():
    policies = ["alns", "mlns", "aco_ls", "local_search", "greedy"]
    results = []

    print("=" * 85)
    print("🔥 BẮT ĐẦU CHUỖI 5 TRẬN SO GĂNG TOÀN DIỆN: D:\\Procon26 VS MỌI SOLVER D:\\hex 🔥")
    print("=" * 85)

    for p in policies:
        try:
            res = play_showdown(hex_policy=p)
            results.append(res)
            time.sleep(1.0)
        except Exception as e:
            print(f"[!] Lỗi trận {p}: {e}")

    print("\n" + "=" * 95)
    print("🏆 BẢNG TỔNG KẾT TOÀN DIỆN: D:\\Procon26  VS  CÁC SOLVER THƯ MỤC d:\\hex")
    print("=" * 95)
    title_hex = "Solver d:\\hex"
    header = f"{title_hex:<18} | {'Tỉ số Bát Mì (Hex vs Procon)':<30} | {'Thời gian giải (ms)':<22} | {'Kết quả':<20}"
    print(header)
    print("-" * 95)
    for r in results:
        score_str = f"{r['hex_team']}: {r['hex_servings']} vs Procon: {r['procon_servings']}"
        time_str = f"{r['hex_time']}ms vs {r['procon_time']}ms"
        print(f"{r['hex_team']:<18} | {score_str:<30} | {time_str:<22} | {r['winner']:<20}")
    print("=" * 95)
    print("\nChi tiết các trận đấu:")
    for r in results:
        print(f" - {r['hex_team']} vs Procon26-Bot: {r['match_url']}")
    print("=" * 95)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Showdown D:\\hex vs D:\\Procon26")
    parser.add_argument("--policy", default=None, choices=["alns", "mlns", "aco_ls", "local_search", "greedy"], help="Hex policy cụ thể")
    parser.add_argument("--all", action="store_true", help="Chạy so sánh đối kháng với toàn bộ 5 solver của d:\\hex")
    args = parser.parse_args()

    if args.all or args.policy is None:
        run_all_comparisons()
    else:
        play_showdown(hex_policy=args.policy)
