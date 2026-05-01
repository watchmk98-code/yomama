(() => {
  const engine = window.YomamaPaperEngine;

  if (!engine) return;

  const summaryStrip = document.getElementById('paper-summary-strip');
  const orderForm = document.getElementById('paper-order-form');
  const resetButton = document.getElementById('paper-reset-state');
  const pendingOrdersBody = document.getElementById('paper-pending-orders-body');
  const positionsBody = document.getElementById('paper-positions-body');
  const cashEventsBody = document.getElementById('paper-cash-events-body');
  const lastResultBox = document.getElementById('paper-last-result');
  const lastErrorsBox = document.getElementById('paper-last-errors');
  const rawStateBox = document.getElementById('paper-raw-state');

  if (
    !summaryStrip ||
    !orderForm ||
    !resetButton ||
    !pendingOrdersBody ||
    !positionsBody ||
    !cashEventsBody ||
    !lastResultBox ||
    !lastErrorsBox ||
    !rawStateBox
  ) {
    return;
  }

  let contestConfig;
  let paperState;
  let lastActionResult = null;
  let lastErrors = [];

  const createFreshDemo = () => {
    contestConfig = engine.createContestConfig();
    paperState = engine.createPaperState({
      contestId: 'contest_about_paper',
      participantId: 'participant_about_paper',
      alias: 'YOMAMA Paper Trader',
    });
  };

  const formatMoney = (value) => {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) return '—';
    return `$${numericValue.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  };

  const escapeHtml = (value) => String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  const readNumber = (value) => {
    if (value === '' || value === null || value === undefined) return undefined;
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : undefined;
  };

  const applyResult = (result) => {
    lastActionResult = result;
    lastErrors = Array.isArray(result?.errors) ? result.errors : [];

    if (result?.ok && result.nextState) {
      paperState = result.nextState;
    }

    render();
  };

  const render = () => {
    const openOrders = engine.getOpenOrders(paperState);
    const fills = Array.isArray(paperState.ledger?.fills) ? paperState.ledger.fills : [];
    const positions = paperState.positions && typeof paperState.positions === 'object'
      ? Object.values(paperState.positions)
      : [];
    const cashEvents = Array.isArray(paperState.ledger?.cashEvents) ? paperState.ledger.cashEvents : [];

    summaryStrip.innerHTML = [
      { label: 'Available Cash', value: formatMoney(paperState.account.availableCash) },
      { label: 'Reserved Cash', value: formatMoney(paperState.account.reservedCash) },
      { label: 'Open Orders', value: String(openOrders.length) },
      { label: 'Fills', value: String(fills.length) },
      { label: 'Positions', value: String(positions.length) },
    ].map((item) => [
      '<article class="paper-summary-card">',
      `<div class="paper-summary-label">${escapeHtml(item.label)}</div>`,
      `<div class="paper-summary-value">${escapeHtml(item.value)}</div>`,
      '</article>',
    ].join('')).join('');

    pendingOrdersBody.innerHTML = openOrders.length
      ? openOrders.map((order) => {
        const defaultFillPrice = order.type === 'limit' && order.limitPrice
          ? order.limitPrice
          : order.referencePrice || '';

        return [
          '<tr>',
          `<td>${escapeHtml(order.id)}</td>`,
          `<td>${escapeHtml(order.symbol)}</td>`,
          `<td>${escapeHtml(order.type)}</td>`,
          `<td>${escapeHtml(String(order.quantity))}</td>`,
          `<td>${escapeHtml(formatMoney(order.reservedAmount || 0))}</td>`,
          `<td>${escapeHtml(order.status)}</td>`,
          '<td>',
          `<div class="paper-action-cell">`,
          `<input type="number" min="0.01" step="0.01" data-fill-input="${escapeHtml(order.id)}" value="${escapeHtml(String(defaultFillPrice))}" />`,
          `<button class="bld-btn alt" type="button" data-action="fill" data-order-id="${escapeHtml(order.id)}">Fill</button>`,
          `<button class="bld-btn alt" type="button" data-action="cancel" data-order-id="${escapeHtml(order.id)}">Cancel</button>`,
          '</div>',
          '</td>',
          '</tr>',
        ].join('');
      }).join('')
      : '<tr><td colspan="7" class="muted">No pending orders yet.</td></tr>';

    positionsBody.innerHTML = positions.length
      ? positions.map((position) => [
        '<tr>',
        `<td>${escapeHtml(position.symbol)}</td>`,
        `<td>${escapeHtml(String(position.quantity))}</td>`,
        `<td>${escapeHtml(formatMoney(position.avgCost))}</td>`,
        `<td>${escapeHtml(formatMoney(position.totalCost))}</td>`,
        '</tr>',
      ].join('')).join('')
      : '<tr><td colspan="4" class="muted">No positions yet.</td></tr>';

    cashEventsBody.innerHTML = cashEvents.length
      ? cashEvents.map((cashEvent) => [
        '<tr>',
        `<td>${escapeHtml(cashEvent.type)}</td>`,
        `<td>${escapeHtml(cashEvent.orderId || '—')}</td>`,
        `<td>${escapeHtml(formatMoney(cashEvent.amount))}</td>`,
        `<td>${escapeHtml(cashEvent.createdAt)}</td>`,
        '</tr>',
      ].join('')).join('')
      : '<tr><td colspan="4" class="muted">No cash events yet.</td></tr>';

    lastResultBox.textContent = lastActionResult
      ? JSON.stringify(lastActionResult, null, 2)
      : 'No actions yet.';

    if (lastErrors.length) {
      lastErrorsBox.innerHTML = `<ul class="paper-error-list">${lastErrors.map((message) => `<li>${escapeHtml(message)}</li>`).join('')}</ul>`;
    } else {
      lastErrorsBox.innerHTML = '<span class="paper-status-ok">No errors.</span>';
    }

    rawStateBox.textContent = JSON.stringify(paperState, null, 2);
  };

  orderForm.addEventListener('submit', (event) => {
    event.preventDefault();

    const draft = engine.createOrderDraft({
      symbol: document.getElementById('paper-order-symbol')?.value,
      side: 'buy',
      type: document.getElementById('paper-order-type')?.value,
      quantity: readNumber(document.getElementById('paper-order-quantity')?.value),
      referencePrice: readNumber(document.getElementById('paper-order-reference-price')?.value),
      limitPrice: readNumber(document.getElementById('paper-order-limit-price')?.value),
      session: document.getElementById('paper-order-session')?.value,
    });

    applyResult(engine.submitDraftOrder(draft, contestConfig, paperState));
  });

  pendingOrdersBody.addEventListener('click', (event) => {
    const actionButton = event.target.closest('[data-action]');
    if (!actionButton) return;

    const orderId = actionButton.getAttribute('data-order-id');
    if (!orderId) return;

    if (actionButton.getAttribute('data-action') === 'cancel') {
      applyResult(engine.cancelPendingOrder(orderId, paperState));
      return;
    }

    if (actionButton.getAttribute('data-action') === 'fill') {
      const fillInput = pendingOrdersBody.querySelector(`[data-fill-input="${orderId}"]`);
      const fillPrice = fillInput ? readNumber(fillInput.value) : undefined;
      applyResult(engine.fillPendingOrder(orderId, fillPrice, paperState));
    }
  });

  resetButton.addEventListener('click', () => {
    createFreshDemo();
    lastActionResult = null;
    lastErrors = [];
    render();
  });

  createFreshDemo();
  render();
})();
