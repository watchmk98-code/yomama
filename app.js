// Shared soundtrack controls for every game page with the standard header.
(function () {
  if (!document.querySelector('.hero .right-meta') || document.getElementById('game-music-script')) return;
  const base = new URL('.', document.currentScript.src);
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = new URL('game-music.css?v=1', base).href;
  document.head.appendChild(style);
  const script = document.createElement('script');
  script.id = 'game-music-script';
  script.src = new URL('game-music.js?v=1', base).href;
  document.head.appendChild(script);
})();

(() => {
  const runtimeParams = new URLSearchParams(window.location.search);
  const forceMotionPauseSetting = Boolean(
    document.body && document.body.classList.contains('motion-paused'),
  );
  const prefersReducedMotionSetting = forceMotionPauseSetting || Boolean(
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );

  const gameSaveStorageKey = 'yomama_game_save_v1';
  const gameSaveStorageBackupKey = 'yomama_game_save_v1_backup';
  // Shared with the buildings lab; declared out here so renderSideWidgetsFromSave
  // can reach it on pages that have no #buildings-lab-root.
  const defaultCharacterKey = 'derdo';
  const sharedAccountStorageKey = 'yomama_watchmk_account_v1';
  const sharedAccountBackupStorageKey = 'yomama_watchmk_account_v1_backup';
  const gameAccountUsername = 'WATCHMK';
  const legacyCharacterSelectionStorageKey = 'hero_select_active_character';
  const temporarilyHiddenCharacterKeys = Object.freeze(['irene']);
  const hiddenCharacterKeySet = new Set(temporarilyHiddenCharacterKeys);

  const toSafeNumber = (value, fallback = 0) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const toSafeInteger = (value, fallback = 0) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.floor(parsed) : fallback;
  };

  const normalizeSeedCharacter = (value) => String(value || '').trim().toLowerCase();
  const normalizeVisibleSeedCharacter = (value, fallback = '') => {
    const normalized = normalizeSeedCharacter(value);
    if (normalized && !hiddenCharacterKeySet.has(normalized)) return normalized;
    const fallbackNormalized = normalizeSeedCharacter(fallback);
    return fallbackNormalized && !hiddenCharacterKeySet.has(fallbackNormalized) ? fallbackNormalized : '';
  };

  const readLegacySelectedCharacter = () => {
    try {
      return normalizeVisibleSeedCharacter(window.localStorage.getItem(legacyCharacterSelectionStorageKey) || '');
    } catch (_) {
      return '';
    }
  };

  const createDefaultGameSave = (preferredCharacter = '', now = Date.now()) => ({
    version: 1,
    selectedCharacter: normalizeVisibleSeedCharacter(preferredCharacter),
    wallet: { cash: 2500 },
    meta: { lastSeenAt: now },
  });

  const sanitizeGameSave = (raw, preferredCharacter = '') => {
    const now = Date.now();
    const source = raw && typeof raw === 'object' ? raw : {};
    const wallet = source.wallet && typeof source.wallet === 'object' ? source.wallet : {};
    const meta = source.meta && typeof source.meta === 'object' ? source.meta : {};
    const selectedCharacter = normalizeVisibleSeedCharacter(preferredCharacter || source.selectedCharacter || '');
    const base = createDefaultGameSave(selectedCharacter, now);

    return {
      version: 1,
      selectedCharacter: base.selectedCharacter,
      wallet: {
        cash: Math.max(0, toSafeNumber(wallet.cash, base.wallet.cash)),
      },
      meta: {
        lastSeenAt: Math.max(0, toSafeInteger(meta.lastSeenAt, now)),
      },
    };
  };

  const getStorageTargets = () => {
    const targets = [];
    try {
      targets.push(window.localStorage);
    } catch (_) {}
    try {
      targets.push(window.sessionStorage);
    } catch (_) {}
    return targets;
  };

  const readFirstValidJson = (keys) => {
    const keyList = Array.isArray(keys) ? keys : [];
    const stores = getStorageTargets();
    for (const storage of stores) {
      for (const key of keyList) {
        try {
          const serialized = storage.getItem(key);
          if (!serialized) continue;
          const parsed = JSON.parse(serialized);
          if (parsed && typeof parsed === 'object') return parsed;
        } catch (_) {}
      }
    }
    return null;
  };

  const writeJsonToAllStores = (keys, value) => {
    const keyList = Array.isArray(keys) ? keys : [];
    const serialized = JSON.stringify(value);
    const stores = getStorageTargets();
    stores.forEach((storage) => {
      keyList.forEach((key) => {
        try {
          storage.setItem(key, serialized);
        } catch (_) {}
      });
    });
  };

  const readSharedAccount = () => readFirstValidJson([sharedAccountStorageKey, sharedAccountBackupStorageKey]);

  const writeSharedAccount = (value) => {
    writeJsonToAllStores([sharedAccountStorageKey, sharedAccountBackupStorageKey], value);
  };

  const sanitizeSharedAccount = (value) => {
    const now = Date.now();
    const source = value && typeof value === 'object' ? value : {};
    const wallet = source.wallet && typeof source.wallet === 'object' ? source.wallet : {};
    const meta = source.meta && typeof source.meta === 'object' ? source.meta : {};
    return {
      version: 1,
      username: String(source.username || gameAccountUsername).toUpperCase(),
      wallet: {
        cash: Math.max(0, toSafeInteger(wallet.cash, 2500)),
      },
      inventory: source.inventory && typeof source.inventory === 'object'
        ? source.inventory
        : {},
      marketplace: source.marketplace && typeof source.marketplace === 'object'
        ? source.marketplace
        : {},
      meta: {
        lastUpdatedAt: Math.max(0, toSafeInteger(meta.lastUpdatedAt, now)),
      },
    };
  };

  const syncSharedAccountFromGameSave = (save) => {
    const safeGameSave = sanitizeGameSave(save, save && save.selectedCharacter ? save.selectedCharacter : '');
    const existing = sanitizeSharedAccount(readSharedAccount());
    const nextAccount = {
      ...existing,
      username: gameAccountUsername,
      wallet: {
        ...(existing.wallet && typeof existing.wallet === 'object' ? existing.wallet : {}),
        cash: Math.max(0, toSafeInteger(safeGameSave.wallet && safeGameSave.wallet.cash, existing.wallet.cash)),
      },
      meta: {
        ...(existing.meta && typeof existing.meta === 'object' ? existing.meta : {}),
        lastUpdatedAt: Date.now(),
      },
    };
    writeSharedAccount(nextAccount);
  };

  const readGameSave = () => readFirstValidJson([gameSaveStorageKey, gameSaveStorageBackupKey]);

  const writeGameSave = (nextSave) => {
    const preferredCharacter = normalizeVisibleSeedCharacter(nextSave && nextSave.selectedCharacter);
    const safeNextSave = sanitizeGameSave(nextSave, preferredCharacter);
    writeJsonToAllStores([gameSaveStorageKey, gameSaveStorageBackupKey], safeNextSave);
    syncSharedAccountFromGameSave(safeNextSave);
  };

  const getOrInitGameSave = () => {
    const seededCharacter = normalizeVisibleSeedCharacter(runtimeParams.get('character')) || readLegacySelectedCharacter();
    const safeSave = sanitizeGameSave(readGameSave(), seededCharacter);
    const storedPlayerSnapshot = readFirstValidJson(['yomama_player_save_v1', 'yomama_player_save_v1_backup']);
    const playerCash = toSafeNumber(
      storedPlayerSnapshot && storedPlayerSnapshot.wallet && storedPlayerSnapshot.wallet.cash,
      Number.NaN,
    );
    const playerUpdatedAt = toSafeInteger(
      storedPlayerSnapshot && storedPlayerSnapshot.meta && storedPlayerSnapshot.meta.lastUpdatedAt,
      0,
    );
    const rawSharedAccount = readSharedAccount();
    const hasSharedAccount = Boolean(rawSharedAccount && typeof rawSharedAccount === 'object');
    const sharedCash = toSafeNumber(
      rawSharedAccount && rawSharedAccount.wallet && rawSharedAccount.wallet.cash,
      Number.NaN,
    );
    const sharedUpdatedAt = Math.max(
      toSafeInteger(rawSharedAccount && rawSharedAccount.meta && rawSharedAccount.meta.lastUpdatedAt, 0),
      toSafeInteger(rawSharedAccount && rawSharedAccount.marketplace && rawSharedAccount.marketplace.lastUpdatedAt, 0),
    );
    const gameCash = toSafeNumber(safeSave.wallet && safeSave.wallet.cash, Number.NaN);
    const gameUpdatedAt = toSafeInteger(safeSave.meta && safeSave.meta.lastSeenAt, 0);
    const cashCandidates = [];
    if (hasSharedAccount && Number.isFinite(sharedCash) && sharedCash >= 0) {
      cashCandidates.push({ cash: Math.floor(sharedCash), updatedAt: sharedUpdatedAt, rank: 3 });
    }
    if (Number.isFinite(playerCash) && playerCash >= 0) {
      cashCandidates.push({ cash: Math.floor(playerCash), updatedAt: playerUpdatedAt, rank: 2 });
    }
    if (Number.isFinite(gameCash) && gameCash >= 0) {
      cashCandidates.push({ cash: Math.floor(gameCash), updatedAt: gameUpdatedAt, rank: 1 });
    }
    const resolvedCash = cashCandidates.length
      ? cashCandidates
        .sort((left, right) => {
          if (right.updatedAt !== left.updatedAt) return right.updatedAt - left.updatedAt;
          return right.rank - left.rank;
        })[0].cash
      : 2500;
    const nextSave = {
      ...safeSave,
      wallet: {
        ...safeSave.wallet,
        cash: resolvedCash,
      },
      meta: {
        ...safeSave.meta,
        lastSeenAt: Date.now(),
      },
    };
    writeGameSave(nextSave);
    return nextSave;
  };

  // Bootstrap once so every page has a stable game-save object.
  const gameSaveState = getOrInitGameSave();


  const playerSaveStorageKey = 'yomama_player_save_v1';
  const playerSaveStorageBackupKey = 'yomama_player_save_v1_backup';
  const characterAliasMap = {
    ogan: 'ozan',
    oganbeyazca: 'ozan',
  };
  let playerSaveState = null;

  const normalizeCharacterKey = (value) => {
    const normalized = String(value || '').trim().toLowerCase();
    if (!normalized) return '';
    const compact = normalized.replace(/[^a-z0-9]/gu, '');
    return characterAliasMap[normalized] || characterAliasMap[compact] || normalized;
  };
  const isCharacterVisible = (value) => {
    const normalized = normalizeCharacterKey(value);
    return Boolean(normalized) && !hiddenCharacterKeySet.has(normalized);
  };
  const normalizeVisibleCharacterKey = (value, fallback = '') => {
    const normalized = normalizeCharacterKey(value);
    if (normalized && !hiddenCharacterKeySet.has(normalized)) return normalized;
    const fallbackNormalized = normalizeCharacterKey(fallback);
    return fallbackNormalized && !hiddenCharacterKeySet.has(fallbackNormalized) ? fallbackNormalized : '';
  };
  const removeHiddenCharacterElements = () => {
    document.querySelectorAll('[data-character]').forEach((element) => {
      const characterKey = element.getAttribute('data-character') || '';
      if (isCharacterVisible(characterKey)) return;
      element.remove();
    });
  };
  const renumberVisibleLeaderboard = () => {
    const fighters = Array.from(document.querySelectorAll('.memos-roster .memos-fighter'));
    fighters.forEach((fighter, index) => {
      const rank = fighter.querySelector('.memos-rank');
      if (rank) rank.textContent = `#${index + 1}`;
    });
    const roster = document.querySelector('.memos-roster');
    if (roster instanceof HTMLElement) {
      roster.style.setProperty('--memos-rows', String(Math.max(fighters.length, 1)));
    }
  };

  removeHiddenCharacterElements();
  renumberVisibleLeaderboard();
  if (document.body) {
    temporarilyHiddenCharacterKeys.forEach((characterKey) => {
      document.body.classList.add(`character-hidden-${characterKey}`);
    });
  }

  const toNonNegativeNumber = (value, fallback = 0) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
  };

  const toNonNegativeInteger = (value, fallback = 0) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : fallback;
  };

  const toPositiveInteger = (value, fallback = 1) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback;
  };

  const buildRandomHex = (length = 12) => {
    const size = Math.max(2, Math.ceil(length / 2));
    if (window.crypto && typeof window.crypto.getRandomValues === 'function') {
      const bytes = new Uint8Array(size);
      window.crypto.getRandomValues(bytes);
      return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('').slice(0, length);
    }
    let fallback = '';
    while (fallback.length < length) {
      fallback += Math.floor(Math.random() * 16).toString(16);
    }
    return fallback.slice(0, length);
  };

  // Building definitions will be supplied by product design in a follow-up step.
  // Keep this empty for now so no concrete building is introduced yet.
  const buildingCatalog = Object.freeze({});
  const fallbackBuildingConfig = Object.freeze({
    key: 'generic_building',
    name: 'Generic Building',
    description: 'Pending building details.',
    purchaseCost: 0,
    baseOutputPerMinute: 0,
    baseStorageCap: 0,
    upgradeBaseCost: 0,
    upgradeSeconds: 0,
    outputGrowth: 1,
    storageGrowth: 1,
    upgradeCostGrowth: 1,
  });

  const getBuildingCatalogEntry = (type) => {
    const normalizedType = String(type || '').trim().toLowerCase();
    const configured = buildingCatalog[normalizedType];
    if (configured && typeof configured === 'object') return configured;
    if (!normalizedType) return fallbackBuildingConfig;
    const inferredName = normalizedType
      .replace(/[_-]+/gu, ' ')
      .replace(/\b\w/gu, (letter) => letter.toUpperCase());
    return {
      ...fallbackBuildingConfig,
      key: normalizedType,
      name: inferredName,
    };
  };

  const getBuildingOutputPerMinute = (type, level = 1) => {
    const config = getBuildingCatalogEntry(type);
    const safeLevel = Math.max(1, toPositiveInteger(level, 1));
    return config.baseOutputPerMinute * Math.pow(config.outputGrowth, safeLevel - 1);
  };

  const getBuildingStorageCap = (type, level = 1) => {
    const config = getBuildingCatalogEntry(type);
    const safeLevel = Math.max(1, toPositiveInteger(level, 1));
    return config.baseStorageCap * Math.pow(config.storageGrowth, safeLevel - 1);
  };

  const createDefaultPlayerSave = (selectedCharacter = 'derdo', now = Date.now()) => ({
    version: 1,
    selectedCharacter: normalizeVisibleCharacterKey(selectedCharacter, 'buffett') || 'buffett',
    wallet: { cash: 2500 },
    holdings: { QQQ: 0, BTC: 0 },
    buildings: [],
    meta: { lastUpdatedAt: now },
  });

  const sanitizeBuilding = (value, now = Date.now()) => {
    const source = value && typeof value === 'object' ? value : {};
    const sourceCostBasis = source.costBasis && typeof source.costBasis === 'object'
      ? source.costBasis
      : {};
    const fallbackConfig = getBuildingCatalogEntry(source.type);
    const id = typeof source.id === 'string' && source.id.trim()
      ? source.id.trim()
      : `bld_${buildRandomHex(12)}`;
    const type = fallbackConfig.key;
    const createdAt = toNonNegativeInteger(source.createdAt, now);
    const level = toPositiveInteger(source.level, 1);
    return {
      id,
      type,
      level,
      createdAt,
      lastCalcAt: toNonNegativeInteger(source.lastCalcAt, createdAt),
      stored: toNonNegativeNumber(source.stored, 0),
      totalCollected: toNonNegativeNumber(source.totalCollected, 0),
      upgradeEndsAt: toNonNegativeInteger(source.upgradeEndsAt, 0),
      costBasis: {
        cashSpent: toNonNegativeNumber(sourceCostBasis.cashSpent, fallbackConfig.purchaseCost),
      },
    };
  };

  const sanitizePlayerSave = (value, preferredCharacter = '') => {
    const now = Date.now();
    const source = value && typeof value === 'object' ? value : {};
    const preferred = normalizeVisibleCharacterKey(preferredCharacter) || normalizeVisibleCharacterKey(source.selectedCharacter) || 'derdo';
    const defaultSave = createDefaultPlayerSave(preferred, now);
    const wallet = source.wallet && typeof source.wallet === 'object' ? source.wallet : {};
    const holdings = source.holdings && typeof source.holdings === 'object' ? source.holdings : {};
    const meta = source.meta && typeof source.meta === 'object' ? source.meta : {};
    const rawBuildings = Array.isArray(source.buildings) ? source.buildings : [];
    const buildings = rawBuildings.length
      ? rawBuildings.map((building) => sanitizeBuilding(building, now))
      : defaultSave.buildings;

    return {
      version: 1,
      selectedCharacter: defaultSave.selectedCharacter,
      wallet: {
        cash: toNonNegativeNumber(wallet.cash, defaultSave.wallet.cash),
      },
      holdings: {
        QQQ: toNonNegativeNumber(holdings.QQQ, defaultSave.holdings.QQQ),
        BTC: toNonNegativeNumber(holdings.BTC, defaultSave.holdings.BTC),
      },
      buildings,
      economyV01: source.economyV01 && typeof source.economyV01 === 'object'
        ? source.economyV01
        : null,
      meta: {
        lastUpdatedAt: Math.max(0, toSafeInteger(meta.lastUpdatedAt, now)),
      },
    };
  };

  const readLegacyCharacterSelection = () => {
    try {
      return normalizeVisibleCharacterKey(window.localStorage.getItem(legacyCharacterSelectionStorageKey) || '');
    } catch (_) {
      return '';
    }
  };

  const readStoredPlayerSave = () => readFirstValidJson([playerSaveStorageKey, playerSaveStorageBackupKey]);

  const writeStoredPlayerSave = (value) => {
    writeJsonToAllStores([playerSaveStorageKey, playerSaveStorageBackupKey], value);
  };

  const readValidCash = (value) => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0) return null;
    return Math.floor(parsed);
  };

  const getSharedCashSnapshot = () => {
    const raw = readSharedAccount();
    if (!raw || typeof raw !== 'object') {
      return { has: false, cash: null, updatedAt: 0 };
    }
    const cash = readValidCash(raw.wallet && raw.wallet.cash);
    const metaUpdatedAt = toSafeInteger(raw.meta && raw.meta.lastUpdatedAt, 0);
    const marketplaceUpdatedAt = toSafeInteger(raw.marketplace && raw.marketplace.lastUpdatedAt, 0);
    return {
      has: cash !== null,
      cash,
      updatedAt: Math.max(metaUpdatedAt, marketplaceUpdatedAt),
    };
  };

  const readCanonicalWalletCash = (fallback = 2500) => {
    const candidates = [];

    const sharedSnapshot = getSharedCashSnapshot();
    if (sharedSnapshot.has && sharedSnapshot.cash !== null) {
      candidates.push({ cash: sharedSnapshot.cash, updatedAt: sharedSnapshot.updatedAt, rank: 3 });
    }

    const gameSave = readGameSave();
    const gameCash = readValidCash(gameSave && gameSave.wallet && gameSave.wallet.cash);
    if (gameCash !== null) {
      candidates.push({
        cash: gameCash,
        updatedAt: toSafeInteger(gameSave && gameSave.meta && gameSave.meta.lastSeenAt, 0),
        rank: 2,
      });
    }

    const playerSave = readStoredPlayerSave();
    const playerCash = readValidCash(playerSave && playerSave.wallet && playerSave.wallet.cash);
    if (playerCash !== null) {
      candidates.push({
        cash: playerCash,
        updatedAt: toSafeInteger(playerSave && playerSave.meta && playerSave.meta.lastUpdatedAt, 0),
        rank: 1,
      });
    }

    if (candidates.length) {
      candidates.sort((left, right) => {
        if (right.updatedAt !== left.updatedAt) return right.updatedAt - left.updatedAt;
        return right.rank - left.rank;
      });
      return candidates[0].cash;
    }

    return Math.max(0, toSafeInteger(fallback, 2500));
  };

  const syncGameSaveFromPlayerSave = (value) => {
    const source = value && typeof value === 'object' ? value : playerSaveState;
    if (!source || typeof source !== 'object') return;

    const canonicalCash = readCanonicalWalletCash(
      toNonNegativeNumber(source.wallet && source.wallet.cash, gameSaveState.wallet.cash),
    );
    if (!source.wallet || typeof source.wallet !== 'object') source.wallet = {};
    source.wallet.cash = canonicalCash;

    gameSaveState.selectedCharacter = normalizeVisibleSeedCharacter(source.selectedCharacter || '');
    gameSaveState.wallet.cash = canonicalCash;
    gameSaveState.meta.lastSeenAt = Date.now();
    writeGameSave(gameSaveState);
  };

  const applyPlayerSave = (value) => {
    const source = value && typeof value === 'object' ? value : {};
    const canonicalCash = readCanonicalWalletCash(
      toNonNegativeNumber(source.wallet && source.wallet.cash, gameSaveState.wallet.cash),
    );
    playerSaveState = sanitizePlayerSave({
      ...source,
      wallet: {
        ...(source.wallet && typeof source.wallet === 'object' ? source.wallet : {}),
        cash: canonicalCash,
      },
      meta: {
        ...(source.meta && typeof source.meta === 'object' ? source.meta : {}),
        lastUpdatedAt: Date.now(),
      },
    });
    writeStoredPlayerSave(playerSaveState);
    syncGameSaveFromPlayerSave(playerSaveState);
    return playerSaveState;
  };

  const getPlayerSave = () => {
    if (playerSaveState) return playerSaveState;
    const seededCharacter = normalizeVisibleCharacterKey(runtimeParams.get('character')) || readLegacyCharacterSelection();
    const storedSave = readStoredPlayerSave();
    playerSaveState = sanitizePlayerSave(storedSave, seededCharacter);
    playerSaveState.wallet.cash = readCanonicalWalletCash(playerSaveState.wallet.cash);
    writeStoredPlayerSave(playerSaveState);
    syncGameSaveFromPlayerSave(playerSaveState);
    return playerSaveState;
  };

  const setSelectedCharacterInPlayerSave = (value) => {
    const selectedCharacter = normalizeVisibleCharacterKey(value);
    if (!selectedCharacter) return getPlayerSave();
    const currentSave = getPlayerSave();
    if (currentSave.selectedCharacter === selectedCharacter) return currentSave;
    const nextSave = {
      ...currentSave,
      selectedCharacter,
    };
    return applyPlayerSave(nextSave);
  };

  const reconcileGameSaveState = () => {
    const storedGameSave = sanitizeGameSave(readGameSave(), gameSaveState.selectedCharacter || '');
    const runtimeSeenAt = toSafeInteger(gameSaveState && gameSaveState.meta && gameSaveState.meta.lastSeenAt, 0);
    const storedSeenAt = toSafeInteger(storedGameSave && storedGameSave.meta && storedGameSave.meta.lastSeenAt, 0);
    const preferredSource = storedSeenAt > runtimeSeenAt ? storedGameSave : gameSaveState;
    const mergedSave = sanitizeGameSave(preferredSource, preferredSource.selectedCharacter || gameSaveState.selectedCharacter || '');
    mergedSave.meta.lastSeenAt = Date.now();
    gameSaveState.selectedCharacter = mergedSave.selectedCharacter;
    gameSaveState.wallet.cash = mergedSave.wallet.cash;
    gameSaveState.meta.lastSeenAt = mergedSave.meta.lastSeenAt;
    writeGameSave(gameSaveState);
  };

  window.addEventListener('pagehide', () => {
    reconcileGameSaveState();
  });

  const settleSingleBuildingEconomy = (value, now = Date.now()) => {
    const nextBuilding = sanitizeBuilding(value, now);
    let changed = false;

    const addProductionUntil = (targetTimestamp, levelToUse) => {
      if (targetTimestamp <= nextBuilding.lastCalcAt) return;
      const elapsedMs = targetTimestamp - nextBuilding.lastCalcAt;
      const outputPerMs = getBuildingOutputPerMinute(nextBuilding.type, levelToUse) / (60 * 1000);
      const storageCap = getBuildingStorageCap(nextBuilding.type, levelToUse);
      const nextStored = Math.min(storageCap, nextBuilding.stored + (elapsedMs * outputPerMs));
      if (Math.abs(nextStored - nextBuilding.stored) > 1e-6) {
        nextBuilding.stored = nextStored;
        changed = true;
      }
      nextBuilding.lastCalcAt = targetTimestamp;
      changed = true;
    };

    if (nextBuilding.upgradeEndsAt > 0 && now >= nextBuilding.upgradeEndsAt) {
      const upgradeResolutionTime = Math.max(nextBuilding.lastCalcAt, nextBuilding.upgradeEndsAt);
      addProductionUntil(upgradeResolutionTime, nextBuilding.level);
      nextBuilding.level = Math.max(1, nextBuilding.level + 1);
      nextBuilding.upgradeEndsAt = 0;
      changed = true;
    }

    addProductionUntil(now, nextBuilding.level);
    return { building: nextBuilding, changed };
  };

  const settlePlayerBuildingEconomy = (value, now = Date.now()) => {
    const sourceSave = sanitizePlayerSave(value);
    let changed = false;
    const nextBuildings = sourceSave.buildings.map((building) => {
      const settled = settleSingleBuildingEconomy(building, now);
      if (settled.changed) changed = true;
      return settled.building;
    });
    if (!changed) {
      return { changed: false, save: sourceSave };
    }
    return {
      changed: true,
      save: {
        ...sourceSave,
        buildings: nextBuildings,
      },
    };
  };

  const getSettledPlayerSave = (now = Date.now()) => {
    const sourceSave = getPlayerSave();
    const settled = settlePlayerBuildingEconomy(sourceSave, now);
    if (!settled.changed) return sourceSave;
    return applyPlayerSave(settled.save);
  };

  getSettledPlayerSave();

  const buildingsLabRoot = document.getElementById('buildings-lab-root');
  const buildingsLabLog = document.getElementById('buildings-lab-log');
  const buildingsSideStats = document.getElementById('buildings-side-stats');
  const buildingsSidePanel = document.querySelector('.buildings-side-panel');

  if (!buildingsLabRoot && (buildingsLabLog || buildingsSideStats)) {
    if (buildingsSidePanel) buildingsSidePanel.hidden = false;

    const sideStatKeys = Object.freeze(['AGR', 'FAB', 'PWR', 'COM', 'LOG']);
    const sideTraitByClassId = Object.freeze({
      homesteader: {
        traitName: 'Harvest Surge',
        traitDescription: '1/day: arm next Farm collection for +20% Food.',
      },
      factory_foreman: {
        traitName: 'Standardize Parts',
        traitDescription: 'Workshop upgrades use -5% Materials after normal multiplier.',
      },
      grid_engineer: {
        traitName: 'Stable Output',
        traitDescription: 'Generator offline cap +60 minutes (pre-automation cap still applies).',
      },
      data_architect: {
        traitName: 'Clean Pipelines',
        traitDescription: 'Data Center +10% output if collected within 10m after cycle boundary.',
      },
      logistics_chief: {
        traitName: 'Queue Order',
        traitDescription: 'Optional queue expansion is deferred in v0.1.',
      },
      administrator: {
        traitName: 'Balanced Budget',
        traitDescription: '1/day: first build/upgrade gets -5% all resources.',
      },
    });

    const escapeSideHtml = (value) => String(value).replace(/[<>&"]/g, (char) => {
      if (char === '<') return '&lt;';
      if (char === '>') return '&gt;';
      if (char === '&') return '&amp;';
      return '&quot;';
    });

    const renderSideWidgetsFromSave = () => {
      const rawPlayerSave = readStoredPlayerSave();
      const economy = rawPlayerSave && typeof rawPlayerSave === 'object'
        ? (rawPlayerSave.economyV01 && typeof rawPlayerSave.economyV01 === 'object' ? rawPlayerSave.economyV01 : null)
        : null;

      if (buildingsLabLog) {
        const entries = economy && Array.isArray(economy.log) ? economy.log : [];
        if (!entries.length) {
          buildingsLabLog.innerHTML = '<div class="muted">No messages yet.</div>';
        } else {
          buildingsLabLog.innerHTML = entries.slice(0, 120).map((entry) => {
            const safeMessage = escapeSideHtml(String(entry && entry.message || ''));
            const safeTime = escapeSideHtml(String(entry && entry.timeLabel || '--:--:--'));
            return `<div class="bld-log-entry"><span class="bld-log-time">${safeTime}</span>${safeMessage}</div>`;
          }).join('');
        }
      }

      if (!buildingsSideStats) return;
      if (!economy) {
        buildingsSideStats.innerHTML = '<div class="muted">Stats unavailable. Start Buildings simulator first.</div>';
        return;
      }

      const selectedCharacter = normalizeVisibleCharacterKey(
        economy.activeCharacter || (rawPlayerSave && rawPlayerSave.selectedCharacter) || '',
        defaultCharacterKey,
      );
      const profiles = economy.characterProfiles && typeof economy.characterProfiles === 'object'
        ? economy.characterProfiles
        : {};
      const profile = selectedCharacter && profiles[selectedCharacter] && typeof profiles[selectedCharacter] === 'object'
        ? profiles[selectedCharacter]
        : null;
      const classId = profile && typeof profile.classId === 'string' ? profile.classId : 'administrator';
      const trait = sideTraitByClassId[classId] || sideTraitByClassId.administrator;
      const baseStats = profile && profile.baseStats && typeof profile.baseStats === 'object'
        ? profile.baseStats
        : {};
      const allocatedStats = profile && profile.allocatedStats && typeof profile.allocatedStats === 'object'
        ? profile.allocatedStats
        : {};

      const statRows = sideStatKeys.map((statKey) => {
        const base = toSafeInteger(baseStats[statKey], 0);
        const allocated = toSafeInteger(allocatedStats[statKey], 0);
        const value = Math.max(0, Math.min(10, base + allocated));
        const widthPercent = Math.round((value / 10) * 100);
        return `
          <div class="bld-stat-row">
            <span class="bld-stat-icon-slot" data-stat="${statKey}" aria-hidden="true"></span>
            <div class="bld-stat-key">${statKey}</div>
            <div class="bld-stat-track"><div class="bld-stat-fill" style="width:${widthPercent}%"></div></div>
            <div class="bld-mono">${value}/10</div>
          </div>
        `;
      }).join('');

      const characterLabel = selectedCharacter ? selectedCharacter.toUpperCase() : 'UNKNOWN';
      buildingsSideStats.innerHTML = `
        <div class="bld-stats-shell">
          <div class="bld-stats-shell-main">
            <div class="bld-stats-grid">${statRows}</div>
            <div class="bld-mini-note">Character: ${escapeSideHtml(characterLabel)}</div>
          </div>
        </div>
        <div class="bld-trait-shell">
          <div class="bld-trait">
            <strong>${escapeSideHtml(trait.traitName)}:</strong> ${escapeSideHtml(trait.traitDescription)}
          </div>
          <span class="bld-trait-icon-slot bld-square-icon-slot" data-slot="trait" aria-hidden="true"></span>
        </div>
      `;
    };

    renderSideWidgetsFromSave();
    window.addEventListener('storage', renderSideWidgetsFromSave);
    window.setInterval(renderSideWidgetsFromSave, 1000);
  }

  const repulsionCanvas = document.getElementById('c');
  if (repulsionCanvas) {
    const parameters = {
      size: 22,
      radius: 0.55,
      proximity: 24,
      growth: 3.6,
      ease: 0.11,
    };

    class Circle {
      constructor(radius, x, y) {
        this.baseRadius = radius;
        this.radius = radius;
        this.growthValue = 0;
        this.x = x;
        this.y = y;
      }

      draw(context, ease) {
        this.radius += ((this.baseRadius + this.growthValue) - this.radius) * ease;
        context.moveTo(this.x, this.y);
        context.arc(this.x, this.y, this.radius, 0, 2 * Math.PI);
      }
    }

    const ctxFx = repulsionCanvas.getContext('2d');
    let circles = [];
    let pointerActive = false;

    const normalize = (value, min, max) => (value - min) / (max - min);
    const interpolate = (value, min, max) => min + (max - min) * value;
    const map = (value, min1, max1, min2, max2) => interpolate(normalize(value, min1, max1), min2, max2);

    const resizeCanvas = () => {
      const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      repulsionCanvas.width = Math.floor(window.innerWidth * dpr);
      repulsionCanvas.height = Math.floor(window.innerHeight * dpr);
      ctxFx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const build = () => {
      circles = [];
      const columns = Math.ceil(window.innerWidth / parameters.size) + 1;
      const rows = Math.ceil(window.innerHeight / parameters.size) + 1;
      const amount = columns * rows;
      for (let i = 0; i < amount; i += 1) {
        const column = i % columns;
        const row = Math.floor(i / columns);
        circles.push(new Circle(parameters.radius, parameters.size * column, parameters.size * row));
      }
    };

    const proximityHandler = (event) => {
      pointerActive = true;
      const x = event.clientX;
      const y = event.clientY;
      for (const c of circles) {
        const distance = Math.hypot(c.x - x, c.y - y);
        let d = map(distance, c.baseRadius, c.baseRadius + parameters.proximity, parameters.growth, 0);
        if (d < 0 || !Number.isFinite(d)) d = 0;
        c.growthValue = d;
      }
    };

    const animateRepulsion = () => {
      ctxFx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      ctxFx.beginPath();
      if (!pointerActive) {
        for (const c of circles) c.growthValue = 0;
      }
      for (const circle of circles) circle.draw(ctxFx, parameters.ease);
      ctxFx.fillStyle = '#bb1e2d';
      ctxFx.fill();
      requestAnimationFrame(animateRepulsion);
    };

    resizeCanvas();
    build();
    animateRepulsion();

    window.addEventListener('resize', () => {
      resizeCanvas();
      build();
    });
    window.addEventListener('mousemove', proximityHandler);
    window.addEventListener('touchmove', (event) => {
      if (!event.touches || !event.touches[0]) return;
      proximityHandler(event.touches[0]);
    }, { passive: true });
    window.addEventListener('mouseleave', () => {
      pointerActive = false;
    });
    window.addEventListener('touchend', () => {
      pointerActive = false;
    });
  }

  const repulsionCanvasSecondary = document.getElementById('c2');
  if (repulsionCanvasSecondary) {
    const parameters = {
      size: 30,
      radius: 1,
      proximity: 70,
      growth: 24,
      ease: 0.075,
    };

    class Point {
      constructor(x, y) {
        this.x = x;
        this.y = y;
      }
    }

    class Circle {
      constructor(radius, x, y) {
        this._radius = radius;
        this.radius = radius;
        this.growthValue = 0;
        this.position = new Point(x, y);
      }

      draw(context, ease) {
        this.radius += ((this._radius + this.growthValue) - this.radius) * ease;
        context.moveTo(this.position.x, this.position.y);
        context.arc(this.position.x, this.position.y, this.radius, 0, 2 * Math.PI);
      }

      addRadius(value) {
        this.growthValue = value;
      }

      get x() {
        return this.position.x;
      }

      get y() {
        return this.position.y;
      }
    }

    const contextFx = repulsionCanvasSecondary.getContext('2d');
    let circles = [];
    const pointer = { x: window.innerWidth * 0.5, y: window.innerHeight * 0.5, active: false };

    const normalize = (value, min, max) => (value - min) / (max - min);
    const interpolate = (value, min, max) => min + (max - min) * value;
    const map = (value, min1, max1, min2, max2) => interpolate(normalize(value, min1, max1), min2, max2);

    const resizeCanvas = () => {
      const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      repulsionCanvasSecondary.width = Math.floor(window.innerWidth * dpr);
      repulsionCanvasSecondary.height = Math.floor(window.innerHeight * dpr);
      contextFx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const build = () => {
      circles = [];
      const { size, radius } = parameters;
      const columns = Math.ceil(window.innerWidth / size) + 1;
      const rows = Math.ceil(window.innerHeight / size) + 1;
      const amount = Math.ceil(columns * rows);
      for (let i = 0; i < amount; i += 1) {
        const column = i % columns;
        const row = Math.floor(i / columns);
        circles.push(new Circle(radius, size * column, size * row));
      }
    };

    const proximityHandler = (event) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      pointer.active = true;
      const { proximity, growth } = parameters;
      for (const c of circles) {
        const distance = Math.hypot(c.x - pointer.x, c.y - pointer.y);
        let d = map(distance, c._radius, c._radius + proximity, growth, 0);
        if (d < 0 || !Number.isFinite(d)) d = 0;
        c.addRadius(d);
      }
    };

    const animateRepulsion = () => {
      contextFx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      contextFx.save();
      contextFx.beginPath();

      if (!pointer.active) {
        for (const c of circles) c.addRadius(0);
      }

      for (const circle of circles) {
        circle.draw(contextFx, parameters.ease);
      }

      contextFx.fillStyle = '#ee3d3d';
      contextFx.fill();
      contextFx.restore();
      requestAnimationFrame(animateRepulsion);
    };

    resizeCanvas();
    build();

    window.addEventListener('resize', () => {
      resizeCanvas();
      build();
    });
    window.addEventListener('mousemove', proximityHandler);
    window.addEventListener('touchmove', (event) => {
      if (!event.touches || !event.touches[0]) return;
      proximityHandler(event.touches[0]);
    }, { passive: true });
    window.addEventListener('mouseleave', () => {
      pointer.active = false;
    });

    animateRepulsion();
  }

  const clock = document.getElementById('clock');
  const leftMeta = document.querySelector('.left-meta');
  const leftMetaAmberCells = leftMeta ? Array.from(leftMeta.querySelectorAll('.amber')) : [];
  const dateCell = leftMetaAmberCells.find((cell) => !cell.classList.contains('chip'));
  const daysInMarketCell = leftMeta ? leftMeta.querySelector('.chip.amber') : null;
  const marketStartDate = new Date(2022, 9, 4);
  const monthAbbrev = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
  const weekdayAbbrev = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  const formatToplineDate = (value) => {
    const weekday = weekdayAbbrev[value.getDay()];
    const month = monthAbbrev[value.getMonth()];
    const day = String(value.getDate()).padStart(2, '0');
    const year = String(value.getFullYear()).slice(-2);
    return `${weekday} ${day}-${month}-${year}`;
  };

  const updateToplineMeta = () => {
    const now = new Date();
    if (clock) {
      clock.textContent = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    }
    if (dateCell) {
      dateCell.textContent = formatToplineDate(now);
    }
    if (daysInMarketCell) {
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const start = new Date(
        marketStartDate.getFullYear(),
        marketStartDate.getMonth(),
        marketStartDate.getDate(),
      );
      const daysElapsed = Math.max(0, Math.floor((today - start) / (1000 * 60 * 60 * 24)));
      daysInMarketCell.textContent = `${daysElapsed} days in the market`;
      daysInMarketCell.textContent = '2184 days in the market';
    }
  };

  if (clock || dateCell || daysInMarketCell) {
    updateToplineMeta();
    window.setInterval(updateToplineMeta, 30 * 1000);
  }

  let updateEqualWeightTickerQuote = () => {};
  let syncEqualWeightTickerFromState = () => {};
  let getEqualWeightTickerSymbols = () => [];

  const ticker = document.getElementById('ticker');
  if (ticker) {
    const createTickerFallbackIcon = ({ label, background, foreground, border = 'rgba(255,255,255,0.18)' }) => {
      const fontSize = label.length >= 4 ? 8 : label.length === 3 ? 9.5 : 11.5;
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" role="img" aria-hidden="true">
          <rect width="28" height="28" rx="8" fill="${background}" />
          <rect x="1" y="1" width="26" height="26" rx="7" fill="none" stroke="${border}" />
          <text
            x="14"
            y="14"
            fill="${foreground}"
            font-family="Arial, Helvetica, sans-serif"
            font-size="${fontSize}"
            font-weight="700"
            text-anchor="middle"
            dominant-baseline="central"
            letter-spacing="0.06em"
          >${label}</text>
        </svg>
      `.trim();
      return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
    };

    const createCompanyFavicon = (domain) => `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`;

    const tickerBrandMetaBySymbol = {
      TSM: { name: 'TSMC', domain: 'tsmc.com', fallback: { label: 'TSM', background: '#102a43', foreground: '#9be7ff', border: '#38bdf8' } },
      TSLA: { name: 'Tesla', domain: 'tesla.com', fallback: { label: 'TSLA', background: '#111111', foreground: '#ff4d4d', border: '#ef4444' } },
      PDD: { name: 'PDD Holdings', domain: 'pddholdings.com', fallback: { label: 'PDD', background: '#7f1d1d', foreground: '#ffe4e6', border: '#fb7185' } },
      ORCL: { name: 'Oracle', domain: 'oracle.com', fallback: { label: 'ORCL', background: '#111827', foreground: '#f87171', border: '#ef4444' } },
      NVDA: { name: 'NVIDIA', domain: 'nvidia.com', fallback: { label: 'NVDA', background: '#76b900', foreground: '#08110a', border: '#d9ff8f' } },
      NOW: { name: 'ServiceNow', domain: 'servicenow.com', fallback: { label: 'NOW', background: '#032f2d', foreground: '#94f7c5', border: '#34d399' } },
      MU: { name: 'Micron', domain: 'micron.com', fallback: { label: 'MU', background: '#172554', foreground: '#bfdbfe', border: '#60a5fa' } },
      MSFT: { name: 'Microsoft', domain: 'microsoft.com', fallback: { label: 'MSFT', background: '#0f172a', foreground: '#7dd3fc', border: '#38bdf8' } },
      META: { name: 'Meta', domain: 'meta.com', fallback: { label: 'META', background: '#0866ff', foreground: '#ffffff', border: '#8ec5ff' } },
      INTU: { name: 'Intuit', domain: 'intuit.com', fallback: { label: 'INTU', background: '#052e5d', foreground: '#dbeafe', border: '#60a5fa' } },
      GOOGL: { name: 'Alphabet', domain: 'google.com', fallback: { label: 'GOOG', background: '#ffffff', foreground: '#1a73e8', border: '#d6e2ff' } },
      CRM: { name: 'Salesforce', domain: 'salesforce.com', fallback: { label: 'CRM', background: '#0c4a6e', foreground: '#dff7ff', border: '#67e8f9' } },
      BIDU: { name: 'Baidu', domain: 'baidu.com', fallback: { label: 'BIDU', background: '#172554', foreground: '#ffffff', border: '#60a5fa' } },
      BABA: { name: 'Alibaba', domain: 'alibabagroup.com', fallback: { label: 'BABA', background: '#431407', foreground: '#fed7aa', border: '#fb923c' } },
      AVGO: { name: 'Broadcom', domain: 'broadcom.com', fallback: { label: 'AVGO', background: '#991b1b', foreground: '#ffffff', border: '#fca5a5' } },
      AMZN: { name: 'Amazon', domain: 'amazon.com', fallback: { label: 'AMZN', background: '#111827', foreground: '#f59e0b', border: '#f59e0b' } },
      AMD: { name: 'AMD', domain: 'amd.com', fallback: { label: 'AMD', background: '#111111', foreground: '#f5f5f5', border: '#a3a3a3' } },
      ADBE: { name: 'Adobe', domain: 'adobe.com', fallback: { label: 'ADBE', background: '#7f1d1d', foreground: '#ffffff', border: '#fca5a5' } },
      AAPL: { name: 'Apple', domain: 'apple.com', fallback: { label: 'AAPL', background: '#f3f4f6', foreground: '#111111', border: '#d1d5db' } },
    };

    const equalWeightTechPortfolio = [
      { symbol: 'TSM', change: 19.36, changePct: 5.26 },
      { symbol: 'TSLA', change: 1.09, changePct: 0.28 },
      { symbol: 'PDD', change: 1.06, changePct: 1.07 },
      { symbol: 'ORCL', change: 6.33, changePct: 3.49 },
      { symbol: 'NVDA', change: 2.62, changePct: 1.31 },
      { symbol: 'NOW', change: 2.93, changePct: 2.93 },
      { symbol: 'MU', change: 38.10, changePct: 8.48 },
      { symbol: 'MSFT', change: 8.76, changePct: 2.07 },
      { symbol: 'META', change: 5.88, changePct: 0.88 },
      { symbol: 'INTU', change: 3.83, changePct: 0.95 },
      { symbol: 'GOOGL', change: 7.03, changePct: 2.12 },
      { symbol: 'CRM', change: 2.69, changePct: 1.44 },
      { symbol: 'BIDU', change: -0.20, changePct: -0.16 },
      { symbol: 'BABA', change: 1.04, changePct: 0.77 },
      { symbol: 'AVGO', change: 20.48, changePct: 5.09 },
      { symbol: 'AMZN', change: 5.45, changePct: 2.18 },
      { symbol: 'AMD', change: 18.97, changePct: 6.67 },
      { symbol: 'ADBE', change: 8.76, changePct: 3.54 },
      { symbol: 'AAPL', change: 7.00, changePct: 2.63 },
    ].map((entry) => {
      const meta = tickerBrandMetaBySymbol[entry.symbol] || {};
      const fallback = meta.fallback || {
        label: entry.symbol.slice(0, 4),
        background: '#111827',
        foreground: '#dff7ff',
        border: '#4fc3f7',
      };
      const previous = entry.changePct !== 0 ? entry.change / (entry.changePct / 100) : 100;
      const price = Math.max(0.01, previous + entry.change);
      return {
        ...entry,
        name: meta.name || entry.symbol,
        previous,
        price,
        logo: meta.domain ? createCompanyFavicon(meta.domain) : '',
        fallbackLogo: createTickerFallbackIcon(fallback),
      };
    });

    ticker.innerHTML = '';
    const tickerQuoteStateBySymbol = new Map();

    const formatTickerPrice = (value) => {
      if (!Number.isFinite(value)) return '$0.00';
      return value.toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    };

    const formatTickerSigned = (value, decimals = 2, suffix = '') => {
      const safeValue = Number.isFinite(value) ? value : 0;
      const absValue = Math.abs(safeValue);
      const body = absValue.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });
      if (safeValue > 0) return `+${body}${suffix}`;
      if (safeValue < 0) return `-${body}${suffix}`;
      return `${body}${suffix}`;
    };

    const getTickerChange = (entry) => {
      const previous = Number.isFinite(entry.previous) && entry.previous > 0 ? entry.previous : null;
      const price = Number.isFinite(entry.price) ? entry.price : null;
      const change = previous !== null && price !== null ? price - previous : entry.change;
      const changePct = previous !== null && previous !== 0 ? (change / previous) * 100 : entry.changePct;
      return { change, changePct };
    };

    const setTickerNodeQuote = (tickerItem, entry) => {
      const priceElement = tickerItem.querySelector('.crypto-price');
      const changeElement = tickerItem.querySelector('.crypto-change');
      if (!priceElement || !changeElement) return;

      const { change, changePct } = getTickerChange(entry);
      const changeClass = change >= 0 ? 'price-up' : 'price-down';
      priceElement.textContent = formatTickerPrice(entry.price);
      changeElement.className = `crypto-change ${changeClass}`;
      changeElement.textContent = `${formatTickerSigned(change)} / ${formatTickerSigned(changePct, 2, '%')}`;
      tickerItem.setAttribute(
        'aria-label',
        `${entry.symbol} ${formatTickerPrice(entry.price)} today ${formatTickerSigned(change)} ${formatTickerSigned(changePct, 2, '%')}`,
      );
    };

    const attachTickerLogoFallback = (tickerItem, entry) => {
      const logoElement = tickerItem.querySelector('.crypto-logo');
      if (!logoElement) return;
      logoElement.addEventListener('error', () => {
        if (logoElement.dataset.fallbackApplied === 'true') return;
        logoElement.dataset.fallbackApplied = 'true';
        logoElement.src = entry.fallbackLogo;
      }, { once: true });
    };

    const createTickerItem = (entry) => {
      const item = document.createElement('div');
      item.className = 'ticker-item';
      item.dataset.symbol = entry.symbol;

      const logo = document.createElement('img');
      logo.className = 'crypto-logo';
      logo.src = entry.logo || entry.fallbackLogo;
      logo.alt = `${entry.name} logo`;

      const name = document.createElement('span');
      name.className = 'crypto-name';
      name.textContent = entry.symbol;

      const price = document.createElement('span');
      price.className = 'crypto-price';

      const change = document.createElement('span');
      change.className = 'crypto-change';

      item.append(logo, name, price, change);
      setTickerNodeQuote(item, entry);
      return item;
    };

    const tickerItems = equalWeightTechPortfolio.map((entry) => {
      const item = createTickerItem(entry);
      const itemClone = item.cloneNode(true);
      attachTickerLogoFallback(item, entry);
      attachTickerLogoFallback(itemClone, entry);
      tickerQuoteStateBySymbol.set(entry.symbol, { entry, nodes: [item, itemClone] });
      return { item, itemClone };
    });

    tickerItems.forEach(({ item }) => {
      ticker.appendChild(item);
    });
    tickerItems.forEach(({ itemClone }) => {
      ticker.appendChild(itemClone);
    });

    updateEqualWeightTickerQuote = (symbol, price, previous) => {
      const record = tickerQuoteStateBySymbol.get(String(symbol || '').trim().toUpperCase());
      const nextPrice = Number(price);
      const nextPrevious = Number(previous);
      if (!record || !Number.isFinite(nextPrice) || !Number.isFinite(nextPrevious) || nextPrevious <= 0) return;

      record.entry.price = nextPrice;
      record.entry.previous = nextPrevious;
      const { change, changePct } = getTickerChange(record.entry);
      record.entry.change = change;
      record.entry.changePct = changePct;
      record.nodes.forEach((tickerItem) => setTickerNodeQuote(tickerItem, record.entry));
    };

    syncEqualWeightTickerFromState = (entry) => {
      if (!entry || entry.isTotal || !entry.isEqualWeightPortfolio) return;
      updateEqualWeightTickerQuote(entry.symbol, entry.today, entry.total);
    };

    getEqualWeightTickerSymbols = () => Array.from(tickerQuoteStateBySymbol.keys());

    if (prefersReducedMotionSetting) {
      ticker.style.transform = 'translateX(0px)';
    } else {
      const defaultTickerSpeed = 0.72;
      let tickerSpeed = defaultTickerSpeed;
      let tickerPosition = 0;
      let tickerAnimationId = 0;

      const stopTickerAnimation = () => {
        if (!tickerAnimationId) return;
        cancelAnimationFrame(tickerAnimationId);
        tickerAnimationId = 0;
      };

      const animateTicker = () => {
        if (document.hidden) {
          tickerAnimationId = 0;
          return;
        }
        tickerPosition -= tickerSpeed;
        if (tickerPosition < -ticker.scrollWidth / 2) tickerPosition = 0;
        ticker.style.transform = `translateX(${tickerPosition}px)`;
        tickerAnimationId = requestAnimationFrame(animateTicker);
      };

      tickerAnimationId = requestAnimationFrame(animateTicker);

      ticker.addEventListener('mouseenter', () => {
        tickerSpeed = 0;
      });

      ticker.addEventListener('mouseleave', () => {
        tickerSpeed = defaultTickerSpeed;
      });

      const handleTickerVisibility = () => {
        if (document.hidden) {
          stopTickerAnimation();
          return;
        }
        if (!tickerAnimationId) {
          tickerAnimationId = requestAnimationFrame(animateTicker);
        }
      };
      document.addEventListener('visibilitychange', handleTickerVisibility);

      window.addEventListener('beforeunload', () => {
        stopTickerAnimation();
        document.removeEventListener('visibilitychange', handleTickerVisibility);
      });
    }
  }

  const moneyRainLayer = document.querySelector('.money-rain');
  if (moneyRainLayer) {
    moneyRainLayer.innerHTML = '';
    const matrixCanvas = document.createElement('canvas');
    matrixCanvas.className = 'money-rain-canvas';
    matrixCanvas.setAttribute('aria-hidden', 'true');
    moneyRainLayer.appendChild(matrixCanvas);

    const ctx = matrixCanvas.getContext('2d', { alpha: true });
    if (ctx) {
      const currencyGlyphs = ['$', '€', '£', '¥', '₿', '₺', '₹', '₩', '₽', '¢', '₴', '₦'];
      const columnStep = 20;
      const matrixSpeedMultiplier = 0.5;
      const matrixStep = columnStep * matrixSpeedMultiplier;
      const matrixGreen = (
        window.getComputedStyle(document.documentElement)
          .getPropertyValue('--matrix-green')
          .trim()
        || '#00ff00'
      );
      const prefersReducedMotion = prefersReducedMotionSetting;
      let w = 0;
      let h = 0;
      let ypos = [0];
      let matrixTimerId = 0;
      let resizeRafId = 0;
      let resizeObserver = null;

      const pickCurrencyGlyph = () => (
        currencyGlyphs[Math.floor(Math.random() * currencyGlyphs.length)] || '$'
      );

      const resizeMatrixCanvas = () => {
        const rect = moneyRainLayer.getBoundingClientRect();
        const cssWidth = Math.max(1, Math.floor(rect.width || moneyRainLayer.clientWidth || 1));
        const cssHeight = Math.max(1, Math.floor(rect.height || moneyRainLayer.clientHeight || 1));
        const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));

        matrixCanvas.width = Math.floor(cssWidth * dpr);
        matrixCanvas.height = Math.floor(cssHeight * dpr);
        matrixCanvas.style.width = `${cssWidth}px`;
        matrixCanvas.style.height = `${cssHeight}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        w = cssWidth;
        h = cssHeight;
        const columnCount = Math.max(1, Math.floor(w / columnStep));
        ypos = Array.from({ length: columnCount }, () => (
          Math.floor(Math.random() * Math.max(1, h))
        ));
      };

        const matrix = () => {
          ctx.fillStyle = '#0001';
          ctx.fillRect(0, 0, w, h);
          ctx.fillStyle = matrixGreen;
          ctx.font = '15pt monospace';
          ctx.textBaseline = 'top';

        ypos.forEach((y, ind) => {
          const text = pickCurrencyGlyph();
          const x = ind * columnStep;
          ctx.fillText(text, x, y);
          if (y > 100 + (Math.random() * 10000)) {
            ypos[ind] = 0;
          } else {
            ypos[ind] = y + matrixStep;
          }
        });
      };

        const drawStaticMatrixFrame = () => {
          ctx.fillStyle = '#000';
          ctx.fillRect(0, 0, w, h);
          ctx.fillStyle = matrixGreen;
          ctx.font = '15pt monospace';
          ctx.textBaseline = 'top';

        ypos.forEach((y, ind) => {
          const x = ind * columnStep;
          const drawY = y % (h + columnStep);
          ctx.fillText(pickCurrencyGlyph(), x, drawY);
        });
      };

      const scheduleMatrixResize = () => {
        if (resizeRafId) return;
        resizeRafId = window.requestAnimationFrame(() => {
          resizeRafId = 0;
          resizeMatrixCanvas();
          if (prefersReducedMotion) drawStaticMatrixFrame();
        });
      };

      const stopMatrix = () => {
        if (!matrixTimerId) return;
        window.clearInterval(matrixTimerId);
        matrixTimerId = 0;
      };

      const startMatrix = () => {
        if (prefersReducedMotion || document.hidden || matrixTimerId) return;
        matrixTimerId = window.setInterval(matrix, 50);
      };

      resizeMatrixCanvas();
      if (prefersReducedMotion) {
        drawStaticMatrixFrame();
      } else {
        startMatrix();
      }

      window.addEventListener('resize', scheduleMatrixResize, { passive: true });
      if (window.ResizeObserver) {
        resizeObserver = new window.ResizeObserver(scheduleMatrixResize);
        resizeObserver.observe(moneyRainLayer);
      }

      const handleMatrixVisibility = () => {
        if (document.hidden) {
          stopMatrix();
          drawStaticMatrixFrame();
          return;
        }
        if (prefersReducedMotion) {
          drawStaticMatrixFrame();
          return;
        }
        startMatrix();
      };
      document.addEventListener('visibilitychange', handleMatrixVisibility);

      const cleanupMatrix = () => {
        stopMatrix();
        if (resizeRafId) {
          window.cancelAnimationFrame(resizeRafId);
          resizeRafId = 0;
        }
        document.removeEventListener('visibilitychange', handleMatrixVisibility);
        window.removeEventListener('resize', scheduleMatrixResize);
        if (resizeObserver) {
          resizeObserver.disconnect();
          resizeObserver = null;
        }
      };

      window.addEventListener('beforeunload', cleanupMatrix);
      window.addEventListener('pagehide', cleanupMatrix);
    }
  }

  const marioCharacters = Array.from(document.querySelectorAll('.mario-roster .mario-character'));
  const marioRoster = document.querySelector('.mario-roster');
  if (marioRoster instanceof HTMLElement) {
    marioRoster.dataset.visibleCount = String(marioCharacters.length || 0);
  }
  const marioStage = document.querySelector('.mario-stage');
  const bioOverlayElement = document.getElementById('hero-bio-overlay');
  if (marioCharacters.length || bioOverlayElement) {
    const pulseDurationMs = 620;
    const marioSelectionStorageKey = legacyCharacterSelectionStorageKey;
    let pulseTimer = null;
    let uiAudioCtx = null;
    const bioOverlay = bioOverlayElement;
    const bioClose = document.getElementById('hero-bio-close');
    const bioName = document.getElementById('hero-bio-name');
    const bioAge = document.getElementById('hero-bio-age');
    const bioRole = document.getElementById('hero-bio-role');
    const bioStyle = document.getElementById('hero-bio-style');
    const bioSig = document.getElementById('hero-bio-sig');
    const bioText = document.getElementById('hero-bio-text');
    const bioPortraitSlot = document.getElementById('hero-bio-portrait-slot');
    const bioWindow = document.querySelector('.hero-bio-window');
    const bioModeLabel = document.getElementById('hero-bio-mode-label');
    const bioViewAnalysis = document.getElementById('hero-bio-view-analysis');
    const bioViewPortfolio = document.getElementById('hero-bio-view-portfolio');
    let activeBioCharacter = '';
    let bioPortraitLoadToken = 0;

    const bioByCharacter = {
      buffett: {
        name: 'WARREN BUFFETT',
        age: 'US wide-moat compounders',
        role: '5Y to 10Y compounding window',
        style: 'Cash flow durability + pricing power',
        signature: 'Reject weak balance sheets and fad narratives',
        text: 'Base case: mega-cap quality still holds relative strength while rates remain structurally above pre-2020 norms.\n\nAction: build in tranches on valuation dislocations, not momentum spikes. Prioritize businesses with recurring demand, conservative leverage, and reinvestment runways.\n\nInvalidation: persistent margin compression with rising capital intensity. If cash conversion drops for multiple quarters, reduce size quickly and rotate to stronger operators.',
        portrait: './assets/hero-select/player-buffett.png',
      },
      marks: {
        name: 'HOWARD MARKS',
        age: 'Credit spreads + macro-sensitive sectors',
        role: 'Quarterly to multi-year cycle view',
        style: 'Second-level thinking around risk appetite',
        signature: 'When optimism is crowded, demand larger margin of safety',
        text: 'Base case: late-cycle conditions continue where headline resilience hides fragility in weaker balance sheets. Dispersion increases before broad trend reversals.\n\nAction: keep quality bias, demand higher return for weaker credits, and avoid leverage-heavy stories priced for perfection.\n\nInvalidation: broad spread tightening with improving earnings breadth and falling financing stress. That would support measured risk-on expansion.',
        portrait: './assets/hero-select/player-marks.png',
      },
      peaker: {
        name: 'PEAKER S.',
        age: 'Cross-border logistics + shadow liquidity channels',
        role: '2W to 3M tactical-operational horizon',
        style: 'Flow mapping and influence network signals',
        signature: 'Avoid crowded routes and obvious consensus trades',
        text: 'Base case: fragmented supply chains create episodic pricing power for operators with verified counterparties and rapid settlement capability.\n\nAction: focus on nodes with asymmetric information edge. Position where market participants underprice execution friction and jurisdiction risk.\n\nInvalidation: policy normalization and tighter enforcement reducing gray-market spread opportunities.',
        portrait: './assets/hero-select/player-peaker.png',
      },
      dennis: {
        name: 'DENNIS YOUNGER',
        age: 'Biotech pipelines + specialty pharma',
        role: 'Catalyst windows around trial milestones',
        style: 'Clinical probability-weighted positioning',
        signature: 'Size by downside after binary events, not upside dreams',
        text: 'Base case: small and mid-cap biotech remains highly selective; capital rewards clear trial design, cash runway visibility, and credible commercialization pathways.\n\nAction: prioritize setups where cash runway extends past key readouts and where management communication reduces interpretation risk.\n\nInvalidation: financing shocks and weak enrollment updates. If dilution risk rises before catalyst dates, reduce exposure immediately.',
        portrait: './assets/hero-select/player-dennis.png',
      },
      irene: {
        name: 'IRENE CARINA',
        age: 'Defensive growth + income resilience',
        role: '6M to 3Y capital preservation window',
        style: 'Low-volatility compounding and drawdown control',
        signature: 'No position without clear exit and liquidity depth',
        text: 'Base case: disinflation progress supports steady earners with strong free-cash-flow conversion and manageable debt service.\n\nAction: keep portfolio beta moderate, reinvest into stable cash generators, and maintain a cash buffer for volatility shocks.\n\nInvalidation: earnings downgrades combined with widening credit stress. In that scenario, increase cash and reduce cyclicals first.',
        portrait: './assets/hero-select/player-irene.png?v=20260216-1',
      },
      derdo: {
        name: 'DERDO MERDO',
        age: 'High-beta equities + narrative momentum',
        role: 'Intraday to swing-trade cycles',
        style: 'News velocity + sentiment inflection',
        signature: 'Cut losers fast when narrative strength collapses',
        text: 'Base case: information speed dominates short-term edge. Price reaction quality after headlines matters more than headline tone itself.\n\nAction: rank setups by liquidity, catalyst clarity, and crowd positioning. Add only when confirmation follows initial move, not before.\n\nInvalidation: persistent false breaks and thin participation. If follow-through dies across the board, switch to defense and wait for clean structure.',
        portrait: './assets/hero-select/player-derdo.png?v=20260216-1',
      },
      ozan: {
        name: 'OGAN BEYAZCA',
        age: 'Origin: Istanbul',
        role: 'Class: Industrial Gambler',
        style: 'Specialty: Volatility',
        signature: 'Prefers Bitcoin. Trusts gold more.',
        text: 'Runs a sock factory by day.\nTrades like a degenerate by night.\n\nPassive Skill: Survives crashes.\nUltimate Move: Buys the dip... twice.',
        portrait: './assets/hero-select/player-ozan.png?v=20260216-1',
      },
      hussein: {
        name: 'HUSSEIN FIRE',
        age: '28',
        role: 'Class: Silent Operator',
        style: 'Origin: Bursa, Türkiye',
        signature: 'Political Alignment: Mixed Signals',
        text: 'Runs a threading factory with his brother.\nNobody understands his portfolio.\n\nLifestyle says returns are strong.\nStrategy remains classified.\n\nStatus: Recently Married\nPassive Skill: Operates in Silence\nSpecial Move: Compounds Off-Radar\nWeakness: Impossible to Read',
        portrait: './assets/hero-select/player-hussein.png?v=20260216-1',
      },
      can: {
        name: 'JOHN TOWNMAN',
        age: 'From M&A to factory-floor operator',
        role: 'Operator first. Investor second.',
        style: 'Real sector: production, machinery, infrastructure',
        signature: 'Assets you can see. Cash flows you can measure.',
        text: 'After starting his career in M&A, John stepped away from the corporate track and moved to Tire, Izmir to help his father build and scale a new machinery facility.\n\nWhere others model spreadsheets, he builds tangible capacity.\n\nHe believes in the real sector: production, machinery, infrastructure. Assets you can see. Cash flows you can measure. Risk you can manage.\n\nStrength is not just a metaphor: he benches 100 kg.\n\nFrom deal rooms to factory floors, John Townman plays the long game.',
        portrait: './assets/hero-select/player-can.png?v=20260216-1',
      },
      hara: {
        name: 'HARA TURANLEE',
        age: 'Cross-border private art markets + emerging scarcity plays',
        role: 'Long-horizon cultural asset allocator',
        style: 'Rarity accumulation + narrative asymmetry',
        signature: 'Acquires before institutional validation',
        text: 'Base case: In fragmented global markets, cultural capital remains underpriced relative to financial assets. Early positioning in emerging artists and original works creates asymmetric upside as galleries, museums, and private collectors re-rate scarcity.\n\nAction: Deploy capital quietly into undervalued original works with constrained supply. Focus on provenance, narrative strength, and artist trajectory before mainstream discovery. Avoid overexposed names already bid by institutional buyers.\n\nInvalidation: Over-financialization of art markets leading to speculative excess and artificial liquidity cycles. In that environment, rotate toward historically validated masters with established museum presence.',
        portrait: './assets/hero-select/player-hara.png?v=20260216-2',
      },
      pelli: {
        name: 'PELLI TURIN',
        age: 'Origin: Germany',
        role: 'Class: Signal Hunter',
        style: 'Role: Quant Strategist',
        signature: 'Lives behind NDAs. Breathes inside datasets.',
        text: 'Signs confidentiality agreements daily. Reads between the lines even more often.\n\nHer edge? Pattern recognition.\n\nShe scans markets like others scroll headlines, searching for structural shifts, technological inflection points, and asymmetric returns.\n\n2021 Play: Micron (MU) - early memory cycle entry. Consensus came later.\n\nFor her, volatility is not chaos. It is mispriced probability.\n\nShe does not chase hype. She models outcomes.\n\nPassive Skill: Detect Structural Shifts\nUltimate: Probability Compression\nNext 10x: Already in her spreadsheet.',
        portrait: './assets/hero-select/player-pelli.png?v=20260216-2',
      },
    };
    const visibleBioByCharacter = Object.fromEntries(
      Object.entries(bioByCharacter).filter(([characterKey]) => isCharacterVisible(characterKey)),
    );

    const centerSpriteByOpaquePixels = (sprite) => {
      if (!(sprite instanceof HTMLImageElement)) return;
      const applyCentering = () => {
        if (!sprite.naturalWidth || !sprite.naturalHeight) return;
        const canvas = document.createElement('canvas');
        canvas.width = sprite.naturalWidth;
        canvas.height = sprite.naturalHeight;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) return;
        ctx.drawImage(sprite, 0, 0);
        const { data, width, height } = ctx.getImageData(0, 0, canvas.width, canvas.height);
        let minX = width;
        let maxX = -1;
        let alphaMass = 0;
        let weightedX = 0;
        for (let y = 0; y < height; y += 1) {
          const rowBase = y * width * 4;
          for (let x = 0; x < width; x += 1) {
            const alpha = data[rowBase + (x * 4) + 3];
            if (alpha < 8) continue;
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            alphaMass += alpha;
            weightedX += x * alpha;
          }
        }
        if (maxX < minX) {
          sprite.style.setProperty('--sprite-shift-x', '0px');
          return;
        }
        const opaqueCenter = alphaMass > 0 ? (weightedX / alphaMass) : ((minX + maxX) / 2);
        const naturalCenter = width / 2;
        const boxW = sprite.clientWidth || 130;
        const boxH = sprite.clientHeight || 188;
        const scale = Math.min(boxW / width, boxH / height) || 1;
        const shift = (naturalCenter - opaqueCenter) * scale;
        const clampedShift = Math.max(-12, Math.min(12, shift));
        sprite.style.setProperty('--sprite-shift-x', `${clampedShift.toFixed(2)}px`);
      };
      if (sprite.complete) {
        applyCentering();
        return;
      }
      sprite.addEventListener('load', applyCentering, { once: true });
    };

    marioCharacters.forEach((button) => {
      const sprite = button.querySelector('.mario-sprite');
      centerSpriteByOpaquePixels(sprite);
    });

    marioCharacters.forEach((button) => {
      button.classList.remove('is-selected', 'selection-pulse');
    });

    const ensureUiAudioCtx = () => {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return null;
      if (!uiAudioCtx) uiAudioCtx = new AudioCtx();
      if (uiAudioCtx.state === 'suspended') uiAudioCtx.resume().catch(() => {});
      return uiAudioCtx;
    };

    const playUiTone = (frequency, duration = 0.055, type = 'square', gainValue = 0.035) => {
      const ctx = ensureUiAudioCtx();
      if (!ctx) return;
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(frequency, now);
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.linearRampToValueAtTime(gainValue, now + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + duration + 0.01);
    };

    const playSelectSfx = () => {
      playUiTone(820, 0.045, 'square', 0.03);
    };

    const playOpenSfx = () => {
      playUiTone(720, 0.05, 'square', 0.03);
      window.setTimeout(() => playUiTone(980, 0.06, 'square', 0.03), 52);
    };

    const playCloseSfx = () => {
      playUiTone(620, 0.06, 'square', 0.028);
    };

    const getSelectedCharacter = () => marioCharacters.find((button) => button.classList.contains('is-selected')) || null;

    const getSelectedIndex = () => marioCharacters.findIndex((button) => button.classList.contains('is-selected'));

    const clearCharacterSelection = () => {
      marioCharacters.forEach((button) => {
        button.classList.remove('is-selected', 'selection-pulse');
      });
      try {
        window.localStorage.removeItem(marioSelectionStorageKey);
      } catch (_) {}
    };

    const escapeHtml = (value) => String(value || '')
      .replace(/&/gu, '&amp;')
      .replace(/</gu, '&lt;')
      .replace(/>/gu, '&gt;')
      .replace(/"/gu, '&quot;')
      .replace(/'/gu, '&#39;');

    const formatBioText = (value) => {
      const withBreaks = escapeHtml(value).replace(/\n/gu, '<br>');
      return withBreaks.replace(
        /(Base case:|Action:|Invalidation:)/gu,
        '<span class="hero-bio-feature-label">$1</span>',
      );
    };

    const setBioMode = (mode) => {
      const isAnalysisMode = mode === 'analysis';
      if (bioModeLabel) {
        bioModeLabel.textContent = isAnalysisMode ? 'NEWS' : 'BIO/PROFILE';
      }
      if (bioViewAnalysis) {
        bioViewAnalysis.textContent = isAnalysisMode ? 'BACK' : 'VIEW NEWS';
      }
      if (bioWindow) {
        bioWindow.classList.toggle('is-analysis-mode', isAnalysisMode);
      }
    };

    const renderBioPortrait = (bio) => {
      if (!bioPortraitSlot) return;
      const loadToken = bioPortraitLoadToken + 1;
      bioPortraitLoadToken = loadToken;
      bioPortraitSlot.replaceChildren();

      const portrait = new Image();
      portrait.className = 'hero-bio-portrait';
      portrait.alt = `${bio.name} pixel portrait`;
      portrait.decoding = 'async';
      portrait.loading = 'eager';
      portrait.style.setProperty('--sprite-shift-x', '0px');

      const mountPortrait = () => {
        if (loadToken !== bioPortraitLoadToken) return;
        bioPortraitSlot.replaceChildren(portrait);
        window.requestAnimationFrame(() => centerSpriteByOpaquePixels(portrait));
      };

      const clearPortrait = () => {
        if (loadToken !== bioPortraitLoadToken) return;
        bioPortraitSlot.replaceChildren();
      };

      portrait.addEventListener('load', mountPortrait, { once: true });
      portrait.addEventListener('error', clearPortrait, { once: true });
      portrait.src = bio.portrait;

      if (portrait.complete && portrait.naturalWidth > 0) {
        mountPortrait();
      }
    };

    const closeBio = () => {
      if (!bioOverlay) return;
      if (bioOverlay.hidden) return;
      bioOverlay.hidden = true;
      setBioMode('bio');
      playCloseSfx();
    };

    const openBio = (characterKey) => {
      if (!bioOverlay) return;
      const normalizedCharacterKey = normalizeCharacterKey(characterKey);
      const bio = visibleBioByCharacter[normalizedCharacterKey];
      if (!bio) return;
      activeBioCharacter = normalizedCharacterKey;
      setBioMode('bio');
      if (bioName) bioName.textContent = bio.name;
      if (bioAge) bioAge.textContent = bio.age || 'N/A';
      if (bioRole) bioRole.textContent = bio.role;
      if (bioStyle) bioStyle.textContent = bio.style;
      if (bioSig) bioSig.textContent = bio.signature;
      if (bioText) bioText.innerHTML = formatBioText(bio.text);
      renderBioPortrait(bio);
      bioOverlay.hidden = false;
      playOpenSfx();
    };

    const setActiveCharacter = (targetButton, withSound = true) => {
      if (!targetButton) return;
      marioCharacters.forEach((button) => {
        button.classList.toggle('is-selected', button === targetButton);
        button.classList.remove('selection-pulse');
      });

      targetButton.classList.add('selection-pulse');
      if (pulseTimer) clearTimeout(pulseTimer);
      pulseTimer = setTimeout(() => {
        targetButton.classList.remove('selection-pulse');
      }, pulseDurationMs);
      const characterKey = normalizeCharacterKey(targetButton.dataset.character || '');
      if (characterKey) {
        setSelectedCharacterInPlayerSave(characterKey);
        try {
          window.localStorage.setItem(marioSelectionStorageKey, characterKey);
        } catch (_) {}
      }
      if (withSound) playSelectSfx();
    };

    marioCharacters.forEach((button) => {
      button.addEventListener('click', () => {
        setActiveCharacter(button);
        openBio(normalizeCharacterKey(button.dataset.character || ''));
      });
    });

    if (marioCharacters.length) {
      document.addEventListener('click', (event) => {
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (target.closest('.mario-character')) return;
        if (target.closest('.hero-bio-overlay')) return;
        clearCharacterSelection();
      });

      if (marioStage) {
        marioStage.addEventListener('mousemove', (event) => {
          if (bioOverlay && !bioOverlay.hidden) return;
          const target = event.target;
          if (!(target instanceof Element)) return;
          if (target.closest('.mario-character')) return;
          if (!getSelectedCharacter()) return;
          clearCharacterSelection();
        });
        marioStage.addEventListener('mouseleave', () => {
          if (bioOverlay && !bioOverlay.hidden) return;
          if (!getSelectedCharacter()) return;
          clearCharacterSelection();
        });
      }
    }

    if (bioClose) bioClose.addEventListener('click', closeBio);
    if (bioOverlay) {
      bioOverlay.addEventListener('click', (event) => {
        if (event.target !== bioOverlay) return;
        closeBio();
      });
    }
    if (bioViewAnalysis) {
      bioViewAnalysis.addEventListener('click', () => {
        if (!bioOverlay || bioOverlay.hidden) return;
        const isAnalysisMode = Boolean(
          bioWindow && bioWindow.classList.contains('is-analysis-mode'),
        );
        if (isAnalysisMode) {
          setBioMode('bio');
          playSelectSfx();
          return;
        }
        setBioMode('analysis');
        playSelectSfx();
      });
    }
    if (bioViewPortfolio) {
      bioViewPortfolio.addEventListener('click', () => {
        const characterQuery = activeBioCharacter
          ? `?character=${encodeURIComponent(activeBioCharacter)}`
          : '';
        window.location.href = `./buildings.html${characterQuery}`;
      });
    }

    window.addEventListener('keydown', (event) => {
      if (bioOverlay && !bioOverlay.hidden) {
        if (event.key === 'Escape') {
          closeBio();
        }
        return;
      }

      if (!marioCharacters.length) return;

      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        const currentIndex = getSelectedIndex();
        const baseIndex = currentIndex === -1 ? 0 : currentIndex;
        const delta = event.key === 'ArrowRight' ? 1 : -1;
        const nextIndex = (baseIndex + delta + marioCharacters.length) % marioCharacters.length;
        const nextButton = marioCharacters[nextIndex];
        if (!nextButton) return;
        setActiveCharacter(nextButton);
        nextButton.focus();
        return;
      }

      if (event.key === 'Enter') {
        const selected = getSelectedCharacter() || marioCharacters[0];
        if (!selected) return;
        if (!selected.classList.contains('is-selected')) setActiveCharacter(selected, false);
        openBio(normalizeCharacterKey(selected.dataset.character || ''));
        return;
      }

      if (event.key !== 'Escape') return;
      clearCharacterSelection();
    });

    if (marioCharacters.length) {
      const saveSelectedCharacter = normalizeVisibleCharacterKey(getPlayerSave().selectedCharacter);
      let persistedCharacter = visibleBioByCharacter[saveSelectedCharacter] ? saveSelectedCharacter : '';
      if (!persistedCharacter) {
        try {
          const fromLegacyStorage = normalizeVisibleCharacterKey(window.localStorage.getItem(marioSelectionStorageKey) || '');
          persistedCharacter = visibleBioByCharacter[fromLegacyStorage] ? fromLegacyStorage : '';
        } catch (_) {}
      }
      if (persistedCharacter) {
        const persistedButton = marioCharacters.find(
          (button) => normalizeCharacterKey(button.dataset.character || '') === persistedCharacter,
        );
        if (persistedButton) setActiveCharacter(persistedButton, false);
      }
    }

    const characterFromQueryRaw = new URLSearchParams(window.location.search).get('character');
    if (characterFromQueryRaw) {
      const resolvedCharacter = normalizeVisibleCharacterKey(characterFromQueryRaw);

      if (visibleBioByCharacter[resolvedCharacter]) {
        const matchedButton = marioCharacters.find(
          (button) => normalizeCharacterKey(button.dataset.character || '') === resolvedCharacter,
        );
        if (matchedButton) setActiveCharacter(matchedButton, false);
        window.requestAnimationFrame(() => openBio(resolvedCharacter));
      }
    }
  }

  const prefersReducedMotion = prefersReducedMotionSetting;
  const demoTicksEnabled = !prefersReducedMotion && runtimeParams.get('demoTicks') !== '0';
  const randFloat = (min, max) => min + (Math.random() * (max - min));
  const randInt = (min, max) => Math.floor(randFloat(min, max + 1));
  const clampNumber = (value, min, max) => Math.max(min, Math.min(max, value));
  const withJitter = (value, jitterRatio = 0.22) => {
    const jitter = 1 + ((Math.random() * 2 - 1) * jitterRatio);
    return Math.max(140, value * jitter);
  };
  const trimTrailingZeros = (textValue) => {
    return String(textValue)
      .replace(/(\.\d*?[1-9])0+$/u, '$1')
      .replace(/\.0+$/u, '');
  };
  const parseNumericText = (textValue) => {
    const cleaned = String(textValue || '').replace(/,/gu, '').replace(/[^\d.+-]/gu, '');
    const parsed = Number.parseFloat(cleaned);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const signOf = (value) => {
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return 'flat';
  };
  const formatSigned = (value, decimals = 2, suffix = '') => {
    const absValue = Math.abs(Number.isFinite(value) ? value : 0);
    const body = trimTrailingZeros(absValue.toFixed(decimals));
    if (value > 0) return `+${body}${suffix}`;
    if (value < 0) return `-${body}${suffix}`;
    return `${body}${suffix}`;
  };
  const pickRandomItems = (items, count) => {
    if (!Array.isArray(items) || !items.length || count <= 0) return [];
    const shuffled = [...items];
    for (let i = shuffled.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled.slice(0, Math.min(count, shuffled.length));
  };
  const applySignClass = (cell, sign) => {
    if (!cell) return;
    cell.classList.remove('up', 'dn', 'muted', 'amber', 'bb-pos', 'bb-neg', 'bb-flat');
    if (sign === 'pos') {
      cell.classList.add('up', 'bb-pos');
    } else if (sign === 'neg') {
      cell.classList.add('dn', 'bb-neg');
    } else {
      cell.classList.add('muted', 'bb-flat');
    }
  };
  const setDirectionClass = (cell, direction) => {
    const sign = direction > 0 ? 'pos' : direction < 0 ? 'neg' : 'flat';
    applySignClass(cell, sign);
  };
  const setSignClass = (cell, value) => {
    applySignClass(cell, signOf(value));
  };
  const flashTimeoutByCell = new WeakMap();
  const flashNumericCell = (cell, direction) => {
    if (!cell || prefersReducedMotion || !direction) return;
    const className = direction > 0 ? 'bb-flash-up' : 'bb-flash-down';
    const activeTimer = flashTimeoutByCell.get(cell);
    if (activeTimer) window.clearTimeout(activeTimer);
    cell.classList.remove('bb-flash-up', 'bb-flash-down');
    // Force reflow so consecutive updates replay the flash animation.
    void cell.offsetWidth;
    cell.classList.add(className);
    const timeoutId = window.setTimeout(() => {
      cell.classList.remove('bb-flash-up', 'bb-flash-down');
      flashTimeoutByCell.delete(cell);
    }, 220);
    flashTimeoutByCell.set(cell, timeoutId);
  };
  const formatMarketLastValue = (value) => {
    const abs = Math.abs(value);
    if (abs >= 1000) return Math.round(value).toLocaleString('en-US');
    if (abs >= 100) return Math.round(value).toString();
    if (abs >= 10) return trimTrailingZeros(value.toFixed(2));
    return trimTrailingZeros(value.toFixed(3));
  };
  const formatMarketDeltaValue = (value, asPercent = false) => {
    const abs = Math.abs(value);
    const fixed = abs >= 100 ? abs.toFixed(0) : abs >= 10 ? abs.toFixed(1) : abs.toFixed(2);
    const body = trimTrailingZeros(fixed);
    return asPercent ? `${body}%` : body;
  };
  const formatSignedPercent = (value) => {
    const decimals = Math.abs(value) >= 10 ? 0 : 1;
    return formatSigned(value, decimals, '%');
  };

  const dashboardPanels = Array.from(document.querySelectorAll('.terminal-main .panel, .terminal-main .split-box'));
  if (!prefersReducedMotion) {
    dashboardPanels.forEach((panel) => {
      panel.classList.add('activity-breathe');
      panel.style.setProperty('--panel-breathe-duration', `${randFloat(5, 9).toFixed(2)}s`);
      panel.style.setProperty('--panel-breathe-delay', `${(-randFloat(0, 3)).toFixed(2)}s`);
    });
  }

  const marketRowState = Array.from(
    document.querySelectorAll('.data-table[aria-label="Market data table"] tbody tr'),
  ).map((row) => {
    const cells = row.querySelectorAll('td');
    if (cells.length < 4) return null;

    const symbol = cells[0].textContent.trim();
    const lastValue = parseNumericText(cells[1].textContent);
    const changeValue = parseNumericText(cells[2].textContent);
    if (!Number.isFinite(lastValue) || !Number.isFinite(changeValue)) return null;

    const isPercentLast = cells[1].textContent.includes('%');
    const hasPercentColumn = cells[3].textContent.includes('%') && !cells[3].textContent.includes('—');
    const percentValue = hasPercentColumn ? parseNumericText(cells[3].textContent) : null;
    const upperSymbol = symbol.toUpperCase();
    let volatility = 0.6;
    if (upperSymbol.includes('DOW') || upperSymbol.includes('S&P') || upperSymbol.includes('SP500')) volatility = 0.32;
    if (upperSymbol.includes('NASDAQ')) volatility = 0.38;
    if (upperSymbol.includes('VIX')) volatility = 0.85;
    if (upperSymbol.includes('GOLD')) volatility = 0.28;
    if (upperSymbol.includes('OIL')) volatility = 0.52;
    if (upperSymbol.includes('BITCOIN')) volatility = 0.95;
    if (upperSymbol.includes('RATE')) volatility = 0.09;

    return {
      symbol,
      last: lastValue,
      reference: lastValue - changeValue,
      lastCell: cells[1],
      change: changeValue,
      changeCell: cells[2],
      percent: Number.isFinite(percentValue) ? percentValue : null,
      percentCell: cells[3],
      isPercentLast,
      hasPercentColumn,
      volatility,
      floor: isPercentLast ? 0.01 : Math.max(0.01, lastValue * 0.2),
      direction: 0,
      streak: 0,
    };
  }).filter(Boolean);

  marketRowState.forEach((entry) => {
    const basis = Number.isFinite(entry.reference) && entry.reference !== 0 ? entry.reference : entry.last;
    const delta = entry.last - basis;
    const deltaPercent = basis !== 0 ? ((delta / basis) * 100) : 0;
    const direction = delta > 0 ? 1 : delta < 0 ? -1 : 0;
    entry.changeCell.textContent = formatSigned(delta, 2, entry.isPercentLast ? '%' : '');
    setDirectionClass(entry.lastCell, direction);
    setSignClass(entry.changeCell, delta);
    if (entry.hasPercentColumn) {
      entry.percentCell.textContent = formatSigned(deltaPercent, 2, '%');
      setSignClass(entry.percentCell, deltaPercent);
    }
  });

  const portfolioRowState = Array.from(
    document.querySelectorAll('.portfolio-table[aria-label="Current portfolio gains table"] tbody tr, .portfolio-table[aria-label="Current buildings gains table"] tbody tr, .portfolio-table[aria-label="MIDAS portfolio table"] tbody tr'),
  ).map((row) => {
    const cells = row.querySelectorAll('td');
    if (cells.length < 3) return null;

    const sourceLabel = row.closest('table')?.getAttribute('aria-label') || '';
    const symbol = cells[0].textContent.trim().toUpperCase();
    const isTotal = symbol === 'TOTAL';
    const changeAmtVal = parseNumericText(cells[1].textContent);
    const changePctVal = parseNumericText(cells[2].textContent);
    if (!isTotal && !Number.isFinite(changeAmtVal)) return null;

    const changeAmt = Number.isFinite(changeAmtVal) ? changeAmtVal : 0;
    const changePct = Number.isFinite(changePctVal) ? changePctVal : 0;
    const prevClose = changePct !== 0 ? (changeAmt / (changePct / 100)) : 100;
    const currentPrice = prevClose + changeAmt;

    return {
      symbol,
      today: currentPrice,
      total: prevClose,
      changeDollarCell: cells[1],
      changePctCell: cells[2],
      isTotal,
      sourceLabel,
      isEqualWeightPortfolio: sourceLabel === 'Current portfolio gains table',
      direction: 0,
      streak: 0,
    };
  }).filter(Boolean);
  const livePortfolioSymbols = ['TSM', 'TSLA', 'PDD', 'ORCL', 'NVDA', 'NOW', 'MU', 'MSFT', 'META', 'INTU', 'GOOGL', 'CRM', 'BIDU', 'BABA', 'AVGO', 'AMZN', 'AMD', 'ADBE', 'AAPL', 'UAE', 'SQQQ', 'IGV', 'INDY'];
  const tradingViewSymbolCandidatesByPortfolioSymbol = {
    TSM: ['NYSE:TSM'],
    TSLA: ['NASDAQ:TSLA'],
    PDD: ['NASDAQ:PDD'],
    ORCL: ['NYSE:ORCL'],
    NVDA: ['NASDAQ:NVDA'],
    NOW: ['NYSE:NOW'],
    MU: ['NASDAQ:MU'],
    MSFT: ['NASDAQ:MSFT'],
    META: ['NASDAQ:META'],
    INTU: ['NASDAQ:INTU'],
    GOOGL: ['NASDAQ:GOOGL'],
    CRM: ['NYSE:CRM'],
    BIDU: ['NASDAQ:BIDU'],
    BABA: ['NYSE:BABA'],
    AVGO: ['NASDAQ:AVGO'],
    AMZN: ['NASDAQ:AMZN'],
    AMD: ['NASDAQ:AMD'],
    ADBE: ['NASDAQ:ADBE'],
    AAPL: ['NASDAQ:AAPL'],
    UAE: ['AMEX:UAE'],
    SQQQ: ['NASDAQ:SQQQ'],
    IGV: ['AMEX:IGV', 'BATS:IGV'],
    INDY: ['NASDAQ:INDY'],
  };
  const tickerPortfolioSymbols = getEqualWeightTickerSymbols();
  const useLivePortfolioData = portfolioRowState.some((entry) => livePortfolioSymbols.includes(entry.symbol))
    || tickerPortfolioSymbols.some((symbol) => livePortfolioSymbols.includes(symbol));

  let burstMode = true;
  const schedulePhaseSwitch = () => {
    const duration = burstMode ? randFloat(6000, 10000) : randFloat(3000, 5000);
    setTimeout(() => {
      burstMode = !burstMode;
      schedulePhaseSwitch();
    }, duration);
  };

  const updateMarketRow = (entry) => {
    const prev = entry.last;
    let changePct = (Math.random() - 0.5) * entry.volatility;
    if (Math.random() < 0.08) changePct *= randFloat(1.8, 3.2);
    if (entry.streak >= 4 && Math.sign(changePct) === entry.direction && Math.random() < 0.18) {
      changePct *= -1;
    }

    const next = clampNumber(prev * (1 + (changePct / 100)), entry.floor, prev * 5);
    const direction = next > prev ? 1 : next < prev ? -1 : 0;
    const basis = Number.isFinite(entry.reference) && entry.reference !== 0 ? entry.reference : prev;
    const delta = next - basis;
    const deltaPercent = basis !== 0 ? ((delta / basis) * 100) : 0;

    if (direction) {
      entry.streak = direction === entry.direction ? entry.streak + 1 : 1;
      entry.direction = direction;
    }

    entry.last = next;
    entry.lastCell.textContent = entry.isPercentLast
      ? `${trimTrailingZeros(next.toFixed(2))}%`
      : formatMarketLastValue(next);
    entry.changeCell.textContent = formatSigned(delta, 2, entry.isPercentLast ? '%' : '');
    setDirectionClass(entry.lastCell, direction);
    setSignClass(entry.changeCell, delta);
    flashNumericCell(entry.lastCell, direction);

    if (entry.hasPercentColumn) {
      entry.percentCell.textContent = formatSigned(deltaPercent, 2, '%');
      setSignClass(entry.percentCell, deltaPercent);
    }
  };

  const formatPortfolioPrice = (value) => {
    if (!Number.isFinite(value)) return '—';
    return value.toLocaleString('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const renderPortfolioRow = (entry, priceDirection) => {
    if (entry.isTotal) {
      entry.changeDollarCell.textContent = '—';
      entry.changePctCell.textContent = '—';
      applySignClass(entry.changeDollarCell, 'flat');
      applySignClass(entry.changePctCell, 'flat');
      return;
    }
    const change = Number.isFinite(entry.today) && Number.isFinite(entry.total) && entry.total > 0
      ? entry.today - entry.total
      : 0;
    const changePct = Number.isFinite(entry.total) && entry.total > 0
      ? (change / entry.total) * 100
      : 0;
    entry.changeDollarCell.textContent = formatSigned(change, 2);
    entry.changePctCell.textContent = formatSigned(changePct, 2, '%');
    setSignClass(entry.changeDollarCell, change);
    setSignClass(entry.changePctCell, change);
    flashNumericCell(entry.changeDollarCell, priceDirection);
    syncEqualWeightTickerFromState(entry);
  };

  portfolioRowState.forEach((entry) => {
    renderPortfolioRow(entry, 0, 0);
  });

  const runMarketTick = () => {
    if (!marketRowState.length) return;
    const affectedCount = Math.max(1, Math.round(marketRowState.length * randFloat(0.08, 0.2)));
    pickRandomItems(marketRowState, affectedCount).forEach((entry) => {
      updateMarketRow(entry);
    });
  };

  const runPortfolioTick = () => {
    if (!portfolioRowState.length) return;
    const tradableRows = portfolioRowState.filter((entry) => !entry.isTotal);
    if (!tradableRows.length) return;

    const affectedCount = Math.max(1, Math.round(tradableRows.length * randFloat(0.08, 0.2)));
    pickRandomItems(tradableRows, affectedCount).forEach((entry) => {
      const prevToday = entry.today;

      let movePct = (Math.random() - 0.5) * 0.15;
      if (Math.random() < 0.08) movePct *= randFloat(1.8, 3.2);
      if (entry.streak >= 4 && Math.sign(movePct) === entry.direction && Math.random() < 0.18) {
        movePct *= -1;
      }

      const prevRef = Number.isFinite(entry.total) && entry.total > 0 ? entry.total : Math.abs(prevToday) || 100;
      entry.today = clampNumber(prevToday * (1 + movePct / 100), prevRef * 0.85, prevRef * 1.25);

      const todayDirection = entry.today > prevToday ? 1 : entry.today < prevToday ? -1 : 0;
      if (todayDirection) {
        entry.streak = todayDirection === entry.direction ? entry.streak + 1 : 1;
        entry.direction = todayDirection;
      }
      renderPortfolioRow(entry, todayDirection);
    });
  };

  const toFiniteNumber = (value) => {
    const parsed = Number.parseFloat(String(value || '').replace(/[^0-9.+-]/gu, ''));
    return Number.isFinite(parsed) ? parsed : null;
  };

  const fetchTradingViewQuote = async (tvSymbol) => {
    const params = new URLSearchParams({
      symbol: tvSymbol,
      fields: 'close,change',
    });
    const response = await fetch(`https://scanner.tradingview.com/symbol?${params.toString()}`, {
      method: 'GET',
      mode: 'cors',
      credentials: 'omit',
      cache: 'no-store',
    });
    if (!response.ok) return null;
    const payload = await response.json().catch(() => null);
    if (!payload || typeof payload !== 'object') return null;
    if (String(payload.code || '').toLowerCase() === 'symbol_not_exists') return null;

    const close = toFiniteNumber(payload.close);
    const changePercent = toFiniteNumber(payload.change);
    if (!Number.isFinite(close) || !Number.isFinite(changePercent)) return null;
    const denominator = 1 + (changePercent / 100);
    const prev = denominator !== 0 ? (close / denominator) : null;
    if (!Number.isFinite(prev)) return null;
    return { close, prev };
  };

  const getLivePortfolioQuotes = async () => {
    if (!livePortfolioSymbols.length) return new Map();
    const quotes = new Map();

    await Promise.all(livePortfolioSymbols.map(async (symbol) => {
      const candidates = tradingViewSymbolCandidatesByPortfolioSymbol[symbol] || [];
      for (const candidate of candidates) {
        const quote = await fetchTradingViewQuote(candidate);
        if (!quote) continue;
        quotes.set(symbol, quote);
        break;
      }
    }));
    livePortfolioSymbols.forEach((symbol) => {
      if (!quotes.has(symbol)) return;
      const quote = quotes.get(symbol);
      if (!quote || !Number.isFinite(quote.close) || !Number.isFinite(quote.prev)) {
        quotes.delete(symbol);
      }
    });
    return quotes;
  };

  let livePortfolioUpdateInFlight = false;
  const refreshLivePortfolioReturns = async () => {
    if (!useLivePortfolioData || livePortfolioUpdateInFlight) return;
    livePortfolioUpdateInFlight = true;
    try {
      const tradableRows = portfolioRowState.filter((entry) => !entry.isTotal);
      const quotes = await getLivePortfolioQuotes();

      tradableRows.forEach((entry) => {
        const quote = quotes.get(entry.symbol);
        if (!quote) return;

        const prevToday = entry.today;
        entry.today = quote.close;
        entry.total = quote.prev;
        const todayDirection = entry.today > prevToday ? 1 : entry.today < prevToday ? -1 : 0;
        renderPortfolioRow(entry, todayDirection);
      });
      tickerPortfolioSymbols.forEach((symbol) => {
        const quote = quotes.get(symbol);
        if (!quote) return;
        updateEqualWeightTickerQuote(symbol, quote.close, quote.prev);
      });
      portfolioRowState.filter((entry) => entry.isTotal).forEach((entry) => renderPortfolioRow(entry, 0));
    } catch (_) {
      // Keep existing rendered values when live fetch fails.
    } finally {
      livePortfolioUpdateInFlight = false;
    }
  };

  const scheduleLoop = (task, minMs, maxMs) => {
    const run = () => {
      task();
      const phaseFactor = burstMode ? 1 : 1.24;
      const interval = withJitter(randFloat(minMs, maxMs) * phaseFactor, 0.22);
      setTimeout(run, interval);
    };
    run();
  };

  const schedulePanelPulse = () => {
    if (prefersReducedMotion || !dashboardPanels.length) return;
    const pulse = () => {
      const maxCount = Math.max(1, Math.ceil(dashboardPanels.length * 0.25));
      const count = randInt(1, maxCount);
      pickRandomItems(dashboardPanels, count).forEach((panel) => {
        panel.classList.remove('activity-pulse');
        void panel.offsetWidth;
        panel.classList.add('activity-pulse');
      });
      setTimeout(pulse, withJitter(randFloat(4500, 8000), 0.22));
    };
    pulse();
  };

  if (demoTicksEnabled && (marketRowState.length || portfolioRowState.length || dashboardPanels.length)) {
    schedulePhaseSwitch();
    scheduleLoop(runMarketTick, 800, 1600);
    if (!useLivePortfolioData) {
      scheduleLoop(runPortfolioTick, 1100, 2000);
    }
    schedulePanelPulse();
  }
  if (useLivePortfolioData) {
    refreshLivePortfolioReturns();
    window.setInterval(() => {
      if (document.hidden) return;
      refreshLivePortfolioReturns();
    }, 30000);
  }

  const largeHeader = document.getElementById('large-header');
  const demoCanvas = document.getElementById('demo-canvas');
  const bannerFrame = document.querySelector('.banner-frame');
  if (bannerFrame && !bannerFrame.querySelector('.header-news-lanes')) {
    const fallbackHeadlines = [
      'MSFT launches new AI model',
      'FED hints at rate cut in June',
      'Wall St. bullish on NVDA earnings',
      'SEC debates Ether ETF launch',
    ];
    const shuffle = (list) => {
      const items = [...list];
      for (let i = items.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        [items[i], items[j]] = [items[j], items[i]];
      }
      return items;
    };
    const tableHeadlines = Array.from(document.querySelectorAll('table[aria-label="News table"] tbody tr td:first-child'))
      .map((cell) => cell.textContent.trim().replace(/\.\.\.$/, ''))
      .filter(Boolean);
    const rowCount = 4;
    const activeHeadlines = new Set();
    const buildRowFlow = (row, side, nextHeadline) => {
      const direction = side === 'left' ? 1 : -1;
      const speedPxPerSecond = (48 + Math.random() * 18) * 1.3;
      const minGap = 28 + Math.random() * 12;
      const items = [];
      let lastTime = performance.now();
      const clamp01 = (value) => Math.max(0, Math.min(1, value));
      const smoothstep = (value) => {
        const t = clamp01(value);
        return t * t * (3 - (2 * t));
      };

      const setItemPosition = (item, now, rowWidth) => {
        const distanceToLogoEdge = direction === 1
          ? rowWidth - (item.x + item.width)
          : item.x;
        const fadeStartPx = rowWidth * 0.46;
        const fadeEndPx = rowWidth * 0.2;
        const rawFade = (fadeStartPx - distanceToLogoEdge) / Math.max(1, fadeStartPx - fadeEndPx);
        const fadeProgress = smoothstep(rawFade);
        const alpha = 1 - fadeProgress;

        // Add dispersion as the text dissolves into the logo edge.
        const wobble = Math.sin(now * item.wobbleSpeed + item.phase) * (item.dispersionAmplitude * fadeProgress);
        const drift = item.dispersionDir * item.dispersionAmplitude * fadeProgress;
        const yOffset = drift + wobble;

        item.el.style.opacity = alpha.toFixed(3);
        item.el.style.filter = `blur(${(fadeProgress * 2.2).toFixed(2)}px)`;
        item.el.style.transform = `translate3d(${item.x.toFixed(2)}px, calc(-50% + ${yOffset.toFixed(2)}px), 0)`;
      };

      const spawnItem = () => {
        const headline = nextHeadline();
        if (!headline) return false;

        const text = document.createElement('span');
        text.className = 'header-news-text';
        text.textContent = headline;
        row.appendChild(text);
        const width = Math.ceil(text.getBoundingClientRect().width);
        const rowWidth = row.clientWidth;
        const x = direction === 1 ? -width : rowWidth;
        const item = {
          el: text,
          headline,
          x,
          width,
          phase: Math.random() * Math.PI * 2,
          wobbleSpeed: 0.008 + Math.random() * 0.01,
          dispersionAmplitude: 1.6 + Math.random() * 2.2,
          dispersionDir: Math.random() < 0.5 ? -1 : 1,
        };
        setItemPosition(item, performance.now(), rowWidth);
        items.push(item);
        return true;
      };

      const canSpawn = () => {
        if (!items.length) return true;
        const rowWidth = row.clientWidth;
        if (direction === 1) {
          let nearestLeftEdge = Infinity;
          items.forEach((item) => {
            if (item.x < nearestLeftEdge) nearestLeftEdge = item.x;
          });
          return nearestLeftEdge >= minGap;
        }
        let nearestRightEdge = -Infinity;
        items.forEach((item) => {
          const edge = item.x + item.width;
          if (edge > nearestRightEdge) nearestRightEdge = edge;
        });
        return nearestRightEdge <= rowWidth - minGap;
      };

      const tick = (now) => {
        const dt = Math.min(0.05, (now - lastTime) / 1000);
        lastTime = now;
        const rowWidth = row.clientWidth;

        for (let i = items.length - 1; i >= 0; i -= 1) {
          const item = items[i];
          item.x += direction * speedPxPerSecond * dt;
          setItemPosition(item, now, rowWidth);

          const isOffscreen = direction === 1
            ? item.x > rowWidth + 8
            : item.x + item.width < -8;
          if (isOffscreen) {
            activeHeadlines.delete(item.headline);
            item.el.remove();
            items.splice(i, 1);
          }
        }

        let spawnGuard = 0;
        while (spawnGuard < 2 && canSpawn()) {
          if (!spawnItem()) break;
          spawnGuard += 1;
        }

        requestAnimationFrame(tick);
      };

      requestAnimationFrame(tick);
    };

    const buildSideLanes = (headlines, side) => {
      if (bannerFrame.querySelector(`.header-news-lanes-${side}`)) return;
      const uniqueHeadlines = Array.from(new Set(headlines.filter(Boolean)));
      const sourceHeadlines = uniqueHeadlines.length ? uniqueHeadlines : fallbackHeadlines;
      const expandedHeadlines = [];
      for (let repeat = 0; repeat < 4; repeat += 1) {
        expandedHeadlines.push(...shuffle(sourceHeadlines));
      }
      let flowPool = [];
      const nextHeadline = () => {
        if (!expandedHeadlines.length) return null;

        let attempts = 0;
        const deferred = [];
        const maxAttempts = Math.max(expandedHeadlines.length, sourceHeadlines.length * 6);

        while (attempts < maxAttempts) {
          if (!flowPool.length) flowPool = shuffle(expandedHeadlines);
          const candidate = flowPool.pop();
          attempts += 1;
          if (!candidate) continue;

          if (!activeHeadlines.has(candidate)) {
            if (deferred.length) flowPool.unshift(...shuffle(deferred));
            activeHeadlines.add(candidate);
            return candidate;
          }
          deferred.push(candidate);
        }

        if (deferred.length) flowPool.unshift(...shuffle(deferred));
        return null;
      };

      const lanes = document.createElement('div');
      lanes.className = `header-news-lanes header-news-lanes-${side}`;
      lanes.setAttribute('aria-hidden', 'true');

      for (let index = 0; index < rowCount; index += 1) {
        const row = document.createElement('div');
        row.className = 'header-news-row';
        row.style.setProperty('--row-top', `${((index + 0.5) * 100) / rowCount}%`);
        buildRowFlow(row, side, nextHeadline);
        lanes.appendChild(row);
      }
      bannerFrame.appendChild(lanes);
    };

    const buildHeaderLanes = (headlines) => {
      buildSideLanes(headlines, 'left');
      buildSideLanes(headlines, 'right');
    };

    fetch('./sample-stock-news.json', { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error(`News fetch failed: ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        const feedHeadlines = Array.isArray(payload)
          ? payload.map((item) => (item && typeof item.title === 'string' ? item.title.trim() : ''))
            .filter(Boolean)
          : [];
        buildHeaderLanes(feedHeadlines.length ? feedHeadlines : tableHeadlines);
      })
      .catch(() => {
        buildHeaderLanes(tableHeadlines.length ? tableHeadlines : fallbackHeadlines);
      });
  }
  if (largeHeader && demoCanvas) {
    const demoCtx = demoCanvas.getContext('2d');
    let headerWidth = 0;
    let headerHeight = 0;
    let points = [];
    const target = { x: 0, y: 0 };
    const nearestCount = 5;
    const pixelStep = 2;
    const snap = (value) => Math.round(value / pixelStep) * pixelStep;
    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
    const randomBetween = (min, max) => min + Math.random() * (max - min);
    const mix = (a, b, t) => a + (b - a) * t;
    const autoTarget = {
      fromX: 0,
      fromY: 0,
      toX: 0,
      toY: 0,
      start: 0,
      duration: 1,
      mode: 'sweep',
      phase: Math.random() * Math.PI * 2,
      wobbleX: 0,
      wobbleY: 0,
      wobbleSpeed: 0.002,
    };
    let trendTarget = 1;
    let trendBlend = 1;

    const getDistance = (p1, p2) => {
      const dx = p1.x - p2.x;
      const dy = p1.y - p2.y;
      return dx * dx + dy * dy;
    };

    const easeInOutCirc = (t) => {
      if (t < 0.5) return (1 - Math.sqrt(1 - 4 * t * t)) / 2;
      return (Math.sqrt(1 - Math.pow(-2 * t + 2, 2)) + 1) / 2;
    };

    const sideOpacityAtX = (x) => {
      const half = headerWidth * 0.5;
      if (half <= 0) return 0;
      const normalized = Math.max(0, Math.min(1, Math.abs(x - half) / half));
      return normalized * normalized * (3 - 2 * normalized);
    };

    const assignClosest = () => {
      points.forEach((point, index) => {
        const distances = [];
        for (let i = 0; i < points.length; i += 1) {
          if (i === index) continue;
          distances.push({ other: points[i], d: getDistance(point, points[i]) });
        }
        distances.sort((a, b) => a.d - b.d);
        point.closest = distances.slice(0, nearestCount).map((entry) => entry.other);
      });
    };

    const scheduleShift = (point, now = performance.now()) => {
      point.shiftStart = now;
      point.shiftDuration = 2400 + Math.random() * 2200;
      point.startX = point.x;
      point.startY = point.y;
      point.targetX = point.originX - 28 + Math.random() * 56;
      point.targetY = point.originY - 24 + Math.random() * 48;
    };

    const buildPoints = () => {
      points = [];
      const stepX = Math.max(26, headerWidth / 20);
      const stepY = Math.max(18, headerHeight / 11);

      for (let x = 0; x < headerWidth; x += stepX) {
        for (let y = 0; y < headerHeight; y += stepY) {
          const px = x + Math.random() * stepX;
          const py = y + Math.random() * stepY;
          const point = {
            x: px,
            y: py,
            originX: px,
            originY: py,
            active: 0,
            circleActive: 0,
            radius: 1.2 + Math.random() * 1.6,
            closest: [],
            shiftStart: 0,
            shiftDuration: 0,
            startX: px,
            startY: py,
            targetX: px,
            targetY: py,
          };
          scheduleShift(point);
          points.push(point);
        }
      }

      assignClosest();
      target.x = headerWidth * 0.5;
      target.y = headerHeight * 0.5;
    };

    const scheduleAutoTarget = (now = performance.now()) => {
      const modes = ['sweep', 'hop', 'drift'];
      autoTarget.mode = modes[Math.floor(Math.random() * modes.length)];
      autoTarget.start = now;
      autoTarget.fromX = target.x;
      autoTarget.fromY = target.y;
      autoTarget.phase = Math.random() * Math.PI * 2;

      if (autoTarget.mode === 'sweep') {
        const towardRight = target.x < headerWidth * 0.5;
        autoTarget.toX = towardRight
          ? randomBetween(headerWidth * 0.72, headerWidth * 0.96)
          : randomBetween(headerWidth * 0.04, headerWidth * 0.28);
        autoTarget.toY = randomBetween(headerHeight * 0.18, headerHeight * 0.82);
        autoTarget.duration = randomBetween(5200, 9000);
        autoTarget.wobbleX = randomBetween(6, 14);
        autoTarget.wobbleY = randomBetween(8, 18);
        autoTarget.wobbleSpeed = randomBetween(0.0008, 0.0014);
      } else if (autoTarget.mode === 'hop') {
        autoTarget.toX = randomBetween(headerWidth * 0.05, headerWidth * 0.95);
        autoTarget.toY = randomBetween(headerHeight * 0.1, headerHeight * 0.9);
        autoTarget.duration = randomBetween(2400, 4600);
        autoTarget.wobbleX = randomBetween(3, 8);
        autoTarget.wobbleY = randomBetween(3, 8);
        autoTarget.wobbleSpeed = randomBetween(0.0011, 0.002);
      } else {
        autoTarget.toX = clamp(target.x + randomBetween(-headerWidth * 0.18, headerWidth * 0.18), headerWidth * 0.03, headerWidth * 0.97);
        autoTarget.toY = clamp(target.y + randomBetween(-headerHeight * 0.22, headerHeight * 0.22), headerHeight * 0.08, headerHeight * 0.92);
        autoTarget.duration = randomBetween(3600, 7000);
        autoTarget.wobbleX = randomBetween(4, 10);
        autoTarget.wobbleY = randomBetween(5, 12);
        autoTarget.wobbleSpeed = randomBetween(0.0009, 0.0018);
      }

      trendTarget = autoTarget.toX >= autoTarget.fromX ? 1 : 0;
      if (Math.random() < 0.18) trendTarget = Math.random() > 0.5 ? 1 : 0;
    };

    const updateAutoTarget = (now) => {
      const elapsed = now - autoTarget.start;
      if (elapsed >= autoTarget.duration) {
        scheduleAutoTarget(now);
      }

      const progress = clamp((now - autoTarget.start) / autoTarget.duration, 0, 1);
      const eased = easeInOutCirc(progress);
      const baseX = autoTarget.fromX + (autoTarget.toX - autoTarget.fromX) * eased;
      const baseY = autoTarget.fromY + (autoTarget.toY - autoTarget.fromY) * eased;

      const wave = now * autoTarget.wobbleSpeed + autoTarget.phase;
      const wobbleX = Math.sin(wave * 1.17) * autoTarget.wobbleX;
      const wobbleY = Math.cos(wave * 0.93) * autoTarget.wobbleY;

      target.x = clamp(baseX + wobbleX, 0, headerWidth);
      target.y = clamp(baseY + wobbleY, 0, headerHeight);
    };

    const resizeHeaderCanvas = () => {
      const rect = largeHeader.getBoundingClientRect();
      headerWidth = Math.max(1, Math.floor(rect.width));
      headerHeight = Math.max(1, Math.floor(rect.height));
      const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      demoCanvas.width = Math.floor(headerWidth * dpr);
      demoCanvas.height = Math.floor(headerHeight * dpr);
      demoCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildPoints();
      scheduleAutoTarget(performance.now());
    };

    const drawLines = (point) => {
      if (!point.active) return;
      const primaryR = Math.round(mix(255, 34, trendBlend));
      const primaryG = Math.round(mix(56, 246, trendBlend));
      const primaryB = Math.round(mix(56, 120, trendBlend));
      const glowR = Math.round(mix(255, 108, trendBlend));
      const glowG = Math.round(mix(120, 255, trendBlend));
      const glowB = Math.round(mix(120, 156, trendBlend));
      point.closest.forEach((closePoint) => {
        const sideOpacity = sideOpacityAtX((point.x + closePoint.x) * 0.5);
        if (sideOpacity <= 0) return;
        const flicker = 0.88 + Math.random() * 0.28;
        const alpha = Math.max(0, Math.min(1, point.active * flicker * sideOpacity));
        demoCtx.beginPath();
        demoCtx.moveTo(snap(point.x), snap(point.y));
        demoCtx.lineTo(snap(closePoint.x), snap(closePoint.y));
        demoCtx.lineWidth = 1;
        demoCtx.strokeStyle = `rgba(${primaryR},${primaryG},${primaryB},${alpha})`;
        demoCtx.stroke();

        demoCtx.beginPath();
        demoCtx.moveTo(snap(point.x), snap(point.y));
        demoCtx.lineTo(snap(closePoint.x), snap(closePoint.y));
        demoCtx.lineWidth = 2;
        demoCtx.strokeStyle = `rgba(${glowR},${glowG},${glowB},${alpha * 0.26})`;
        demoCtx.stroke();
      });
    };

    const drawPoint = (point) => {
      if (!point.circleActive) return;
      const glowR = Math.round(mix(255, 90, trendBlend));
      const glowG = Math.round(mix(98, 255, trendBlend));
      const glowB = Math.round(mix(98, 148, trendBlend));
      const coreR = Math.round(mix(255, 205, trendBlend));
      const coreG = Math.round(mix(198, 255, trendBlend));
      const coreB = Math.round(mix(198, 220, trendBlend));
      const sideOpacity = sideOpacityAtX(point.x);
      if (sideOpacity <= 0) return;
      const px = snap(point.x);
      const py = snap(point.y);
      const coreSize = Math.max(2, Math.round(point.radius * 1.6));
      const glowSize = coreSize + 2;
      demoCtx.fillStyle = `rgba(${glowR},${glowG},${glowB},${Math.min(1, point.circleActive * 0.42 * sideOpacity)})`;
      demoCtx.fillRect(px - glowSize / 2, py - glowSize / 2, glowSize, glowSize);
      demoCtx.fillStyle = `rgba(${coreR},${coreG},${coreB},${Math.min(1, point.circleActive * 0.95 * sideOpacity)})`;
      demoCtx.fillRect(px - coreSize / 2, py - coreSize / 2, coreSize, coreSize);
    };

    const animateHeader = (now) => {
      demoCtx.globalCompositeOperation = 'source-over';
      demoCtx.clearRect(0, 0, headerWidth, headerHeight);
      demoCtx.globalCompositeOperation = 'lighter';
      updateAutoTarget(now);
      trendBlend += (trendTarget - trendBlend) * 0.018;
      const activityScale = 0.8 + (0.5 + 0.5 * Math.sin(now * 0.0015)) * 0.4;

      points.forEach((point) => {
        const progress = Math.min(1, (now - point.shiftStart) / point.shiftDuration);
        const eased = easeInOutCirc(progress);
        point.x = point.startX + (point.targetX - point.startX) * eased;
        point.y = point.startY + (point.targetY - point.startY) * eased;
        if (progress >= 1) scheduleShift(point, now);

        const d = getDistance(target, point);
        if (d < 4000) {
          point.active = 0.3 * activityScale;
          point.circleActive = 0.6 * activityScale;
        } else if (d < 20000) {
          point.active = 0.1 * activityScale;
          point.circleActive = 0.3 * activityScale;
        } else if (d < 40000) {
          point.active = 0.02 * activityScale;
          point.circleActive = 0.1 * activityScale;
        } else {
          point.active = 0;
          point.circleActive = 0;
        }

        drawLines(point);
        drawPoint(point);
      });

      if (prefersReducedMotionSetting) return;
      requestAnimationFrame(animateHeader);
    };

    resizeHeaderCanvas();
    scheduleAutoTarget();
    window.addEventListener('resize', resizeHeaderCanvas);
    if (prefersReducedMotionSetting) {
      animateHeader(performance.now());
    } else {
      requestAnimationFrame(animateHeader);
    }
  }

  const canvas = document.getElementById('chart');
  const ctx = canvas ? canvas.getContext('2d') : null;

  const stockTitle = document.getElementById('stock-title');
  const titleSwitch = document.querySelector('.title-switch');
  const stockSearch = document.querySelector('.panel-search-input') || document.querySelector('.search');
  const searchFrame = document.querySelector('.banner-search') || document.querySelector('.electric-search');
  const searchContainer = stockSearch ? stockSearch.closest('.future-search-space') : null;
  const isPanelSearch = Boolean(stockSearch && stockSearch.classList.contains('panel-search-input'));
  const updateMeta = document.getElementById('update-meta');
  const updateIntro = document.getElementById('update-intro');
  const point1 = document.getElementById('point-1');
  const point2 = document.getElementById('point-2');
  const point3 = document.getElementById('point-3');
  const valuationText = document.getElementById('valuation-text');
  const analystPhotoSlot = document.querySelector('.analyst-photo-slot');
  const analystBioSlot = document.querySelector('.analyst-bio-slot');
  let confirmSearchTimer = null;
  const defaultSearchPlaceholder = stockSearch?.getAttribute('placeholder') || '$_$';
  const tvContainer = document.querySelector('#tv-symbol-overview .tradingview-widget-container');
  const tvHost = document.getElementById('tv-symbol-overview');
  const splitBox = tvHost ? tvHost.closest('.split-box') : null;
  const fundamentalsPane = splitBox ? splitBox.querySelector('.split-pane-left') : null;
  const fundamentalsCloseButton = document.getElementById('fundamentals-close');
  const fundamentalsGrid = document.getElementById('fundamentals-grid');
  const widgetHeader = document.getElementById('widget-header');
  const fundamentalsHeader = document.getElementById('fundamentals-header');
  const chartDefaultConfig = {
    interval: 'D',
    range: '12M',
  };
  const resetChartDefaultView = () => {
    chartDefaultConfig.interval = 'D';
    chartDefaultConfig.range = '12M';
  };
  const preferredTvSymbolMap = {
    AAPL: ['NASDAQ:AAPL'],
    NVDA: ['NASDAQ:NVDA'],
    MSFT: ['NASDAQ:MSFT'],
    TSLA: ['NASDAQ:TSLA'],
    AMZN: ['NASDAQ:AMZN'],
    META: ['NASDAQ:META'],
    INDY: ['AMEX:INDY'],
    LULU: ['NASDAQ:LULU'],
    QQQ: ['NASDAQ:QQQ'],
    TQQQ: ['NASDAQ:TQQQ'],
    UNH: ['NYSE:UNH'],
    VOO: ['AMEX:VOO'],
    CASH: ['AMEX:BIL', 'TVC:DXY'],
    M2: ['FRED:WM2NS', 'FRED:M2SL'],
    TOTAL: ['AMEX:VTI'],
    BTC: ['COINBASE:BTCUSD', 'BITSTAMP:BTCUSD', 'BINANCE:BTCUSDT'],
    ETH: ['COINBASE:ETHUSD', 'BITSTAMP:ETHUSD', 'BINANCE:ETHUSDT'],
    USDTRY: ['FX_IDC:USDTRY', 'OANDA:USDTRY'],
    'USD/TRY': ['FX_IDC:USDTRY', 'OANDA:USDTRY'],
    BIST100: ['FX_IDC:USDTRY', 'OANDA:USDTRY', 'BIST:XU100'],
    'XAU/USD': ['OANDA:XAUUSD', 'FX_IDC:XAUUSD'],
  };
  let widgetFallbackTimer = null;
  let widgetRenderToken = 0;
  const directSymbolValidationCache = new Map();

  const probeTradingViewSymbol = async (candidate) => {
    const normalizedCandidate = String(candidate || '').trim().toUpperCase();
    if (!normalizedCandidate) return false;
    if (directSymbolValidationCache.has(normalizedCandidate)) {
      return directSymbolValidationCache.get(normalizedCandidate);
    }

    let verdict = null;
    try {
      const params = new URLSearchParams({
        symbol: normalizedCandidate,
        fields: 'type',
      });
      const response = await fetch(`https://scanner.tradingview.com/symbol?${params.toString()}`, {
        method: 'GET',
        mode: 'cors',
        credentials: 'omit',
        cache: 'no-store',
      });

      if (!response.ok) {
        verdict = response.status === 404 ? false : null;
      } else {
        const payload = await response.json().catch(() => null);
        if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
          const code = String(payload.code || '').toLowerCase();
          verdict = code === 'symbol_not_exists' ? false : true;
        } else {
          verdict = null;
        }
      }
    } catch {
      verdict = null;
    }

    if (verdict !== null) {
      directSymbolValidationCache.set(normalizedCandidate, verdict);
    }
    return verdict;
  };

  const pickValidDirectSymbolCandidateIndex = async (candidates, renderToken) => {
    let sawUnknown = false;

    for (let index = 0; index < candidates.length; index += 1) {
      const validity = await probeTradingViewSymbol(candidates[index]);
      if (renderToken !== widgetRenderToken) return null;
      if (validity === true) return index;
      if (validity === null) sawUnknown = true;
    }

    if (sawUnknown) return 0;
    return -1;
  };

  const setNoResultsMode = (enabled) => {
    if (!splitBox) return;
    splitBox.classList.toggle('is-no-results', Boolean(enabled));
  };

  const setFundamentalsCollapsed = (collapsed) => {
    if (!splitBox) return;
    const shouldCollapse = Boolean(collapsed);
    splitBox.classList.toggle('split-box-chart-only', shouldCollapse);
    if (fundamentalsPane) fundamentalsPane.setAttribute('aria-hidden', shouldCollapse ? 'true' : 'false');
    if (fundamentalsCloseButton) {
      fundamentalsCloseButton.setAttribute('aria-expanded', shouldCollapse ? 'false' : 'true');
    }
  };

  if (splitBox) {
    setFundamentalsCollapsed(splitBox.classList.contains('split-box-chart-only'));
  }

  const getTradingViewWidgetDimensions = () => {
    if (!tvHost) return { width: 0, height: 0 };
    const rect = tvHost.getBoundingClientRect();
    return {
      width: Math.max(0, Math.floor(rect.width)),
      height: Math.max(0, Math.floor(rect.height)),
    };
  };

  const bindDraggable = (element) => {
    if (!element) return;
    element.setAttribute('draggable', 'false');

    let startX = 0;
    let startY = 0;
    let baseX = 0;
    let baseY = 0;

    const readOffset = (name) => {
      const value = element.style.getPropertyValue(name).trim();
      const numeric = Number.parseFloat(value);
      return Number.isFinite(numeric) ? numeric : 0;
    };

    const handleMove = (clientX, clientY) => {
      const dx = clientX - startX;
      const dy = clientY - startY;
      element.style.setProperty('--drag-x', `${baseX + dx}px`);
      element.style.setProperty('--drag-y', `${baseY + dy}px`);
    };

    element.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      startX = event.clientX;
      startY = event.clientY;
      baseX = readOffset('--drag-x');
      baseY = readOffset('--drag-y');
      element.classList.add('dragging');
      element.setPointerCapture(event.pointerId);
    });

    element.addEventListener('pointermove', (event) => {
      if (!element.classList.contains('dragging')) return;
      handleMove(event.clientX, event.clientY);
    });

    const handleMouseMove = (event) => {
      if (!element.classList.contains('dragging')) return;
      handleMove(event.clientX, event.clientY);
    };

    const endDrag = (event) => {
      if (!element.classList.contains('dragging')) return;
      element.classList.remove('dragging');
      if (typeof event.pointerId === 'number' && element.hasPointerCapture(event.pointerId)) {
        element.releasePointerCapture(event.pointerId);
      }
    };

    element.addEventListener('pointerup', endDrag);
    element.addEventListener('pointercancel', endDrag);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', endDrag);
  };

  const buildChartSymbolCandidates = (stock) => {
    const candidates = [];
    const stockSymbol = String(stock.symbol || '').trim();
    const normalizedStockSymbol = stockSymbol.toUpperCase();
    const exchange = String(stock.exchange || 'NASDAQ').trim().toUpperCase();

    const preferredCandidates = preferredTvSymbolMap[stockSymbol] || preferredTvSymbolMap[normalizedStockSymbol];
    if (Array.isArray(preferredCandidates)) candidates.push(...preferredCandidates);

    if (Array.isArray(stock.tvSymbols)) candidates.push(...stock.tvSymbols);
    if (stock.tvSymbol) candidates.push(stock.tvSymbol);

    if (normalizedStockSymbol) {
      const compactPair = normalizedStockSymbol.replace(/[^A-Z0-9]/g, '');
      const isPairStyle = normalizedStockSymbol.includes('/');

      if (isPairStyle && compactPair) {
        candidates.push(`OANDA:${compactPair}`);
        candidates.push(`FX_IDC:${compactPair}`);
      } else {
        candidates.push(`${exchange}:${normalizedStockSymbol}`);
        if (exchange === 'NASDAQ' || exchange === 'NYSE' || exchange === 'AMEX') {
          candidates.push(`CBOE:${normalizedStockSymbol}`);
        }
        if (exchange === 'CRYPTO') {
          candidates.push(`COINBASE:${normalizedStockSymbol}USD`);
          candidates.push(`BITSTAMP:${normalizedStockSymbol}USD`);
          candidates.push(`BINANCE:${normalizedStockSymbol}USDT`);
        }
      }
      candidates.push(normalizedStockSymbol);
    }

    const deduped = [];
    const seen = new Set();
    candidates.forEach((value) => {
      const normalized = String(value || '').trim();
      if (!normalized) return;
      const normalizedKey = normalized.toUpperCase();
      if (seen.has(normalizedKey)) return;
      seen.add(normalizedKey);
      deduped.push(normalized);
    });
    return deduped;
  };

  const buildTradingViewWidgetUrl = (widgetType, config, locale = 'en') => {
    const encodedLocale = encodeURIComponent(locale);
    const encodedConfig = encodeURIComponent(JSON.stringify(config));
    const safeWidgetType = encodeURIComponent(String(widgetType || 'symbol-overview'));
    return `https://www.tradingview-widget.com/embed-widget/${safeWidgetType}/?locale=${encodedLocale}#${encodedConfig}`;
  };

  const ensureChartBlueToAmberFilter = () => {
    if (document.getElementById('chart-blue-to-amber')) return;
    const svgNs = 'http://www.w3.org/2000/svg';
    let host = document.getElementById('chart-filter-defs');
    if (!host) {
      host = document.createElementNS(svgNs, 'svg');
      host.setAttribute('id', 'chart-filter-defs');
      host.setAttribute('aria-hidden', 'true');
      host.setAttribute('focusable', 'false');
      host.style.position = 'absolute';
      host.style.width = '0';
      host.style.height = '0';
      host.style.overflow = 'hidden';
      host.style.pointerEvents = 'none';
      document.body.appendChild(host);
    }

    let defs = host.querySelector('defs');
    if (!defs) {
      defs = document.createElementNS(svgNs, 'defs');
      host.appendChild(defs);
    }

    const filter = document.createElementNS(svgNs, 'filter');
    filter.setAttribute('id', 'chart-blue-to-amber');
    filter.setAttribute('color-interpolation-filters', 'sRGB');

    const blueBrightMask = document.createElementNS(svgNs, 'feColorMatrix');
    blueBrightMask.setAttribute('in', 'SourceGraphic');
    blueBrightMask.setAttribute('type', 'matrix');
    blueBrightMask.setAttribute(
      'values',
      '0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 -1.1 -1.1 2.3 0 0',
    );
    blueBrightMask.setAttribute('result', 'blueBrightMaskRaw');

    const brightMaskCurve = document.createElementNS(svgNs, 'feComponentTransfer');
    brightMaskCurve.setAttribute('in', 'blueBrightMaskRaw');
    brightMaskCurve.setAttribute('result', 'blueBrightMask');

    const brightMaskAlpha = document.createElementNS(svgNs, 'feFuncA');
    brightMaskAlpha.setAttribute('type', 'gamma');
    brightMaskAlpha.setAttribute('amplitude', '1');
    brightMaskAlpha.setAttribute('exponent', '1.1');
    brightMaskAlpha.setAttribute('offset', '0');
    brightMaskCurve.appendChild(brightMaskAlpha);

    const amberFlood = document.createElementNS(svgNs, 'feFlood');
    amberFlood.setAttribute('flood-color', '#e6a100');
    amberFlood.setAttribute('result', 'amberFlood');

    const amberOnBrightBlue = document.createElementNS(svgNs, 'feComposite');
    amberOnBrightBlue.setAttribute('in', 'amberFlood');
    amberOnBrightBlue.setAttribute('in2', 'blueBrightMask');
    amberOnBrightBlue.setAttribute('operator', 'in');
    amberOnBrightBlue.setAttribute('result', 'amberOnBrightBlue');

    const baseWithoutBlue = document.createElementNS(svgNs, 'feComposite');
    baseWithoutBlue.setAttribute('in', 'SourceGraphic');
    baseWithoutBlue.setAttribute('in2', 'blueBrightMask');
    baseWithoutBlue.setAttribute('operator', 'out');
    baseWithoutBlue.setAttribute('result', 'baseWithoutBlue');

    const merge = document.createElementNS(svgNs, 'feMerge');
    const mergeBase = document.createElementNS(svgNs, 'feMergeNode');
    mergeBase.setAttribute('in', 'baseWithoutBlue');
    const mergeAmber = document.createElementNS(svgNs, 'feMergeNode');
    mergeAmber.setAttribute('in', 'amberOnBrightBlue');
    merge.appendChild(mergeBase);
    merge.appendChild(mergeAmber);

    filter.appendChild(blueBrightMask);
    filter.appendChild(brightMaskCurve);
    filter.appendChild(amberFlood);
    filter.appendChild(amberOnBrightBlue);
    filter.appendChild(baseWithoutBlue);
    filter.appendChild(merge);
    defs.appendChild(filter);
  };

  const renderTradingViewWidget = (stock) => {
    if (!tvContainer) return;
    ensureChartBlueToAmberFilter();
    if (widgetFallbackTimer) clearTimeout(widgetFallbackTimer);
    widgetRenderToken += 1;
    const renderToken = widgetRenderToken;

    const selectedRangeConfig = chartDefaultConfig;
    const { width, height } = getTradingViewWidgetDimensions();
    const fallbackWidth = tvHost ? Math.floor(tvHost.clientWidth) : 0;
    const fallbackHeight = tvHost ? Math.floor(tvHost.clientHeight) : 0;
    const widgetWidth = Math.max(280, width || fallbackWidth || 0);
    const widgetHeight = Math.max(220, height || fallbackHeight || 0);

    const chartSymbols = buildChartSymbolCandidates(stock);
    const renderUnavailableState = () => {
      if (renderToken !== widgetRenderToken) return;
      tvContainer.innerHTML = `
        <div class="tradingview-widget-container__widget tradingview-widget-unavailable">
          CHART UNAVAILABLE
        </div>
      `;
    };
    const renderNoResultsState = () => {
      if (renderToken !== widgetRenderToken) return;
      renderNoResultsScreen();
    };

    if (!chartSymbols.length) {
      if (stock.isDirectSymbol) {
        renderNoResultsState();
        return;
      }
      renderUnavailableState();
      return;
    }

    const renderAttempt = (candidateIndex) => {
      if (renderToken !== widgetRenderToken) return;
      const chartSymbol = chartSymbols[candidateIndex] || chartSymbols[0];
      if (!chartSymbol) {
        renderUnavailableState();
        return;
      }

      const iframe = document.createElement('iframe');
      iframe.setAttribute('scrolling', 'no');
      iframe.setAttribute('allowtransparency', 'true');
      iframe.setAttribute('frameborder', '0');
      iframe.setAttribute('allowfullscreen', 'true');
      iframe.loading = 'eager';
      iframe.referrerPolicy = 'no-referrer-when-downgrade';

      const embedConfig = {
        autosize: false,
        width: widgetWidth,
        height: widgetHeight,
        symbol: chartSymbol,
        interval: String(selectedRangeConfig.interval),
        range: String(selectedRangeConfig.range),
        timezone: 'exchange',
        theme: 'dark',
        style: '3',
        locale: 'en',
        allow_symbol_change: false,
        hide_top_toolbar: false,
        hide_side_toolbar: true,
        hide_legend: false,
        withdateranges: true,
        hide_volume: true,
        save_image: false,
        calendar: false,
        backgroundColor: '#000000',
        gridColor: 'rgba(255,176,0,0.22)',
        studies: [],
        overrides: {
          'paneProperties.background': '#000000',
          'paneProperties.backgroundType': 'solid',
          'paneProperties.vertGridProperties.color': 'rgba(255,176,0,0.14)',
          'paneProperties.horzGridProperties.color': 'rgba(255,176,0,0.22)',
          'mainSeriesProperties.style': 3,
          'mainSeriesProperties.showPriceLine': true,
          'mainSeriesProperties.priceLineColor': '#ffb000',
          'mainSeriesProperties.priceLineWidth': 1,
          'mainSeriesProperties.areaStyle.color1': 'rgba(255,176,0,0.35)',
          'mainSeriesProperties.areaStyle.color2': 'rgba(0,0,0,0.02)',
          'mainSeriesProperties.areaStyle.linecolor': '#ffb000',
          'mainSeriesProperties.areaStyle.linewidth': 2,
          'scalesProperties.textColor': '#8a8f9f',
          'scalesProperties.lineColor': 'rgba(255,176,0,0.26)',
        },
        support_host: 'https://www.tradingview.com',
      };
      iframe.src = buildTradingViewWidgetUrl('advanced-chart', embedConfig);

      let didAdvanceCandidate = false;
      const advanceCandidate = () => {
        if (didAdvanceCandidate) return;
        didAdvanceCandidate = true;
        if (renderToken !== widgetRenderToken) return;
        if (candidateIndex >= chartSymbols.length - 1) {
          if (stock.isDirectSymbol) {
            renderNoResultsState();
            return;
          }
          renderUnavailableState();
          return;
        }
        renderAttempt(candidateIndex + 1);
      };

      iframe.addEventListener('error', advanceCandidate, { once: true });
      iframe.addEventListener('load', () => {
        if (renderToken !== widgetRenderToken) return;
        if (widgetFallbackTimer) clearTimeout(widgetFallbackTimer);
        widgetFallbackTimer = null;
      }, { once: true });

      tvContainer.innerHTML = '';
      tvContainer.appendChild(iframe);

      widgetFallbackTimer = setTimeout(() => {
        if (renderToken !== widgetRenderToken) return;
        const activeFrame = tvContainer.querySelector('iframe');
        if (activeFrame !== iframe) return;
        advanceCandidate();
      }, 6000);
    };

    if (stock.isDirectSymbol) {
      pickValidDirectSymbolCandidateIndex(chartSymbols, renderToken)
        .then((candidateIndex) => {
          if (renderToken !== widgetRenderToken) return;
          if (candidateIndex === null) return;
          if (candidateIndex === -1) {
            renderNoResultsState();
            return;
          }
          renderAttempt(candidateIndex);
        })
        .catch(() => {
          if (renderToken !== widgetRenderToken) return;
          renderAttempt(0);
        });
      return;
    }

    renderAttempt(0);
  };

  let fundamentalsCachePromise = null;
  let fundamentalsRenderToken = 0;
  let fundamentalsCharts = [];
  let syntheticAnimationCleanup = null;
  let ansiUpLoadPromise = null;

  const destroyFundamentalsCharts = () => {
    fundamentalsCharts.forEach((chart) => {
      if (chart && typeof chart.destroy === 'function') chart.destroy();
    });
    fundamentalsCharts = [];
  };

  const stopSyntheticFundamentalsAnimation = () => {
    if (typeof syntheticAnimationCleanup === 'function') {
      syntheticAnimationCleanup();
    }
    syntheticAnimationCleanup = null;
  };

  const renderNoResultsScreen = () => {
    if (widgetFallbackTimer) {
      clearTimeout(widgetFallbackTimer);
      widgetFallbackTimer = null;
    }
    setNoResultsMode(true);
    if (tvContainer) {
      tvContainer.innerHTML = `
        <div class="tradingview-widget-container__widget tradingview-widget-no-results">
          NO RESULTS
        </div>
      `;
    }
    fundamentalsRenderToken += 1;
    stopSyntheticFundamentalsAnimation();
    destroyFundamentalsCharts();
    if (fundamentalsGrid) fundamentalsGrid.innerHTML = '';
    if (widgetHeader) widgetHeader.textContent = '—';
  };

  const loadAnsiUp = () => {
    if (typeof window.AnsiUp === 'function') return Promise.resolve(window.AnsiUp);
    if (!ansiUpLoadPromise) {
      ansiUpLoadPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/ansi_up@5.0.0/ansi_up.js';
        script.async = true;
        script.onload = () => {
          if (typeof window.AnsiUp === 'function') {
            resolve(window.AnsiUp);
            return;
          }
          reject(new Error('AnsiUp not available on window'));
        };
        script.onerror = () => reject(new Error('Failed to load ansi_up.js'));
        document.head.appendChild(script);
      }).catch((error) => {
        ansiUpLoadPromise = null;
        throw error;
      });
    }
    return ansiUpLoadPromise;
  };

  const loadFundamentalsData = () => {
    if (!fundamentalsCachePromise) {
      fundamentalsCachePromise = fetch('./sample-stock-fundamentals.json', { cache: 'no-store' })
        .then((response) => (response.ok ? response.json() : { symbols: {} }))
        .catch(() => ({ symbols: {} }));
    }
    return fundamentalsCachePromise;
  };

  const formatMoney = (value) => {
    if (!Number.isFinite(value)) return 'N/A';
    const abs = Math.abs(value);
    if (abs >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
    if (abs >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
    return `$${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  };

  const formatPercent = (value) => {
    if (!Number.isFinite(value)) return 'N/A';
    return `${(value * 100).toFixed(1)}%`;
  };

  const getFundMetricValue = (metric) => (metric && Number.isFinite(metric.value) ? metric.value : NaN);

  const toBillions = (value) => (Number.isFinite(value) ? value / 1e9 : null);
  const safeRatio = (numerator, denominator) => {
    if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) return NaN;
    return numerator / denominator;
  };
  const metricUsd = (value, end, filed, fy, fp = 'FY', form = 'MODEL', tag = 'ModelMetric') => ({
    value,
    unit: 'USD',
    end,
    filed,
    fy,
    fp,
    form,
    tag,
  });
  const metricEps = (value, end, filed, fy, fp = 'FY', form = 'MODEL') => ({
    value,
    unit: 'USD/shares',
    end,
    filed,
    fy,
    fp,
    form,
    tag: 'EarningsPerShareBasic',
  });
  const fallbackFundamentalsUpdatedAt = '2026-02-15';
  const portfolioFundamentalsFallback = {
    INDY: {
      symbol: 'INDY',
      company: 'iShares India 50 ETF',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(215000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'InvestmentIncome'),
      grossProfit: metricUsd(145000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetInvestmentIncome'),
      operatingIncome: metricUsd(108000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'OperatingIncomeLoss'),
      netIncome: metricUsd(86000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetIncomeLoss'),
      eps: metricEps(2.41, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR'),
      assets: metricUsd(7600000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'Assets'),
      liabilities: metricUsd(470000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'Liabilities'),
      equity: metricUsd(7130000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'StockholdersEquity'),
      cash: metricUsd(92000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(104000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.6744186046511628,
      netMargin: 0.4,
    },
    QQQ: {
      symbol: 'QQQ',
      company: 'Invesco QQQ Trust Series 1',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(4850000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'InvestmentIncome'),
      grossProfit: metricUsd(3360000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetInvestmentIncome'),
      operatingIncome: metricUsd(2950000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'OperatingIncomeLoss'),
      netIncome: metricUsd(2410000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetIncomeLoss'),
      eps: metricEps(22.37, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR'),
      assets: metricUsd(332000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'Assets'),
      liabilities: metricUsd(5400000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'Liabilities'),
      equity: metricUsd(326600000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'StockholdersEquity'),
      cash: metricUsd(2150000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(2790000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.6927835051546391,
      netMargin: 0.4969072164948454,
    },
    TQQQ: {
      symbol: 'TQQQ',
      company: 'ProShares UltraPro QQQ',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(1280000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'InvestmentIncome'),
      grossProfit: metricUsd(805000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetInvestmentIncome'),
      operatingIncome: metricUsd(682000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'OperatingIncomeLoss'),
      netIncome: metricUsd(524000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetIncomeLoss'),
      eps: metricEps(6.82, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR'),
      assets: metricUsd(24500000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'Assets'),
      liabilities: metricUsd(3600000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'Liabilities'),
      equity: metricUsd(20900000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'StockholdersEquity'),
      cash: metricUsd(640000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(588000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.62890625,
      netMargin: 0.409375,
    },
    UNH: {
      symbol: 'UNH',
      company: 'UnitedHealth Group Incorporated',
      cik: '0000731766',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(409000000000, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K', 'RevenueFromContractWithCustomerExcludingAssessedTax'),
      grossProfit: metricUsd(101000000000, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K', 'GrossProfit'),
      operatingIncome: metricUsd(32700000000, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K', 'OperatingIncomeLoss'),
      netIncome: metricUsd(23200000000, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K', 'NetIncomeLoss'),
      eps: metricEps(26.41, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K'),
      assets: metricUsd(319000000000, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K', 'Assets'),
      liabilities: metricUsd(205000000000, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K', 'Liabilities'),
      equity: metricUsd(114000000000, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K', 'StockholdersEquity'),
      cash: metricUsd(36800000000, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(30800000000, '2025-12-31', '2026-02-15', 2025, 'FY', '10-K', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.2469437652811736,
      netMargin: 0.05672371638141809,
    },
    VOO: {
      symbol: 'VOO',
      company: 'Vanguard S&P 500 ETF',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(3250000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'InvestmentIncome'),
      grossProfit: metricUsd(2190000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetInvestmentIncome'),
      operatingIncome: metricUsd(1870000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'OperatingIncomeLoss'),
      netIncome: metricUsd(1460000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetIncomeLoss'),
      eps: metricEps(19.54, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR'),
      assets: metricUsd(512000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'Assets'),
      liabilities: metricUsd(6200000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'Liabilities'),
      equity: metricUsd(505800000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'StockholdersEquity'),
      cash: metricUsd(2890000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(1710000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'N-CSR', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.6738461538461539,
      netMargin: 0.4492307692307692,
    },
    CASH: {
      symbol: 'CASH',
      company: 'Cash Position (Synthetic)',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(0, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Revenue'),
      grossProfit: metricUsd(0, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'GrossProfit'),
      operatingIncome: metricUsd(0, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'OperatingIncomeLoss'),
      netIncome: metricUsd(0, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetIncomeLoss'),
      eps: metricEps(0, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL'),
      assets: metricUsd(12500000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Assets'),
      liabilities: metricUsd(0, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Liabilities'),
      equity: metricUsd(12500000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'StockholdersEquity'),
      cash: metricUsd(12500000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(0, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0,
      netMargin: 0,
    },
    M2: {
      symbol: 'M2',
      company: 'Global Money Supply M2 (Synthetic)',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(81200000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'LiquidityProxy'),
      grossProfit: metricUsd(40300000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'GrossProfit'),
      operatingIncome: metricUsd(28600000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'OperatingIncomeLoss'),
      netIncome: metricUsd(22300000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetIncomeLoss'),
      eps: metricEps(6.2, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL'),
      assets: metricUsd(934000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Assets'),
      liabilities: metricUsd(241000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Liabilities'),
      equity: metricUsd(693000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'StockholdersEquity'),
      cash: metricUsd(35800000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(17100000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.4963054187192118,
      netMargin: 0.2746305418719212,
    },
    BTC: {
      symbol: 'BTC',
      company: 'Bitcoin Spot (Synthetic)',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(89400000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetworkValueProxy'),
      grossProfit: metricUsd(53600000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'GrossProfit'),
      operatingIncome: metricUsd(38800000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'OperatingIncomeLoss'),
      netIncome: metricUsd(32600000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetIncomeLoss'),
      eps: metricEps(15.4, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL'),
      assets: metricUsd(1165000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Assets'),
      liabilities: metricUsd(121000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Liabilities'),
      equity: metricUsd(1044000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'StockholdersEquity'),
      cash: metricUsd(28400000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(31200000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.5995525727069351,
      netMargin: 0.3646532438478747,
    },
    ETH: {
      symbol: 'ETH',
      company: 'Ethereum Spot (Synthetic)',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(38200000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetworkValueProxy'),
      grossProfit: metricUsd(21200000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'GrossProfit'),
      operatingIncome: metricUsd(14600000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'OperatingIncomeLoss'),
      netIncome: metricUsd(11800000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetIncomeLoss'),
      eps: metricEps(8.6, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL'),
      assets: metricUsd(452000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Assets'),
      liabilities: metricUsd(64200000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Liabilities'),
      equity: metricUsd(387800000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'StockholdersEquity'),
      cash: metricUsd(19600000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(13300000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.5549738219895288,
      netMargin: 0.3089005235602094,
    },
    'USD/TRY': {
      symbol: 'USD/TRY',
      company: 'USD/TRY FX Pair (Synthetic)',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'TRY',
      data_source: 'Buildings model data',
      revenue: metricUsd(9200000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'MacroRegimeProxy'),
      grossProfit: metricUsd(4360000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'GrossProfit'),
      operatingIncome: metricUsd(3110000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'OperatingIncomeLoss'),
      netIncome: metricUsd(2420000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetIncomeLoss'),
      eps: metricEps(4.1, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL'),
      assets: metricUsd(128000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Assets'),
      liabilities: metricUsd(70500000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Liabilities'),
      equity: metricUsd(57500000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'StockholdersEquity'),
      cash: metricUsd(18600000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(2960000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.47391304347826085,
      netMargin: 0.26304347826086955,
    },
    BIST100: {
      symbol: 'BIST100',
      company: 'Borsa Istanbul 100 Index (Synthetic)',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'TRY',
      data_source: 'Buildings model data',
      revenue: metricUsd(14500000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'IndexEarningsProxy'),
      grossProfit: metricUsd(6820000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'GrossProfit'),
      operatingIncome: metricUsd(4810000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'OperatingIncomeLoss'),
      netIncome: metricUsd(3520000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetIncomeLoss'),
      eps: metricEps(5.1, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL'),
      assets: metricUsd(176000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Assets'),
      liabilities: metricUsd(92100000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Liabilities'),
      equity: metricUsd(83900000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'StockholdersEquity'),
      cash: metricUsd(22800000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(4390000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.4703448275862069,
      netMargin: 0.24275862068965518,
    },
    'XAU/USD': {
      symbol: 'XAU/USD',
      company: 'Gold Spot (Synthetic)',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(12800000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'CommodityValueProxy'),
      grossProfit: metricUsd(6110000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'GrossProfit'),
      operatingIncome: metricUsd(4530000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'OperatingIncomeLoss'),
      netIncome: metricUsd(3790000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetIncomeLoss'),
      eps: metricEps(4.3, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL'),
      assets: metricUsd(233000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Assets'),
      liabilities: metricUsd(41000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Liabilities'),
      equity: metricUsd(192000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'StockholdersEquity'),
      cash: metricUsd(11200000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(3680000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.47734375,
      netMargin: 0.29609375,
    },
    TOTAL: {
      symbol: 'TOTAL',
      company: 'Buildings Total (Synthetic)',
      cik: 'N/A',
      period_end: '2025-12-31',
      currency: 'USD',
      data_source: 'Buildings model data',
      revenue: metricUsd(1665000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Revenue'),
      grossProfit: metricUsd(428000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'GrossProfit'),
      operatingIncome: metricUsd(205000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'OperatingIncomeLoss'),
      netIncome: metricUsd(155000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetIncomeLoss'),
      eps: metricEps(19.84, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL'),
      assets: metricUsd(1210000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Assets'),
      liabilities: metricUsd(392000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'Liabilities'),
      equity: metricUsd(818000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'StockholdersEquity'),
      cash: metricUsd(52100000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'CashAndCashEquivalentsAtCarryingValue'),
      operatingCashFlow: metricUsd(223000000000, '2025-12-31', '2026-02-15', 2025, 'FY', 'MODEL', 'NetCashProvidedByUsedInOperatingActivities'),
      grossMargin: 0.25705705705705704,
      netMargin: 0.09309309309309309,
    },
  };

  const formatDateCompact = (value) => {
    if (!value) return 'N/A';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: '2-digit' });
  };

  const metricPeriodLabel = (metric) => {
    if (!metric) return 'N/A';
    if (Number.isFinite(metric.fy) && metric.fp) return `${metric.fy} ${metric.fp}`;
    if (Number.isFinite(metric.fy)) return String(metric.fy);
    return metric.end ? formatDateCompact(metric.end) : 'N/A';
  };

  const getThemeColor = (name, fallback) => {
    const rootStyles = getComputedStyle(document.documentElement);
    const value = rootStyles.getPropertyValue(name).trim();
    return value || fallback;
  };

  const escapeHtml = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

  const isSyntheticFundamentalsEntry = (primaryEntry, entry) => {
    if (primaryEntry || !entry) return false;
    return String(entry.company || '').includes('(Synthetic)');
  };

  const startSyntheticFundamentalsAnimation = async (mountEl, symbol) => {
    if (!mountEl) return;
    stopSyntheticFundamentalsAnimation();

    const asciiEl = mountEl.querySelector('#ascii, .fund-synthetic-ascii');
    if (!asciiEl) return;

    let canceled = false;
    let intervalId = null;
    let waitFramesId = null;

    syntheticAnimationCleanup = () => {
      canceled = true;
      if (waitFramesId) clearInterval(waitFramesId);
      if (intervalId) clearInterval(intervalId);
    };

    const isFrameArray = (value) => Array.isArray(value) && value.length > 0 && typeof value[0] === 'string';

    const pickFrames = (candidate) => {
      if (!candidate) return [];
      if (isFrameArray(candidate)) return candidate;
      if (typeof candidate !== 'object') return [];

      const nestedKeys = ['frames', 'asciiFrames', 'skullFrames', 'animationFrames', 'data', 'items'];
      for (const key of nestedKeys) {
        if (isFrameArray(candidate[key])) return candidate[key];
      }
      return [];
    };

    const readFrames = () => {
      const candidates = [
        window.skullFrames,
        window.asciiFrames,
        window.SKULL_FRAMES,
        window.ASCII_FRAMES,
        window.__skullFrames,
        window.__asciiFrames,
        window.skullAnimation,
        window.asciiAnimation,
        window.skullData,
        window.asciiData,
        window.dropboxFrames,
      ];

      for (const candidate of candidates) {
        const frames = pickFrames(candidate);
        if (frames.length) return frames;
      }

      if (typeof frames !== 'undefined') {
        const frameList = pickFrames(frames);
        if (frameList.length) return frameList;
      }
      if (typeof skullFrames !== 'undefined') {
        const frameList = pickFrames(skullFrames);
        if (frameList.length) return frameList;
      }
      if (typeof asciiFrames !== 'undefined') {
        const frameList = pickFrames(asciiFrames);
        if (frameList.length) return frameList;
      }

      if (typeof window.getSkullFrames === 'function') {
        const frames = pickFrames(window.getSkullFrames());
        if (frames.length) return frames;
      }
      if (typeof window.getAsciiFrames === 'function') {
        const frames = pickFrames(window.getAsciiFrames());
        if (frames.length) return frames;
      }

      // Last resort for legacy globals named `frames` if they are actual string arrays.
      const legacyFrames = pickFrames(window.frames);
      if (legacyFrames.length) return legacyFrames;

      return [];
    };

    try {
      const AnsiUpCtor = await loadAnsiUp();
      if (canceled) return;

      const ansi_up = new AnsiUpCtor();
      const fps = 12;

      const ANSI_RE = /\x1B\[[0-?]*[ -/]*[@-~]/g;
      const BG_SET = new Set(['m', ' ']);
      const detectTopCrop = (frame, maxScan = 60, threshold = 0.08) => {
        const lines = String(frame || '').replace(ANSI_RE, '').split('\n');
        const limit = Math.min(maxScan, lines.length);
        for (let r = 0; r < limit; r += 1) {
          const line = lines[r] || '';
          if (!line.length) continue;
          let fg = 0;
          let total = 0;
          for (let i = 0; i < line.length; i += 1) {
            const ch = line[i];
            if (ch !== '\r' && ch !== '\n') {
              total += 1;
              if (!BG_SET.has(ch)) fg += 1;
            }
          }
          if (total > 0 && fg / total >= threshold) return r;
        }
        return 0;
      };

      const whenFramesReady = (cb) => {
        const initialFrames = readFrames();
        if (initialFrames.length) {
          cb(initialFrames);
          return;
        }
        asciiEl.textContent = `Waiting for skull frames for ${symbol}...`;
        const startedAt = Date.now();
        waitFramesId = setInterval(() => {
          if (canceled) return;
          const pendingFrames = readFrames();
          if (pendingFrames.length) {
            clearInterval(waitFramesId);
            waitFramesId = null;
            cb(pendingFrames);
            return;
          }
          if (Date.now() - startedAt > 5000) {
            clearInterval(waitFramesId);
            waitFramesId = null;
            asciiEl.textContent = `No skull frames loaded for ${symbol}. Populate assets/skull-frames.js`;
          }
        }, 50);
      };

      whenFramesReady((frames) => {
        if (canceled || !Array.isArray(frames) || !frames.length) {
          asciiEl.textContent = `No animation frames for ${symbol}.`;
          return;
        }

        const first = frames[0] || '';
        const TOP_CROP = detectTopCrop(first, 60, 0.08);
        const BOTTOM_CROP = 0;
        const cropFrame = (frame) => {
          const lines = String(frame || '').split('\n');
          const start = Math.min(TOP_CROP, lines.length);
          const end = BOTTOM_CROP ? -BOTTOM_CROP : undefined;
          return lines.slice(start, end).join('\n');
        };

        const colorCycle = [
          getThemeColor('--red', '#ff4d4d'),
          getThemeColor('--amber', '#ffb000'),
          getThemeColor('--green', '#00ff66'),
        ];
        let colorIndex = 0;
        let i = 0;
        const draw = () => {
          if (canceled || document.hidden) return;
          const raw = frames[i] || '';
          const cropped = cropFrame(raw);
          asciiEl.style.color = colorCycle[colorIndex];
          asciiEl.innerHTML = ansi_up.ansi_to_html(cropped);
          colorIndex = (colorIndex + 1) % colorCycle.length;
          i = (i + 1) % frames.length;
        };

        intervalId = setInterval(draw, 1000 / fps);
        draw();
      });
    } catch (error) {
      asciiEl.textContent = `Animation loader failed for ${symbol}.`;
      console.warn('Synthetic fundamentals animation failed:', error);
    }
  };

  const renderBloombergFundTable = (title, rows) => {
    const tableRows = rows.map((row) => {
      const valueClass = Number.isFinite(row.raw) && row.raw < 0 ? 'fund-negative' : '';
      return `
        <tr>
          <td>${escapeHtml(row.label)}</td>
          <td class="${valueClass}">${escapeHtml(row.value)}</td>
          <td>${escapeHtml(row.period)}</td>
        </tr>
      `;
    }).join('');

    return `
      <section class="fund-block">
        <div class="fund-block-title">${escapeHtml(title)}</div>
        <div class="fund-table-scroll">
          <table class="bbg-fund-table" role="table">
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Value</th>
                <th scope="col">Period</th>
              </tr>
            </thead>
            <tbody>${tableRows}</tbody>
          </table>
        </div>
      </section>
    `;
  };

  const renderFundamentalsCharts = (entry) => {
    if (!fundamentalsGrid) return;
    const scaleChartEl = document.getElementById('fund-chart-scale');
    const ratioChartEl = document.getElementById('fund-chart-ratios');
    if (!scaleChartEl || !ratioChartEl) return;

    if (typeof window.Highcharts !== 'object') {
      scaleChartEl.innerHTML = '<div class="fund-chart-fallback">Highcharts failed to load.</div>';
      ratioChartEl.innerHTML = '<div class="fund-chart-fallback">Highcharts failed to load.</div>';
      return;
    }

    const theme = {
      text: getThemeColor('--bbg-text', '#e6e8eb'),
      mutedText: getThemeColor('--bbg-text-muted', '#9aa0a6'),
      surface: getThemeColor('--bbg-surface-1', '#16181c'),
      border: getThemeColor('--bbg-border', '#2a2e35'),
    };

    const revenue = getFundMetricValue(entry.revenue);
    const grossProfit = getFundMetricValue(entry.grossProfit);
    const operatingIncome = getFundMetricValue(entry.operatingIncome);
    const netIncome = getFundMetricValue(entry.netIncome);
    const operatingCashFlow = getFundMetricValue(entry.operatingCashFlow);
    const cash = getFundMetricValue(entry.cash);
    const assets = getFundMetricValue(entry.assets);

    const categoryLabels = ['Revenue', 'Gross Profit', 'Op Income', 'Net Income', 'Op CF'];
    const valueSeries = [
      toBillions(revenue),
      toBillions(grossProfit),
      toBillions(operatingIncome),
      toBillions(netIncome),
      toBillions(operatingCashFlow),
    ];

    const grossMarginPct = Number.isFinite(Number(entry.grossMargin)) ? Number(entry.grossMargin) * 100 : null;
    const operatingMarginPct = Number.isFinite(safeRatio(operatingIncome, revenue))
      ? safeRatio(operatingIncome, revenue) * 100
      : null;
    const netMarginPct = Number.isFinite(Number(entry.netMargin)) ? Number(entry.netMargin) * 100 : null;
    const cashToAssetsPct = Number.isFinite(safeRatio(cash, assets)) ? safeRatio(cash, assets) * 100 : null;
    const cfConversionPct = Number.isFinite(safeRatio(operatingCashFlow, netIncome))
      ? safeRatio(operatingCashFlow, netIncome) * 100
      : null;

    const ratioCategories = ['Gross Mgn', 'Operating Mgn', 'Net Mgn', 'Cash / Assets', 'CF Conversion'];
    const ratioSeries = [grossMarginPct, operatingMarginPct, netMarginPct, cashToAssetsPct, cfConversionPct];

    const validRatioValues = ratioSeries.filter((value) => Number.isFinite(value));
    const ratioMin = validRatioValues.length ? Math.min(...validRatioValues) : 0;
    const ratioMax = validRatioValues.length ? Math.max(...validRatioValues) : 100;

    const axisLineColor = 'rgba(42, 46, 53, 0.9)';
    const scaleChart = window.Highcharts.chart(scaleChartEl, {
      credits: { enabled: false },
      accessibility: { enabled: false },
      legend: { enabled: false },
      chart: {
        type: 'column',
        backgroundColor: 'transparent',
        spacing: [10, 10, 10, 10],
      },
      title: { text: null },
      xAxis: {
        categories: categoryLabels,
        lineColor: axisLineColor,
        tickColor: axisLineColor,
        labels: { style: { color: theme.mutedText, fontSize: '11px' } },
      },
      yAxis: {
        title: { text: null },
        gridLineColor: axisLineColor,
        labels: {
          style: { color: theme.mutedText, fontSize: '11px' },
          formatter() {
            return `${this.value}B`;
          },
        },
      },
      tooltip: {
        backgroundColor: theme.surface,
        borderColor: theme.border,
        style: { color: theme.text },
        useHTML: true,
        pointFormatter() {
          if (!Number.isFinite(this.y)) return '<span>N/A</span>';
          return `<span>${this.category}: <b>${this.y.toFixed(1)}B</b></span>`;
        },
      },
      series: [{
        name: 'USD Billions',
        data: valueSeries.map((value, index) => ({
          y: value,
          color: [
            'rgba(255,176,0,0.72)',
            'rgba(230,232,235,0.65)',
            'rgba(83,201,134,0.58)',
            'rgba(228,111,111,0.58)',
            'rgba(255,176,0,0.52)',
          ][index % 5],
        })),
        borderWidth: 0,
        borderRadius: 0,
        pointPadding: 0.12,
        groupPadding: 0.18,
      }],
    });

    const ratioChart = window.Highcharts.chart(ratioChartEl, {
      credits: { enabled: false },
      accessibility: { enabled: false },
      legend: { enabled: false },
      chart: {
        type: 'bar',
        backgroundColor: 'transparent',
        spacing: [10, 10, 10, 10],
      },
      title: { text: null },
      xAxis: {
        categories: ratioCategories,
        lineColor: axisLineColor,
        tickColor: axisLineColor,
        labels: { style: { color: theme.mutedText, fontSize: '11px' } },
      },
      yAxis: {
        title: { text: null },
        min: ratioMin < 0 ? Math.floor(ratioMin * 1.1) : 0,
        max: ratioMax > 0 ? Math.ceil(ratioMax * 1.1) : null,
        gridLineColor: axisLineColor,
        labels: {
          style: { color: theme.mutedText, fontSize: '11px' },
          formatter() {
            return `${this.value}%`;
          },
        },
      },
      tooltip: {
        backgroundColor: theme.surface,
        borderColor: theme.border,
        style: { color: theme.text },
        useHTML: true,
        pointFormatter() {
          if (!Number.isFinite(this.y)) return '<span>N/A</span>';
          return `<span>${this.category}: <b>${this.y.toFixed(1)}%</b></span>`;
        },
      },
      series: [{
        name: 'Ratio',
        data: ratioSeries.map((value, index) => ({
          y: value,
          color: index < 3 ? 'rgba(255,176,0,0.68)' : 'rgba(83,201,134,0.58)',
        })),
        borderWidth: 0,
        borderRadius: 0,
      }],
    });

    fundamentalsCharts.push(scaleChart, ratioChart);
  };

  const renderFundamentalsPanel = async (stock) => {
    if (!fundamentalsGrid) return;
    const token = ++fundamentalsRenderToken;
    destroyFundamentalsCharts();
    stopSyntheticFundamentalsAnimation();
    fundamentalsGrid.innerHTML = '<div class="fund-empty-state">Loading fundamentals...</div>';

    const dataset = await loadFundamentalsData();
    if (token !== fundamentalsRenderToken) return;

    const primaryEntry = dataset?.symbols?.[stock.symbol];
    const entry = primaryEntry || portfolioFundamentalsFallback[stock.symbol];
    if (!entry) {
      fundamentalsGrid.innerHTML = '<div class="fund-empty-state">No fundamentals available</div>';
      return;
    }

    if (isSyntheticFundamentalsEntry(primaryEntry, entry)) {
      fundamentalsGrid.innerHTML = `
        <div class="fund-synthetic-animation-shell">
          <div class="fund-synthetic-animation-stage">
            <pre id="ascii" class="fund-synthetic-ascii" aria-label="${escapeHtml(stock.symbol)} rotating skull animation"></pre>
          </div>
        </div>
      `;
      startSyntheticFundamentalsAnimation(fundamentalsGrid, stock.symbol);
      return;
    }

    const revenue = getFundMetricValue(entry.revenue);
    const operatingIncome = getFundMetricValue(entry.operatingIncome);
    const liabilities = getFundMetricValue(entry.liabilities);
    const equity = getFundMetricValue(entry.equity);
    const cash = getFundMetricValue(entry.cash);
    const assets = getFundMetricValue(entry.assets);
    const operatingCashFlow = getFundMetricValue(entry.operatingCashFlow);
    const netIncome = getFundMetricValue(entry.netIncome);

    const operatingMargin = safeRatio(operatingIncome, revenue);
    const cashToAssets = safeRatio(cash, assets);
    const debtToEquity = safeRatio(liabilities, equity);
    const cfConversion = safeRatio(operatingCashFlow, netIncome);

    const incomeRows = [
      { label: 'Revenue', value: formatMoney(revenue), raw: revenue, period: metricPeriodLabel(entry.revenue) },
      { label: 'Gross Profit', value: formatMoney(getFundMetricValue(entry.grossProfit)), raw: getFundMetricValue(entry.grossProfit), period: metricPeriodLabel(entry.grossProfit) },
      { label: 'Operating Income', value: formatMoney(operatingIncome), raw: operatingIncome, period: metricPeriodLabel(entry.operatingIncome) },
      { label: 'Net Income', value: formatMoney(netIncome), raw: netIncome, period: metricPeriodLabel(entry.netIncome) },
      { label: 'Op. Cash Flow', value: formatMoney(operatingCashFlow), raw: operatingCashFlow, period: metricPeriodLabel(entry.operatingCashFlow) },
      { label: 'EPS (Basic)', value: Number.isFinite(getFundMetricValue(entry.eps)) ? `$${getFundMetricValue(entry.eps).toFixed(2)}` : 'N/A', raw: getFundMetricValue(entry.eps), period: metricPeriodLabel(entry.eps) },
    ];

    const balanceRows = [
      { label: 'Cash', value: formatMoney(cash), raw: cash, period: metricPeriodLabel(entry.cash) },
      { label: 'Assets', value: formatMoney(assets), raw: assets, period: metricPeriodLabel(entry.assets) },
      { label: 'Liabilities', value: formatMoney(liabilities), raw: liabilities, period: metricPeriodLabel(entry.liabilities) },
      { label: 'Equity', value: formatMoney(equity), raw: equity, period: metricPeriodLabel(entry.equity) },
      { label: 'Gross Margin', value: formatPercent(Number(entry.grossMargin)), raw: Number(entry.grossMargin), period: metricPeriodLabel(entry.grossProfit) },
      { label: 'Operating Margin', value: formatPercent(operatingMargin), raw: operatingMargin, period: metricPeriodLabel(entry.operatingIncome) },
      { label: 'Net Margin', value: formatPercent(Number(entry.netMargin)), raw: Number(entry.netMargin), period: metricPeriodLabel(entry.netIncome) },
      { label: 'Cash / Assets', value: formatPercent(cashToAssets), raw: cashToAssets, period: metricPeriodLabel(entry.cash) },
      { label: 'Liab / Equity', value: Number.isFinite(debtToEquity) ? `${debtToEquity.toFixed(2)}x` : 'N/A', raw: debtToEquity, period: metricPeriodLabel(entry.liabilities) },
      { label: 'CF Conversion', value: Number.isFinite(cfConversion) ? `${cfConversion.toFixed(2)}x` : 'N/A', raw: cfConversion, period: metricPeriodLabel(entry.operatingCashFlow) },
    ];

    const updatedDate = formatDateCompact(primaryEntry ? dataset?.updated_at : fallbackFundamentalsUpdatedAt);
    const periodEnd = formatDateCompact(entry.period_end);
    const source = primaryEntry ? (dataset?.source || 'N/A') : (entry.data_source || 'Buildings model data');

    fundamentalsGrid.innerHTML = `
      <div class="fundamentals-layout">
        <div class="fund-strip" role="status">
          <span><strong>${escapeHtml(entry.symbol)}</strong> ${escapeHtml(entry.company)}</span>
          <span>Period End: ${escapeHtml(periodEnd)}</span>
          <span>Data Updated: ${escapeHtml(updatedDate)}</span>
          <span>Source: ${escapeHtml(source)}</span>
        </div>
        <div class="fund-table-grid">
          ${renderBloombergFundTable('Income & Cash Flow', incomeRows)}
          ${renderBloombergFundTable('Balance Sheet & Ratios', balanceRows)}
        </div>
        <div class="fund-chart-grid">
          <section class="fund-block">
            <div class="fund-block-title">Scale (USD Billions)</div>
            <div class="fund-chart" id="fund-chart-scale" aria-label="Fundamental scale chart"></div>
          </section>
          <section class="fund-block">
            <div class="fund-block-title">Efficiency and Leverage</div>
            <div class="fund-chart" id="fund-chart-ratios" aria-label="Fundamental ratio chart"></div>
          </section>
        </div>
      </div>
    `;

    renderFundamentalsCharts(entry);
  };
  if (stockTitle && titleSwitch){
    const stocks = [
      {
        symbol: 'AAPL',
        name: 'Apple Inc.',
        exchange: 'NASDAQ',
        intro: 'Quick take: still long Apple. January print was clean, cash is heavy, and execution is still better than peers.',
        points: [
          'Revenue and EPS beat; no accounting smoke in the release',
          'Services keeps printing high-margin dollars quarter after quarter',
          'Guide stayed firm enough for us to keep size on',
        ],
        valuation: 'Premium multiple stays. We pay up for clean books, durable cash flow, and repeatable margin.',
        meta: '',
      },
      {
        symbol: 'NVDA',
        name: 'NVIDIA Corp.',
        exchange: 'NASDAQ',
        intro: 'Quick take: we keep NVIDIA on a tight bullish leash. Big upside, big expectations, and zero room for sloppy numbers.',
        points: [
          'Feb call timing is set; this is an event-driven name right now',
          'Street will grade demand, guide, and margin line by line',
          'If numbers hold, momentum stays paid; if not, tape punishes fast',
        ],
        valuation: 'Multiple is expensive and we know it. We keep it for growth velocity, not for comfort.',
        meta: '',
      },
      {
        symbol: 'MSFT',
        name: 'Microsoft Corp.',
        exchange: 'NASDAQ',
        intro: 'Quick take: still long Microsoft. Enterprise cash engine is intact and AI spend is translating into revenue, not just headlines.',
        points: [
          'Azure and core cloud held up where it matters: billings and usage',
          'Copilot monetization keeps broadening inside enterprise accounts',
          'Operating discipline remained visible even with higher AI capex',
        ],
        valuation: 'We keep the quality premium. Recurring revenue plus scale economics earns it.',
        meta: '',
      },
      {
        symbol: 'TSLA',
        name: 'Tesla Inc.',
        exchange: 'NASDAQ',
        intro: 'Quick take: we trade Tesla with discipline, not emotion. Great optionality, messy quarter-to-quarter optics, and fast sentiment swings.',
        points: [
          'Pricing and demand are still the pressure points in auto',
          'Energy/storage keeps adding real contribution to the P&L mix',
          'Next platform and autonomy timeline stay key to upside case',
        ],
        valuation: 'We underwrite upside, but we haircut for margin volatility. Position size stays controlled.',
        meta: '',
      },
      {
        symbol: 'AMZN',
        name: 'Amazon.com Inc.',
        exchange: 'NASDAQ',
        intro: 'Quick take: still constructive on Amazon. Retail efficiency is real, and AWS keeps the long game funded.',
        points: [
          'Retail unit economics improved again in the latest release',
          'AI/data-center capex is high, but it is tied to demand',
          'Ads and third-party services keep lifting blended margins',
        ],
        valuation: 'We keep paying a premium while free cash flow keeps stepping up.',
        meta: '',
      },
      {
        symbol: 'INDY',
        name: 'iShares India 50 ETF',
        exchange: 'AMEX',
        intro: 'Quick take: INDY remains our India beta sleeve. Flows are sticky, but we watch valuation and currency sensitivity.',
        points: [
          'Macro sensitivity is mostly rates plus INR moves',
          'Breadth across top holdings matters more than one-name leadership',
          'Sizing stays tactical around global risk-on and risk-off rotations',
        ],
        valuation: 'We treat INDY as a macro vehicle, not a single-stock story. Position sizing does the heavy lifting.',
        meta: '',
      },
      {
        symbol: 'LULU',
        name: 'Lululemon Athletica Inc.',
        exchange: 'NASDAQ',
        intro: 'Quick take: we stay constructive on Lululemon. Brand strength and pricing power still matter in this tape.',
        points: [
          'North America comps remain the main read on near-term demand',
          'International expansion is still the cleanest multi-year growth leg',
          'Margin durability depends on inventory discipline and markdown control',
        ],
        valuation: 'We pay up for brand quality, but we keep sizing disciplined around consumer-spend volatility.',
        meta: '',
      },
      {
        symbol: 'QQQ',
        name: 'Invesco QQQ Trust',
        exchange: 'NASDAQ',
        intro: 'Quick take: QQQ stays core for large-cap growth exposure, but we keep discipline around concentration risk.',
        points: [
          'Mega-cap tech earnings continue to drive index direction',
          'Rates and duration expectations still dominate multiple expansion',
          'We keep risk balanced with position-size controls, not opinions',
        ],
        valuation: 'We own QQQ for liquid growth beta and rebalance with volatility, not headlines.',
        meta: '',
      },
      {
        symbol: 'TQQQ',
        name: 'ProShares UltraPro QQQ',
        exchange: 'NASDAQ',
        intro: 'Quick take: TQQQ is tactical leverage only. Conviction can be high, but holding periods stay deliberate.',
        points: [
          'Path dependency and volatility drag are always in play',
          'Upside is powerful when trend is persistent and broad',
          'Risk limits are mandatory, especially into event-heavy weeks',
        ],
        valuation: 'No static valuation story here. It is a leveraged instrument that requires active risk management.',
        meta: '',
      },
      {
        symbol: 'UNH',
        name: 'UnitedHealth Group',
        exchange: 'NYSE',
        intro: 'Quick take: UNH remains our defensive quality compounder inside healthcare with steady cash generation.',
        points: [
          'Medical-cost trend and reimbursement dynamics are key watch items',
          'Optum diversification supports earnings durability',
          'Execution quality still matters more than macro noise in this name',
        ],
        valuation: 'We pay for consistency and cash conversion, while respecting policy and utilization risk.',
        meta: '',
      },
      {
        symbol: 'VOO',
        name: 'Vanguard S&P 500 ETF',
        exchange: 'AMEX',
        intro: 'Quick take: VOO is our broad-market core. Low-friction exposure and compounding do the work over time.',
        points: [
          'Index concentration remains elevated, but still diversified enough for core exposure',
          'Rebalancing cadence matters more than short-term market noise',
          'We pair it with selective active sleeves for alpha attempts',
        ],
        valuation: 'VOO is a framework position: cheap implementation, broad breadth, and high discipline.',
        meta: '',
      },
      {
        symbol: 'CASH',
        name: 'Cash Position',
        exchange: 'TVC',
        exchangeLabel: 'CASH',
        tvSymbols: ['AMEX:BIL', 'TVC:DXY'],
        tvSymbol: 'TVC:DXY',
        intro: 'Quick take: cash is optionality. We keep dry powder to exploit dislocations without forced selling.',
        points: [
          'Cash weight expands when forward reward-to-risk compresses',
          'Deployment rules are predefined before volatility spikes',
          'Carry matters, but flexibility matters more in uncertain regimes',
        ],
        valuation: 'This is a risk-budget tool, not a growth position.',
        meta: '',
      },
      {
        symbol: 'M2',
        name: 'Global Money Supply',
        exchange: 'FRED',
        exchangeLabel: 'M2',
        tvSymbols: ['FRED:WM2NS', 'FRED:M2SL'],
        tvSymbol: 'FRED:WM2NS',
        intro: 'Quick take: M2 is our broad liquidity regime barometer for monetary expansion versus contraction.',
        points: [
          'Trend direction informs macro risk appetite and duration sensitivity',
          'Inflection points often lead cross-asset rotation before headlines catch up',
          'Policy transmission lag means signal interpretation must stay regime-aware',
        ],
        valuation: 'M2 is a macro-liquidity signal, not an equity-style valuation target.',
        meta: '',
      },
      {
        symbol: 'TOTAL',
        name: 'Buildings Total',
        exchange: 'AMEX',
        exchangeLabel: 'BUILDINGS',
        tvSymbol: 'AMEX:VTI',
        intro: 'Quick take: total view tracks aggregate exposure, concentration, and realized compounding across all sleeves.',
        points: [
          'The total line is what we optimize, not single-name narratives',
          'Correlation spikes are managed through sizing and hedge overlays',
          'Drawdown control remains the first KPI before upside capture',
        ],
        valuation: 'Buildings-level valuation is a weighted blend; allocation discipline is the real edge.',
        meta: '',
      },
      {
        symbol: 'META',
        name: 'Meta Platforms',
        exchange: 'NASDAQ',
        intro: 'Quick take: still long Meta. Ads are still printing and AI is improving monetization, not just optics.',
        points: [
          'Core ad engine remained strong in the latest quarter',
          'Recommendation AI improved engagement and ad conversion quality',
          'Capex is elevated, but tied to scale and future yield',
        ],
        valuation: 'Multiple stays supported while ad cash flow compounds and execution remains clean.',
        meta: '',
      },
      {
        symbol: 'BTC',
        name: 'Bitcoin',
        exchange: 'CRYPTO',
        tvSymbols: ['COINBASE:BTCUSD', 'BITSTAMP:BTCUSD', 'BINANCE:BTCUSDT'],
        tvSymbol: 'COINBASE:BTCUSD',
        intro: 'Quick take: Bitcoin remains our high-conviction macro-liquidity proxy with strict risk controls.',
        points: [
          'ETF flow direction remains the key short-term demand signal',
          'Volatility clusters around macro prints and policy headlines',
          'Position sizing must respect drawdown velocity in crypto',
        ],
        valuation: 'We treat BTC as a liquidity and risk sentiment barometer, not a traditional discounted cash-flow asset.',
        meta: '',
      },
      {
        symbol: 'ETH',
        name: 'Ethereum',
        exchange: 'CRYPTO',
        tvSymbols: ['COINBASE:ETHUSD', 'BITSTAMP:ETHUSD', 'BINANCE:ETHUSDT'],
        tvSymbol: 'COINBASE:ETHUSD',
        intro: 'Quick take: Ethereum is our programmable-asset beta with higher execution risk and higher optionality.',
        points: [
          'Network activity and fee trends matter for medium-term conviction',
          'ETH beta can diverge from BTC during narrative rotations',
          'We manage exposure tactically around volatility regime shifts',
        ],
        valuation: 'ETH valuation is regime-dependent; we focus on adoption, activity quality, and liquidity conditions.',
        meta: '',
      },
      {
        symbol: 'BIST100',
        name: 'Borsa Istanbul 100',
        exchange: 'BIST',
        tvSymbols: ['FX_IDC:USDTRY', 'OANDA:USDTRY', 'BIST:XU100'],
        tvSymbol: 'BIST:XU100',
        intro: 'Quick take: BIST100 is a tactical macro-equity exposure driven by domestic liquidity and currency conditions.',
        points: [
          'Local rates and inflation expectations remain primary drivers',
          'Index leadership breadth is critical for trend durability',
          'FX stability has an outsized impact on foreign flow appetite',
        ],
        valuation: 'We evaluate BIST100 with top-down macro filters first, then sector rotation and liquidity depth.',
        meta: '',
      },
      {
        symbol: 'USD/TRY',
        name: 'USD/TRY FX Rate',
        exchange: 'FX',
        tvSymbols: ['FX_IDC:USDTRY', 'OANDA:USDTRY'],
        tvSymbol: 'FX_IDC:USDTRY',
        intro: 'Quick take: USD/TRY is our primary domestic macro stress gauge for inflation, liquidity, and policy credibility.',
        points: [
          'Real-rate differentials and reserve policy shape medium-term trend',
          'Short-term spikes often cluster around macro data and policy communication',
          'Risk positioning should respect volatility regime shifts and liquidity windows',
        ],
        valuation: 'For USD/TRY, we model regime probabilities and policy path sensitivity rather than equity-style valuation multiples.',
        meta: '',
      },
      {
        symbol: 'XAU/USD',
        name: 'Gold Spot',
        exchange: 'FX',
        tvSymbols: ['OANDA:XAUUSD', 'FX_IDC:XAUUSD'],
        tvSymbol: 'OANDA:XAUUSD',
        intro: 'Quick take: XAU/USD is our policy-uncertainty and real-yield hedge when macro visibility deteriorates.',
        points: [
          'Real rates and USD direction dominate short-term path',
          'Positioning squeezes can produce sharp two-way moves',
          'We pair gold exposure with broader risk-book context',
        ],
        valuation: 'Gold is not a cash-flow story for us; it is portfolio insurance and regime diversification.',
        meta: '',
      },
      {
        symbol: 'TSM',
        name: 'Taiwan Semiconductor',
        exchange: 'NYSE',
        intro: 'Quick take: TSM is the world\'s most critical semiconductor foundry. AI capex waves directly fund its order book.',
        points: [
          'Advanced node leadership (3nm, 2nm) keeps pricing power elevated',
          'AI chip demand from NVDA, AMD, Apple drives record CoWoS capacity',
          'Geopolitical premium is real but foundry indispensability offsets it',
        ],
        valuation: 'We pay for structural irreplaceability and compounding capital return.',
        meta: '',
      },
      {
        symbol: 'PDD',
        name: 'PDD Holdings',
        exchange: 'NASDAQ',
        intro: 'Quick take: PDD runs two of the fastest-growing e-commerce engines globally through Pinduoduo and Temu.',
        points: [
          'Temu international expansion still accelerating but margin pressure rising',
          'Domestic Pinduoduo market share gains continue against Alibaba and JD',
          'Regulatory environment in China remains the key overhang to monitor',
        ],
        valuation: 'Discount to growth rate is compelling; we hold with regulatory risk priced in.',
        meta: '',
      },
      {
        symbol: 'ORCL',
        name: 'Oracle Corp.',
        exchange: 'NYSE',
        intro: 'Quick take: Oracle cloud inflection is real. Database lock-in plus AI infrastructure demand is a durable combination.',
        points: [
          'OCI cloud revenue acceleration is the key re-rating catalyst',
          'AI training cluster wins from hyperscalers add high-margin workloads',
          'Legacy database installed base provides sticky recurring cash flows',
        ],
        valuation: 'We pay a premium for cloud transition durability and AI infrastructure tailwinds.',
        meta: '',
      },
      {
        symbol: 'NOW',
        name: 'ServiceNow',
        exchange: 'NYSE',
        intro: 'Quick take: ServiceNow is enterprise workflow infrastructure. AI features are expanding deal sizes and retention.',
        points: [
          'Platform stickiness is among the highest in enterprise software',
          'AI SKUs lifting ACV per customer at a faster pace than expected',
          'Federal and international verticals add durable long-term runway',
        ],
        valuation: 'Growth quality justifies premium; we keep size while execution stays clean.',
        meta: '',
      },
      {
        symbol: 'MU',
        name: 'Micron Technology',
        exchange: 'NASDAQ',
        intro: 'Quick take: Micron is the AI memory cycle play. HBM supply tightness and data center DRAM demand are the tailwinds.',
        points: [
          'HBM3E ramp directly tied to NVDA GB200 platform demand',
          'DRAM pricing recovery from trough supports margin expansion',
          'NAND remains softer but supply discipline is improving across the industry',
        ],
        valuation: 'Cyclical premium warranted when HBM mix and pricing momentum align.',
        meta: '',
      },
      {
        symbol: 'INTU',
        name: 'Intuit Inc.',
        exchange: 'NASDAQ',
        intro: 'Quick take: Intuit compounds through tax and SMB finance dominance. AI integration is broadening monetization.',
        points: [
          'TurboTax and QuickBooks retention rates remain best-in-class',
          'Intuit Assist AI features increasing ARPU in small business segment',
          'Credit Karma monetization is the swing factor for near-term upside',
        ],
        valuation: 'We pay for recurring cash flow quality and platform switching costs.',
        meta: '',
      },
      {
        symbol: 'GOOGL',
        name: 'Alphabet Inc.',
        exchange: 'NASDAQ',
        intro: 'Quick take: Alphabet remains core. Search dominance is intact and Cloud is inflecting at the right time.',
        points: [
          'Search revenue growth reaccelerated; AI Overviews not yet cannibalizing',
          'Google Cloud margin expansion is the key re-rating driver this year',
          'YouTube advertising is benefiting from connected TV and shorts monetization',
        ],
        valuation: 'Search cash flow plus Cloud optionality supports our long position.',
        meta: '',
      },
      {
        symbol: 'CRM',
        name: 'Salesforce',
        exchange: 'NYSE',
        intro: 'Quick take: Salesforce is navigating the AI transition well with Agentforce driving early enterprise interest.',
        points: [
          'Agentforce pipeline is building; conversion to ARR is the key 2025 watch',
          'Data Cloud and Einstein GPT embedding deepens platform stickiness',
          'Margin expansion from prior cost discipline remains intact',
        ],
        valuation: 'We hold at this level; need AI revenue recognition evidence to add size.',
        meta: '',
      },
      {
        symbol: 'BIDU',
        name: 'Baidu Inc.',
        exchange: 'NASDAQ',
        intro: 'Quick take: Baidu is a China AI and search compounder trading at a deep discount to global peers.',
        points: [
          'ERNIE Bot large model leadership in China provides strategic moat',
          'Apollo Go autonomous vehicle fleet is the high-upside optionality play',
          'Core search revenue remains pressured but cloud AI is offsetting decline',
        ],
        valuation: 'Significant discount to NAV; we size for asymmetric optionality with regulatory risk managed.',
        meta: '',
      },
      {
        symbol: 'BABA',
        name: 'Alibaba Group',
        exchange: 'NYSE',
        intro: 'Quick take: Alibaba is the deep value China tech play. Cloud growth re-acceleration and AI investment are the catalysts.',
        points: [
          'Cloud revenue growth reaccelerated; AI inference demand is the driver',
          'International commerce via AliExpress and Lazada adds diversification',
          'Regulatory and macro headwinds in China are largely priced in at current levels',
        ],
        valuation: 'Compelling discount to sum-of-parts; we hold and look for cloud inflection confirmation.',
        meta: '',
      },
      {
        symbol: 'AVGO',
        name: 'Broadcom Inc.',
        exchange: 'NASDAQ',
        intro: 'Quick take: Broadcom is the custom AI ASIC and networking infrastructure compounder. VMware adds recurring software cash.',
        points: [
          'XPU custom AI chip contracts with hyperscalers are multi-year, high-margin',
          'Networking switching and routing for AI clusters drives hardware backlog',
          'VMware integration unlocking software recurring revenue step-change',
        ],
        valuation: 'Premium valuation is supported by AI backlog visibility and software margin mix.',
        meta: '',
      },
      {
        symbol: 'AMD',
        name: 'Advanced Micro Devices',
        exchange: 'NASDAQ',
        intro: 'Quick take: AMD is the credible challenger in both AI GPU and data center CPU markets with real traction.',
        points: [
          'MI300X gaining share in AI inference; hyperscaler deployments expanding',
          'EPYC server CPU continues to take share from Intel in data center',
          'PC and gaming remain softer but recovery is underway',
        ],
        valuation: 'AI GPU optionality and CPU share gain story justifies our position at current levels.',
        meta: '',
      },
      {
        symbol: 'ADBE',
        name: 'Adobe Inc.',
        exchange: 'NASDAQ',
        intro: 'Quick take: Adobe is navigating the generative AI transition from a position of creative workflow strength.',
        points: [
          'Firefly AI integration across Creative Cloud is driving early ARPU lift',
          'Document Cloud and Experience Cloud provide diversified recurring base',
          'Concern around AI disruption to core creative tools is the main valuation overhang',
        ],
        valuation: 'We hold with selective size; re-rating requires sustained AI monetization evidence.',
        meta: '',
      },
      {
        symbol: 'UAE',
        name: 'iShares MSCI UAE ETF',
        exchange: 'AMEX',
        intro: 'Quick take: UAE is our Gulf exposure sleeve. Energy transition and sovereign investment flows drive the macro backdrop.',
        points: [
          'UAE market benefiting from oil price stability and government diversification spending',
          'Low correlation to US equity beta provides portfolio diversification value',
          'Currency peg to USD removes foreign exchange risk from the position',
        ],
        valuation: 'We hold UAE for diversification and low-vol Gulf exposure alongside core tech positions.',
        meta: '',
      },
      {
        symbol: 'SQQQ',
        name: 'ProShares UltraPro Short QQQ',
        exchange: 'NASDAQ',
        intro: 'Quick take: SQQQ is our tactical hedge instrument. It is a short-term tool, never a long-term hold.',
        points: [
          'Triple inverse leverage amplifies losses in trending bull markets',
          'Used tactically as a hedge against large-cap tech drawdowns',
          'Decay from daily rebalancing makes it unsuitable for buy-and-hold',
        ],
        valuation: 'SQQQ is a risk-management instrument, not an investment thesis.',
        meta: '',
      },
      {
        symbol: 'IGV',
        name: 'iShares Expanded Tech-Software Sector ETF',
        exchange: 'AMEX',
        intro: 'Quick take: IGV gives concentrated software exposure with broader diversification than single-name picks.',
        points: [
          'Holdings concentrated in enterprise SaaS and infrastructure software leaders',
          'AI-driven software monetization is the long-term growth catalyst across holdings',
          'Lower single-name event risk than holding individual software names outright',
        ],
        valuation: 'We hold IGV as a software sector vehicle where single-name conviction is lower.',
        meta: '',
      },
    ];
    let stockIndex = 0;
    let activeStockOverride = null;
    const getActiveStock = () => activeStockOverride || stocks[stockIndex];
    let titleFitRaf = null;
    const renderRandomPixelPortrait = () => {
      if (!analystPhotoSlot) return;

      const size = 16;
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      canvas.width = size;
      canvas.height = size;
      canvas.className = 'analyst-pixel-portrait';
      if (!ctx) return;

      const palette = ['#000000', '#1b1200', '#4f3200', '#7a4d00', '#ffb000', '#ffd06b'];
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, size, size);

      for (let y = 0; y < size; y += 1) {
        for (let x = 0; x < size / 2; x += 1) {
          if (Math.random() < 0.44) {
            const color = palette[Math.floor(Math.random() * palette.length)];
            ctx.fillStyle = color;
            ctx.fillRect(x, y, 1, 1);
            ctx.fillRect(size - 1 - x, y, 1, 1);
          }
        }
      }

      analystPhotoSlot.innerHTML = '';
      analystPhotoSlot.appendChild(canvas);
    };

    const analystAliases = [
      'Cipher Lynx',
      'Nova Quill',
      'Delta Pike',
      'Amber Voss',
      'Echo Vale',
      'Rook Mercer',
      'Onyx Hale',
      'Jade Cross',
    ];
    const analystDesks = [
      'Macro + Tech Desk',
      'Growth Signals Unit',
      'Momentum Rotation Desk',
      'Cross-Asset Flow Team',
      'Event Risk Desk',
      'Quant Overlay Pod',
    ];
    const analystStyles = [
      'Trend-first. Risk-tight.',
      'Earnings tape specialist.',
      'Volatility aware allocator.',
      'Catalyst and cash-flow focused.',
      'Price action over narratives.',
      'Asymmetric setups hunter.',
    ];

    const pickRandom = (items) => items[Math.floor(Math.random() * items.length)];

    const renderRandomAnalystBio = () => {
      if (!analystBioSlot) return;
      analystBioSlot.innerHTML = `
        <div class="analyst-bio-lines">
          <span>${pickRandom(analystAliases)}</span>
          <span>${pickRandom(analystDesks)}</span>
          <span>${pickRandom(analystStyles)}</span>
        </div>
      `;
    };

    const fitStockTitle = () => {
      if (!stockTitle) return;

      const maxSize = window.innerWidth <= 1100 ? 20 : 27;
      const minSize = 14;
      let size = maxSize;

      stockTitle.style.fontSize = `${size}px`;
      stockTitle.style.lineHeight = '1';

      const available = stockTitle.clientWidth;
      if (!available) return;

      while (stockTitle.scrollWidth > available && size > minSize) {
        size -= 1;
        stockTitle.style.fontSize = `${size}px`;
      }
    };

    const scheduleTitleFit = () => {
      if (titleFitRaf) cancelAnimationFrame(titleFitRaf);
      titleFitRaf = requestAnimationFrame(() => {
        titleFitRaf = null;
        fitStockTitle();
      });
    };

    const isLikelyDirectSymbolQuery = (value) => {
      const trimmed = String(value || '').trim();
      if (!trimmed || /\s/.test(trimmed)) return false;
      return /^[A-Za-z0-9^][A-Za-z0-9^:./_+=!-]{0,39}$/.test(trimmed);
    };

    const buildDirectSymbolStock = (rawInput) => {
      if (!isLikelyDirectSymbolQuery(rawInput)) return null;

      const normalized = String(rawInput || '').trim().toUpperCase();
      const colonIndex = normalized.indexOf(':');
      const hasExplicitExchange = colonIndex > 0;
      const symbol = hasExplicitExchange ? normalized.slice(colonIndex + 1) : normalized;
      if (!symbol) return null;

      const exchange = hasExplicitExchange
        ? normalized.slice(0, colonIndex)
        : ((symbol.includes('/') || /^[A-Z]{6}$/.test(symbol)) ? 'FX' : 'NASDAQ');

      return {
        symbol,
        name: symbol,
        exchange,
        tvSymbol: hasExplicitExchange ? normalized : undefined,
        isDirectSymbol: true,
        intro: `Quick take: direct TradingView lookup for ${symbol}.`,
        points: [
          'Live chart is pulled directly from TradingView symbol mapping.',
          'Use EXCHANGE:SYMBOL for precision when multiple listings exist.',
          'Fundamentals panel only includes symbols preloaded in this app.',
        ],
        valuation: 'No local valuation profile is attached to this ad-hoc symbol.',
        meta: hasExplicitExchange ? `Direct symbol mode: ${normalized}` : 'Direct symbol mode',
      };
    };

    const renderStock = () => {
      const stock = getActiveStock();
      if (!stock) return;
      setNoResultsMode(false);
      stockTitle.style.setProperty('--drag-x', '0px');
      stockTitle.style.setProperty('--drag-y', '0px');
      stockTitle.textContent = stock.symbol;
      scheduleTitleFit();
      renderRandomPixelPortrait();
      renderRandomAnalystBio();
      if (stockSearch && !isPanelSearch) stockSearch.value = stock.symbol;
      if (updateIntro) {
        const prefix = 'Quick take:';
        if (stock.intro.startsWith(prefix)) {
          const remainder = stock.intro.slice(prefix.length).trim();
          updateIntro.innerHTML = `<span class="quick-take-label">${prefix}</span> ${remainder}`;
        } else {
          updateIntro.textContent = stock.intro;
        }
      }
      if (point1) point1.textContent = stock.points[0];
      if (point2) point2.textContent = stock.points[1];
      if (point3) point3.textContent = stock.points[2];
      if (valuationText) valuationText.textContent = stock.valuation;
      if (updateMeta) updateMeta.textContent = stock.meta;
      if (widgetHeader) widgetHeader.textContent = stock.symbol;
      if (fundamentalsHeader) fundamentalsHeader.textContent = `${stock.symbol} • FUNDAMENTALS`;
      renderTradingViewWidget(stock);
      renderFundamentalsPanel(stock);
    };

    const confirmSearch = (state = 'success') => {
      if (searchFrame) searchFrame.classList.add('confirmed');
      if (searchContainer) {
        searchContainer.classList.remove('search-confirm-success', 'search-confirm-fail');
        // Force reflow so repeated Enter presses replay the short pulse.
        void searchContainer.offsetWidth;
        searchContainer.classList.add(state === 'success' ? 'search-confirm-success' : 'search-confirm-fail');
      }
      if (confirmSearchTimer) clearTimeout(confirmSearchTimer);
      confirmSearchTimer = setTimeout(() => {
        if (searchFrame) searchFrame.classList.remove('confirmed');
        if (searchContainer) searchContainer.classList.remove('search-confirm-success', 'search-confirm-fail');
      }, 120);
    };

    const runSearch = (rawQuery) => {
      const rawInput = String(rawQuery ?? (stockSearch ? stockSearch.value : '')).trim();
      if (!rawInput) return false;
      const query = rawInput.toLowerCase();
      const normalizeSymbol = (value) => String(value).toLowerCase().replace(/[^a-z0-9]/g, '');
      const normalizedQuery = normalizeSymbol(query);
      const queryAliasSymbolMap = {
        kur: 'USD/TRY',
        m2: 'M2',
      };

      if (normalizedQuery === 'cash') {
        activeStockOverride = null;
        renderNoResultsScreen();
        return false;
      }

      let foundIndex = stocks.findIndex((stock) => {
        return (
          stock.symbol.toLowerCase() === query ||
          normalizeSymbol(stock.symbol) === normalizedQuery ||
          stock.name.toLowerCase().includes(query)
        );
      });

      if (foundIndex === -1) {
        const aliasSymbol = queryAliasSymbolMap[query] || queryAliasSymbolMap[normalizedQuery];
        if (aliasSymbol) {
          foundIndex = stocks.findIndex(
            (stock) => String(stock.symbol || '').toUpperCase() === aliasSymbol.toUpperCase(),
          );
        }
      }

      if (foundIndex === -1) {
        const directStock = buildDirectSymbolStock(rawInput);
        if (!directStock) return false;
        resetChartDefaultView();
        activeStockOverride = directStock;
        renderStock();
        return true;
      }

      resetChartDefaultView();
      activeStockOverride = null;
      stockIndex = foundIndex;
      renderStock();
      return true;
    };

    const goNextStock = () => {
      activeStockOverride = null;
      stockIndex = (stockIndex + 1) % stocks.length;
      renderStock();
    };
    const goPrevStock = () => {
      activeStockOverride = null;
      stockIndex = (stockIndex - 1 + stocks.length) % stocks.length;
      renderStock();
    };
    const portfolioRows = Array.from(
      document.querySelectorAll('.portfolio-table[aria-label="Current portfolio gains table"] tbody tr, .portfolio-table[aria-label="Current buildings gains table"] tbody tr, .portfolio-table[aria-label="MIDAS portfolio table"] tbody tr'),
    );
    portfolioRows.forEach((row) => {
      row.addEventListener('click', () => {
        const symbolCell = row.querySelector('td');
        const targetSymbol = symbolCell ? symbolCell.textContent.trim().toUpperCase() : '';
        if (!targetSymbol) return;
        const targetIndex = stocks.findIndex((stock) => stock.symbol === targetSymbol);
        if (targetIndex === -1) return;
        activeStockOverride = null;
        stockIndex = targetIndex;
        renderStock();
      });
    });

    titleSwitch.addEventListener('click', (event) => {
      const rect = titleSwitch.getBoundingClientRect();
      if (!rect.width) return;
      const relativeX = event.clientX - rect.left;
      if (relativeX < rect.width * 0.5) {
        goPrevStock();
        return;
      }
      goNextStock();
    });

    if (stockSearch) {
      if (isPanelSearch) {
        if (searchContainer) {
          searchContainer.addEventListener('mousedown', (event) => {
            if (event.target === stockSearch) return;
            event.preventDefault();
            stockSearch.focus();
          });
        }
        stockSearch.addEventListener('focus', () => {
          stockSearch.placeholder = '';
        });
        stockSearch.addEventListener('blur', () => {
          if (!stockSearch.value.trim()) {
            stockSearch.placeholder = defaultSearchPlaceholder;
          }
        });

        const isEditableTarget = (target) => {
          if (!(target instanceof Element)) return false;
          if (target.isContentEditable) return true;
          const tagName = target.tagName;
          if (tagName === 'TEXTAREA') return true;
          if (tagName !== 'INPUT') return false;
          const input = target;
          if (input.readOnly || input.disabled) return false;
          const type = String(input.getAttribute('type') || 'text').toLowerCase();
          return !['button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio', 'range', 'reset', 'submit'].includes(type);
        };

        const applyGlobalSearchKey = (key) => {
          const selectionStart = stockSearch.selectionStart ?? stockSearch.value.length;
          const selectionEnd = stockSearch.selectionEnd ?? stockSearch.value.length;
          let didMutate = false;

          if (key === 'Backspace') {
            if (selectionStart !== selectionEnd) {
              stockSearch.setRangeText('', selectionStart, selectionEnd, 'end');
              didMutate = true;
            } else if (selectionStart > 0) {
              stockSearch.setRangeText('', selectionStart - 1, selectionEnd, 'end');
              didMutate = true;
            }
          } else if (key === 'Delete') {
            if (selectionStart !== selectionEnd) {
              stockSearch.setRangeText('', selectionStart, selectionEnd, 'end');
              didMutate = true;
            } else if (selectionEnd < stockSearch.value.length) {
              stockSearch.setRangeText('', selectionStart, selectionEnd + 1, 'end');
              didMutate = true;
            }
          } else if (key.length === 1) {
            stockSearch.setRangeText(key, selectionStart, selectionEnd, 'end');
            didMutate = true;
          }

          if (!didMutate) return;
          stockSearch.dispatchEvent(new Event('input', { bubbles: true }));
        };

        window.addEventListener('keydown', (event) => {
          if (event.defaultPrevented) return;
          if (event.metaKey || event.ctrlKey || event.altKey) return;
          const key = event.key;
          if (!(key.length === 1 || key === 'Backspace' || key === 'Delete')) return;
          if (event.target === stockSearch) return;

          const activeElement = document.activeElement;
          if (isEditableTarget(event.target) || isEditableTarget(activeElement)) return;

          event.preventDefault();
          stockSearch.focus({ preventScroll: true });
          applyGlobalSearchKey(key);
        });
      }

      stockSearch.addEventListener('keydown', (event) => {
        const key = event.key.toLowerCase();
        if ((event.metaKey || event.ctrlKey) && key === 'a') {
          event.preventDefault();
          stockSearch.value = '';
          return;
        }

        if (event.key !== 'Enter') return;
        event.preventDefault();
        const success = runSearch();
        confirmSearch(success ? 'success' : 'fail');
      });
    }

    let widgetResizeTimer = null;
    const scheduleWidgetFit = () => {
      if (widgetResizeTimer) clearTimeout(widgetResizeTimer);
      widgetResizeTimer = setTimeout(() => {
        const activeStock = getActiveStock();
        if (!activeStock) return;
        renderTradingViewWidget(activeStock);
      }, 120);
    };

    if (fundamentalsCloseButton) {
      fundamentalsCloseButton.addEventListener('click', () => {
        if (!splitBox || splitBox.classList.contains('split-box-chart-only')) return;
        setFundamentalsCollapsed(true);
        scheduleWidgetFit();
      });
    }

    window.addEventListener('resize', () => {
      scheduleTitleFit();
      scheduleWidgetFit();
    });
    renderStock();
  }

  function resize(){
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(rect.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function drawGrid(w, h){
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = 'rgba(242,242,242,0.12)';
    ctx.lineWidth = 1;
    for (let i = 1; i < 9; i++){
      const y = (h / 9) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
    for (let i = 1; i < 18; i++){
      const x = (w / 18) * i;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
  }

  function gen(n){
    let seed = 1337;
    const rnd = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
    let p = 165;
    const data = [];
    for (let i = 0; i < n; i++){
      const drift = (rnd() - 0.5) * 2.4;
      const o = p;
      const c = p + drift;
      const hi = Math.max(o, c) + rnd() * 2.2;
      const lo = Math.min(o, c) - rnd() * 2.2;
      p = c;
      data.push({ o, c, hi, lo, vol: Math.floor(40 + rnd() * 170) });
    }
    return data;
  }

  function drawCandles(w, h){
    const pad = 14;
    const data = gen(46);
    const min = Math.min(...data.map(d => d.lo));
    const max = Math.max(...data.map(d => d.hi));
    const scaleY = (v) => pad + (h - 2 * pad) * (1 - (v - min) / (max - min));
    const cw = (w - 2 * pad) / data.length;
    const volH = 58;
    const volTop = h - pad - volH;

    ctx.strokeStyle = 'rgba(255,176,0,0.24)';
    ctx.beginPath();
    ctx.moveTo(pad, volTop);
    ctx.lineTo(w - pad, volTop);
    ctx.stroke();

    data.forEach((d, i) => {
      const x = pad + i * cw + cw * 0.14;
      const bodyW = cw * 0.68;
      const yO = scaleY(d.o);
      const yC = scaleY(d.c);
      const yH = scaleY(d.hi);
      const yL = scaleY(d.lo);
      const up = d.c >= d.o;

      ctx.strokeStyle = up ? 'rgba(0,255,102,0.95)' : 'rgba(255,77,77,0.95)';
      ctx.fillStyle = up ? 'rgba(0,255,102,0.35)' : 'rgba(255,77,77,0.35)';

      ctx.beginPath();
      ctx.moveTo(x + bodyW / 2, yH);
      ctx.lineTo(x + bodyW / 2, yL);
      ctx.stroke();

      const top = Math.min(yO, yC);
      const bh = Math.max(2, Math.abs(yC - yO));
      ctx.fillRect(x, top, bodyW, bh);
      ctx.strokeRect(x, top, bodyW, bh);

      const vh = Math.max(2, (d.vol / 210) * volH);
      ctx.fillStyle = up ? 'rgba(0,255,102,0.28)' : 'rgba(255,176,0,0.28)';
      ctx.fillRect(x, h - pad - vh, bodyW, vh);
    });

    const ma = (win, color) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      data.forEach((d, i) => {
        const s = Math.max(0, i - win + 1);
        const slice = data.slice(s, i + 1);
        const avg = slice.reduce((a, x) => a + x.c, 0) / slice.length;
        const x = pad + i * cw + cw * 0.5;
        const y = scaleY(avg);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    };

    ma(8, 'rgba(255,176,0,0.92)');
    ma(21, 'rgba(242,242,242,0.78)');
  }

  function draw(){
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    drawGrid(w, h);
    drawCandles(w, h);
  }

  if (canvas && ctx) {
    window.addEventListener('resize', resize);
    resize();
  }
 const stage = document.getElementById('figures-stage');
  if (stage) {
    const cards = Array.from(stage.querySelectorAll('.figure-card'));
    const figures = cards.map((card) => {
      const canvas = card.querySelector('.figure-canvas');
      const ctx2 = canvas ? canvas.getContext('2d') : null;
      return { card, canvas, ctx2, particles: [] };
    }).filter((entry) => entry.canvas && entry.ctx2);

    const specs = {
      ghost: {
        body: '#7ef3ff',
        glow: 'rgba(126,243,255,0.45)',
        accent: '#d8faff',
        core: '#c2ffff',
        eye: '#e5feff',
      },
      isaac: {
        body: '#f1c8bd',
        glow: 'rgba(241,200,189,0.35)',
        accent: '#ffe1d8',
        core: '#f7d9d2',
        eye: '#111111',
      },
      azazel: {
        body: '#161616',
        glow: 'rgba(255,35,35,0.45)',
        accent: '#5a5a5a',
        core: '#2f2f2f',
        eye: '#ff3636',
      },
    };

    const fitFigureCanvas = (entry) => {
      if (!entry.canvas || !entry.ctx2) return;
      const rect = entry.canvas.getBoundingClientRect();
      const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      entry.canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      entry.canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      entry.ctx2.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const spawnParticles = (entry, kind, count) => {
      for (let i = 0; i < count; i += 1) {
        entry.particles.push({
          x: Math.random(),
          y: Math.random(),
          vx: (Math.random() - 0.5) * 0.0014,
          vy: -0.0008 - Math.random() * 0.0012,
          r: 0.5 + Math.random() * 2.2,
          life: 0.3 + Math.random() * 0.7,
          kind,
        });
      }
    };

    figures.forEach((entry) => {
      const kind = entry.card.dataset.figure || 'isaac';
      fitFigureCanvas(entry);
      spawnParticles(entry, kind, kind === 'azazel' ? 32 : 48);
    });

    const drawFigure = (entry, t) => {
      const kind = entry.card.dataset.figure || 'isaac';
      const spec = specs[kind];
      const ctxF = entry.ctx2;
      const w = entry.canvas.clientWidth;
      const h = entry.canvas.clientHeight;
      if (!ctxF || !w || !h) return;

      const cx = w * 0.5;
      const baseY = h * 0.5;
      const bob = Math.sin(t * 0.002 + (kind === 'ghost' ? 0 : kind === 'isaac' ? 0.7 : 1.2)) * h * 0.015;
      const cy = baseY + bob;

      ctxF.clearRect(0, 0, w, h);

      const shadowGradient = ctxF.createRadialGradient(cx, h * 0.86, 0, cx, h * 0.86, w * 0.34);
      shadowGradient.addColorStop(0, 'rgba(0,0,0,0.48)');
      shadowGradient.addColorStop(1, 'rgba(0,0,0,0)');
      ctxF.fillStyle = shadowGradient;
      ctxF.beginPath();
      ctxF.ellipse(cx, h * 0.86, w * 0.28, h * 0.07, 0, 0, Math.PI * 2);
      ctxF.fill();

      ctxF.shadowBlur = Math.max(10, w * 0.06);
      ctxF.shadowColor = spec.glow;
      ctxF.fillStyle = spec.body;

      if (kind === 'ghost') {
        // Ghost body + tail ring
        ctxF.beginPath();
        ctxF.moveTo(cx - w * 0.2, cy - h * 0.13);
        ctxF.bezierCurveTo(cx - w * 0.26, cy + h * 0.03, cx - w * 0.22, cy + h * 0.22, cx, cy + h * 0.27);
        ctxF.bezierCurveTo(cx + w * 0.22, cy + h * 0.22, cx + w * 0.26, cy + h * 0.03, cx + w * 0.2, cy - h * 0.13);
        ctxF.bezierCurveTo(cx + w * 0.13, cy - h * 0.24, cx - w * 0.13, cy - h * 0.24, cx - w * 0.2, cy - h * 0.13);
        ctxF.fill();

        ctxF.strokeStyle = '#ffe24d';
        ctxF.lineWidth = Math.max(2, w * 0.012);
        ctxF.beginPath();
        ctxF.ellipse(cx, cy + h * 0.18, w * 0.21, h * 0.05, 0.2, 0, Math.PI * 2);
        ctxF.stroke();

        ctxF.fillStyle = spec.core;
        ctxF.beginPath();
        ctxF.arc(cx, cy - h * 0.06, w * 0.08, 0, Math.PI * 2);
        ctxF.fill();
        ctxF.fillStyle = '#f8feff';
        ctxF.fillRect(cx - w * 0.045, cy - h * 0.07, w * 0.024, h * 0.022);
        ctxF.fillRect(cx + w * 0.021, cy - h * 0.07, w * 0.024, h * 0.022);
      }

      if (kind === 'isaac') {
        // Body
        ctxF.beginPath();
        ctxF.roundRect(cx - w * 0.12, cy + h * 0.01, w * 0.24, h * 0.28, w * 0.08);
        ctxF.fill();
        // Head
        ctxF.fillStyle = spec.core;
        ctxF.beginPath();
        ctxF.arc(cx, cy - h * 0.09, w * 0.13, 0, Math.PI * 2);
        ctxF.fill();
        // Ears
        ctxF.fillStyle = '#f7d0c8';
        ctxF.beginPath();
        ctxF.arc(cx - w * 0.1, cy - h * 0.09, w * 0.036, 0, Math.PI * 2);
        ctxF.arc(cx + w * 0.1, cy - h * 0.09, w * 0.036, 0, Math.PI * 2);
        ctxF.fill();
        // Arms/legs
        ctxF.fillStyle = '#eebdb0';
        ctxF.fillRect(cx - w * 0.18, cy + h * 0.08, w * 0.07, h * 0.03);
        ctxF.fillRect(cx + w * 0.11, cy + h * 0.08, w * 0.07, h * 0.03);
        ctxF.fillRect(cx - w * 0.08, cy + h * 0.28, w * 0.06, h * 0.08);
        ctxF.fillRect(cx + w * 0.02, cy + h * 0.28, w * 0.06, h * 0.08);
        // Face
        ctxF.fillStyle = '#111';
        ctxF.beginPath();
        ctxF.arc(cx - w * 0.04, cy - h * 0.09, w * 0.016, 0, Math.PI * 2);
        ctxF.arc(cx + w * 0.04, cy - h * 0.09, w * 0.016, 0, Math.PI * 2);
        ctxF.fill();
        ctxF.strokeStyle = '#8ad7ff';
        ctxF.lineWidth = Math.max(1, w * 0.006);
        ctxF.beginPath();
        ctxF.moveTo(cx - w * 0.05, cy - h * 0.06);
        ctxF.lineTo(cx - w * 0.07, cy + h * 0.02);
        ctxF.moveTo(cx + w * 0.05, cy - h * 0.06);
        ctxF.lineTo(cx + w * 0.07, cy + h * 0.02);
        ctxF.stroke();
      }

      if (kind === 'azazel') {
        // Wings
        ctxF.fillStyle = '#1f1f1f';
        ctxF.beginPath();
        ctxF.moveTo(cx - w * 0.2, cy - h * 0.01);
        ctxF.lineTo(cx - w * 0.44, cy + h * 0.13);
        ctxF.lineTo(cx - w * 0.25, cy + h * 0.06);
        ctxF.closePath();
        ctxF.fill();
        ctxF.beginPath();
        ctxF.moveTo(cx + w * 0.2, cy - h * 0.01);
        ctxF.lineTo(cx + w * 0.44, cy + h * 0.13);
        ctxF.lineTo(cx + w * 0.25, cy + h * 0.06);
        ctxF.closePath();
        ctxF.fill();
        // Body
        ctxF.fillStyle = '#2a2a2a';
        ctxF.beginPath();
        ctxF.roundRect(cx - w * 0.12, cy + h * 0.02, w * 0.24, h * 0.27, w * 0.07);
        ctxF.fill();
        // Head
        ctxF.fillStyle = '#343434';
        ctxF.beginPath();
        ctxF.arc(cx, cy - h * 0.1, w * 0.12, 0, Math.PI * 2);
        ctxF.fill();
        // Horns
        ctxF.fillStyle = '#0d0d0d';
        ctxF.beginPath();
        ctxF.moveTo(cx - w * 0.08, cy - h * 0.17);
        ctxF.lineTo(cx - w * 0.16, cy - h * 0.29);
        ctxF.lineTo(cx - w * 0.02, cy - h * 0.2);
        ctxF.closePath();
        ctxF.fill();
        ctxF.beginPath();
        ctxF.moveTo(cx + w * 0.08, cy - h * 0.17);
        ctxF.lineTo(cx + w * 0.16, cy - h * 0.29);
        ctxF.lineTo(cx + w * 0.02, cy - h * 0.2);
        ctxF.closePath();
        ctxF.fill();
        // Eyes and mouth
        ctxF.fillStyle = '#ff3d3d';
        ctxF.beginPath();
        ctxF.arc(cx - w * 0.034, cy - h * 0.1, w * 0.016, 0, Math.PI * 2);
        ctxF.arc(cx + w * 0.034, cy - h * 0.1, w * 0.016, 0, Math.PI * 2);
        ctxF.fill();
        ctxF.strokeStyle = '#cc1f1f';
        ctxF.lineWidth = Math.max(1, w * 0.005);
        ctxF.beginPath();
        ctxF.moveTo(cx - w * 0.04, cy - h * 0.05);
        ctxF.lineTo(cx + w * 0.04, cy - h * 0.05);
        ctxF.stroke();
      }

      ctxF.shadowBlur = 0;

      entry.particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < -0.1 || p.x > 1.1 || p.y < -0.1) {
          p.x = Math.random();
          p.y = 1 + Math.random() * 0.2;
        }
        const px = p.x * w;
        const py = p.y * h;
        ctxF.globalAlpha = p.life;
        ctxF.fillStyle = kind === 'azazel' ? '#ff4a4a' : kind === 'ghost' ? '#dbffff' : '#ffffff';
        ctxF.beginPath();
        ctxF.arc(px, py, p.r, 0, Math.PI * 2);
        ctxF.fill();
      });
      ctxF.globalAlpha = 1;
    };

    const drag = { card: null, startX: 0, startY: 0, baseX: 0, baseY: 0 };
    const readPos = (card) => ({
      x: Number.parseFloat(card.dataset.x || '0') || 0,
      y: Number.parseFloat(card.dataset.y || '0') || 0,
    });
    const writePos = (card, x, y) => {
      card.dataset.x = String(x);
      card.dataset.y = String(y);
      card.style.transform = `translate(${x}px, ${y}px)`;
    };
    const clamp = (card, x, y) => {
      const baseLeft = card.offsetLeft;
      const baseTop = card.offsetTop;
      const maxLeft = window.innerWidth - card.offsetWidth;
      const maxTop = window.innerHeight - card.offsetHeight;
      const desiredLeft = baseLeft + x;
      const desiredTop = baseTop + y;
      const safeLeft = Math.max(0, Math.min(maxLeft, desiredLeft));
      const safeTop = Math.max(0, Math.min(maxTop, desiredTop));
      return { x: safeLeft - baseLeft, y: safeTop - baseTop };
    };

    cards.forEach((card, index) => {
      writePos(card, 0, 0);
      card.style.zIndex = String(20 + index);
      card.addEventListener('pointerdown', (event) => {
        if (event.button !== 0) return;
        drag.card = card;
        drag.startX = event.clientX;
        drag.startY = event.clientY;
        const pos = readPos(card);
        drag.baseX = pos.x;
        drag.baseY = pos.y;
        card.classList.add('dragging');
        card.setPointerCapture(event.pointerId);
        event.preventDefault();
      });
      card.addEventListener('pointermove', (event) => {
        if (drag.card !== card) return;
        const nextX = drag.baseX + (event.clientX - drag.startX);
        const nextY = drag.baseY + (event.clientY - drag.startY);
        const safe = clamp(card, nextX, nextY);
        writePos(card, safe.x, safe.y);
      });
      const stop = (event) => {
        if (drag.card !== card) return;
        card.classList.remove('dragging');
        if (card.hasPointerCapture(event.pointerId)) card.releasePointerCapture(event.pointerId);
        drag.card = null;
      };
      card.addEventListener('pointerup', stop);
      card.addEventListener('pointercancel', stop);
    });

    let figuresAnimationId = 0;
    const animateFigures = (time) => {
      if (document.hidden) {
        figuresAnimationId = 0;
        return;
      }
      figures.forEach((entry) => drawFigure(entry, time));
      figuresAnimationId = requestAnimationFrame(animateFigures);
    };

    figuresAnimationId = requestAnimationFrame(animateFigures);

    const handleFiguresVisibility = () => {
      if (document.hidden) {
        if (figuresAnimationId) {
          cancelAnimationFrame(figuresAnimationId);
          figuresAnimationId = 0;
        }
        return;
      }
      if (!figuresAnimationId) {
        figuresAnimationId = requestAnimationFrame(animateFigures);
      }
    };
    document.addEventListener('visibilitychange', handleFiguresVisibility);

    window.addEventListener('beforeunload', () => {
      if (figuresAnimationId) cancelAnimationFrame(figuresAnimationId);
      document.removeEventListener('visibilitychange', handleFiguresVisibility);
    });

    window.addEventListener('resize', () => {
      figures.forEach((entry) => fitFigureCanvas(entry));
    });
  }

  const newsDesk = document.getElementById('news-desk');
  const newsFeedBody = document.getElementById('news-feed-body');
  if (newsDesk && newsFeedBody) {
    const newsRankedBody = document.getElementById('news-ranked-body');
    const newsSourceLabel = document.getElementById('news-source-label');
    const newsCountLabel = document.getElementById('news-count-label');
    const newsUpdatedLabel = document.getElementById('news-updated-label');
    const newsModeLabel = document.getElementById('news-mode-label');
    const newsSelectedSourceCode = document.getElementById('news-selected-source-code');
    const newsSelectedTimeQuote = document.getElementById('news-selected-time-quote');
    const newsSelectedCategoryQuote = document.getElementById('news-selected-category-quote');
    const newsRefreshButton = document.getElementById('news-refresh-button');
    const newsStatusBanner = document.getElementById('news-status-banner');
    const newsStatusText = document.getElementById('news-status-text');
    const newsStatusHint = document.getElementById('news-status-hint');
    const newsFeedMeta = document.getElementById('news-feed-meta');
    const newsDetailImage = document.getElementById('news-detail-image');
    const newsDetailMediaCopy = document.getElementById('news-detail-media-copy');
    const newsDetailCategory = document.getElementById('news-detail-category');
    const newsDetailSource = document.getElementById('news-detail-source');
    const newsDetailHeadline = document.getElementById('news-detail-headline');
    const newsDetailMeta = document.getElementById('news-detail-meta');
    const newsDetailSummary = document.getElementById('news-detail-summary');
    const newsOpenStory = document.getElementById('news-open-story');
    const newsDetailLink = document.getElementById('news-detail-link');

    const emergencyNewsSeed = [
      {
        id: 'seed-1',
        title: 'Yahoo wire standby: local sample feed engaged until live proxy responds',
        link: '',
        published_at: '2026-04-22T18:05:00Z',
        source: 'TERMINAL',
        summary: 'The NEWS desk is live, but the browser needs the included local proxy to pull fresh Yahoo Finance headlines without CORS issues.',
        category: 'SYSTEM / STATUS',
        image_url: '',
      },
      {
        id: 'seed-2',
        title: 'Bloomberg-style desk keeps the wire dense, fast, and amber-first',
        link: '',
        published_at: '2026-04-22T17:48:00Z',
        source: 'YAHOO',
        summary: 'Rows on the left behave like a terminal tape, while the selected story expands on the right with source, time, route, and summary.',
        category: 'DESK / DESIGN',
        image_url: '',
      },
      {
        id: 'seed-3',
        title: 'Run python3 server.py to route Yahoo Finance RSS into /api/yahoo-finance-news',
        link: '',
        published_at: '2026-04-22T17:22:00Z',
        source: 'SETUP',
        summary: 'Once the local proxy is serving the page, the NEWS desk auto-refreshes the Yahoo Finance wire and swaps out the fallback tape.',
        category: 'SETUP / LIVE',
        image_url: '',
      },
      {
        id: 'seed-4',
        title: 'Live stories are selectable, refreshable, and readable without leaving the terminal',
        link: '',
        published_at: '2026-04-22T16:54:00Z',
        source: 'NEWS DESK',
        summary: 'The feed intentionally stays sharp and rectangular, using the site’s existing amber, green, and black palette instead of generic card UI.',
        category: 'FEATURE / NEWS',
        image_url: '',
      },
    ];

    const newsState = {
      items: [],
      selectedId: '',
      lastUpdatedAt: null,
      sourceLabel: 'YAHOO RSS',
      mode: 'CONNECTING',
      statusTone: 'is-loading',
      refreshTimerId: 0,
      ageTimerId: 0,
      isLoading: false,
    };

    const htmlEntityDecoder = document.createElement('textarea');
    const decodeEntities = (value) => {
      htmlEntityDecoder.innerHTML = String(value || '');
      return htmlEntityDecoder.value;
    };
    const stripMarkup = (value) => decodeEntities(String(value || '').replace(/<[^>]+>/g, ' '))
      .replace(/\s+/g, ' ')
      .trim();
    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
    const newsMonths = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

    const parseNewsDate = (value) => {
      if (!value) return null;
      const parsed = new Date(value);
      return Number.isFinite(parsed.getTime()) ? parsed : null;
    };

    const formatNewsAge = (value) => {
      const date = value instanceof Date ? value : parseNewsDate(value);
      if (!date) return '--';
      const deltaMs = Math.max(0, Date.now() - date.getTime());
      const deltaMinutes = Math.floor(deltaMs / 60000);
      if (deltaMinutes <= 0) return 'NOW';
      if (deltaMinutes < 60) return `-${deltaMinutes}M`;
      const deltaHours = Math.floor(deltaMinutes / 60);
      if (deltaHours < 24) return `-${deltaHours}H`;
      const deltaDays = Math.floor(deltaHours / 24);
      return `-${deltaDays}D`;
    };

    const formatNewsStamp = (value) => {
      const date = value instanceof Date ? value : parseNewsDate(value);
      if (!date) return 'TIME UNKNOWN';
      const month = newsMonths[date.getUTCMonth()];
      const day = String(date.getUTCDate()).padStart(2, '0');
      const year = date.getUTCFullYear();
      const hours = String(date.getUTCHours()).padStart(2, '0');
      const minutes = String(date.getUTCMinutes()).padStart(2, '0');
      return `${day} ${month} ${year} ${hours}:${minutes} UTC`;
    };

    const formatCompactNewsStamp = (value) => {
      const date = value instanceof Date ? value : parseNewsDate(value);
      if (!date) return '--';
      const month = newsMonths[date.getUTCMonth()];
      const day = String(date.getUTCDate()).padStart(2, '0');
      const hours = String(date.getUTCHours()).padStart(2, '0');
      const minutes = String(date.getUTCMinutes()).padStart(2, '0');
      return `${day} ${month} ${hours}:${minutes}Z`;
    };

    const formatNewsWireTime = (value) => {
      const date = value instanceof Date ? value : parseNewsDate(value);
      if (!date) return '--';
      const now = new Date();
      const isSameUtcDay = date.getUTCFullYear() === now.getUTCFullYear()
        && date.getUTCMonth() === now.getUTCMonth()
        && date.getUTCDate() === now.getUTCDate();
      if (isSameUtcDay) {
        const hours = String(date.getUTCHours()).padStart(2, '0');
        const minutes = String(date.getUTCMinutes()).padStart(2, '0');
        return `${hours}:${minutes}`;
      }
      const month = String(date.getUTCMonth() + 1).padStart(2, '0');
      const day = String(date.getUTCDate()).padStart(2, '0');
      return `${month}/${day}`;
    };

    const formatNewsSourceCode = (value) => {
      const raw = String(value || '').trim();
      if (!raw) return 'NEWS';
      const wordTokens = raw
        .toUpperCase()
        .split(/[^A-Z0-9]+/g)
        .filter(Boolean);
      if (wordTokens.length > 1) return wordTokens.map((token) => token[0]).join('').slice(0, 4);
      return raw.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 4) || 'NEWS';
    };

    const formatNewsCategoryQuote = (value) => {
      const compact = String(value || 'LIVE')
        .toUpperCase()
        .replace(/\s*\/\s*/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      if (!compact) return 'LIVE';
      return compact.slice(0, 18);
    };

    const deriveSourceLabel = (link) => {
      if (!link) return 'YAHOO';
      try {
        const host = new URL(link, window.location.href).hostname.replace(/^www\./, '');
        const base = host.split('.')[0] || 'YAHOO';
        return base.toUpperCase();
      } catch (_) {
        return 'YAHOO';
      }
    };

    const deriveCategoryFromLink = (link) => {
      if (!link) return 'MARKETS';
      try {
        const segments = new URL(link, window.location.href).pathname
          .split('/')
          .filter(Boolean)
          .map((part) => part.replace(/-/g, ' ').toUpperCase());
        if (!segments.length) return 'MARKETS';
        const categoryParts = [];
        for (const part of segments) {
          if (part === 'ARTICLES') break;
          categoryParts.push(part);
          if (categoryParts.length === 2) break;
        }
        return categoryParts.length ? categoryParts.join(' / ') : 'MARKETS';
      } catch (_) {
        return 'MARKETS';
      }
    };

    const normalizeNewsItem = (item, index) => {
      const title = stripMarkup(item && item.title) || `WIRE ITEM ${index + 1}`;
      const link = String((item && item.link) || '').trim();
      const publishedAt = String(
        (item && (item.published_at || item.publishedAt || item.pubDate)) || '',
      ).trim();
      const summary = stripMarkup(item && (item.summary || item.description))
        || 'Yahoo Finance did not include a summary snippet for this story. Open the article for full copy.';
      const source = 'YAHOO';
      const category = stripMarkup(item && item.category) || deriveCategoryFromLink(link);
      const imageUrl = String((item && (item.image_url || item.thumbnail || item.image)) || '').trim();
      const publishedAtDate = parseNewsDate(publishedAt);
      return {
        id: stripMarkup(item && (item.id || item.guid)) || link || `news-${index}`,
        title,
        link,
        publishedAt,
        publishedAtDate,
        summary,
        source,
        category,
        imageUrl,
      };
    };

    const setNewsStatus = (tone, text, hint) => {
      newsState.statusTone = tone;
      if (newsStatusBanner) newsStatusBanner.className = `news-status-banner ${tone}`;
      if (newsStatusText) newsStatusText.textContent = text;
      if (newsStatusHint) newsStatusHint.textContent = hint;
    };

    const setOpenStoryState = (link) => {
      if (!newsOpenStory) return;
      if (link) {
        newsOpenStory.href = link;
        newsOpenStory.classList.remove('is-disabled');
        newsOpenStory.setAttribute('aria-disabled', 'false');
      } else {
        newsOpenStory.href = '#';
        newsOpenStory.classList.add('is-disabled');
        newsOpenStory.setAttribute('aria-disabled', 'true');
      }
    };

    const getSelectedNewsItem = () => newsState.items.find((item) => item.id === newsState.selectedId)
      || newsState.items[0]
      || null;

    const createNewsFeedRow = (item, index, variant = 'time') => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'news-feed-row';
      row.style.setProperty('--news-row-order', String(index));
      if (variant === 'ranked') row.classList.add('is-ranked');
      row.setAttribute('aria-pressed', 'false');
      row.title = item.link
        ? `${formatNewsStamp(item.publishedAtDate)} | Click to open story`
        : `${formatNewsStamp(item.publishedAtDate)} | ${formatNewsAge(item.publishedAtDate)}`;
      row.addEventListener('click', () => {
        row.blur();
        if (item.link) window.open(item.link, '_blank', 'noopener,noreferrer');
      });

      const rank = document.createElement('span');
      rank.className = 'news-feed-rank';
      rank.textContent = `${index + 1})`;

      const main = document.createElement('span');
      main.className = 'news-feed-main';

      const headline = document.createElement('span');
      headline.className = 'news-feed-headline';
      headline.textContent = item.title;

      const side = document.createElement('span');
      side.className = 'news-feed-side';

      const time = document.createElement('span');
      time.className = 'news-feed-time';
      time.textContent = formatNewsWireTime(item.publishedAtDate);

      main.appendChild(headline);
      side.append(time);
      row.append(rank, main, side);
      return row;
    };

    const renderNewsRanked = () => {
      if (!newsRankedBody) return;
      newsRankedBody.replaceChildren();
      if (!newsState.items.length) {
        const empty = document.createElement('div');
        empty.className = 'news-feed-empty';
        empty.textContent = 'NO RANKED STORIES AVAILABLE.';
        newsRankedBody.appendChild(empty);
        return;
      }

      const fragment = document.createDocumentFragment();
      newsState.items.slice(0, 3).forEach((item, index) => {
        fragment.appendChild(createNewsFeedRow(item, index, 'ranked'));
      });
      newsRankedBody.appendChild(fragment);
    };

    const renderNewsFeed = () => {
      newsFeedBody.replaceChildren();
      if (!newsState.items.length) {
        const empty = document.createElement('div');
        empty.className = 'news-feed-empty';
        empty.textContent = 'NO STORIES AVAILABLE.';
        newsFeedBody.appendChild(empty);
        return;
      }

      const fragment = document.createDocumentFragment();
      newsState.items.forEach((item, index) => {
        fragment.appendChild(createNewsFeedRow(item, index, 'time'));
      });
      newsFeedBody.appendChild(fragment);
    };

    const renderNewsDetail = () => {
      const item = getSelectedNewsItem();
      if (!item) {
        if (newsSelectedSourceCode) newsSelectedSourceCode.textContent = 'NEWS';
        if (newsSelectedTimeQuote) newsSelectedTimeQuote.textContent = '--';
        if (newsSelectedCategoryQuote) newsSelectedCategoryQuote.textContent = 'LIVE';
        if (newsDetailCategory) newsDetailCategory.textContent = 'NO DATA';
        if (newsDetailSource) newsDetailSource.textContent = 'YAHOO FINANCE';
        if (newsDetailHeadline) newsDetailHeadline.textContent = 'Waiting for live stories...';
        if (newsDetailMeta) newsDetailMeta.textContent = 'No story selected.';
        if (newsDetailSummary) {
          newsDetailSummary.textContent = 'The news desk will populate once the first valid payload arrives.';
        }
        if (newsDetailLink) newsDetailLink.textContent = 'LINK WILL APPEAR HERE';
        if (newsDetailImage) {
          newsDetailImage.hidden = true;
          newsDetailImage.removeAttribute('src');
        }
        if (newsDetailMediaCopy) {
          newsDetailMediaCopy.textContent = 'YAHOO / NEWS';
          newsDetailMediaCopy.style.opacity = '1';
        }
        setOpenStoryState('');
        return;
      }

      if (newsSelectedSourceCode) newsSelectedSourceCode.textContent = formatNewsSourceCode(item.source);
      if (newsSelectedTimeQuote) newsSelectedTimeQuote.textContent = formatNewsWireTime(item.publishedAtDate);
      if (newsSelectedCategoryQuote) newsSelectedCategoryQuote.textContent = formatNewsCategoryQuote(item.category);
      if (newsDetailCategory) newsDetailCategory.textContent = item.category;
      if (newsDetailSource) newsDetailSource.textContent = item.source.toUpperCase();
      if (newsDetailHeadline) newsDetailHeadline.textContent = item.title;
      if (newsDetailMeta) {
        newsDetailMeta.textContent = `${item.source.toUpperCase()} | ${formatNewsStamp(item.publishedAtDate)} | ${item.category}`;
      }
      if (newsDetailSummary) newsDetailSummary.textContent = item.summary;
      if (newsDetailLink) newsDetailLink.textContent = item.link || 'STORY LINK UNAVAILABLE';

      if (newsDetailImage) {
        if (item.imageUrl) {
          newsDetailImage.hidden = false;
          newsDetailImage.src = item.imageUrl;
          newsDetailImage.alt = `${item.title} article image`;
          if (newsDetailMediaCopy) newsDetailMediaCopy.style.opacity = '0';
        } else {
          newsDetailImage.hidden = true;
          newsDetailImage.removeAttribute('src');
          if (newsDetailMediaCopy) {
            newsDetailMediaCopy.textContent = item.category;
            newsDetailMediaCopy.style.opacity = '1';
          }
        }
      }

      setOpenStoryState(item.link);
    };

    const renderNewsMeta = () => {
      if (newsSourceLabel) {
        const deskSourceLabel = String(newsState.sourceLabel || 'YAHOO')
          .toUpperCase()
          .split(/\s+/)[0]
          .slice(0, 10) || 'YAHOO';
        newsSourceLabel.textContent = deskSourceLabel;
      }
      if (newsCountLabel) newsCountLabel.textContent = `${newsState.items.length.toLocaleString('en-US')}`;
      if (newsUpdatedLabel) {
        newsUpdatedLabel.textContent = newsState.lastUpdatedAt
          ? formatCompactNewsStamp(newsState.lastUpdatedAt)
          : '--';
      }
      if (newsModeLabel) newsModeLabel.textContent = newsState.mode;
      if (newsFeedMeta) {
        const updatedLabel = newsState.lastUpdatedAt
          ? formatCompactNewsStamp(newsState.lastUpdatedAt)
          : '--';
        newsFeedMeta.textContent = `${newsState.items.length} STORIES | ${updatedLabel} | ${newsState.mode}`;
      }
    };

    const applyNewsPayload = (items, meta) => {
      const normalizedItems = (Array.isArray(items) ? items : [])
        .map((item, index) => normalizeNewsItem(item, index))
        .filter((item) => item.title)
        .slice(0, 28);

      newsState.items = normalizedItems;
      newsState.lastUpdatedAt = parseNewsDate(meta && meta.fetchedAt) || new Date();
      newsState.sourceLabel = String((meta && meta.sourceLabel) || 'YAHOO RSS').toUpperCase();
      newsState.mode = String((meta && meta.mode) || 'LIVE').toUpperCase();
      if (!newsState.items.some((item) => item.id === newsState.selectedId)) {
        newsState.selectedId = newsState.items[0] ? newsState.items[0].id : '';
      }

      setNewsStatus(
        String((meta && meta.tone) || 'is-live'),
        String((meta && meta.statusText) || 'LIVE YAHOO FEED ONLINE'),
        String((meta && meta.statusHint) || 'Feed loaded.'),
      );
      renderNewsMeta();
      renderNewsRanked();
      renderNewsFeed();
      renderNewsDetail();
    };

    const fetchJson = async (url) => {
      const response = await fetch(url, { cache: 'no-store' });
      if (!response.ok) throw new Error(`Fetch failed: ${response.status}`);
      return response.json();
    };

    const requestLiveNews = async () => {
      const payload = await fetchJson('./api/yahoo-finance-news?limit=28');
      if (!payload || !Array.isArray(payload.items) || !payload.items.length) {
        throw new Error('Live news payload was empty.');
      }
      return payload;
    };

    const requestFallbackNews = async () => {
      try {
        const payload = await fetchJson('./sample-stock-news.json');
        if (Array.isArray(payload) && payload.length) return payload;
      } catch (_) {}
      return emergencyNewsSeed;
    };

    const loadNewsDesk = async (backgroundRefresh = false) => {
      if (newsState.isLoading) return;
      newsState.isLoading = true;
      if (newsRefreshButton) {
        newsRefreshButton.disabled = true;
        newsRefreshButton.textContent = backgroundRefresh ? 'AUTO REFRESH...' : 'REFRESHING...';
      }
      if (!backgroundRefresh) {
        setNewsStatus(
          'is-loading',
          'CONNECTING TO YAHOO FINANCE RSS...',
          'Pulling live wire through the local proxy.',
        );
      }

      try {
        const payload = await requestLiveNews();
        applyNewsPayload(payload.items, {
          sourceLabel: 'YAHOO RSS',
          mode: 'LIVE',
          fetchedAt: payload.fetched_at,
          tone: 'is-live',
          statusText: 'LIVE YAHOO FINANCE RSS ONLINE',
          statusHint: `Auto-refresh target: ${clamp(Number(payload.ttl_minutes) || 5, 1, 15)} minutes. Proxy endpoint is serving current Yahoo headlines.`,
        });
      } catch (liveError) {
        console.warn('Live Yahoo Finance feed unavailable. Falling back to local sample tape.', liveError);
        const fallbackItems = await requestFallbackNews();
        applyNewsPayload(fallbackItems, {
          sourceLabel: 'YAHOO RSS',
          mode: 'CACHE',
          fetchedAt: new Date().toISOString(),
          tone: 'is-fallback',
          statusText: 'LIVE YAHOO FEED UNAVAILABLE',
          statusHint: 'Showing local sample tape. Run `python3 server.py` on port 3000 for live Yahoo Finance RSS.',
        });
      } finally {
        newsState.isLoading = false;
        if (newsRefreshButton) {
          newsRefreshButton.disabled = false;
          newsRefreshButton.textContent = 'REFRESH WIRE';
        }
      }
    };

    if (newsRefreshButton) {
      newsRefreshButton.addEventListener('click', () => {
        loadNewsDesk(false).catch((error) => {
          console.warn('Manual news refresh failed.', error);
        });
      });
    }

    newsState.items = emergencyNewsSeed.map((item, index) => normalizeNewsItem(item, index));
    newsState.selectedId = newsState.items[0] ? newsState.items[0].id : '';
    renderNewsMeta();
    renderNewsRanked();
    renderNewsFeed();
    renderNewsDetail();
    loadNewsDesk(false).catch((error) => {
      console.warn('Initial news desk load failed.', error);
    });

    newsState.refreshTimerId = window.setInterval(() => {
      loadNewsDesk(true).catch((error) => {
        console.warn('Background news refresh failed.', error);
      });
    }, 5 * 60 * 1000);

    newsState.ageTimerId = window.setInterval(() => {
      renderNewsFeed();
      renderNewsDetail();
      renderNewsMeta();
    }, 60 * 1000);

    window.addEventListener('beforeunload', () => {
      if (newsState.refreshTimerId) window.clearInterval(newsState.refreshTimerId);
      if (newsState.ageTimerId) window.clearInterval(newsState.ageTimerId);
    });
  }

  // MEMOS widget test checklist:
  // - short memo = no animation
  // - long memo = auto-scroll loops
  // - hover pauses
  // - reduced motion disables animation and enables manual scroll
  // - pixel art shows and stays within bounds
  const memoWidget = document.getElementById('memo-widget');
  if (memoWidget) {
    try {
    const memoPrevBtn = document.getElementById('memo-prev');
    const memoNextBtn = document.getElementById('memo-next');
    const memoPortrait = document.getElementById('memo-portrait');
    const memoPortraitImage = document.getElementById('memo-portrait-image');
    const memoFilename = document.getElementById('memo-filename');
    const memoTitle = document.getElementById('memo-title');
    const memoStatus = document.getElementById('memo-status');
    const memoViewport = document.getElementById('memo-scroll-viewport');
    const memoTrack = document.getElementById('memo-scroll-track');
    const memoBody = document.getElementById('memo-body');
    const memoBodyClone = document.getElementById('memo-body-clone');
    const memoGap = document.getElementById('memo-scroll-gap');
    const requiredNodes = [
      memoPortrait,
      memoPortraitImage,
      memoFilename,
      memoTitle,
      memoStatus,
      memoViewport,
      memoTrack,
      memoBody,
      memoBodyClone,
      memoGap,
    ];
    if (requiredNodes.some((node) => !node)) return;

    const memos = [
      {
        id: 'buffett-2026',
        title: 'Concentrate When Odds Are Obvious',
        filename: 'BUFFETT_1977_LETTER.TXT',
        authorKey: 'buffett',
        bodyText: [
          'Discipline compounds like capital. You do not need constant activity; you need selective action.',
          'When probability and price diverge sharply, size matters. When they do not, patience matters more than brilliance.',
        ],
      },
      {
        id: 'marks-2026',
        title: 'Second-Level Thinking Under Crowd Pressure',
        filename: 'MARKS_SECOND_LEVEL_MEMO.TXT',
        authorKey: 'marks',
        bodyText: [
          'Markets price consensus quickly and risk slowly. The edge is not optimism or pessimism, it is calibration.',
          'Ask what is already discounted, what can break the narrative, and whether survival is guaranteed if timing is wrong.',
        ],
      },
      {
        id: 'nomad-2026',
        title: 'Cross-Asset Liquidity Reflex',
        filename: 'NOMAD_PARTNERSHIP_NOTE.TXT',
        authorKey: 'nomad',
        bodyText: [
          'Liquidity is path-dependent. Price does not move because value changes first; value is often re-labeled after financing conditions force repositioning.',
          'Build books that can absorb volatility without forced liquidation.',
        ],
      },
    ].filter((memo) => isCharacterVisible(memo.authorKey));

    const memoImageCacheKey = String(Date.now());
    const memoImageWithVersion = (path) => `${path}?v=${memoImageCacheKey}`;
    const memoPortraitByAuthor = {
      buffett: memoImageWithVersion('./memos/warren_buffett_pixel_y2k.png'),
      marks: memoImageWithVersion('./memos/howard_marks_pixel_y2k.png'),
      nomad: memoImageWithVersion('./memos/nomad_partnership_pixel_y2k_logo.png'),
    };

    const mediaReduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let activeMemoId = memos[0].id;

    const getActiveMemo = () => memos.find((memo) => memo.id === activeMemoId) || memos[0];
    const shiftMemo = (delta) => {
      const currentIndex = memos.findIndex((memo) => memo.id === activeMemoId);
      const safeIndex = currentIndex >= 0 ? currentIndex : 0;
      const nextIndex = (safeIndex + delta + memos.length) % memos.length;
      activeMemoId = memos[nextIndex].id;
      renderMemo();
    };

    const getMemoSections = (memo) => {
      if (Array.isArray(memo.bodyText)) {
        return memo.bodyText.map((section) => String(section).trim()).filter(Boolean);
      }
      return String(memo.bodyText || '')
        .split(/\n{2,}/)
        .map((section) => section.trim())
        .filter(Boolean);
    };

    const renderMemoSections = (target, sections) => {
      target.replaceChildren();
      sections.forEach((section) => {
        const block = document.createElement('p');
        block.className = 'memo-entry';
        block.textContent = section;
        target.appendChild(block);
      });
    };

    const setPortraitSource = (memo) => {
      const src = memoPortraitByAuthor[memo.authorKey] || '';
      memoPortrait.classList.remove('is-fallback');
      memoPortrait.removeAttribute('data-fallback');

      if (!src) {
        memoPortrait.classList.add('is-fallback');
        memoPortrait.setAttribute('data-fallback', memo.authorKey.toUpperCase().slice(0, 4));
        memoPortraitImage.removeAttribute('src');
        memoPortraitImage.alt = '';
        return;
      }

      memoPortraitImage.alt = `${memo.authorKey} pixel portrait`;
      memoPortraitImage.src = src;
      memoPortraitImage.onerror = () => {
        memoPortrait.classList.add('is-fallback');
        memoPortrait.setAttribute('data-fallback', memo.authorKey.toUpperCase().slice(0, 4));
      };
      memoPortraitImage.onload = () => {
        memoPortrait.classList.remove('is-fallback');
        memoPortrait.removeAttribute('data-fallback');
      };
    };

    const applyManualScrollMode = () => {
      memoTrack.classList.remove('is-animated');
      memoViewport.classList.add('manual-scroll');
      memoViewport.scrollTop = 0;
      memoGap.style.height = '0px';
      memoBodyClone.style.display = 'none';
      memoBodyClone.replaceChildren();
    };

    const recalculateMemoScroll = () => {
      if (mediaReduceMotion.matches) {
        applyManualScrollMode();
        return;
      }

      const viewportHeight = memoViewport.clientHeight;
      const contentHeight = memoBody.scrollHeight;
      const overflow = contentHeight - viewportHeight;
      if (overflow <= 1) {
        applyManualScrollMode();
        return;
      }

      const gapHeight = Math.max(24, Math.min(72, Math.round(viewportHeight * 0.3)));
      const loopDistance = contentHeight + gapHeight;
      const durationSeconds = Math.max(12, contentHeight / 30);

      memoGap.style.height = `${gapHeight}px`;
      memoBodyClone.style.display = 'block';
      memoBodyClone.innerHTML = memoBody.innerHTML;
      memoViewport.classList.remove('manual-scroll');
      memoTrack.style.setProperty('--memo-scroll-distance', `${loopDistance}px`);
      memoTrack.style.setProperty('--memo-scroll-duration', `${durationSeconds}s`);
      memoTrack.classList.remove('is-animated');
      void memoTrack.offsetWidth;
      memoTrack.classList.add('is-animated');
    };

    const renderMemo = () => {
      const memo = getActiveMemo();
      memoFilename.textContent = memo.filename;
      memoTitle.textContent = memo.title;
      memoStatus.textContent = 'ACTIVE';
      renderMemoSections(memoBody, getMemoSections(memo));
      setPortraitSource(memo);
      recalculateMemoScroll();
    };

    if ('ResizeObserver' in window) {
      const memoResizeObserver = new ResizeObserver(() => recalculateMemoScroll());
      memoResizeObserver.observe(memoViewport);
      memoResizeObserver.observe(memoBody);
      memoResizeObserver.observe(memoWidget);
    }

    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => recalculateMemoScroll()).catch(() => {});
    }

    if (typeof mediaReduceMotion.addEventListener === 'function') {
      mediaReduceMotion.addEventListener('change', recalculateMemoScroll);
    } else if (typeof mediaReduceMotion.addListener === 'function') {
      mediaReduceMotion.addListener(recalculateMemoScroll);
    }

    if (memoPrevBtn) memoPrevBtn.addEventListener('click', () => shiftMemo(-1));
    if (memoNextBtn) memoNextBtn.addEventListener('click', () => shiftMemo(1));
    memoWidget.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        shiftMemo(-1);
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        shiftMemo(1);
      }
    });

    window.addEventListener('resize', recalculateMemoScroll);
    renderMemo();
    } catch (err) {
      console.warn('Memo widget init failed, keeping fallback markup.', err);
    }
  }
})();
