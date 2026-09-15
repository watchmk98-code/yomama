/* Alpaca supplies all price data. TradingView Lightweight Charts supplies the
 * drawing/zoom/crosshair interactions; no external widget or trading API runs. */
(function () {
  'use strict';
  var mounted = new WeakMap();
  var intervals = { '1D': '1m', '1W': '30m', '1M': '1h', '3M': '4h', '1Y': '1D', '5Y': '1W' };
  var money = function (value) { return '$' + value.toFixed(2); };
  function exchangeTime(time, options) {
    return new Date(time * 1000).toLocaleString('en-US', Object.assign({ timeZone: 'America/New_York' }, options));
  }
  function status(state, kind, message) {
    state.host.dataset.status = kind;
    state.message.textContent = message || '';
    state.message.hidden = !message;
    state.host.setAttribute('aria-busy', String(kind === 'loading'));
  }
  function create(host) {
    var mount = document.createElement('div');
    mount.className = 'port-chart-canvas';
    var message = document.createElement('p');
    message.id = 'port-chart-message';
    message.className = 'port-chart-message';
    message.setAttribute('role', 'status');
    var tooltip = document.createElement('div');
    tooltip.className = 'port-chart-tooltip port-market-tooltip';
    tooltip.hidden = true;
    host.replaceChildren(mount, message, tooltip);
    var state = { host: host, message: message, tooltip: tooltip, rows: [], generation: 0, busy: false, requestedAt: null };
    if (!window.LightweightCharts) {
      status(state, 'unavailable', 'Chart could not load. Reload the page to try again.');
      return state;
    }
    var style = getComputedStyle(host);
    state.amber = style.getPropertyValue('--amber').trim() || '#ffb000';
    state.green = style.getPropertyValue('--green').trim() || '#16b86a';
    state.red = style.getPropertyValue('--red').trim() || '#c63939';
    state.chart = LightweightCharts.createChart(mount, {
      autoSize: true, width: host.clientWidth, height: host.clientHeight,
      layout: { background: { type: 'solid', color: '#000000' }, textColor: '#8a8f9f', fontFamily: 'VT323, monospace', fontSize: 14, attributionLogo: true },
      grid: { vertLines: { color: 'rgba(255,176,0,0.14)' }, horzLines: { color: 'rgba(255,176,0,0.22)' } },
      rightPriceScale: { borderColor: 'rgba(255,176,0,0.26)', scaleMargins: { top: .15, bottom: .12 } },
      timeScale: { borderColor: 'rgba(255,176,0,0.26)', timeVisible: true, secondsVisible: false,
        tickMarkFormatter: function (time, type) {
          return exchangeTime(time, type === 0 ? { year: 'numeric' } : type === 1 ? { month: 'short' } :
            type === 2 ? { month: 'short', day: 'numeric' } : { hour: '2-digit', minute: '2-digit', hour12: false });
        } },
      localization: { priceFormatter: money, timeFormatter: function (time) {
        return exchangeTime(time, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) + ' ET';
      } },
      crosshair: { mode: 0, vertLine: { color: 'rgba(255,176,0,.65)', labelBackgroundColor: '#34302a' },
        horzLine: { color: 'rgba(255,176,0,.65)', labelBackgroundColor: '#34302a' } },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true }
    });
    state.chart.subscribeCrosshairMove(function (event) {
      var row = state.series && event.seriesData.get(state.series);
      if (!row || !event.point || event.point.x < 0 || event.point.y < 0) { tooltip.hidden = true; return; }
      tooltip.textContent = state.type === 'candles' || state.type === 'bars'
        ? 'O ' + money(row.open) + '  H ' + money(row.high) + '  L ' + money(row.low) + '  C ' + money(row.close)
        : money(row.value);
      tooltip.hidden = false;
      tooltip.style.left = '8px'; tooltip.style.top = '8px';
    });
    return state;
  }
  function seriesData(state) {
    return state.rows.map(function (row) {
      return state.type === 'candles' || state.type === 'bars'
        ? { time: row.time, open: row.open, high: row.high, low: row.low, close: row.close }
        : { time: row.time, value: row.close };
    });
  }
  function setType(state, type) {
    if (state.type === type) return;
    var view = state.chart.timeScale().getVisibleLogicalRange();
    if (state.series) state.chart.removeSeries(state.series);
    state.type = type;
    state.host.dataset.chartType = type;
    state.tooltip.hidden = true;
    var definition = { area: LightweightCharts.AreaSeries, line: LightweightCharts.LineSeries,
      candles: LightweightCharts.CandlestickSeries, bars: LightweightCharts.BarSeries }[type];
    state.series = state.chart.addSeries(definition, {
      lineColor: state.amber, color: state.amber, lineWidth: 2,
      topColor: 'rgba(255,176,0,.35)', bottomColor: 'rgba(255,176,0,.02)',
      upColor: state.green, downColor: state.red, borderUpColor: state.green, borderDownColor: state.red,
      wickUpColor: state.green, wickDownColor: state.red,
      priceLineVisible: false, lastValueVisible: true
    });
    state.series.setData(seriesData(state));
    state.quoteLine = null;
    if (view) state.chart.timeScale().setVisibleLogicalRange(view);
  }
  function updateQuote(state, quote) {
    // Historical OHLC comes from actual trades. The quote midpoint is a separate
    // labelled guide and never manufactures a candle or rewrites its close.
    var price = quote && quote.price;
    if (!(Number.isFinite(price) && price > 0) || !state.rows.length) {
      if (state.quoteLine) state.series.removePriceLine(state.quoteLine);
      state.quoteLine = null;
      return;
    }
    var options = { price: price, color: state.amber, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: 'QUOTE' };
    if (state.quoteLine) state.quoteLine.applyOptions(options);
    else state.quoteLine = state.series.createPriceLine(options);
  }
  function validRows(rows) {
    if (!Array.isArray(rows)) throw Error('Invalid chart data');
    var previous = 0;
    rows.forEach(function (row) {
      if (!Number.isInteger(row.time) || row.time <= previous ||
          !['open', 'high', 'low', 'close'].every(function (key) { return Number.isFinite(row[key]) && row[key] > 0; }) ||
          row.high < Math.max(row.open, row.close, row.low) || row.low > Math.min(row.open, row.close)) throw Error('Invalid chart data');
      previous = row.time;
    });
    return rows;
  }
  function fetchHistory(state, options) {
    state.busy = true;
    state.requestedAt = performance.now();
    var generation = state.generation;
    options.request(options.symbol, options.range).then(function (payload) {
      if (generation !== state.generation) return;
      if (!payload || payload.symbol !== options.symbol || payload.range !== options.range || payload.source !== 'alpaca_sip' ||
          ['ok', 'empty'].indexOf(payload.status) < 0) throw Error('History unavailable');
      var rows = validRows(payload.bars);
      var firstLoad = !state.rows.length;
      var view = state.chart.timeScale().getVisibleLogicalRange();
      state.rows = rows;
      state.series.setData(seriesData(state));
      if (firstLoad) state.chart.timeScale().fitContent();
      else if (view) state.chart.timeScale().setVisibleLogicalRange(view);
      state.host.setAttribute('aria-label', options.symbol + ' ' + intervals[options.range] + ' ' + state.type + ' chart, Alpaca SIP prices');
      status(state, rows.length ? 'ready' : 'empty', rows.length ? '' : 'No Alpaca history for this period.');
      document.getElementById('port-chart-source').textContent = 'Alpaca SIP · ' + intervals[options.range] + ' bars · USD · ET';
      updateQuote(state, state.latestQuote);
    }).catch(function () {
      if (generation !== state.generation) return;
      status(state, 'unavailable', state.rows.length ? 'History update unavailable. Showing the last loaded bars.' : 'Alpaca history unavailable. Retrying…');
    }).finally(function () { if (generation === state.generation) state.busy = false; });
  }
  function render(host, options) {
    var state = mounted.get(host);
    if (!state) { state = create(host); mounted.set(host, state); }
    if (!state.chart) return;
    var selection = options.symbol + ':' + options.range + ':' + options.token;
    if (state.selection !== selection) {
      state.selection = selection;
      state.generation += 1;
      state.busy = false; state.requestedAt = null; state.rows = [];
      if (state.series) state.series.setData([]);
      state.tooltip.hidden = true;
      state.host.dataset.symbol = options.symbol;
      state.host.dataset.range = options.range;
      status(state, 'loading', 'Loading Alpaca history…');
      document.getElementById('port-chart-source').textContent = 'Alpaca SIP · ' + intervals[options.range] + ' bars · USD · ET';
    }
    setType(state, options.type);
    host.setAttribute('aria-label', options.symbol + ' ' + intervals[options.range] + ' ' + options.type + ' chart, Alpaca SIP prices');
    state.latestQuote = options.quote;
    updateQuote(state, options.quote);
    if (!window.ResizeObserver) state.chart.resize(host.clientWidth, host.clientHeight);
    var refreshMs = options.range === '1D' || options.range === '1W' ? 30000 : 60000;
    if (!state.busy && (state.requestedAt === null || performance.now() - state.requestedAt >= refreshMs)) fetchHistory(state, options);
  }
  function fit(host) {
    var state = mounted.get(host);
    if (state && state.chart) state.chart.timeScale().fitContent();
  }
  window.YomamaPortChart = { render: render, fit: fit };
})();
