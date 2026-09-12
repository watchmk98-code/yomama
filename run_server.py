#!/usr/bin/env python3
"""Start the class server the way a host such as Render expects.

    python3 run_server.py [port]

Same as `python3 server.py [port]`, with one addition: when YOMAMA_DB is set
the SQLite file lives there instead of next to the code. A host rebuilds the
code directory on every deploy, so the database has to sit on a persistent
disk, e.g. YOMAMA_DB=/data/game.db.

Kept out of server.py and game_api.py on purpose: hosting concerns live in
this one file and the game files stay untouched.
"""

from __future__ import annotations

import os
from pathlib import Path

import game_api
import server


def main() -> None:
    db = os.environ.get("YOMAMA_DB", "").strip()
    if db:
        path = Path(db).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        game_api.DB_PATH = path          # connect() reads this at call time
    print(f"database      : {game_api.DB_PATH}")
    server.main()                        # the port comes from argv, as with server.py


if __name__ == "__main__":
    main()
