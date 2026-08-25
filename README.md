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

You can also open `index.html` directly in a browser, but the local server is better because it supports the app's lightweight finance-news and FX proxy endpoints.

## Main Screens

- `index.html` - main portfolio terminal/dashboard
- `flow.html` - analyst/character selection
- `analysis.html` - analysis view with character profiles and fundamentals
- `memos.html` - memo/leaderboard experience
- `collect.html` - buildings and resource simulator
- `produce.html` - production recipes
- `marketplace.html` - product marketplace
- `paper-trading-demo.html` - paper-trading engine demo
- `teach.html` - teacher dashboard prototype

## Notes For Testers

- Progress and account state are stored in browser localStorage/sessionStorage.
- Some market/news/chart features use external APIs or CDN scripts and may fall back to sample data when offline.
- The core app is intentionally terminal-like: black background, amber/green/red finance colors, sharp geometry, and dense information layout.

## Project Structure

- `app.js` - shared runtime and most application behavior
- `styles.css` - global visual system and page styling
- `server.py` - local static server plus small proxy endpoints
- `config/economy.v0.1.json` - buildings/economy configuration
- `marketplace.js` - marketplace buy/sell logic
- `produce.js` - recipe production logic
- `engine/paper-engine.js` - isolated paper-trading engine scaffold
- `assets/` and `memos/` - visual assets
