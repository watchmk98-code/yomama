/* Fit the existing recipe dialog without changing purchases, focus, or content. */
(function () {
  'use strict';
  var dialog = document.getElementById('craft-dialog');
  if (!dialog) return;
  var observedBody = null;
  var frame = 0;
  var fitting = false;
  var bodyObserver = new MutationObserver(schedule);

  function number(value) { return parseFloat(value) || 0; }
  function set(name, value) { dialog.style.setProperty('--dialog-' + name, value + 'px'); }
  function schedule() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(fit);
  }
  function fit() {
    if (!dialog.open || fitting) return;
    var body = dialog.querySelector('.craft-dialog-body');
    if (!body) return;
    fitting = true;
    try {
      if (observedBody !== body) {
        bodyObserver.disconnect();
        bodyObserver.observe(body, {childList:true, characterData:true, subtree:true});
        observedBody = body;
      }
      var viewport = window.visualViewport;
      var width = viewport ? viewport.width : innerWidth;
      var height = viewport ? viewport.height : innerHeight;
      var wide = width >= 650 && height < 560;
      var small = width < 450;
      var short = height < 560;
      dialog.dataset.fitLayout = wide ? 'wide' : 'tall';
      set('padding', short ? 9 : small ? 11 : 14);
      set('title', short || small ? 28 : 36);
      set('caption', short ? 20 : small ? 21 : 24);
      set('heading', short ? 20 : 23);
      set('icon', short ? 34 : small ? 42 : height < 800 ? 50 : 66);
      set('name', short ? 18 : small ? 20 : 24);
      set('source', short ? 14 : small ? 16 : 18);
      set('number', short ? 24 : 28);
      set('number-width', small || short ? 38 : 48);
      set('buy', short ? 16 : 18);
      set('feedback', short ? 17 : 19);
      set('control', short ? 38 : 48);
      set('button', short ? 30 : 36);
      var artHeight = Math.min(wide ? 150 : 270, height * (wide ? .38 : .27), width * .7);
      set('art-height', artHeight);
      body.style.zoom = '1';
      body.style.width = 'auto';
      var style = getComputedStyle(dialog);
      var verticalFrame = number(style.paddingTop) + number(style.paddingBottom) + number(style.borderTopWidth) + number(style.borderBottomWidth);
      var availableHeight = Math.max(40, height - 20 - verticalFrame);
      var contentWidth = Math.max(40, dialog.clientWidth - number(style.paddingLeft) - number(style.paddingRight));
      body.style.width = contentWidth + 'px';
      var measuredHeight = body.getBoundingClientRect().height;
      if (measuredHeight > availableHeight) {
        // Preserve readable rows and controls by spending the artwork space first.
        artHeight = Math.max(wide ? 64 : 44, artHeight - (measuredHeight - availableHeight) - 4);
        set('art-height', artHeight);
      }
      // Long names, five buy rows, or a very small viewport can still need a
      // modest final scale. Zoom participates in layout, so no content is clipped.
      var scale = 1;
      for (var pass = 0; pass < 5; pass += 1) {
        var bounds = body.getBoundingClientRect();
        var contentHeight = Math.max(bounds.height, body.scrollHeight * scale);
        var horizontal = body.scrollWidth * scale;
        var correction = Math.min(1, availableHeight / Math.max(1, contentHeight), contentWidth / Math.max(1, horizontal));
        if (correction >= .999) break;
        scale *= correction * .99;
        body.style.zoom = String(scale);
        body.style.width = contentWidth / scale + 'px';
      }
      dialog.scrollTop = 0;
      dialog.scrollLeft = 0;
      dialog.dataset.fitReady = 'true';
    } finally { fitting = false; }
  }
  new MutationObserver(function () { if (dialog.open) schedule(); }).observe(dialog, {attributes:true, attributeFilter:['open']});
  window.addEventListener('resize', schedule);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', schedule);
  if (document.fonts) document.fonts.ready.then(schedule);
  window.YomamaCraftFitDialog = {fit:fit};
  schedule();
}());
