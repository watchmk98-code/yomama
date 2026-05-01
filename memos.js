(() => {
  const fighterButtons = Array.from(document.querySelectorAll('.memos-fighter[data-memo-fighter]'));
  if (!fighterButtons.length) return;

  const championPortrait = document.getElementById('memos-champion-portrait');
  const championName = document.getElementById('memos-champion-name');
  const championAlias = document.getElementById('memos-champion-alias');
  const championRank = document.getElementById('memos-champion-rank');
  const championPoints = document.getElementById('memos-champion-points');
  const championStyle = document.getElementById('memos-champion-style');
  const championSpecial = document.getElementById('memos-champion-special');

  if (
    !championPortrait ||
    !championName ||
    !championAlias ||
    !championRank ||
    !championPoints ||
    !championStyle ||
    !championSpecial
  ) {
    return;
  }

  const storageKey = 'memos_current_champion';
  const numberFormatter = new Intl.NumberFormat('en-US');

  const parsePoints = (button) => {
    const value = Number.parseInt(button.dataset.points || '0', 10);
    return Number.isFinite(value) ? value : 0;
  };

  const getTopPointsButton = () => {
    return fighterButtons.reduce((top, current) => {
      if (!top) return current;
      return parsePoints(current) > parsePoints(top) ? current : top;
    }, null);
  };

  const setChampion = (button, persist = true) => {
    if (!button) return;

    fighterButtons.forEach((entry) => {
      const isChampion = entry === button;
      entry.classList.toggle('is-current-champion', isChampion);
      entry.setAttribute('aria-pressed', isChampion ? 'true' : 'false');
    });

    const portrait = button.querySelector('.memos-fighter-portrait');
    const portraitSrc = portrait ? portrait.getAttribute('src') : '';
    const name = String(button.dataset.name || '').trim();
    const alias = String(button.dataset.alias || '').trim();
    const rank = String(button.dataset.rank || '').trim();
    const points = parsePoints(button);
    const style = String(button.dataset.style || '').trim();
    const special = String(button.dataset.special || '').trim();

    if (portraitSrc) championPortrait.src = portraitSrc;
    championPortrait.alt = `${name} champion portrait`;
    championName.textContent = name || 'UNKNOWN';
    championAlias.textContent = alias || 'Unranked';
    championRank.textContent = rank ? `#${rank}` : '#-';
    championPoints.textContent = numberFormatter.format(points);
    championStyle.textContent = style || 'No style assigned';
    championSpecial.textContent = special || 'No special move assigned';

    if (persist) {
      try {
        window.localStorage.setItem(storageKey, button.dataset.memoFighter || '');
      } catch (_) {}
    }
  };

  fighterButtons.forEach((button) => {
    button.addEventListener('click', () => {
      setChampion(button);
    });
  });

  let initialChampion = null;

  try {
    const persistedId = window.localStorage.getItem(storageKey) || '';
    if (persistedId) {
      initialChampion = fighterButtons.find((button) => button.dataset.memoFighter === persistedId) || null;
    }
  } catch (_) {}

  if (!initialChampion) {
    initialChampion = getTopPointsButton();
  }

  setChampion(initialChampion, false);
})();
