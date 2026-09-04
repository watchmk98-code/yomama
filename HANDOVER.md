# YOMAMA INVESTMENTS — developer handover

Read this before changing anything. It is short on purpose; the parts that
will bite you are marked.

## What this is

A browser game for a cohort of ~30 players sharing one market, designed to run
continuously for a ~3 month term. Players run a small industrial base
(buildings → resources → products), sell into a **shared** marketplace where
prices move with everyone's supply, and invest the proceeds.

Half finance terminal, half tycoon game. The visual identity is deliberate and
finished — see "Do not break" below.

## Run it

```bash
python3 server.py 3000
```

No build step, no package install, no framework. Python 3.9+ stdlib only.
It prints the LAN address other machines should use.

- Teacher/host console: `/class.html` — opens a class, prints the code, shows a live roster
- Players: `/join.html` — class code + name + 4-digit PIN
- Game: `/collect.html` (base), `/produce.html` (recipes), `/marketplace.html` (selling)

## Architecture

Plain HTML pages + one shared `app.js` (335KB, hand-authored) + `styles.css`.
No bundler. Pages are independent; shared state moves through the server.

| File | Role |
|---|---|
| `server.py` | Static file server (allowlisted), news/FX proxies, game API routing |
| `game_api.py` | All game logic that must be authoritative. SQLite. |
| `yomama-net.js` | The **only** thing that talks to the game API |
| `app.js` | Buildings/economy simulation, most UI |
| `marketplace.js`, `produce.js` | Per-page logic |
| `config/economy.v0.1.json` | All economy tuning |

**The split that matters:**

- **Server owns** (in `game.db`): cash, product inventory, equity positions,
  market prices and stock, the leaderboard, the roster. These are scored, so
  they must not be editable in devtools.
- **Client owns**: building levels, build timers, resources. Simulated in the
  browser, then synced to the server as an opaque blob.

Everything degrades: with no session, or an unreachable server, pages fall back
to the original localStorage behaviour.

## ⚠️ The economy is a solved system — do not tune one number

The costs in `config/economy.v0.1.json` are **derived**, not hand-picked:

```
cash cost of an upgrade = its marginal income gain × 40 days
```

That is why every building pays back in the same time, why all four get
upgraded roughly equally over a term, and why the base finishes around day 91.
Changing any single input silently breaks the others. In particular:

- **Building outputs are set to the ratio recipes consume.** Change one output
  ladder and resources start being wasted again.
- **Product prices set the value of every resource.** These are shadow prices
  from a 4-recipe linear program — supply does *not* affect them. Hydro Lettuce
  was repriced from \$11.88 to \$21.18 specifically to stop food being worth
  \$0.04/unit, which had made the farm a dead building.
- **Cycle times and cash costs are coupled.** Income scales linearly with cycle
  speed, so halving `cycleMinutes` doubles income and every cost must move with
  it.

If you need to rebalance, re-derive with a linear program over the five
recipes; do not nudge values by feel. The intended shape is: base maxes near
the end of the term, a daily player finishes, a weekly player gets about half
way.

## ⚠️ The cross-device save has four invariants

Buildings and resources sync through `/api/game/buildings`. It is easy to
break; each of these was a real bug:

1. **Never push before hydrating.** A newly opened device must not write its
   blank starting state over the real save. `pushBuildings` refuses until
   hydration has settled.
2. **Do not use `location.reload()` to apply a fetched save.** `app.js`
   finishes its own async init and persists in-memory defaults over whatever
   was adopted. Pages must `await YomamaNet.ready()` instead.
3. **`getPlayerSave()` memoises.** After adopting a server copy you must clear
   `playerSaveState`, or the adopted data sits unread in localStorage.
4. **Stamp saves when state changes, not when it sends.** Otherwise merely
   reopening the game on an old device makes it look newer and silently reverts
   another device's progress.

`produce.js` still reads its resources without awaiting `ready()`. The normal
path is safe because joining always lands on `collect.html` first, but landing
directly on `produce.html` in a fresh browser can briefly show a stale base.
Worth closing.

## Known gaps

| Area | State |
|---|---|
| `teach.html` | Gradebook mock — 54 invented students from a seeded PRNG. Not wired to anything. |
| `memos.html` leaderboard | Animation of fictional characters with random jitter. The real leaderboard is in the API and on `class.html`. |
| `focus-tree.html` | Static markup. No handlers, no state, no costs. |
| Paper trading (`port_trading.html`) | No price source; position marks are typed in by the player. |
| Production anti-cheat | Production is simulated client-side. `/api/game/produce` meters deposits (400 units + 120/hour) but a determined player can inflate within that. |
| PINs | Stored in plaintext. Fine for a known cohort, weak for public signup. |
| Hosting | Runs on a laptop over LAN. Not deployed. Needs HTTPS, a real server in front of `ThreadingHTTPServer`, and `game.db` backups. |

## Do not break

- **No build step.** Plain files, opened directly or served statically. Keep it that way.
- **The visual language is finished**: near-black background, amber accent, green/red for
  gain/loss, VT323 terminal type, zero border radius, dense layout. Do not soften
  it into rounded fintech cards or add gradients.
- **The static-file allowlist in `server.py`.** It exists because the server
  previously handed out `game.db` (player names, session tokens, the host
  token), `.git/`, and backup archives to anyone who asked. It is an allowlist
  deliberately — a blocklist would republish every new secret dropped in the folder.
- **Server authority.** Anything that appears on the leaderboard must be
  computed server-side.

## Testing

There is no test suite. Behaviour was verified by driving real browsers with
Playwright — join flows, cross-device saves, the trade loop, price movement
under load, and the static-file allowlist. Worth formalising: the save sync in
particular has four non-obvious invariants and no regression test.

Useful check for economy changes: simulate 91 days of greedy play against the
config and confirm the base still finishes near day 85–91 with all four
buildings upgraded roughly equally.
