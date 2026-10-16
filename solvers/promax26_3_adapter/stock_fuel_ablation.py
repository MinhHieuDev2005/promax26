"""Sequential ablation with saved plans, binary hashes and explicit settings."""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from run_snapshot import ROOT

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--budget',type=int,default=3000)
    p.add_argument('--seeds',type=int,nargs='+',default=[1,2,3])
    p.add_argument('--study570',action='store_true')
    p.add_argument('--joint570',action='store_true')
    args=p.parse_args()
    out=ROOT/'reports/stock-fuel'
    if args.study570: out=out/'target570-marginal-mobile'
    if args.joint570: out=ROOT/'reports/stock-fuel/target570-joint-boundary'
    out.mkdir(parents=True,exist_ok=True)
    configurations={
        'baseline':('solver_versions/udon530_cross_550_gui_default.exe',[]),
        'stock':('build-stock-fuel/udon_stock_fuel_runner.exe',['--stock-repair','--tail-repair']),
        'fuel':('build-stock-fuel/udon_stock_fuel_runner.exe',['--terminal-rollout']),
        'combined':('build-stock-fuel/udon_stock_fuel_runner.exe',['--stock-repair','--tail-repair','--terminal-rollout']),
    }
    if args.study570:
        candidate='build-stock-fuel/udon_stock_fuel_runner.exe'
        configurations={
            'baseline':('solver_versions/udon530_cross_550_validated.exe',[]),
            'stock':(candidate,['--marginal-stock']),
            'fuel':(candidate,['--mobile-forecast','--future-weight','0.2']),
            'combined':(candidate,['--marginal-stock','--mobile-forecast','--future-weight','0.2']),
        }
    if args.joint570:
        candidate='build-stock-fuel/udon_stock_fuel_runner.exe'
        configurations={
            'baseline':('solver_versions/udon530_cross_550_validated.exe',[]),
            'actual-ruin':(candidate,['--actual-ruin']),
            'boundary':(candidate,['--boundary-select']),
            'joint-boundary':(candidate,['--actual-ruin','--boundary-select']),
        }
    with (out/'BENCHMARK_RESULTS.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f)
        w.writerow(['variant','seed','budget_ms','threads','distinct','cumulative','total','runtime_ms','valid','report','sha256'])
        for seed in args.seeds:
            for name,(exe,flags) in configurations.items():
                report=out/f'{name}-{args.budget}ms-s{seed}.json'
                command=[sys.executable,str(Path(__file__).with_name('run_snapshot.py')),
                    '--snapshot','cases/master/32japan.snapshot.json','--exe',exe,
                    '--budget',str(args.budget),'--seed',str(seed),'--threads','8',
                    '--roles','0,0,0,0,1,0,0','--end-spot-weight','0' if args.study570 or args.joint570 else '-1','--cross-moves','7',
                    '--output',str(report),*flags]
                subprocess.run(command,cwd=ROOT,check=True)
                r=json.loads(report.read_text(encoding='utf-8'))
                w.writerow([name,seed,args.budget,8,*r['score'],sum(d['wall_ms'] for d in r['days']),
                    True,report.name,r['exe_sha256']])
                f.flush()

if __name__=='__main__': main()
