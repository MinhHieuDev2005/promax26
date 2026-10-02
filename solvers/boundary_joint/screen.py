"""One-factor fixed-state screening; forecasts are never match achievements."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from study import DEADLINE, ROOT


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--label",required=True)
    p.add_argument("--checkpoint",default="solver_learning/runs/u25-preview-release-confirm-user-input-25x25-match-s2.json")
    p.add_argument("--day",type=int,default=3)
    a=p.parse_args()
    variants=[("control",0,0,0), ("endpoints",3,0,0), ("more_endpoints",6,0,0),
              ("slack1",3,1,0), ("slack2",3,2,0), ("chokudai",3,1,1)]
    rows=[]
    for name,quota,slack,tails in variants:
        if time.time()+55>DEADLINE:
            break
        label=a.label+"-"+name
        cmd=[sys.executable,str(Path(__file__).with_name("study.py")),"--label",label,
             "--checkpoint",a.checkpoint,"--day",str(a.day),"--quota",str(quota),
             "--slack",str(slack),"--tails",str(tails),"--seeds","1"]
        subprocess.run(cmd,cwd=ROOT,check=True,timeout=60)
        found=[f for f in (ROOT/"solver_learning/runs").glob(label+"-*.json")
               if "partial" not in f.name and "summary" not in f.name]
        if len(found)!=1:raise RuntimeError("ambiguous trial artifacts")
        record=json.loads(found[0].read_text(encoding="utf-8"))
        diag=record["days"][0]["diagnostics"]
        rows.append({"variant":name,"checkpoint":str(found[0].relative_to(ROOT)),
                     "score_today":record["days"][0]["servings"],
                     "rollouts":diag.get("rollouts"),"wall_ms":record["max_day_ms"],
                     "peak_rss_bytes":record["peak_rss_bytes"],
                     "valid":record["verified"],"coverage":record["full_coverage"],
                     "within_budget":record["deadline_pass"]})
    path=ROOT/"solver_learning/runs"/(a.label+"-screen.json")
    with path.open("x",encoding="utf-8") as f:
        json.dump({"scope":"fixed state only, independent time-limited ALNS seeds; not a paired fixed-incumbent ablation", "rows":rows},f,indent=2)
    for row in rows:
        forecasts=row["rollouts"] or []
        print(row["variant"],"today",row["score_today"],"best_forecast",max([r["sum"] for r in forecasts],default=None),"wall_ms",round(row["wall_ms"]),flush=True)


if __name__=="__main__":main()
