(() => {
  const fighters = Array.from(document.querySelectorAll('.memos-fighter'));
  if (!fighters.length) return;

  const prefersReducedMotion = Boolean(
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  const leaderboardMotionEnabled = !prefersReducedMotion;
  const roster = document.querySelector('.memos-roster');
  if (roster instanceof HTMLElement) {
    roster.style.setProperty('--memos-rows', String(Math.max(fighters.length, 1)));
  }

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
  const leaderboardTimeouts = new WeakMap();

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
    const timersByClass = leaderboardTimeouts.get(element) || new Map();
    clearQueuedTimeout(timersByClass.get(className));
    const timeoutId = queueTimeout(() => {
      element.classList.remove(className);
      timersByClass.delete(className);
      if (!timersByClass.size) leaderboardTimeouts.delete(element);
    }, delay);
    timersByClass.set(className, timeoutId);
    leaderboardTimeouts.set(element, timersByClass);
  };

  const parsePointsValue = (textValue) => {
    const numeric = Number.parseInt(String(textValue || '').replace(/[^\d-]/gu, ''), 10);
    return Number.isFinite(numeric) ? numeric : 0;
  };

  const leaderboardFrameStorageKey = 'memos_leaderboard_timeframe';
  const timeframeButtons = Array.from(document.querySelectorAll('.memos-timeframe-btn[data-timeframe]'));
  const timeframeMetaItems = Array.from(document.querySelectorAll('.memos-timeframe-meta-item[data-timeframe-meta]'));
  const timeframeMetaNodes = timeframeMetaItems.reduce((accumulator, node) => {
    const key = String(node.getAttribute('data-timeframe-meta') || '').trim().toLowerCase();
    if (key) accumulator[key] = node;
    return accumulator;
  }, {});
  const leaderboardFrames = {
    daily: {
      key: 'daily',
      min: 7000,
      max: 11000,
      deltaMin: -135,
      deltaMax: 210,
      tickMs: 2000,
      updatesMin: 2,
      updatesMax: 4,
      forceOrderChange: true,
    },
    weekly: {
      key: 'weekly',
      min: 30000,
      max: 70000,
      deltaMin: -95,
      deltaMax: 140,
      tickMs: 12000,
      updatesMin: 1,
      updatesMax: 1,
      forceOrderChange: false,
    },
    monthly: {
      key: 'monthly',
      min: 120000,
      max: 260000,
      deltaMin: -240,
      deltaMax: 360,
      tickMs: 22000,
      updatesMin: 1,
      updatesMax: 1,
      forceOrderChange: false,
    },
  };
  const normalizeFrameKey = (value) => {
    const normalized = String(value || '').trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(leaderboardFrames, normalized) ? normalized : '';
  };
  const queryParams = new URLSearchParams(window.location.search);
  const queryFrame = normalizeFrameKey(queryParams.get('tf'));
  let storedFrame = '';
  try {
    storedFrame = normalizeFrameKey(window.localStorage.getItem(leaderboardFrameStorageKey));
  } catch (_) {}
  let activeLeaderboardFrame = queryFrame || storedFrame || 'daily';

  const persistFrameSelection = (frame) => {
    try {
      window.localStorage.setItem(leaderboardFrameStorageKey, frame);
    } catch (_) {}
    const nextParams = new URLSearchParams(window.location.search);
    nextParams.set('tf', frame);
    const nextQuery = nextParams.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash || ''}`;
    window.history.replaceState(null, '', nextUrl);
  };

  persistFrameSelection(activeLeaderboardFrame);

  const formatPointsValue = (value) => Math.round(value).toLocaleString('en-US');
  const formatDeltaValue = (value) => {
    const numeric = Number.isFinite(value) ? Math.round(value) : 0;
    if (numeric > 0) return `\u0394 +${Math.abs(numeric).toLocaleString('en-US')}`;
    if (numeric < 0) return `\u0394 -${Math.abs(numeric).toLocaleString('en-US')}`;
    return '\u0394 0';
  };
  const formatTimeStamp = (value) => {
    if (!(value instanceof Date) || Number.isNaN(value.getTime())) return '--:--:--';
    return value.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };
  const clamp01 = (value) => clamp(value, 0, 1);
  const getFrameConfig = () => leaderboardFrames[activeLeaderboardFrame] || leaderboardFrames.daily;
  const lastUpdatedByFrame = {
    daily: new Date(),
    weekly: new Date(),
    monthly: new Date(),
  };

  const setActiveFrameButton = () => {
    timeframeButtons.forEach((button) => {
      const isActive = button.dataset.timeframe === activeLeaderboardFrame;
      button.classList.toggle('is-active', isActive);
      button.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
  };

  const updateTimeframeMeta = () => {
    Object.keys(leaderboardFrames).forEach((frame) => {
      const node = timeframeMetaNodes[frame];
      if (!node) return;
      const prefix = frame === 'daily' ? 'D' : frame === 'weekly' ? 'W' : 'M';
      node.textContent = `${prefix}: ${formatTimeStamp(lastUpdatedByFrame[frame])}`;
      node.classList.toggle('is-active', frame === activeLeaderboardFrame);
    });
  };

  const applyPointsFlash = (entry, delta, frameConfig) => {
    if (!leaderboardMotionEnabled || !entry.pointsNode || !delta || !frameConfig) return;
    const pointsNode = entry.pointsNode;
    const pointsShell = pointsNode.closest('.memos-fighter-points');
    const currentPoints = entry.pointsByFrame[frameConfig.key];
    const deltaRange = Math.max(
      Math.abs(frameConfig.deltaMin),
      Math.abs(frameConfig.deltaMax),
      1,
    );
    const normalizedPoints = clamp01(
      (currentPoints - frameConfig.min) / Math.max(1, frameConfig.max - frameConfig.min),
    );
    const deltaIntensity = clamp01(Math.abs(delta) / deltaRange);
    const directionBias = delta > 0 ? normalizedPoints : (1 - normalizedPoints);
    const intensity = clamp01((deltaIntensity * 0.7) + (directionBias * 0.6));
    const flashRgb = delta > 0 ? '0,255,102' : '255,77,77';
    pointsNode.style.setProperty('--memos-points-flash-rgb', flashRgb);
    pointsNode.style.setProperty('--memos-points-flash-strength', intensity.toFixed(3));
    pointsNode.classList.remove('memos-points-up', 'memos-points-down');
    void pointsNode.offsetWidth;
    pointsNode.classList.add(delta > 0 ? 'memos-points-up' : 'memos-points-down');
    queueClassClear(pointsNode, 'memos-points-up', 420);
    queueClassClear(pointsNode, 'memos-points-down', 420);

    if (pointsShell) {
      pointsShell.classList.remove('memos-points-up', 'memos-points-down');
      void pointsShell.offsetWidth;
      pointsShell.classList.add(delta > 0 ? 'memos-points-up' : 'memos-points-down');
      queueClassClear(pointsShell, 'memos-points-up', 420);
      queueClassClear(pointsShell, 'memos-points-down', 420);
    }
  };

  const leaderboardState = fighters.map((fighter, index) => {
    const pointsNode = fighter.querySelector('.memos-points-value');
    const pointsShell = pointsNode ? pointsNode.closest('.memos-fighter-points') : null;
    let deltaNode = pointsShell ? pointsShell.querySelector('.memos-points-delta') : null;
    if (!deltaNode && pointsShell) {
      deltaNode = document.createElement('span');
      deltaNode.className = 'memos-points-delta';
      pointsShell.appendChild(deltaNode);
    }
    const rankNode = fighter.querySelector('.memos-rank');
    const nameNode = fighter.querySelector('.memos-fighter-name');
    const dailyPoints = parsePointsValue(pointsNode ? pointsNode.textContent : '');
    const weeklyPoints = clamp(Math.round((dailyPoints * rand(4.4, 5.6)) + rand(-900, 900)), leaderboardFrames.weekly.min, leaderboardFrames.weekly.max);
    const monthlyPoints = clamp(Math.round((dailyPoints * rand(17, 23)) + rand(-3000, 3000)), leaderboardFrames.monthly.min, leaderboardFrames.monthly.max);
    if (leaderboardMotionEnabled) {
      fighter.classList.add('memos-fighter-enter');
      fighter.style.setProperty('--memos-enter-delay', `${index * 46}ms`);
    }
    return {
      fighter,
      pointsNode,
      deltaNode,
      rankNode,
      nameNode,
      pointsByFrame: {
        daily: dailyPoints,
        weekly: weeklyPoints,
        monthly: monthlyPoints,
      },
      deltaByFrame: {
        daily: 0,
        weekly: 0,
        monthly: 0,
      },
      rank: index + 1,
    };
  });

  if (leaderboardMotionEnabled) {
    queueTimeout(() => {
      fighters.forEach((fighter) => fighter.classList.remove('memos-fighter-enter'));
    }, 1900);
  }

  const updateLeaderboardDom = () => {
    leaderboardState.forEach((entry, index) => {
      const nextRank = index + 1;
      entry.rank = nextRank;
      if (entry.rankNode) entry.rankNode.textContent = `#${nextRank}`;
      if (entry.pointsNode) {
        const points = entry.pointsByFrame[activeLeaderboardFrame];
        entry.pointsNode.textContent = formatPointsValue(points);
      }
      if (entry.deltaNode) {
        const delta = entry.deltaByFrame[activeLeaderboardFrame];
        entry.deltaNode.textContent = formatDeltaValue(delta);
        entry.deltaNode.classList.remove('is-up', 'is-down', 'is-flat');
        if (delta > 0) entry.deltaNode.classList.add('is-up');
        else if (delta < 0) entry.deltaNode.classList.add('is-down');
        else entry.deltaNode.classList.add('is-flat');
      }
    });
  };

  const applyRankMovement = (previousRanks) => {
    leaderboardState.forEach((entry) => {
      const oldRank = previousRanks.get(entry.fighter) || entry.rank;
      const rankMovement = oldRank - entry.rank;
      if (entry.rankNode) {
        entry.rankNode.classList.remove('memos-rank-up', 'memos-rank-down');
      }
      if (entry.nameNode) {
        entry.nameNode.classList.remove('memos-name-rank-up', 'memos-name-rank-down');
      }
      if (rankMovement > 0) {
        if (entry.rankNode && leaderboardMotionEnabled) {
          entry.rankNode.classList.add('memos-rank-up');
          queueClassClear(entry.rankNode, 'memos-rank-up', 620);
        }
        if (entry.nameNode && leaderboardMotionEnabled) {
          entry.nameNode.classList.add('memos-name-rank-up');
          queueClassClear(entry.nameNode, 'memos-name-rank-up', 900);
        }
      } else if (rankMovement < 0) {
        if (entry.rankNode && leaderboardMotionEnabled) {
          entry.rankNode.classList.add('memos-rank-down');
          queueClassClear(entry.rankNode, 'memos-rank-down', 620);
        }
        if (entry.nameNode && leaderboardMotionEnabled) {
          entry.nameNode.classList.add('memos-name-rank-down');
          queueClassClear(entry.nameNode, 'memos-name-rank-down', 900);
        }
      }
      if (entry.rankNode && rankMovement !== 0 && leaderboardMotionEnabled) {
        entry.rankNode.classList.remove('memos-rank-shift');
        void entry.rankNode.offsetWidth;
        entry.rankNode.classList.add('memos-rank-shift');
        queueClassClear(entry.rankNode, 'memos-rank-shift', 420);
      }
    });
  };

  const animateRowReorder = (beforeRects) => {
    if (!leaderboardMotionEnabled) return;
    leaderboardState.forEach((entry) => {
      const first = beforeRects.get(entry.fighter);
      const last = entry.fighter.getBoundingClientRect();
      const deltaY = first ? first.top - last.top : 0;
      if (!deltaY) return;
      entry.fighter.style.transition = 'none';
      entry.fighter.style.transform = `translateY(${deltaY.toFixed(2)}px)`;
      void entry.fighter.offsetWidth;
      entry.fighter.style.transition = 'transform 1100ms cubic-bezier(0.22, 1, 0.36, 1)';
      entry.fighter.style.transform = '';
      queueTimeout(() => {
        entry.fighter.style.transition = '';
      }, 1200);
    });
  };

  const reorderByActiveFrame = ({ forceOrderChange = false } = {}) => {
    if (!roster || leaderboardState.length < 2) return;
    const previousOrder = leaderboardState.map((entry) => entry.fighter);
    const previousRanks = new Map(leaderboardState.map((entry, index) => [entry.fighter, index + 1]));
    const beforeRects = new Map();
    leaderboardState.forEach((entry) => {
      beforeRects.set(entry.fighter, entry.fighter.getBoundingClientRect());
    });

    leaderboardState.sort(
      (a, b) => (b.pointsByFrame[activeLeaderboardFrame] - a.pointsByFrame[activeLeaderboardFrame]),
    );

    if (forceOrderChange) {
      const orderChanged = leaderboardState.some((entry, index) => entry.fighter !== previousOrder[index]);
      if (!orderChanged) {
        const swapIndex = Math.floor(rand(0, leaderboardState.length - 1.01));
        const a = leaderboardState[swapIndex];
        const b = leaderboardState[Math.min(leaderboardState.length - 1, swapIndex + 1)];
        if (a && b) {
          const key = activeLeaderboardFrame;
          const pointsA = a.pointsByFrame[key];
          a.pointsByFrame[key] = b.pointsByFrame[key];
          b.pointsByFrame[key] = pointsA;
          leaderboardState.sort(
            (left, right) => (right.pointsByFrame[key] - left.pointsByFrame[key]),
          );
        }
      }
    }

    updateLeaderboardDom();
    leaderboardState.forEach((entry) => roster.appendChild(entry.fighter));
    applyRankMovement(previousRanks);
    animateRowReorder(beforeRects);
  };

  leaderboardState.sort(
    (a, b) => (b.pointsByFrame[activeLeaderboardFrame] - a.pointsByFrame[activeLeaderboardFrame]),
  );
  leaderboardState.forEach((entry) => {
    if (roster) roster.appendChild(entry.fighter);
  });
  updateLeaderboardDom();
  setActiveFrameButton();
  updateTimeframeMeta();

  const runLeaderboardTick = () => {
    if (!roster || leaderboardState.length < 2) return;
    const frameConfig = getFrameConfig();
    const key = frameConfig.key;
    const updates = clamp(
      Math.round(rand(frameConfig.updatesMin, frameConfig.updatesMax)),
      1,
      leaderboardState.length,
    );
    const shuffled = [...leaderboardState].sort(() => Math.random() - 0.5);
    shuffled.slice(0, updates).forEach((entry) => {
      const prevPoints = entry.pointsByFrame[key];
      const delta = Math.round(rand(frameConfig.deltaMin, frameConfig.deltaMax));
      entry.pointsByFrame[key] = clamp(prevPoints + delta, frameConfig.min, frameConfig.max);
      entry.deltaByFrame[key] = delta;
      applyPointsFlash(entry, delta, frameConfig);
    });
    lastUpdatedByFrame[key] = new Date();
    updateTimeframeMeta();
    reorderByActiveFrame({ forceOrderChange: Boolean(frameConfig.forceOrderChange) });
  };

  const onTimeframeSelect = (nextFrame) => {
    if (!leaderboardFrames[nextFrame] || nextFrame === activeLeaderboardFrame) return;
    activeLeaderboardFrame = nextFrame;
    persistFrameSelection(activeLeaderboardFrame);
    setActiveFrameButton();
    updateTimeframeMeta();
    reorderByActiveFrame({ forceOrderChange: false });
    scheduleNextLeaderboardTick();
  };

  timeframeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const nextFrame = String(button.dataset.timeframe || '').toLowerCase();
      onTimeframeSelect(nextFrame);
    });
  });

  let leaderboardTickTimeoutId = null;
  const scheduleNextLeaderboardTick = (delayOverride) => {
    clearQueuedTimeout(leaderboardTickTimeoutId);
    const frameConfig = getFrameConfig();
    const delay = Number.isFinite(delayOverride) ? delayOverride : frameConfig.tickMs;
    leaderboardTickTimeoutId = queueTimeout(() => {
      leaderboardTickTimeoutId = null;
      runLeaderboardTick();
      scheduleNextLeaderboardTick();
    }, delay);
  };

  scheduleNextLeaderboardTick(1400);
  const navigateToAnalysisBio = (characterKey) => {
    if (!characterKey) return;
    window.location.href = `./analysis.html?character=${encodeURIComponent(characterKey)}`;
  };

  const startBarAnimation = (fighter, index) => {
    const canvas = fighter.querySelector('.memos-fighter-bg-canvas');
    if (!(canvas instanceof HTMLCanvasElement)) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const portrait = fighter.querySelector('.memos-fighter-portrait');
    const characterKey = String(fighter.getAttribute('data-character') || '').trim().toLowerCase();

    if (characterKey) {
      fighter.addEventListener('click', () => {
        navigateToAnalysisBio(characterKey);
      });
      fighter.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        navigateToAnalysisBio(characterKey);
      });
    }

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
      stepMinX: rand(20, 34),
      stepMinY: rand(14, 22),
      shiftX: rand(14, 34),
      shiftY: rand(8, 22),
      shiftMin: rand(1500, 2600),
      shiftMax: rand(2900, 5200),
      wobbleX: rand(4, 14),
      wobbleY: rand(3, 10),
      wobbleSpeed: rand(0.0011, 0.0024),
      targetMin: rand(2200, 3600),
      targetMax: rand(4800, 7600),
      pulseSpeed: rand(0.001, 0.0018),
      activityLow: rand(0.06, 0.11),
      activityMid: rand(0.12, 0.2),
      activityHigh: rand(0.22, 0.34),
    };

    let width = 1;
    let height = 1;
    let dpr = 1;
    let points = [];
    let rafId = 0;
    const target = { x: 0, y: 0 };
    const autoTarget = {
      fromX: 0,
      fromY: 0,
      toX: 0,
      toY: 0,
      start: 0,
      duration: 1,
      phase: Math.random() * Math.PI * 2,
    };
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
      probeCtx.drawImage(portrait, 0, 0);

      const { data, width: imageWidth, height: imageHeight } = probeCtx.getImageData(
        0,
        0,
        probeCanvas.width,
        probeCanvas.height,
      );
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

      if (maxX < minX) {
        portrait.style.setProperty('--memos-sprite-shift-x', '0px');
        return;
      }

      const opaqueCenter = alphaMass > 0 ? (weightedX / alphaMass) : ((minX + maxX) / 2);
      const naturalCenter = imageWidth / 2;
      const shell = portrait.closest('.memos-fighter-portrait-shell');
      const boxW = shell ? shell.clientWidth : (portrait.clientWidth || 72);
      const boxH = shell ? shell.clientHeight : (portrait.clientHeight || 88);
      const scale = Math.min(boxW / imageWidth, boxH / imageHeight) || 1;
      const shift = (naturalCenter - opaqueCenter) * scale;
      const opaqueWidth = Math.max(1, (maxX - minX) + 1);
      const spareHalfWidth = Math.max(0, (boxW - (opaqueWidth * scale)) * 0.5);
      const maxShift = Math.min(6, spareHalfWidth * 0.9);
      const clampedShift = clamp(shift, -maxShift, maxShift);
      portrait.style.setProperty('--memos-sprite-shift-x', `${clampedShift.toFixed(2)}px`);
    };

    if (portrait instanceof HTMLImageElement) {
      if (portrait.complete && portrait.naturalWidth > 0) {
        alignPortrait();
      } else {
        portrait.addEventListener('load', alignPortrait, { once: true });
      }
    }

    const getDistance = (a, b) => {
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      return dx * dx + dy * dy;
    };

    const sideOpacityAtX = (x) => {
      const half = width * 0.5;
      if (half <= 0) return 0;
      const normalized = Math.abs(x - half) / half;
      const eased = clamp(normalized, 0, 1);
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
        point.closest = distances.slice(0, config.nearestCount).map((entry) => entry.point);
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
          const point = {
            x: px,
            y: py,
            originX: px,
            originY: py,
            active: 0,
            glow: 0,
            radius: rand(1.1, 2.4),
            closest: [],
            shiftStart: 0,
            shiftDuration: 0,
            startX: px,
            startY: py,
            targetX: px,
            targetY: py,
          };
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
      if ((now - autoTarget.start) >= autoTarget.duration) {
        scheduleTarget(now);
      }
      const progress = clamp((now - autoTarget.start) / autoTarget.duration, 0, 1);
      const eased = easeInOutCirc(progress);
      const wave = now * config.wobbleSpeed + autoTarget.phase;
      const wobbleX = Math.sin(wave * 1.2) * config.wobbleX;
      const wobbleY = Math.cos(wave * 0.88) * config.wobbleY;
      target.x = clamp(autoTarget.fromX + (autoTarget.toX - autoTarget.fromX) * eased + wobbleX, 0, width);
      target.y = clamp(autoTarget.fromY + (autoTarget.toY - autoTarget.fromY) * eased + wobbleY, 0, height);
      colorBlend += (colorTarget - colorBlend) * 0.012;
    };

    const drawLines = (point) => {
      if (!point.active) return;
      const colorA = [
        Math.round(mix(primary[0], secondary[0], colorBlend)),
        Math.round(mix(primary[1], secondary[1], colorBlend)),
        Math.round(mix(primary[2], secondary[2], colorBlend)),
      ];
      const colorB = [
        Math.round(mix(secondary[0], tertiary[0], colorBlend)),
        Math.round(mix(secondary[1], tertiary[1], colorBlend)),
        Math.round(mix(secondary[2], tertiary[2], colorBlend)),
      ];

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
      const colorA = [
        Math.round(mix(primary[0], secondary[0], colorBlend)),
        Math.round(mix(primary[1], secondary[1], colorBlend)),
        Math.round(mix(primary[2], secondary[2], colorBlend)),
      ];
      const colorB = [
        Math.round(mix(secondary[0], tertiary[0], colorBlend)),
        Math.round(mix(secondary[1], tertiary[1], colorBlend)),
        Math.round(mix(secondary[2], tertiary[2], colorBlend)),
      ];
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
        if (distance < 3200) {
          point.active = config.activityHigh * activityPulse;
          point.glow = (config.activityHigh + 0.2) * activityPulse;
        } else if (distance < 14000) {
          point.active = config.activityMid * activityPulse;
          point.glow = (config.activityMid + 0.08) * activityPulse;
        } else if (distance < 30000) {
          point.active = config.activityLow * activityPulse;
          point.glow = (config.activityLow + 0.02) * activityPulse;
        } else {
          point.active = 0;
          point.glow = 0;
        }

        drawLines(point);
        drawPoint(point);
      });
    };

    const animate = (now) => {
      renderFrame(now);
      rafId = window.requestAnimationFrame(animate);
    };

    resize();
    renderFrame(performance.now());
    if (!prefersReducedMotion) {
      rafId = window.requestAnimationFrame(animate);
    }

    const resizeObserver = window.ResizeObserver
      ? new window.ResizeObserver(() => resize())
      : null;
    if (resizeObserver) resizeObserver.observe(fighter);

    const onResize = () => resize();
    window.addEventListener('resize', onResize, { passive: true });

    activeAnimations.push(() => {
      if (rafId) window.cancelAnimationFrame(rafId);
      window.removeEventListener('resize', onResize);
      if (resizeObserver) resizeObserver.disconnect();
    });
  };

  fighters.forEach((fighter, index) => startBarAnimation(fighter, index));

  const teardown = () => {
    activeAnimations.forEach((cleanup) => cleanup());
    activeTimeouts.forEach((timeoutId) => window.clearTimeout(timeoutId));
    activeTimeouts.clear();
  };

  window.addEventListener('pagehide', teardown, { once: true });
  window.addEventListener('beforeunload', teardown, { once: true });
})();
