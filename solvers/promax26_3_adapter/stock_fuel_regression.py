"""Cross-check stock, transit, fuel and carryover against both local simulators."""
import copy
import json
import os
import random
from pathlib import Path
from run_snapshot import BENCH, ROOT

EXE = ROOT / 'build-stock-fuel/udon_stock_fuel_runner.exe'
BASE = json.loads((ROOT/'cases/master/32japan.snapshot.json').read_text(encoding='utf-8'))

def case(stock=1, steps=4):
    p = copy.deepcopy(BASE)
    p['config'].update(map={'width': 32, 'height': 32, 'cells': [[0]*32 for _ in range(32)]},
        agents=[0,0,8,8,8,8,8], spots=[{'pos':1,'brand':0,'stocks':stock}],
        daySteps=[steps,steps], daySeconds=[60,60])
    p['types'] = [0,0,1,1,1,1,1]
    p['day_info'] = {'day':0,'agents':[{'kind':k,'pos':pos,'fuel':80}
        for k,pos in zip(p['types'],p['config']['agents'])], 'others':[], 'traffics':[]}
    p['history'] = {'distinct_brands':[], 'submitted_actions':[], 'cumulative_daily_types':0,'total_servings':0}
    p['search'] = {'timeLimitMs':100,'threads':1,'randomSeed':1}
    return p

def check(p, plan, balls):
    actual = BENCH.trace(p, plan, os.environ.copy())
    assert actual['frames'][-1]['servings'] == balls, actual
    q = copy.deepcopy(p)
    q['replayPlan'] = plan
    other,_ = BENCH.call(EXE,q,os.environ.copy())
    assert other['diagnostics']['total_udon_today'] == balls
    return actual

def main():
    p = case()
    plan = [[2,-2],[2,-2]] + [[-4]]*5
    a = check(p,plan,1)
    assert a['acquisitions'] == [{'step':2,'agent':0,'spot':1}]
    check(case(2),plan,2)
    p = case(2,6)
    check(p,[[2,5,2],[-6]]+[[-6]]*5,1)
    p = case()
    p['day_info']['agents'][0]['pos'] = 1
    p['config']['spots'].append({'pos':2,'brand':1,'stocks':1})
    # Patrol 1 must pass the depleted spot 1 to collect spot 2.
    a = check(p,[[-4],[2,2]]+[[-4]]*5,2)
    assert any(e['agent']==1 and e['spot']==2 for e in a['acquisitions'])
    BENCH.advance(p,[[-4],[2,2]]+[[-4]]*5,a,[])
    assert p['day_info']['agents'][1]['fuel'] == 78
    assert p['day_info']['agents'][1]['pos'] == 2
    check(p,[[-4]]*7,2)  # Stock replenishes; positions and fuel persist.
    p = case()
    p['day_info']['agents'][2]['pos'] = 1
    a = check(p,[[2,-2],[-4]]+[[-4]]*5,1)
    assert a['frames'][-1]['agents'][0]['fuel']==p['config']['fuelLimits']
    p = case()
    response,_ = BENCH.call(EXE,p,os.environ.copy(),timeout=5)
    BENCH.trace(p,response['plan'],os.environ.copy())
    for settings in ({'marginalStock':True},
                     {'actualRuin':True,'threads':2,'crossMoves':7},
                     {'boundarySelect':True,'threads':2},
                     {'actualRuin':True,'boundarySelect':True,'threads':2,'crossMoves':7},
                     {'mobileForecast':True,'futureWeight':0.2},
                     {'marginalStock':True,'mobileForecast':True,'futureWeight':0.2}):
        trial=copy.deepcopy(p)
        trial['search'].update(settings)
        response,_=BENCH.call(EXE,trial,os.environ.copy(),timeout=5)
        verified=BENCH.trace(trial,response['plan'],os.environ.copy())
        assert verified['frames'][-1]['servings']==response['diagnostics']['total_udon_today']
    # Full simulator agreement on random one-dimensional routes, including waits.
    generator=random.Random(1701)
    for _ in range(30):
        p=case(generator.randint(1,3),12)
        plan=[]
        for agent in range(7):
            if agent>=2:
                plan.append([-12]); continue
            cell=0
            route=[]
            for step in range(6):
                action=generator.choice([2,-2] if cell==0 else [2,5,-2])
                route.append(action)
                if action>=0: cell+=1 if action==2 else -1
            plan.append(route)
        actual=BENCH.trace(p,plan,os.environ.copy())
        check(p,plan,actual['frames'][-1]['servings'])
    p=case(1,8)
    p['replayPlan']=[[2,2,5,-2],[-8]]+[[-8]]*5
    p['search']['loopRepair']=True
    response,_=BENCH.call(EXE,p,os.environ.copy())
    assert response['diagnostics']['removed_loop_movement_ticks']>=4
    fixed=BENCH.trace(p,response['plan'],os.environ.copy())
    assert fixed['frames'][-1]['servings']==1
    assert fixed['frames'][-1]['agents'][0]['fuel']==79
    # Reinvest an idle window: stock 2, second patrol has already collected;
    # patrol 0 can collect the remaining serving and return to its supply.
    p=case(2,8)
    p['day_info']['agents'][1]['pos']=1
    p['day_info']['agents'][2]['pos']=0
    p['replayPlan']=[[-8] for _ in range(7)]
    p['search'].update(loopRepair=True,loopReinvest=True,timeLimitMs=55000)
    before=BENCH.trace(p,p['replayPlan'],os.environ.copy())
    response,_=BENCH.call(EXE,p,os.environ.copy())
    after=BENCH.trace(p,response['plan'],os.environ.copy())
    assert before['frames'][-1]['servings']==1
    assert after['frames'][-1]['servings']==2
    assert all(x['cell']==y['cell'] and y['fuel']>=x['fuel']
        for x,y in zip(before['frames'][-1]['agents'],after['frames'][-1]['agents']))
    print('PASS: single/multiple stock, duplicate, necessary transit, carryover, refuel, full simulator agreement, low-budget output')

if __name__=='__main__': main()
