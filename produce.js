(function () {
  const resourceGrid = document.getElementById('produce-resource-grid');
  const productsBody = document.getElementById('produce-products-body');
  const statusEl = document.getElementById('produce-status');
  if (!resourceGrid || !productsBody || !statusEl) return;

  const PLAYER_KEYS = ['yomama_player_save_v1', 'yomama_player_save_v1_backup'];
  const GAME_KEYS = ['yomama_game_save_v1', 'yomama_game_save_v1_backup'];
  const MARKET_KEYS = ['yomama_marketplace_inventory_v1', 'yomama_marketplace_inventory_v1_backup'];
  const ACCOUNT_KEYS = ['yomama_watchmk_account_v1', 'yomama_watchmk_account_v1_backup'];
  const USERNAME = 'WATCHMK';
  const resourceKeys = Object.freeze(['food', 'materials', 'energy', 'data']);
  const resourceLabels = Object.freeze({
    food: 'Food',
    materials: 'Materials',
    energy: 'Energy',
    data: 'Data',
  });

  const products = Object.freeze([
    {
      id: 'hydro_lettuce_crate',
      name: 'Hydro Lettuce Crate',
      startStock: 48,
      recipe: { food: 36, materials: 8, energy: 6, data: 2 },
    },
    {
      id: 'canned_bean_pack',
      name: 'Canned Bean Pack',
      startStock: 32,
      recipe: { food: 24, materials: 12, energy: 5, data: 1 },
    },
    {
      id: 'bio_fuel_cell',
      name: 'Bio Fuel Cell',
      startStock: 18,
      recipe: { food: 14, materials: 24, energy: 36, data: 12 },
    },
    {
      id: 'copper_tool_set',
      name: 'Copper Tool Set',
      startStock: 25,
      recipe: { food: 8, materials: 34, energy: 16, data: 6 },
    },
    {
      id: 'sensor_chip_batch',
      name: 'Sensor Chip Batch',
      startStock: 14,
      recipe: { food: 6, materials: 28, energy: 24, data: 32 },
    },
  ]);

  const getStorages = () => {
    const stores = [];
    try {
      stores.push(window.localStorage);
    } catch (_) {}
    try {
      stores.push(window.sessionStorage);
    } catch (_) {}
    return stores;
  };

  const readFirstValidJson = (keys) => {
    const keyList = Array.isArray(keys) ? keys : [];
    const stores = getStorages();
    for (const storage of stores) {
      for (const key of keyList) {
        try {
          const raw = storage.getItem(key);
          if (!raw) continue;
          const parsed = JSON.parse(raw);
          if (parsed && typeof parsed === 'object') return parsed;
        } catch (_) {}
      }
    }
    return null;
  };

  const writeJsonToAllStores = (keys, value) => {
    const keyList = Array.isArray(keys) ? keys : [];
    const encoded = JSON.stringify(value);
    const stores = getStorages();
    stores.forEach((storage) => {
      keyList.forEach((key) => {
        try {
          storage.setItem(key, encoded);
        } catch (_) {}
      });
    });
  };

  const toSafeInt = (value, fallback = 0) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.floor(parsed) : fallback;
  };

  const toNonNegativeInt = (value, fallback = 0) => Math.max(0, toSafeInt(value, fallback));
  const formatNumber = (value) => Math.max(0, toSafeInt(value, 0)).toLocaleString('en-US');
  const escapeHtml = (value) => String(value).replace(/[<>&"]/g, (char) => {
    if (char === '<') return '&lt;';
    if (char === '>') return '&gt;';
    if (char === '&') return '&amp;';
    return '&quot;';
  });

  const defaultResourceInventory = () => ({
    food: 260,
    materials: 220,
    energy: 190,
    data: 140,
  });

  const sanitizeResourceInventory = (value) => {
    const source = value && typeof value === 'object' ? value : {};
    const result = defaultResourceInventory();
    resourceKeys.forEach((key) => {
      result[key] = toNonNegativeInt(source[key], result[key]);
    });
    return result;
  };

  const defaultProductInventory = () => {
    const map = {};
    products.forEach((product) => {
      map[product.id] = product.startStock;
    });
    return map;
  };

  const sanitizeProductInventory = (value) => {
    const source = value && typeof value === 'object' ? value : {};
    const result = defaultProductInventory();
    products.forEach((product) => {
      result[product.id] = toNonNegativeInt(source[product.id], result[product.id]);
    });
    return result;
  };

  const readCashFromState = (value) => {
    if (!value || typeof value !== 'object') return null;
    const walletCash = Number(value.wallet && value.wallet.cash);
    if (Number.isFinite(walletCash) && walletCash >= 0) return Math.floor(walletCash);
    const topLevelCash = Number(value.cash);
    if (Number.isFinite(topLevelCash) && topLevelCash >= 0) return Math.floor(topLevelCash);
    const accountWalletCash = Number(value.account && value.account.wallet && value.account.wallet.cash);
    if (Number.isFinite(accountWalletCash) && accountWalletCash >= 0) return Math.floor(accountWalletCash);
    const accountCash = Number(value.account && value.account.cash);
    if (Number.isFinite(accountCash) && accountCash >= 0) return Math.floor(accountCash);
    return null;
  };

  const readProductInventoryFromState = (value) => {
    if (!value || typeof value !== 'object') return null;
    const candidates = [
      value.inventory,
      value.marketplaceInventory,
      value.marketplace && value.marketplace.inventory,
    ];
    for (const candidate of candidates) {
      if (candidate && typeof candidate === 'object') {
        return sanitizeProductInventory(candidate);
      }
    }
    return null;
  };

  const readResourceInventory = () => {
    const playerSave = readFirstValidJson(PLAYER_KEYS);
    if (!playerSave || typeof playerSave !== 'object') {
      return defaultResourceInventory();
    }
    const economyInventory = playerSave.economyV01 && playerSave.economyV01.inventory;
    if (economyInventory && typeof economyInventory === 'object') {
      return sanitizeResourceInventory(economyInventory);
    }
    return defaultResourceInventory();
  };

  const readProductInventory = () => {
    const accountSave = readFirstValidJson(ACCOUNT_KEYS);
    const accountInventory = readProductInventoryFromState(accountSave);
    if (accountInventory) return accountInventory;
    return sanitizeProductInventory(readFirstValidJson(MARKET_KEYS));
  };

  const readWalletCash = () => {
    const accountSave = readFirstValidJson(ACCOUNT_KEYS);
    const accountCash = readCashFromState(accountSave);
    if (accountCash !== null) return accountCash;

    const playerSave = readFirstValidJson(PLAYER_KEYS);
    const playerCash = readCashFromState(playerSave);
    if (playerCash !== null) return playerCash;

    const gameSave = readFirstValidJson(GAME_KEYS);
    const gameCash = readCashFromState(gameSave);
    if (gameCash !== null) return gameCash;

    return 2500;
  };

  const persistResourceInventory = (resourceInventory) => {
    const safeInventory = sanitizeResourceInventory(resourceInventory);
    const existingPlayer = readFirstValidJson(PLAYER_KEYS) || {};
    const fallbackCash = toNonNegativeInt(readCashFromState(existingPlayer), 2500);
    const existingWallet = existingPlayer.wallet && typeof existingPlayer.wallet === 'object'
      ? existingPlayer.wallet
      : {};
    const existingEconomy = existingPlayer.economyV01 && typeof existingPlayer.economyV01 === 'object'
      ? existingPlayer.economyV01
      : {};
    const nextPlayer = {
      ...existingPlayer,
      version: 1,
      selectedCharacter: String(existingPlayer.selectedCharacter || 'buffett').toLowerCase(),
      wallet: {
        ...existingWallet,
        cash: toNonNegativeInt(existingWallet.cash, fallbackCash),
      },
      holdings: existingPlayer.holdings && typeof existingPlayer.holdings === 'object'
        ? existingPlayer.holdings
        : { QQQ: 0, BTC: 0 },
      buildings: Array.isArray(existingPlayer.buildings) ? existingPlayer.buildings : [],
      economyV01: {
        ...existingEconomy,
        inventory: safeInventory,
      },
      meta: {
        ...(existingPlayer.meta && typeof existingPlayer.meta === 'object' ? existingPlayer.meta : {}),
        lastUpdatedAt: Date.now(),
      },
    };
    writeJsonToAllStores(PLAYER_KEYS, nextPlayer);
  };

  const persistProductInventory = (productInventory) => {
    writeJsonToAllStores(MARKET_KEYS, sanitizeProductInventory(productInventory));
  };

  const persistAccountSnapshot = (cash, productInventory) => {
    const safeCash = toNonNegativeInt(cash, 0);
    const safeInventory = sanitizeProductInventory(productInventory);
    const existingAccount = readFirstValidJson(ACCOUNT_KEYS) || {};
    const accountSave = {
      ...existingAccount,
      version: 1,
      username: String(existingAccount.username || USERNAME).toUpperCase(),
      wallet: {
        ...(existingAccount.wallet && typeof existingAccount.wallet === 'object' ? existingAccount.wallet : {}),
        cash: safeCash,
      },
      inventory: safeInventory,
      marketplace: {
        ...(existingAccount.marketplace && typeof existingAccount.marketplace === 'object' ? existingAccount.marketplace : {}),
        inventory: safeInventory,
        lastUpdatedAt: Date.now(),
      },
      meta: {
        ...(existingAccount.meta && typeof existingAccount.meta === 'object' ? existingAccount.meta : {}),
        lastUpdatedAt: Date.now(),
      },
    };
    writeJsonToAllStores(ACCOUNT_KEYS, accountSave);
  };

  const state = {
    resources: readResourceInventory(),
    products: readProductInventory(),
    cash: readWalletCash(),
  };

  const setStatus = (message, tone = 'neutral') => {
    statusEl.classList.remove('is-success', 'is-error');
    if (tone === 'success') statusEl.classList.add('is-success');
    if (tone === 'error') statusEl.classList.add('is-error');
    statusEl.textContent = message;
  };

  const findProduct = (id) => products.find((product) => product.id === id) || null;

  const computeMaxCraftable = (recipe) => {
    let maxCraftable = Number.POSITIVE_INFINITY;
    resourceKeys.forEach((resourceKey) => {
      const need = toNonNegativeInt(recipe[resourceKey], 0);
      if (need <= 0) return;
      const have = toNonNegativeInt(state.resources[resourceKey], 0);
      maxCraftable = Math.min(maxCraftable, Math.floor(have / need));
    });
    if (!Number.isFinite(maxCraftable)) return 0;
    return Math.max(0, maxCraftable);
  };

  const renderResourceInventory = () => {
    resourceGrid.innerHTML = resourceKeys.map((resourceKey) => {
      const label = resourceLabels[resourceKey] || resourceKey.toUpperCase();
      const value = toNonNegativeInt(state.resources[resourceKey], 0);
      return `
        <div class="bld-resource">
          <div class="bld-resource-main">
            <div class="bld-resource-label">${escapeHtml(label)}</div>
            <div class="bld-resource-value">${formatNumber(value)}</div>
            <div class="bld-resource-cap">Available</div>
          </div>
          <span class="bld-resource-icon-slot bld-square-icon-slot" data-resource="${escapeHtml(resourceKey)}" aria-hidden="true"></span>
        </div>
      `;
    }).join('');
  };

  const renderProductRows = () => {
    productsBody.innerHTML = products.map((product) => {
      const recipe = sanitizeResourceInventory(product.recipe);
      const inStock = toNonNegativeInt(state.products[product.id], product.startStock);
      const maxCraftable = computeMaxCraftable(recipe);
      const canProduce = maxCraftable > 0;
      return `
        <tr>
          <td>${escapeHtml(product.name)}</td>
          <td class="marketplace-qty">${formatNumber(recipe.food)}</td>
          <td class="marketplace-qty">${formatNumber(recipe.materials)}</td>
          <td class="marketplace-qty">${formatNumber(recipe.energy)}</td>
          <td class="marketplace-qty">${formatNumber(recipe.data)}</td>
          <td class="marketplace-qty">${formatNumber(inStock)}</td>
          <td class="marketplace-qty ${canProduce ? 'produce-availability-good' : 'produce-availability-bad'}">
            ${canProduce ? `YES (${formatNumber(maxCraftable)})` : 'NO'}
          </td>
          <td class="marketplace-qty">
            <input
              class="marketplace-qty-input produce-qty-input"
              type="number"
              min="1"
              step="1"
              value="1"
              data-product-qty="${product.id}"
              ${canProduce ? '' : 'disabled'}
            />
          </td>
          <td class="produce-action-cell">
            <button
              type="button"
              class="bld-btn"
              data-action="produce-product"
              data-product="${product.id}"
              ${canProduce ? '' : 'disabled'}
            >PRODUCE</button>
          </td>
        </tr>
      `;
    }).join('');
  };

  const renderAll = () => {
    renderResourceInventory();
    renderProductRows();
  };

  const persistState = () => {
    persistResourceInventory(state.resources);
    persistProductInventory(state.products);
    persistAccountSnapshot(state.cash, state.products);
  };

  const readQtyForProduct = (productId) => {
    const input = document.querySelector(`input[data-product-qty="${productId}"]`);
    if (!input) return 1;
    return Math.max(1, toNonNegativeInt(input.value, 1));
  };

  const handleProduce = (productId) => {
    const product = findProduct(productId);
    if (!product) return;

    const recipe = sanitizeResourceInventory(product.recipe);
    const maxCraftable = computeMaxCraftable(recipe);
    if (maxCraftable <= 0) {
      setStatus(`Not enough resources to produce ${product.name}.`, 'error');
      return;
    }

    const qty = readQtyForProduct(product.id);
    if (qty > maxCraftable) {
      setStatus(`You can produce at most ${formatNumber(maxCraftable)} ${product.name} right now.`, 'error');
      return;
    }

    resourceKeys.forEach((resourceKey) => {
      const current = toNonNegativeInt(state.resources[resourceKey], 0);
      const spend = recipe[resourceKey] * qty;
      state.resources[resourceKey] = Math.max(0, current - spend);
    });
    state.products[product.id] = toNonNegativeInt(state.products[product.id], product.startStock) + qty;

    persistState();
    renderAll();

    // In a class session the finished goods must also reach the server, or they
    // never appear in the shared marketplace.
    const net = window.YomamaNet;
    if (net && net.isLive()) {
      setStatus(`Produced ${formatNumber(qty)} ${product.name}. Sending to your warehouse...`);
      net.deposit(product.id, qty).then((res) => {
        setStatus(
          `Produced ${formatNumber(qty)} ${product.name}. Ready to sell (${res.qty} in stock).`,
          'success',
        );
      }).catch((err) => {
        setStatus((err && err.message) || `Produced ${formatNumber(qty)} ${product.name}, but the server did not record it.`, 'error');
      });
      return;
    }

    setStatus(`Produced ${formatNumber(qty)} ${product.name}. Inventory updated.`, 'success');
  };

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target.closest('button[data-action]') : null;
    if (!target) return;
    const shell = target.closest('.produce-shell');
    if (!shell) return;
    const action = String(target.getAttribute('data-action') || '').toLowerCase();
    if (action !== 'produce-product') return;
    const productId = String(target.getAttribute('data-product') || '');
    if (!productId) return;
    handleProduce(productId);
  });

  document.addEventListener('change', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (!target.hasAttribute('data-product-qty')) return;
    target.value = String(Math.max(1, toNonNegativeInt(target.value, 1)));
  });

  persistState();
  renderAll();
  setStatus('Produce view ready. Rows marked YES are currently craftable with your Food, Materials, Energy, and Data.', 'neutral');
})();
