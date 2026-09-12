// Rebuild fixtures from the supplied, unmodified JS engine (not the Python port).
const fs=require('fs'),E=require('../engine/economy-engine.reference.js');
const cfg=JSON.parse(fs.readFileSync('config/economy.v3.json'));
// Four attendance profiles supplied in Downloads/yomama_sim_lab.html.
const profiles=[
 {name:'once/day (random time)',logins:'1',randomTimes:1,windowStart:'07:00',windowEnd:'23:00',sessionMin:10,attendance:1,strategy:'optimizer'},
 {name:'3x/day (random times)',logins:'3',randomTimes:1,windowStart:'07:00',windowEnd:'23:00',sessionMin:10,attendance:1,strategy:'optimizer'},
 {name:'real kid (1x random, shows up 65%)',logins:'1',randomTimes:1,windowStart:'07:00',windowEnd:'23:00',sessionMin:10,attendance:.65,strategy:'optimizer'},
 {name:'fixed 19:00 (reference)',logins:'19:00',randomTimes:0,windowStart:'07:00',windowEnd:'23:00',sessionMin:10,attendance:1,strategy:'optimizer'}
];
function flatten(r){return {netWorthDay7:r.nw,buildingsOwned:r.tier,levels:r.levels,families:r.families,incomePerDay:r.incDay,taxPaid:r.tax,gateDay:r.gateDay,unlockDays:r.unlock,contracts:r.contracts,realEvents:r.events,hourlyNetWorth:r.hourly};}
const deterministic=JSON.parse(JSON.stringify(cfg));deterministic.tiers.forEach(t=>t.sigma=0);
deterministic.profiles=[{name:'evening',logins:'19:00',sessionMin:10,strategy:'optimizer',attendance:1}];
const d=E.simulate(deterministic,7)[0];if(d.nw!==114157066)throw Error('Supplied acceptance value differs');
const note='Generated from supplied economy-engine.reference.js v3; original v3 fixtures were not provided. Four attendance profiles copied from the supplied simulator; all share one v3 market.';
fs.writeFileSync('tests/golden.deterministic.json',JSON.stringify({_note:note,days:7,classSeed:7,profile:deterministic.profiles[0],...flatten(d)},null,2)+'\n');
cfg.profiles=profiles;const results=E.simulate(cfg,7);
fs.writeFileSync('tests/golden.stochastic.json',JSON.stringify({_note:note,days:7,classSeed:7,profiles:Object.fromEntries(results.map((r,i)=>[profiles[i].name,{profile:profiles[i],...flatten(r)}]))},null,2)+'\n');
