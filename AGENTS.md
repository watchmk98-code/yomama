# AGENTS.md - read this before touching anything

Two agents work in this tree at the same time:

- **Codex** owns the game: the economy engine, game logic, the pages and
  their scripts (`production_economy.py`, `breakfast_event.py`, `econ.js`,
  `econ-kids.css`, `game-fit.js`, `app.js`, the `*.html` pages, `config/`,
  `previews/`, the economy tests).
- **Claude Code** owns accounts, access control, hosting and provisioning
  (`access.py`, `admin.py`, `run_server.py`, `render.yaml`, `account.js`,
  `DEPLOY.md`, `previews/preview_support.py`, `tests/test_access_*.py`,
  `tests/test_admin*.py`, `tests/test_page_gate.py`, `tests/test_contract.py`,
  `tests/ui_account.cjs`, this file) - and, since 2026-09-12, **the LEAD page**
  (`memos.html`, `memos-bars.js`, `tests/ui_lead.cjs`, `tests/test_standings.py`,
  the `standings` table and `_leaderboard` in `game_api.py`). Codex: do not
  edit those; the user decided the page keeps its original arcade look.

Both edit `game_api.py`, `server.py`, `join.html`, `class.html` and
`yomama-net.js`. This file is how the access/hosting side tells the game side
what changed under it. It is kept current. Where an older document disagrees
with it (`00_CHATGPT_START_HERE.md`, `01_PROJECT_CONTEXT_DETAILED.md`,
`HANDOVER.md`, `TEKNIK-NOTLAR.md`), this file is right.

## 1. The site is live

`https://yomama-pbp3.onrender.com` runs the `classroom-server-and-economy`
branch on Render (Frankfurt, `starter` instance, a 1 GB disk at `/data`,
Cloudflare in front). Real classes with real students' seats exist on it.
Consequences:

- **Pushing does not deploy.** `render.yaml` has `autoDeploy: false` because a
  deploy restarts the service and would throw a class out mid-lesson. The
  user presses Manual Deploy between classes. Say "needs Manual Deploy" in
  your summary; never suggest turning auto-deploy on.
- The live database is `/data/game.db` on the Render disk. It is not the
  `./game.db` in this folder (that one is the local dev save, gitignored).
  You cannot reach the live one from here, and you must not assume the live
  classes run the rules you just wrote (see section 5).
- Python is 3.12 on Render and 3.9 on this machine. Code has to run on both:
  keep `from __future__ import annotations` for `X | None`, no `match`, no
  3.10-only stdlib.
- The repository is public. Never commit class codes, teacher codes, PINs,
  `game.db*` or `roster*.json` (all gitignored; keep them so). Do not put
  them in this file or in test fixtures either.

## 2. Access model (what replaced auto-login)

- `game_api.AUTO_LOGIN = False`. Every API request needs the `token` of a seat.
  There is no solo player and no "first visitor gets a seat" on the public
  server. `AUTO_LOGIN = True` exists only for local previews (section 4) and
  must never be set in `game_api.py` itself or in anything that runs on Render.
- **Classes are opened only by the developer**, from the command line:
  `python3 admin.py open --label "9-B" --size 30`. There is no HTTP route for
  it (`POST /api/game/session` is gone, 404) and no admin key: the shell is the
  key. `game_api.create_session()` still exists for the tests only.
- **Students**: `join.html` -> `POST /api/game/join {code, name, pin}` ->
  `{token, name, code, rejoined}`. Names are unique per class and upper-cased;
  the PIN is 4 digits; the same name + PIN returns the same token on any device.
- **Teachers**: `class.html` -> `POST /api/game/teacher/login {teacher_code}` ->
  `{code, teacher_token, label, class_size}`. The 6-character teacher code is
  printed by `admin.py open`; the console for that one class then uses the
  `teacher_token` with `POST /api/game/teacher` (pause, resume, reset_player,
  roster), `GET /api/game/teacher/econ` and `POST /api/game/teacher/event`.
  `class.html` also seats the teacher as a player so they can try the game.
- **Class flags** on the `sessions` row, written by `admin.py`, read by
  `access.py`: `active` (revoke/restore: every request of the class is 403),
  `joins_open` (close/reopen: new seats are 403, rejoins still work),
  `class_size` (a seat cap, teacher's seat included, next student is told
  "full"), `teacher_code`, `label`. Also `admin.py kick`, `rotate` (new
  teacher code and token), `resize`, `export`/`import` (the roster: codes,
  names, PINs), `reset` (section 5).
- **Rate limits** (`access.py`): `/api/game/join` allows 30 unknown codes and
  `/api/game/teacher/login` 10 per address per ten minutes, then 429. Only a
  404 counts: a closed or full class and a wrong PIN are refusals of a right
  code, and a whole classroom shares one router. Wrong PINs: 10 per
  (class, name). The address is `CF-Connecting-IP` / first `X-Forwarded-For`
  entry only when `YOMAMA_BEHIND_PROXY=1` (Render sets it), else the socket.
- **Login wall** (`server.py`): every `*.html` except `PUBLIC_PAGES`
  (`/join.html`, `/class.html`) is served only to a browser whose cookie
  `yomama_session` is the token of a seat that still exists in an active class
  (`game_api.token_may_browse`). Anyone else gets `302 /join.html?next=<page>`.
  Gated pages carry `Cache-Control: no-store` and `Vary: Cookie`. Assets stay
  public. Only `PUBLIC_SUFFIXES` (html, css, js, json, images, fonts, media)
  are ever served; `.py`, `.db`, dotfiles, `.git`, the zips and
  `config/quiz*.json` (the answer key) are 404 on purpose.
- **Browser side**: `yomama-net.js` keeps the cookie in step with
  `localStorage.yomama_session_v1` (`{token, name, code}`; `join.html` and
  `class.html` write it, `econ.js` and `econ-nav.js` read it). `account.js`,
  loaded on every page that has the header, makes the `LOG OUT` pill work,
  sends a signed-out browser to `join.html`, signs out after 20 idle minutes
  (`window.YOMAMA_IDLE_MINUTES`, 0 disables) and signs out every other tab.
  It clears `yomama_session_v1`, `yomama_server_cash_v1`, `yomama_teacher_v1`,
  `yomama_teacher_seat_v1` and the cookie. `join.html` honours a same-origin
  `?next=` and shows a message for `?signedout=1|idle`.

Fixed names. Renaming any of these breaks sign-in for the live classes:
the cookie `yomama_session`, the localStorage keys above, the token format
(`secrets.token_urlsafe(24)`, matched by `server.TOKEN_RE`), the routes
`/api/game/join`, `/api/game/teacher/login`, `/api/game/teacher`, and the
response fields listed above.

## 3. What the tests enforce (`tests/test_contract.py` and friends)

Run the whole suite before you finish, not just the economy tests:

    .venv/bin/python -m pytest tests -q
    node --check econ.js econ-nav.js teacher-econ.js account.js yomama-net.js

CI (`.github/workflows/economy.yml`) runs the same on every push. The
access-layer tests fail loudly, with a message naming the section here, when:

- an endpoint in `server.GAME_GET_ROUTES` / `GAME_POST_ROUTES` answers a
  request without a valid token (every handler must raise `ApiError`
  401/403/404 for a bogus token), or is missing from the `_class_locked` name
  list at the bottom of `game_api.py` while touching economy state;
- a page on disk is served without the cookie, or a page with the header
  (`.right-meta`) does not load `account.js`;
- the cookie name, the localStorage keys, `PUBLIC_PAGES` or `AUTO_LOGIN`
  change; `access.LOGIN_LIMITS` names a route that no longer exists;
  `admin.ADMIN_COLUMNS` is not a subset of `game_api.MIGRATIONS`;
- `game.db`, `roster*.json` leave `.gitignore`, or a secret file type becomes
  servable;
- a state payload loses a field the header, the console or the licence gate
  reads (`cash`, `netWorth`, `gateOpen`, `leaderboard`, `name`; `player.cash`,
  `session.code`; teacher `students[].name/netWorth/rank/checklist/gateOpen`,
  roster `name/net_worth/rank`, `count`, `paused`);
- an admin-opened class cannot be joined and played, or `reset`/`import`
  cannot create a fresh player state (they call
  `economy.new_state(cfg, tick, seed=...)`, `economy.net_worth(cfg, st)` and
  `economy.load_config()`: keep those signatures or fix every caller);
- `previews/day3_preview.py` no longer serves a signed-in game.

## 4. Running things now

**The real server, with a class** (what students get):

    python3 server.py 3000              # or: python3 run_server.py 3000
    python3 admin.py open --label DEV --size 5     # against ./game.db; the server
                                                   # must have run once (it creates the tables)

Sign in at `http://127.0.0.1:3000/join.html` with the printed class code, any
name and any 4-digit PIN; the console is `class.html` with the teacher code.
`python3 admin.py list` shows the classes. Codex normally has this server
running on :3000 already; do not start a second one on the same port.

**Previews and Playwright** (no class code, temp database):

    python3 previews/day3_preview.py 3003 --days 14     # or --fresh; add --no-snapshot
    node tests/ui_viewport.cjs http://127.0.0.1:3003    # and the other tests/ui_*.cjs

The preview process sets `AUTO_LOGIN = True` for itself, seats one SOLO player,
turns the wall off on that port and serves every page already signed in as
that seat (localStorage seeded before `account.js` runs, idle sign-out off).
The `tests/ui_*.cjs` checks therefore work unchanged. For an ad-hoc launcher
do not subclass `server.NewsProxyHandler` by hand; use the three lines at the
top of `previews/preview_support.py`. It refuses to run on the real `game.db`.

`tests/ui_account.cjs` is the exception: it tests sign-in itself, so it needs
the real server and a real class code:
`node tests/ui_account.cjs http://127.0.0.1:3000 CODE`.

Playwright is installed one directory above the project (`../node_modules`);
`node tests/...` from the project root finds it.

## 5. Changing the economy: what reaches a running class

- A class snapshots the rules at its first join (or the teacher's first look)
  into `sessions.econ_config`. Editing `config/economy.v4.json` or the engine
  changes **new classes only**. `game_api.econ_config()` replaces a snapshot
  only when it has no `fun` key, or when the startup config is version 4 and
  the snapshot is not.
- To put new rules on an existing class: deploy first, then
  `python3 admin.py reset CODE --yes` (on Render: `--db /data/game.db` from the
  Shell tab). Seats, names, PINs, tokens and both codes stay; cash, buildings,
  goods, positions and the class clock start over. Without `--yes` nothing
  happens. Saying "the balance changed" is not enough: say the classes need a
  reset, or that old saves migrate in place.
- Old saves in a class that keeps its snapshot go through
  `production_economy.migrate_state` on load. A new state field needs a
  default there, not only in `new_state`.
- If the config `version` ever moves past 4, grep `game_api.py` for
  `version') == 4` first; a dozen branches key on it, and `reset`/`import`
  assume the current version.
- Player rows: `players.econ` (state JSON), `econ_meta` (tick, report),
  `econ_nw` (net worth cache the leaderboard and roster read), `cash` (the
  Part 2 wallet), `buildings` (display blob), `pin`, `token`. New columns go
  into `game_api.MIGRATIONS` (and `admin.ADMIN_COLUMNS` if `admin.py` must read
  them), never into the `CREATE TABLE` text: existing databases would not get them.

## 5b. The LEAD page (class standings)

`memos.html` keeps the original look - fighter cards, portraits, PTS, the
Daily/Weekly/Monthly strip - but every row is a real seat: `memos-bars.js`
reads `/api/game/state` (`leaderboard`: `name`, `net_worth`, `rank`, `you`,
`gain.{daily,weekly,monthly}`) every 15 s, PTS is net worth, the board is
ranked by it, and the timeframe buttons only choose which gain the delta
line shows. Portraits are a stable hash of class code + name over
`assets/hero-select/player-*.png` (no backups). Gains come from the
`standings` table: `_save_state` records each seat's opening figure per day
(`INSERT OR IGNORE`), `reset` and the teacher's `reset_player` clear it.
There are no sample fighters, no simulated points and no preview flag; the
LEAD tab stays visible in every page's navigation. The earlier plain-row
version, its `class_preview.py` and their tests were removed on the user's
decision.

## 6. Adding things

- **An endpoint**: register it in `server.GAME_GET_ROUTES` /
  `GAME_POST_ROUTES`; authenticate with `_auth(conn, body)` (or
  `_teacher_auth`); add its name to the `_class_locked` list at the bottom of
  `game_api.py` if it reads or writes economy state; register it in
  `access.LOGIN_LIMITS` if it takes a code from a stranger. Return `ApiError`,
  never a dict, for a bad token.
- **A page**: copy the header from `buildings.html`, including
  `<script src="./account.js?v=1">` after `econ.js`. The wall covers every
  `.html` automatically; do not add pages to `server.PUBLIC_PAGES`.
- **A file the browser must fetch**: its suffix has to be in
  `server.PUBLIC_SUFFIXES`. A file that must stay private must not have one of
  those suffixes, or needs its own rule in `is_public_path` (as `config/quiz*`).
- **Something the teacher console shows**: `class.html` polls
  `POST /api/game/teacher {action: "roster"}` and `teacher-econ.js` polls
  `GET /api/game/teacher/econ`; both send `teacher_token`.

## 7. Git and working next to another agent

- Branch: `classroom-server-and-economy` (`main` is far behind; do not merge
  or push there). Origin: `github.com/watchmk98-code/yomama`.
- Both agents edit this tree at once. Before staging, run `git status`: files
  you did not touch may be modified or untracked by the other agent. Stage by
  name (`git add file1 file2`), not `git add -A` or `git add .`, and do not
  revert or "clean up" changes you did not make.
- Never commit `game.db*`, `roster*.json`, `.checks/`, `previews/*.log`,
  `backups/`, the zips. They are gitignored; if `git status` shows one, stop.
- If you must edit `access.py`, `admin.py`, `account.js`, `run_server.py`,
  `render.yaml` or the access parts of `server.py` / `game_api.py`, run the
  whole suite and say so in the commit message.
- Ports in use here: Codex's dev server on :3000, previews on 3001, 3003,
  3005, 3006. Pick a free port for a new preview.
- The Claude Code side puts new work in new files and makes only the small
  integration edits listed in section 2 inside game files; it checks mtimes
  before editing a file the other agent has open.
