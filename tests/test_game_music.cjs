const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'game-music.js'), 'utf8');
const prefsKey = 'yomama_music_v1';
const positionKey = 'yomama_music_position_shy_fx_this_style_v1';

class Events {
  constructor() { this.listeners = new Map(); }
  addEventListener(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(callback);
  }
  emit(type, details = {}) {
    for (const callback of this.listeners.get(type) || []) callback({ target: this, ...details });
  }
}

class Element extends Events {
  constructor(tagName) {
    super();
    this.tagName = tagName;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.className = '';
    this.textContent = '';
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      add: name => { this.className += ` ${name}`; },
    };
  }
  appendChild(child) { this.children.push(child); return child; }
  prepend(child) { this.children.unshift(child); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  matches(selector) {
    if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
    if (selector.startsWith('#')) return this.id === selector.slice(1);
    const attribute = selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
    if (attribute) return attribute[2] === undefined
      ? this.getAttribute(attribute[1]) !== null
      : this.getAttribute(attribute[1]) === attribute[2];
    return this.tagName === selector;
  }
  querySelector(selector) {
    for (const child of this.children) {
      if (child.matches(selector)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
  set innerHTML(html) {
    // These controls need element lookup, not a browser layout engine.
    this.children = [];
    for (const match of html.matchAll(/<([a-z][a-z0-9-]*)([^>]*)>/g)) {
      const child = new Element(match[1]);
      for (const attr of match[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) {
        child.setAttribute(attr[1], attr[2] ?? '');
        if (attr[1] === 'class') child.className = attr[2];
        if (attr[1] === 'id') child.id = attr[2];
      }
      this.children.push(child);
    }
  }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

class Audio extends Element {
  constructor() {
    super('audio');
    this.paused = true;
    this.readyState = 0;
    this.currentTime = 0;
    this.duration = NaN;
    this.error = null;
    this.attempts = [];
    this.loadCalls = 0;
  }
  set src(value) { this.setAttribute('src', value); }
  get src() { return this.getAttribute('src'); }
  play() {
    this.paused = false;
    return new Promise((resolve, reject) => { this.attempts.push({ resolve, reject }); });
  }
  pause() { this.paused = true; this.emit('pause'); }
  load() {
    this.loadCalls++;
    this.error = null;
    this.readyState = 0;
    this.currentTime = 0;
    this.duration = NaN;
  }
  metadata(duration = 300) {
    this.duration = duration;
    this.readyState = 1;
    this.emit('loadedmetadata');
  }
}

function storage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
  };
}

function page(options = {}) {
  const localStorage = options.localStorage || storage();
  const sessionStorage = options.sessionStorage || storage();
  const body = new Element('body');
  const header = body.appendChild(new Element('header'));
  header.className = 'hero';
  const meta = header.appendChild(new Element('div'));
  meta.className = 'right-meta';
  const document = Object.assign(new Events(), {
    body,
    hidden: options.hidden || false,
    currentScript: { src: 'https://game.example/game-music.js?v=2' },
    querySelector: selector => body.querySelector(selector),
    getElementById: id => body.querySelector(`#${id}`),
    createElement: tag => tag === 'audio' ? new Audio() : new Element(tag),
  });
  const window = new Events();
  vm.runInNewContext(source, { document, window, localStorage, sessionStorage, URL }, { filename: 'game-music.js' });
  const audio = document.getElementById('game-music-audio');
  const dialog = document.getElementById('game-music-dialog');
  return {
    audio, document, window, localStorage, sessionStorage, dialog,
    toggle: dialog.querySelector('[data-music-toggle]'),
    volume: dialog.querySelector('input'),
    status: dialog.querySelector('[role="status"]'),
    settings: meta.querySelector('.game-music-settings'),
    prefs: () => JSON.parse(localStorage.getItem(prefsKey)),
  };
}

// Drain both the play promise and its chained catch handler.
const settle = () => new Promise(resolve => setImmediate(resolve));

test('music stays undownloaded until the player explicitly chooses Play', async () => {
  const game = page();
  assert.equal(game.audio.preload, 'none');
  assert.equal(game.audio.src, null);
  assert.equal(game.audio.attempts.length, 0);
  game.settings.emit('click');
  assert.equal(game.dialog.open, true);
  game.window.emit('pageshow');
  game.volume.value = '20';
  game.volume.emit('input');
  assert.equal(game.audio.src, null);
  assert.equal(game.audio.attempts.length, 0);

  game.toggle.emit('click');
  assert.equal(game.audio.src, 'https://game.example/assets/music/shy-fx-this-style.mp4');
  assert.equal(game.audio.loop, true);
  assert.equal(game.audio.attempts.length, 1);
  game.audio.attempts[0].resolve();
  await settle();
  assert.equal(game.toggle.getAttribute('aria-pressed'), 'true');
  assert.equal(game.prefs().enabled, true);
});

test('canceling a loading track survives a late play completion', async () => {
  const game = page();
  game.toggle.emit('click');
  assert.equal(game.toggle.textContent, 'Cancel loading');
  game.toggle.emit('click');
  game.audio.attempts[0].resolve();
  await settle();
  assert.equal(game.audio.paused, true);
  assert.equal(game.prefs().enabled, false);
  assert.equal(game.toggle.textContent, 'Play music');
  assert.equal(game.toggle.getAttribute('aria-pressed'), 'false');
});

test('an old canceled play rejection cannot replace a newer loading state', async () => {
  const game = page();
  game.toggle.emit('click');
  game.toggle.emit('click');
  game.toggle.emit('click');
  game.audio.attempts[0].reject(Object.assign(new Error('Interrupted'), { name: 'AbortError' }));
  await settle();
  assert.equal(game.toggle.textContent, 'Cancel loading');
  assert.equal(game.status.textContent, 'Loading music…');
  assert.equal(game.prefs().enabled, true);
  game.audio.attempts[1].resolve();
  await settle();
  assert.equal(game.toggle.textContent, 'Pause music');
});

test('explicitly turning music off and choosing zero volume survive navigation', async () => {
  const localStorage = storage();
  const game = page({ localStorage });
  game.toggle.emit('click');
  game.audio.attempts[0].resolve();
  await settle();
  game.volume.value = '0';
  game.volume.emit('input');
  assert.equal(game.audio.volume, 0);
  assert.deepEqual(game.prefs(), { enabled: true, volume: 0 });
  game.toggle.emit('click');
  assert.deepEqual(game.prefs(), { enabled: false, volume: 0 });

  const nextPage = page({ localStorage });
  assert.equal(nextPage.audio.volume, 0);
  assert.equal(nextPage.volume.value, '0');
  assert.equal(nextPage.audio.src, null);
  assert.equal(nextPage.audio.attempts.length, 0);
});

test('page navigation restores the saved position only after metadata is available', async () => {
  const localStorage = storage({ [prefsKey]: JSON.stringify({ enabled: true, volume: 0.25 }) });
  const sessionStorage = storage({ [positionKey]: '725.5' });
  const game = page({ localStorage, sessionStorage });
  game.window.emit('pagehide');
  assert.equal(sessionStorage.getItem(positionKey), '725.5');
  game.audio.metadata(300);
  assert.equal(game.audio.currentTime, 125.5);
  game.window.emit('pageshow');
  game.audio.attempts.at(-1).resolve();
  await settle();
  game.audio.currentTime = 149.75;
  game.window.emit('pagehide');
  assert.equal(game.audio.paused, true);
  assert.equal(sessionStorage.getItem(positionKey), '149.75');
  assert.equal(game.prefs().enabled, true);

  const nextPage = page({ localStorage, sessionStorage });
  assert.equal(nextPage.audio.attempts.length, 1);
  nextPage.audio.metadata(300);
  assert.equal(nextPage.audio.currentTime, 149.75);
});

test('hidden tabs stop playback and resume the same position when visible', async () => {
  const game = page();
  game.toggle.emit('click');
  game.audio.metadata();
  game.audio.attempts[0].resolve();
  await settle();
  game.audio.currentTime = 42;
  game.document.hidden = true;
  game.document.emit('visibilitychange');
  assert.equal(game.audio.paused, true);
  assert.equal(game.prefs().enabled, true);
  game.window.emit('pageshow');
  assert.equal(game.audio.attempts.length, 1);

  game.document.hidden = false;
  game.document.emit('visibilitychange');
  assert.equal(game.audio.attempts.length, 2);
  assert.equal(game.audio.currentTime, 42);
  game.audio.attempts[1].resolve();
  await settle();
  assert.equal(game.toggle.getAttribute('aria-pressed'), 'true');
});

test('disabled browser storage still permits music controls without uncaught errors', async () => {
  const unavailable = {
    getItem() { throw new Error('Storage access denied'); },
    setItem() { throw new Error('Storage access denied'); },
  };
  const game = page({ localStorage: unavailable, sessionStorage: unavailable });
  assert.equal(game.audio.src, null);
  game.toggle.emit('click');
  game.audio.metadata();
  game.audio.attempts[0].resolve();
  await settle();
  game.volume.value = '0';
  game.volume.emit('input');
  game.toggle.emit('click');
  assert.equal(game.audio.paused, true);
  game.toggle.emit('click');
  game.audio.attempts[1].resolve();
  await settle();
  assert.equal(game.audio.volume, 0);
  assert.equal(game.toggle.getAttribute('aria-pressed'), 'true');
  assert.doesNotThrow(() => game.window.emit('pagehide'));
  assert.doesNotThrow(() => {
    game.document.hidden = true;
    game.document.emit('visibilitychange');
    game.document.hidden = false;
    game.document.emit('visibilitychange');
    game.window.emit('pageshow');
  });
  assert.equal(game.audio.volume, 0);
  assert.equal(game.audio.attempts.length, 3);
  game.audio.attempts[2].resolve();
  await settle();
  assert.equal(game.toggle.getAttribute('aria-pressed'), 'true');
});

test('a media error stops active playback and Play reloads the track for a retry', async () => {
  const game = page();
  game.toggle.emit('click');
  game.audio.metadata();
  game.audio.attempts[0].resolve();
  await settle();
  game.audio.currentTime = 60.5;
  game.audio.error = { code: 2 };
  game.audio.emit('error');
  assert.equal(game.audio.paused, true);
  assert.match(game.status.textContent, /Press Play to retry/);
  assert.equal(game.toggle.textContent, 'Play music');
  game.toggle.emit('click');
  assert.equal(game.audio.loadCalls, 1);
  assert.equal(game.audio.attempts.length, 2);
  game.audio.metadata();
  assert.equal(game.audio.currentTime, 60.5);
  game.audio.attempts[1].resolve();
  await settle();
  assert.equal(game.toggle.getAttribute('aria-pressed'), 'true');
  assert.match(game.status.textContent, /Playing/);
});

test('a loading media failure can retry while the failed play promise is still pending', async () => {
  const game = page();
  game.toggle.emit('click');
  game.audio.error = { code: 2 };
  game.audio.emit('error');
  assert.equal(game.audio.paused, true);
  assert.equal(game.toggle.textContent, 'Play music');
  game.toggle.emit('click');
  assert.equal(game.audio.loadCalls, 1);
  game.audio.attempts[0].reject(new Error('Failed previous resource'));
  await settle();
  assert.equal(game.toggle.textContent, 'Cancel loading');
  assert.equal(game.audio.paused, false);
  game.audio.attempts[1].resolve();
  await settle();
  assert.equal(game.toggle.getAttribute('aria-pressed'), 'true');
});

test('autoplay rejection can be retried through the visible Play control', async () => {
  const game = page({ localStorage: storage({ [prefsKey]: JSON.stringify({ enabled: true, volume: 0.3 }) }) });
  game.audio.attempts[0].reject(Object.assign(new Error('Gesture needed'), { name: 'NotAllowedError' }));
  await settle();
  assert.equal(game.audio.paused, true);
  assert.equal(game.toggle.textContent, 'Play music');
  assert.match(game.status.textContent, /Press Play to continue/);
  game.toggle.emit('click');
  game.audio.attempts[1].resolve();
  await settle();
  assert.equal(game.toggle.getAttribute('aria-pressed'), 'true');
});
