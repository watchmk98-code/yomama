(function () {
  "use strict";

  var ENGINE_VERSION = "0.1.0";

  var DEFAULT_CONTEST_CONFIG = {
    startingCash: 100000,
    benchmarkSymbol: "SPY",
    longOnly: true,
    allowedOrderTypes: ["market", "limit"],
    allowedSessions: ["pre", "regular", "after"],
    quoteDelayMinutes: 15,
    slippageModel: "base_plus_extended_hours",
    assetUniverseMode: "curated_us_stocks_etfs",
    scoreWeights: {
      performance: 0.8,
      discipline: 0.2
    }
  };

  function createId(prefix) {
    return [
      prefix,
      Date.now().toString(36),
      Math.random().toString(36).slice(2, 8)
    ].join("_");
  }

  function toTrimmedString(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function toUpperSymbol(value) {
    return toTrimmedString(value).toUpperCase();
  }

  function toLowerValue(value) {
    return toTrimmedString(value).toLowerCase();
  }

  function toPositiveInteger(value) {
    var numericValue = typeof value === "number" ? value : Number(value);

    if (!Number.isInteger(numericValue) || numericValue <= 0) {
      return null;
    }

    return numericValue;
  }

  function toPositiveNumberOrNull(value) {
    if (value === null || value === undefined || value === "") {
      return null;
    }

    var numericValue = typeof value === "number" ? value : Number(value);

    if (!Number.isFinite(numericValue) || numericValue <= 0) {
      return null;
    }

    return numericValue;
  }

  function toNonNegativeNumber(value, fallback) {
    var numericValue = typeof value === "number" ? value : Number(value);

    if (!Number.isFinite(numericValue) || numericValue < 0) {
      return fallback;
    }

    return numericValue;
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function createIsoTimestamp() {
    return new Date().toISOString();
  }

  function normalizeStringArray(values, fallbackValues) {
    var source = Array.isArray(values) ? values : fallbackValues;

    return source
      .map(function (value) {
        return toLowerValue(value);
      })
      .filter(function (value) {
        return value;
      });
  }

  function cloneValue(value) {
    if (Array.isArray(value)) {
      return value.map(cloneValue);
    }

    if (value && typeof value === "object") {
      var clone = {};
      var keys = Object.keys(value);
      var index = 0;

      for (index = 0; index < keys.length; index += 1) {
        clone[keys[index]] = cloneValue(value[keys[index]]);
      }

      return clone;
    }

    return value;
  }

  function clonePaperState(paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};

    return {
      version: state.version || ENGINE_VERSION,
      contestId: toTrimmedString(state.contestId),
      participantId: toTrimmedString(state.participantId),
      alias: toTrimmedString(state.alias),
      account: {
        startingCash:
          state.account && typeof state.account.startingCash === "number"
            ? state.account.startingCash
            : DEFAULT_CONTEST_CONFIG.startingCash,
        availableCash:
          state.account && typeof state.account.availableCash === "number"
            ? state.account.availableCash
            : DEFAULT_CONTEST_CONFIG.startingCash,
        reservedCash:
          state.account && typeof state.account.reservedCash === "number"
            ? state.account.reservedCash
            : 0,
        realizedPnl:
          state.account && typeof state.account.realizedPnl === "number"
            ? state.account.realizedPnl
            : 0
      },
      ledger: {
        orders:
          state.ledger && Array.isArray(state.ledger.orders)
            ? state.ledger.orders.map(cloneValue)
            : [],
        fills:
          state.ledger && Array.isArray(state.ledger.fills)
            ? state.ledger.fills.map(cloneValue)
            : [],
        cashEvents:
          state.ledger && Array.isArray(state.ledger.cashEvents)
            ? state.ledger.cashEvents.map(cloneValue)
            : []
      },
      benchmark: createBenchmarkState(
        state.benchmark,
        DEFAULT_CONTEST_CONFIG.benchmarkSymbol
      ),
      positions: state.positions && typeof state.positions === "object" ? cloneValue(state.positions) : {},
      snapshots: Array.isArray(state.snapshots) ? state.snapshots.map(cloneValue) : [],
      scoreSnapshots: Array.isArray(state.scoreSnapshots) ? state.scoreSnapshots.map(cloneValue) : [],
      meta: {
        createdAt:
          state.meta && typeof state.meta.createdAt === "string"
            ? state.meta.createdAt
            : createIsoTimestamp(),
        updatedAt:
          state.meta && typeof state.meta.updatedAt === "string"
            ? state.meta.updatedAt
            : createIsoTimestamp()
      }
    };
  }

  function normalizeSubmittedOrder(order, fallbackTimestamp) {
    var normalizedOrder = cloneValue(order);

    normalizedOrder.id = normalizedOrder.id || createId("draft");
    normalizedOrder.symbol = toUpperSymbol(normalizedOrder.symbol);
    normalizedOrder.side = toLowerValue(normalizedOrder.side);
    normalizedOrder.type = toLowerValue(normalizedOrder.type);
    normalizedOrder.quantity = toPositiveInteger(normalizedOrder.quantity);
    normalizedOrder.limitPrice = toPositiveNumberOrNull(normalizedOrder.limitPrice);
    normalizedOrder.referencePrice = toPositiveNumberOrNull(normalizedOrder.referencePrice);
    normalizedOrder.session = toLowerValue(normalizedOrder.session) || "regular";
    normalizedOrder.timeInForce = toLowerValue(normalizedOrder.timeInForce) || "day";
    normalizedOrder.createdAt = normalizedOrder.createdAt || fallbackTimestamp;

    return normalizedOrder;
  }

  /**
   * Returns the current aggregated position for a symbol when one exists.
   *
   * @param {Object} paperState Current participant paper state.
   * @param {string} symbol Symbol key to inspect.
   * @returns {Object|null} The current symbol position or null.
   */
  function getPositionForSymbol(paperState, symbol) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var positionSymbol = toUpperSymbol(symbol);

    if (!positionSymbol || !state.positions || typeof state.positions !== "object") {
      return null;
    }

    return state.positions[positionSymbol] || null;
  }

  function findOrderIndexById(orders, orderId) {
    var targetOrderId = toTrimmedString(orderId);
    var index = 0;

    for (index = 0; index < orders.length; index += 1) {
      if (orders[index] && orders[index].id === targetOrderId) {
        return index;
      }
    }

    return -1;
  }

  /**
   * Builds one aggregated position record with consistent mark-to-market fields.
   *
   * @param {Object} params Position inputs.
   * @returns {Object} A plain position snapshot with valuation fields.
   */
  function buildPositionSnapshot(params) {
    var input = params && typeof params === "object" ? params : {};
    var quantity = toPositiveInteger(input.quantity) || 0;
    var totalCost = toNonNegativeNumber(input.totalCost, 0);
    var avgCost = toPositiveNumberOrNull(input.avgCost);
    var fallbackAvgCost = quantity > 0 ? totalCost / quantity : 0;
    var resolvedAvgCost = avgCost || fallbackAvgCost;
    var marketPrice = toPositiveNumberOrNull(input.marketPrice) || resolvedAvgCost;
    var marketValue = quantity * marketPrice;
    var position = {
      symbol: toUpperSymbol(input.symbol),
      quantity: quantity,
      totalCost: totalCost,
      avgCost: resolvedAvgCost,
      openedAt: input.openedAt || createIsoTimestamp(),
      updatedAt: input.updatedAt || createIsoTimestamp(),
      marketPrice: marketPrice,
      marketValue: marketValue,
      unrealizedPnl: marketValue - totalCost
    };

    if (input.lastMarkedAt) {
      position.lastMarkedAt = input.lastMarkedAt;
    }

    return position;
  }

  function createBenchmarkState(params, fallbackSymbol) {
    var input = params && typeof params === "object" ? params : {};

    return {
      symbol: toUpperSymbol(input.symbol) || toUpperSymbol(fallbackSymbol) || DEFAULT_CONTEST_CONFIG.benchmarkSymbol,
      baselinePrice: toPositiveNumberOrNull(input.baselinePrice),
      currentPrice: toPositiveNumberOrNull(input.currentPrice),
      baselineAt: typeof input.baselineAt === "string" ? input.baselineAt : null,
      currentAt: typeof input.currentAt === "string" ? input.currentAt : null,
      source: toTrimmedString(input.source) || "manual"
    };
  }

  /**
   * Creates the contest configuration with locked defaults and shallow overrides.
   *
   * @param {Object} [overrides={}] Optional top-level overrides for the scaffold config.
   * @returns {Object} A normalized contest configuration object.
   */
  function createContestConfig(overrides) {
    var safeOverrides = overrides && typeof overrides === "object" ? overrides : {};

    return {
      startingCash: toNonNegativeNumber(safeOverrides.startingCash, DEFAULT_CONTEST_CONFIG.startingCash),
      benchmarkSymbol: toUpperSymbol(safeOverrides.benchmarkSymbol) || DEFAULT_CONTEST_CONFIG.benchmarkSymbol,
      longOnly: typeof safeOverrides.longOnly === "boolean" ? safeOverrides.longOnly : DEFAULT_CONTEST_CONFIG.longOnly,
      allowedOrderTypes: normalizeStringArray(
        safeOverrides.allowedOrderTypes,
        DEFAULT_CONTEST_CONFIG.allowedOrderTypes
      ),
      allowedSessions: normalizeStringArray(
        safeOverrides.allowedSessions,
        DEFAULT_CONTEST_CONFIG.allowedSessions
      ),
      quoteDelayMinutes: toNonNegativeNumber(
        safeOverrides.quoteDelayMinutes,
        DEFAULT_CONTEST_CONFIG.quoteDelayMinutes
      ),
      slippageModel: toTrimmedString(safeOverrides.slippageModel) || DEFAULT_CONTEST_CONFIG.slippageModel,
      assetUniverseMode:
        toTrimmedString(safeOverrides.assetUniverseMode) || DEFAULT_CONTEST_CONFIG.assetUniverseMode,
      scoreWeights: {
        performance:
          safeOverrides.scoreWeights &&
          typeof safeOverrides.scoreWeights.performance === "number"
            ? safeOverrides.scoreWeights.performance
            : DEFAULT_CONTEST_CONFIG.scoreWeights.performance,
        discipline:
          safeOverrides.scoreWeights &&
          typeof safeOverrides.scoreWeights.discipline === "number"
            ? safeOverrides.scoreWeights.discipline
            : DEFAULT_CONTEST_CONFIG.scoreWeights.discipline
      }
    };
  }

  /**
   * Creates a participant account scaffold with normalized cash fields.
   *
   * @param {Object} params Participant account inputs.
   * @param {string} params.participantId Participant identifier.
   * @param {string} params.alias Display alias for the participant.
   * @param {number} params.startingCash Starting cash balance for the account.
   * @returns {Object} A normalized participant account object.
   */
  function createParticipantAccount(params) {
    var input = params && typeof params === "object" ? params : {};
    var startingCash = toNonNegativeNumber(
      input.startingCash,
      DEFAULT_CONTEST_CONFIG.startingCash
    );

    return {
      participantId: toTrimmedString(input.participantId),
      alias: toTrimmedString(input.alias),
      startingCash: startingCash,
      availableCash: startingCash,
      reservedCash: 0,
      realizedPnl: 0
    };
  }

  /**
   * Creates the initial paper-trading state scaffold for one participant.
   *
   * @param {Object} params Paper state inputs.
   * @param {string} params.contestId Contest identifier.
   * @param {string} params.participantId Participant identifier.
   * @param {string} params.alias Display alias for the participant.
   * @param {string} [params.benchmarkSymbol] Optional benchmark symbol for the scaffold.
   * @returns {Object} A readable state snapshot with empty ledgers and positions.
   */
  function createPaperState(params) {
    var input = params && typeof params === "object" ? params : {};
    var createdAt = createIsoTimestamp();
    var benchmarkSymbol = toUpperSymbol(input.benchmarkSymbol) || DEFAULT_CONTEST_CONFIG.benchmarkSymbol;
    var account = createParticipantAccount({
      participantId: input.participantId,
      alias: input.alias,
      startingCash: DEFAULT_CONTEST_CONFIG.startingCash
    });

    return {
      version: ENGINE_VERSION,
      contestId: toTrimmedString(input.contestId),
      participantId: account.participantId,
      alias: account.alias,
      account: {
        startingCash: account.startingCash,
        availableCash: account.availableCash,
        reservedCash: account.reservedCash,
        realizedPnl: account.realizedPnl
      },
      ledger: {
        orders: [],
        fills: [],
        cashEvents: []
      },
      benchmark: createBenchmarkState(
        { symbol: benchmarkSymbol },
        benchmarkSymbol
      ),
      positions: {},
      snapshots: [],
      scoreSnapshots: [],
      meta: {
        createdAt: createdAt,
        updatedAt: createdAt
      }
    };
  }

  /**
   * Creates a normalized draft order object without submitting or mutating state.
   *
   * @param {Object} params Draft order inputs.
   * @param {string} params.symbol Ticker symbol for the order.
   * @param {string} params.side Order side, expected to be buy or sell.
   * @param {string} params.type Order type, expected to be market or limit.
   * @param {number} params.quantity Share quantity for the order.
   * @param {number} [params.limitPrice] Optional limit price for limit orders.
   * @param {number} [params.referencePrice] Optional reference price for basic checks.
   * @param {string} [params.session] Trading session label for the draft.
   * @param {string} [params.timeInForce] Time-in-force policy for the draft.
   * @returns {Object} A plain normalized order draft with draft status.
   */
  function createOrderDraft(params) {
    var input = params && typeof params === "object" ? params : {};

    return {
      id: createId("draft"),
      symbol: toUpperSymbol(input.symbol),
      side: toLowerValue(input.side),
      type: toLowerValue(input.type),
      quantity: toPositiveInteger(input.quantity),
      limitPrice: toPositiveNumberOrNull(input.limitPrice),
      referencePrice: toPositiveNumberOrNull(input.referencePrice),
      session: toLowerValue(input.session) || "regular",
      timeInForce: toLowerValue(input.timeInForce) || "day",
      status: "draft",
      createdAt: createIsoTimestamp()
    };
  }

  /**
   * Performs basic synchronous validation for a draft order against config and state.
   *
   * @param {Object} order Draft order to validate.
   * @param {Object} contestConfig Contest configuration for rule checks.
   * @param {Object} paperState Current participant paper state.
   * @returns {{ok: boolean, errors: string[]}} Validation result with collected errors.
   */
  function validateDraftOrder(order, contestConfig, paperState) {
    var errors = [];
    var draftOrder = order && typeof order === "object" ? order : {};
    var config = createContestConfig(contestConfig);
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var symbol = draftOrder.symbol;
    var side = draftOrder.side;
    var type = draftOrder.type;
    var quantity = draftOrder.quantity;
    var limitPrice = draftOrder.limitPrice;
    var referencePrice = draftOrder.referencePrice;
    var session = draftOrder.session;
    var timeInForce = draftOrder.timeInForce;
    var currentPosition = getPositionForSymbol(state, symbol);
    var heldQuantity =
      currentPosition && typeof currentPosition.quantity === "number"
        ? currentPosition.quantity
        : 0;

    if (!symbol || typeof symbol !== "string" || symbol !== symbol.toUpperCase()) {
      errors.push("Symbol must be a non-empty uppercase string.");
    }

    if (side !== "buy" && side !== "sell") {
      errors.push('Side must be either "buy" or "sell".');
    }

    if (type !== "market" && type !== "limit") {
      errors.push('Type must be either "market" or "limit".');
    } else if (config.allowedOrderTypes.indexOf(type) === -1) {
      errors.push("Order type is not allowed by this contest.");
    }

    if (config.allowedSessions.indexOf(session) === -1) {
      errors.push("Session must be one of the allowed sessions in this contest.");
    }

    if (timeInForce !== "day") {
      errors.push('Time-in-force must be "day".');
    }

    if (!Number.isInteger(quantity) || quantity <= 0) {
      errors.push("Quantity must be a positive integer.");
    }

    if (type === "limit" && (!Number.isFinite(limitPrice) || limitPrice <= 0)) {
      errors.push("Limit orders require a positive limitPrice.");
    }

    if (side === "buy" && type === "market" && (!Number.isFinite(referencePrice) || referencePrice <= 0)) {
      errors.push("Buy market orders require a positive referencePrice.");
    }

    if (side === "sell" && Number.isInteger(quantity) && quantity > 0) {
      if (!currentPosition || heldQuantity <= 0) {
        errors.push("Sell orders require an existing long position.");
      } else if (quantity > heldQuantity) {
        errors.push("Sell quantity cannot exceed the current held quantity.");
      }
    }

    return {
      ok: errors.length === 0,
      errors: errors
    };
  }

  /**
   * Estimates the cash reservation for a submitted order using simple buy-side rules.
   *
   * @param {Object} order Order-like object to estimate against.
   * @returns {number} A positive reservation amount for valid buy orders, otherwise 0.
   */
  function estimateOrderReservation(order) {
    var sourceOrder = order && typeof order === "object" ? order : {};
    var side = toLowerValue(sourceOrder.side);
    var type = toLowerValue(sourceOrder.type);
    var quantity = toPositiveInteger(sourceOrder.quantity);
    var limitPrice = toPositiveNumberOrNull(sourceOrder.limitPrice);
    var referencePrice = toPositiveNumberOrNull(sourceOrder.referencePrice);

    if (side !== "buy" || !Number.isInteger(quantity) || quantity <= 0) {
      return 0;
    }

    if (type === "market" && referencePrice) {
      return quantity * referencePrice;
    }

    if (type === "limit" && limitPrice) {
      return quantity * limitPrice;
    }

    return 0;
  }

  /**
   * Validates and submits a draft order into a cloned paper-state ledger without fills.
   *
   * @param {Object} orderDraft Draft order to submit.
   * @param {Object} contestConfig Contest configuration for validation rules.
   * @param {Object} paperState Current participant paper state.
   * @returns {{ok: boolean, errors: string[], order?: Object, nextState: Object}} Submit result.
   */
  function submitDraftOrder(orderDraft, contestConfig, paperState) {
    var validation = validateDraftOrder(orderDraft, contestConfig, paperState);

    if (!validation.ok) {
      return {
        ok: false,
        errors: validation.errors.slice(),
        nextState: paperState
      };
    }

    var draft = orderDraft && typeof orderDraft === "object" ? orderDraft : {};
    var nextState = clonePaperState(paperState);
    var submittedAt = createIsoTimestamp();
    var submittedOrder = normalizeSubmittedOrder(draft, submittedAt);
    var reservedAmount = estimateOrderReservation(submittedOrder);

    if (reservedAmount > nextState.account.availableCash) {
      return {
        ok: false,
        errors: ["Order reservation exceeds available cash."],
        nextState: paperState
      };
    }

    submittedOrder.status = "pending";
    submittedOrder.submittedAt = submittedAt;
    submittedOrder.reservedAmount = reservedAmount;

    if (reservedAmount > 0) {
      nextState.account.availableCash -= reservedAmount;
      nextState.account.reservedCash += reservedAmount;
      nextState.ledger.cashEvents.push({
        type: "cash_reserved",
        orderId: submittedOrder.id,
        amount: reservedAmount,
        createdAt: submittedAt
      });
    }

    nextState.ledger.orders.push(submittedOrder);
    nextState.meta.updatedAt = submittedAt;

    return {
      ok: true,
      errors: [],
      order: submittedOrder,
      nextState: nextState
    };
  }

  /**
   * Cancels one pending order and releases any cash reservation attached to it.
   *
   * @param {string} orderId Order identifier to cancel.
   * @param {Object} paperState Current participant paper state.
   * @returns {{ok: boolean, errors: string[], order?: Object, nextState: Object}} Cancel result.
   */
  function cancelPendingOrder(orderId, paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var orders =
      state.ledger && Array.isArray(state.ledger.orders)
        ? state.ledger.orders
        : [];
    var orderIndex = findOrderIndexById(orders, orderId);

    if (orderIndex === -1) {
      return {
        ok: false,
        errors: ["Pending order not found."],
        nextState: paperState
      };
    }

    if (orders[orderIndex].status !== "pending") {
      return {
        ok: false,
        errors: ["Only pending orders can be canceled."],
        nextState: paperState
      };
    }

    var nextState = clonePaperState(paperState);
    var canceledAt = createIsoTimestamp();
    var canceledOrder = nextState.ledger.orders[orderIndex];
    var reservedAmount =
      canceledOrder && typeof canceledOrder.reservedAmount === "number" && canceledOrder.reservedAmount > 0
        ? canceledOrder.reservedAmount
        : 0;

    canceledOrder.status = "canceled";
    canceledOrder.canceledAt = canceledAt;

    if (reservedAmount > 0) {
      nextState.account.availableCash += reservedAmount;
      nextState.account.reservedCash = Math.max(0, nextState.account.reservedCash - reservedAmount);
      nextState.ledger.cashEvents.push({
        type: "cash_released",
        orderId: canceledOrder.id,
        amount: reservedAmount,
        createdAt: canceledAt
      });
    }

    nextState.meta.updatedAt = canceledAt;

    return {
      ok: true,
      errors: [],
      order: cloneValue(canceledOrder),
      nextState: nextState
    };
  }

  /**
   * Fills one pending order, settles cash, and updates the aggregated long position.
   *
   * @param {string} orderId Order identifier to fill.
   * @param {number} fillPrice Execution price for the fill.
   * @param {Object} paperState Current participant paper state.
   * @returns {{ok: boolean, errors: string[], order?: Object, fill?: Object, nextState: Object}} Fill result.
   */
  function fillPendingOrder(orderId, fillPrice, paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var orders =
      state.ledger && Array.isArray(state.ledger.orders)
        ? state.ledger.orders
        : [];
    var orderIndex = findOrderIndexById(orders, orderId);
    var normalizedFillPrice = toPositiveNumberOrNull(fillPrice);
    var errors = [];

    if (orderIndex === -1) {
      return {
        ok: false,
        errors: ["Pending order not found."],
        nextState: paperState
      };
    }

    var pendingOrder = orders[orderIndex];
    var reservedAmount =
      pendingOrder && typeof pendingOrder.reservedAmount === "number"
        ? pendingOrder.reservedAmount
        : 0;
    var currentPosition = getPositionForSymbol(state, pendingOrder.symbol);
    var heldQuantity =
      currentPosition && typeof currentPosition.quantity === "number"
        ? currentPosition.quantity
        : 0;
    var grossAmount = pendingOrder && Number.isInteger(pendingOrder.quantity) && normalizedFillPrice
      ? pendingOrder.quantity * normalizedFillPrice
      : 0;

    if (pendingOrder.status !== "pending") {
      errors.push("Only pending orders can be filled.");
    }

    if (!normalizedFillPrice) {
      errors.push("Fill price must be a positive number.");
    }

    if (
      pendingOrder.side === "buy" &&
      pendingOrder.type === "limit" &&
      normalizedFillPrice &&
      (!pendingOrder.limitPrice || normalizedFillPrice > pendingOrder.limitPrice)
    ) {
      errors.push("Buy limit orders cannot fill above the limitPrice.");
    }

    if (pendingOrder.side === "buy" && !(reservedAmount > 0)) {
      errors.push("Pending buy orders require a positive reservedAmount before fill.");
    }

    if (pendingOrder.side === "buy" && grossAmount > reservedAmount) {
      errors.push("Fill cost cannot exceed the reservedAmount.");
    }

    if (
      pendingOrder.side === "sell" &&
      pendingOrder.type === "limit" &&
      normalizedFillPrice &&
      (!pendingOrder.limitPrice || normalizedFillPrice < pendingOrder.limitPrice)
    ) {
      errors.push("Sell limit orders cannot fill below the limitPrice.");
    }

    if (pendingOrder.side === "sell") {
      if (!currentPosition || heldQuantity <= 0) {
        errors.push("Sell fills require an existing long position.");
      } else if (pendingOrder.quantity > heldQuantity) {
        errors.push("Sell fill quantity cannot exceed the current held quantity.");
      }
    }

    if (errors.length > 0) {
      return {
        ok: false,
        errors: errors,
        nextState: paperState
      };
    }

    var nextState = clonePaperState(paperState);
    var filledAt = createIsoTimestamp();
    var filledOrder = nextState.ledger.orders[orderIndex];
    var fillId = createId("fill");
    var existingPosition = getPositionForSymbol(nextState, filledOrder.symbol);
    var fillRecord = {
      id: fillId,
      orderId: filledOrder.id,
      symbol: filledOrder.symbol,
      side: filledOrder.side,
      type: filledOrder.type,
      quantity: filledOrder.quantity,
      fillPrice: normalizedFillPrice,
      grossAmount: grossAmount,
      realizedPnl: 0,
      createdAt: filledAt
    };

    filledOrder.status = "filled";
    filledOrder.filledAt = filledAt;
    filledOrder.fillPrice = normalizedFillPrice;
    filledOrder.filledQuantity = filledOrder.quantity;
    filledOrder.fillId = fillId;

    if (filledOrder.side === "buy") {
      var refundAmount = reservedAmount - grossAmount;
      var nextQuantity = existingPosition ? existingPosition.quantity + filledOrder.quantity : filledOrder.quantity;
      var nextTotalCost = existingPosition ? existingPosition.totalCost + grossAmount : grossAmount;
      var nextAvgCost = nextTotalCost / nextQuantity;

      nextState.account.reservedCash = Math.max(0, nextState.account.reservedCash - reservedAmount);
      nextState.ledger.cashEvents.push({
        type: "cash_settled",
        orderId: filledOrder.id,
        amount: grossAmount,
        createdAt: filledAt
      });

      if (refundAmount > 0) {
        nextState.account.availableCash += refundAmount;
        nextState.ledger.cashEvents.push({
          type: "cash_released",
          orderId: filledOrder.id,
          amount: refundAmount,
          createdAt: filledAt
        });
      }

      nextState.positions[filledOrder.symbol] = buildPositionSnapshot({
        symbol: filledOrder.symbol,
        quantity: nextQuantity,
        totalCost: nextTotalCost,
        avgCost: nextAvgCost,
        openedAt: existingPosition ? existingPosition.openedAt : filledAt,
        updatedAt: filledAt,
        marketPrice: nextAvgCost
      });
    } else {
      var currentAvgCost =
        existingPosition && typeof existingPosition.avgCost === "number"
          ? existingPosition.avgCost
          : 0;
      var soldCostBasis = currentAvgCost * filledOrder.quantity;
      var currentTotalCost =
        existingPosition && typeof existingPosition.totalCost === "number"
          ? existingPosition.totalCost
          : currentAvgCost * heldQuantity;
      var remainingQuantity = heldQuantity - filledOrder.quantity;
      var remainingTotalCost = Math.max(0, currentTotalCost - soldCostBasis);
      var currentMarketPrice =
        existingPosition && toPositiveNumberOrNull(existingPosition.marketPrice)
          ? existingPosition.marketPrice
          : currentAvgCost;

      if (typeof nextState.account.realizedPnl !== "number") {
        nextState.account.realizedPnl = 0;
      }

      fillRecord.realizedPnl = (normalizedFillPrice - currentAvgCost) * filledOrder.quantity;
      nextState.account.availableCash += grossAmount;
      nextState.account.realizedPnl += fillRecord.realizedPnl;
      nextState.ledger.cashEvents.push({
        type: "cash_received",
        orderId: filledOrder.id,
        amount: grossAmount,
        createdAt: filledAt
      });

      if (remainingQuantity > 0) {
        nextState.positions[filledOrder.symbol] = buildPositionSnapshot({
          symbol: filledOrder.symbol,
          quantity: remainingQuantity,
          totalCost: remainingTotalCost,
          avgCost: currentAvgCost,
          openedAt: existingPosition && existingPosition.openedAt ? existingPosition.openedAt : filledAt,
          updatedAt: filledAt,
          marketPrice: currentMarketPrice,
          lastMarkedAt:
            existingPosition && existingPosition.lastMarkedAt
              ? existingPosition.lastMarkedAt
              : undefined
        });
      } else {
        delete nextState.positions[filledOrder.symbol];
      }
    }

    nextState.ledger.fills.push(fillRecord);
    nextState.meta.updatedAt = filledAt;

    return {
      ok: true,
      errors: [],
      order: cloneValue(filledOrder),
      fill: fillRecord,
      nextState: nextState
    };
  }

  /**
   * Returns all currently pending orders from the paper-state ledger.
   *
   * @param {Object} paperState Current participant paper state.
   * @returns {Object[]} A list of open pending orders.
   */
  function getOpenOrders(paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var orders =
      state.ledger && Array.isArray(state.ledger.orders)
        ? state.ledger.orders
        : [];

    return orders
      .filter(function (order) {
        return order && order.status === "pending";
      })
      .map(cloneValue);
  }

  /**
   * Returns a plain portfolio summary using stored cash and position valuation fields.
   *
   * @param {Object} paperState Current participant paper state.
   * @returns {Object} A read-only summary of cash, valuation, pnl, and counts.
   */
  function getPortfolioSummary(paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var account = state.account && typeof state.account === "object" ? state.account : {};
    var positions =
      state.positions && typeof state.positions === "object"
        ? Object.keys(state.positions).map(function (symbol) {
            return state.positions[symbol];
          })
        : [];
    var orders =
      state.ledger && Array.isArray(state.ledger.orders)
        ? state.ledger.orders
        : [];
    var fills =
      state.ledger && Array.isArray(state.ledger.fills)
        ? state.ledger.fills
        : [];
    var startingCash = toNonNegativeNumber(account.startingCash, DEFAULT_CONTEST_CONFIG.startingCash);
    var availableCash = toNonNegativeNumber(account.availableCash, startingCash);
    var reservedCash = toNonNegativeNumber(account.reservedCash, 0);
    var realizedPnl = typeof account.realizedPnl === "number" ? account.realizedPnl : 0;
    var costBasis = 0;
    var marketValue = 0;
    var unrealizedPnl = 0;

    positions.forEach(function (position) {
      var totalCost =
        position && typeof position.totalCost === "number"
          ? position.totalCost
          : 0;
      var currentMarketValue =
        position && typeof position.marketValue === "number"
          ? position.marketValue
          : totalCost;
      var currentUnrealizedPnl =
        position && typeof position.unrealizedPnl === "number"
          ? position.unrealizedPnl
          : 0;

      costBasis += totalCost;
      marketValue += currentMarketValue;
      unrealizedPnl += currentUnrealizedPnl;
    });

    return {
      startingCash: startingCash,
      availableCash: availableCash,
      reservedCash: reservedCash,
      cashTotal: availableCash + reservedCash,
      costBasis: costBasis,
      marketValue: marketValue,
      realizedPnl: realizedPnl,
      unrealizedPnl: unrealizedPnl,
      totalPnl: realizedPnl + unrealizedPnl,
      equity: availableCash + reservedCash + marketValue,
      positionsCount: positions.length,
      openOrdersCount: orders.filter(function (order) {
        return order && order.status === "pending";
      }).length,
      fillsCount: fills.length
    };
  }

  /**
   * Creates one plain valuation snapshot from the current paper-state summary.
   *
   * @param {Object} paperState Current participant paper state.
   * @param {Object} [overrides={}] Optional display metadata overrides.
   * @returns {Object} A read-only snapshot record.
   */
  function createValuationSnapshot(paperState, overrides) {
    var summary = getPortfolioSummary(paperState);
    var safeOverrides = overrides && typeof overrides === "object" ? overrides : {};

    return {
      id: createId("snapshot"),
      createdAt: toTrimmedString(safeOverrides.createdAt) || createIsoTimestamp(),
      label: toTrimmedString(safeOverrides.label),
      source: toTrimmedString(safeOverrides.source) || "manual",
      startingCash: summary.startingCash,
      cashTotal: summary.cashTotal,
      marketValue: summary.marketValue,
      realizedPnl: summary.realizedPnl,
      unrealizedPnl: summary.unrealizedPnl,
      totalPnl: summary.totalPnl,
      equity: summary.equity,
      positionsCount: summary.positionsCount,
      openOrdersCount: summary.openOrdersCount,
      fillsCount: summary.fillsCount
    };
  }

  /**
   * Appends one manual valuation snapshot to cloned state without changing trading rules.
   *
   * @param {Object} paperState Current participant paper state.
   * @param {Object} [overrides={}] Optional snapshot metadata overrides.
   * @returns {{ok: boolean, errors: string[], snapshot: Object, nextState: Object}} Snapshot result.
   */
  function recordValuationSnapshot(paperState, overrides) {
    var nextState = clonePaperState(paperState);
    var snapshot = createValuationSnapshot(paperState, overrides);

    nextState.snapshots.push(snapshot);
    nextState.meta.updatedAt = snapshot.createdAt;

    return {
      ok: true,
      errors: [],
      snapshot: snapshot,
      nextState: nextState
    };
  }

  /**
   * Returns the recorded equity timeline in snapshot insertion order.
   *
   * @param {Object} paperState Current participant paper state.
   * @returns {Object[]} A simple array view of recorded equity snapshots.
   */
  function getEquityTimeline(paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var snapshots = Array.isArray(state.snapshots) ? state.snapshots : [];

    return snapshots.map(function (snapshot) {
      var item = snapshot && typeof snapshot === "object" ? snapshot : {};

      return {
        id: toTrimmedString(item.id),
        createdAt: toTrimmedString(item.createdAt),
        label: toTrimmedString(item.label),
        source: toTrimmedString(item.source),
        equity: typeof item.equity === "number" ? item.equity : 0,
        totalPnl: typeof item.totalPnl === "number" ? item.totalPnl : 0,
        marketValue: typeof item.marketValue === "number" ? item.marketValue : 0,
        cashTotal: typeof item.cashTotal === "number" ? item.cashTotal : 0
      };
    });
  }

  /**
   * Sets the benchmark baseline price on cloned state without mutating the input state.
   *
   * @param {number} price Benchmark baseline price.
   * @param {Object} paperState Current participant paper state.
   * @param {Object} [overrides={}] Optional symbol, source, or createdAt overrides.
   * @returns {{ok: boolean, errors: string[], nextState: Object, benchmark?: Object}} Baseline result.
   */
  function setBenchmarkBaseline(price, paperState, overrides) {
    var normalizedPrice = toPositiveNumberOrNull(price);
    var safeOverrides = overrides && typeof overrides === "object" ? overrides : {};

    if (!normalizedPrice) {
      return {
        ok: false,
        errors: ["Benchmark baseline price must be a positive number."],
        nextState: paperState
      };
    }

    var nextState = clonePaperState(paperState);
    var benchmarkAt = toTrimmedString(safeOverrides.createdAt) || createIsoTimestamp();
    var benchmarkSymbol =
      toUpperSymbol(safeOverrides.symbol) ||
      nextState.benchmark.symbol ||
      DEFAULT_CONTEST_CONFIG.benchmarkSymbol;

    nextState.benchmark.symbol = benchmarkSymbol;
    nextState.benchmark.baselinePrice = normalizedPrice;
    nextState.benchmark.baselineAt = benchmarkAt;
    nextState.benchmark.source = toTrimmedString(safeOverrides.source) || "manual";

    if (nextState.benchmark.currentPrice === null) {
      nextState.benchmark.currentPrice = normalizedPrice;
      nextState.benchmark.currentAt = benchmarkAt;
    }

    nextState.meta.updatedAt = benchmarkAt;

    return {
      ok: true,
      errors: [],
      nextState: nextState,
      benchmark: cloneValue(nextState.benchmark)
    };
  }

  /**
   * Marks the current benchmark price on cloned state without changing trading rules.
   *
   * @param {number} price Benchmark current price.
   * @param {Object} paperState Current participant paper state.
   * @param {Object} [overrides={}] Optional symbol, source, or createdAt overrides.
   * @returns {{ok: boolean, errors: string[], nextState: Object, benchmark?: Object}} Benchmark mark result.
   */
  function markBenchmarkPrice(price, paperState, overrides) {
    var normalizedPrice = toPositiveNumberOrNull(price);
    var safeOverrides = overrides && typeof overrides === "object" ? overrides : {};

    if (!normalizedPrice) {
      return {
        ok: false,
        errors: ["Benchmark current price must be a positive number."],
        nextState: paperState
      };
    }

    var nextState = clonePaperState(paperState);
    var benchmarkAt = toTrimmedString(safeOverrides.createdAt) || createIsoTimestamp();
    var benchmarkSymbol =
      toUpperSymbol(safeOverrides.symbol) ||
      nextState.benchmark.symbol ||
      DEFAULT_CONTEST_CONFIG.benchmarkSymbol;

    nextState.benchmark.symbol = benchmarkSymbol;
    nextState.benchmark.currentPrice = normalizedPrice;
    nextState.benchmark.currentAt = benchmarkAt;
    nextState.benchmark.source =
      toTrimmedString(safeOverrides.source) ||
      nextState.benchmark.source ||
      "manual";

    if (nextState.benchmark.baselinePrice === null) {
      nextState.benchmark.baselinePrice = normalizedPrice;
      nextState.benchmark.baselineAt = benchmarkAt;
    }

    nextState.meta.updatedAt = benchmarkAt;

    return {
      ok: true,
      errors: [],
      nextState: nextState,
      benchmark: cloneValue(nextState.benchmark)
    };
  }

  /**
   * Returns a plain benchmark-relative contest summary using current equity and benchmark state.
   *
   * @param {Object} paperState Current participant paper state.
   * @returns {Object} A read-only return summary for the portfolio and benchmark.
   */
  function getContestReturnSummary(paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var portfolioSummary = getPortfolioSummary(state);
    var benchmark = createBenchmarkState(
      state.benchmark,
      DEFAULT_CONTEST_CONFIG.benchmarkSymbol
    );
    var startingCash = portfolioSummary.startingCash;
    var equity = portfolioSummary.equity;
    var totalPnl = portfolioSummary.totalPnl;
    var portfolioReturnPct =
      startingCash > 0 ? ((equity - startingCash) / startingCash) * 100 : 0;
    var benchmarkBaselinePrice = benchmark.baselinePrice;
    var benchmarkCurrentPrice = benchmark.currentPrice;
    var benchmarkReturnPct = null;
    var excessReturnPct = null;
    var benchmarkValueOfStartingCash = null;

    if (benchmarkBaselinePrice && benchmarkCurrentPrice) {
      benchmarkReturnPct =
        ((benchmarkCurrentPrice - benchmarkBaselinePrice) / benchmarkBaselinePrice) * 100;
      excessReturnPct = portfolioReturnPct - benchmarkReturnPct;
      benchmarkValueOfStartingCash =
        startingCash * (1 + benchmarkReturnPct / 100);
    }

    return {
      benchmarkSymbol: benchmark.symbol,
      benchmarkBaselinePrice: benchmarkBaselinePrice,
      benchmarkCurrentPrice: benchmarkCurrentPrice,
      startingCash: startingCash,
      equity: equity,
      totalPnl: totalPnl,
      portfolioReturnPct: portfolioReturnPct,
      benchmarkReturnPct: benchmarkReturnPct,
      excessReturnPct: excessReturnPct,
      benchmarkValueOfStartingCash: benchmarkValueOfStartingCash
    };
  }

  /**
   * Returns raw order and fill activity totals from the current paper-state ledger.
   *
   * @param {Object} paperState Current participant paper state.
   * @returns {Object} A read-only trade stats summary.
   */
  function getTradeStats(paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var orders =
      state.ledger && Array.isArray(state.ledger.orders)
        ? state.ledger.orders
        : [];
    var fills =
      state.ledger && Array.isArray(state.ledger.fills)
        ? state.ledger.fills
        : [];
    var account = state.account && typeof state.account === "object" ? state.account : {};
    var startingCash =
      typeof account.startingCash === "number" ? account.startingCash : 0;
    var buyFillsCount = 0;
    var sellFillsCount = 0;
    var grossBuyVolume = 0;
    var grossSellVolume = 0;

    fills.forEach(function (fill) {
      var grossAmount =
        fill && typeof fill.grossAmount === "number" ? fill.grossAmount : 0;

      if (fill && fill.side === "buy") {
        buyFillsCount += 1;
        grossBuyVolume += grossAmount;
      }

      if (fill && fill.side === "sell") {
        sellFillsCount += 1;
        grossSellVolume += grossAmount;
      }
    });

    var grossTurnover = grossBuyVolume + grossSellVolume;

    return {
      submittedOrdersCount: orders.length,
      openOrdersCount: orders.filter(function (order) {
        return order && order.status === "pending";
      }).length,
      filledOrdersCount: orders.filter(function (order) {
        return order && order.status === "filled";
      }).length,
      canceledOrdersCount: orders.filter(function (order) {
        return order && order.status === "canceled";
      }).length,
      buyFillsCount: buyFillsCount,
      sellFillsCount: sellFillsCount,
      grossBuyVolume: grossBuyVolume,
      grossSellVolume: grossSellVolume,
      grossTurnover: grossTurnover,
      turnoverPctOfStartingCash:
        startingCash > 0 ? (grossTurnover / startingCash) * 100 : 0
    };
  }

  /**
   * Returns current open-position weights using market value when it exists.
   *
   * @param {Object} paperState Current participant paper state.
   * @returns {Object[]} A descending list of position weights.
   */
  function getPositionWeights(paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var positions =
      state.positions && typeof state.positions === "object"
        ? Object.keys(state.positions).map(function (symbol) {
            return state.positions[symbol];
          })
        : [];
    var equity = getPortfolioSummary(state).equity;

    return positions
      .map(function (position) {
        var basisValue =
          position && typeof position.marketValue === "number"
            ? position.marketValue
            : position && typeof position.totalCost === "number"
              ? position.totalCost
              : 0;

        return {
          symbol: position && position.symbol ? position.symbol : "",
          quantity:
            position && typeof position.quantity === "number"
              ? position.quantity
              : 0,
          basisValue: basisValue,
          weightPct: equity > 0 ? (basisValue / equity) * 100 : 0
        };
      })
      .sort(function (left, right) {
        return right.weightPct - left.weightPct;
      });
  }

  /**
   * Returns raw turnover, concentration, and exposure metrics without scoring.
   *
   * @param {Object} paperState Current participant paper state.
   * @returns {Object} A read-only discipline metrics summary.
   */
  function getDisciplineMetrics(paperState) {
    var portfolioSummary = getPortfolioSummary(paperState);
    var tradeStats = getTradeStats(paperState);
    var positionWeights = getPositionWeights(paperState);
    var equity = portfolioSummary.equity;
    var largestPosition = positionWeights.length ? positionWeights[0] : null;

    return {
      grossTurnover: tradeStats.grossTurnover,
      turnoverPctOfStartingCash: tradeStats.turnoverPctOfStartingCash,
      maxPositionWeightPct: largestPosition ? largestPosition.weightPct : 0,
      maxPositionSymbol: largestPosition ? largestPosition.symbol : null,
      investedPct: equity > 0 ? (portfolioSummary.marketValue / equity) * 100 : 0,
      cashPct: equity > 0 ? (portfolioSummary.cashTotal / equity) * 100 : 0,
      positionsCount: portfolioSummary.positionsCount,
      filledTradeCount: tradeStats.buyFillsCount + tradeStats.sellFillsCount
    };
  }

  /**
   * Returns a read-only preview of one possible score breakdown without mutating state.
   *
   * @param {Object} paperState Current participant paper state.
   * @param {Object} [overrides={}] Optional score-preview config overrides.
   * @returns {Object} A read-only score preview summary.
   */
  function getScorePreview(paperState, overrides) {
    var safeOverrides = overrides && typeof overrides === "object" ? overrides : {};
    var contestReturnSummary = getContestReturnSummary(paperState);
    var disciplineMetrics = getDisciplineMetrics(paperState);
    var config = {
      performanceWeight:
        typeof safeOverrides.performanceWeight === "number" &&
        Number.isFinite(safeOverrides.performanceWeight)
          ? safeOverrides.performanceWeight
          : 0.8,
      disciplineWeight:
        typeof safeOverrides.disciplineWeight === "number" &&
        Number.isFinite(safeOverrides.disciplineWeight)
          ? safeOverrides.disciplineWeight
          : 0.2,
      rawReturnWeight:
        typeof safeOverrides.rawReturnWeight === "number" &&
        Number.isFinite(safeOverrides.rawReturnWeight)
          ? safeOverrides.rawReturnWeight
          : 0.5,
      excessReturnWeight:
        typeof safeOverrides.excessReturnWeight === "number" &&
        Number.isFinite(safeOverrides.excessReturnWeight)
          ? safeOverrides.excessReturnWeight
          : 0.5,
      performanceScale:
        typeof safeOverrides.performanceScale === "number" &&
        Number.isFinite(safeOverrides.performanceScale)
          ? safeOverrides.performanceScale
          : 5,
      turnoverPenaltyRate:
        typeof safeOverrides.turnoverPenaltyRate === "number" &&
        Number.isFinite(safeOverrides.turnoverPenaltyRate)
          ? safeOverrides.turnoverPenaltyRate
          : 0.5,
      concentrationSoftLimitPct:
        typeof safeOverrides.concentrationSoftLimitPct === "number" &&
        Number.isFinite(safeOverrides.concentrationSoftLimitPct)
          ? safeOverrides.concentrationSoftLimitPct
          : 35,
      concentrationPenaltyRate:
        typeof safeOverrides.concentrationPenaltyRate === "number" &&
        Number.isFinite(safeOverrides.concentrationPenaltyRate)
          ? safeOverrides.concentrationPenaltyRate
          : 1
    };
    var portfolioReturnPct =
      contestReturnSummary && typeof contestReturnSummary.portfolioReturnPct === "number"
        ? contestReturnSummary.portfolioReturnPct
        : 0;
    var benchmarkReturnPct =
      contestReturnSummary && typeof contestReturnSummary.benchmarkReturnPct === "number"
        ? contestReturnSummary.benchmarkReturnPct
        : null;
    var excessReturnPct =
      contestReturnSummary && typeof contestReturnSummary.excessReturnPct === "number"
        ? contestReturnSummary.excessReturnPct
        : null;
    var turnoverPctOfStartingCash =
      disciplineMetrics && typeof disciplineMetrics.turnoverPctOfStartingCash === "number"
        ? disciplineMetrics.turnoverPctOfStartingCash
        : 0;
    var maxPositionWeightPct =
      disciplineMetrics && typeof disciplineMetrics.maxPositionWeightPct === "number"
        ? disciplineMetrics.maxPositionWeightPct
        : 0;
    var performanceInputPct =
      typeof excessReturnPct === "number"
        ? (portfolioReturnPct * config.rawReturnWeight) +
          (excessReturnPct * config.excessReturnWeight)
        : portfolioReturnPct;
    var performanceScore = clamp(
      50 + (performanceInputPct * config.performanceScale),
      0,
      100
    );
    var turnoverPenalty =
      turnoverPctOfStartingCash * config.turnoverPenaltyRate;
    var concentrationPenalty =
      Math.max(
        0,
        maxPositionWeightPct - config.concentrationSoftLimitPct
      ) * config.concentrationPenaltyRate;
    var disciplineScore = clamp(
      100 - turnoverPenalty - concentrationPenalty,
      0,
      100
    );
    var weightedPerformanceScore =
      performanceScore * config.performanceWeight;
    var weightedDisciplineScore =
      disciplineScore * config.disciplineWeight;
    var totalPreviewScore =
      weightedPerformanceScore + weightedDisciplineScore;

    return {
      config: config,
      inputs: {
        portfolioReturnPct: portfolioReturnPct,
        benchmarkReturnPct: benchmarkReturnPct,
        excessReturnPct: excessReturnPct,
        turnoverPctOfStartingCash: turnoverPctOfStartingCash,
        maxPositionWeightPct: maxPositionWeightPct
      },
      performance: {
        performanceInputPct: performanceInputPct,
        performanceScore: performanceScore
      },
      discipline: {
        turnoverPenalty: turnoverPenalty,
        concentrationPenalty: concentrationPenalty,
        disciplineScore: disciplineScore
      },
      weighted: {
        weightedPerformanceScore: weightedPerformanceScore,
        weightedDisciplineScore: weightedDisciplineScore
      },
      totalPreviewScore: totalPreviewScore
    };
  }

  /**
   * Creates one plain score snapshot from the current preview and summary helpers.
   *
   * @param {Object} paperState Current participant paper state.
   * @param {Object} [overrides={}] Optional snapshot metadata overrides.
   * @returns {Object} A read-only score snapshot record.
   */
  function createScoreSnapshot(paperState, overrides) {
    var safeOverrides = overrides && typeof overrides === "object" ? overrides : {};
    var scorePreview = getScorePreview(paperState);
    var contestReturnSummary = getContestReturnSummary(paperState);
    var disciplineMetrics = getDisciplineMetrics(paperState);
    var portfolioSummary = getPortfolioSummary(paperState);

    return {
      id: createId("score_snapshot"),
      createdAt: toTrimmedString(safeOverrides.createdAt) || createIsoTimestamp(),
      label: toTrimmedString(safeOverrides.label),
      source: toTrimmedString(safeOverrides.source) || "manual",
      config: cloneValue(scorePreview.config),
      totalScore: scorePreview.totalPreviewScore,
      performanceScore: scorePreview.performance.performanceScore,
      disciplineScore: scorePreview.discipline.disciplineScore,
      portfolioReturnPct: contestReturnSummary.portfolioReturnPct,
      benchmarkReturnPct: contestReturnSummary.benchmarkReturnPct,
      excessReturnPct: contestReturnSummary.excessReturnPct,
      turnoverPctOfStartingCash: disciplineMetrics.turnoverPctOfStartingCash,
      maxPositionWeightPct: disciplineMetrics.maxPositionWeightPct,
      equity: portfolioSummary.equity,
      totalPnl: portfolioSummary.totalPnl
    };
  }

  /**
   * Appends one manual score snapshot to cloned state without adding ranking behavior.
   *
   * @param {Object} paperState Current participant paper state.
   * @param {Object} [overrides={}] Optional snapshot metadata overrides.
   * @returns {{ok: boolean, errors: string[], snapshot: Object, nextState: Object}} Snapshot result.
   */
  function recordScoreSnapshot(paperState, overrides) {
    var nextState = clonePaperState(paperState);
    var snapshot = createScoreSnapshot(paperState, overrides);

    nextState.scoreSnapshots.push(snapshot);
    nextState.meta.updatedAt = snapshot.createdAt;

    return {
      ok: true,
      errors: [],
      snapshot: snapshot,
      nextState: nextState
    };
  }

  /**
   * Returns latest, previous, and best official score values from recorded snapshots.
   *
   * @param {Object} paperState Current participant paper state.
   * @returns {Object} A read-only official score status summary.
   */
  function getOfficialScoreStatus(paperState) {
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var scoreSnapshots = Array.isArray(state.scoreSnapshots) ? state.scoreSnapshots : [];
    var recordedScoresCount = scoreSnapshots.length;
    var latestSnapshot =
      recordedScoresCount > 0 ? scoreSnapshots[recordedScoresCount - 1] : null;
    var previousSnapshot =
      recordedScoresCount > 1 ? scoreSnapshots[recordedScoresCount - 2] : null;
    var bestSnapshot = null;
    var bestScore = null;
    var previewScore = getScorePreview(paperState).totalPreviewScore;

    scoreSnapshots.forEach(function (snapshot) {
      var totalScore =
        snapshot && typeof snapshot.totalScore === "number"
          ? snapshot.totalScore
          : null;

      if (totalScore === null) {
        return;
      }

      if (bestScore === null || totalScore > bestScore) {
        bestScore = totalScore;
        bestSnapshot = snapshot;
      }
    });

    var latestOfficialScore =
      latestSnapshot && typeof latestSnapshot.totalScore === "number"
        ? latestSnapshot.totalScore
        : null;
    var previousOfficialScore =
      previousSnapshot && typeof previousSnapshot.totalScore === "number"
        ? previousSnapshot.totalScore
        : null;
    var bestOfficialScore =
      bestSnapshot && typeof bestSnapshot.totalScore === "number"
        ? bestSnapshot.totalScore
        : null;

    return {
      hasOfficialScore: recordedScoresCount > 0,
      recordedScoresCount: recordedScoresCount,
      latestSnapshot: latestSnapshot ? cloneValue(latestSnapshot) : null,
      previousSnapshot: previousSnapshot ? cloneValue(previousSnapshot) : null,
      bestSnapshot: bestSnapshot ? cloneValue(bestSnapshot) : null,
      latestOfficialScore: latestOfficialScore,
      previousOfficialScore: previousOfficialScore,
      bestOfficialScore: bestOfficialScore,
      scoreDeltaFromPrevious:
        latestOfficialScore !== null && previousOfficialScore !== null
          ? latestOfficialScore - previousOfficialScore
          : null,
      previewScore: previewScore,
      previewVsLatestGap:
        latestOfficialScore !== null ? previewScore - latestOfficialScore : null
    };
  }

  /**
   * Applies manual mark-to-market prices to existing open positions without mutating input state.
   *
   * @param {Object} priceMap Symbol-to-price map such as { SPY: 530 }.
   * @param {Object} paperState Current participant paper state.
   * @returns {{ok: boolean, errors: string[], nextState: Object, summary?: Object}} Mark result.
   */
  function markPortfolioToMarket(priceMap, paperState) {
    var sourcePriceMap = priceMap && typeof priceMap === "object" ? priceMap : {};
    var state = paperState && typeof paperState === "object" ? paperState : {};
    var providedSymbols = Object.keys(sourcePriceMap);
    var normalizedPriceMap = {};
    var errors = [];

    providedSymbols.forEach(function (symbol) {
      var normalizedSymbol = toUpperSymbol(symbol);
      var normalizedPrice = toPositiveNumberOrNull(sourcePriceMap[symbol]);

      if (!normalizedPrice) {
        errors.push("Mark price for " + (normalizedSymbol || toTrimmedString(symbol) || "unknown symbol") + " must be a positive number.");
        return;
      }

      if (normalizedSymbol) {
        normalizedPriceMap[normalizedSymbol] = normalizedPrice;
      }
    });

    if (errors.length > 0) {
      return {
        ok: false,
        errors: errors,
        nextState: paperState
      };
    }

    var nextState = clonePaperState(state);
    var markedAt = createIsoTimestamp();

    Object.keys(normalizedPriceMap).forEach(function (symbol) {
      var existingPosition = getPositionForSymbol(nextState, symbol);

      if (!existingPosition) {
        return;
      }

      nextState.positions[symbol] = buildPositionSnapshot({
        symbol: existingPosition.symbol,
        quantity: existingPosition.quantity,
        totalCost: existingPosition.totalCost,
        avgCost: existingPosition.avgCost,
        openedAt: existingPosition.openedAt,
        updatedAt: markedAt,
        marketPrice: normalizedPriceMap[symbol],
        lastMarkedAt: markedAt
      });
    });

    nextState.meta.updatedAt = markedAt;

    return {
      ok: true,
      errors: [],
      nextState: nextState,
      summary: getPortfolioSummary(nextState)
    };
  }

  window.YomamaPaperEngine = {
    ENGINE_VERSION: ENGINE_VERSION,
    createContestConfig: createContestConfig,
    createParticipantAccount: createParticipantAccount,
    createPaperState: createPaperState,
    createOrderDraft: createOrderDraft,
    validateDraftOrder: validateDraftOrder,
    estimateOrderReservation: estimateOrderReservation,
    submitDraftOrder: submitDraftOrder,
    cancelPendingOrder: cancelPendingOrder,
    fillPendingOrder: fillPendingOrder,
    getOpenOrders: getOpenOrders,
    getPortfolioSummary: getPortfolioSummary,
    createValuationSnapshot: createValuationSnapshot,
    recordValuationSnapshot: recordValuationSnapshot,
    getEquityTimeline: getEquityTimeline,
    setBenchmarkBaseline: setBenchmarkBaseline,
    markBenchmarkPrice: markBenchmarkPrice,
    getContestReturnSummary: getContestReturnSummary,
    getTradeStats: getTradeStats,
    getPositionWeights: getPositionWeights,
    getDisciplineMetrics: getDisciplineMetrics,
    getScorePreview: getScorePreview,
    createScoreSnapshot: createScoreSnapshot,
    recordScoreSnapshot: recordScoreSnapshot,
    getOfficialScoreStatus: getOfficialScoreStatus,
    markPortfolioToMarket: markPortfolioToMarket
  };
}());
