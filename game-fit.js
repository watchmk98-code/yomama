/* Viewport layouts: panels use pages; Market goods scale to remain visible. */
(function(){
  'use strict';
  var tabs={}, pages={}, resizing, lastSelected;
  if(new URLSearchParams(location.search).has('customer'))tabs.Market=1;
  if(location.hash==='#stock')tabs.Build=1;
  if(location.hash==='#team')tabs.Operations=1;
  if(location.hash==='#quests')tabs.Operations=2;
  function compact(){return innerWidth<1100 || innerHeight<=650 || (innerHeight<720 && !!document.querySelector('#econ-building')) || (innerHeight<820 && !!document.querySelector('#econ-building #game-expansion-choice, #econ-building .game-construction'));}
  function guideText(value){var node=document.createElement('span');node.textContent=value;return node.innerHTML;}
  function moneyGuide(state){
    if(!state.operatingStatement || !state.operatingStatement.enabled)return '';
    return '<p class="game-guide-tip"><strong>Sales</strong> shows what customers pay. <strong>Costs</strong> includes making goods, plus supplies and selling fees taken from sales. <strong>Cash</strong> is what you can spend. Order rewards and buyer cards show cash after selling fees; production costs are paid separately. <strong>Shop payout</strong> means the cash left from a normal shop sale after selling fees.</p>';
  }
  function rhythmGuide(state){
    var rhythms=state.sectorRhythms;
    if(!rhythms || !rhythms.enabled)return '';
    return '<details class="game-guide-more"><summary>Why does stock arrive in batches?</summary><p><strong>Production / min</strong> shows an average. Goods arrive in batches, so your stock can jump after a wait. The batch pattern keeps the same average output.</p><ul>'+
      (rhythms.profiles || []).map(function(profile){return '<li><strong>'+guideText(profile.label)+':</strong> '+guideText(profile.description)+'</li>';}).join('')+
      '</ul><p>Industry can make a smaller batch if cash or shelf space is too tight for a large one. Energy products begin at different times, with a starting wait of up to '+guideText(2*(state.tickSeconds || 15))+' game seconds. Pausing the business or class pauses this wait. Stock updates every '+guideText(state.tickSeconds || 15)+' game seconds.</p></details>';
  }
  function guideMarkup(kind,state){
    var costs=state.operations && state.operations.enabled, independent=state.productionMode==='independent';
    if(kind==='build')return '<p class="game-guide-intro">Make goods → sell goods → earn cash.</p>'+
      '<ol class="game-guide-steps">'+
      '<li><strong>Choose a business.</strong> Select its name to see what it makes, its Stock, and its Upgrades.</li>'+
      '<li><strong>Let it work.</strong> Open businesses make goods automatically over time. Goods appear in <strong>Stock</strong>. You earn cash when goods are sold.</li>'+
      (independent?'<li><strong>Each business makes its own goods.</strong> It does not take ingredients from your other businesses.<span class="game-guide-example">The Roastery makes pastries. Your Farm keeps its eggs and honey.</span></li>':'<li><strong>Feed the recipes.</strong> Some products need goods from other businesses. A recipe uses up its ingredients to make a new item.<span class="game-guide-example">Farm eggs + honey → Roastery pastries</span></li>')+
      '<li><strong>Sell or save.</strong> Shop customers buy automatically when goods are available. Visit <strong>Market</strong> to choose orders or sign regular buyers.</li></ol>'+
      '<p class="game-guide-tip"><strong>Grey item?</strong> Click <strong>Locked · Unlock →</strong> in Stock and complete the quest shown.</p>'+
      moneyGuide(state)+
      rhythmGuide(state)+
      '<details class="game-guide-more"><summary>Which upgrade should I choose?</summary><ul>'+
      '<li><strong>Production:</strong> make goods faster. The green number shows extra sales with your current customers. <strong>+0 YM/min</strong> means more output but no extra sales yet.</li><li><strong>Customers:</strong> attract more walk-in buyers. They still need goods to buy.</li><li><strong>Storage:</strong> fit more goods on your shelves.</li></ul>'+
      (costs?'<p>Upgrades cost cash and increase running costs. Check <strong>Sales · last 60s</strong> and <strong>Costs · last 60s</strong> for cash actually earned and spent. Potential figures are estimates. Saved goods still cost money to make; payment arrives when you deliver them.</p>':'')+
      '<p>To open another business, use <strong>Expand</strong> and collect what its price and requirements show.</p></details>'+
      '<details class="game-guide-more"><summary>Why did my goods stop growing?</summary><p>Check the business message and Stock. You may need '+(independent?'empty shelf space, a quest unlock':'ingredients, empty shelf space, an unlocked recipe')+(costs?', or cash to pay production costs.':'.')+' Make sure the business'+(independent?'':' and its recipes')+(independent?' is not paused.</p>':' are not paused.</p>')+
      '<p><strong>Hold goods</strong> stops walk-in sales only. '+(independent?'Deliveries can still use goods.':'Recipes and deliveries can still use goods.')+' Press <strong>Resume shop sales</strong> to sell automatically again.</p>'+
      '<p>Regular buyers'+(independent?'':' and their recipes')+' get supplies first. Pause a buyer in Market if you need those goods for something else.</p></details>';
    var timed=!!state.orderPreview, varied=((state.contracts || {}).rolls || []).some(function(r){return r.id==='small';});
    return '<p class="game-guide-intro">An order is a shopping list. Bring the goods to earn its reward.</p>'+
      '<ol class="game-guide-steps">'+
      '<li><strong>Pick a reward.</strong> The <strong>Goal order</strong> asks only for what your current opening goal still needs. Other cards are optional. Look at the cash reward at the bottom of a card.</li>'+
      '<li><strong>Fill the shopping list.</strong> Read <strong>Have / need</strong> beside each item.<span class="game-guide-example">3 / 5 = 3 ready to use. You need 2 more.</span>Let your businesses make the missing goods. The estimate shows how long gathering them may take; <strong>If saved</strong> assumes you press <strong>Save for this order</strong>.'+(state.sectorRhythms && state.sectorRhythms.enabled?' Industry makes larger batches, so stock may jump after a wait.':'')+' Use <strong>Save for this order</strong> to keep supplies for this job after regular buyers get theirs.</li>'+
      '<li><strong>Deliver when every item is ready.</strong> Press <strong>Deliver</strong>. The goods leave your stock and you get the reward.'+
      (timed?' <strong>Start delivery</strong> sends a timed shipment instead: its goods are saved for the trip, and you get paid when the timer ends.':'')+'</li></ol>'+
      '<p class="game-guide-tip"><strong>Want another offer?</strong> <strong>CLICK!!!!</strong> changes that card for free. Clicking it earns no cash.</p>'+
      moneyGuide(state)+
      (varied?'<details class="game-guide-more"><summary>What do the order labels mean?</summary><ul><li><strong>Small:</strong> a few units of one product. Try this when you have a little stock to spare.</li><li><strong>Standard:</strong> a regular-sized shopping list.</li><li><strong>Bulk:</strong> lots of one product. Clear spare stock, but earn less per item than a Standard order on the same card.</li><li><strong>Large:</strong> a bigger shopping list with a better price per item.</li><li><strong>Rare and Jackpot:</strong> bigger requests with extra cash bonuses.</li></ul><p>Check the goods and reward each time. A bigger reward also uses more of your stock. On a timed card, you still wait for delivery.</p></details>':'')+
      (timed?'<details class="game-guide-more"><summary>What is different about the three cards?</summary><ul><li><strong>Delivery:</strong> wait for payment. A bigger payout takes longer.</li><li><strong>Sector:</strong> an order from one business group, such as Food. The game picks the group. Earn cash.</li><li><strong>Third card:</strong> a general order. Deliver its goods to get cash right away.</li></ul></details>':'')+
      '<details class="game-guide-more"><summary>Who gets my goods first?</summary><p><strong>Regular buyers:</strong> choose a buyer and press <strong>Sign customer</strong>. They buy a set bundle automatically on a timer, at a lower price. '+(independent?'Goods for their next shipment are saved first.':'Their next shipment and its ingredients get supplies first.')+' Short of goods? The buyer waits.</p>'+
      '<p><strong>Need those goods for an order?</strong> Press <strong>Pause</strong> on the buyer. You stop their payments and free their supplies. <strong>Resume</strong> starts a new shipment timer.</p>'+
      '<p><strong>Walk-in customers:</strong> buy available goods automatically at the normal price. They may not buy everything you make. The <strong>Customers</strong> upgrade brings more buyers; demand does not change randomly.</p>'+
      '<p><strong>One stock, many choices:</strong> goods you '+(independent?'sell or deliver':'sell or use in a recipe')+' are gone. Keep a regular buyer supplied, save for an order, or leave goods for walk-ins.</p></details>';
  }
  function choose(group,index){tabs[group]=index;render();}
  function sectionMenu(){
    var nav=document.querySelector('.hero .tabs');if(!nav)return;
    var select=document.getElementById('game-section-menu');
    if(!select){select=document.createElement('select');select.id='game-section-menu';select.setAttribute('aria-label','Main navigation');select.addEventListener('change',function(){location.href=select.value;});nav.after(select);}
    select.replaceChildren();
    Array.from(nav.querySelectorAll('a:not([hidden])')).forEach(function(a){var o=document.createElement('option');o.value=a.getAttribute('href');o.textContent=a.textContent;o.selected=a.getAttribute('aria-current')==='page';select.appendChild(o);});
  }
  function tabset(root,key,items){
    root.querySelectorAll('.game-view-tabs').forEach(function(n){n.remove();});
    items=items.filter(function(i){return i[1];});
    if(!items.length)return;
    items.forEach(function(i){i[1].classList.remove('game-view-hidden');i[1].removeAttribute('role');i[1].removeAttribute('aria-labelledby');});
    if((!compact() && key!=='Operations') || items.length<2)return;
    var selected=Math.min(tabs[key]||0,items.length-1);tabs[key]=selected;
    var nav=document.createElement('div');nav.className='game-view-tabs';nav.setAttribute('role','tablist');nav.setAttribute('aria-label',key+' panels');
    items.forEach(function(item,index){
      var button=document.createElement('button');button.type='button';button.id='game-tab-'+key+'-'+index;button.textContent=item[0];button.setAttribute('role','tab');button.setAttribute('aria-selected',String(index===selected));button.tabIndex=index===selected?0:-1;
      item[1].id=item[1].id || 'game-view-'+key+'-'+index;button.setAttribute('aria-controls',item[1].id);item[1].setAttribute('role','tabpanel');item[1].setAttribute('aria-labelledby',button.id);
      button.addEventListener('click',function(){choose(key,index);root.querySelectorAll('.game-view-tabs button')[index].focus();});
      button.addEventListener('keydown',function(e){var next;if(e.key==='ArrowRight'||e.key==='ArrowLeft')next=(index+(e.key==='ArrowRight'?1:-1)+items.length)%items.length;else if(e.key==='Home')next=0;else if(e.key==='End')next=items.length-1;else return;e.preventDefault();choose(key,next);root.querySelectorAll('.game-view-tabs button')[next].focus();});
      nav.appendChild(button);item[1].classList.toggle('game-view-hidden',index!==selected);
    });
    root.prepend(nav);
  }
  function paginate(selector,key,minHeight,columns){
    var host=document.querySelector(selector);if(!host || !host.getClientRects().length)return;
    var parent=host.parentElement, inlinePager=key==='Orders';
    var pagerParent=inlinePager?parent.querySelector('.game-panel-head'):parent;
    var old=pagerParent.querySelector(':scope > .game-pager[data-page="'+key+'"]');if(old)old.remove();
    var children=Array.from(host.children);children.forEach(function(e){e.hidden=false;});
    host.classList.add('game-paged-list');
    var per=Math.max(columns,Math.floor((host.clientHeight-(inlinePager?0:36))/minHeight)*columns);
    per=Math.min(per,children.length || 1);
    var count=Math.ceil(children.length/per);
    if(key==='Buildings'){
      var selected=children.findIndex(function(e){return e.getAttribute('aria-pressed')==='true';});
      var slot=selected>=0?children[selected].getAttribute('data-select-building'):null;
      if(slot!==lastSelected || pages[key]===undefined){pages[key]=Math.max(0,Math.floor(selected/per));lastSelected=slot;}
    }
    var current=Math.min(pages[key]||0,Math.max(0,count-1));pages[key]=current;
    children.forEach(function(e,i){e.hidden=i<current*per || i>=(current+1)*per;});
    host.style.setProperty('--page-rows',Math.ceil(Math.min(per,children.length-current*per)/columns));
    if(count<=1)return;
    var nav=document.createElement('div');nav.className='game-pager';nav.dataset.page=key;nav.setAttribute('aria-label',key+' pages');
    function button(label,step){var b=document.createElement('button');b.type='button';b.textContent=label;b.setAttribute('aria-label',(step>0?'Next ':'Previous ')+key.toLowerCase()+' page');b.disabled=step<0?current===0:current===count-1;b.addEventListener('click',function(){pages[key]=current+step;render();var nav=document.querySelector('.game-pager[data-page="'+key+'"]');var n=nav&&nav.querySelector('button'+(step>0?':last-child':':first-child'));if(n&&n.disabled)n=nav.querySelector('button:not(:disabled)');if(n)n.focus();});return b;}
    nav.appendChild(button('←',-1));var info=document.createElement('span');info.textContent=(current+1)+' / '+count;nav.appendChild(info);nav.appendChild(button('→',1));
    pagerParent.appendChild(nav);
  }
  function fitMarketGoods(market){
    if(!market)return;
    market.querySelectorAll('.game-order-goods,.game-contract-goods').forEach(function(host){
      // All requirements must stay visible: shrink them, never paginate goods.
      // Card/tab navigation may hide whole panels, but never individual items.
      var caption=host.parentElement.querySelector('.game-order-caption,.game-contract-caption');
      if(caption)caption.querySelectorAll('.game-pager').forEach(function(nav){nav.remove();});
      var rows=Array.from(host.children);
      rows.forEach(function(row){row.hidden=false;});
      host.classList.remove('game-paged-list');
      host.style.removeProperty('--page-rows');
      host.style.setProperty('--market-goods-scale','1');
      host.style.setProperty('--market-goods-geometry','1');
      if(!rows.length || !host.getClientRects().length || host.clientHeight<=0 || host.clientWidth<=0)return;
      function fits(){
        var box=host.getBoundingClientRect();
        if(host.scrollHeight>host.clientHeight+1 || host.scrollWidth>host.clientWidth+1)return false;
        return rows.every(function(row){
          var bounds=row.getBoundingClientRect();
          if(bounds.bottom>box.bottom+.5 || bounds.right>box.right+.5)return false;
          return Array.from(row.querySelectorAll('span')).every(function(text){return text.scrollWidth<=text.clientWidth+1;});
        });
      }
      // Preserve the full font while reducing roomy icons and row spacing first.
      // Measuring wrapped rows covers both long names and large quantities.
      if(fits())return;
      host.style.setProperty('--market-goods-geometry','.25');
      var geometryOnly=fits(), low=geometryOnly ? .25 : 0, high=1;
      for(var step=0;step<10;step++){
        var scale=(low+high)/2;
        if(geometryOnly)host.style.setProperty('--market-goods-geometry',String(scale));
        else {
          host.style.setProperty('--market-goods-scale',String(scale));
          host.style.setProperty('--market-goods-geometry',String(scale*.25));
        }
        if(fits())low=scale;else high=scale;
      }
      var fitted=Math.max(.001,Math.floor(low*1000)/1000);
      host.style.setProperty('--market-goods-scale',String(geometryOnly?1:fitted));
      host.style.setProperty('--market-goods-geometry',String(geometryOnly?fitted:fitted*.25));
    });
  }
  function render(){
    if(!document.body.classList.contains('game-page'))return;
    var focusedId=document.activeElement && document.activeElement.id;
    document.body.classList.add('game-fitted');document.body.classList.toggle('game-compact',compact());sectionMenu();
    var build=document.getElementById('econ-building'), market=document.getElementById('econ-market'), ops=document.getElementById('econ-auto'), licence=document.getElementById('econ-license');
    if(build){
      var buildHeading=document.querySelector('.game-build-page .game-page-head h1');
      if(buildHeading && !document.getElementById('game-build-guide')){
        var buildGuide=document.createElement('button');buildGuide.type='button';buildGuide.id='game-build-guide';buildGuide.className='game-guide-button game-build-guide';buildGuide.dataset.marketHelp='build';buildGuide.setAttribute('aria-haspopup','dialog');buildGuide.textContent='guide';buildHeading.after(buildGuide);
      }
      build.querySelectorAll('.game-fit-controls').forEach(function(n){n.remove();});
      var site=build.querySelector('.game-site'), stock=build.querySelector('.game-building-stock');
      if(site && stock){if(compact())site.after(stock);else site.appendChild(stock);}
      tabset(build,'Build',[['Building',site],['Stock',stock],['Upgrades',build.querySelector('.game-operations')],['Expand',build.querySelector('.game-expansion')]]);
      document.body.dataset.fitBuildView=String(tabs.Build||0);
      var picker=build.querySelector('.game-fit-picker');if(picker)picker.remove();
      if(compact() && window.YomamaEcon){var s=window.YomamaEcon.state();if(s && s.buildings.length>1){picker=document.createElement('select');picker.className='game-fit-picker';picker.setAttribute('aria-label','Selected building');s.buildings.forEach(function(b){var o=document.createElement('option');o.value=b.slot;o.textContent=b.name;o.selected=!!build.querySelector('[data-select-building="'+b.slot+'"][aria-pressed="true"]');picker.appendChild(o);});picker.onchange=function(){var b=build.querySelector('[data-select-building="'+picker.value+'"]');if(b)b.click();};build.insertBefore(picker,build.firstChild);}}
      if(compact()){
        var controls=document.createElement('div');controls.className='game-fit-controls';
        if(picker && picker.isConnected)controls.appendChild(picker);
        var buildTabs=build.querySelector('.game-view-tabs');if(buildTabs)controls.appendChild(buildTabs);
        build.prepend(controls);
      }
    }
    if(market){
      var regulars=market.querySelector('.game-customer-contracts');
      tabset(market,'Market',[['Orders',market.querySelector('.game-market-orders')],['Contracts',regulars]]);
      market.classList.toggle('game-market-narrow',!compact() && !!regulars && innerWidth<1250);
      var buyerPanel=market.querySelector('.game-contract-panel');
      market.classList.toggle('game-market-tight',!!buyerPanel && buyerPanel.clientHeight<570);
      var ordersHeading=market.querySelector('.game-market-orders > .game-panel-head');
      if(ordersHeading && !ordersHeading.querySelector('[data-market-help="orders"]')){
        var guide=document.createElement('button');guide.type='button';guide.id='game-orders-guide';guide.className='game-guide-button game-orders-guide';guide.dataset.marketHelp='orders';guide.setAttribute('aria-haspopup','dialog');guide.textContent='guide';ordersHeading.querySelector('h2').after(guide);
      }
      var buyerHeading=regulars && regulars.querySelector('.game-panel-head');
      if(buyerHeading && !buyerHeading.querySelector('[data-market-help]')){
        var help=document.createElement('button');help.type='button';help.id='game-market-buyer-help';help.className='game-market-help';help.dataset.marketHelp='buyers';help.setAttribute('aria-label','About regular buyers');help.textContent='?';buyerHeading.appendChild(help);
      }
      var offer=market.querySelector('.game-contract-order-choice'), offerPreview=market.querySelector('[data-market-help="offer"]');
      if(offerPreview)offerPreview.remove();
      if(offer){
        offer.hidden=!!buyerPanel && buyerPanel.clientHeight<570;
        if(offer.hidden){offerPreview=document.createElement('button');offerPreview.id='game-market-offer';offerPreview.type='button';offerPreview.className='game-market-offer';offerPreview.dataset.marketHelp='offer';offerPreview.setAttribute('aria-label','Review order size');offerPreview.textContent='Order size…';market.querySelector('.game-contract-footer').appendChild(offerPreview);}
      }
    }
    if(ops && !ops.querySelector('.wf-workspace'))tabset(ops,'Operations',[[(window.YomamaEcon && window.YomamaEcon.state() || {}).productionMode==='independent'?'Products':'Recipes',ops.querySelector('.game-purpose-main')],['Team',ops.querySelector('.game-business-team')],['Quests',ops.querySelector('.game-business-quests')]]);
    if(licence){var sections=Array.from(licence.querySelector('.game-license-layout')?.children||[]);tabset(licence,'Licence',sections.map(function(n){return [n.classList.contains('game-invest')?'Invest':n.querySelector('#game-goals')?'Goals':'Quiz',n];}));var goals=licence.querySelector('#game-goals');if(goals)goals.open=true;}
    paginate('.game-roster-list','Buildings',68,1);
    var orderGrid=market && market.querySelector('.game-order-grid');
    var orderCardWidth=orderGrid && orderGrid.clientHeight<500?430:350;
    var orderColumns=compact() || (market && market.classList.contains('game-market-narrow'))?1:Math.max(1,Math.min(3,Math.floor((orderGrid?orderGrid.clientWidth:0)/orderCardWidth)));
    if(market)market.style.setProperty('--market-order-columns',orderColumns);
    paginate('.game-market-orders .game-order-grid','Orders',10000,orderColumns);
    fitMarketGoods(market);
    paginate('.game-purpose-main .game-recipe','Recipes',140,compact()?1:(innerWidth>1100?2:1));
    paginate('.game-inventory-rows','Inventory',compact()?38:76,compact()?1:3);
    paginate('.game-checklist','Milestones',50,1);
    if(focusedId && focusedId.indexOf('game-tab-')===0){var focusedTab=document.getElementById(focusedId);if(focusedTab)focusedTab.focus({preventScroll:true});}
  }
  window.YomamaFit={render:render};
  document.addEventListener('click',function(event){
    var action=event.target.closest('.game-market-help-dialog [data-econ-action]');if(action){action.closest('dialog').close();return;}
    var trigger=event.target.closest('[data-market-help]');if(!trigger)return;
    var helpKind=trigger.dataset.marketHelp;
    var panel=document.querySelector('.game-customer-contracts');if(!panel && helpKind!=='orders' && helpKind!=='build')return;
    var dialog=document.createElement('dialog');dialog.className='econ-kid game-market-help-dialog';dialog.setAttribute('aria-labelledby','market-help-title');
    if(helpKind==='orders' || helpKind==='build')dialog.classList.add('game-guide-dialog');
    var heading=document.createElement('div');heading.className='game-dialog-head';
    var title=document.createElement('h2');title.id='market-help-title';title.textContent=helpKind==='build'?'Build guide':helpKind==='orders'?'Orders guide':helpKind==='offer'?'Review order size':'Regular buyers';heading.appendChild(title);
    var close=document.createElement('button');close.type='button';close.className='game-small-button';close.textContent='Close';close.addEventListener('click',function(){dialog.close();});heading.appendChild(close);dialog.appendChild(heading);
    if(helpKind==='orders' || helpKind==='build')dialog.insertAdjacentHTML('beforeend',guideMarkup(helpKind,window.YomamaEcon && window.YomamaEcon.state() || {}));
    else if(helpKind==='offer'){var terms=panel.querySelector('.game-contract-order-choice').cloneNode(true);terms.hidden=false;terms.querySelectorAll('[id]').forEach(function(node){node.removeAttribute('id');});dialog.appendChild(terms);}
    else panel.querySelectorAll('.game-contract-intro,.game-contract-description,.game-contract-help,.game-contract-footer > span:last-of-type').forEach(function(source){var paragraph=document.createElement('p');paragraph.textContent=source.textContent;dialog.appendChild(paragraph);});
    dialog.addEventListener('close',function(){dialog.remove();var next=document.querySelector('[data-market-help="'+helpKind+'"]');if(next)next.focus({preventScroll:true});});document.body.appendChild(dialog);dialog.showModal();
  });
  window.addEventListener('hashchange',function(){if(location.hash==='#stock'){tabs.Build=1;render();}else if(location.hash==='#goal-order'){tabs.Market=0;pages.Orders=0;render();}});
  window.addEventListener('resize',function(){clearTimeout(resizing);resizing=setTimeout(render,100);});
  window.addEventListener('yomama:econ',render);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render);else render();
  if(document.fonts){document.fonts.ready.then(render);document.fonts.addEventListener('loadingdone',render);}
})();
