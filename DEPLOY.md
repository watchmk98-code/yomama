# Deploying the class server

What you get: one URL your teachers and friends open; classes that only you
can create, each with a class code for the students and a teacher code for the
console; progress that survives restarts and redeploys.

Nothing here touches the game files. Hosting lives in `run_server.py` and
`render.yaml`, provisioning in `admin.py`, the rules in `access.py`.

## 1. Render account

- Sign up with GitHub. Workspace plan: **Hobby** (free). Do not buy Pro.
- Billing: add a card. The instance is a paid one, about $7/month plus $0.25
  for the disk. Free instances have no disk, and Render wipes their filesystem,
  `game.db` included, every time they idle for fifteen minutes.

## 2. Create the service

- New + → **Blueprint** → connect `watchmk98-code/yomama` → pick the branch to
  deploy → Apply. Render reads `render.yaml` and creates the web service, a
  1 GB disk at `/data`, and `YOMAMA_DB=/data/game.db`.
- The first deploy takes a couple of minutes. Your URL is
  `https://<name>.onrender.com`; check that `/join.html` loads.

## 3. Open a class

Service → **Shell** tab (paid instances have one):

    python3 admin.py open --label "9-B" --size 30

    Opened class KRT39  (9-B, 30 seats)

      STUDENTS  join.html   class code   KRT39    + their name + a 4-digit PIN
      TEACHER   class.html  teacher code MQ4TVX   (console for this class only)

The card for a teacher is five lines: the URL; "students go to `/join.html`,
type `KRT39`, a name, and a 4-digit PIN they will remember"; "you go to
`/class.html` and type `MQ4TVX`". One class per group; each gets its own pair.

## 4. Running it

    python3 admin.py list                  # every class: players, state
    python3 admin.py roster KRT39          # who joined, ranked
    python3 admin.py close KRT39           # no new students; the joined ones play on
    python3 admin.py reopen KRT39
    python3 admin.py revoke KRT39          # kill switch: nobody in the class can play
    python3 admin.py restore KRT39
    python3 admin.py kick KRT39 "ALEX K"   # frees the seat; they can rejoin from zero
    python3 admin.py rotate KRT39          # new teacher code if the old one got out

The same commands work on your machine against `./game.db`.

## 5. Updating the code

`render.yaml` turns auto-deploy off: a service with a disk restarts on every
deploy, which would throw a class out mid-lesson. Push whenever you like and
press **Manual Deploy** between classes.

## What the server enforces

- No HTTP endpoint opens a class; `POST /api/game/session` is gone (404).
- Every game request needs a player token from `join.html`; there is no solo
  or auto-login player (`AUTO_LOGIN = False` in `game_api.py`).
- A closed class refuses new seats but lets its own students back in with
  their name and PIN. A revoked class refuses everyone, teacher included.
- `class.html` exchanges the teacher code for the console token at
  `POST /api/game/teacher/login`; `rotate` invalidates both.
- Wrong codes are budgeted per address: 30 per ten minutes on `join`, 10 on
  `teacher/login`, then 429. Right answers never count, so a whole class
  behind one router is fine. On Render the address comes from
  `X-Forwarded-For` (`YOMAMA_BEHIND_PROXY=1`); on a LAN, from the socket.
- `game.db`, `.git`, `*.py` and every other non-page file are never served.
