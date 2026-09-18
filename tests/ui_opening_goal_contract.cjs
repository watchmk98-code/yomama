/* Construction notice and removed group-project UI contracts without a browser. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const noOp = () => {};
const window = {location:{search:'',hash:''},localStorage:{getItem:()=>null},matchMedia:()=>({matches:false}),addEventListener:noOp};
const document = {readyState:'loading',addEventListener:noOp,getElementById:()=>null,querySelectorAll:()=>[]};
const source = fs.readFileSync(path.join(root,'econ.js'),'utf8').replace(
  '  // ------------------------------------------------------------------ boot --',
  '  window.contract={openingGuide,ordersMarkup};\n  // ------------------------------------------------------------------ boot --'
);
vm.runInNewContext(source,{window,document,location:window.location,URLSearchParams,console});

const banner = window.contract.openingGuide({
  paused:false,
  nextStep:null,
  build:{tier:1,name:'Harbor Fish Stall',remainingSec:30}
});
assert.equal(banner, '', 'The temporary notice board switch hides construction notices');

const idle = window.contract.openingGuide({paused:false,nextStep:null,build:null,buildingsOwned:1,buildings:[{}]});
assert.equal(idle, '', 'The temporary notice board switch hides idle notices');

const complete = window.contract.openingGuide({paused:false,nextStep:null,build:null,buildingsOwned:15});
assert.equal(complete, '', 'The temporary notice board switch hides completion notices');

const order = {id:'ordinary',name:'Ordinary delivery',requirements:[],reward:10,canFulfill:true};
const market = window.contract.ordersMarkup({
  paused:false,buildings:[],contracts:{offers:[order,{...order,id:'second',name:'Second delivery'}]},
  goalOrder:{...order,id:'legacy-goal',name:'Removed group goal'}
});
assert.match(market,/Ordinary delivery/,'The market still renders ordinary orders after group projects are removed');
assert.match(market,/Second delivery/,'Multiple offers still sort and render');
assert.doesNotMatch(market,/Removed group goal|id="goal-order"/,'Legacy goal data does not recreate the removed panel');

const css = fs.readFileSync(path.join(root,'econ-kids.css'),'utf8');
assert.match(css,/\.game-opening-guide\s*\{[^}]*border:\s*1px solid #927bff[^}]*box-shadow:[^}]*rgba\(119,98,255,/s,
  'Protected construction notice retains its violet border and glow');
assert.match(css,/\.game-opening-guide strong\s*\{[^}]*color:#a89bff[^}]*text-shadow:/s,
  'Protected construction title retains its distinct light-violet emphasis');

console.log('Passed disabled violet business-status notice and removed group-project UI contracts.');
