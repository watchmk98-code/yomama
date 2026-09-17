/* The original approved concept art is preserved, unchanged, in the atlas.
 * SVG viewports reveal its illustrations without including the mockup's UI.
 */
(function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var source = './assets/focus-tree/food-empire-atlas.png';
  var sourceWidth = 1536;
  var sourceHeight = 1024;
  var titleCount = 0;
  var clipCount = 0;
  var crops = {
    secure_harvest:       { x: 394,  y: 214, width: 137, height: 92 },
    reliable_supply:     { x: 393,  y: 340, width: 140, height: 90 },
    preserve_surplus:    { x: 101,  y: 465, width: 136, height: 92 },
    distribution_network:{ x: 100,  y: 592, width: 136, height: 93 },
    regional_supplier:   { x: 99,   y: 720, width: 137, height: 94 },
    local_brand:         { x: 702,  y: 463, width: 136, height: 95 },
    breakfast_regulars:  { x: 706,  y: 599, width: 135, height: 85 },
    signature_experience:{ x: 706,  y: 722, width: 135, height: 92 },
    food_empire:         { x: 405,  y: 837, width: 145, height: 97 },
    'local_brand-detail':{ x: 1145, y: 272, width: 315, height: 275 }
  };

  Object.keys(crops).forEach(function (id) { Object.freeze(crops[id]); });

  function createSvg(id, accessibleTitle) {
    var crop = crops[id] || crops.local_brand;
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', [crop.x, crop.y, crop.width, crop.height].join(' '));
    svg.setAttribute('width', crop.width);
    svg.setAttribute('height', crop.height);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('class', 'food-empire-art');
    svg.style.overflow = 'hidden';
    svg.style.imageRendering = 'pixelated';
    if (accessibleTitle) {
      var title = document.createElementNS(NS, 'title');
      title.id = 'food-empire-art-title-' + (++titleCount);
      title.textContent = String(accessibleTitle);
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-labelledby', title.id);
      svg.appendChild(title);
    } else {
      svg.setAttribute('aria-hidden', 'true');
    }
    var illustration = document.createElementNS(NS, 'image');
    // The viewport can letterbox in a responsive card. Clip the image to the
    // crop itself as well, so neighboring UI in the atlas cannot show there.
    var defs = document.createElementNS(NS, 'defs');
    var clip = document.createElementNS(NS, 'clipPath');
    clip.id = 'food-empire-art-clip-' + (++clipCount);
    clip.setAttribute('clipPathUnits', 'userSpaceOnUse');
    var rectangle = document.createElementNS(NS, 'rect');
    ['x', 'y', 'width', 'height'].forEach(function (key) {
      rectangle.setAttribute(key, crop[key]);
    });
    clip.appendChild(rectangle); defs.appendChild(clip); svg.appendChild(defs);
    illustration.setAttribute('clip-path', 'url(#' + clip.id + ')');
    illustration.setAttribute('href', source);
    illustration.setAttribute('x', '0');
    illustration.setAttribute('y', '0');
    illustration.setAttribute('width', sourceWidth);
    illustration.setAttribute('height', sourceHeight);
    svg.appendChild(illustration);
    return svg;
  }

  window.FoodEmpireArt = Object.freeze({
    source: source,
    sourceWidth: sourceWidth,
    sourceHeight: sourceHeight,
    crops: Object.freeze(crops),
    createSvg: createSvg
  });
})();
