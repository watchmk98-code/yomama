"""Access rules for the class server: who may join, play, or open the console.

admin.py adds the columns these read (sessions.active, sessions.joins_open,
sessions.teacher_code). A database from before admin.py has none of them, so
a missing column counts as "allowed" and an old game.db keeps working.

ApiError is imported inside the functions because game_api imports this
module; a top-level import would be circular.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections import deque

# Set on a host that fronts the server with a proxy (render.yaml does). Then
# the visitor's address is the first X-Forwarded-For entry; on a LAN, where any
# client could forge that header, it is the peer address.
BEHIND_PROXY = os.environ.get("YOMAMA_BEHIND_PROXY", "") not in ("", "0")


def _col(row, name, default):
    try:
        return row[name]
    except (IndexError, KeyError):      # sqlite3.Row raises IndexError for an unknown column
        return default


def check_active(session) -> None:
    """Every player and teacher request. A revoked class refuses all of them."""
    if not int(_col(session, "active", 1)):
        from game_api import ApiError
        raise ApiError("this class has been closed", 403)


def check_joins_open(session) -> None:
    """join() only: a class can stop taking students while the joined ones play on."""
    check_active(session)
    if not int(_col(session, "joins_open", 1)):
        from game_api import ApiError
        raise ApiError("this class is not taking new students", 403)


def teacher_login(conn, teacher_code) -> dict:
    """Exchange the short teacher code for the session's teacher token.

    The code is for typing off a card; the token is what class.html then
    sends with every console request, exactly as it does today.
    """
    from game_api import ApiError
    code = "".join(str(teacher_code or "").split()).upper()
    if not code:
        raise ApiError("teacher code is required")
    try:
        s = conn.execute("SELECT * FROM sessions WHERE teacher_code=?", (code,)).fetchone()
    except sqlite3.OperationalError:    # no such column: no class was ever opened with admin.py
        s = None
    if s is None:
        raise ApiError("no class with that teacher code", 404)
    check_active(s)
    return {"code": s["code"], "teacher_token": s["teacher_token"],
            "label": _col(s, "label", ""), "class_size": int(s["class_size"])}


class RateLimiter:
    """At most `limit` failed attempts per key per `window` seconds.

    Counts failures only. A whole classroom sits behind one router, so all
    thirty students share one public IP: counting every attempt would lock a
    class out of its own join page. Counting only wrong codes still leaves a
    guesser thirty tries per ten minutes against 33 million class codes.
    """

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._hits: dict = {}
        self._lock = threading.Lock()

    def blocked(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return False
            while q and q[0] <= now - self.window:
                q.popleft()
            if not q:
                del self._hits[key]
                return False
            return len(q) >= self.limit

    def hit(self, key: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._hits.setdefault(key, deque()).append(now)
            if len(self._hits) > 10_000:            # bound memory under a flood
                stale = [k for k, q in self._hits.items() if q[-1] <= now - self.window]
                for k in stale:
                    del self._hits[k]


# Paths that take a code from a stranger, and how many wrong ones to allow.
LOGIN_LIMITS = {
    "/api/game/join":          RateLimiter(30, 600),
    "/api/game/teacher/login": RateLimiter(10, 600),
}


def client_ip(headers, peer: str, behind_proxy: bool | None = None) -> str:
    """The visitor's address, as the limiter keys it.

    Behind a proxy the first X-Forwarded-For entry is the client. A client can
    forge that entry, which only lets it dodge its own budget - the safer
    failure. The last entry is what the nearest hop saw, which behind a CDN is
    the CDN, and one key for everybody would lock a whole class out at once.
    """
    if behind_proxy is None:
        behind_proxy = BEHIND_PROXY
    if behind_proxy:
        forwarded = (headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return peer
