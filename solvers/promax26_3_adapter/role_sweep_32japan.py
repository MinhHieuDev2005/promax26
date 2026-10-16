"""Small reproducible role screen for the current 32japan case."""
import csv
import json
import subprocess
import sys
from pathlib import Path
from run_snapshot import ROOT

runner=Path(__file__).with_name('run_snapshot.py')
exe='solver_versions/udon530_cross_550_validated.exe'
roles=[]
for supply in range(7):
    role=[0]*7; role[supply]=1; roles.append(role)
for left,right in ((0,1),(0,4),(1,4),(1,5),(4,5),(4,6)):
    role=[0]*7; role[left]=role[right]=1; roles.append(role)
out=ROOT/'reports/stock-fuel/role-screen'
out.mkdir(parents=True,exist_ok=True)
rows=[]
for index,role in enumerate(roles):
    report=out/f'role-{index}-1000ms.json'
    subprocess.run([sys.executable,str(runner),'--snapshot','cases/master/32japan.snapshot.json',
        '--exe',exe,'--budget','1000','--seed','1','--threads','8','--roles',
        ','.join(map(str,role)),'--cross-moves','7','--end-spot-weight','0',
        '--output',str(report)],cwd=ROOT,check=True)
    result=json.loads(report.read_text(encoding='utf-8'))
    rows.append([index,','.join(map(str,role)),*result['score']])
with (out/'RESULTS.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.writer(f); writer.writerow(['id','roles','c1','c2','c3']); writer.writerows(rows)
print(sorted(rows,key=lambda row:(row[2],row[3],row[4]),reverse=True))
