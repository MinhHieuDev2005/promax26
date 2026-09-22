#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAUI Procon 2026 Online Solver Runner
Runs the high-performance C++ solver (ALNS / MLNS+DP) from d:\\hex
directly against the live HAUI Procon server (https://procon26.haui.ac.vn/).
"""

import argparse
import copy
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
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
DEFAULT_TEAM = "hihi"

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
        raise RuntimeError(f"Solver failed ({proc.returncode}): {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def play_match(source_match_id=None, match_id=None, policy="alns", team_name=DEFAULT_TEAM, username=DEFAULT_USER, password=DEFAULT_PASS):
    binary = ROOT / "build" / "hexudon.exe"
    if not binary.is_file():
        binary = ROOT / "build" / "hexudon"
    if not binary.is_file():
        raise FileNotFoundError(f"Solver binary not found at {binary}")

    print(f"=== HEXUDON SOLVER (d:\\hex) ===")
    print(f"Policy: {policy.upper()} | Binary: {binary.resolve()}")
    
    client = HauiClient()
    print(f"[*] Logging in as '{username}'...")
    login_info = client.login(username, password)
    admin_name = login_info.get("admin", {}).get("display_name", username)
    print(f"[+] Logged in successfully: {admin_name}")

    teams = client.get_teams()
    team = next((t for t in teams if t["name"] == team_name), None)
    if not team:
        raise ValueError(f"Team '{team_name}' not found in account!")
    team_token = team["token"]
    print(f"[+] Using team '{team_name}' (ID: {team['id']}, token: {team_token[:12]}...)")

    if source_match_id and not match_id:
        print(f"[*] Fetching source match {source_match_id} to create practice game...")
        source_data = client.get_match(source_match_id)
        map_config = json.loads(source_data["match"]["map_config_json"])
        map_config["startsAt"] = int(time.time()) + 90
        map_config["players"] = 1
        
        match_name = f"hex-solver-{policy}-{int(time.time())}"
        print(f"[*] Creating new match '{match_name}'...")
        new_match = client.create_match(match_name, map_config)
        match_id = new_match["match"]["id"]
        print(f"[+] Match created: https://procon26.haui.ac.vn/matches/{match_id}")

        client.add_team(match_id, team["id"])
        client.match_action(match_id, "start_agent_select")
        print(f"[+] Match set to agent_select")
    else:
        match_data = client.get_match(match_id)
        map_config = json.loads(match_data["match"]["map_config_json"])
        print(f"[*] Playing on existing match: https://procon26.haui.ac.vn/matches/{match_id}")

    # Step 1: Agent type selection via d:\hex solver
    print(f"\n--- BƯỚC 1: Chọn loại xe bằng Solver '{policy}' ---")
    types_payload = {"config": map_config}
    start_t = time.time()
    agent_types = run_solver(binary, "types", policy, types_payload)
    elapsed = time.time() - start_t
    print(f"[+] Solver '{policy}' chọn loại xe: {agent_types} ({elapsed:.2f}s)")

    print(f"[*] Nộp vai trò xe lên server HAUI...")
    sub_res = client.submit_roles(match_id, team_token, agent_types)
    print(f"[+] Server chấp nhận vai trò: {sub_res}")

    # Start match
    try:
        client.match_action(match_id, "start")
        print(f"[+] Đã kích hoạt trận đấu (start)")
    except Exception as e:
        print(f"[!] Start notice: {e}")

    # Step 2: Solve each day
    total_days = len(map_config.get("daySteps", []))
    print(f"\n--- BƯỚC 2: Giải từng ngày thi đấu (Tổng: {total_days} ngày) ---")

    history = {
        "traffics": [],
        "agent_paths": [],
        "collected_brands": 0,
        "sum_daily_types": 0,
        "servings": 0,
        "spot_stock": [s["stocks"] for s in map_config.get("spots", [])]
    }
    prev_agents = None

    for day_num in range(1, total_days + 1):
        day_idx = day_num - 1
        steps = map_config["daySteps"][day_idx]
        print(f"\n>>> [NGÀY {day_num}/{total_days}] Số bước: {steps}")

        # Wait for server status to reflect current day
        status = None
        for _ in range(30):
            try:
                st = client.get_game_status(match_id, team_token)
                if st.get("currentDay") == day_num:
                    status = st
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not status:
            # Fallback to direct fetch
            status = client.get_game_status(match_id, team_token)

        cur_agents = status.get("agents", [])
        if not cur_agents and prev_agents:
            cur_agents = prev_agents
        elif not cur_agents:
            cur_agents = [{"kind": agent_types[i], "pos": pos, "fuel": map_config["fuelLimits"]} for i, pos in enumerate(map_config["agents"])]

        traffics = status.get("traffics", [])

        day_info = {
            "day": day_idx,
            "steps": steps,
            "agents": [{"kind": cur_agents[i].get("kind", agent_types[i]), "pos": cur_agents[i]["pos"], "fuel": cur_agents[i].get("fuel", map_config["fuelLimits"])} for i in range(len(cur_agents))],
            "traffics": [{"pos": item["pos"], "status": item["status"]} for item in traffics]
        }

        plan_payload = {
            "config": map_config,
            "day_info": day_info,
            "types": agent_types,
            "history": history,
            "search": {
                "time_limit_ms": 5000
            }
        }

        print(f"[*] Solver '{policy}' đang tính toán nước đi cho Ngày {day_num}...")
        t0 = time.time()
        plan = run_solver(binary, "plan", policy, plan_payload, timeout=30)
        t_plan = time.time() - t0
        print(f"[+] Đã tìm ra phương án tối ưu trong {t_plan:.2f}s: {len(plan)} xe")

        print(f"[*] Nộp bài Ngày {day_num} lên server...")
        ans_res = client.submit_actions(match_id, team_token, plan)
        print(f"[+] Server HAUI ghi nhận: {ans_res}")

        # Advance to next day if practice match
        if day_num < total_days:
            time.sleep(0.5)
            try:
                client.match_action(match_id, "next_day")
                print(f"[+] Đã chuyển sang ngày tiếp theo (next_day)")
            except Exception as e:
                print(f"[!] Next day notice: {e}")

    # Step 3: Fetch final results
    print(f"\n--- BƯỚC 3: Tổng kết điểm thi đấu từ Server HAUI ---")
    time.sleep(1.0)
    final_match = client.get_match(match_id)
    teams_res = final_match.get("teams", [])
    our_team = next((t for t in teams_res if t["team_id"] == team["id"]), None)

    if our_team:
        print(f"===========================================================")
        print(f"🏆 KẾT QUẢ GIẢI BỞI SOLVER '{policy.upper()}' (d:\\hex):")
        print(f"   Trận đấu: https://procon26.haui.ac.vn/matches/{match_id}")
        print(f"   Đội thi đấu: {our_team.get('team_name')}")
        print(f"   Số loại Udon toàn trận: {our_team.get('total_udon_types')}")
        print(f"   Tổng loại Udon theo ngày: {our_team.get('total_udon_daily_types')}")
        print(f"   Số suất mì (Servings): {our_team.get('total_udon_servings')}")
        print(f"   Tổng thời gian phản hồi: {our_team.get('total_response_time_ms')} ms")
        print(f"===========================================================")
    else:
        print(f"Match status: {final_match.get('match', {}).get('status')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run d:\\hex solver on HAUI Procon server")
    parser.add_argument("--source-match", default="450b82df-22f1-4bb8-a7f2-dc782fcc00f0", help="Source match ID to clone")
    parser.add_argument("--match-id", default=None, help="Specific match ID to play directly")
    parser.add_argument("--policy", default="alns", choices=["alns", "mlns", "aco_ls", "local_search", "greedy"], help="Solver policy")
    parser.add_argument("--team", default=DEFAULT_TEAM, help="Team name")
    args = parser.parse_args()

    play_match(source_match_id=args.source_match, match_id=args.match_id, policy=args.policy, team_name=args.team)
