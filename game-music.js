/* Optional shared soundtrack. Only an explicit Music click enables playback. */
(function () {
  'use strict';
  var header = document.querySelector('.hero');
  var meta = header && header.querySelector('.right-meta');
  if (!meta || document.getElementById('game-music-audio')) return;

  var base = new URL('.', document.currentScript.src);
  var prefsKey = 'yomama_music_v1';
  var positionKey = 'yomama_music_position_v1';
  var prefs = readPrefs();
  var resumeAt = 0;
  try { resumeAt = Math.max(0, Number(sessionStorage.getItem(positionKey)) || 0); } catch (_) {}
  var pending = false;
  var errorText = '';
  var request = 0;
  var lastSaved = 0;

  function readPrefs() {
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(prefsKey)) || {}; } catch (_) {
      return prefs || { enabled: false, volume: 0.3 };
    }
    return {
      enabled: saved.enabled === true,
      volume: typeof saved.volume === 'number' && Number.isFinite(saved.volume) ? Math.max(0, Math.min(1, saved.volume)) : 0.3
    };
  }
  function savePrefs() {
    try { localStorage.setItem(prefsKey, JSON.stringify(prefs)); } catch (_) {}
  }

  var audio = document.createElement('audio');
  audio.id = 'game-music-audio';
  audio.preload = 'none';
  audio.loop = true;
  audio.volume = prefs.volume;
  // Assign the source only on play so opting out also avoids the download.
  document.body.appendChild(audio);

  var dialog = document.createElement('dialog');
  dialog.id = 'game-music-dialog';
  dialog.setAttribute('aria-labelledby', 'game-music-title');
  dialog.innerHTML = '<div class="game-music-heading"><h2 id="game-music-title">Music</h2>' +
    '<button type="button" data-music-close aria-label="Close music settings">×</button></div>' +
    '<p class="game-music-track">CLS No. 1 · I in G Major<br><small>2nd revision</small></p>' +
    '<button type="button" class="game-music-play" data-music-toggle>Play music</button>' +
    '<label class="game-music-volume" for="game-music-volume">Volume <output id="game-music-level"></output></label>' +
    '<input id="game-music-volume" type="range" min="0" max="100" step="5">' +
    '<p class="game-music-status" role="status" aria-live="polite"></p>';
  document.body.appendChild(dialog);
  var volume = dialog.querySelector('input');
  var level = dialog.querySelector('output');
  var status = dialog.querySelector('[role="status"]');
  var toggles = [dialog.querySelector('[data-music-toggle]')];

  function controls(compact) {
    var group = document.createElement('div');
    group.className = 'game-music-controls' + (compact ? ' game-music-compact' : '');
    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'game-music-toggle';
    toggle.dataset.musicToggle = '';
    toggles.push(toggle);
    group.appendChild(toggle);
    var settings = document.createElement('button');
    settings.type = 'button';
    settings.className = 'game-music-settings';
    settings.textContent = '⋯';
    settings.setAttribute('aria-label', 'Music settings');
    settings.setAttribute('aria-haspopup', 'dialog');
    settings.setAttribute('aria-controls', dialog.id);
    settings.title = 'Music volume and track';
    settings.addEventListener('click', function () { dialog.showModal(); });
    group.appendChild(settings);
    return group;
  }
  meta.prepend(controls(false));
  header.appendChild(controls(true));
  header.classList.add('has-game-music');

  function render() {
    var playing = !audio.paused && !pending;
    toggles.forEach(function (button) {
      button.textContent = button.classList.contains('game-music-play') ?
        (pending ? 'Cancel loading' : playing ? 'Pause music' : 'Play music') :
        (pending ? '♫ …' : playing ? '♫ ON' : prefs.enabled ? '♫ PLAY' : '♫ OFF');
      button.setAttribute('aria-pressed', String(playing));
      button.setAttribute('aria-label', pending ? 'Cancel music loading' : playing ? 'Pause music' : 'Play music');
      button.title = pending ? 'Cancel music loading' : playing ? 'Pause music' : 'Play music';
    });
    volume.value = String(Math.round(prefs.volume * 100));
    level.textContent = volume.value + '%';
    status.textContent = errorText || (pending ? 'Loading music…' : playing ? 'Playing · repeats automatically' : 'Press Play to listen.');
  }

  function savePosition() {
    // Do not overwrite a saved position with zero before metadata arrives.
    if (audio.readyState < 1) return;
    try { sessionStorage.setItem(positionKey, String(audio.currentTime)); } catch (_) {}
    lastSaved = Date.now();
  }

  function stop() {
    request++;
    pending = false;
    savePosition();
    audio.pause();
    render();
  }

  function play() {
    if (!prefs.enabled || document.hidden || pending || !audio.paused) return;
    var attempt = ++request;
    pending = true;
    errorText = '';
    audio.volume = prefs.volume;
    if (!audio.getAttribute('src')) audio.src = new URL('assets/music/cls-no-1-g-major.mp4', base).href;
    else if (audio.error) {
      if (audio.currentTime > 0) resumeAt = audio.currentTime;
      audio.load();
    }
    render();
    audio.play().then(function () {
      if (attempt !== request) return;
      pending = false;
      render();
    }).catch(function (error) {
      if (attempt !== request) return;
      pending = false;
      audio.pause();
      errorText = error.name === 'NotAllowedError' ? 'Press Play to continue the music.' : 'Music could not load. Press Play to retry.';
      render();
    });
  }

  toggles.forEach(function (button) {
    button.addEventListener('click', function () {
      if (pending || !audio.paused) {
        prefs.enabled = false;
        errorText = '';
        stop();
      } else {
        prefs.enabled = true;
        play();
      }
      savePrefs();
    });
  });
  volume.addEventListener('input', function () {
    prefs.volume = Number(volume.value) / 100;
    audio.volume = prefs.volume;
    savePrefs();
    render();
  });
  dialog.querySelector('[data-music-close]').addEventListener('click', function () { dialog.close(); });
  dialog.addEventListener('click', function (event) {
    if (event.target !== dialog) return;
    var bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  audio.addEventListener('loadedmetadata', function () {
    if (Number.isFinite(resumeAt) && Number.isFinite(audio.duration) && audio.duration > 0) {
      audio.currentTime = resumeAt % audio.duration;
      resumeAt = 0;
    }
  });
  audio.addEventListener('timeupdate', function () { if (Date.now() - lastSaved > 5000) savePosition(); });
  audio.addEventListener('pause', render);
  audio.addEventListener('error', function () {
    request++;
    pending = false;
    audio.pause();
    errorText = 'Music could not load. Press Play to retry.';
    render();
  });
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) stop();
    else { prefs = readPrefs(); audio.volume = prefs.volume; render(); play(); }
  });
  window.addEventListener('pagehide', stop);
  window.addEventListener('pageshow', function () { prefs = readPrefs(); render(); play(); });
  window.addEventListener('storage', function (event) {
    if (event.key !== prefsKey && event.key !== null) return;
    prefs = readPrefs();
    audio.volume = prefs.volume;
    if (!prefs.enabled) stop();
    else play();
    render();
  });
  render();
  play();
}());
