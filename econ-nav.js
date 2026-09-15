/* PORT is available to every signed-in seat in the GAME navigation. */
(function(){
  'use strict';
  var port=location.pathname.endsWith('/port_trading.html');
  var hasSeat=false;
  try{hasSeat=!!(JSON.parse(localStorage.getItem('yomama_session_v1')||'null')||{}).token;}catch(_){}
  // Also cover older static headers on pages that do not load app.js.
  document.querySelectorAll('.hero .tabs a[href*="port_trading.html"]').forEach(function(a){a.remove();});
  if(port){
    document.querySelectorAll('.hero .tabs a[href*="buildings.html"]').forEach(function(a){
      a.classList.add('active');a.setAttribute('aria-current','page');
    });
  }
  // Keep every business menu in the same order, including older saved pages.
  document.querySelectorAll('.game-nav').forEach(function(nav){
    var market=nav.querySelector('a[href*="marketplace.html"]');
    if(!market)return;
    nav.dataset.craftNav='true';
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
    var portLink=nav.querySelector('a[href*="port_trading.html"]');
    if(!portLink){
      portLink=document.createElement('a');portLink.href='./port_trading.html';
      portLink.innerHTML='<span>PORT</span>';
    }
    craftLink.after(portLink);
    portLink.hidden=!hasSeat;
    portLink.removeAttribute('data-econ-gate');
    if(!portLink.querySelector('.port-nav-icon')){
      var portIcon=document.createElement('img');portIcon.className='port-nav-icon';
      portIcon.src='./assets/game-art/nav/port.svg';portIcon.alt='';
      portIcon.width=28;portIcon.height=28;portIcon.setAttribute('aria-hidden','true');
      portLink.prepend(portIcon);
    }
    if(port)portLink.setAttribute('aria-current','page');
    nav.style.setProperty('--game-nav-columns','6');
  });
  if(document.querySelector('.game-nav[data-craft-nav]')){
    var craftNavStyle=document.createElement('style');
    craftNavStyle.textContent='.game-nav .craft-nav-icon{display:inline-block;width:28px;height:28px;flex:0 0 28px;background:url("./assets/craft/craft-items.png?v=1") no-repeat -34.51px -32.57px / 190.46px 158.71px;image-rendering:pixelated;}.game-nav .port-nav-icon{width:28px;height:28px;object-fit:contain;image-rendering:pixelated;flex:none;}.game-nav a[hidden]{display:none!important;}@media(max-width:900px){.game-page .game-page-head .game-nav[data-craft-nav],.game-page .game-nav[data-craft-nav]{display:grid;grid-template-columns:repeat(var(--game-nav-columns,5),minmax(0,1fr));}.game-nav[data-craft-nav] a{min-width:0;}}@media(max-width:550px){.game-nav[data-craft-nav] a{flex-direction:column;gap:2px;padding-inline:1px;font-size:14px;letter-spacing:0;}.game-nav[data-craft-nav] a img,.game-nav[data-craft-nav] .craft-nav-icon{display:none;}.game-nav[data-craft-nav] a .port-nav-icon{display:block;width:18px;height:18px;}}@media(max-width:380px){.game-page .game-nav[data-craft-nav] a{font-size:11px;}}';
    document.head.appendChild(craftNavStyle);
  }
  document.querySelectorAll('a[href*="produce.html"],a[href*="collect.html"],a[href*="focus-tree.html"]').forEach(function(a){a.hidden=true;});
  document.querySelectorAll('a[href*="port_trading.html"]').forEach(function(a){
    a.hidden=!hasSeat;
    a.removeAttribute('data-econ-gate');
    a.title='Open PORT';
  });
  document.querySelectorAll('.game-nav[data-craft-nav]').forEach(function(nav){
    var count=Array.from(nav.querySelectorAll('a')).filter(function(a){return !a.hidden;}).length;
    nav.style.setProperty('--game-nav-columns',String(count));
  });
}());
