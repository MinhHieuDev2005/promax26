"""Apply C++ loop repair to identical saved inputs/plans, with independent replay."""
import copy
import argparse
import csv
import json
import os
from run_snapshot import BENCH, ROOT
from stock_fuel_audit import neighbor, cost

def movement_fuel(data, plan):
    total=0
    for agent,actions in zip(data['day_info']['agents'],plan):
        if agent['kind']!=0: continue
        cell=agent['pos']
        for action in actions:
            if action>=0:
                total+=cost(data['config'],cell)[1]
                cell=neighbor(data['config'],cell,action)
    return total

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', default='reports/stock-fuel/LOOP_REPLAY_RESULTS.csv')
    parser.add_argument('--budget', type=int, default=3000)
    parser.add_argument('--report', help='Replay one saved match instead of the three screening runs')
    parser.add_argument('--tail-repair', action='store_true')
    args=parser.parse_args()
    rows=[]
    for seed in ((1,) if args.report else (1,2,3)):
        report=json.loads((ROOT/(args.report or f'reports/stock-fuel/baseline-3000ms-s{seed}.json')).read_text(encoding='utf-8'))
        data=json.loads((ROOT/'cases/master/32japan.snapshot.json').read_text(encoding='utf-8'))
        traffic=[]
        for day in report['days']:
            data['day_info']['agents']=day['start_agents']
            original=BENCH.trace(data,day['plan'],os.environ.copy())
            payload=copy.deepcopy(data)
            payload['replayPlan']=day['plan']
            payload['search']={'timeLimitMs':args.budget,'threads':1,'loopRepair':not args.tail_repair,
                'loopReinvest':not args.tail_repair,'tailRepair':args.tail_repair,
                'objectiveMode':'OFFICIAL_LEXICOGRAPHIC'}
            response,ms=BENCH.call(ROOT/'build-stock-fuel/udon_stock_fuel_runner.exe',payload,os.environ.copy())
            changed=BENCH.trace(data,response['plan'],os.environ.copy())
            a,b=original['frames'][-1],changed['frames'][-1]
            assert b['servings']>=a['servings']
            assert all(x['cell']==y['cell'] and x['fuel']<=y['fuel'] for x,y in zip(a['agents'],b['agents']))
            rows.append([seed,day['day'],a['servings'],b['servings'],
                response['diagnostics'].get('removed_loop_movement_ticks',0),
                sum(y['fuel']-x['fuel'] for x,y in zip(a['agents'],b['agents'])),ms,
                movement_fuel(data,day['plan'])-movement_fuel(data,response['plan'])])
            # Use original boundary states to isolate the effect on this exact plan.
            BENCH.advance(data,day['plan'],original,traffic)
            for road in data['day_info']['traffics']: road['status']=0
    output=ROOT/args.output
    with output.open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f)
        writer.writerow(['seed','day','before_udon','after_udon','removed_movement_ticks','end_fuel_gain','runtime_ms','movement_fuel_saved'])
        writer.writerows(rows)
    print(json.dumps({'plans':len(rows),'removed_movement_ticks':sum(r[4] for r in rows),
        'end_fuel_gain':sum(r[5] for r in rows),'udon_gain':sum(r[3]-r[2] for r in rows),
        'movement_fuel_saved':sum(r[7] for r in rows)}))

if __name__=='__main__': main()
