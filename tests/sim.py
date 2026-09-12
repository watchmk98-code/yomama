"""Simulator-only attendance, strategies, and contract decisions. Never imported by the server."""
import math
import economy as E


def buyLoop(cfg, st, tick):
    strat=st.get('strategy','optimizer')
    if strat=='optimizer':
        E.auto_continue(cfg,st,tick)
        return
    g=cfg['global']; expand_lv=40 if strat=='hoarder' else 8 if strat=='rusher' else g['gradLv']
    for _ in range(800):
        opts=[]
        for bi,b in enumerate(st['b']):
            t=cfg['tiers'][st['tierOf'][bi]]
            c=E.level_cost(cfg,st,bi)
            if c is not None:
                d=t['rev']*(b['lv']+1)*E.ms(cfg,b['lv']+1)*b['auto']*E.set_mult(cfg,st,bi)-E.bRev(cfg,st,bi)
                opts.append(dict(k='lvl',i=bi,c=c,d=d))
            if strat!='nohq':
                c=E.auto_cost(cfg,st,bi)
                if c is not None:
                    mult=g['a1Mult'] if b['auto']==1 else g['a2Mult']
                    opts.append(dict(k='auto',i=bi,c=c,d=E.bRev(cfg,st,bi)*(mult-1)))
        q=len(st['queue'])+bool(st['build'])
        if q<g['queueDepth'] and (q>0 or st['b'][-1]['lv']>=expand_lv):
            candidates=E.expand_options(cfg,st)
            if candidates:
                def score(i):
                    t=cfg['tiers'][i];n=sum(cfg['tiers'][ti]['family']==t['family'] for ti in st['tierOf'])
                    return t['rev']*(1+cfg['fun']['setFamilyPct']/100 if n>=2 and cfg['fun']['setBonus'] else 1)*(1+.02*n)/t['baseCost']
                if strat=='random': pick=candidates[math.floor(st.random()*len(candidates))]
                elif strat=='specialist': pick=next((i for i in candidates if cfg['tiers'][i]['family']==cfg['tiers'][st['tierOf'][0]]['family']),candidates[0])
                else: pick=max(candidates,key=score)
                opts.append(dict(k='expand',i=pick,c=cfg['tiers'][pick]['baseCost'],d=cfg['tiers'][pick]['rev']))
        aff=[o for o in opts if o['c']<=st['cash']]
        if not aff: break
        if strat=='biggest': best=max(aff,key=lambda o:o['c'])
        elif strat=='random': best=aff[math.floor(st.random()*len(aff))]
        else: best=next((o for o in aff if o['k']=='expand'),None) or max(aff,key=lambda o:o['d']/o['c'])
        i=best['i'];st['cash']-=best['c'];st['book']+=best['c']
        if best['k']=='lvl': st['b'][i]['lv']+=1
        elif best['k']=='auto': st['b'][i]['auto']=g['a1Mult'] if st['b'][i]['auto']==1 else g['a1Mult']*g['a2Mult']
        elif st['build'] is None: st['build']=dict(t=tick+E.jsround(cfg['tiers'][i]['timerH']*3600/g['tick']),i=i)
        else: st['queue'].append(i)


def considerContracts(cfg, st, k):
    f=cfg['fun']
    if not f['contracts'] or not st['offers']: return
    while len(st['contracts'])<f['contractSlots'] and st['offers']:
        o=max(st['offers'],key=lambda o:o['reward']);st['offers'].remove(o)
        fill=o['target']/(E.bRev(cfg,st,o['bi']) or 1)
        ok=st.random()<.5 if st['strategy']=='random' else fill<(o['deadline']-k)*.7
        if ok: st['contracts'].append(dict(o,delivered=0));st['cStats']['accepted']+=1


def simulate(cfg, days):
    g=cfg['global'];day=E.ticks_per_day(cfg);hour=E.ticks_per_hour(cfg);total=day*days
    cls=E.new_class(cfg,total);players=[]
    for pi,p in enumerate(cfg['profiles']):
        ar=E.rng(g['seed']*7919+pi*31+1);tr=E.rng(g['seed']*104729+pi*17+3)
        def to_tick(x):
            parts=str(x).split(':');return E.jsround((int(parts[0] or 0)*3600+(int(parts[1]) if len(parts)>1 else 0)*60)/g['tick'])
        fixed=[x.strip() for x in str(p['logins']).split(',') if x.strip()]
        random_times=p.get('randomTimes',0);n=max(1,int(fixed[0]) or 1) if random_times else len(fixed)
        w0=to_tick(p.get('windowStart','07:00'));w1=to_tick(p.get('windowEnd','23:00'))
        logins=[];present=[]
        for d in range(days):
            L=sorted(w0+math.floor(tr()*max(1,w1-w0)) for _ in range(n)) if random_times else list(map(to_tick,fixed))
            logins.append(L);present.append([ar()<p.get('attendance',1) for _ in L])
        st=E.new_state(cfg,seed=g['seed']*48611+pi*7+5)
        st['strategy']=p.get('strategy','optimizer');st.on_continue=buyLoop
        players.append(dict(p=p,st=st,logins=logins,present=present,slen=E.jsround(p['sessionMin']*60/g['tick']),hourly=[],queuedMax=0))
    for k in range(total):
        E.class_tick(cfg,cls,[x['st'] for x in players],k)
        for x in players:
            st=x['st'];E.player_tick(cfg,cls,st,k)
            tod=k%day;di=k//day
            active=any(x['present'][di][li] and s<=tod<s+x['slen'] for li,s in enumerate(x['logins'][di]))
            if active:
                E.on_login(cfg,st,k)
                E.sell_all(cfg,st,lambda ti:E.class_price(cfg,cls,ti,k),k,True)
                considerContracts(cfg,st,k);buyLoop(cfg,st,k)
                x['queuedMax']=max(x['queuedMax'],len(st['queue'])+bool(st['build']))
            if k%hour==0: x['hourly'].append(E.net_worth(st))
    result=[]
    for x in players:
        st=x['st'];families={}
        for ti in st['tierOf']:
            fam=cfg['tiers'][ti]['family'];families[fam]=families.get(fam,0)+1
        result.append(dict(name=x['p']['name'],strategy=st['strategy'],nw=E.net_worth(st),tier=len(st['b']),lv=st['b'][-1]['lv'],
                           levels=[b['lv'] for b in st['b']],families=families,incDay=E.revS(cfg,st)*day,tax=st['taxPaid'],
                           unlock=st['unlock'],hourly=x['hourly'],gateDay=st['gateDay'],queuedMax=x['queuedMax'],
                           contracts=st['cStats'],events=sum(e['real'] for e in cls['ev'])))
    return result
