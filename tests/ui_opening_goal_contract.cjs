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
  '  window.contract={openingGuide};\n  // ------------------------------------------------------------------ boot --'
);
vm.runInNewContext(source,{window,document,location:window.location,URLSearchParams,console});

const banner = window.contract.openingGuide({
  paused:false,
  nextStep:null,
  build:{tier:1,name:'Harbor Fish Stall',remainingSec:30}
});
assert.match(banner,/class="game-opening-guide"/,'Active construction always renders the protected notice');
assert.match(banner,/Harbor Fish Stall is being built/);
assert.match(banner,/30s remaining\. Your other businesses keep working\./);
assert.doesNotMatch(banner,/projects|data-building-activities|href=/i,'Construction notice stays independent of removed projects');

const idle = window.contract.openingGuide({paused:false,nextStep:null,build:null});
assert.equal(idle,'','The notice is reserved for real construction or a funded build action');

const css = fs.readFileSync(path.join(root,'econ-kids.css'),'utf8');
assert.match(css,/\.game-opening-guide\s*\{[^}]*border:\s*1px solid #927bff[^}]*box-shadow:[^}]*rgba\(119,98,255,/s,
  'Protected construction notice retains its violet border and glow');
assert.match(css,/\.game-opening-guide strong\s*\{[^}]*color:#a89bff[^}]*text-shadow:/s,
  'Protected construction title retains its distinct light-violet emphasis');

console.log('Passed protected violet construction notice and removed group-project UI contracts.');
