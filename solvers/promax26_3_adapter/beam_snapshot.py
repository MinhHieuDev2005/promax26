"""Idle multi-day beam benchmark using the existing validated runner protocol."""
import argparse
import copy
import heapq
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from run_snapshot import BENCH, ROOT


def build_metric(config):
    """Return a conservative next-day joint patrol/supply serviceability metric."""
    width=config['map']['width']
    height=config['map']['height']
    cells=[value for row in config['map']['cells'] for value in row]
    spots=config['spots']
    sources={spot['pos'] for spot in spots}
    even=((-1,0),(-1,1),(0,1),(1,1),(1,0),(0,-1))
    odd=((-1,-1),(-1,0),(0,1),(1,0),(1,-1),(0,-1))

    def distances(source, fuel):
        result=[10**9]*(width*height)
        result[source]=0
        queue=[(0,source)]
        while queue:
            distance,pos=heapq.heappop(queue)
            if distance!=result[pos]: continue
            row,column=divmod(pos,width)
            for dr,dc in even if row%2==0 else odd:
                nr,nc=row+dr,column+dc
                if not (0<=nr<height and 0<=nc<width): continue
                target=nr*width+nc
                if cells[target]==3: continue
                cost=(1 if cells[pos]==0 else 2) if fuel else (1 if cells[pos]==2 else 2 if cells[pos]==0 else 3)
                candidate=distance+cost
                if candidate<result[target]:
                    result[target]=candidate
                    heapq.heappush(queue,(candidate,target))
        return result

    time_cache={source:distances(source,False) for source in sources}
    fuel_cache={source:distances(source,True) for source in sources}
    def from_source(source, cache, fuel):
        if source not in cache: cache[source]=distances(source,fuel)
        return cache[source]

    def metric(item):
        agents=item['days'][-1]['end_agents']
        patrols=[agent for agent in agents if agent['type']==0]
        supplies=[agent for agent in agents if agent['type']==1]
        horizon=config['daySteps'][min(len(item['days']),len(config['daySteps'])-1)]
        supply_time=from_source(supplies[0]['cell'],time_cache,False) if supplies else None
        reachable=[[] for _ in spots]
        serviceable=0
        useful_fuel=0
        rendezvous_sum=0
        brand_mask=0
        for patrol_index,patrol in enumerate(patrols):
            patrol_time=from_source(patrol['cell'],time_cache,False)
            patrol_fuel=from_source(patrol['cell'],fuel_cache,True)
            can_serve=False
            best_slack=0
            best_rendezvous=supply_time[patrol['cell']] if supply_time else horizon+1
            for spot_index,spot in enumerate(spots):
                travel=patrol_time[spot['pos']]
                fuel=patrol_fuel[spot['pos']]
                direct=fuel<=patrol['fuel'] and travel<=horizon
                rendezvous=supply_time[patrol['cell']] if supply_time else 10**9
                refilled=rendezvous+travel<=horizon and fuel<=80
                if not (direct or refilled): continue
                arrival=travel if direct else rendezvous+travel
                slack=max(0,(patrol['fuel']-fuel) if direct else 80-fuel)
                reachable[spot_index].append((arrival,-slack,patrol_index))
                can_serve=True
                best_slack=max(best_slack,slack)
            serviceable+=can_serve
            useful_fuel+=best_slack
            rendezvous_sum+=best_rendezvous

        # Finite stock is assigned once. Per-patrol capacity approximates how many
        # separated targets fit in the horizon; it is a bound, never official score.
        capacity=max(1,horizon//10)
        load=[0]*len(patrols)
        collected=0
        order=sorted(range(len(spots)),key=lambda i:(len(reachable[i]),-spots[i]['stocks']))
        for spot_index in order:
            if not reachable[spot_index]: continue
            brand_mask|=1<<spots[spot_index]['brand']
            for _ in range(spots[spot_index]['stocks']):
                choices=[edge for edge in reachable[spot_index] if load[edge[2]]<capacity]
                if not choices: break
                arrival,negative_slack,patrol_index=min(choices,key=lambda edge:
                    (load[edge[2]],edge[0],edge[1]))
                load[patrol_index]+=1
                collected+=1
        brands=brand_mask.bit_count()
        return (collected,brands,serviceable,useful_fuel,-rendezvous_sum)
    return metric


def dominates(left,right):
    return all(a>=b for a,b in zip(left,right)) and any(a>b for a,b in zip(left,right))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--budget',type=int,default=3000)
    parser.add_argument('--beam',type=int,default=3)
    parser.add_argument('--candidates',type=int,default=4)
    parser.add_argument('--initial-candidates',type=int)
    parser.add_argument('--threads',type=int,default=2)
    parser.add_argument('--joint-serviceability',action='store_true')
    parser.add_argument('--roles',default='0,0,0,0,1,0,0')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=json.loads(args.snapshot.read_text(encoding='utf-8'))
    roles=[int(x) for x in args.roles.split(',')]
    source['types']=roles
    for agent,kind in zip(source['day_info']['agents'],roles): agent['kind']=kind
    exe=args.exe.resolve()
    env=dict(os.environ,HEXUDON_THREADS=str(args.threads))
    beam=[{'data':source,'days':[],'traffic':[]}]
    serviceability=build_metric(source['config'])

    def expand(item,seed):
        data=copy.deepcopy(item['data'])
        data['search']={'timeLimitMs':args.budget,'randomSeed':seed,'threads':args.threads,
            'futureWeight':0.0,'crossMoves':7,'endSpotWeight':0.0,
            'objectiveMode':'OFFICIAL_LEXICOGRAPHIC'}
        response,wall=BENCH.call(exe,data,env,timeout=args.budget/1000+15)
        replay=BENCH.trace(data,response['plan'],env)
        frame=replay['frames'][-1]
        day=data['day_info']['day']
        record={'day':day,'seed':seed,'wall_ms':wall,'score':[
            len(set(data['history']['distinct_brands'])|
                {s['brand'] for s in data['config']['spots']
                 if any(a['spot']==s['pos'] for a in replay['acquisitions'])}),
            len({s['brand'] for s in data['config']['spots']
                 if any(a['spot']==s['pos'] for a in replay['acquisitions'])}),
            frame['servings']], 'plan':response['plan'],
            'start_agents':copy.deepcopy(data['day_info']['agents']),
            'end_agents':copy.deepcopy(frame['agents'])}
        traffic=item['traffic'][:]
        BENCH.advance(data,response['plan'],replay,traffic)
        for road in data['day_info']['traffics']: road['status']=0
        return {'data':data,'days':item['days']+[record],'traffic':traffic}

    total_days=len(source['config']['daySteps'])
    for day in range(total_days):
        jobs=[]
        candidate_count=args.initial_candidates if day==0 and args.initial_candidates else args.candidates
        with ThreadPoolExecutor(max_workers=max(1,min(len(beam)*candidate_count,8))) as pool:
            for index,item in enumerate(beam):
                for candidate in range(candidate_count):
                    seed=1+day*1000+index*candidate_count+candidate
                    jobs.append(pool.submit(expand,item,seed))
            expanded=[job.result() for job in jobs]
        # Exact official requirements first. Keep position diversity so high-fuel
        # copies of the same boundary do not consume the whole beam.
        full=[x for x in expanded if x['days'][-1]['score'][:2]==[24,24]]
        if full: expanded=full
        unique={}
        for item in expanded:
            key=tuple((a['cell'],a['fuel']) for a in item['days'][-1]['end_agents'])
            total=item['data']['history']['total_servings']
            if key not in unique or total>unique[key]['data']['history']['total_servings']:
                unique[key]=item
        expanded=list(unique.values())
        if args.joint_serviceability:
            for item in expanded:
                item['serviceability']=serviceability(item)
                item['rank']=(item['data']['history']['total_servings'],)+item['serviceability']
            pareto=[item for item in expanded if not any(
                dominates(other['rank'],item['rank']) for other in expanded if other is not item)]
            pareto.sort(key=lambda x:x['rank'],reverse=True)
            selected=[]
            while pareto and len(selected)<args.beam:
                if not selected: choice=pareto[0]
                else:
                    signatures=[tuple(a['cell'] for a in x['days'][-1]['end_agents']) for x in selected]
                    choice=max(pareto,key=lambda x:(min(sum(a!=b for a,b in zip(
                        tuple(agent['cell'] for agent in x['days'][-1]['end_agents']),signature))
                        for signature in signatures),x['rank']))
                selected.append(choice)
                pareto.remove(choice)
            if len(selected)<args.beam:
                rest=[item for item in sorted(expanded,key=lambda x:x['rank'],reverse=True)
                      if item not in selected]
                selected.extend(rest[:args.beam-len(selected)])
            beam=selected
            summary=[(x['data']['history']['total_servings'],x['serviceability']) for x in beam]
        else:
            expanded.sort(key=lambda x:(x['data']['history']['total_servings'],
                sum(a['fuel'] for a in x['days'][-1]['end_agents'] if a['type']==0)),reverse=True)
            beam=expanded[:args.beam]
            if len(expanded)>args.beam and args.beam>1:
                beam[-1]=max(expanded[args.beam-1:],key=lambda x:sum(
                    a['fuel'] for a in x['days'][-1]['end_agents'] if a['type']==0))
            summary=[(x['data']['history']['total_servings'],sum(
                a['fuel'] for a in x['days'][-1]['end_agents'] if a['type']==0)) for x in beam]
        print('BEAM',day,summary)
    best=max(beam,key=lambda x:(len(x['data']['history']['distinct_brands']),
        x['data']['history']['cumulative_daily_types'],x['data']['history']['total_servings']))
    result={'score':[len(best['data']['history']['distinct_brands']),
        best['data']['history']['cumulative_daily_types'],best['data']['history']['total_servings']],
        'beam':args.beam,'candidates':args.candidates,
        'initial_candidates':args.initial_candidates,'threads':args.threads,
        'budget_ms':args.budget,'exe':str(exe),'selection':
            'joint-serviceability-pareto' if args.joint_serviceability else 'total-fuel',
        'days':best['days']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(result['score'])


if __name__=='__main__': main()
