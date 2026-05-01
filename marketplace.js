(function () {
  const inventoryBody = document.getElementById('marketplace-inventory-body');
  const buyBody = document.getElementById('marketplace-buy-body');
  const sellBody = document.getElementById('marketplace-sell-body');
  const statusEl = document.getElementById('marketplace-status');
  if (!inventoryBody || !buyBody || !sellBody || !statusEl) return;

  const PLAYER_KEYS = ['yomama_player_save_v1', 'yomama_player_save_v1_backup'];
  const GAME_KEYS = ['yomama_game_save_v1', 'yomama_game_save_v1_backup'];
  const MARKET_KEYS = ['yomama_marketplace_inventory_v1', 'yomama_marketplace_inventory_v1_backup'];
  const MARKET_STOCK_KEYS = ['yomama_marketplace_stock_v1', 'yomama_marketplace_stock_v1_backup'];
  const ACCOUNT_KEYS = ['yomama_watchmk_account_v1', 'yomama_watchmk_account_v1_backup'];
  const USERNAME = 'WATCHMK';

  const products = Object.freeze([
    {
      id: 'hydro_lettuce_crate',
      name: 'Hydro Lettuce Crate',
      buyPrice: 14,
      sellPrice: 11,
      startStock: 48,
      marketStartStock: 140,
      marketCap: 220,
    },
    {
      id: 'canned_bean_pack',
      name: 'Canned Bean Pack',
      buyPrice: 9,
      sellPrice: 7,
      startStock: 32,
      marketStartStock: 120,
      marketCap: 200,
    },
    {
      id: 'bio_fuel_cell',
      name: 'Bio Fuel Cell',
      buyPrice: 62,
      sellPrice: 54,
      startStock: 18,
      marketStartStock: 55,
      marketCap: 90,
    },
    {
      id: 'copper_tool_set',
      name: 'Copper Tool Set',
      buyPrice: 39,
      sellPrice: 31,
      startStock: 25,
      marketStartStock: 80,
      marketCap: 130,
    },
    {
      id: 'sensor_chip_batch',
      name: 'Sensor Chip Batch',
      buyPrice: 85,
      sellPrice: 74,
      startStock: 14,
      marketStartStock: 42,
      marketCap: 70,
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

  const formatMoney = (value) => `$${Math.round(value).toLocaleString('en-US')}`;

  const defaultInventory = () => {
    const map = {};
    products.forEach((product) => {
      map[product.id] = product.startStock;
    });
    return map;
  };

  const sanitizeInventory = (value) => {
    const source = value && typeof value === 'object' ? value : {};
    const result = defaultInventory();
    products.forEach((product) => {
      result[product.id] = toNonNegativeInt(source[product.id], result[product.id]);
    });
    return result;
  };

  const defaultMarketStock = () => {
    const map = {};
    products.forEach((product) => {
      map[product.id] = toNonNegativeInt(product.marketStartStock, 0);
    });
    return map;
  };

  const sanitizeMarketStock = (value) => {
    const source = value && typeof value === 'object' ? value : {};
    const result = defaultMarketStock();
    products.forEach((product) => {
      const cap = toNonNegativeInt(product.marketCap, result[product.id]);
      result[product.id] = Math.min(cap, toNonNegativeInt(source[product.id], result[product.id]));
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

  const readInventoryFromState = (value) => {
    if (!value || typeof value !== 'object') return null;
    const candidates = [
      value.inventory,
      value.marketplaceInventory,
      value.marketplace && value.marketplace.inventory,
    ];
    for (const candidate of candidates) {
      if (candidate && typeof candidate === 'object') {
        return sanitizeInventory(candidate);
      }
    }
    return null;
  };

  const readMarketStockFromState = (value) => {
    if (!value || typeof value !== 'object') return null;
    const candidates = [
      value.marketStock,
      value.marketplaceStock,
      value.marketplace && value.marketplace.stock,
      value.marketplace && value.marketplace.marketStock,
    ];
    for (const candidate of candidates) {
      if (candidate && typeof candidate === 'object') {
        return sanitizeMarketStock(candidate);
      }
    }
    return null;
  };

  const getWalletCash = () => {
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

  const updateCashChip = (cash, shouldFlash) => {
    const rightMeta = document.querySelector('.right-meta');
    if (!rightMeta) return;

    let chip = document.getElementById('game-cash-chip');
    if (!chip) {
      chip = document.createElement('span');
      chip.id = 'game-cash-chip';
      chip.className = 'chip amber';
      rightMeta.insertBefore(chip, rightMeta.firstChild);
    }

    chip.textContent = `USER ${USERNAME} | CASH ${formatMoney(cash)}`;

    if (!shouldFlash) return;
    chip.classList.remove('marketplace-cash-flash');
    void chip.offsetWidth;
    chip.classList.add('marketplace-cash-flash');
    window.setTimeout(() => {
      chip.classList.remove('marketplace-cash-flash');
    }, 260);
  };

  const persistWalletCash = (cash) => {
    const safeCash = toNonNegativeInt(cash, 0);

    const existingPlayer = readFirstValidJson(PLAYER_KEYS) || {};
    const playerSave = {
      version: 1,
      selectedCharacter: String(existingPlayer.selectedCharacter || 'buffett').toLowerCase(),
      wallet: {
        ...(existingPlayer.wallet && typeof existingPlayer.wallet === 'object' ? existingPlayer.wallet : {}),
        cash: safeCash,
      },
      holdings: existingPlayer.holdings && typeof existingPlayer.holdings === 'object'
        ? existingPlayer.holdings
        : { QQQ: 0, BTC: 0 },
      buildings: Array.isArray(existingPlayer.buildings) ? existingPlayer.buildings : [],
      economyV01: existingPlayer.economyV01 && typeof existingPlayer.economyV01 === 'object'
        ? existingPlayer.economyV01
        : null,
      meta: {
        ...(existingPlayer.meta && typeof existingPlayer.meta === 'object' ? existingPlayer.meta : {}),
        lastUpdatedAt: Date.now(),
      },
    };
    writeJsonToAllStores(PLAYER_KEYS, playerSave);

    const existingGame = readFirstValidJson(GAME_KEYS) || {};
    const gameSave = {
      version: 1,
      selectedCharacter: String(existingGame.selectedCharacter || playerSave.selectedCharacter || '').toLowerCase(),
      wallet: {
        ...(existingGame.wallet && typeof existingGame.wallet === 'object' ? existingGame.wallet : {}),
        cash: safeCash,
      },
      meta: {
        ...(existingGame.meta && typeof existingGame.meta === 'object' ? existingGame.meta : {}),
        lastSeenAt: Date.now(),
      },
    };
    writeJsonToAllStores(GAME_KEYS, gameSave);
  };

  const persistAccountSnapshot = (cash, inventory, marketStock) => {
    const safeCash = toNonNegativeInt(cash, 0);
    const safeInventory = sanitizeInventory(inventory);
    const safeMarketStock = sanitizeMarketStock(marketStock);
    const existingAccount = readFirstValidJson(ACCOUNT_KEYS) || {};
    const accountSave = {
      version: 1,
      username: String(existingAccount.username || USERNAME).toUpperCase(),
      wallet: {
        ...(existingAccount.wallet && typeof existingAccount.wallet === 'object' ? existingAccount.wallet : {}),
        cash: safeCash,
      },
      inventory: safeInventory,
      marketStock: safeMarketStock,
      marketplace: {
        ...(existingAccount.marketplace && typeof existingAccount.marketplace === 'object' ? existingAccount.marketplace : {}),
        inventory: safeInventory,
        stock: safeMarketStock,
        lastUpdatedAt: Date.now(),
      },
      meta: {
        ...(existingAccount.meta && typeof existingAccount.meta === 'object' ? existingAccount.meta : {}),
        lastUpdatedAt: Date.now(),
      },
    };
    writeJsonToAllStores(ACCOUNT_KEYS, accountSave);
  };

  const accountState = readFirstValidJson(ACCOUNT_KEYS);
  const hasAccountState = Boolean(accountState && typeof accountState === 'object');
  const state = {
    cash: getWalletCash(),
    inventory: readInventoryFromState(accountState) || sanitizeInventory(readFirstValidJson(MARKET_KEYS)),
    marketStock: readMarketStockFromState(accountState) || sanitizeMarketStock(readFirstValidJson(MARKET_STOCK_KEYS)),
  };

  const setStatus = (message, tone = 'neutral') => {
    statusEl.classList.remove('is-success', 'is-error');
    if (tone === 'success') statusEl.classList.add('is-success');
    if (tone === 'error') statusEl.classList.add('is-error');
    statusEl.textContent = message;
  };

  const findProduct = (id) => products.find((product) => product.id === id) || null;
  const getMarketAvailable = (product) => toNonNegativeInt(state.marketStock[product.id], product.marketStartStock);
  const getMarketCap = (product) => Math.max(
    toNonNegativeInt(product.marketCap, product.marketStartStock),
    toNonNegativeInt(product.marketStartStock, 0),
  );
  const getMarketSpace = (product) => Math.max(0, getMarketCap(product) - getMarketAvailable(product));

  const renderInventoryTable = () => {
    inventoryBody.innerHTML = products.map((product) => `
      <tr>
        <td>${product.name}</td>
        <td class="marketplace-qty">${toNonNegativeInt(state.inventory[product.id], product.startStock)}</td>
        <td class="amber">${formatMoney(product.buyPrice)}</td>
        <td class="up">${formatMoney(product.sellPrice)}</td>
      </tr>
    `).join('');
  };

  const renderTradeTable = (targetBody, tradeType) => {
    const isBuy = tradeType === 'buy';
    targetBody.innerHTML = products.map((product) => {
      const marketAvailable = getMarketAvailable(product);
      const marketCap = getMarketCap(product);
      const marketSpace = getMarketSpace(product);
      const inStock = toNonNegativeInt(state.inventory[product.id], product.startStock);
      const hasRoom = marketSpace > 0;
      const canBuy = marketAvailable > 0;
      const canSell = hasRoom && inStock > 0;
      const qtyMax = isBuy
        ? Math.max(1, marketAvailable)
        : Math.max(1, Math.min(inStock, marketSpace));
      const availabilityValue = isBuy
        ? `${marketAvailable}/${marketCap}`
        : `${marketSpace}/${marketCap}`;
      const availabilityClass = isBuy
        ? (marketAvailable > 0 ? 'up' : 'dn')
        : (marketSpace > 0 ? 'up' : 'dn');
      const tradeDisabled = isBuy ? !canBuy : !canSell;
      return `
        <tr>
          <td>${product.name}</td>
          <td class="${isBuy ? 'amber' : 'up'}">${formatMoney(isBuy ? product.buyPrice : product.sellPrice)}</td>
          <td class="marketplace-qty ${availabilityClass}">${availabilityValue}</td>
          <td class="marketplace-qty">
            <input
              class="marketplace-qty-input"
              type="number"
              min="1"
              max="${qtyMax}"
              step="1"
              value="1"
              data-trade="${tradeType}"
              data-product="${product.id}"
              aria-label="${tradeType} quantity for ${product.name}"
              ${tradeDisabled ? 'disabled' : ''}
            />
          </td>
          <td class="marketplace-action-cell">
            <button
              class="bld-btn${isBuy ? '' : ' alt'}"
              type="button"
              data-action="${tradeType}"
              data-product="${product.id}"
              ${tradeDisabled ? 'disabled' : ''}
            >${tradeType.toUpperCase()}</button>
            <button
              class="bld-btn alt"
              type="button"
              data-action="${tradeType}-all"
              data-product="${product.id}"
              ${tradeDisabled ? 'disabled' : ''}
            >${tradeType.toUpperCase()} ALL</button>
          </td>
        </tr>
      `;
    }).join('');
  };

  const renderAll = (flashCash = false) => {
    renderInventoryTable();
    renderTradeTable(buyBody, 'buy');
    renderTradeTable(sellBody, 'sell');
    updateCashChip(state.cash, flashCash);
  };

  const persistState = () => {
    writeJsonToAllStores(MARKET_KEYS, state.inventory);
    writeJsonToAllStores(MARKET_STOCK_KEYS, state.marketStock);
    persistWalletCash(state.cash);
    persistAccountSnapshot(state.cash, state.inventory, state.marketStock);
  };

  const readQtyForAction = (tradeType, productId) => {
    const selector = `input.marketplace-qty-input[data-trade="${tradeType}"][data-product="${productId}"]`;
    const input = document.querySelector(selector);
    if (!input) return 1;
    const max = toNonNegativeInt(input.getAttribute('max'), 0);
    const requested = Math.max(1, toNonNegativeInt(input.value, 1));
    if (max <= 0) return requested;
    return Math.min(max, requested);
  };

  const handleBuy = (productId, buyAll = false) => {
    const product = findProduct(productId);
    if (!product) return;
    const marketAvailable = getMarketAvailable(product);
    if (marketAvailable <= 0) {
      setStatus(`${product.name} is sold out right now.`, 'error');
      return;
    }

    const affordableQty = Math.floor(state.cash / product.buyPrice);
    const qty = buyAll
      ? Math.max(0, Math.min(marketAvailable, affordableQty))
      : readQtyForAction('buy', product.id);
    if (qty <= 0) {
      setStatus(`Not enough cash to buy any ${product.name}.`, 'error');
      return;
    }
    if (qty > marketAvailable) {
      setStatus(`Only ${marketAvailable} ${product.name} available in marketplace stock.`, 'error');
      return;
    }

    const totalCost = product.buyPrice * qty;

    if (state.cash < totalCost) {
      setStatus(`Not enough cash to buy ${qty} ${product.name}. Need ${formatMoney(totalCost)}.`, 'error');
      return;
    }

    state.cash -= totalCost;
    state.inventory[product.id] = toNonNegativeInt(state.inventory[product.id], 0) + qty;
    state.marketStock[product.id] = Math.max(0, marketAvailable - qty);
    persistState();
    renderAll(true);
    setStatus(
      `Bought ${qty} ${product.name} for ${formatMoney(totalCost)}. Marketplace stock now ${state.marketStock[product.id]}/${getMarketCap(product)}.`,
      'success',
    );
  };

  const handleSell = (productId, sellAll = false) => {
    const product = findProduct(productId);
    if (!product) return;
    const inStock = toNonNegativeInt(state.inventory[product.id], 0);
    const marketAvailable = getMarketAvailable(product);
    const marketCap = getMarketCap(product);
    const marketSpace = Math.max(0, marketCap - marketAvailable);

    if (marketSpace <= 0) {
      setStatus(`Marketplace is full for ${product.name}. (${marketAvailable}/${marketCap})`, 'error');
      return;
    }

    const qty = sellAll
      ? Math.max(0, Math.min(inStock, marketSpace))
      : readQtyForAction('sell', product.id);
    if (qty <= 0) {
      setStatus(`No ${product.name} available to sell.`, 'error');
      return;
    }

    if (qty > inStock) {
      setStatus(`Not enough stock to sell ${qty} ${product.name}. You have ${inStock}.`, 'error');
      return;
    }
    if (qty > marketSpace) {
      setStatus(`Marketplace can take only ${marketSpace} more ${product.name} right now.`, 'error');
      return;
    }

    const totalValue = product.sellPrice * qty;
    state.cash += totalValue;
    state.inventory[product.id] = inStock - qty;
    state.marketStock[product.id] = Math.min(marketCap, marketAvailable + qty);
    persistState();
    renderAll(true);
    setStatus(
      `Sold ${qty} ${product.name} for ${formatMoney(totalValue)}. Marketplace stock now ${state.marketStock[product.id]}/${marketCap}.`,
      'success',
    );
  };

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target.closest('button[data-action]') : null;
    if (!target) return;
    const action = String(target.getAttribute('data-action') || '').toLowerCase();
    const productId = String(target.getAttribute('data-product') || '');
    if (!productId) return;
    if (action === 'buy') handleBuy(productId);
    if (action === 'buy-all') handleBuy(productId, true);
    if (action === 'sell') handleSell(productId);
    if (action === 'sell-all') handleSell(productId, true);
  });

  document.addEventListener('change', (event) => {
    const input = event.target instanceof Element ? event.target.closest('input.marketplace-qty-input') : null;
    if (!(input instanceof HTMLInputElement)) return;
    const max = toNonNegativeInt(input.getAttribute('max'), 0);
    const requested = Math.max(1, toNonNegativeInt(input.value, 1));
    input.value = String(max > 0 ? Math.min(max, requested) : requested);
  });

  persistState();
  renderAll(false);
  setStatus(
    hasAccountState
      ? `WATCHMK account loaded. Cash, inventory, and capped marketplace stock synced.`
      : 'Marketplace ready. Use BUY/BUY ALL or SELL/SELL ALL with capped marketplace stock.',
  );
})();
