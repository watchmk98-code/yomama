/* Navigation and Part 2 access depend on the authoritative licence. */
(function(){
  'use strict';
  // Keep every business menu in the same order, including older saved pages.
  document.querySelectorAll('.game-nav').forEach(function(nav){
    var market=nav.querySelector('a[href*="marketplace.html"]');
    if(!market)return;
    nav.dataset.craftNav='true';
    if(!nav.querySelector('a[href*="craft.html"]')){
      var craft=document.createElement('a');craft.href='./craft.html';
      craft.innerHTML='<span>Craft</span>';market.after(craft);
    }
    if(location.pathname.endsWith('/craft.html'))nav.querySelector('a[href*="craft.html"]').setAttribute('aria-current','page');
  });
  if(document.querySelector('.game-nav[data-craft-nav]')){
    var craftNavStyle=document.createElement('style');
    craftNavStyle.textContent='@media(max-width:900px){.game-page .game-page-head .game-nav[data-craft-nav],.game-page .game-nav[data-craft-nav]{grid-template-columns:repeat(5,minmax(0,1fr));}.game-nav[data-craft-nav] a{min-width:0;}}@media(max-width:550px){.game-nav[data-craft-nav] a{flex-direction:column;gap:2px;padding-inline:1px;font-size:14px;}.game-nav[data-craft-nav] a img{display:none;}}';
    document.head.appendChild(craftNavStyle);
  }
  document.querySelectorAll('a[href*="produce.html"],a[href*="collect.html"],a[href*="focus-tree.html"]').forEach(function(a){a.hidden=true;});
  var links=Array.from(document.querySelectorAll('a[href*="port_trading.html"]'));
  links.forEach(function(a){a.hidden=true;});
  function apply(s){links.forEach(function(a){a.hidden=!s.gateOpen;});}
  window.addEventListener('yomama:econ',function(e){apply(e.detail);});
  var port=location.pathname.endsWith('/port_trading.html');
  if(!port && document.querySelector('[id^="econ-"]'))return;
  var token='';try{token=(JSON.parse(localStorage.getItem('yomama_session_v1')||'null')||{}).token||'';}catch(_){}
  var overlay;
  if(port){overlay=document.createElement('dialog');overlay.textContent='Checking your analyst licence…';document.body.appendChild(overlay);overlay.showModal();}
  fetch('/api/game/econ/state?token='+encodeURIComponent(token)).then(function(r){if(!r.ok)throw Error('Unable to check your licence');return r.json();}).then(function(s){
    apply(s);if(port){if(!s.gateOpen)location.replace('./license.html');else overlay.remove();}
  }).catch(function(){if(overlay)overlay.textContent='Cannot reach the class server. Reload to check your licence.';});
}());
