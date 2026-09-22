#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAUI Procon 2026 - 4-Solver Championship Tournament
Thi đấu đối kháng 4 solver/trận, xoay vòng cho đến khi tất cả các cặp solver
đều chạm trán trực tiếp với nhau ít nhất 1-2 lần.
Bao gồm cả 5 solver từ d:\\hex và solver mẫu từ D:\\Procon26!
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


# --- Solvers ---
def run_hex_solver(command, policy, payload, timeout=30):
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
        raise RuntimeError(f"Hex solver {policy} error ({proc.returncode}): {proc.stderr.strip()}")
    return json.loads(proc.stdout)


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


ALL_SOLVERS = {
    "ALNS": {"team_name": "Team-ALNS", "source": "hex", "policy": "alns", "desc": "Adaptive LNS (d:\\hex)"},
    "MLNS": {"team_name": "Team-MLNS", "source": "hex", "policy": "mlns", "desc": "Multi-Day LNS (d:\\hex)"},
    "ACO": {"team_name": "Team-ACO", "source": "hex", "policy": "aco_ls", "desc": "Ant Colony + LS (d:\\hex)"},
    "LocalSearch": {"team_name": "Team-LocalSearch", "source": "hex", "policy": "local_search", "desc": "2-Opt/Relocate (d:\\hex)"},
    "Greedy": {"team_name": "Team-Greedy", "source": "hex", "policy": "greedy", "desc": "Classic Greedy (d:\\hex)"},
    "Procon26": {"team_name": "Procon26-Bot", "source": "procon26", "policy": "greedy_refuel", "desc": "Sample Bot (D:\\Procon26)"},
}

# Lịch thi đấu 5 trận 4-solver bao phủ 100% tất cả 15 cặp đối đầu
TOURNAMENT_SCHEDULE = [
    {"id": 1, "title": "Bảng Tử Thần (Top 4 Mạnh Nhất)", "solvers": ["ALNS", "MLNS", "ACO", "Procon26"]},
    {"id": 2, "title": "Thử Thách Chiến Thuật", "solvers": ["ALNS", "LocalSearch", "Greedy", "Procon26"]},
    {"id": 3, "title": "Cạnh Tranh Trực Tiếp", "solvers": ["MLNS", "ACO", "LocalSearch", "Greedy"]},
    {"id": 4, "title": "So Kèo Kỹ Thuật", "solvers": ["ALNS", "MLNS", "LocalSearch", "Procon26"]},
    {"id": 5, "title": "Đại Chiến Vòng Khép", "solvers": ["ALNS", "ACO", "Greedy", "Procon26"]},
]


def play_4way_match(client, match_cfg, map_config, teams_info):
    match_id_num = match_cfg["id"]
    match_title = match_cfg["title"]
    solver_keys = match_cfg["solvers"]

    print("\n" + "=" * 85)
    print(f"🥊 TRẬN {match_id_num}/5: {match_title}")
    print(f"   Tham gia: {', '.join(solver_keys)}")
    print("=" * 85)

    competing_teams = []
    for skey in solver_keys:
        info = ALL_SOLVERS[skey]
        t_obj = teams_info[info["team_name"]]
        competing_teams.append({
            "key": skey,
            "team_name": info["team_name"],
            "source": info["source"],
            "policy": info["policy"],
            "desc": info["desc"],
            "id": t_obj["id"],
            "token": t_obj["token"],
            "roles": None
        })

    # Tạo trận
    cfg_copy = json.loads(json.dumps(map_config))
    cfg_copy["players"] = 4
    cfg_copy["startsAt"] = int(time.time()) + 90
    cfg_copy["daySeconds"] = [60, 60, 60, 60]

    match_name = f"Tourney-Match{match_id_num}-{int(time.time())}"
    new_match = client.create_match(match_name, cfg_copy)
    match_id = new_match["match"]["id"]
    match_url = f"https://procon26.haui.ac.vn/matches/{match_id}"
    print(f"[*] Trận đấu đã tạo trên HAUI: {match_url}")

    for c in competing_teams:
        client.add_team(match_id, c["id"])

    client.match_action(match_id, "start_agent_select")

    # Bước 1: Nộp vai trò xe
    print("   [1] Đang chọn vai trò xe...")
    for c in competing_teams:
        if c["source"] == "hex":
            try:
                roles = run_hex_solver("types", c["policy"], {"config": cfg_copy})
            except Exception:
                roles = run_hex_solver("types", "greedy", {"config": cfg_copy})
        else:
            roles = run_procon26_roles(cfg_copy)
        c["roles"] = roles
        client.submit_roles(match_id, c["token"], roles)
        print(f"       - {c['key']:<12}: {roles}")

    client.match_action(match_id, "start")

    # Bước 2: Thi đấu từng ngày
    total_days = len(cfg_copy.get("daySteps", []))
    for day_num in range(1, total_days + 1):
        day_idx = day_num - 1
        steps = cfg_copy["daySteps"][day_idx]
        print(f"   [2] Ngày {day_num}/{total_days} (Số bước: {steps})")

        # Đồng bộ trạng thái
        statuses = {}
        for attempt in range(25):
            synced = True
            for c in competing_teams:
                try:
                    st = client.get_game_status(match_id, c["token"])
                    statuses[c["key"]] = st
                    if st.get("currentDay") != day_num:
                        synced = False
                except Exception:
                    synced = False
            if synced and len(statuses) == 4:
                break
            time.sleep(0.5)

        traffics = statuses[competing_teams[0]["key"]].get("traffics", [])

        for c in competing_teams:
            st = statuses.get(c["key"], {})
            raw_agents = st.get("agents", [])
            built_agents = []
            for i in range(len(cfg_copy["agents"])):
                if i < len(raw_agents):
                    kind = c["roles"][i] if raw_agents[i].get("kind") is None else raw_agents[i].get("kind")
                    pos = raw_agents[i].get("pos", cfg_copy["agents"][i])
                    fuel = cfg_copy["fuelLimits"] if raw_agents[i].get("fuel") is None else raw_agents[i].get("fuel")
                else:
                    kind = c["roles"][i]
                    pos = cfg_copy["agents"][i]
                    fuel = cfg_copy["fuelLimits"]
                built_agents.append({"kind": kind, "pos": pos, "fuel": fuel})

            day_info = {
                "day": day_idx,
                "steps": steps,
                "agents": built_agents,
                "traffics": [{"pos": item["pos"], "status": item["status"]} for item in traffics]
            }

            t0 = time.time()
            if c["source"] == "hex":
                try:
                    plan = run_hex_solver("plan", c["policy"], {"config": cfg_copy, "day_info": day_info, "types": c["roles"], "search": {"time_limit_ms": 3000}})
                except Exception:
                    plan = run_hex_solver("plan", "greedy", {"config": cfg_copy, "day_info": day_info, "types": c["roles"], "search": {"time_limit_ms": 1000}})
            else:
                plan = run_procon26_plan(cfg_copy, st, c["roles"], day_num=day_num)
            t_solve = time.time() - t0

            client.submit_actions(match_id, c["token"], plan)
            print(f"       + {c['key']:<12} nộp bài ({t_solve:.2f}s)")

        # Chuyển ngày
        if day_num < total_days:
            time.sleep(0.5)
            try:
                client.match_action(match_id, "next_day")
            except Exception:
                pass

    # Tổng kết trận
    time.sleep(1.5)
    final_match = client.get_match(match_id)
    teams_res = final_match.get("teams", [])

    teams_res_map = {t.get("team_id"): t for t in teams_res}
    match_results = []
    for c in competing_teams:
        st = teams_res_map.get(c["id"], {})
        match_results.append({
            "key": c["key"],
            "team_name": c["team_name"],
            "servings": st.get("total_udon_servings", 0),
            "types": st.get("total_udon_types", 0),
            "daily_types": st.get("total_udon_daily_types", 0),
            "time_ms": st.get("total_response_time_ms", 0),
        })

    match_results.sort(key=lambda x: (x["servings"], x["types"], x["daily_types"]), reverse=True)

    print("\n   🏁 KẾT QUẢ TRẬN ĐẤU:")
    for rank, res in enumerate(match_results, 1):
        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else "4️⃣"))
        print(f"      {medal} {res['key']:<12}: {res['servings']:>3} bát mì  |  {res['types']}/4 loại  |  {res['time_ms']}ms")
    print(f"      Replay: {match_url}")

    return {
        "match_id": match_id_num,
        "title": match_title,
        "match_url": match_url,
        "rankings": match_results
    }


def run_full_championship():
    client = HauiClient()
    client.login(DEFAULT_USER, DEFAULT_PASS)
    all_teams_raw = client.get_teams()
    teams_info = {t["name"]: t for t in all_teams_raw}

    with open(ROOT_HEX / "map_22x22.json", "r", encoding="utf-8") as f:
        map_config = json.load(f)

    print("=" * 85)
    print("🏆🏆🏆 GIẢI VÔ ĐỊCH 4-SOLVER ROUND-ROBIN TOURNAMENT (6 SIÊU BOT) 🏆🏆🏆")
    print("=" * 85)
    print("Các Solver tham gia:")
    for k, v in ALL_SOLVERS.items():
        print(f" - {k:<12}: {v['desc']}")
    print("\nLịch trình: 5 trận đấu 4-solver (Bảo đảm mọi cặp đấu đều đối đầu trực tiếp)")
    print("=" * 85)

    all_match_reports = []
    # Điểm tích lũy: Thắng trận (Rank 1): 4đ, Rank 2: 3đ, Rank 3: 2đ, Rank 4: 1đ
    cumulative_stats = {
        k: {"matches": 0, "wins": 0, "top2": 0, "servings": 0, "points": 0, "ranks": []}
        for k in ALL_SOLVERS.keys()
    }

    # Ma trận đối đầu
    h2h = {k1: {k2: {"win": 0, "loss": 0, "tie": 0} for k2 in ALL_SOLVERS.keys()} for k1 in ALL_SOLVERS.keys()}

    for m_cfg in TOURNAMENT_SCHEDULE:
        report = play_4way_match(client, m_cfg, map_config, teams_info)
        all_match_reports.append(report)

        # Cập nhật thống kê
        rankings = report["rankings"]
        for rank_idx, r in enumerate(rankings, 1):
            s_key = r["key"]
            pts = 5 - rank_idx
            cumulative_stats[s_key]["matches"] += 1
            cumulative_stats[s_key]["servings"] += r["servings"]
            cumulative_stats[s_key]["points"] += pts
            cumulative_stats[s_key]["ranks"].append(rank_idx)
            if rank_idx == 1:
                cumulative_stats[s_key]["wins"] += 1
            if rank_idx <= 2:
                cumulative_stats[s_key]["top2"] += 1

        # Cập nhật Head-to-Head
        for i in range(len(rankings)):
            for j in range(i + 1, len(rankings)):
                k1 = rankings[i]["key"]
                k2 = rankings[j]["key"]
                s1 = rankings[i]["servings"]
                s2 = rankings[j]["servings"]
                if s1 > s2:
                    h2h[k1][k2]["win"] += 1
                    h2h[k2][k1]["loss"] += 1
                elif s1 < s2:
                    h2h[k1][k2]["loss"] += 1
                    h2h[k2][k1]["win"] += 1
                else:
                    h2h[k1][k2]["tie"] += 1
                    h2h[k2][k1]["tie"] += 1

        time.sleep(1.0)

    # In Bảng Xếp Hạng Chung Cuộc
    print("\n" + "=" * 90)
    print("🏆🏆🏆 BẢNG TỔNG SẮP HUY CHƯƠNG TOÀN DIỆN GIẢI ĐẤU 4-SOLVER 🏆🏆🏆")
    print("=" * 90)
    hdr = f"{'Thứ hạng':<10} | {'Solver':<14} | {'Số trận':<8} | {'Vô địch':<9} | {'Top 2':<7} | {'Tổng Bát Mì':<13} | {'TB Bát/Trận':<12} | {'Hạng TB':<8}"
    print(hdr)
    print("-" * 90)

    leaderboard = []
    for k, stats in cumulative_stats.items():
        m_cnt = stats["matches"]
        avg_serv = stats["servings"] / m_cnt if m_cnt > 0 else 0
        avg_rnk = sum(stats["ranks"]) / m_cnt if m_cnt > 0 else 99
        leaderboard.append({
            "key": k,
            "desc": ALL_SOLVERS[k]["desc"],
            "matches": m_cnt,
            "wins": stats["wins"],
            "top2": stats["top2"],
            "servings": stats["servings"],
            "avg_servings": avg_serv,
            "avg_rank": avg_rnk,
            "points": stats["points"]
        })

    leaderboard.sort(key=lambda x: (x["wins"], x["points"], x["avg_servings"]), reverse=True)

    medals = ["🥇 QUÁN QUÂN", "🥈 Á QUÂN", "🥉 QUÝ QUÂN", "4️⃣ HẠNG 4", "5️⃣ HẠNG 5", "6️⃣ HẠNG 6"]
    for idx, item in enumerate(leaderboard):
        m_tag = medals[idx] if idx < len(medals) else f"{idx+1}"
        row = f"{m_tag:<10} | {item['key']:<14} | {item['matches']:>4} trận | {item['wins']:>4} lần  | {item['top2']:>3} lần | {item['servings']:>7} bát    | {item['avg_servings']:>7.1f} bát   | {item['avg_rank']:>5.2f}"
        print(row)
    print("=" * 90)

    # Link replay từng trận
    print("\n🔗 Danh sách Replay chi tiết từng trận đấu trên server:")
    for rep in all_match_reports:
        print(f" - Trận {rep['match_id']} ({rep['title']}): {rep['match_url']}")
    print("=" * 90)

    best_solver = leaderboard[0]
    print(f"\n🌟 SOLVER XUẤT SẮC NHẤT GIẢI ĐẤU: {best_solver['key'].upper()} ({best_solver['desc']})!")
    print(f"   Đạt {best_solver['wins']} lần Vô địch, trung bình {best_solver['avg_servings']:.1f} bát mì/trận, thứ hạng trung bình: {best_solver['avg_rank']:.2f}")


if __name__ == "__main__":
    run_full_championship()
