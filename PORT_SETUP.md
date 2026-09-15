# PORT: first saved-account milestone

PORT now saves each student's virtual account in `players.port_state` in the
existing game database. The seat token selects the account. A first visit
creates $100,000 cash, empty holdings and an opening cash entry. Browser sample
accounts are never imported. The original sample terminal is available only
at `port_trading.html?demo=1` and remains browser-local.

Open **GAME → PORT**, beside Craft in the business navigation. PORT is available
to every signed-in student, including fresh and reset seats, without an analyst
licence. The chart stays visible in its panel. The order ticket uses green
text and borders for Buy and red for Sell.

The existing town wallet, town net worth and standings retain their rules.
The town-to-PORT currency exchange is deferred. The older Part 2 wallet and
positions remain separate legacy records; their contents are not sample
PORT holdings and are not imported automatically.

## Alpaca connection

The game reads SIP bid/ask quotes, the US market clock and exchange calendar. All student trades
are virtual and executed by YOMAMA; the adapter never calls Alpaca's order API.

Set these environment variables on the server:

- `APCA_API_KEY_ID`
- `APCA_API_SECRET_KEY`
- `APCA_API_BASE_URL` — defaults to `https://paper-api.alpaca.markets`; use
  `https://api.alpaca.markets` only when using a live-account key for data.

Use an API key whose account has the paid SIP data entitlement. Credentials
must stay outside the web root, repository and browser assets. No credential
values are included in this document. The separately offered Alpaca connector
in ChatGPT does not configure a running YOMAMA server's credentials.

Reference: [latest SIP quotes](https://docs.alpaca.markets/us/reference/stocklatestquotes-1)
and [US market calendar](https://docs.alpaca.markets/us/reference/legacycalendar).

## Current execution rules

- PORT follows real time, independently of the accelerated town clock. The UI
  displays New York exchange time using the server clock, so changing a device's
  date or timezone cannot change trading eligibility or quote freshness.
- Trading follows regular US sessions: normally 09:30–16:00 ET. Alpaca's
  calendar supplies holidays and early closes. Orders cannot fill outside the
  current session, even if a cached clock response still says the market is open.
- Whole shares; buy at ask, sell at bid; no short selling or leverage.
- Integer-cent cash and cost basis, with cash/share reservations for open orders.
- Market and GTC limit orders, cancellations, fills and history are saved together.
- A client request ID prevents duplicate orders after lost responses or retries.
  Each account reset gets a new ID, so old pending browser requests cannot buy
  again in a reset account.
- Only the server's background execution cycle can fill orders. Page refreshes,
  order submissions and cancellation requests do not trigger fills. Orders keep
  running with every browser closed and resume from saved state after a restart.
- Fills use the first eligible quote observed by that cycle, timestamped at or
  after the server received the order, inside the regular session and at most
  10 seconds old. Older snapshots cannot rewind an account's execution history.
- Market orders expire after 30 real seconds or at that session's close,
  whichever comes first. GTC limit orders remain pending across sessions until
  filled or cancelled. An accepted order is not a confirmed fill.
- Cancellation intent is saved immediately, without waiting on Alpaca. The
  worker compares its receipt time with the quote timestamp: an eligible
  earlier quote may still fill the order; a quote at or after cancellation
  cannot. Closed-market cancellations complete on the next server cycle.
- New orders require a signed-in seat, an active/unpaused class, and regular US
  market hours. Class pauses freeze portfolio transitions, while real-time
  market-order deadlines keep advancing. After resume, fills require a quote
  timestamped at or after resume. The worker does not count as town activity.
- Feed failures block new orders and fills while preserving saved accounts.
  Expired market orders still release their reservations on the next permitted
  cycle. No historical fills are invented after an outage or server downtime.

`port_worker.py` starts with the server and checks saved accounts every two real
seconds, sharing one REST quote batch across accounts in each cycle. Provider
latency can lengthen that interval. This is sampled execution: a limit crossed
between samples can be missed, and fills use the next observed eligible quote,
not every exchange tick. Streaming and corporate actions remain future work.
The open PORT page separately refreshes its saved account every two seconds.

## Price chart

PORT draws real Alpaca SIP historical OHLC bars inside the existing research
panel, with the dashboard's black and amber styling. The compact toolbar has
interval controls, bars/candles/area icons, a line option and reset view. Zoom,
pan and crosshair interactions come from a local copy of TradingView Lightweight
Charts 5.2.1. TradingView supplies chart software only; Alpaca supplies prices.
Chart type and interval preferences survive refresh. Portfolio polling and
resizing preserve the chart and the student's zoom.

The terminal keeps watchlist and stock-picker controls stable during refreshes,
reports completed orders in the existing feedback area, and lets Escape dismiss
the chart-style menu. Touch devices receive 44-pixel targets for trading and
chart controls; their groups wrap within the existing panels on narrow screens.
Both market eligibility and chart refresh timing are independent of device
wall-clock changes.

Authenticated `GET /api/game/port/chart?symbol=AAPL&range=1W&token=...` returns
split-adjusted historical bars, including available extended-hours activity.
The server checks the seat and active class before and after provider requests.
No Alpaca credentials reach browser assets or requests.

| Toolbar interval | API range | Loaded history | History refresh |
| --- | --- | --- | --- |
| 1m | 1D | Latest New York trading date with data | 30 seconds |
| 30m | 1W | Past 7 calendar days | 30 seconds |
| 1h | 1M | Past 31 calendar days | 60 seconds |
| 4h | 3M | Past 91 calendar days | 60 seconds |
| D | 1Y | Past 366 calendar days | 60 seconds |
| W | 5Y | Past 1,827 calendar days | 60 seconds |

The 4h and W views request Alpaca's native `4Hour` and `1Week` bars. All intervals
use the provider's historical OHLC values. See [Alpaca's supported bar intervals](https://docs.alpaca.markets/us/reference/stockbars).

The separate QUOTE guide uses the fresh Alpaca bid/ask midpoint from the
two-second portfolio poll. It never rewrites a historical close or invents a
candle. Orders still buy at ask and sell at bid. Chart failures show an explicit
unavailable message; the separate `?demo=1` page keeps its labelled illustrative
graph. Vendored chart software retains its upstream LICENSE and NOTICE under
`vendor/lightweight-charts-5.2.1/`.

## Preview and verification

An isolated, fresh student seat, using the configured Alpaca feed:

```sh
python3 previews/port_preview.py 3015
```

Repeatable test quotes in a temporary database:

```sh
python3 previews/port_preview.py 3014 --fixture-quotes
node tests/ui_port_persistence.cjs http://127.0.0.1:3014
node tests/ui_port_server.cjs http://127.0.0.1:3014
node tests/ui_port_terminal.cjs http://127.0.0.1:3014
.venv/bin/python -m pytest tests -q
```

The persistence browser test buys in one browser context, reads the same
account in another, sells there and verifies the first browser after reload.
It then submits an order, closes every browser, and verifies that the worker
filled it before any browser reopened.
Fixture quotes are labelled and never enabled by a public server setting.

## Reaching existing classes

Deploying adds the new column automatically. Existing seats,
towns and class configurations remain intact; **no class reset is required**.
The existing teacher/student and class-reset operations also reset PORT.
PORT access is independent of the analyst licence for existing and future
seats; other licence requirements retain their rules.

The code and Alpaca environment variables must reach Render before students
can use this version. Render has automatic deployment disabled: **needs
Manual Deploy**, between classes. Local preview verification does not change
the live database or deploy the site.
