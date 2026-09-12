/* Real sprite files and UI; all contract state changes stay inside this test. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.argv[2]||'http://127.0.0.1:3010';

(async()=>{
 const response=await fetch(base+'/api/game/econ/state');assert(response.ok);
 const state=await response.json();state.paused=false;
 const customers=state.customerContracts.customers;
 customers.forEach(customer=>customer.available=true);
 state.customerContracts.active=[];
 state.customerContracts.slots=4;
 state.customerContracts.nextUnlock=null;
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768},reducedMotion:'no-preference'});
  const errors=[],missing=[];
  page.on('pageerror',error=>errors.push(error.message));
  let failArt=false;
  page.on('response',response=>{
   if(!failArt&&response.url().includes('/assets/customers/')&&response.status()>=400)missing.push(response.url());
  });
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.origin!==base)return route.abort();
   if(failArt&&url.pathname.includes('/assets/customers/'))return route.fulfill({status:404,body:''});
   if(!url.pathname.startsWith('/api/game/econ/'))return route.continue();
   if(url.pathname.endsWith('/quiz'))return route.fulfill({json:{questions:[],passMark:4}});
   if(url.pathname.endsWith('/login'))return route.fulfill({json:state});
   assert.equal(route.request().method(),'GET','emote verification must not modify a save');
   return route.fulfill({json:state});
  });
  await page.goto(base+'/marketplace.html');
  const panel=page.locator('.game-customer-contracts');
  const avatars=panel.locator('.game-customer-avatar');
  const avatar=panel.locator('[data-customer-slot][aria-pressed=true] .game-customer-avatar');
  const art=avatar.locator('img');
  await avatar.waitFor();
  async function decodeVisibleArt(){
   await panel.locator('.game-customer-avatar img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));
  }
  async function refresh(){await page.evaluate(()=>window.YomamaEcon.refresh());await decodeVisibleArt();}
  async function assertFourPortraits(label){
   assert.equal(await panel.locator('[data-customer-slot]').count(),4,label+' has four slots');
   assert.equal(await avatars.count(),4,label+' does not duplicate the selected portrait');
   assert.equal(await panel.locator('.game-customer-avatar:visible').count(),4,label+' shows all four portraits');
   const ids=await avatars.evaluateAll(nodes=>nodes.map(node=>node.dataset.customerArt));
   assert.equal(new Set(ids).size,4,label+' shows distinct customers');
  }
  async function assertPanelFit(label){
   const outside=await panel.evaluate(root=>{
    const boundary=root.getBoundingClientRect();
    return [...root.querySelectorAll('button,select,.game-customer-character,.game-customer-avatar,.game-customer-slot-label,.game-contract-status,.econ-good-line,.game-contract-description,.game-contract-pay,.game-contract-history,.game-customer-emote-label,.game-contract-order-choice,.game-contract-help')]
     .filter(el=>el.getClientRects().length&&!el.closest('[hidden]')).filter(el=>{
      const r=el.getBoundingClientRect();
      return r.top<Math.max(0,boundary.top)-1||r.bottom>Math.min(innerHeight,boundary.bottom)+1||r.right>Math.min(innerWidth,boundary.right)+1||r.left<Math.max(0,boundary.left)-1;
     }).map(el=>el.className);
   });
   assert.deepEqual(outside,[],label+' customer art and controls fit inside the panel and viewport');
   const regions=await panel.evaluate(root=>{
    const slots=root.querySelector('.game-contract-slots').getBoundingClientRect();
    const body=root.querySelector('.game-contract-body').getBoundingClientRect();
    const footer=root.querySelector('.game-contract-footer').getBoundingClientRect();
    const contentBottom=Math.max(...[...root.querySelectorAll('.game-contract-summary,.game-contract-supply')].map(node=>node.getBoundingClientRect().bottom));
    return {rosterBeforeDetails:slots.bottom<=body.top+1,detailsBeforeFooter:body.bottom<=footer.top+1,contentBeforeFooter:contentBottom+3<=footer.top+1};
   });
   assert.deepEqual(regions,{rosterBeforeDetails:true,detailsBeforeFooter:true,contentBeforeFooter:true},label+' roster, details content and footer do not overlap');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1&&document.documentElement.scrollHeight<=innerHeight+1),label+' has no page scrolling');
  }
  await decodeVisibleArt();
  await assertFourPortraits('open roster');
  const chooser=page.locator('#game-customer-choice');
  assert.equal(customers.length,17,'every regular customer has a character');
  for(const customer of customers){
   await chooser.selectOption(customer.id);
   await decodeVisibleArt();
   assert.equal(await avatar.getAttribute('data-customer-art'),customer.id);
   assert((await art.getAttribute('src')).endsWith('/'+customer.id+'_16f.png'));
   assert(await art.evaluate(img=>img.naturalWidth===img.naturalHeight&&img.naturalWidth>0),customer.id+' square 4×4 emote sheet');
   assert.equal(await avatar.getAttribute('data-emote'),'working');
  }
  const candidate=customers.find(customer=>customer.id!=='orbital_research');
  const current={...structuredClone(candidate),id:'emote-preview-contract',customerId:candidate.id,slot:0,
   deliveries:7,earned:700,paused:false,status:'supplying',nextDeliverySeconds:120,
   requirements:candidate.requirements.map(need=>({...need,reserved:need.quantity,owned:need.quantity}))};
  state.customerContracts.active=[current];
  await refresh();
  assert.equal(await avatar.getAttribute('data-emote'),'working','history on first appearance is not a fresh shipment');
  // Verify the actual cropping for all four work frames, not just an animation name.
  const frames=await art.evaluate(img=>{
   const animation=img.getAnimations()[0];animation.pause();
   const width=img.getBoundingClientRect().width/4;
   const result=[];
   for(let i=0;i<4;i++){
    animation.currentTime=i*800+400;
    const matrix=new DOMMatrixReadOnly(getComputedStyle(img).transform);
    result.push(Math.round(matrix.m41/width));
   }
   animation.play();return result;
  });
  assert.deepEqual(frames,[0,-1,-2,-3]);
  current.status='waiting';await refresh();
  assert.equal(await avatar.getAttribute('data-emote'),'waiting');
  assert.equal(await avatar.evaluate(el=>Number(el.style.getPropertyValue('--customer-row'))),1);
  current.paused=true;await refresh();
  assert.equal(await avatar.getAttribute('data-emote'),'paused');
  assert.equal(await avatar.evaluate(el=>Number(el.style.getPropertyValue('--customer-row'))),3);
  assert.equal(await art.evaluate(img=>getComputedStyle(img).animationName),'none');
  current.paused=false;current.status='supplying';await refresh();
  current.deliveries++;await refresh();
  assert.equal(await avatar.getAttribute('data-emote'),'thanks','a real shipment increment triggers the thank-you emote');
  assert.equal(await avatar.evaluate(el=>Number(el.style.getPropertyValue('--customer-row'))),2);
  await refresh();
  await page.waitForFunction(()=>document.querySelector('[data-customer-slot][aria-pressed=true] .game-customer-avatar').dataset.emote==='working',null,{timeout:7000});
  await refresh();assert.equal(await avatar.getAttribute('data-emote'),'working','unchanged shipment counts cannot replay celebrations');
  const roster=[current,...customers.filter(customer=>customer.id!==candidate.id&&customer.id!=='orbital_research').slice(0,3).map((customer,index)=>({
   ...structuredClone(customer),id:'emote-preview-contract-'+(index+1),customerId:customer.id,slot:index+1,
   deliveries:8+index,earned:800+index*100,paused:index===1,status:index===0?'waiting':'supplying',nextDeliverySeconds:120,
   requirements:customer.requirements.map(need=>({...need,reserved:need.quantity,owned:need.quantity}))
  }))];
  state.customerContracts.active=roster;await refresh();
  await assertFourPortraits('active roster');
  const rosterEmotes=()=>avatars.evaluateAll(nodes=>nodes.map(node=>node.dataset.emote));
  assert.deepEqual(await rosterEmotes(),['working','waiting','paused','working'],'each simultaneous customer reflects its own contract');
  roster[3].deliveries++;await refresh();
  assert.deepEqual(await rosterEmotes(),['working','waiting','paused','thanks'],'an unselected shipment only celebrates for its own customer');
  assert.equal(await panel.locator('[data-customer-slot][aria-pressed=true]').getAttribute('data-customer-slot'),'0','shipment feedback preserves selection');
  await panel.locator('[data-customer-slot="2"] .game-customer-avatar').click();
  assert.equal(await panel.locator('[data-customer-slot][aria-pressed=true]').count(),1,'only one customer is selected');
  assert.equal(await panel.locator('[data-customer-slot][aria-pressed=true]').getAttribute('data-customer-slot'),'2','clicking the character selects its slot');
  assert.equal(await panel.locator('.game-contract-summary > h3').textContent(),roster[2].name);
  assert.equal(await panel.locator('#game-customer-toggle').textContent(),'Resume');
  assert.equal(await panel.locator('#game-customer-toggle').getAttribute('data-econ-action'),'customer:resume:2::'+roster[2].id,'controls target the selected contract');
  await refresh();
  assert.equal(await panel.locator('[data-customer-slot][aria-pressed=true]').getAttribute('data-customer-slot'),'2','selection persists after economy refresh');
  assert.equal(await panel.locator('.game-contract-summary > h3').textContent(),roster[2].name);
  await panel.locator('[data-customer-slot="0"] .game-customer-avatar').click();
  state.paused=true;await refresh();assert.deepEqual(await rosterEmotes(),Array(4).fill('paused'),'class pause rests every customer');
  state.paused=false;await refresh();
  const animationNames=()=>avatars.locator('img').evaluateAll(imgs=>imgs.map(img=>getComputedStyle(img).animationName));
  await page.locator('[data-customer-motion]').click();
  assert.deepEqual(await animationNames(),Array(4).fill('none'),'motion off stops every character');
  await page.locator('[data-customer-motion]').click();
  assert.deepEqual(await animationNames(),['game-customer-emote','game-customer-emote','none','game-customer-emote'],'motion on respects individually paused customers');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.deepEqual(await animationNames(),Array(4).fill('none'),'reduced motion stops every character');
  assert.equal(await page.locator('[data-customer-motion]').isVisible(),false);
  await page.emulateMedia({reducedMotion:'no-preference'});
  // A late-game customer also has two goods and the larger-order offer to fit.
  const late=customers.find(customer=>customer.id==='orbital_research');
  Object.assign(current,{customerId:late.id,name:late.name,reward:late.reward,intervalSeconds:late.intervalSeconds,
   requirements:late.requirements.map(need=>({...need,reserved:need.quantity,owned:need.quantity})),
   largerOffer:{reward:Math.round(late.reward*2.2),requirements:late.requirements.map(need=>({...need,quantity:need.quantity*2}))}});
  await refresh();
  for(const [width,height,label] of [[1366,768,'desktop'],[1024,768,'tablet'],[768,768,'compact-tablet'],[390,844,'mobile'],[844,390,'landscape']]){
   await page.setViewportSize({width,height});
   await page.evaluate(()=>window.YomamaFit.render());
   const tab=page.getByRole('tab',{name:'Contracts',exact:true});
   if(await tab.count())await tab.click();
   await panel.waitFor({state:'visible'});
   await decodeVisibleArt();
   await assertFourPortraits(label+' active roster');
   await assertPanelFit(label+' active roster');
   await page.screenshot({animations:'disabled',path:'previews/customer-emotes-'+label+'.png'});
   state.customerContracts.active=[];await refresh();
   for(const customer of customers){
    await chooser.selectOption(customer.id);
    await decodeVisibleArt();
    await assertFourPortraits(customer.id+' preview '+label);
    await assertPanelFit(customer.id+' introduction '+label);
   }
   state.customerContracts.active=roster;await refresh();
  }
  assert.deepEqual(missing,[]);
  failArt=true;await page.reload();
  await panel.locator('[data-customer-slot="0"]').waitFor({state:'attached'});
  const tab=page.getByRole('tab',{name:'Contracts',exact:true});
  if(await tab.count())await tab.click();
  await page.waitForFunction(()=>[...document.querySelectorAll('.game-customer-avatar')].length===4&&[...document.querySelectorAll('.game-customer-avatar')].every(node=>node.classList.contains('is-missing')));
  assert.equal(await avatars.locator('img').count(),0);
  assert.equal(await avatar.getAttribute('data-initial'),'O');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'passed',customers:17,simultaneousCharacters:4,emotes:4,frames:4,deliveryReaction:true,independentReactions:true,selectionPersists:true,pause:true,reducedMotion:true,fallback:true,viewports:5}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
