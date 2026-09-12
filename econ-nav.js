/* Navigation and Part 2 access depend on the authoritative licence. */
(function(){
  'use strict';
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
