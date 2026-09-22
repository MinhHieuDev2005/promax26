#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAUI Procon 2026 - Versus Match Runner (Đấu Đối Kháng Trực Tiếp)
Cho phép 2 đội (hihi vs haha) cùng thi đấu đối kháng trực tiếp trên web HAUI.
Đội 1 (hihi): Do Solver d:\hex (ALNS / MLNS) điều khiển.
Đội 2 (haha): Do Bot đối thủ (hoặc Solver khác như Greedy / Local Search / Người chơi) điều khiển.
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
        raise RuntimeError(f"Solver {policy} failed ({proc.returncode}). Payload saved to {debug_path}. Stderr: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def get_team_by_name(teams, name):
    for t in teams:
        if t["name"].strip().lower() == name.strip().lower():
            return t
    available = [t["name"] for t in teams]
    raise ValueError(f"Không tìm thấy đội '{name}' trên web HAUI. Các đội hiện có: {available}")


def auto_detect_policy(team_name, explicit_policy=None):
    if explicit_policy:
        return explicit_policy.lower()
    name_lower = team_name.lower()
    if "alns" in name_lower:
        return "alns"
    if "mlns" in name_lower:
        return "mlns"
    if "greedy" in name_lower:
        return "greedy"
    if "aco" in name_lower:
        return "aco_ls"
    if "local" in name_lower or "ls" in name_lower:
        return "local_search"
    return "alns"


def play_versus(team1_name="Team-ALNS", team2_name="Team-Greedy", policy_team1=None, policy_team2=None, source_match_id=None, map_config_file=None):
    binary = ROOT / "build" / "hexudon.exe"
    if not binary.is_file():
        raise FileNotFoundError(f"Solver binary not found at {binary}")

    client = HauiClient()
    client.login(DEFAULT_USER, DEFAULT_PASS)
    teams = client.get_teams()

    # Tìm thông tin 2 đội theo tên
    try:
        t1_obj = get_team_by_name(teams, team1_name)
    except ValueError:
        # Fallback về hihi nếu chưa có
        t1_obj = get_team_by_name(teams, "hihi")
        team1_name = "hihi"

    try:
        t2_obj = get_team_by_name(teams, team2_name)
    except ValueError:
        t2_obj = get_team_by_name(teams, "haha")
        team2_name = "haha"

    policy1 = auto_detect_policy(team1_name, policy_team1)
    policy2 = auto_detect_policy(team2_name, policy_team2)

    print("=" * 75)
    print(f"⚔️  TRẬN ĐẤU ĐỐI KHÁNG TRỰC TIẾP:")
    print(f"   🚩 Đội 1: '{t1_obj['name']}' (Solver: {policy1.upper()})")
    print(f"   🚩 Đội 2: '{t2_obj['name']}' (Solver: {policy2.upper()})")
    print("=" * 75)

    # Tạo trận đấu đối kháng mới (players = 2)
    map_config = None
    if map_config_file and os.path.isfile(map_config_file):
        print(f"[*] Đọc cấu hình bản đồ từ file: {map_config_file}")
        with open(map_config_file, "r", encoding="utf-8") as f:
            map_config = json.load(f)
    elif source_match_id:
        try:
            source_data = client.get_match(source_match_id)
            map_config = json.loads(source_data["match"]["map_config_json"])
        except Exception:
            default_fixture = ROOT / "map_22x22.json"
            if default_fixture.is_file():
                print(f"[*] Không tìm thấy trận {source_match_id}, chuyển sang dùng bản đồ mẫu: {default_fixture}")
                with open(default_fixture, "r", encoding="utf-8") as f:
                    map_config = json.load(f)
            else:
                raise
    else:
        default_fixture = ROOT / "map_22x22.json"
        if default_fixture.is_file():
            with open(default_fixture, "r", encoding="utf-8") as f:
                map_config = json.load(f)

    map_config["players"] = 2
    map_config["startsAt"] = int(time.time()) + 90
    map_config["daySeconds"] = [60, 60, 60, 60]

    match_name = f"{t1_obj['name']}-vs-{t2_obj['name']}-{int(time.time())}"
    print(f"[*] Đang tạo trận đấu đối kháng trên HAUI: '{match_name}'...")
    new_match = client.create_match(match_name, map_config)
    match_id = new_match["match"]["id"]
    match_url = f"https://procon26.haui.ac.vn/matches/{match_id}"
    print(f"[+] Trận đấu đã tạo thành công: {match_url}")

    client.add_team(match_id, t1_obj["id"])
    client.add_team(match_id, t2_obj["id"])
    client.match_action(match_id, "start_agent_select")
    print(f"[+] Đã thêm 2 đội ({t1_obj['name']} & {t2_obj['name']}) vào trận và mở chọn vai trò xe!\n")

    # Bước 1: Chọn vai trò xe cho cả 2 đội
    print(f"--- BƯỚC 1: Chọn vai trò xe ---")
    types_payload = {"config": map_config}
    
    roles1 = run_solver(binary, "types", policy1, types_payload)
    print(f"[{t1_obj['name']} ({policy1.upper()})] Chọn vai trò: {roles1}")
    client.submit_roles(match_id, t1_obj["token"], roles1)

    roles2 = run_solver(binary, "types", policy2, types_payload)
    print(f"[{t2_obj['name']} ({policy2.upper()})] Chọn vai trò: {roles2}")
    client.submit_roles(match_id, t2_obj["token"], roles2)
    print(f"[+] Cả 2 đội đã nộp cấu hình vai trò xe thành công!")

    # Bắt đầu tính giờ thi đấu
    client.match_action(match_id, "start")
    print(f"[+] Đã kích hoạt trận đấu 'start' (Trận chính thức diễn ra!)\n")

    # Bước 2: Thi đấu từng ngày
    total_days = len(map_config.get("daySteps", []))
    print(f"--- BƯỚC 2: Cả 2 đội cùng giải và nộp bài từng ngày (Tổng: {total_days} ngày) ---")

    for day_num in range(1, total_days + 1):
        day_idx = day_num - 1
        steps = map_config["daySteps"][day_idx]
        print(f"\n=======================================================")
        print(f"⚔️  NGÀY {day_num}/{total_days} (Số bước: {steps})")
        print(f"=======================================================")

        # Chờ server đồng bộ ngày hiện tại
        st1, st2 = None, None
        for _ in range(30):
            try:
                s1 = client.get_game_status(match_id, t1_obj["token"])
                s2 = client.get_game_status(match_id, t2_obj["token"])
                if s1.get("currentDay") == day_num and s2.get("currentDay") == day_num:
                    st1, st2 = s1, s2
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not st1:
            st1 = client.get_game_status(match_id, t1_obj["token"])
        if not st2:
            st2 = client.get_game_status(match_id, t2_obj["token"])

        agents1 = st1.get("agents", [])
        if not agents1:
            agents1 = [{"kind": roles1[i], "pos": pos, "fuel": map_config["fuelLimits"]} for i, pos in enumerate(map_config["agents"])]
        agents2 = st2.get("agents", [])
        if not agents2:
            agents2 = [{"kind": roles2[i], "pos": pos, "fuel": map_config["fuelLimits"]} for i, pos in enumerate(map_config["agents"])]

        traffics = st1.get("traffics", [])

        def build_agents(raw_agents, roles):
            res = []
            for i, a in enumerate(raw_agents):
                kind = roles[i] if a.get("kind") is None else a.get("kind")
                pos = a.get("pos", map_config["agents"][i])
                fuel = map_config["fuelLimits"] if a.get("fuel") is None else a.get("fuel")
                res.append({"kind": kind, "pos": pos, "fuel": fuel})
            return res

        # Tính toán nước đi cho Đội 1
        day_info1 = {
            "day": day_idx,
            "steps": steps,
            "agents": build_agents(agents1, roles1),
            "traffics": [{"pos": item["pos"], "status": item["status"]} for item in traffics]
        }
        print(f"[*] [{t1_obj['name']} - {policy1.upper()}] Đang tính toán nước đi...")
        t0 = time.time()
        try:
            plan1 = run_solver(binary, "plan", policy1, {"config": map_config, "day_info": day_info1, "types": roles1, "search": {"time_limit_ms": 5000}})
        except Exception as e:
            print(f"[!] Solver {policy1} lỗi ({e}), fallback sang greedy...")
            plan1 = run_solver(binary, "plan", "greedy", {"config": map_config, "day_info": day_info1, "types": roles1, "search": {"time_limit_ms": 1000}})
        t1 = time.time() - t0
        client.submit_actions(match_id, t1_obj["token"], plan1)
        print(f"[+] [{t1_obj['name']} - {policy1.upper()}] Đã nộp bài ({t1:.2f}s)!")

        # Tính toán nước đi cho Đội 2
        day_info2 = {
            "day": day_idx,
            "steps": steps,
            "agents": build_agents(agents2, roles2),
            "traffics": [{"pos": item["pos"], "status": item["status"]} for item in traffics]
        }
        print(f"[*] [{t2_obj['name']} - {policy2.upper()}] Đang tính toán nước đi...")
        t0 = time.time()
        try:
            plan2 = run_solver(binary, "plan", policy2, {"config": map_config, "day_info": day_info2, "types": roles2, "search": {"time_limit_ms": 5000}})
        except Exception as e:
            print(f"[!] Solver {policy2} lỗi ({e}), fallback sang greedy...")
            plan2 = run_solver(binary, "plan", "greedy", {"config": map_config, "day_info": day_info2, "types": roles2, "search": {"time_limit_ms": 1000}})
        t2 = time.time() - t0
        client.submit_actions(match_id, t2_obj["token"], plan2)
        print(f"[+] [{t2_obj['name']} - {policy2.upper()}] Đã nộp bài ({t2:.2f}s)!")

        # Chuyển sang ngày tiếp theo
        if day_num < total_days:
            time.sleep(0.5)
            try:
                client.match_action(match_id, "next_day")
                print(f"[+] Đã hoàn thành Ngày {day_num} -> Chuyển sang ngày tiếp theo!")
            except Exception as e:
                print(f"[!] Chuyển ngày: {e}")

    # Bước 3: Tổng kết tỉ số đối kháng
    time.sleep(1.0)
    final_match = client.get_match(match_id)
    teams_res = final_match.get("teams", [])
    print(f"\n" + "=" * 70)
    print(f"🏁 TỔNG KẾT KẾT QUẢ ĐỐI KHÁNG TRỰC TIẾP TỪ SERVER HAUI:")
    print(f"Xem replay: {match_url}")
    print("=" * 70)

    teams_sorted = sorted(teams_res, key=lambda x: (x.get("total_udon_servings", 0), x.get("total_udon_types", 0), x.get("total_udon_daily_types", 0)), reverse=True)
    for t in teams_sorted:
        tname = t.get("team_name", "Unknown")
        servings = t.get("total_udon_servings", 0)
        types = t.get("total_udon_types", 0)
        daily_types = t.get("total_udon_daily_types", 0)
        resp_time = t.get("total_response_time_ms", 0)
        print(f"   🚩 ĐỘI {tname.upper():<12}: {servings:>3} bát mì  |  {types}/4 loại  |  {daily_types} loại/ngày  |  Thời gian phản hồi: {resp_time}ms")

    if len(teams_sorted) >= 2:
        s1 = teams_sorted[0].get("total_udon_servings", 0)
        s2 = teams_sorted[1].get("total_udon_servings", 0)
        t1_name = teams_sorted[0].get("team_name").upper()
        t2_name = teams_sorted[1].get("team_name").upper()
        if s1 > s2:
            print(f"\n🏆 CHIẾN THẮNG THUỘC VỀ: ĐỘI {t1_name}!")
        elif s1 < s2:
            print(f"\n🏆 CHIẾN THẮNG THUỘC VỀ: ĐỘI {t2_name}!")
        else:
            print("\n🤝 KẾT QUẢ: HAI ĐỘI HÒA NHAU!")
    print("=" * 70)


def list_all_teams():
    client = HauiClient()
    client.login(DEFAULT_USER, DEFAULT_PASS)
    teams = client.get_teams()
    print("=" * 70)
    print(f"📋 DANH SÁCH CÁC ĐỘI (TEAMS) TRÊN HAUI PROCON 2026:")
    print("=" * 70)
    for t in teams:
        print(f" - {t['name']:<15} (ID: {t['id']}, Token: {t['token'][:16]}...)")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chạy đối kháng trực tiếp 2 đội trên HAUI server")
    parser.add_argument("--list-teams", action="store_true", help="Hiển thị danh sách các đội hiện có")
    parser.add_argument("--team1", default="Team-ALNS", help="Tên Đội 1 (mặc định: Team-ALNS hoặc hihi)")
    parser.add_argument("--team2", default="Team-Greedy", help="Tên Đội 2 (mặc định: Team-Greedy hoặc haha)")
    parser.add_argument("--policy1", default=None, choices=["alns", "mlns", "aco_ls", "local_search", "greedy"], help="Chiến thuật của Đội 1 (tự động nhận diện từ tên đội nếu để trống)")
    parser.add_argument("--policy2", default=None, choices=["alns", "mlns", "aco_ls", "local_search", "greedy"], help="Chiến thuật của Đội 2 (tự động nhận diện từ tên đội nếu để trống)")
    parser.add_argument("--source-match", default=None, help="Source match ID để lấy bản đồ")
    parser.add_argument("--map-config", default=str(ROOT / "map_22x22.json"), help="File cấu hình bản đồ JSON")
    args = parser.parse_args()

    if args.list_teams:
        list_all_teams()
    else:
        play_versus(
            team1_name=args.team1,
            team2_name=args.team2,
            policy_team1=args.policy1,
            policy_team2=args.policy2,
            source_match_id=args.source_match,
            map_config_file=args.map_config
        )
