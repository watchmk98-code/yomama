#!/usr/bin/env python3
"""Rebuild preload-manifest.js, the list loading.js warms the cache with.

The game ships ~145 MB of sprites. Downloading all of them before the first
screen would be slower than the problem it fixes, so the manifest carries two
lists and loading.js treats them differently:

  core  the small shared art that appears a moment after the first paint and
        is not in the page markup to begin with: the HUD svgs, the order
        reactions, the little stat icons. Kilobytes, all of it. loading.js
        blocks the LOADING screen on these.
  warm  everything heavy - the category and facility squares, the action
        illustrations, the licence badges, the building stills and sheets,
        the craft sheets. loading.js fetches these one at a time once the
        screen is gone, so opening CRAFT or the Expand tab finds them cached.

What the first build screen actually paints - this player's building, their
goods, their customers, the nav icons - is in the page markup, so loading.js
reads that off the page and waits for it as well. It is not listed here: it
is per player, and the browser is fetching it anyway.

Nothing heavy belongs in core. The screen is only honest if it ends when the
page is ready; a core list big enough to outlast the page turns it into a
fixed delay, which is worse than the pop-in it replaces.

Sizes go in the file as well: the bar fills by bytes arrived, not by files
arrived, so a 2 MB sheet does not tick the same as a 4 KB icon.

The query strings matter. styles.css asks for stat_agr.png?v=20260219-1; a
preload of the bare path would fill a different cache entry and the browser
would fetch the icon twice. So every reference in the .html/.css/.js of this
folder is scanned and the version each file is actually asked for is kept.

    python3 preload_manifest.py          # rewrite preload-manifest.js
    python3 preload_manifest.py --check  # non-zero if it is out of date
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "preload-manifest.js"

# Heavy art warmed in the background. Past this the browser is doing more harm
# than good on a shared classroom connection.
WARM_BUDGET_BYTES = 48 * 1024 * 1024

# Nothing bigger than this may block the screen. A file over it is a file a
# whole class waits on, and on school wifi that is seconds each.
CORE_MAX_BYTES = 64 * 1024

# Both "./assets/game-art/ui/coin.svg" and the banner at the root, each with
# the ?v= it is asked for. Stray matches are harmless: only names that are
# also on the curated list below reach the manifest.
REF_RE = re.compile(
    r"\.?/?((?:assets/[A-Za-z0-9_\-./]+|[A-Za-z0-9_\-]+)\.(?:png|svg|jpg|jpeg|gif|webp))"
    r"(\?[A-Za-z0-9_\-=.&]*)?")


def source_files() -> list[Path]:
    """The shipped pages and their scripts - the flat top level, nothing else.

    Older copies of the same pages sit in subfolders (engine/, output/, an
    original.html here and there) still asking for last winter's ?v=. Reading
    them would out-vote the live pages and preload a stale cache entry."""
    out = []
    for path in sorted(ROOT.glob("*")):
        if not path.is_file() or path.suffix.lower() not in (".html", ".css", ".js"):
            continue
        if path == OUT:
            continue        # the last run's own list is not a reference
        out.append(path)
    return out


def query_map() -> dict[str, str]:
    """assets/x.png -> the '?v=...' the pages actually ask for (the common one)."""
    seen: dict[str, Counter] = defaultdict(Counter)
    for path in source_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for rel, query in REF_RE.findall(text):
            seen[rel][query or ""] += 1
    return {rel: counts.most_common(1)[0][0] for rel, counts in seen.items()}


def entry(rel: str, queries: dict[str, str]) -> list | None:
    file = ROOT / rel
    if not file.is_file():
        return None
    return [rel + queries.get(rel, ""), file.stat().st_size]


def globs(*patterns: str) -> list[str]:
    out: list[str] = []
    for pattern in patterns:
        out.extend(sorted(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern) if p.is_file()))
    return out


def build() -> dict:
    queries = query_map()

    # Named one by one, because econ.js builds most of these paths at runtime
    # ('actions/' + icon + '.png') and no scanner can see them.
    core_paths = [
        "assets/game-art/ui/prestige.svg",
        "assets/game-art/ui/workers.svg",
        "assets/game-art/nav/port.svg",
        # Shown the moment an order lands or is missed, which can be seconds in.
        "assets/game-art/reactions/thumbs-up-pixel.svg",
        "assets/game-art/reactions/dollar-sign-pixel.svg",
        "assets/game-art/reactions/lucky-seven-pixel.svg",
        "assets/game-art/reactions/gold-bars-pixel.svg",
        # The 128px stat icons styles.css draws the sector chips with. Their
        # 512px *_custom_square twins are a separate set nothing asks for.
        *[p for p in globs("assets/buildings-icons/stat_*.png")
          if "custom" not in Path(p).name and p in queries],
    ]

    warm_paths = [
        # Heavy, and none of it is on screen at the first paint: the reaction
        # photo, the licence badges, the action illustrations, the category and
        # facility squares (_preview_* are contact sheets for people, not art
        # the game ever loads).
        "assets/game-art/reactions/crying-face-pixel.png",
        *globs("assets/game-art/badges/*.png"),
        "assets/game-art/actions/action_level_up.png",
        "assets/game-art/actions/action_auto_control.png",
        "assets/game-art/actions/action_expand.png",
        *[p for p in globs("assets/buildings-icons/*_custom_square.png")
          if not Path(p).name.startswith("_preview") and p in queries],
        "banner-colored.png",
        *globs("assets/buildings/*.png"),
        *globs("assets/buildings/spritesheets/*.png"),
        *globs("assets/craft/craft-items*.png"),
        *globs("assets/craft/craft-supplies*.png"),
        *globs("assets/craft/business-assets-*.png"),
    ]

    oversized = [p for p in core_paths
                 if (ROOT / p).is_file() and (ROOT / p).stat().st_size > CORE_MAX_BYTES]
    if oversized:
        raise SystemExit("core is for small files; move these to warm: " + ", ".join(oversized))

    core = [e for e in (entry(p, queries) for p in dict.fromkeys(core_paths)) if e]

    warm, spent = [], 0
    # Smallest first: the cheap sheets land while the connection is still free.
    for item in sorted((e for e in (entry(p, queries) for p in dict.fromkeys(warm_paths)) if e),
                       key=lambda e: e[1]):
        if spent + item[1] > WARM_BUDGET_BYTES:
            continue
        warm.append(item)
        spent += item[1]

    return {"core": core, "warm": warm}


def render(data: dict) -> str:
    head = (
        "/* Generated by preload_manifest.py - do not edit by hand.\n"
        "   [url, bytes] per file. core blocks the LOADING screen; warm is\n"
        "   fetched quietly afterwards so the next page opens instantly. */\n"
    )
    lines = ["window.YomamaPreloadManifest = {"]
    for key in ("core", "warm"):
        lines.append('  "%s": [' % key)
        lines.extend("    %s," % json.dumps(item, separators=(",", " ")) for item in data[key])
        lines.append("  ],")
    total = sum(size for key in ("core", "warm") for _, size in data[key])
    lines.append('  "version": %s' % json.dumps(str(total)))
    lines.append("};")
    return head + "\n".join(lines) + "\n"


def main() -> int:
    text = render(build())
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current == text:
            return 0
        print("preload-manifest.js is out of date; run python3 preload_manifest.py")
        return 1
    OUT.write_text(text, encoding="utf-8")
    data = build()
    core_mb = sum(s for _, s in data["core"]) / 1048576
    warm_mb = sum(s for _, s in data["warm"]) / 1048576
    print("preload-manifest.js: %d core files (%.1f MB), %d warm files (%.1f MB)"
          % (len(data["core"]), core_mb, len(data["warm"]), warm_mb))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
