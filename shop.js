/* Live craft-supply storefront. The class save owns stock, cash and prices. */
(function () {
  'use strict';
  var root=document.getElementById('supply-shop');if(!root)return;
  var session={};try{session=JSON.parse(localStorage.getItem('yomama_session_v1')||'{}')||{};}catch(_){}
  var state=null,category='all',basket={},busy=false,pending=null,refreshing=null;
  var basketStep=10,basketLimit=100;
  var featured=['craft_roastery_roasted_beans','wooden_boards','packaging','metal_sheets','craft_workshop_steel_brackets','craft_garage_spare_parts'];
  var basics={wooden_boards:1,fiber_bundles:1,packaging:1,paper_sheets:1,textile_cloth:1,food_safe_containers:1};
  var el=function(id){return document.getElementById(id);};
  var esc=function(value){return String(value==null?'':value).replace(/[&<>"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];});};
  var money=function(n){return Math.round(n||0).toLocaleString('en-US')+' YM';};
  function note(message,tone){el('shop-status').textContent=message;el('shop-status').dataset.tone=tone||'';}
  function request(path,body){
    var options={method:body?'POST':'GET',cache:'no-store',headers:{}};
    if(body){options.headers['Content-Type']='application/json';options.body=JSON.stringify(Object.assign({},body,{token:session.token||''}));}
    var controller=new AbortController();options.signal=controller.signal;
    var timeout=setTimeout(function(){controller.abort();},20000);
    return fetch(path,options).then(function(response){return response.json().catch(function(){return {};}).then(function(data){
      if(!response.ok||data.ok===false){var error=new Error(data.why||data.error||'Could not reach the shop.');error.status=response.status;throw error;}
      return data;
    });}).finally(function(){clearTimeout(timeout);});
  }
  function catalog(){return state&&state.crafting&&state.crafting.supplies||[];}
  function craftUses(){
    var uses={};
    ((state&&state.crafting&&state.crafting.items)||[]).forEach(function(product){
      if(!product.pilot||!product.available||(!product.unlocked&&(product.buildingLocked||product.progressionLocked)))return;
      (product.ingredients||[]).forEach(function(ingredient){
        if(ingredient.kind!=='supply')return;
        (uses[ingredient.id]||(uses[ingredient.id]=[])).push(product.name);
      });
    });
    return uses;
  }
  function group(item){return item.id.indexOf('craft_')===0?'parts':basics[item.id]?'basics':'materials';}
  function item(id){return catalog().find(function(row){return row.id===id;});}
  function art(supply){
    var id=supply.id;
    if(id.indexOf('craft_')===0){
      var good=id.indexOf('craft_input_')===0?id.slice(12):id.slice(6);
      if(good==='cannery_preserves')good='cannery_canned_goods';
      return '<span class="shop-art shop-art-good" style="background-image:url(\'./assets/game-art/goods/'+encodeURIComponent(good)+'.png\')" aria-hidden="true"></span>';
    }
    var index=catalog().findIndex(function(row){return row.id===id;});
    var sheets=window.YomamaCraftArt&&window.YomamaCraftArt.supplies||[];
    var sheet=sheets.find(function(entry){return index>=entry.start&&index<entry.start+entry.rects.length;});
    if(!sheet)return '<span class="shop-art" aria-hidden="true">◇</span>';
    var rect=sheet.rects[index-sheet.start],size=Math.max(rect[2],rect[3]);
    var style='--sprite-image:url('+sheet.src+');--sprite-width:'+(rect[2]/size*100)+'%;--sprite-height:'+(rect[3]/size*100)+'%;--sprite-sheet-width:'+(sheet.width/rect[2]*100)+'%;--sprite-sheet-height:'+(sheet.height/rect[3]*100)+'%;--sprite-x:'+(rect[0]/(sheet.width-rect[2])*100)+'%;--sprite-y:'+(rect[1]/(sheet.height-rect[3])*100)+'%';
    return '<span class="shop-art" style="'+style+'" aria-hidden="true"></span>';
  }
  function renderProducts(){
    var host=el('shop-products'),oldScroll=host.scrollTop;
    var uses=category==='craft'?craftUses():{};
    var rows=catalog().filter(function(row){return category==='all'||(category==='craft'?!!uses[row.id]:group(row)===category);}).slice().sort(function(a,b){
      var ai=featured.indexOf(a.id),bi=featured.indexOf(b.id);
      if(ai<0)ai=1000;if(bi<0)bi=1000;
      return ai-bi||a.name.localeCompare(b.name);
    });
    host.innerHTML=rows.length?rows.map(function(row){var names=uses[row.id]||[];var useLabel=names.length>2?names.slice(0,2).join(', ')+' +'+(names.length-2)+' more':names.join(', ');return '<article class="shop-product" data-selected="'+!!basket[row.id]+'">'+art(row)+'<div class="shop-product-copy"><strong>'+esc(row.name)+'</strong><small>'+money(row.unitPrice)+'</small><em>Owned '+(row.quantity||0)+'</em>'+(category==='craft'?'<span class="shop-product-use" title="'+esc(names.join(', '))+'">For '+esc(useLabel)+'</span>':'')+'</div><button type="button" class="shop-add" data-shop-add="'+esc(row.id)+'" aria-label="Add '+basketStep+' '+esc(row.name)+' to basket"'+(busy||pending||basket[row.id]>=basketLimit?' disabled':'')+'>+</button></article>';}).join(''):'<p class="shop-catalog-empty">'+(category==='craft'?'No bright or unlocked craft products need shop supplies yet.':'No supplies in this category.')+'</p>';
    host.scrollTop=oldScroll;
  }
  function renderBasket(){
    var ids=Object.keys(basket).filter(function(id){return basket[id]>0&&item(id);});
    var total=ids.reduce(function(value,id){return value+item(id).unitPrice*basket[id];},0);
    var count=ids.reduce(function(value,id){return value+basket[id];},0);
    el('shop-basket-count').textContent=count+' ITEM'+(count===1?'':'S');
    el('shop-total').textContent=money(total);
    el('shop-basket-rows').innerHTML=ids.length?ids.map(function(id){var row=item(id);return '<div class="shop-basket-row">'+art(row)+'<div><strong>'+esc(row.name)+'</strong><small>'+money(row.unitPrice)+' EACH</small></div><div class="shop-quantity"><button type="button" data-shop-change="'+esc(id)+'" data-delta="-'+basketStep+'" aria-label="Remove '+basketStep+' '+esc(row.name)+'"'+(busy||pending?' disabled':'')+'>−</button><output>'+basket[id]+'</output><button type="button" data-shop-change="'+esc(id)+'" data-delta="'+basketStep+'" aria-label="Add '+basketStep+' '+esc(row.name)+'"'+(busy||pending||basket[id]>=basketLimit?' disabled':'')+'>+</button></div><div class="shop-basket-line-total">'+money(row.unitPrice*basket[id])+'</div></div>';}).join(''):'<p class="shop-empty">Pick a supply to get started.</p>';
    var buy=el('shop-buy');buy.textContent=pending?'RETRY CHECKOUT':'BUY SUPPLIES';buy.disabled=busy||!ids.length||!!(state&&state.paused)||(!pending&&total>(state&&state.cash||0));
    buy.title=state&&state.paused?'Class is paused':!ids.length?'Add supplies to your basket':total>(state&&state.cash||0)?'Need '+money(total-state.cash)+' more':'';
  }
  function render(){if(!state)return;renderProducts();renderBasket();}
  function apply(payload){state=payload;window.dispatchEvent(new CustomEvent('yomama:econ',{detail:payload}));render();}
  function refresh(force){
    if(refreshing)return refreshing;
    if(!force&&document.hidden)return Promise.resolve();
    refreshing=request('/api/game/econ/state?token='+encodeURIComponent(session.token||'')).then(function(payload){
      if(!pending)apply(payload);
      else{state=payload;render();}
    }).catch(function(error){note(error.status===401||error.status===403?error.message:'Connection interrupted. Retry in a moment.','error');}).finally(function(){refreshing=null;});
    return refreshing;
  }
  function change(id,delta){
    if(busy||pending||!item(id))return;
    basket[id]=Math.min(basketLimit,Math.max(0,(basket[id]||0)+delta));if(!basket[id])delete basket[id];
    render();if(Object.keys(basket).length)note('Basket ready. Your purchase saves to this class seat.');
  }
  function requestId(){if(crypto.randomUUID)return crypto.randomUUID();var bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,function(n){return n.toString(16).padStart(2,'0');}).join('');}
  function checkout(){
    if(busy||!state||state.paused)return;
    if(!pending){
      var items=Object.keys(basket).filter(function(id){return basket[id]>0;}).map(function(id){return {supplyId:id,quantity:basket[id]};});
      if(!items.length)return;
      var total=items.reduce(function(value,row){return value+item(row.supplyId).unitPrice*row.quantity;},0);
      if(total>state.cash){note('Need '+money(total-state.cash)+' more for this basket.','error');return;}
      pending={action:'buy_supplies',items:items,requestId:requestId(),revision:state.crafting.revision};
    }
    busy=true;note('Packing your supplies…');render();
    request('/api/game/craft',pending).then(function(payload){
      var receipt=payload.receipt||{},count=pending.items.reduce(function(value,row){return value+row.quantity;},0);
      pending=null;basket={};apply(payload);
      note('Bought '+count+' supplies for '+money(receipt.cost)+'. Ready in Craft.','success');
      var box=root.querySelector('.shop-basket');box.classList.remove('is-delivered');void box.offsetWidth;box.classList.add('is-delivered');
      sellerReact('purchase');
    }).catch(function(error){
      if(error.status){pending=null;refresh(true);}
      note(error.status?error.message:'Could not confirm the purchase. Use Retry checkout to check it safely.','error');
    }).finally(function(){busy=false;render();});
  }
  root.addEventListener('click',function(event){
    var button=event.target.closest('button');if(!button)return;
    if(button.dataset.shopCategory){category=button.dataset.shopCategory;root.querySelectorAll('[data-shop-category]').forEach(function(tab){tab.setAttribute('aria-pressed',String(tab===button));});el('shop-products').scrollTop=0;renderProducts();return;}
    if(button.dataset.shopAdd){change(button.dataset.shopAdd,basketStep);return;}
    if(button.dataset.shopChange){change(button.dataset.shopChange,Number(button.dataset.delta)||0);return;}
    if(button.id==='shop-buy')checkout();
  });
  // Show one still portrait while the shop art is static.
  var canvas=el('shopkeeper'),ctx=canvas.getContext('2d'),atlas=new Image();
  function sellerReact(kind){el('shop-speech').textContent=kind==='purchase'?'Good choice. I got you.':'I got what you need.';}
  atlas.onload=function(){ctx.clearRect(0,0,canvas.width,canvas.height);ctx.imageSmoothingEnabled=false;ctx.drawImage(atlas,0,0,512,512,0,0,canvas.width,canvas.height);};
  atlas.src='./assets/shop/shopkeeper-sprites-v2.png';
  if(!session.token){note('Sign in to visit the supply shop.','error');return;}
  request('/api/game/econ/login',{}).then(function(payload){apply(payload);note('Your craft supplies are ready to order. Cash '+money(payload.cash)+'.');}).catch(function(error){note(error.message||'Cannot reach your class.','error');});
  setInterval(function(){if(!busy)refresh(false);},15000);
})();
