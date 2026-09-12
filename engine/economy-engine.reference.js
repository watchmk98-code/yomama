/* YOMAMA Part 1 — reference economy engine v3 (hoarding + fun layer)
 * EXTRACTED VERBATIM from yomama_sim_lab.html (functions rng .. simulate) plus a server-facing API.
 * Node: const E=require('./economy-engine.reference.js'); Browser: window.YomamaEconomy.
 * All money whole YM; tick = cfg.global.tick seconds. Port every Math.round exactly where it appears.
 */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.YomamaEconomy=factory();})(typeof self!=='undefined'?self:this,function(){
const FAMILIES={F:{name:'Food',bandMin:0.90,bandMax:1.10,premium:1.00,depth:5},I:{name:'Industry',bandMin:0.80,bandMax:1.25,premium:1.05,depth:2},E:{name:'Energy/Tech',bandMin:0.70,bandMax:1.40,premium:1.10,depth:1}};
function rng(seed){let s=seed>>>0||1;return()=>{s^=s<<13;s>>>=0;s^=s>>>17;s^=s<<5;s>>>=0;return s/4294967296}}
function gauss(r){let u=0,v=0;while(u===0)u=r();while(v===0)v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v)}
const famOf=(cfg,i)=>FAMILIES[cfg.tiers[i].family||'F'];
function priceStreams(cfg,ticks){ // base multiplier per tier (before events/pressure), clamped to the FAMILY band
  const g=cfg.global,out=[];
  cfg.tiers.forEach((t,i)=>{const F=famOf(cfg,i),r=rng(g.seed*1000+i+1);let m=1;const a=new Float32Array(ticks);
    for(let k=0;k<ticks;k++){m+=g.theta*(1-m)+t.sigma*gauss(r);m=Math.min(F.bandMax,Math.max(F.bandMin,m));a[k]=m}
    out.push(a)});
  return out;
}
/* ---- news events (class-wide): schedule = [{rumourTick, startTick, family, mag, real}] ---- */
function eventSchedule(cfg,ticks){
  const g=cfg.global,f=cfg.fun,HOUR=Math.round(3600/g.tick);if(!f.events)return[];
  const r=rng(g.seed*7777+13),ev=[];let t=Math.round(HOUR*2);
  while(t<ticks){const fam=['F','I','E'][Math.floor(r()*3)];const up=r()<0.5;const mag=up?1+(f.eventMagUp-1)*(0.6+0.4*r()):1-(1-f.eventMagDown)*(0.6+0.4*r());
    ev.push({rumourTick:t-Math.round(f.rumourLeadMin*60/g.tick),startTick:t,family:fam,mag,real:r()<f.rumourTruth,holdTicks:Math.round(f.eventHoldMin*60/g.tick)});
    t+=Math.round(HOUR*f.eventEveryH*(0.7+0.6*r()));}
  return ev;
}
function eventMult(cfg,ev,fam,k){ // multiplier from active events on a family at tick k
  const g=cfg.global,ramp=Math.round(300/g.tick),decay=Math.round(1800/g.tick);let m=1;
  for(const e of ev){if(!e.real||e.family!==fam)continue;const dt=k-e.startTick;if(dt<0||dt>ramp+e.holdTicks+decay)continue;
    let w=1;if(dt<ramp)w=dt/ramp;else if(dt>ramp+e.holdTicks)w=1-(dt-ramp-e.holdTicks)/decay;m*=1+(e.mag-1)*w}
  return m;
}
function rumourNow(cfg,ev,k){ // {family, up} if a rumour is active (before the event starts)
  for(const e of ev){if(k>=e.rumourTick&&k<e.startTick)return{family:e.family,up:e.mag>1}}return null;
}
function ms(cfg,L){let m=1;for(const x of cfg.milestones)if(L>=x.lv)m*=x.mult;return m}
function msMult(cfg,L){return ms(cfg,L)}
/* ---- set bonuses ---- */
function setMult(cfg,st,bi){const f=cfg.fun;if(!f||!f.setBonus)return 1;const t=cfg.tiers[st.tierOf[bi]];let m=1;
  const famCount=st.tierOf.reduce((n,ti)=>n+(cfg.tiers[ti].family===t.family?1:0),0);if(famCount>=3)m*=1+f.setFamilyPct/100;
  const rowCount=st.tierOf.reduce((n,ti)=>n+(cfg.tiers[ti].row===t.row?1:0),0);if(rowCount>=3)m*=1+f.setRowPct/100;return m}
function bRev(cfg,st,bi){const b=st.b[bi];return Math.round(cfg.tiers[st.tierOf[bi]].rev*b.lv*ms(cfg,b.lv)*b.auto*setMult(cfg,st,bi))}
function revS(cfg,st){let r=0;for(let i=0;i<st.b.length;i++)r+=bRev(cfg,st,i);return r}
function taxRate(cfg,y){const b=[{above:0,rate:0},...cfg.tax].sort((a,c)=>a.above-c.above);let tx=0;
  for(let i=1;i<b.length;i++){const lo=b[i-1].above,rate=b[i-1].rate,hi=b[i].above;if(y>lo)tx+=(Math.min(y,hi)-lo)*rate}
  const last=b[b.length-1];if(y>last.above)tx+=(y-last.above)*last.rate;return y>0?tx/y:0}
function ticksPerDay(cfg){return Math.round(86400/cfg.global.tick)}
function net(cfg,st,gross){const r=taxRate(cfg,revS(cfg,st)*ticksPerDay(cfg));const tx=Math.round(gross*r);st.taxPaid+=tx;return Math.round(gross)-tx}
function tierCostMult(st){return st.rb.cost}
/* ---- which buildings can be bought next (grid): any unowned in current row, or first of next row once you own >=1 in this row ---- */
function expandOptions(cfg,st){const owned=new Set(st.tierOf.concat(st.queue,st.build?[st.build.i]:[]));const opts=[];const N=cfg.global.frontier||3;
  for(let i=0;i<cfg.tiers.length&&opts.length<N;i++)if(!owned.has(i))opts.push(i);return opts}
function buyLoop(cfg,st,tick){
  const g=cfg.global, strat=st.strategy||'optimizer';
  const expandLv = strat==='hoarder'?40 : strat==='rusher'?8 : g.gradLv;
  for(let guard=0;guard<800;guard++){
    const opts=[],cm=tierCostMult(st);
    for(let i=0;i<st.b.length;i++){const b=st.b[i],t=cfg.tiers[st.tierOf[i]];
      if(b.lv<(g.maxLevel||200)){const c=Math.round(t.baseCost*Math.pow(g.growth,b.lv)*cm);const d=t.rev*(b.lv+1)*ms(cfg,b.lv+1)*b.auto*setMult(cfg,st,i)-bRev(cfg,st,i);opts.push({k:'lvl',i,c,d})}
      if(strat!=='nohq'){
        if(b.auto===1)opts.push({k:'a1',i,c:Math.round(g.a1Cost*t.baseCost*cm),d:bRev(cfg,st,i)*(g.a1Mult-1)});
        else if(b.auto===g.a1Mult&&(!g.a2NeedsNextTier||i<st.b.length-1))opts.push({k:'a2',i,c:Math.round(g.a2Cost*t.baseCost*cm),d:bRev(cfg,st,i)*(g.a2Mult-1)});
      }
    }
    const qLen=st.queue.length+(st.build!==null?1:0);
    if(qLen<g.queueDepth&&(qLen>0||st.b[st.b.length-1].lv>=expandLv)){
      const cands=expandOptions(cfg,st);
      // pick family: specialist keeps its main family; optimizer = highest revenue incl. set progress; others random
      let pick=null;
      if(cands.length){
        const score=i=>{const t=cfg.tiers[i];const famCount=st.tierOf.filter(ti=>cfg.tiers[ti].family===t.family).length;return t.rev*(famCount>=2&&cfg.fun.setBonus?1+cfg.fun.setFamilyPct/100:1)*(1+0.02*famCount)/t.baseCost};  // value per YM
        if(strat==='random')pick=cands[Math.floor(st.srng()*cands.length)];
        else if(strat==='specialist'){const fam=cfg.tiers[st.tierOf[0]].family;pick=cands.find(i=>cfg.tiers[i].family===fam)??cands[0]}
        else pick=cands.reduce((a,b)=>score(b)>score(a)?b:a);
        opts.push({k:'expand',i:pick,c:Math.round(cfg.tiers[pick].baseCost*cm),d:cfg.tiers[pick].rev});
      }
    }
    const aff=opts.filter(o=>o.c<=st.cash);if(!aff.length)break;
    let best;const ex=aff.find(o=>o.k==='expand');
    if(strat==='biggest')best=aff.reduce((a,b)=>b.c>a.c?b:a);
    else if(strat==='random')best=aff[Math.floor(st.srng()*aff.length)];
    else best=ex||aff.reduce((a,b)=>(b.d/b.c>a.d/a.c?b:a));
    st.cash-=best.c;st.book+=best.c;
    if(best.k==='lvl')st.b[best.i].lv++;
    else if(best.k==='a1')st.b[best.i].auto=g.a1Mult;
    else if(best.k==='a2')st.b[best.i].auto=g.a1Mult*g.a2Mult;
    else if(best.k==='expand'){const timer=Math.round(cfg.tiers[best.i].timerH*3600/g.tick);if(st.build===null)st.build={t:tick+timer,i:best.i};else st.queue.push(best.i)}
  }
}
function finishBuild(cfg,st,k,DAY){
  const g=cfg.global;const i=st.build.i;
  // buildings are indexed by tier index: keep st.b sparse-safe by storing at position len and mapping index -> tier
  st.b.push({lv:1,auto:1,tier:i});st.tierOf.push(i);st.build=null;st.unlock[st.b.length-1]=k/DAY;
  if(st.gateDay===null&&st.b.length>=g.gateTier)st.gateDay=k/DAY;
  if(st.queue.length){const j=st.queue.shift();st.build={t:k+Math.round(cfg.tiers[j].timerH*3600/g.tick),i:j}}
  else if(g.autoContinue){ sellAll(cfg,st,null,k,false); buyLoop(cfg,st,k) }
}
/* ---- contracts ---- */
function offerContracts(cfg,st,k,DAY){const f=cfg.fun;if(!f.contracts)return;st.offers=[];
  for(let n=0;n<3;n++){const bi=Math.floor(st.srng()*st.b.length);const rate=bRev(cfg,st,bi);if(rate<=0)continue;
    const hours=f.contractTargetH*(0.6+0.8*st.srng());const target=Math.round(rate*hours*240);const rew=f.contractRewardPct*(0.7+0.6*st.srng())/100;
    st.offers.push({bi,target,reward:Math.round(target*rew),penalty:Math.round(target*rew*f.contractPenaltyPct/f.contractRewardPct),deadline:k+Math.round(f.contractWindowH*3600/cfg.global.tick)})}}
function considerContracts(cfg,st,k){const f=cfg.fun;if(!f.contracts||!st.offers)return;const strat=st.strategy;
  while(st.contracts.length<f.contractSlots&&st.offers.length){
    const o=st.offers.reduce((a,b)=>b.reward>a.reward?b:a);st.offers=st.offers.filter(x=>x!==o);
    const rate=bRev(cfg,st,o.bi)||1;const fillTicks=o.target/rate;const window=o.deadline-k;
    const ok= strat==='random'? st.srng()<0.5 : fillTicks<window*0.7;
    if(ok){st.contracts.push({...o,delivered:0});st.cStats.accepted++}
  }}
function tickContracts(cfg,st,k,produced){ // produced: map bi -> YM produced this tick; contracts take goods first
  for(const c of st.contracts){const p=produced[c.bi]||0;const take=Math.min(p,c.target-c.delivered);if(take>0){c.delivered+=take;produced[c.bi]=p-take}}
  for(const c of st.contracts.slice()){
    if(c.delivered>=c.target){st.cash+=net(cfg,st,c.target+c.reward);st.cStats.done++;st.cStats.net+=c.reward;st.contracts.splice(st.contracts.indexOf(c),1)}
    else if(k>=c.deadline){st.cash=Math.max(0,st.cash-c.penalty);st.cStats.failed++;st.cStats.net-=c.penalty;st.contracts.splice(st.contracts.indexOf(c),1)}
  }}
/* ---- selling (per building goods pool), premium sale, pressure, rumour-aware holds ---- */
function sellAll(cfg,st,mk,k,manual){ // mk: (tierIndex)->multiplier or null for fair value
  const f=cfg.fun;
  for(let bi=0;bi<st.b.length;bi++){const v=st.pend[bi]||0;if(v<=0)continue;const ti=st.tierOf[bi];
    if(manual&&f.botsReact&&st.rumour&&st.rumour.family===cfg.tiers[ti].family&&st.rumour.up)continue; // hold for the spike
    const m=mk?mk(ti):1;const gross=Math.round(v*m*(manual?1+f.premiumSalePct/100:1));
    st.cash+=net(cfg,st,gross);st.pend[bi]=0;if(st.onSold)st.onSold(ti,v)}
}
function simulate(cfg,days){
  const g=cfg.global,f=cfg.fun||{},TICK=g.tick,DAY=Math.round(86400/TICK),T=DAY*days,HOUR=Math.round(3600/TICK);
  const streams=priceStreams(cfg,T),ev=eventSchedule(cfg,T);
  const pressure=new Float64Array(cfg.tiers.length);const pDecay=f.pressure?Math.pow(0.5,1/(f.pressureHalfLifeMin*60/TICK)):1;
  let classIncomePerHour=1;
  const priceAt=(ti,k)=>{const fam=cfg.tiers[ti].family;let m=streams[ti][k]*eventMult(cfg,ev,fam,k);if(f.pressure){const depth=FAMILIES[fam].depth*classIncomePerHour;m-=Math.min(0.3,pressure[ti]/Math.max(1,depth))}return Math.max(0.4,Math.min(2.0,m))};
  const P=cfg.profiles.map((p,pi)=>{
    const att=p.attendance??1,ar=rng(g.seed*7919+pi*31+1);
    const toTick=x=>{const[h,m]=String(x).split(':').map(Number);return Math.round(((h||0)*3600+(m||0)*60)/TICK)};
    const fixed=String(p.logins).split(',').map(x=>x.trim()).filter(Boolean);
    const isRandom=!!(p.randomTimes??0), nLogins=isRandom?Math.max(1,parseInt(fixed[0])||1):fixed.length;
    const w0=toTick(p.windowStart??'07:00'), w1=toTick(p.windowEnd??'23:00');const tr=rng(g.seed*104729+pi*17+3);
    const dayLogins=[],present=[];
    for(let d=0;d<days;d++){const L=isRandom?Array.from({length:nLogins},()=>w0+Math.floor(tr()*Math.max(1,w1-w0))).sort((a,b)=>a-b):fixed.map(toTick);dayLogins.push(L);present.push(L.map(()=>ar()<att))}
    const st={strategy:p.strategy||'optimizer',srng:rng(g.seed*48611+pi*7+5),cash:0,b:[{lv:1,auto:1,tier:0}],tierOf:[0],pend:{},book:cfg.tiers[0].baseCost,build:null,queue:[],taxPaid:0,unlock:{0:0},hourly:[],gateDay:null,lastLogin:0,catchupUntil:-1,rb:{cost:1,inc:1},queuedMax:0,contracts:[],offers:null,cStats:{accepted:0,done:0,failed:0,net:0},rumour:null,heldForRumour:0};
    st.onSold=(ti,v)=>{if(f.pressure)pressure[ti]+=v};
    return {p,dayLogins,sLen:Math.round(p.sessionMin*60/TICK),present,st};
  });
  for(let k=0;k<T;k++){
    if(f.pressure)for(let i=0;i<pressure.length;i++)pressure[i]*=pDecay;
    if(k%HOUR===0){classIncomePerHour=Math.max(1,P.reduce((a,x)=>a+revS(cfg,x.st),0)*HOUR)}
    const rum=rumourNow(cfg,ev,k);
    for(const x of P){const st=x.st;st.rumour=rum;
      if(st.build!==null&&k>=st.build.t)finishBuild(cfg,st,k,DAY);
      if(f.contracts&&k%DAY===0)offerContracts(cfg,st,k,DAY);
      const total=revS(cfg,st);const boost=k<st.catchupUntil?g.catchupMult:1;const produced={};
      for(let bi=0;bi<st.b.length;bi++){produced[bi]=Math.round(bRev(cfg,st,bi)*st.rb.inc*boost)}
      if(f.contracts)tickContracts(cfg,st,k,produced);
      const cap=total*g.whHours*HOUR+1;
      for(let bi=0;bi<st.b.length;bi++){st.pend[bi]=(st.pend[bi]||0)+produced[bi];const capB=Math.round(cap*(total?bRev(cfg,st,bi)/total:1))+1;
        if(st.pend[bi]>capB){const ov=st.pend[bi]-capB;st.pend[bi]=capB;const ti=st.tierOf[bi];st.cash+=net(cfg,st,Math.round(ov*priceAt(ti,k)*(1-g.overflowDisc)));st.onSold(ti,ov)}}
      const tod=k%DAY,dayIdx=Math.floor(k/DAY);
      const inSession=x.dayLogins[dayIdx].some((s0,li)=>x.present[dayIdx][li]&&tod>=s0&&tod<s0+x.sLen);
      if(inSession){
        if(k-st.lastLogin>=g.catchupAbsenceH*HOUR&&st.lastLogin>0)st.catchupUntil=k+Math.round(g.catchupHours*HOUR);
        st.lastLogin=k;
        sellAll(cfg,st,ti=>priceAt(ti,k),k,true);
        if(f.contracts)considerContracts(cfg,st,k);
        buyLoop(cfg,st,k);
        st.queuedMax=Math.max(st.queuedMax,st.queue.length+(st.build!==null?1:0));
      }
      if(k%HOUR===0)st.hourly.push(st.cash+Object.values(st.pend).reduce((a,b)=>a+b,0)+st.book);
    }
  }
  return P.map(x=>{const st=x.st;if(st.gateDay===null&&st.b.length>=g.gateTier)st.gateDay=days;
    const fams={};st.tierOf.forEach(ti=>{const fm=cfg.tiers[ti].family;fams[fm]=(fams[fm]||0)+1});
    return {name:x.p.name,strategy:st.strategy,nw:st.cash+Object.values(st.pend).reduce((a,b)=>a+b,0)+st.book,tier:st.b.length,lv:st.b[st.b.length-1].lv,levels:st.b.map(b=>b.lv),families:fams,incDay:revS(cfg,st)*ticksPerDay(cfg),tax:st.taxPaid,unlock:st.unlock,hourly:st.hourly,gateDay:st.gateDay,queuedMax:st.queuedMax,contracts:st.cStats,events:ev.filter(e=>e.real).length}});
}


/* ================= SERVER-FACING API (explicit player actions; same rules as the bot) ================= */
function newState(cfg){return {strategy:'player',srng:rng(1),cash:0,b:[{lv:1,auto:1,tier:0}],tierOf:[0],pend:{},book:cfg.tiers[0].baseCost,build:null,queue:[],taxPaid:0,unlock:{0:0},gateDay:null,lastLogin:0,catchupUntil:-1,rb:{cost:1,inc:1},contracts:[],offers:null,cStats:{accepted:0,done:0,failed:0,net:0},rumour:null,checklist:{lv25:false,auto:false,goodSales:0,quiz:false},keepPercent:null,onSold:null}}
function levelCost(cfg,st,bi){const g=cfg.global,b=st.b[bi];if(b.lv>=(g.maxLevel||200))return null;return Math.round(cfg.tiers[st.tierOf[bi]].baseCost*Math.pow(g.growth,b.lv))}
function autoCost(cfg,st,bi){const g=cfg.global,b=st.b[bi],base=cfg.tiers[st.tierOf[bi]].baseCost;if(b.auto===1)return Math.round(g.a1Cost*base);if(b.auto===g.a1Mult){if(g.a2NeedsNextTier&&bi>=st.b.length-1)return null;return Math.round(g.a2Cost*base)}return null}
function buyLevel(cfg,st,bi){const c=levelCost(cfg,st,bi);if(c===null)return{ok:false,why:'max level'};if(st.cash<c)return{ok:false,why:'need '+c+' YM'};st.cash-=c;st.book+=c;st.b[bi].lv++;if(st.b[bi].lv>=25)st.checklist.lv25=true;return{ok:true,cost:c}}
function buyAuto(cfg,st,bi){const c=autoCost(cfg,st,bi);if(c===null)return{ok:false,why:'not available'};if(st.cash<c)return{ok:false,why:'need '+c+' YM'};st.cash-=c;st.book+=c;st.b[bi].auto=st.b[bi].auto===1?cfg.global.a1Mult:cfg.global.a1Mult*cfg.global.a2Mult;st.checklist.auto=true;return{ok:true,cost:c}}
function canExpand(cfg,st,ti){const g=cfg.global,q=st.queue.length+(st.build?1:0);if(q>=g.queueDepth)return{ok:false,why:'build queue full'};if(q===0&&st.b[st.b.length-1].lv<g.gradLv)return{ok:false,why:'newest building must be level '+g.gradLv};const opts=expandOptions(cfg,st);if(!opts.includes(ti))return{ok:false,why:'not on the frontier',frontier:opts};const cost=cfg.tiers[ti].baseCost;if(st.cash<cost)return{ok:false,why:'need '+cost+' YM'};return{ok:true,cost}}
function expand(cfg,st,ti,tick){const ok=canExpand(cfg,st,ti);if(!ok.ok)return ok;st.cash-=ok.cost;st.book+=ok.cost;const timer=Math.round(cfg.tiers[ti].timerH*3600/cfg.global.tick);if(st.build===null)st.build={t:tick+timer,i:ti};else st.queue.push(ti);return{ok:true,cost:ok.cost}}
function sellOne(cfg,st,bi,price,manual){const v=st.pend[bi]||0;if(v<=0)return{ok:false,why:'nothing to sell'};const gross=Math.round(v*price*(manual?1+(cfg.fun.premiumSalePct||0)/100:1));const before=st.cash;const n=net(cfg,st,gross);st.cash+=n;st.pend[bi]=0;if(price>=(cfg.gate?.goodSalePrice||1.03)-1e-6&&price>1)st.checklist.goodSales++;if(st.onSold)st.onSold(st.tierOf[bi],v);return{ok:true,gross,net:n,tax:gross-n}}
function acceptContract(cfg,st,offerIdx,k){if(!st.offers||!st.offers[offerIdx])return{ok:false,why:'no such offer'};if(st.contracts.length>=cfg.fun.contractSlots)return{ok:false,why:'no free slot'};const o=st.offers.splice(offerIdx,1)[0];st.contracts.push({...o,delivered:0});st.cStats.accepted++;return{ok:true,contract:o}}
function gateOpen(cfg,st){const c=st.checklist;return st.b.length>=cfg.global.gateTier&&c.lv25&&c.auto&&c.goodSales>=(cfg.gate?.goodSalesNeeded||10)&&c.quiz}
/* class-level world: price streams, events, pressure. Call classTick once per tick, then playerTick per player. */
function newClass(cfg,ticks){return {streams:priceStreams(cfg,ticks),ev:eventSchedule(cfg,ticks),pressure:new Float64Array(cfg.tiers.length),incomePerHour:1,k:0}}
function classPrice(cfg,cls,ti,k){const f=cfg.fun,fam=cfg.tiers[ti].family;let m=cls.streams[ti][k]*eventMult(cfg,cls.ev,fam,k);if(f.pressure){const depth=FAMILIES[fam].depth*cls.incomePerHour;m-=Math.min(0.3,cls.pressure[ti]/Math.max(1,depth))}return Math.max(0.4,Math.min(2.0,m))}
function classTick(cfg,cls,players,k){const f=cfg.fun,HOUR=Math.round(3600/cfg.global.tick);if(f.pressure){const d=Math.pow(0.5,1/(f.pressureHalfLifeMin*60/cfg.global.tick));for(let i=0;i<cls.pressure.length;i++)cls.pressure[i]*=d}if(k%HOUR===0)cls.incomePerHour=Math.max(1,players.reduce((a,st)=>a+revS(cfg,st),0)*HOUR);cls.k=k}
function playerTick(cfg,cls,st,k){const g=cfg.global,f=cfg.fun,DAY=Math.round(86400/g.tick),HOUR=Math.round(3600/g.tick);st.rumour=rumourNow(cfg,cls.ev,k);st.onSold=(ti,v)=>{if(f.pressure)cls.pressure[ti]+=v};
  if(st.build!==null&&k>=st.build.t)finishBuild(cfg,st,k,DAY);
  if(f.contracts&&k%DAY===0)offerContracts(cfg,st,k,DAY);
  const total=revS(cfg,st);const boost=k<st.catchupUntil?g.catchupMult:1;const produced={};
  for(let bi=0;bi<st.b.length;bi++)produced[bi]=Math.round(bRev(cfg,st,bi)*st.rb.inc*boost);
  if(f.contracts)tickContracts(cfg,st,k,produced);
  const cap=total*g.whHours*HOUR+1;
  for(let bi=0;bi<st.b.length;bi++){st.pend[bi]=(st.pend[bi]||0)+produced[bi];const capB=Math.round(cap*(total?bRev(cfg,st,bi)/total:1))+1;
    if(st.pend[bi]>capB){const ov=st.pend[bi]-capB;st.pend[bi]=capB;const ti=st.tierOf[bi];st.cash+=net(cfg,st,Math.round(ov*classPrice(cfg,cls,ti,k)*(1-g.overflowDisc)));st.onSold(ti,ov)}}}
function onLogin(cfg,st,k){const g=cfg.global,HOUR=Math.round(3600/g.tick);if(st.lastLogin>0&&k-st.lastLogin>=g.catchupAbsenceH*HOUR)st.catchupUntil=k+Math.round(g.catchupHours*HOUR);st.lastLogin=k}
function netWorth(st){return st.cash+Object.values(st.pend).reduce((a,b)=>a+b,0)+st.book}
return {FAMILIES,rng,gauss,priceStreams,eventSchedule,eventMult,rumourNow,ms,setMult,bRev,revS,taxRate,net,expandOptions,buyLoop,finishBuild,offerContracts,considerContracts,tickContracts,sellAll,simulate,
  newState,levelCost,autoCost,buyLevel,buyAuto,canExpand,expand,sellOne,acceptContract,gateOpen,newClass,classPrice,classTick,playerTick,onLogin,netWorth};
});
