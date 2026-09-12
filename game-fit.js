/* Viewport layouts: visible panels stretch; overflow uses explicit pages. */
(function(){
  'use strict';
  var tabs={}, pages={}, orderIds={}, resizing, lastSelected;
  function compact(){return innerWidth<1100 || innerHeight<=650;}
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
    if(!compact() || items.length<2)return;
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
    var parent=host.parentElement, old=parent.querySelector(':scope > .game-pager[data-page="'+key+'"]');if(old)old.remove();
    var children=Array.from(host.children);children.forEach(function(e){e.hidden=false;});
    host.classList.add('game-paged-list');
    var per=Math.max(columns,Math.floor((host.clientHeight-36)/minHeight)*columns);
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
    nav.appendChild(button('←',-1));var info=document.createElement('span');info.textContent=(current+1)+' / '+count;nav.appendChild(info);nav.appendChild(button('→',1));parent.appendChild(nav);
  }
  function render(){
    if(!document.body.classList.contains('game-page'))return;
    var focusedId=document.activeElement && document.activeElement.id;
    document.body.classList.add('game-fitted');document.body.classList.toggle('game-compact',compact());sectionMenu();
    var build=document.getElementById('econ-building'), market=document.getElementById('econ-market'), warehouse=document.getElementById('econ-warehouse'), ops=document.getElementById('econ-auto'), licence=document.getElementById('econ-license');
    if(build){
      build.querySelectorAll('.game-fit-controls').forEach(function(n){n.remove();});
      tabset(build,'Build',[['Building',build.querySelector('.game-site')],['Upgrades',build.querySelector('.game-operations')],['Expand',build.querySelector('.game-expansion')]]);
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
    if(warehouse)tabset(warehouse,'Warehouse',[['Stock',warehouse.querySelector('.game-inventory-table')],['Manage',warehouse.querySelector('.game-purpose-side')]]);
    if(market){
      var regulars=market.querySelector('.game-customer-contracts');
      tabset(market,'Market',[['Orders',market.querySelector('.game-market-orders')],['Contracts',regulars]]);
      market.classList.toggle('game-market-narrow',!compact() && !!regulars && innerWidth<1250);
    }
    if(ops)tabset(ops,'Operations',[['Recipes',ops.querySelector('.game-purpose-main')]]);
    if(licence){var sections=Array.from(licence.querySelector('.game-license-layout')?.children||[]);tabset(licence,'Licence',sections.map(function(n){return [n.classList.contains('game-invest')?'Invest':n.querySelector('#game-goals')?'Goals':'Quiz',n];}));var goals=licence.querySelector('#game-goals');if(goals)goals.open=true;}
    paginate('.game-roster-list','Buildings',68,1);
    var orderColumns=compact() || (market && market.classList.contains('game-market-narrow'))?1:3;
    paginate('.game-market-orders .game-order-grid','Orders',orderColumns===1?10000:160,orderColumns);
    for(var orderIndex=0;orderIndex<3;orderIndex++){
      var orderHost=document.querySelector('[data-order-items="'+orderIndex+'"]');
      if(orderHost && orderIds[orderIndex]!==orderHost.dataset.orderId){
        pages['Order '+(orderIndex+1)+' goods']=0;orderIds[orderIndex]=orderHost.dataset.orderId;
      }
      paginate('[data-order-items="'+orderIndex+'"] .game-order-goods','Order '+(orderIndex+1)+' goods',28,1);
    }
    paginate('.game-purpose-main .game-recipe','Recipes',140,compact()?1:(innerWidth>1100?2:1));
    paginate('.game-inventory-rows','Inventory',60,1);
    paginate('.game-checklist','Milestones',50,1);
    if(focusedId && focusedId.indexOf('game-tab-')===0){var focusedTab=document.getElementById(focusedId);if(focusedTab)focusedTab.focus({preventScroll:true});}
  }
  window.YomamaFit={render:render};
  window.addEventListener('resize',function(){clearTimeout(resizing);resizing=setTimeout(render,100);});
  window.addEventListener('yomama:econ',render);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render);else render();
})();
