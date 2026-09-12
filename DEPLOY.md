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
    python3 admin.py resize KRT39 40       # seats, your own included; the next student is refused

The same commands work on your machine against `./game.db`.

## 5. Keeping the accounts

The codes and PINs you hand out live in `game.db` on the disk. Keep a copy
of them outside the database too, so they survive anything:

    python3 admin.py --db /data/game.db export > /data/roster.json

and download that file to your own machine as well. It holds every class
code, teacher code, name and PIN - **never put it in git**; the repository
is public, and `roster*.json` is in `.gitignore` for that reason.

To bring the same classes and seats back - a new database, a new service,
or a PIN you changed in the file:

    python3 admin.py --db /data/game.db import /data/roster.json

It creates what is missing and refreshes what exists, with the same codes
and PINs, and never touches anyone's progress.

## 6. A new game, same seats

When the economy has changed and everyone should start over:

1. Deploy the new code first (Manual Deploy), so the rules on disk are the
   rules the server runs.
2. In the Shell: `python3 admin.py --db /data/game.db reset YSNRD --yes`
   (or `reset --all --yes`).

Cash, buildings, goods, positions and the class clock start over under the
new rules. Every name, PIN, class code and teacher code stays exactly as it
was, and browsers that were signed in stay signed in. Without `--yes`
nothing happens.

## 6b. Jump ahead in time (a simulation)

To show what a few days of play look like without waiting for them:

    python3 admin.py --db /data/game.db advance YSNRD F2XHJ --days 4 --random-hours 24 --yes

Each class named moves 4 days ahead in game time, plus a random 0-24 hours
drawn separately per class, and every town in it is replayed as if its
owner had been playing the whole time: buildings produce, shops sell,
regular customers collect, construction finishes. Nothing is wiped and
nobody is signed out; the next time a student opens the game they get the
usual "while you were away" report for the whole stretch. All towns in a
class share one clock, so the jump is per class, not per student. There
is no way back, so the command does nothing without `--yes`. Run it
between sessions: a big jump takes a little while, and a student who is
playing during it would see the days pass in front of them.

That alone only replays the passive economy: nobody buys anything, so the
towns end up with a pile of cash and the same buildings. Add `--play` and
a stand-in visits every town a few times a day and plays it the way a
student would - ships delivery orders, takes on regular customers, picks
a specialty, buys the next business and upgrades - so the towns grow.
Each seat gets its own stable personality (some build wide, some upgrade
deep, some keep money back, some skip visits), so towns differ. The
stand-in only does what a student could do from the pages and never
takes the quiz for anyone.

    python3 admin.py --db /data/game.db advance YSNRD F2XHJ --days 4 --random-hours 24 --play --yes

Already jumped without `--play`? Either let the stand-in spend the pile
on top (`advance CODE --days 1 --play --yes`: the town keeps everything
it has, ends a day further on with businesses and upgrades bought), or
start that class over and replay it properly (`reset CODE --yes`, then
the `--play` command above). Four played days from a fresh town end with
eight or nine businesses and a few million YM.

## 7. Updating the code

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
- `--size` is a seat cap, the teacher's own seat included; the next student
  is told the class is full. `resize` raises it.
- Unknown codes are budgeted per address: 30 per ten minutes on `join`, 10 on
  `teacher/login`, then 429. Only a code nobody has counts - a closed or full
  class and a wrong PIN are refusals of a right code - so a whole class
  behind one router is never locked out. Wrong PINs have their own budget of
  ten per seat. On Render the address is Cloudflare's `CF-Connecting-IP`,
  else the first `X-Forwarded-For` entry (`YOMAMA_BEHIND_PROXY=1`); on a LAN,
  the socket.
- `game.db`, `.git`, `*.py`, the quiz answer key under `config/` and every
  other non-page file are never served.
- No page but the two login screens (`join.html`, `class.html`) is served to
  a browser without the `yomama_session` cookie of a live seat in an active
  class; everyone else gets a 302 to `join.html?next=<page>`. Assets stay
  public. LOG OUT clears the cookie; a browser idle for twenty minutes is
  signed out on its own.
