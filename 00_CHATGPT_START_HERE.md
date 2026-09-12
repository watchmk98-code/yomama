> **Status (2026-09-12):** this file describes the early static prototype and is kept for history.
> The economy now runs on the Python server, no page is served before signing in, and classes
> are opened by the developer from the command line. Read `AGENTS.md` first. The design-language
> sections below still hold; the technical ones (localStorage economy, `collect.html`,
> `marketplace.js`, `produce.js`, `config/economy.v0.1.json`) do not.

# ChatGPT Start Here

This repository is a static multi-page web prototype called `YOMAMA INVESTMENTS`.

It is not a generic fintech dashboard. It is a Bloomberg-inspired retail portfolio terminal wrapped in a stylized game/world-building layer:

- retail portfolio tracking
- analyst/character selection
- leaderboard and memo energy
- a persistent buildings/economy simulator
- marketplace and production systems

## What ChatGPT Should Understand First

- The codebase is plain HTML, CSS, and JavaScript. There is no framework, bundler, or build step.
- Most shared behavior lives in `app.js`.
- The app uses a strong visual identity that should be preserved.
- The project already has an intentional tone: terminal-like, dense, sharp, playful-serious, and not polished into generic startup UI.

## Non-Negotiable Design Principles

- Keep the pitch-black terminal background.
- Keep the amber/green/red color logic.
- Keep sharp rectangular geometry with zero rounded corners.
- Keep VT323 / OCR / retro monospace direction.
- Keep the dense Bloomberg-like information layout.
- Keep the cyan/magenta glitch energy mostly contained to the hero/banner area.
- Do not redesign this into a soft card-based fintech SaaS dashboard.
- Do not replace the personality of the app with generic finance copy.

## Product Direction

Current direction is:

`Bloomberg-style portfolio clarity for retail users, inside the YOMAMA world.`

That means the finance side should focus on:

- portfolio value
- day change
- total return
- benchmark comparison
- holdings
- allocation
- dividends/income
- simple insights and news

It should avoid drifting into a fully institutional product unless explicitly requested.

## Where To Look First

- `index.html`
  Main dashboard / terminal landing page.
- `styles.css`
  Core visual system and page-specific styling.
- `app.js`
  Shared runtime, dashboard behavior, character system, persistence, buildings simulator, sample-data loading, ticker, fundamentals, and more.
- `collect.html`
  Main entry into the buildings simulator.
- `config/economy.v0.1.json`
  Core tuning for resources and building progression.
- `marketplace.js`
  Marketplace buy/sell flows.
- `produce.js`
  Product recipe and production flows.
- `memos-bars.js`
  Animated leaderboard logic.

## How To Run Or Preview

This is a static site. The easiest options are:

- open `index.html` directly in a browser
- or serve the folder locally with a simple static server

If a local server is used, start from the project root and open `index.html`.

Note that some behavior depends on:

- CDN scripts for `PixiJS` and `Highcharts`
- browser storage
- network fetches for TradingView scanner data

## Paste-Ready Prompt For A New ChatGPT Session

Use this prompt when starting a fresh ChatGPT browser chat with the zipped source:

```text
You are helping me with a static HTML/CSS/JS project called YOMAMA INVESTMENTS.

This is a Bloomberg-inspired retail portfolio terminal with a strong custom identity. It is not a generic fintech app. Preserve the existing design language:
- black terminal background
- amber/green/red semantic color system
- VT323 / OCR / retro monospace feel
- sharp rectangular geometry, no rounded corners
- dense information layout
- glitch/pixel/cyan-magenta hero energy only where already appropriate

Important product context:
- The finance layer should feel like Bloomberg-style clarity for retail investors.
- The app also includes a world/character/economy layer: analysts, leaderboard, buildings, production, marketplace, and focus tree.
- Do not flatten this into a boring SaaS dashboard or remove the app's personality.

Technical constraints:
- No framework or bundler.
- Shared behavior mostly lives in app.js.
- Buildings/economy state and account state persist through localStorage/sessionStorage keys. Do not casually rename storage keys.
- Preserve page-to-page navigation and current structure unless there is a strong reason to change it.

When making suggestions or edits:
- start by understanding the existing file structure
- preserve the visual grammar
- make minimal, intentional changes
- avoid generic rewrites
- explain tradeoffs clearly
```

## Recommended Working Rules For ChatGPT

- Read before rewriting.
- Prefer extending the existing structure over replacing it.
- If touching finance UI, keep it retail-focused.
- If touching buildings/economy code, preserve storage compatibility.
- If touching styles, match the terminal system already in `styles.css`.
- If adding documentation, keep it practical and specific to this repo.

## Archive Contents

The zip for handoff is intended to include:

- source code
- styles
- config
- assets
- sample data
- these ChatGPT guidance files

Transient logs and old backup archives are not required for understanding the project.
