"""The stand-in player for `admin.py advance --play`.

A time jump on its own only replays the passive economy: shops sell, regulars
collect, builds finish. Nobody buys anything, so four simulated days leave a
town with a pile of cash and the same buildings. With --play, between two
slices of the jump each town gets a short visit from a stand-in who plays the
way a student would: ships the delivery orders whose goods are on the shelf,
takes on a regular customer when a slot is free, picks a specialty, and spends
part of the cash on the next business or an upgrade.

Every decision goes through the engine's own functions, so nothing happens
here that a student could not do from the pages. The stand-in has a
personality drawn from the class seed and the seat, stable across runs, so
towns differ the way real ones do: some build wide, some upgrade deep, some
keep money back, some skip visits. The quiz is never taken for anyone.
"""
from __future__ import annotations

import random

import production_economy as economy

KINDS = ("production", "sales", "storage")


def persona(seed: int) -> dict:
    rng = random.Random(f"persona:{int(seed)}")
    return dict(
        build=rng.uniform(0.3, 1.0),                 # appetite for new businesses
        upgrade=rng.uniform(0.3, 1.0),               # appetite for upgrades
        reserve=rng.choice((0.0, 0.1, 0.25, 0.4)),   # share of cash kept back at each visit
        visits=rng.uniform(0.4, 0.9),                # share of visit chances actually taken
        buys=rng.randint(2, 5),                      # purchases per visit at most
        nextfirst=rng.uniform(0.5, 0.95),            # chance of buying the next business rather than a later one
        kinds=rng.sample(KINDS, len(KINDS)),         # preferred upgrade order
    )


def seat_seed(cfg, player_id: int) -> int:
    return int(cfg["global"]["seed"]) * 7919 + int(player_id) * 13 + 3


def visit(cfg, st, seed: int, when: int) -> dict:
    """One visit at class tick `when`. Returns counts of what happened."""
    p = persona(seed)
    rng = random.Random(f"visit:{int(seed)}:{int(when)}")
    done = dict(skipped=False, orders=0, customers=0, builds=0, upgrades=0, focus=0)
    if rng.random() > p["visits"]:
        done["skipped"] = True
        return done

    # 1. Ship whatever delivery orders the shelf can fill.
    for i in range(len(st.get("offers") or [])):
        if economy.fulfill_order(cfg, st, i).get("ok"):
            done["orders"] += 1

    # 2. A regular customer for a free slot; a larger order once it is offered.
    customers = st.get("customerContracts", {}).get("active", [])
    used = {c["slot"] for c in customers}
    free = [s for s in range(economy._customer_slots(st)) if s not in used]
    if free and rng.random() < 0.8:
        have = {c["customerId"] for c in customers}
        options = [c for c in economy._customer_catalog(cfg, st) if c["available"] and c["id"] not in have]
        if options:
            pick = rng.choice(options)
            if economy.manage_customer_contract(cfg, st, free[0], "accept", customer_id=pick["id"]).get("ok"):
                done["customers"] += 1
    for c in list(customers):
        if not c.get("largerOrder") and c["deliveries"] >= 3 and rng.random() < 0.5:
            economy.manage_customer_contract(cfg, st, c["slot"], "upgrade", contract_id=c["id"])

    # 3. A specialty once a farm or roastery reaches level 3.
    for slot, b in enumerate(st["b"]):
        options = economy.focus_options(cfg, b)
        if options and not b.get("focus") and b["lv"] >= 3 and rng.random() < 0.6:
            if economy.set_focus(cfg, st, slot, rng.choice(options)[0]).get("ok"):
                done["focus"] += 1

    # 4. Spend: the next business or an upgrade, within this visit's budget.
    budget = st["cash"] * (1.0 - p["reserve"])
    for _ in range(p["buys"]):
        spent = _buy_something(cfg, st, p, rng, budget)
        if spent is None:
            break
        budget -= spent
        done[spent_kind(spent)] += 1
    return done


def spent_kind(spent):
    return "builds" if isinstance(spent, Build) else "upgrades"


class Build(int):
    """Cost of a business, so the caller can tell it from an upgrade."""


def _buy_something(cfg, st, p, rng, budget):
    builds = []
    for ti in economy.expand_options(cfg, st):
        quote = economy.can_expand(cfg, st, ti)
        if quote.get("ok") and quote["cost"] <= budget:
            builds.append((ti, quote["cost"]))
    upgrades = []
    for slot in range(len(st["b"])):
        for kind in KINDS:
            cost = economy.upgrade_cost(cfg, st, slot, kind)
            if cost is not None and cost <= budget and cost <= st["cash"]:
                upgrades.append((slot, kind, cost))
    if not builds and not upgrades:
        return None
    weight_b = p["build"] if builds else 0.0
    weight_u = p["upgrade"] if upgrades else 0.0
    if rng.random() * (weight_b + weight_u) < weight_b:
        ti, cost = builds[0] if rng.random() < p["nextfirst"] else rng.choice(builds)
        if economy.expand(cfg, st, ti, st["tick"]).get("ok"):
            return Build(cost)
        return None
    # Preferred kind first; within it, the least developed building.
    for kind in p["kinds"]:
        choices = [u for u in upgrades if u[1] == kind]
        if choices and rng.random() < 0.75:
            slot, kind, cost = min(choices, key=lambda u: (st["b"][u[0]][{"production": "lv", "sales": "sales", "storage": "storage"}[kind]], u[2]))
            break
    else:
        slot, kind, cost = rng.choice(upgrades)
    if economy.buy_upgrade(cfg, st, slot, kind).get("ok"):
        return cost
    return None
