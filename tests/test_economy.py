"""Seven v3 acceptance groups. Fixtures originate in the supplied JS reference."""
import copy
import json
import math
import random
from pathlib import Path
import sys
import subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import economy as E
from sim import simulate

CFG=E.load_config()
HERE=Path(__file__).parent


def flattened(r):
    return dict(netWorthDay7=r['nw'],buildingsOwned=r['tier'],levels=r['levels'],families=r['families'],incomePerDay=r['incDay'],
                taxPaid=r['tax'],gateDay=r['gateDay'],unlockDays=r['unlock'],contracts=r['contracts'],realEvents=r['events'],hourlyNetWorth=r['hourly'])


def test_deterministic_golden():
    expected=json.loads((HERE/'golden.deterministic.json').read_text())
    cfg=copy.deepcopy(CFG);cfg['global']['seed']=expected['classSeed'];cfg['profiles']=[expected['profile']]
    for t in cfg['tiers']: t['sigma']=0
    actual=flattened(simulate(cfg,expected['days'])[0])
    assert actual['netWorthDay7']==114157066
    assert actual=={key:expected[key] for key in actual}


def test_stochastic_shared_class_golden():
    expected=json.loads((HERE/'golden.stochastic.json').read_text())
    cfg=copy.deepcopy(CFG);cfg['profiles']=[b['profile'] for b in expected['profiles'].values()];cfg['global']['seed']=expected['classSeed']
    actual=simulate(cfg,expected['days'])
    assert len(actual)==4
    for result,want in zip(actual,expected['profiles'].values()):
        got=flattened(result)
        assert got=={key:want[key] for key in got},result['name']


def test_invariants_fuzz_100_configs():
    rnd=random.Random(7)
    for trial in range(100):
        cfg=copy.deepcopy(CFG);g=cfg['global'];g['growth']=rnd.uniform(1.01,1.3);g['maxLevel']=rnd.randint(20,55)
        g['whHours']=rnd.choice([.1,1,4,8]);g['gradLv']=rnd.randint(2,g['maxLevel']);g['autoContinue']=rnd.choice([0,1])
        cfg['tax']=[dict(above=rnd.randint(0,10000),rate=rnd.uniform(0,.8))]
        for t in cfg['tiers']:
            t.update(baseCost=rnd.randint(20,10000),rev=rnd.randint(1,300),timerH=rnd.uniform(.01,.1),sigma=rnd.uniform(0,.1))
        cfg['fun']['eventFirstH']=.01
        cfg['fun']['contractTargetH']=.01;cfg['fun']['contractWindowH']=.02
        st=E.new_state(cfg);st['cash']=100000;st['b'][0]['lv']=g['gradLv']
        cls=E.new_class(cfg,300);old_count=1
        for k in range(300):
            build=copy.deepcopy(st['build'])
            E.class_tick(cfg,cls,[st],k)
            E.player_tick(cfg,cls,st,k)
            assert st['cash']>=0 and E.net_worth(st)>=0 and math.isfinite(E.net_worth(st))
            assert len(st['b'])>=old_count and st['taxPaid']>=0
            assert all(b['lv']<=g['maxLevel'] for b in st['b'])
            if len(st['b'])>old_count: assert build and k>=build['t']
            old_count=len(st['b'])
            unlock=list(st['unlock'].values());assert all(b>a for a,b in zip(unlock,unlock[1:]))
            assert all(p>=0 for p in cls['pressure'])
            for ti in range(len(cfg['tiers'])): assert cfg['fun']['priceMin']<=E.class_price(cfg,cls,ti,k)<=cfg['fun']['priceMax']
            if k%30==0:
                for bi in range(len(st['b'])): E.sell_one(cfg,st,bi,E.class_price(cfg,cls,st['tierOf'][bi],k))
                E.auto_continue(cfg,st,k)
                if st['offers']: E.accept_contract(cfg,st,0,k)
        before=cls['pressure'][:];E.class_tick(cfg,cls,[],301)
        assert all(0<=b<=a for a,b in zip(before,cls['pressure']))


def test_replay_equivalence_with_json_restart():
    cfg=copy.deepcopy(CFG);cfg['tiers'][1]['timerH']=.2;cfg['global']['whHours']=.1
    a=E.new_state(cfg);a['b'][0]['lv']=cfg['global']['gradLv'];a['cash']=100000
    assert E.expand(cfg,a,1,0)['ok']
    E.offer_contracts(cfg,a,1);E.accept_contract(cfg,a,0,1)
    b=E.State(json.loads(json.dumps(a)))
    ca=E.new_class(cfg,1000);cb=E.new_class(cfg,1000)
    E.advance_class(cfg,ca,[a],0,1000)
    for start in range(0,1000,100):
        E.advance_class(cfg,cb,[b],start,start+100)
        b=E.State(json.loads(json.dumps(b)))
        cb=dict(E.new_class(cfg,1000),pressure=json.loads(json.dumps(cb['pressure'])),incomePerHour=cb['incomePerHour'],k=cb['k'])
    assert a==b
    assert ca['pressure']==cb['pressure'] and ca['incomePerHour']==cb['incomePerHour']


def test_frontier_retains_all_owned_buildings():
    cfg=copy.deepcopy(CFG);cfg['global']['autoContinue']=0
    st=E.new_state(cfg);st['cash']=100000;st['b'][0]['lv']=cfg['global']['gradLv']
    assert E.expand_options(cfg,st)==[1,2,3]
    assert not E.expand(cfg,st,4,0)['ok']
    assert E.expand(cfg,st,3,0)['ok'];assert E.expand_options(cfg,st)==[1,2,4]
    assert E.expand(cfg,st,2,0)['ok'];assert not E.expand(cfg,st,1,0)['ok']
    cls=E.new_class(cfg,5000);t=st['build']['t']
    E.class_tick(cfg,cls,[st],t-1);E.player_tick(cfg,cls,st,t-1);assert st['tierOf']==[0]
    E.class_tick(cfg,cls,[st],t);E.player_tick(cfg,cls,st,t);assert st['tierOf']==[0,3]
    assert st['pend']['0']>0 and st['pend']['1']>0
    previous=E.bRev(cfg,st,1);assert E.buy_level(cfg,st,1)['ok'];assert E.bRev(cfg,st,1)>previous
    assert E.revS(cfg,st)==sum(E.bRev(cfg,st,i) for i in range(2))


def test_contract_diversion_completion_tax_and_deadline():
    st=E.new_state(CFG);st['b'][0]['lv']=CFG['global']['maxLevel']
    st['contracts']=[dict(bi=0,target=100,reward=40,penalty=20,deadline=100,delivered=0)]
    produced={0:60};E.tick_contracts(CFG,st,0,produced);assert produced[0]==0 and st['contracts'][0]['delivered']==60
    rate=E.tax_rate(CFG,E.revS(CFG,st)*E.ticks_per_day(CFG));produced={0:60};E.tick_contracts(CFG,st,1,produced)
    assert produced[0]==20 and st['cash']==140-E.jsround(140*rate) and not st['contracts']
    assert st['cStats']['done']==1
    st['cash']=5;st['contracts']=[dict(bi=0,target=100,reward=40,penalty=20,deadline=2,delivered=0)]
    E.tick_contracts(CFG,st,2,{0:1});assert st['cash']==0 and st['cStats']['failed']==1
    # Completion takes priority on the exact deadline, matching the reference.
    st['contracts']=[dict(bi=0,target=1,reward=1,penalty=20,deadline=3,delivered=0)]
    E.tick_contracts(CFG,st,3,{0:1});assert st['cStats']['done']==2


def test_event_shape_family_targeting_and_false_rumour():
    cfg=copy.deepcopy(CFG)
    for t in cfg['tiers']:t['sigma']=0
    cfg['fun']['pressure']=0
    cls=E.new_class(cfg,1000);ramp=E.jsround(cfg['fun']['eventRampMin']*60/cfg['global']['tick']);decay=E.jsround(cfg['fun']['eventDecayMin']*60/cfg['global']['tick'])
    event=dict(rumourTick=0,startTick=20,family='F',mag=1.4,real=True,holdTicks=30);cls['ev']=[event]
    assert E.rumour_now(cfg,cls['ev'],1)==dict(family='F',up=True)
    for dt,mult in [(0,1),(ramp/2,1.2),(ramp,1.4),(ramp+30,1.4),(ramp+30+decay/2,1.2),(ramp+30+decay,1)]:
        assert math.isclose(E.class_price(cfg,cls,0,20+int(dt)),mult)
        assert E.class_price(cfg,cls,3,20+int(dt))==1
    event['real']=False
    assert E.rumour_now(cfg,cls['ev'],1)
    assert E.class_price(cfg,cls,0,20+ramp)==1


def test_rng_float32_and_api_against_javascript():
    script="""const E=require('./engine/economy-engine.reference.js'),cfg=require('./config/economy.v3.json');
const r=E.rng(0xffffffff), draws=Array.from({length:100},()=>r());const st=E.newState(cfg),cls=E.newClass(cfg,300);
for(let k=0;k<300;k++){E.classTick(cfg,cls,[st],k);E.playerTick(cfg,cls,st,k);}
st.cash=100000;E.buyLevel(cfg,st,0);E.buyAuto(cfg,st,0);const receipt=E.sellOne(cfg,st,0,E.classPrice(cfg,cls,0,299),true);
console.log(JSON.stringify({draws,price:Array.from(cls.streams[0].slice(0,100)),events:cls.ev,st,pressure:Array.from(cls.pressure),receipt}));"""
    expected=json.loads(subprocess.check_output(['node','-e',script],cwd=HERE.parent,text=True))
    r=E.rng(0xffffffff);assert [r() for _ in range(100)]==expected['draws']
    assert list(E.price_streams(CFG,100)[0])==expected['price']
    assert E.event_schedule(CFG,300)==expected['events']
    st=E.new_state(CFG);cls=E.new_class(CFG,300);E.advance_class(CFG,cls,[st],0,300)
    st['cash']=100000;E.buy_level(CFG,st,0);E.buy_auto(CFG,st,0);receipt=E.sell_one(CFG,st,0,E.class_price(CFG,cls,0,299),True)
    assert receipt==expected['receipt'];assert cls['pressure']==expected['pressure']
    for key in ('cash','b','tierOf','pend','book','taxPaid','contracts','offers','checklist','cStats'):
        assert st[key]==expected['st'][key],key
