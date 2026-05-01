# YOMAMA INVESTMENTS - Detailed Project Context

## 1. Project Identity

`YOMAMA INVESTMENTS` is a static prototype that merges two ideas:

1. A Bloomberg-inspired retail portfolio terminal
2. A stylized game-like universe with analysts, leaderboard, buildings, economy, production, and marketplace systems

The result is not just a finance dashboard and not just a game skin. The identity comes from the combination.

The app feels like:

- terminal-native
- editorial but dense
- retail-focused rather than institutional
- playful in world-building, serious in visual discipline

## 2. Tech Stack And Runtime Model

This project uses:

- plain HTML pages
- one shared CSS file: `styles.css`
- mostly shared JavaScript in `app.js`
- a few specialized JS modules for sub-features
- CDN-loaded libraries:
  - `PixiJS`
  - `Highcharts` on chart/fundamentals pages

There is no React, no Vue, no bundler, and no server-side framework.

The project behaves like a hand-authored static site with shared runtime logic.

## 3. Core Visual Language

The visual system is one of the most important parts of the project.

### Design tokens and style direction

- background is near pure black
- primary text is light gray/white
- amber is the main accent and focus color
- bright green indicates positive/gain states
- red indicates negative/loss states
- borders and dividers are thin and amber/brown
- typography is retro terminal / OCR / monospace led by `VT323`
- border radius is intentionally removed everywhere
- layout is dense, modular, and terminal-like
- the hero/banner area allows more expressive cyan/magenta glitch energy

### What not to do

- do not soften the UI into rounded fintech cards
- do not introduce generic SaaS gradients everywhere
- do not replace the terminal tone with clean-white productivity styling
- do not overuse glassmorphism or modern "AI startup" visuals

## 4. High-Level Product Structure

The product is split across multiple static pages.

### Main finance / brand pages

- `index.html`
  Main dashboard / terminal landing page with market table, news, portfolio table, chart area, fundamentals area, and memo/leaderboard widget.
- `analysis.html`
  Analysis-focused screen that combines character bio/profile overlay with fundamentals/charting.
- `memos.html`
  Leaderboard page.
- `flow.html`
  Analyst / character selection screen.
- `about.html`
  Brand/about page.
- `contact.html`
  Contact page.
- `tomfort-method.html`
  Dedicated branded concept page.
- `preview.html`
  Alternate preview/variant of the main dashboard.
- `fundamentals-terminal.html`
  Standalone fundamentals terminal experiment.

### Buildings / economy pages

- `collect.html`
  Main buildings simulator view.
- `warehouse.html`
  Warehouse workspace shell.
- `produce.html`
  Production recipes and manufacturing page.
- `advanced-hq.html`
  Advanced facilities management view.
- `marketplace.html`
  Product trading / marketplace page.
- `focus-tree.html`
  Narrative strategy/focus-tree page for Derdo Merdo.
- `buildings.html`
  Buildings-related page variant.

## 5. Shared Runtime Responsibilities In `app.js`

`app.js` is the center of the codebase. It handles much more than a normal page script.

Major responsibilities include:

- bootstrapping shared save/account state
- syncing localStorage/sessionStorage
- rendering global cash chip
- character selection and character visibility filtering
- bio/profile overlays
- economy/buildings simulator bootstrapping
- building production and upgrade logic
- stat allocation and respec logic
- simulator logs and rewards
- dashboard ticker generation and animation
- portfolio and market table updates
- sample news loading
- fundamentals rendering and fallback behavior
- hero/banner animation behavior
- page-specific enhancements based on which DOM elements exist

Important implication:

Any change in `app.js` can affect multiple pages.

## 6. Persistent Data And Storage Model

The app uses browser storage heavily. This matters a lot if another assistant is going to edit the project.

### Important storage keys in use

- `yomama_game_save_v1`
- `yomama_game_save_v1_backup`
- `yomama_watchmk_account_v1`
- `yomama_watchmk_account_v1_backup`
- `yomama_player_save_v1`
- `yomama_player_save_v1_backup`
- `hero_select_active_character`
- `memos_current_champion`
- `memos_leaderboard_timeframe`
- marketplace-related keys in `marketplace.js`

### Why this matters

- storage keys are part of the app's persistence contract
- renaming keys casually can break saves and cross-page sync
- the buildings/economy system, selected analyst, marketplace state, and account state are interconnected

## 7. Finance Layer

The finance/dashboard side is intentionally Bloomberg-inspired but should stay retail-focused.

### Finance capabilities already present or implied

- dashboard shell with market tables and news
- chart area with time horizons
- fundamentals panel
- current portfolio/current buildings tables
- sample portfolio data
- sample stock fundamentals and stock news data
- live-ish data hooks via TradingView scanner endpoint

### Current product direction for finance

This should continue toward:

- portfolio value
- day change
- total return
- benchmark comparison
- holdings
- allocation
- dividends/income
- linked news
- light risk and insight panels

This should not become a full institutional risk workstation unless explicitly requested.

## 8. Character / Analyst Layer

The project has a roster of stylized "analysts" / characters.

Known characters include:

- Buffett
- Tomfort
- Marks
- Peaker
- Dennis
- Irene
- Derdo
- Ozan
- Hussein
- Can / John
- Hara
- Pelli

The character system supports:

- roster selection in `flow.html`
- profile/bio overlays
- selected character persistence
- navigation from leaderboard to analysis
- economy profile linkage per character

This layer is part of the product identity and should be preserved.

## 9. Buildings / Economy Layer

The buildings subsystem is one of the most developed product slices.

### Core idea

Users build and upgrade a base that produces resources and interacts with marketplace and production systems.

### Main resource types from `config/economy.v0.1.json`

- food
- materials
- energy
- data

### Production buildings

- farm
- workshop
- generator
- data_center

### Advanced buildings

- hq
- warehouse
- logistics
- marketplace
- contractor_office
- automation

### Economy mechanics present in code

- build and upgrade costs
- build timers
- production cycle timers
- output by level
- resource caps
- automation extensions
- crew limits
- stat-based modifiers
- per-character profiles
- progression rewards
- logs and simulator state

## 10. Marketplace And Production

### `produce.js`

Handles recipe-based manufacturing. It reads inventory/account state and lets users convert resources into products.

### `marketplace.js`

Handles buying and selling products, capped marketplace stock, inventory sync, and cash/account updates.

### Shared concern

These systems depend on:

- resource inventory
- account cash
- marketplace inventory
- persistent storage contracts

Changes here should be careful and data-compatible.

## 11. Leaderboard / Memo Layer

`memos.html` and `memos-bars.js` provide a more animated, character-driven leaderboard experience.

Key behaviors:

- animated rank changes
- daily / weekly / monthly frame switching
- point deltas and motion feedback
- persisted timeframe selection
- navigation from a leaderboard character entry into analysis

This is not just decorative. It reinforces the app's world and character logic.

## 12. Sample Data And Config Files

Important local data files:

- `config/economy.v0.1.json`
  Economy tuning, resources, building costs, timings, automation values.
- `sample-stock-fundamentals.json`
  Local fundamentals data used for dashboard/analysis rendering and fallback content.
- `sample-stock-news.json`
- `sample-stock-news.ndjson`
- `sample-stock-news.xml`
  Local news data samples / experiments.

These files are useful context for any assistant that wants to understand the intended data shape.

## 13. Important Assets

- `banner-colored.png`
  Main hero/banner image.
- `assets/fonts/VT323-Regular.ttf`
  Primary terminal font source.
- `assets/hero-select/*`
  Character portraits and selection assets.
- `memos/*`
  Memo and portrait art.
- `assets/buildings-icons/*`
  Buildings/economy icon system.

## 14. Known Structural Patterns

### Shared header shell

Most pages use:

- top meta strip
- scrolling ticker
- right-side clock and action buttons
- banner/glitch hero
- tab navigation

### Dashboard layout

Finance pages generally use:

- left column for search + market/news tables
- center column for charts/fundamentals
- right column for current portfolio/buildings + memo/insight widgets

### Buildings layout

Buildings pages generally use:

- main simulator workspace
- quick-links bar for buildings sub-pages
- side panels for messages and stats

## 15. File-Level Responsibilities

- `styles.css`
  Global visual system plus large amounts of component/page styling.
- `app.js`
  Shared application runtime and most feature logic.
- `buildings-nav.js`
  Syncs buildings quick-link active state.
- `produce.js`
  Production recipes and crafting logic.
- `marketplace.js`
  Marketplace trading logic.
- `memos-bars.js`
  Leaderboard interactions and animation.
- `memos.js`
  Additional memo-related persistence logic.

## 16. Working Guidelines For Another Assistant

If another assistant edits this project, it should:

- preserve the existing visual grammar
- avoid generic redesigns
- treat `app.js` as shared infrastructure
- preserve browser storage compatibility
- check page-specific DOM before changing shared logic
- keep the retail portfolio direction on the finance side
- preserve the game/world layer instead of stripping it away

## 17. Good First Files To Read Before Editing

Recommended reading order:

1. `00_CHATGPT_START_HERE.md`
2. `index.html`
3. `styles.css`
4. `app.js`
5. `collect.html`
6. `config/economy.v0.1.json`
7. `marketplace.js`
8. `produce.js`
9. `memos-bars.js`

## 18. Summary In One Sentence

This project is a static, Bloomberg-inspired retail portfolio terminal with a strong retro-terminal visual identity and a connected analyst/buildings/economy game layer that must be preserved as part of the product, not treated as incidental decoration.
