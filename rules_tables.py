"""Lookup tables derived from the class rules (cfg) alone.

derived(cfg, name, build) returns build(cfg). While pinned(cfg) is active -
production_economy.advance_class holds it for one replay - each named table
is built once and reused for every call with that same cfg object: the engine
never writes cfg, and nothing else runs between the ticks of a replay, so
every call would rebuild the same table. Outside a pin nothing is cached, so
a caller that edits cfg between calls (tests do) sees its edits, as before.
Tables are shared: callers only read them.
"""
from __future__ import annotations

_pinned = None   # (cfg, {name: table}) while a replay runs


def derived(cfg, name, build):
    pin = _pinned
    if pin is not None and pin[0] is cfg:
        tables = pin[1]
        try:
            return tables[name]
        except KeyError:
            table = tables[name] = build(cfg)
            return table
    return build(cfg)


class pinned:
    """with pinned(cfg): ... - cfg's derived tables live for the block."""

    def __init__(self, cfg):
        self.cfg = cfg

    def __enter__(self):
        global _pinned
        self.saved = _pinned
        _pinned = (self.cfg, {})

    def __exit__(self, *exc):
        global _pinned
        _pinned = self.saved
