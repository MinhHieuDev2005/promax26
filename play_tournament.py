#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAUI Procon 2026 - Mega Battle Royale Tournament (Đại Chiến 5 Thuật Toán)
Thi đấu đối kháng đồng thời 5 thuật toán đỉnh cao trên cùng một bàn cờ:
1. Team-ALNS         (Adaptive Large Neighborhood Search)
2. Team-MLNS         (Multi-Day LNS with DP Lookahead)
3. Team-ACO          (Ant Colony Optimization + Local Search)
4. Team-LocalSearch  (Relocate / Swap / 2-Opt)
5. Team-Greedy       (Classic Greedy Heuristic)
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

ROOT = Path(__file__).resolve().parent
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


def run_solver(binary, command, policy, payload, timeout=60):
    cmd = [str(binary), command, policy]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=timeout,
        cwd=ROOT
    )
    if proc.returncode != 0:
        debug_path = ROOT / f"debug_{command}_{policy}_fail.json"
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        raise RuntimeError(f"Solver {policy} failed ({proc.returncode}). Stderr: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def play_grand_tournament(map_config_file=None):
    binary = ROOT / "build" / "hexudon.exe"
    if not binary.is_file():
        raise FileNotFoundError(f"Solver binary not found at {binary}")

    client = HauiClient()
    client.login(DEFAULT_USER, DEFAULT_PASS)
    teams_all = client.get_teams()

    # 5 đội đại diện cho 5 thuật toán
    competing_configs = [
        {"name": "Team-ALNS", "policy": "alns", "desc": "Adaptive LNS (Production)"},
        {"name": "Team-MLNS", "policy": "mlns", "desc": "Multi-Day LNS + DP Lookahead"},
        {"name": "Team-ACO", "policy": "aco_ls", "desc": "Ant Colony Optimization + LS"},
        {"name": "Team-LocalSearch", "policy": "local_search", "desc": "2-Opt / Relocate / Swap"},
        {"name": "Team-Greedy", "policy": "greedy", "desc": "Classic Greedy Heuristic"},
    ]

    competitors = []
    for cfg in competing_configs:
        t_obj = next((t for t in teams_all if t["name"].strip().lower() == cfg["name"].strip().lower()), None)
        if not t_obj:
            raise ValueError(f"Không tìm thấy đội '{cfg['name']}' trên server HAUI.")
        competitors.append({
            "name": cfg["name"],
            "policy": cfg["policy"],
            "desc": cfg["desc"],
            "id": t_obj["id"],
            "token": t_obj["token"],
            "roles": None
        })

    print("=" * 80)
    print("🏆🏆🏆 ĐẠI CHIẾN BATTLE ROYALE - 5 SIÊU THUẬT TOÁN PROCON 2026 🏆🏆🏆")
    print("=" * 80)
    for i, c in enumerate(competitors, 1):
        print(f" {i}. {c['name']:<18} | Policy: {c['policy'].upper():<14} | {c['desc']}")
    print("=" * 80)

    # Đọc bản đồ
    if map_config_file and os.path.isfile(map_config_file):
        with open(map_config_file, "r", encoding="utf-8") as f:
            map_config = json.load(f)
    else:
        with open(ROOT / "map_22x22.json", "r", encoding="utf-8") as f:
            map_config = json.load(f)

    num_players = len(competitors)
    map_config["players"] = num_players
    map_config["startsAt"] = int(time.time()) + 90
    map_config["daySeconds"] = [60, 60, 60, 60]

    match_name = f"BattleRoyale-5Solvers-{int(time.time())}"
    print(f"\n[*] Đang tạo trận đấu đấu trường 5 đội: '{match_name}'...")
    new_match = client.create_match(match_name, map_config)
    match_id = new_match["match"]["id"]
    match_url = f"https://procon26.haui.ac.vn/matches/{match_id}"
    print(f"[+] Trận đấu đã tạo: {match_url}")

    for c in competitors:
        client.add_team(match_id, c["id"])
        print(f"   + Đã thêm {c['name']} vào trận")

    client.match_action(match_id, "start_agent_select")
    print(f"[+] Đã bật chế độ 'start_agent_select' cho cả 5 đội!\n")

    # BƯỚC 1: Cả 5 đội chọn vai trò xe
    print("--- BƯỚC 1: Cả 5 đội tính toán & nộp vai trò xe ---")
    types_payload = {"config": map_config}
    for c in competitors:
        try:
            roles = run_solver(binary, "types", c["policy"], types_payload)
        except Exception as e:
            print(f"[!] {c['name']} lỗi types ({e}), fallback sang greedy...")
            roles = run_solver(binary, "types", "greedy", types_payload)
        c["roles"] = roles
        client.submit_roles(match_id, c["token"], roles)
        print(f"   [{c['name']} - {c['policy'].upper()}]: Chọn vai trò: {roles}")

    client.match_action(match_id, "start")
    print(f"\n[+] Trận đại chiến chính thức BẮT ĐẦU (start)!\n")

    # BƯỚC 2: Thi đấu từng ngày
    total_days = len(map_config.get("daySteps", []))
    for day_num in range(1, total_days + 1):
        day_idx = day_num - 1
        steps = map_config["daySteps"][day_idx]
        print(f"\n=======================================================")
        print(f"⚔️  NGÀY THI ĐẤU {day_num}/{total_days} (Số bước: {steps})")
        print(f"=======================================================")

        # Đợi server đồng bộ
        statuses = {}
        for attempt in range(25):
            synced = True
            for c in competitors:
                try:
                    st = client.get_game_status(match_id, c["token"])
                    statuses[c["name"]] = st
                    if st.get("currentDay") != day_num:
                        synced = False
                except Exception:
                    synced = False
            if synced and len(statuses) == num_players:
                break
            time.sleep(0.5)

        traffics = statuses[competitors[0]["name"]].get("traffics", [])

        # Mỗi đội lần lượt giải và nộp bài
        for c in competitors:
            st = statuses.get(c["name"], {})
            raw_agents = st.get("agents", [])
            built_agents = []
            for i in range(len(map_config["agents"])):
                if i < len(raw_agents):
                    kind = c["roles"][i] if raw_agents[i].get("kind") is None else raw_agents[i].get("kind")
                    pos = raw_agents[i].get("pos", map_config["agents"][i])
                    fuel = map_config["fuelLimits"] if raw_agents[i].get("fuel") is None else raw_agents[i].get("fuel")
                else:
                    kind = c["roles"][i]
                    pos = map_config["agents"][i]
                    fuel = map_config["fuelLimits"]
                built_agents.append({"kind": kind, "pos": pos, "fuel": fuel})

            day_info = {
                "day": day_idx,
                "steps": steps,
                "agents": built_agents,
                "traffics": [{"pos": item["pos"], "status": item["status"]} for item in traffics]
            }

            plan_payload = {
                "config": map_config,
                "day_info": day_info,
                "types": c["roles"],
                "search": {"time_limit_ms": 5000}
            }

            print(f"[*] [{c['name']:<16}] ({c['policy'].upper()}) đang tính toán...")
            t0 = time.time()
            try:
                plan = run_solver(binary, "plan", c["policy"], plan_payload, timeout=30)
            except Exception as e:
                print(f"    [!] {c['name']} gặp sự cố ({e}), fallback sang greedy...")
                plan = run_solver(binary, "plan", "greedy", plan_payload, timeout=10)
            t_calc = time.time() - t0

            client.submit_actions(match_id, c["token"], plan)
            print(f"    [+] Nộp bài thành công ({t_calc:.2f}s)!")

        # Chuyển sang ngày tiếp theo
        if day_num < total_days:
            time.sleep(0.5)
            try:
                client.match_action(match_id, "next_day")
                print(f"[+] Hoàn thành Ngày {day_num} -> Server chuyển sang Ngày {day_num + 1}!")
            except Exception as e:
                print(f"[!] Chuyển ngày: {e}")

    # BƯỚC 3: Tổng kết bảng vàng
    time.sleep(1.5)
    final_match = client.get_match(match_id)
    teams_res = final_match.get("teams", [])

    print("\n" + "=" * 85)
    print("🏆 BẢNG XẾP HẠNG CHUNG CUỘC - ĐẠI CHIẾN BATTLE ROYALE 5 THUẬT TOÁN:")
    print(f"🔗 Xem Replay & Diễn biến trên Web: {match_url}")
    print("=" * 85)

    teams_sorted = sorted(
        teams_res,
        key=lambda x: (x.get("total_udon_servings", 0), x.get("total_udon_types", 0), x.get("total_udon_daily_types", 0)),
        reverse=True
    )

    medals = ["🥇 QUÁN QUÂN", "🥈 Á QUÂN", "🥉 QUÝ QUÂN", "4️⃣ HẠNG 4", "5️⃣ HẠNG 5"]
    for idx, t in enumerate(teams_sorted):
        medal = medals[idx] if idx < len(medals) else f"{idx+1}️⃣"
        tname = t.get("team_name", "Unknown")
        servings = t.get("total_udon_servings", 0)
        types = t.get("total_udon_types", 0)
        daily_types = t.get("total_udon_daily_types", 0)
        resp_time = t.get("total_response_time_ms", 0)
        print(f" {medal:<13} | {tname:<18} | {servings:>3} bát mì | {types}/4 loại mì | {daily_types:>2} loại/ngày | Phản hồi: {resp_time}ms")
    print("=" * 85)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mega Battle Royale 5 Solvers trên HAUI Procon")
    parser.add_argument("--map-config", default=str(ROOT / "map_22x22.json"), help="File cấu hình bản đồ")
    args = parser.parse_args()

    play_grand_tournament(map_config_file=args.map_config)
