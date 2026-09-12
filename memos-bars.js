/* LEAD page: the class standings in the arcade look.

   Every row is a real seat in this browser's class. Names, net worth and
   ranks come from the classroom server (/api/game/state -> leaderboard)
   every fifteen seconds; PTS is net worth and the board is ranked by it.
   Each student gets a portrait from the hero set, chosen by a stable hash of
   class code and name, so it never changes between visits. The Daily /
   Weekly / Monthly switch picks which real gain the delta line shows: the
   server keeps each seat's opening figure per day. No sample fighters, no
   invented points. */
(() => {
  const roster = document.querySelector('.memos-roster');
  const template = document.getElementById('memos-fighter-template');
  const access = document.getElementById('memos-access');
  const accessMessage = document.getElementById('memos-access-message');
  if (!roster || !template) return;
  const net = window.YomamaNet;

  const prefersReducedMotion = Boolean(
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  const motion = !prefersReducedMotion;

  // ------------------------------------------------------------- helpers ---
  const parseColor = (value, fallback) => {
    const text = String(value || '').trim();
    if (/^#([a-f0-9]{3}|[a-f0-9]{6})$/i.test(text)) {
      const hex = text.slice(1);
      if (hex.length === 3) {
        return [
          Number.parseInt(hex[0] + hex[0], 16),
          Number.parseInt(hex[1] + hex[1], 16),
          Number.parseInt(hex[2] + hex[2], 16),
        ];
      }
      return [
        Number.parseInt(hex.slice(0, 2), 16),
        Number.parseInt(hex.slice(2, 4), 16),
        Number.parseInt(hex.slice(4, 6), 16),
      ];
    }
    const rgbMatch = text.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
    if (rgbMatch) {
      return [
        Number.parseInt(rgbMatch[1], 10),
        Number.parseInt(rgbMatch[2], 10),
        Number.parseInt(rgbMatch[3], 10),
      ];
    }
    return fallback;
  };
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const clamp01 = (value) => clamp(value, 0, 1);
  const rand = (min, max) => min + Math.random() * (max - min);
  const mix = (a, b, t) => a + (b - a) * t;
  const easeInOutCirc = (t) => {
    if (t < 0.5) return (1 - Math.sqrt(1 - 4 * t * t)) / 2;
    return (Math.sqrt(1 - ((-2 * t + 2) ** 2)) + 1) / 2;
  };
  const rootStyles = getComputedStyle(document.documentElement);
  const palette = [
    parseColor(rootStyles.getPropertyValue('--amber'), [255, 176, 0]),
    parseColor(rootStyles.getPropertyValue('--green'), [0, 255, 102]),
    parseColor(rootStyles.getPropertyValue('--red'), [255, 77, 77]),
  ];

  const activeAnimations = [];
  const activeTimeouts = new Set();
  const classTimeouts = new WeakMap();
  const queueTimeout = (callback, delay) => {
    const timeoutId = window.setTimeout(() => {
      activeTimeouts.delete(timeoutId);
      callback();
    }, delay);
    activeTimeouts.add(timeoutId);
    return timeoutId;
  };
  const clearQueuedTimeout = (timeoutId) => {
    if (!timeoutId) return;
    window.clearTimeout(timeoutId);
    activeTimeouts.delete(timeoutId);
  };
  const queueClassClear = (element, className, delay) => {
    if (!(element instanceof Element)) return;
    const timersByClass = classTimeouts.get(element) || new Map();
    clearQueuedTimeout(timersByClass.get(className));
    const timeoutId = queueTimeout(() => {
      element.classList.remove(className);
      timersByClass.delete(className);
      if (!timersByClass.size) classTimeouts.delete(element);
    }, delay);
    timersByClass.set(className, timeoutId);
    classTimeouts.set(element, timersByClass);
  };

  // ----------------------------------------------------------- portraits ---
  // Chosen by a stable hash of class code and name: the same student gets the
  // same face on every device and every visit; two students rarely share one.
  const PORTRAITS = ['buffett', 'can', 'dennis', 'derdo', 'hara', 'hussein', 'irene', 'marks', 'ozan', 'peaker', 'pelli'];
  const hashText = (text) => {
    let h = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h;
  };
  const portraitFor = (code, name) => PORTRAITS[hashText(String(code) + '/' + String(name)) % PORTRAITS.length];

  // ----------------------------------------------------- timeframe switch ---
  // Which real gain the delta line shows. The standings are always net worth.
  const frames = { daily: 'D', weekly: 'W', monthly: 'M' };
  const frameStorageKey = 'memos_leaderboard_timeframe';
  const timeframeButtons = Array.from(document.querySelectorAll('.memos-timeframe-btn[data-timeframe]'));
  const timeframeMetaNodes = Array.from(document.querySelectorAll('.memos-timeframe-meta-item[data-timeframe-meta]'))
    .reduce((acc, node) => {
      const key = String(node.getAttribute('data-timeframe-meta') || '').trim().toLowerCase();
      if (key) acc[key] = node;
      return acc;
    }, {});
  const normalizeFrameKey = (value) => {
    const key = String(value || '').trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(frames, key) ? key : '';
  };
  let storedFrame = '';
  try { storedFrame = normalizeFrameKey(window.localStorage.getItem(frameStorageKey)); } catch (_) {}
  let activeFrame = normalizeFrameKey(new URLSearchParams(window.location.search).get('tf')) || storedFrame || 'daily';
  const persistFrameSelection = (frame) => {
    try { window.localStorage.setItem(frameStorageKey, frame); } catch (_) {}
    const params = new URLSearchParams(window.location.search);
    params.set('tf', frame);
    const query = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`);
  };
  persistFrameSelection(activeFrame);

  const formatPointsValue = (value) => Math.round(value).toLocaleString('en-US');
  const formatDeltaValue = (value) => {
    const numeric = Number.isFinite(value) ? Math.round(value) : 0;
    if (numeric > 0) return `Δ +${Math.abs(numeric).toLocaleString('en-US')}`;
    if (numeric < 0) return `Δ -${Math.abs(numeric).toLocaleString('en-US')}`;
    return 'Δ 0';
  };
  const formatTimeStamp = (value) => {
    if (!(value instanceof Date) || Number.isNaN(value.getTime())) return '--:--:--';
    return value.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  };
  let lastUpdated = null;
  const setActiveFrameButton = () => {
    timeframeButtons.forEach((button) => {
      const isActive = button.dataset.timeframe === activeFrame;
      button.classList.toggle('is-active', isActive);
      button.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
  };
  const updateTimeframeMeta = () => {
    Object.keys(frames).forEach((frame) => {
      const node = timeframeMetaNodes[frame];
      if (!node) return;
      node.textContent = `${frames[frame]}: ${formatTimeStamp(lastUpdated)}`;
      node.classList.toggle('is-active', frame === activeFrame);
    });
  };

  // ---------------------------------------------------------------- rows ---
  const entries = new Map();   // name -> entry
  const showAccess = (text) => {
    roster.hidden = true;
    if (access) access.hidden = false;
    if (accessMessage) accessMessage.textContent = text;
  };
  const showRoster = () => {
    roster.hidden = false;
    if (access) access.hidden = true;
  };

  const applyPointsFlash = (entry, delta) => {
    if (!motion || !delta) return;
    const intensity = clamp01(0.35 + (Math.abs(delta) / Math.max(1, Math.abs(entry.netWorth) || 1)) * 4);
    const flashRgb = delta > 0 ? '0,255,102' : '255,77,77';
    [entry.pointsNode, entry.pointsShell].forEach((node) => {
      if (!node) return;
      node.style.setProperty('--memos-points-flash-rgb', flashRgb);
      node.style.setProperty('--memos-points-flash-strength', intensity.toFixed(3));
      node.classList.remove('memos-points-up', 'memos-points-down');
      void node.offsetWidth;
      node.classList.add(delta > 0 ? 'memos-points-up' : 'memos-points-down');
      queueClassClear(node, 'memos-points-up', 420);
      queueClassClear(node, 'memos-points-down', 420);
    });
  };

  const updateDom = () => {
    entries.forEach((entry) => {
      if (entry.rankNode) entry.rankNode.textContent = `#${entry.rank}`;
      if (entry.pointsNode) entry.pointsNode.textContent = formatPointsValue(entry.netWorth || 0);
      if (entry.deltaNode) {
        const delta = Number(entry.gain[activeFrame]) || 0;
        entry.deltaNode.textContent = formatDeltaValue(delta);
        entry.deltaNode.classList.remove('is-up', 'is-down', 'is-flat');
        entry.deltaNode.classList.add(delta > 0 ? 'is-up' : delta < 0 ? 'is-down' : 'is-flat');
      }
    });
  };

  const applyRankMovement = (previousRanks) => {
    entries.forEach((entry) => {
      const oldRank = previousRanks.get(entry.fighter) || entry.rank;
      const movement = oldRank - entry.rank;
      if (entry.rankNode) entry.rankNode.classList.remove('memos-rank-up', 'memos-rank-down');
      if (entry.nameNode) entry.nameNode.classList.remove('memos-name-rank-up', 'memos-name-rank-down');
      if (!motion || !movement) return;
      const dir = movement > 0 ? 'up' : 'down';
      if (entry.rankNode) {
        entry.rankNode.classList.add(`memos-rank-${dir}`);
        queueClassClear(entry.rankNode, `memos-rank-${dir}`, 620);
        entry.rankNode.classList.remove('memos-rank-shift');
        void entry.rankNode.offsetWidth;
        entry.rankNode.classList.add('memos-rank-shift');
        queueClassClear(entry.rankNode, 'memos-rank-shift', 420);
      }
      if (entry.nameNode) {
        entry.nameNode.classList.add(`memos-name-rank-${dir}`);
        queueClassClear(entry.nameNode, `memos-name-rank-${dir}`, 900);
      }
    });
  };

  const animateRowReorder = (beforeRects) => {
    if (!motion) return;
    entries.forEach((entry) => {
      const first = beforeRects.get(entry.fighter);
      const last = entry.fighter.getBoundingClientRect();
      const deltaY = first ? first.top - last.top : 0;
      if (!deltaY) return;
      entry.fighter.style.transition = 'none';
      entry.fighter.style.transform = `translateY(${deltaY.toFixed(2)}px)`;
      void entry.fighter.offsetWidth;
      entry.fighter.style.transition = 'transform 1100ms cubic-bezier(0.22, 1, 0.36, 1)';
      entry.fighter.style.transform = '';
      queueTimeout(() => { entry.fighter.style.transition = ''; }, 1200);
    });
  };

  const buildFighter = (student, code) => {
    const fragment = template.content.cloneNode(true);
    const fighter = fragment.querySelector('.memos-fighter');
    const key = portraitFor(code, student.name);
    fighter.classList.add(`player-${key}`);
    fighter.setAttribute('data-character', key);
    fighter.setAttribute('aria-label', `${student.name} standing`);
    const portrait = fighter.querySelector('.memos-fighter-portrait');
    portrait.src = `./assets/hero-select/player-${key}.png`;
    portrait.alt = `${student.name} pixel portrait`;
    const nameNode = fighter.querySelector('.memos-fighter-name');
    nameNode.textContent = student.name;
    const pointsNode = fighter.querySelector('.memos-points-value');
    const pointsShell = pointsNode ? pointsNode.closest('.memos-fighter-points') : null;
    const deltaNode = document.createElement('span');
    deltaNode.className = 'memos-points-delta';
    if (pointsShell) pointsShell.appendChild(deltaNode);
    if (motion) {
      fighter.classList.add('memos-fighter-enter');
      fighter.style.setProperty('--memos-enter-delay', `${entries.size * 46}ms`);
      queueTimeout(() => fighter.classList.remove('memos-fighter-enter'), 1900);
    }
    const entry = {
      name: student.name, fighter, portrait, nameNode,
      styleNode: fighter.querySelector('.memos-fighter-style'),
      pointsNode, pointsShell, deltaNode,
      rankNode: fighter.querySelector('.memos-rank'),
      netWorth: null, gain: { daily: 0, weekly: 0, monthly: 0 }, rank: 0, stop: null,
    };
    roster.appendChild(fighter);
    entry.stop = startBarAnimation(fighter, entries.size);
    return entry;
  };

  const applyBoard = (state) => {
    const board = Array.isArray(state && state.leaderboard) ? state.leaderboard.slice() : [];
    const code = state && state.session ? String(state.session.code || '') : '';
    board.sort((a, b) => ((Number(b.net_worth) || 0) - (Number(a.net_worth) || 0))
      || String(a.name).localeCompare(String(b.name)));
    if (!board.length) {
      entries.forEach((entry) => { if (entry.stop) entry.stop(); entry.fighter.remove(); });
      entries.clear();
      showAccess('Waiting for classmates to join.');
      return;
    }
    showRoster();
    const previousRanks = new Map();
    const beforeRects = new Map();
    entries.forEach((entry) => {
      previousRanks.set(entry.fighter, entry.rank);
      beforeRects.set(entry.fighter, entry.fighter.getBoundingClientRect());
    });
    const seen = new Set();
    board.forEach((student, index) => {
      const name = String(student.name || '');
      seen.add(name);
      let entry = entries.get(name);
      if (!entry) {
        entry = buildFighter({ name, you: Boolean(student.you) }, code);
        entries.set(name, entry);
      }
      const netWorth = Number(student.net_worth) || 0;
      if (entry.netWorth !== null && netWorth !== entry.netWorth) applyPointsFlash(entry, netWorth - entry.netWorth);
      entry.netWorth = netWorth;
      entry.gain = Object.assign({ daily: 0, weekly: 0, monthly: 0 }, student.gain || {});
      entry.rank = index + 1;
      entry.fighter.classList.toggle('is-you', Boolean(student.you));
      if (entry.styleNode) entry.styleNode.textContent = `${student.you ? 'You · ' : ''}Net worth · Class ${code}`;
      roster.appendChild(entry.fighter);
    });
    entries.forEach((entry, name) => {
      if (seen.has(name)) return;
      if (entry.stop) entry.stop();
      entry.fighter.remove();
      entries.delete(name);
    });
    roster.style.setProperty('--memos-rows', String(Math.max(entries.size, 1)));
    updateDom();
    applyRankMovement(previousRanks);
    animateRowReorder(beforeRects);
    lastUpdated = new Date();
    updateTimeframeMeta();
  };

  // ------------------------------------------------------------- server ---
  let busy = false;
  const refresh = (initial) => {
    if (busy) return Promise.resolve();
    if (!net || !net.isJoined()) {
      showAccess('Join a class to see your classmates on the board.');
      return Promise.resolve();
    }
    busy = true;
    const pending = initial
      ? net.connect().then((ok) => { if (!ok) throw new Error('offline'); return net.lastState(); })
      : net.refresh();
    return pending.then(applyBoard).catch(() => {
      if (!entries.size) {
        showAccess(net.isJoined() ? 'Class standings are unavailable. Reconnecting…'
                                  : 'Join a class to see your classmates on the board.');
      }
    }).finally(() => { busy = false; });
  };

  timeframeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const next = normalizeFrameKey(button.dataset.timeframe);
      if (!next || next === activeFrame) return;
      activeFrame = next;
      persistFrameSelection(activeFrame);
      setActiveFrameButton();
      updateTimeframeMeta();
      updateDom();
    });
  });
  setActiveFrameButton();
  updateTimeframeMeta();

  // --------------------------------------------- the glow behind each row ---
  function startBarAnimation(fighter, index) {
    const canvas = fighter.querySelector('.memos-fighter-bg-canvas');
    if (!(canvas instanceof HTMLCanvasElement)) return null;
    const context = canvas.getContext('2d');
    if (!context) return null;
    const portrait = fighter.querySelector('.memos-fighter-portrait');

    fighter.style.setProperty('--memos-fighter-chaos-a', `${rand(12, 26).toFixed(2)}s`);
    fighter.style.setProperty('--memos-fighter-chaos-b', `${rand(16, 34).toFixed(2)}s`);
    fighter.style.setProperty('--memos-fighter-overlay-opacity', `${rand(0.22, 0.4).toFixed(3)}`);
    fighter.style.setProperty('--memos-fighter-scan-opacity', `${rand(0.045, 0.11).toFixed(3)}`);
    fighter.style.setProperty('--memos-fighter-canvas-opacity', `${rand(0.25, 0.52).toFixed(3)}`);

    const primary = palette[index % palette.length];
    const secondary = palette[(index + 1) % palette.length];
    const tertiary = palette[(index + 2) % palette.length];
    const config = {
      nearestCount: Math.round(rand(3, 5)),
      stepMinX: rand(20, 34), stepMinY: rand(14, 22),
      shiftX: rand(14, 34), shiftY: rand(8, 22),
      shiftMin: rand(1500, 2600), shiftMax: rand(2900, 5200),
      wobbleX: rand(4, 14), wobbleY: rand(3, 10), wobbleSpeed: rand(0.0011, 0.0024),
      targetMin: rand(2200, 3600), targetMax: rand(4800, 7600),
      pulseSpeed: rand(0.001, 0.0018),
      activityLow: rand(0.06, 0.11), activityMid: rand(0.12, 0.2), activityHigh: rand(0.22, 0.34),
    };
    let width = 1;
    let height = 1;
    let dpr = 1;
    let points = [];
    let rafId = 0;
    const target = { x: 0, y: 0 };
    const autoTarget = { fromX: 0, fromY: 0, toX: 0, toY: 0, start: 0, duration: 1, phase: Math.random() * Math.PI * 2 };
    let colorBlend = Math.random();
    let colorTarget = Math.random();

    const alignPortrait = () => {
      if (!(portrait instanceof HTMLImageElement)) return;
      if (!portrait.naturalWidth || !portrait.naturalHeight) return;
      const probeCanvas = document.createElement('canvas');
      probeCanvas.width = portrait.naturalWidth;
      probeCanvas.height = portrait.naturalHeight;
      const probeCtx = probeCanvas.getContext('2d', { willReadFrequently: true });
      if (!probeCtx) return;
      let data;
      try {
        probeCtx.drawImage(portrait, 0, 0);
        data = probeCtx.getImageData(0, 0, probeCanvas.width, probeCanvas.height).data;
      } catch (_) { return; }
      const imageWidth = probeCanvas.width;
      const imageHeight = probeCanvas.height;
      let minX = imageWidth;
      let maxX = -1;
      let alphaMass = 0;
      let weightedX = 0;
      for (let y = 0; y < imageHeight; y += 1) {
        const rowBase = y * imageWidth * 4;
        for (let x = 0; x < imageWidth; x += 1) {
          const alpha = data[rowBase + (x * 4) + 3];
          if (alpha < 8) continue;
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          alphaMass += alpha;
          weightedX += x * alpha;
        }
      }
      if (maxX < minX) { portrait.style.setProperty('--memos-sprite-shift-x', '0px'); return; }
      const opaqueCenter = alphaMass > 0 ? (weightedX / alphaMass) : ((minX + maxX) / 2);
      const shell = portrait.closest('.memos-fighter-portrait-shell');
      const boxW = shell ? shell.clientWidth : (portrait.clientWidth || 72);
      const boxH = shell ? shell.clientHeight : (portrait.clientHeight || 88);
      const scale = Math.min(boxW / imageWidth, boxH / imageHeight) || 1;
      const shift = ((imageWidth / 2) - opaqueCenter) * scale;
      const spareHalfWidth = Math.max(0, (boxW - (Math.max(1, (maxX - minX) + 1) * scale)) * 0.5);
      const maxShift = Math.min(6, spareHalfWidth * 0.9);
      portrait.style.setProperty('--memos-sprite-shift-x', `${clamp(shift, -maxShift, maxShift).toFixed(2)}px`);
    };
    if (portrait instanceof HTMLImageElement) {
      if (portrait.complete && portrait.naturalWidth > 0) alignPortrait();
      else portrait.addEventListener('load', alignPortrait, { once: true });
    }

    const getDistance = (a, b) => { const dx = a.x - b.x; const dy = a.y - b.y; return dx * dx + dy * dy; };
    const sideOpacityAtX = (x) => {
      const half = width * 0.5;
      if (half <= 0) return 0;
      const eased = clamp(Math.abs(x - half) / half, 0, 1);
      return 0.22 + (eased * eased * (3 - 2 * eased) * 0.78);
    };
    const schedulePointShift = (point, now = performance.now()) => {
      point.shiftStart = now;
      point.shiftDuration = rand(config.shiftMin, config.shiftMax);
      point.startX = point.x;
      point.startY = point.y;
      point.targetX = point.originX - config.shiftX + Math.random() * config.shiftX * 2;
      point.targetY = point.originY - config.shiftY + Math.random() * config.shiftY * 2;
    };
    const assignClosest = () => {
      points.forEach((point, indexPoint) => {
        const distances = [];
        for (let i = 0; i < points.length; i += 1) {
          if (i === indexPoint) continue;
          distances.push({ point: points[i], distance: getDistance(point, points[i]) });
        }
        distances.sort((a, b) => a.distance - b.distance);
        point.closest = distances.slice(0, config.nearestCount).map((d) => d.point);
      });
    };
    const buildPoints = () => {
      points = [];
      const stepX = Math.max(config.stepMinX, width / rand(11, 18));
      const stepY = Math.max(config.stepMinY, height / rand(4, 7));
      for (let x = 0; x < width; x += stepX) {
        for (let y = 0; y < height; y += stepY) {
          const px = x + Math.random() * stepX;
          const py = y + Math.random() * stepY;
          const point = { x: px, y: py, originX: px, originY: py, active: 0, glow: 0, radius: rand(1.1, 2.4),
            closest: [], shiftStart: 0, shiftDuration: 0, startX: px, startY: py, targetX: px, targetY: py };
          schedulePointShift(point);
          points.push(point);
        }
      }
      assignClosest();
      target.x = width * 0.5;
      target.y = height * 0.5;
    };
    const scheduleTarget = (now = performance.now()) => {
      autoTarget.start = now;
      autoTarget.duration = rand(config.targetMin, config.targetMax);
      autoTarget.fromX = target.x;
      autoTarget.fromY = target.y;
      autoTarget.toX = rand(width * 0.06, width * 0.94);
      autoTarget.toY = rand(height * 0.12, height * 0.88);
      autoTarget.phase = Math.random() * Math.PI * 2;
      colorTarget = Math.random();
    };
    const resize = () => {
      const rect = fighter.getBoundingClientRect();
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildPoints();
      scheduleTarget(performance.now());
      alignPortrait();
    };
    const updateTarget = (now) => {
      if ((now - autoTarget.start) >= autoTarget.duration) scheduleTarget(now);
      const progress = clamp((now - autoTarget.start) / autoTarget.duration, 0, 1);
      const eased = easeInOutCirc(progress);
      const wave = now * config.wobbleSpeed + autoTarget.phase;
      target.x = clamp(autoTarget.fromX + (autoTarget.toX - autoTarget.fromX) * eased + Math.sin(wave * 1.2) * config.wobbleX, 0, width);
      target.y = clamp(autoTarget.fromY + (autoTarget.toY - autoTarget.fromY) * eased + Math.cos(wave * 0.88) * config.wobbleY, 0, height);
      colorBlend += (colorTarget - colorBlend) * 0.012;
    };
    const blend = (a, b) => [
      Math.round(mix(a[0], b[0], colorBlend)), Math.round(mix(a[1], b[1], colorBlend)), Math.round(mix(a[2], b[2], colorBlend)),
    ];
    const drawLines = (point) => {
      if (!point.active) return;
      const colorA = blend(primary, secondary);
      const colorB = blend(secondary, tertiary);
      point.closest.forEach((closePoint) => {
        const sideOpacity = sideOpacityAtX((point.x + closePoint.x) * 0.5);
        if (sideOpacity <= 0) return;
        const alpha = point.active * (0.82 + Math.random() * 0.24) * sideOpacity;
        context.beginPath();
        context.moveTo(Math.round(point.x), Math.round(point.y));
        context.lineTo(Math.round(closePoint.x), Math.round(closePoint.y));
        context.lineWidth = 1;
        context.strokeStyle = `rgba(${colorA[0]},${colorA[1]},${colorA[2]},${alpha})`;
        context.stroke();
        context.beginPath();
        context.moveTo(Math.round(point.x), Math.round(point.y));
        context.lineTo(Math.round(closePoint.x), Math.round(closePoint.y));
        context.lineWidth = 2;
        context.strokeStyle = `rgba(${colorB[0]},${colorB[1]},${colorB[2]},${alpha * 0.22})`;
        context.stroke();
      });
    };
    const drawPoint = (point) => {
      if (!point.glow) return;
      const colorA = blend(primary, secondary);
      const colorB = blend(secondary, tertiary);
      const sideOpacity = sideOpacityAtX(point.x);
      if (sideOpacity <= 0) return;
      const px = Math.round(point.x);
      const py = Math.round(point.y);
      const coreSize = Math.max(2, Math.round(point.radius * 1.4));
      const glowSize = coreSize + 2;
      context.fillStyle = `rgba(${colorA[0]},${colorA[1]},${colorA[2]},${point.glow * 0.42 * sideOpacity})`;
      context.fillRect(px - glowSize / 2, py - glowSize / 2, glowSize, glowSize);
      context.fillStyle = `rgba(${colorB[0]},${colorB[1]},${colorB[2]},${point.glow * 0.9 * sideOpacity})`;
      context.fillRect(px - coreSize / 2, py - coreSize / 2, coreSize, coreSize);
    };
    const renderFrame = (now) => {
      context.clearRect(0, 0, width, height);
      context.globalCompositeOperation = 'lighter';
      updateTarget(now);
      const activityPulse = 0.82 + (0.5 + 0.5 * Math.sin(now * config.pulseSpeed)) * 0.34;
      points.forEach((point) => {
        const progress = clamp((now - point.shiftStart) / point.shiftDuration, 0, 1);
        const eased = easeInOutCirc(progress);
        point.x = point.startX + (point.targetX - point.startX) * eased;
        point.y = point.startY + (point.targetY - point.startY) * eased;
        if (progress >= 1) schedulePointShift(point, now);
        const distance = getDistance(point, target);
        if (distance < 3200) { point.active = config.activityHigh * activityPulse; point.glow = (config.activityHigh + 0.2) * activityPulse; }
        else if (distance < 14000) { point.active = config.activityMid * activityPulse; point.glow = (config.activityMid + 0.08) * activityPulse; }
        else if (distance < 30000) { point.active = config.activityLow * activityPulse; point.glow = (config.activityLow + 0.02) * activityPulse; }
        else { point.active = 0; point.glow = 0; }
        drawLines(point);
        drawPoint(point);
      });
    };
    const animate = (now) => { renderFrame(now); rafId = window.requestAnimationFrame(animate); };
    resize();
    renderFrame(performance.now());
    if (motion) rafId = window.requestAnimationFrame(animate);
    const resizeObserver = window.ResizeObserver ? new window.ResizeObserver(() => resize()) : null;
    if (resizeObserver) resizeObserver.observe(fighter);
    const onResize = () => resize();
    window.addEventListener('resize', onResize, { passive: true });
    const stop = () => {
      if (rafId) window.cancelAnimationFrame(rafId);
      window.removeEventListener('resize', onResize);
      if (resizeObserver) resizeObserver.disconnect();
    };
    activeAnimations.push(stop);
    return stop;
  }

  // ------------------------------------------------------------ lifecycle ---
  refresh(true);
  let timer = window.setInterval(() => { if (document.visibilityState === 'visible') refresh(false); }, 15000);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') refresh(false); });
  window.addEventListener('storage', (event) => {
    if (!event.key || event.key === 'yomama_session_v1') window.location.reload();   // another tab changed seats
  });
  const teardown = () => {
    window.clearInterval(timer);
    activeAnimations.forEach((stop) => stop());
    activeTimeouts.forEach((timeoutId) => window.clearTimeout(timeoutId));
    activeTimeouts.clear();
  };
  window.addEventListener('pagehide', teardown, { once: true });
  window.addEventListener('beforeunload', teardown, { once: true });
})();
