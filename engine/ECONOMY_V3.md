# Part 1 economy v3

Part 1 uses the hoarding economy: every owned building remains productive. The Python server owns all YM, purchases, contracts, prices, and licence decisions. `econ.js` renders server payloads and sends intentions. Part 2 trading code is preserved; only its licence checks change.

## Source of truth

- `config/economy.v3.json`: supplied v3 economic values, families, goods, and tax brackets. Extra `fun`, `gate.levelNeeded`, and `runtime` fields externalize constants that were literals in the supplied reference; their values have not been retuned.
- `engine/economy-engine.reference.js`: the supplied JavaScript, unchanged, including its simulator. It is an oracle for tests, never a client money authority.
- `economy.py`: Python rules, unsigned xorshift32, Box–Muller draw order, float32 price outputs, and `floor(x + 0.5)` for JavaScript rounding. Float64 internal stream state is retained between samples.
- `game_api.py`: SQLite, authentication, class clocks, transactions, reports, and derived payloads.
- `tests/sim.py`: attendance schedules, test-bot strategies, contract decisions, and simulation. The server never imports it.
- `content/headlines.json`: 42 placeholder headlines. `content/memos.json`: 90 placeholder memos, keyed by building and trigger. All placeholder copy is marked TODO.

The supplied engine wins where the prose conflicts. In particular:

1. The first event starts at hour 2; its first rumour starts at minute 75, not within the first hour.
2. Contract completion pays the target plus reward, taxed. It does **not** call the pressure hook. Manual sales, overflow, and auto-continue sales do.
3. Each building has one goods pool and one price stream. Three named goods are a server-generated display split; Sell clears the whole building pool.
4. `finishBuild` sells at fair value and performs one optimizer purchase round only if its construction queue empties. `auto_continue` implements that production rule; scheduled bot play remains in tests. Reference automatic purchases do not award explicit-purchase checklist credit.
5. The reference uses 240 output ticks per hour for contract targets even if a test changes tick duration. This constant is now `fun.contractOutputTicksPerHour`.
6. Frontier order is config tier order, which is cost order in the supplied config. Preserve that order when adding buildings.

The base document and simulator found in Downloads describe an older economy. The v3 fun-layer document and original v3 golden fixtures were not supplied. The replacement fixtures are explicitly labelled as generated from the supplied v3 engine. The four stochastic attendance profiles come from the supplied simulator and run together in one shared class. The deterministic oracle reproduces the task's independent value, **114,157,066 YM**.

## Class replay and transactions

`tick` means the next tick to replay. A new player starts at the class's current tick; joining late does not grant past production. A request advances ticks `[last_class_tick, current_tick)` one by one, capped at `runtime.maxCatchupDays` (30 days). Further state requests continue from the saved position. No closed-form catch-up is used.

For each tick:

1. Decay shared pressure, and recompute aggregate hourly income at hour boundaries.
2. Visit players in stable database ID order, excluding students who have not joined yet.
3. Complete construction and start the next queued build, or execute the reference auto-continue round.
4. Refresh daily contract offers; produce and round each building's output.
5. Divert goods into contracts, then settle completion/deadline outcomes.
6. Fill each building's warehouse allocation and sell overflow at its current class price, applying tax and pressure immediately.

Actions use the last replayed price sample. A sale immediately changes the class pressure used by subsequent requests. Events ramp from zero effect at their start sample. Teacher events start at the current sample, so their effect begins with the next market sample.

Every economy request uses a per-class reentrant lock and a SQLite transaction (`BEGIN IMMEDIATE`). SQLite's writer lock also serializes independent server processes. A process-wide lock retains compatibility with the existing database handlers. Only deterministic base price streams are cached; mutable pressure and income are reloaded from SQLite. Failed actions roll back their request transaction. A client catches up through `/econ/state` before retrying an action if it is beyond the replay cap.

Sessions persist `class_seed`, `started_at`, a config snapshot, `pressure`, `income_per_hour`, `econ_tick`, and teacher `custom_events`. Seeded events regenerate deterministically; no event table is needed. Class config snapshots remain fixed across later config file edits.

`players.econ` holds the serializable engine state. `b[slot]` contains the level/Auto Control for an owned slot, and `tierOf[slot]` identifies its config tier. JSON warehouse/unlock keys are strings. `players.econ_meta` holds replay tick, RNG state, report counters/baselines, and the previous rank. `econ_nw` is an INTEGER for ranking; every Part 1 monetary JSON value is an integer. The existing REAL wallet/position columns belong to Part 2.

Reports accumulate even when a classmate triggers replay. After at least two hours since the previous login, the login response reports production, overflow and its discount cost, completed builds, real events, contract outcomes, and rank change. Collect only closes the dialog. Welcome-back production follows the separate 24-hour absence / one-hour boost rule.

## Existing saves

On first access, a legacy class receives the v3 snapshot and an audit ledger entry containing its prior config and player states. Migration retains cash, book value, tax, checklist progress, stored goods, its actually owned building, and paid construction. Levels above the v3 cap are clamped to the cap. Previously sold buildings are not recreated or refunded again. Shared pressure begins at zero at migration, since legacy sales did not track pressure. New classes start cleanly at Greenfield Farm, zero cash, one YM per tick. The existing automatic solo-seat mode remains available, with its artificial head start removed.

The live `game.db` is not modified by the test suite; tests use temporary databases. Back up existing databases before operational rollout if rollback is needed. Do not run old and v3 server processes against the same database.

## API and screens

All paths are under `/api/game`. Student requests use the existing player token; teacher requests require the teacher token.

| Method and path | Action |
|---|---|
| POST `/econ/login` | Replay, login boost, overnight report, full payload |
| GET `/econ/state` | Replay and full payload, including leaderboard |
| POST `/econ/sell` `{slot}` | Sell one owned building's pool; premium and tax receipt |
| POST `/econ/level`, `/econ/auto` `{slot}` | Buy an explicit upgrade |
| POST `/econ/expand` `{tier}` | Buy a frontier building; structured 400 reason/frontier on rejection |
| GET `/econ/contracts` | Full state with offers and active delivery progress |
| POST `/econ/contracts/accept` `{offerIndex}` | Accept an offer |
| GET `/econ/ticker` | Recent real event lines, rumour, owned prices and pressure hints |
| GET/POST `/econ/quiz` | Quiz questions without answers / grade supplied answers |
| POST `/econ/keep` `{percent}` | Store an integer choice after the licence opens |
| GET `/teacher/econ` | Per-student collection, families, worth, checklist, gate |
| POST `/teacher/event` | Publish `{family, mag, holdMin, headline}` |

The existing building, Auto Control, warehouse, market, licence, and dashboard screens render these payloads with their existing terminal styling and building artwork. Mercury Logistics is a delivery-contract drawer on the building screen. Teacher controls appear on `teach.html` and `class.html`. Hidden navigation excludes Produce, Collect, and Focus Tree. Part 2 navigation and the equity API both check the server licence; the Keep choice does not execute Part 2 liquidation.

## Validation

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tests/requirements.txt
.venv/bin/python -m pytest tests -q
```

Node.js is required for the direct JavaScript-oracle test. CI runs all seven requested acceptance groups plus API integration tests: exact deterministic and four-player stochastic goldens, 100 randomized configs, replay/restart equivalence, frontier/hoarding, contracts, events, RNG/float32 parity, concurrent sales, teacher authorization, late joins, reports, pause, and gate enforcement.

Regenerate fixtures only when intentionally changing the authoritative engine/config:

```sh
node tests/make_golden.js
```

The old v1 golden files remain under `tests/legacy_v1/` for provenance and are not active acceptance fixtures. `python3 tests/run_tests.py` also runs the engine tests without pytest; the SQLite integration suite uses pytest fixtures.
