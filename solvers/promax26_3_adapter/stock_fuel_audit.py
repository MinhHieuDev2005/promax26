"""Replay saved plans and audit chronological shared stock; unknown intent stays unknown."""
import argparse
import copy
import csv
import json
import os
import heapq
from pathlib import Path
from run_snapshot import BENCH

def neighbor(config, cell, direction):
    width, height = config['map']['width'], config['map']['height']
    y,x = divmod(cell,width)
    dx = (0,1,1,1,0,-1) if y%2==0 else (-1,0,1,0,-1,-1)
    nx,ny = x+dx[direction], y+(-1,-1,0,1,1,0)[direction]
    if 0<=nx<width and 0<=ny<height and config['map']['cells'][ny][nx]!=3:
        return ny*width+nx
    return None

def cost(config, cell):
    terrain=config['map']['cells'][cell//config['map']['width']][cell%config['map']['width']]
    return (2,1,3)[terrain], 1 if terrain==0 else 2

def shortcut(config, source, target, blocked):
    queue=[(0,0,source,[])]
    best={source:(0,0)}
    while queue:
        elapsed,fuel,cell,path=heapq.heappop(queue)
        if (elapsed,fuel)!=best[cell]: continue
        if cell==target: return elapsed,fuel,path
        dt,df=cost(config,cell)
        for direction in range(6):
            dest=neighbor(config,cell,direction)
            if dest is None or dest==blocked: continue
            candidate=(elapsed+dt,fuel+df)
            if candidate<best.get(dest,(10**9,10**9)):
                best[dest]=candidate
                heapq.heappush(queue,(*candidate,dest,path+[direction]))
    return None

def counterfactual(data, plan, replay, row):
    """Prove a local shortcut with same suffix timing, score and boundary positions."""
    if row['actual_udon'] or row['tick']==1: return
    agent=row['patrol']
    actions=plan[agent]
    cell=data['day_info']['agents'][agent]['pos']
    boundaries=[(0,cell)]
    for action in actions:
        elapsed=boundaries[-1][0]
        if action<0: elapsed-=action
        else:
            elapsed+=cost(data['config'],cell)[0]
            cell=neighbor(data['config'],cell,action)
        boundaries.append((elapsed,cell))
    matches=[k for k,(tick,pos) in enumerate(boundaries) if tick==row['tick'] and pos==row['spot']]
    for k in matches:
        left,right=max(0,k-2),min(len(actions),k+2)
        begin,source=boundaries[left]
        end,target=boundaries[right]
        if source==row['spot'] or target==row['spot']: continue
        alternate=shortcut(data['config'],source,target,row['spot'])
        if not alternate or alternate[0]>=end-begin: continue
        duration,alternate_fuel,moves=alternate
        candidate=copy.deepcopy(plan)
        candidate[agent]=actions[:left]+moves+[-(end-begin-duration)]+actions[right:]
        try: changed=BENCH.trace(data,candidate,os.environ.copy())
        except RuntimeError: continue
        old,new=replay['frames'][-1],changed['frames'][-1]
        old_brands={s['brand'] for s in data['config']['spots'] if any(e['spot']==s['pos'] for e in replay['acquisitions'])}
        new_brands={s['brand'] for s in data['config']['spots'] if any(e['spot']==s['pos'] for e in changed['acquisitions'])}
        if not old_brands<=new_brands or new['servings']<old['servings']: continue
        if any(a['cell']!=b['cell'] or b['fuel']<a['fuel'] for a,b in zip(old['agents'],new['agents'])): continue
        row.update(avoidable_detour='proven_local_shortcut',necessary=False,
            wasted_steps=end-begin-duration,
            wasted_fuel=sum(cost(data['config'],boundaries[k][1])[1]
                for k in range(left,right) if actions[k]>=0)-alternate_fuel)
        return


def events(config, replay, day):
    stock = {s['pos']: s['stocks'] for s in config['spots']}
    acquired = {(x['step'], x['agent'], x['spot']) for x in replay['acquisitions']}
    seen = set()
    frames = replay['frames']
    result = []
    for before, after in zip(frames, frames[1:]):
        tick = after['step']
        for agent, (old, new) in enumerate(zip(before['agents'], after['agents'])):
            pos = new['cell']
            if new['type'] != 0 or pos not in stock:
                continue
            collected = int((tick, agent, pos) in acquired)
            stock_before = stock[pos]
            stock[pos] -= collected
            if stock[pos] < 0:
                raise AssertionError('negative shared stock')
            arrival = old['cell'] != pos or tick == 1
            if arrival or collected:
                result.append(dict(day=day, tick=tick, patrol=agent, spot=pos,
                    arrival_position=pos, planned_target='unknown',
                    stock_before=stock_before, stock_after=stock[pos],
                    actual_udon=collected, fuel_before_tick=old['fuel'],
                    fuel_after_tick=new['fuel'], repeat_visit=(agent,pos) in seen,
                    visit_class='productive' if collected else 'zero_yield_unclassified',
                    necessary='unknown', avoidable_detour='unproven',
                    wasted_steps='', wasted_fuel=''))
                seen.add((agent,pos))
    assert sum(x['actual_udon'] for x in result) == frames[-1]['servings']
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.snapshot.read_text(encoding='utf-8'))
    report = json.loads(args.report.read_text(encoding='utf-8'))
    rows = []
    traffic = []
    for day in report['days']:
        if 'plan' not in day:
            raise ValueError('Historical report has no plan; exact replay cannot be recovered from visits alone')
        data['day_info']['agents'] = day['start_agents']
        replay = BENCH.trace(data, day['plan'], os.environ.copy())
        daily=events(data['config'], replay, day['day'])
        for row in daily:
            counterfactual(data,day['plan'],replay,row)
        rows.extend(daily)
        assert replay['frames'][-1]['agents'] == day['end_agents']
        BENCH.advance(data, day['plan'], replay, traffic)
        for road in data['day_info']['traffics']:
            road['status'] = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'events': len(rows), 'collected': sum(r['actual_udon'] for r in rows),
        'zero_yield_unclassified': sum(not r['actual_udon'] for r in rows),
        'proven_local_shortcuts': sum(r['avoidable_detour']=='proven_local_shortcut' for r in rows),
        'wasted_steps': 'individual alternatives only; overlapping alternatives are not additive'}))

if __name__ == '__main__':
    main()
