"""Serve a preview-only variation of the existing Market renderer."""
from __future__ import annotations


DELIVERY_CARD = r'''
  function deliveryDuration(seconds) {
    seconds=Math.max(0,Math.ceil(Number(seconds || 0)));
    return Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');
  }
  function timedDeliveryCard(o,i,s) {
    var seconds=Math.max(0,Number(o.deliveryRemainingSec || 0));
    var until=Date.now()+seconds*1000;
    var rarity=['standard','large','rare','jackpot'].includes(o.rarity)?o.rarity:'standard';
    return '<section class="k-card game-order game-order-cooldown" data-rarity="'+rarity+'" data-order-slot="'+i+'">'+orderReactionMarkup(i)+'<h3><span class="game-order-name">'+esc(o.name)+'</span><small class="game-order-tier">Delivering</small></h3><div class="game-order-context"><span class="game-order-channel">Delivery orders</span><p class="game-order-purpose">Goods reserved for this shipment.</p></div><div class="game-order-items game-preview-countdown"><span>Arrives in</span><strong data-preview-until="'+until+'" data-preview-paused="'+!!s.paused+'" data-preview-remaining="'+seconds+'" role="timer">'+deliveryDuration(seconds)+'</strong></div><div class="game-order-reward"><span>'+ym(o.reward)+'</span><small>Paid on arrival</small></div><div class="game-order-controls">'+bigButton('fulfill:'+i+':'+o.id,'Delivering','Payment on arrival',true)+'</div><button class="game-text-button" type="button" data-econ-action="replace:'+i+':'+o.id+'" disabled>Delivery in progress</button></section>';
  }
  function trackOrderArrivals(previous,next) {
    if(!previous)return;
    var delivery=(next.orderPreview || {}).lastDelivery;
    var prior=(previous.orderPreview || {}).lastDelivery;
    if(!delivery || (prior && prior.orderId===delivery.orderId))return;
    var jackpot=delivery.rarity==='jackpot';
    reactToOrder(0,'delivered',jackpot?'Delivered a jackpot order':'Delivered an order',jackpot?'gold-bars-pixel.svg':null);
    setStatus('Delivered · '+ym(delivery.reward)+(delivery.materials?' · +'+materialAmount(delivery.materials):''),'success');
  }
  var shipmentRefreshAt=0;
  window.setInterval(function(){
    document.querySelectorAll('[data-preview-until]').forEach(function(node){
      var paused=node.dataset.previewPaused==='true';
      var seconds=paused?Number(node.dataset.previewRemaining):Math.max(0,Math.ceil((Number(node.dataset.previewUntil)-Date.now())/1000));
      node.textContent=deliveryDuration(seconds);
      if(!paused && seconds===0 && Date.now()>shipmentRefreshAt){
        shipmentRefreshAt=Date.now()+1000;
        refresh();
      }
    });
  },250);

'''


def market_script(source):
    """Keep original emoji art/actions and display payment at delivery arrival."""
    changes = (
        ('  function ordersMarkup(s) {', DELIVERY_CARD + '  function ordersMarkup(s) {'),
        ('var o=entry.order,i=entry.index;if(o.project)return projectCard(o,i,s);',
         'var o=entry.order,i=entry.index;if(o.inTransit)return timedDeliveryCard(o,i,s);if(o.project)return projectCard(o,i,s);'),
        ("bigButton('fulfill:'+i+':'+o.id,'Deliver',o.canFulfill?'Ready':o.why || 'Waiting for goods',!o.canFulfill)",
         "bigButton('fulfill:'+i+':'+o.id,o.classId==='cooldown'?'Start delivery':'Deliver',o.canFulfill?(o.classId==='cooldown'?deliveryDuration(o.deliverySeconds)+' delivery':'Ready'):o.why || 'Waiting for goods',!o.canFulfill)"),
        ("if (busy) {\n      if(name.indexOf('replace:')===0)",
         "if(/^(fulfill|replace|commit):/.test(name)){var targeted=orderOffers(snapshot || {})[Number(name.split(':')[1])];if(targeted && targeted.inTransit)return;}\n    if (busy) {\n      if(name.indexOf('replace:')===0)"),
        ("if(nextOrder)act('replace:'+nextSlot+':'+nextOrder.id);",
         "if(nextOrder && !nextOrder.inTransit)act('replace:'+nextSlot+':'+nextOrder.id);"),
        ("if(deliveredOrder)reactToOrder(",
         "if(deliveredOrder && (!receipt || receipt.kind!=='order_dispatch'))reactToOrder("),
        ("    trackCustomerDeliveries(snapshot,payload);",
         "    trackCustomerDeliveries(snapshot,payload);\n    trackOrderArrivals(snapshot,payload);"),
        ("        else if (name.indexOf('fulfill:')===0) setStatus(",
         "        else if (receipt && receipt.kind==='order_dispatch') setStatus('Delivery started · payment on arrival','success');\n        else if (name.indexOf('fulfill:')===0) setStatus("),
    )
    for old, new in changes:
        if source.count(old) != 1:
            raise ValueError('Market renderer changed; check the preview patch: ' + old[:60])
        source = source.replace(old, new, 1)
    return source
