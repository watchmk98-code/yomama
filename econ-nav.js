/* Port stays visible from the start; trading requires the earned licence. */
(function(){
  'use strict';
  var port=location.pathname.endsWith('/port_trading.html');
  var hasSeat=false;
  try{hasSeat=!!(JSON.parse(localStorage.getItem('yomama_session_v1')||'null')||{}).token;}catch(_){}
  // Also cover older static headers on pages that do not load app.js.
  document.querySelectorAll('.hero .tabs a[href="./port_trading.html"]').forEach(function(a){a.remove();});
  if(port){
    document.querySelectorAll('.hero .tabs a[href*="buildings.html"]').forEach(function(a){
      a.classList.add('active');a.setAttribute('aria-current','page');
    });
  }
  // Pages with their own state clients still use the same live economy HUD.
  var bannerHead=document.querySelector('.business-illustrated .game-page-head');
  if(bannerHead && !document.getElementById('game-hud')){
    var bannerHud=document.createElement('div');bannerHud.id='game-hud';bannerHud.className='econ-kid';
    if(port)bannerHud.dataset.economyClient='true';
    bannerHead.after(bannerHud);
    window.addEventListener('yomama:econ',function(event){
      if(window.YomamaEcon)bannerHud.innerHTML=window.YomamaEcon.resourceBar(event.detail);
    });
  }
  // Keep every business menu in the same order, including older saved pages.
  document.querySelectorAll('.game-nav').forEach(function(nav){
    var market=nav.querySelector('a[href*="marketplace.html"]');
    if(!market)return;
    nav.dataset.craftNav='true';
    var shopLink=nav.querySelector('a[href*="shop.html"]');
    if(!shopLink){
      shopLink=document.createElement('a');shopLink.href='./shop.html';
      shopLink.innerHTML='<span class="shop-nav-icon" aria-hidden="true">▣</span><span>Shop</span>';
      market.after(shopLink);
    }
    if(location.pathname.endsWith('/shop.html'))shopLink.setAttribute('aria-current','page');
    var focusLink=nav.querySelector('a[href*="focus-tree.html"]');
    if(!focusLink){
      focusLink=document.createElement('a');focusLink.href='./focus-tree.html';
      focusLink.innerHTML='<img src="./assets/focus-tree/focus.svg" alt="" width="28" height="28" aria-hidden="true"><span>Focus</span>';
      var licence=nav.querySelector('a[href*="license.html"]');
      if(licence)licence.before(focusLink);else nav.appendChild(focusLink);
    }
    focusLink.hidden=false;
    var bankLink=nav.querySelector('a[href*="bank.html"]');
    if(!bankLink){
      bankLink=document.createElement('a');bankLink.href='./bank.html';
      bankLink.innerHTML='<span aria-hidden="true">▥</span><span>Bank</span>';
      focusLink.after(bankLink);
    }
    if(location.pathname.endsWith('/bank.html'))bankLink.setAttribute('aria-current','page');
    if(location.pathname.endsWith('/focus-tree.html'))focusLink.setAttribute('aria-current','page');
    if(!nav.querySelector('a[href*="craft.html"]')){
      var craft=document.createElement('a');craft.href='./craft.html';
      craft.innerHTML='<span>Craft</span>';market.after(craft);
    }
    var craftLink=nav.querySelector('a[href*="craft.html"]');
    if(!craftLink.querySelector('.craft-nav-icon')){
      var craftIcon=document.createElement('span');
      craftIcon.className='craft-nav-icon';craftIcon.setAttribute('aria-hidden','true');
      craftLink.prepend(craftIcon);
    }
    if(location.pathname.endsWith('/craft.html'))craftLink.setAttribute('aria-current','page');
    var portLink=nav.querySelector('a[href="./port_trading.html"]');
    if(!portLink){
      portLink=document.createElement('a');portLink.href='./port_trading.html';
      portLink.innerHTML='<span>Port</span>';
    }
    craftLink.after(portLink);
    market.after(shopLink);
    portLink.hidden=!hasSeat;
    portLink.removeAttribute('data-econ-gate');
    if(!portLink.querySelector('.port-nav-icon')){
      var portIcon=document.createElement('img');portIcon.className='port-nav-icon';
      portIcon.src='./assets/game-art/nav/port.svg';portIcon.alt='';
      portIcon.width=28;portIcon.height=28;portIcon.setAttribute('aria-hidden','true');
      portLink.prepend(portIcon);
    }
    if(port)portLink.setAttribute('aria-current','page');
    nav.style.setProperty('--game-nav-columns','7');
  });
  if(document.querySelector('.game-nav[data-craft-nav]')){
    var craftNavStyle=document.createElement('style');
    craftNavStyle.textContent='.game-nav .craft-nav-icon{display:inline-block;width:28px;height:28px;flex:0 0 28px;background:url("./assets/craft/craft-items.png?v=1") no-repeat -34.51px -32.57px / 190.46px 158.71px;image-rendering:pixelated;}.game-nav .shop-nav-icon{width:28px;height:28px;flex:0 0 28px;display:grid;place-items:center;color:#ffb000;font-size:27px;line-height:1;}.game-nav .port-nav-icon{width:28px;height:28px;object-fit:contain;image-rendering:pixelated;flex:none;}.game-nav a[hidden]{display:none!important;}@media(max-width:900px){.game-page .game-page-head .game-nav[data-craft-nav],.game-page .game-nav[data-craft-nav]{display:grid;grid-template-columns:repeat(var(--game-nav-columns,5),minmax(0,1fr));}.game-nav[data-craft-nav] a{min-width:0;}}@media(max-width:550px){.game-nav[data-craft-nav] a{flex-direction:column;gap:2px;padding-inline:1px;font-size:14px;letter-spacing:0;}.game-nav[data-craft-nav] a img,.game-nav[data-craft-nav] .craft-nav-icon{display:none;}.game-nav[data-craft-nav] a .port-nav-icon{display:block;width:18px;height:18px;}}@media(max-width:380px){.game-page .game-nav[data-craft-nav] a{font-size:11px;}}';
    document.head.appendChild(craftNavStyle);
  }
  // Pages out of play. advanced-hq.html is Operations: the server redirects it
  // away as well (server.RETIRED_PAGES), this only keeps the link out of sight.
  document.querySelectorAll('a[href*="produce.html"],a[href*="collect.html"],a[href*="advanced-hq.html"]').forEach(function(a){a.hidden=true;});
  document.querySelectorAll('a[href="./port_trading.html"]').forEach(function(a){
    a.hidden=!hasSeat;
    a.removeAttribute('data-econ-gate');
    a.title='Port · earn your licence to trade';
  });
  window.addEventListener('yomama:econ',function(event){
    document.querySelectorAll('a[href="./port_trading.html"]').forEach(function(a){
      a.hidden=!hasSeat;
      a.title=event.detail.gateOpen?'Open Port':'Port · earn your licence to trade';
      a.classList.toggle('is-locked',!event.detail.gateOpen);
    });
  });
  document.querySelectorAll('.game-nav[data-craft-nav]').forEach(function(nav){
    var count=Array.from(nav.querySelectorAll('a')).filter(function(a){return !a.hidden;}).length;
    nav.style.setProperty('--game-nav-columns',String(count));
  });
}());
