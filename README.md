# YOMAMA INVESTMENTS

YOMAMA INVESTMENTS is a static HTML/CSS/JavaScript prototype that combines a Bloomberg-style retail portfolio terminal with a gamified analyst, buildings, production, marketplace, memo, and paper-trading world.

The project has no build step and no package installation requirement.

## Open The App

The recommended way to run it is with the included local server:

```bash
python3 server.py
```

Then open:

```text
http://127.0.0.1:3000/index.html
```

If port 3000 is already in use, choose another port:

```bash
python3 server.py 3001
```

Then open:

```text
http://127.0.0.1:3001/index.html
```

Use the local server for the game: production, sales, deliveries, and saves run on its Python backend. Opening the HTML file alone cannot run the economy.

The current building game uses real goods, automatic customers, recipes, three upgrade types, and optional deliveries. See [ECONOMY_README.md](ECONOMY_README.md) for rules and verification. For a separate fresh playtest, run `python3 previews/day3_preview.py 3001 --fresh`, then open `http://127.0.0.1:3001/buildings.html`. This preview uses a temporary save.

## Main Screens

- `index.html` - main portfolio terminal/dashboard
- `flow.html` - analyst/character selection
- `analysis.html` - analysis view with character profiles and fundamentals
- `memos.html` - memo/leaderboard experience
- `buildings.html` - owned businesses, production/customer/storage upgrades, and expansion
- `warehouse.html` - actual product inventory, shelf capacity, and reservations
- `marketplace.html` - automatic customer sales and optional stock clearance
- `advanced-hq.html` - operations, recipes, and processing controls
- `license.html` - business milestones, quiz and access to a separate practice portfolio
- `class.html` - teacher console: enter the teacher code, watch progress
- `join.html` - student sign-in (class code + name + PIN)
- `paper-trading-demo.html` - paper-trading engine demo
- `teach.html` - teacher dashboard prototype (still showing sample students)
- `classroom-sim.html` - offline balance simulation: thirty bot students play the
  v4 economy on one class clock, in a browser port of `production_economy.py`

`collect.html`, `produce.html` and `focus-tree.html` belong to the retired
client-side economy. They are off the navigation but still on disk.

## Notes For Testers

- To play the economy you need a class code. Classes are opened by the
  developer with `python3 admin.py open` (see `DEPLOY.md`), never from a page.
  Students join from `join.html` with the class code, a name and a 4-digit PIN;
  the teacher opens `class.html` with the teacher code. Without a class the
  economy screens say so.
- LOG OUT (top right of every page) signs the browser out so the next person
  can sign in; a browser idle for 20 minutes is signed out on its own.
- Money, buildings and prices live on the server, not in the browser. Only
  display preferences (character choice and the like) use localStorage.
- Some market/news/chart features use external APIs or CDN scripts and may fall back to sample data when offline.
- The core app is intentionally terminal-like: black background, amber/green/red finance colors, sharp geometry, and dense information layout.

## Project Structure

- `app.js` - shared runtime: ticker, clock, news desk, memos, charts
- `econ.js` - every economy screen (the only client-side economy code)
- `styles.css` - global visual system and page styling
- `server.py` - local static server, proxy endpoints, API routing
- `game_api.py` - classroom server: sessions, players, endpoints (SQLite)
- `access.py` - who may join, play or open the console; rate limit on wrong codes
- `account.js` - the LOG OUT pill on every page; idle and cross-tab sign-out for shared computers
- `admin.py` - developer CLI: open, list, close, revoke, resize classes; kick; rotate codes
- `run_server.py`, `render.yaml`, `DEPLOY.md` - hosting on Render
- `production_economy.py` - the current economy engine (`economy.py` retains v3)
- `config/economy.v4.json` - production economy configuration
- `config/quiz.json` - licence quiz about the current rules
- `engine/economy-engine.reference.js` - reference engine the port is tested against
- `engine/paper-engine.js` - isolated paper-trading engine scaffold
- `tests/` - economy tests: `python3 tests/run_tests.py`
- `assets/` and `memos/` - visual assets

See `ECONOMY_README.md` for how the economy works and `TEKNIK-NOTLAR.md` (in
Turkish) for the traps in the code.

The farm/roastery progression update adds order-specific reservations, upgrade consequences, specialties at production level 3, permanent breakfast rewards, and four new building sprites. See [progression design and validation](previews/progression-design.md).
