"""Reproducible in-memory comparison of recurring buyers and walk-in sales.

Uses real production, inventory, customer, walk-in, and operating-cost ticks.
Creates staged towns, never opens a database or modifies economy parameters.
Run: .venv/bin/python previews/playtest_regular_buyers.py
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import production_economy as E
import rules_tables
from previews.order_classes_preview import sample_town


PROFILES = (("balanced", 1, 1), ("production_heavy", 3, 1), ("sales_heavy", 1, 3))
ROSTERS = {
    1: {"ingredients": ("corner_grocer", "sunrise_diner")},
    3: {"ingredients": ("corner_grocer", "sunrise_diner", "honey_collective"),
        "finished": ("harbor_bistro", "copper_cafe"),
        "mixed": ("corner_grocer", "harbor_bistro", "copper_cafe")},
    6: {"ingredients": ("corner_grocer", "sunrise_diner", "honey_collective", "harbor_bistro"),
        "finished": ("copper_cafe", "rally_crew", "builders_union", "neighborhood_grid")},
}


def setup(cfg, count, production, sales, roster, mode):
    st = sample_town(cfg, count, 71)
    st["cash"] = 1000000
    for b in st["b"]:
        b.update(lv=production, sales=sales, auto=sales, storage=1, reserve=False)
    E.business_operations.ensure(cfg, st)
    for slot, customer_id in enumerate(roster):
        cash = st["cash"]
        accepted = E.manage_customer_contract(cfg, st, slot, "accept", customer_id=customer_id)
        assert accepted["ok"], accepted
        assert st["cash"] == cash, "Signing a buyer cannot generate cash"
        if mode == "paused":
            paused = E.manage_customer_contract(cfg, st, slot, "pause", contract_id=accepted["contractId"])
            assert paused["ok"], paused
    return st


def snapshot(st):
    return copy.deepcopy(dict(cash=st["cash"], inventory=st["inventory"],
        report=st["report"], activity=st["businessProgression"]["activity"],
        operating=st["businessOperations"]["totalOperatingCosts"]))


def differences(after, before):
    return {key: after.get(key, 0) - before.get(key, 0) for key in set(after) | set(before)
            if after.get(key, 0) != before.get(key, 0)}


def assert_conservation(cfg, before, after):
    goods = E.catalog(cfg)
    produced = differences(after["activity"]["produced"], before["activity"]["produced"])
    sold = differences(after["activity"]["sold"], before["activity"]["sold"])
    consumed = {}
    for gid, qty in produced.items():
        assert qty % goods[gid]["quantity"] == 0
        for need in goods[gid].get("inputs", []):
            ngid = need["goodId"]
            consumed[ngid] = consumed.get(ngid, 0) + qty // goods[gid]["quantity"] * need["quantity"]
    for gid in goods:
        expected = before["inventory"].get(gid, 0) + produced.get(gid, 0) - sold.get(gid, 0) - consumed.get(gid, 0)
        assert after["inventory"].get(gid, 0) == expected, (gid, expected, after["inventory"].get(gid, 0))
        assert expected >= 0
    walkins = after["report"]["retailEarned"] - before["report"]["retailEarned"]
    regulars = after["report"]["customerEarned"] - before["report"]["customerEarned"]
    costs = after["operating"] - before["operating"]
    assert after["cash"] - before["cash"] == walkins + regulars - costs
    return produced, sold, consumed


def run(cfg, count, profile, roster_name, roster, mode, warmup_minutes, measured_minutes):
    label, production, sales = profile
    st = setup(cfg, count, production, sales, roster, mode)
    start = snapshot(st)
    warmup = round(warmup_minutes * 60 / cfg["global"]["tick"])
    ticks = round(measured_minutes * 60 / cfg["global"]["tick"])
    deliveries = []
    upgraded = []
    before = snapshot(st) if not warmup else None
    measured_start_terms = None
    with rules_tables.pinned(cfg):
        for k in range(warmup + ticks):
            if k == warmup:
                before = snapshot(st)
                measured_start_terms = copy.deepcopy(st["customerContracts"]["active"])
            old = {c["customerId"]: copy.deepcopy(c) for c in st["customerContracts"]["active"]}
            E.player_tick(cfg, {}, st, k)
            for c in st["customerContracts"]["active"]:
                prev = old[c["customerId"]]
                if c["deliveries"] > prev["deliveries"] and k >= warmup:
                    deliveries.append(dict(customer=c["customerId"], tick=k + 1,
                        lateSeconds=max(0, k + 1 - prev["nextDeliveryTick"]) * cfg["global"]["tick"],
                        reward=c["reward"], units=sum(n["quantity"] for n in c["requirements"]),
                        requirements=copy.deepcopy(c["requirements"])))
                if mode == "larger" and c["deliveries"] >= 3 and not c["largerOrder"]:
                    result = E.manage_customer_contract(cfg, st, c["slot"], "upgrade", contract_id=c["id"])
                    assert result["ok"], result
                    upgraded.append(dict(customer=c["customerId"], tick=k + 1))
    after = snapshot(st)
    produced, sold, consumed = assert_conservation(cfg, before, after)
    assert_conservation(cfg, start, after)
    goods = E.catalog(cfg)
    walkin_units = differences(after["activity"]["salesBySource"].get("walkIns", {}),
                               before["activity"]["salesBySource"].get("walkIns", {}))
    regular_units = differences(after["activity"]["salesBySource"].get("regularBuyers", {}),
                                before["activity"]["salesBySource"].get("regularBuyers", {}))
    walkins = after["report"]["retailEarned"] - before["report"]["retailEarned"]
    regulars = after["report"]["customerEarned"] - before["report"]["customerEarned"]
    costs = after["operating"] - before["operating"]
    capacities = {g["id"]: E._good_capacity(cfg, st, slot, g["id"])
                  for slot, ti in enumerate(st["tierOf"]) for g in cfg["tiers"][ti]["goods"]}
    assert all(qty <= capacities[gid] for gid, qty in after["inventory"].items()), "Normal shelf capacities must hold"
    assert sum(event["reward"] for event in deliveries) == regulars, "Shipment events must match actual credited cash"
    assert sum(event["units"] for event in deliveries) == sum(regular_units.values()), "Shipment events must match actual stock debits"
    buyer_results = []
    for c in st["customerContracts"]["active"]:
        events = [event for event in deliveries if event["customer"] == c["customerId"]]
        nominal = measured_minutes * 60 / c["intervalSeconds"]
        buyer_results.append(dict(customer=c["customerId"], shipments=len(events),
            cash=sum(event["reward"] for event in events), units=sum(event["units"] for event in events),
            nominalShipments=nominal, deliveredFractionOfNominal=round(len(events) / nominal, 4),
            onTimeShipments=sum(event["lateSeconds"] == 0 for event in events),
            meanLateSeconds=round(sum(event["lateSeconds"] for event in events) / len(events), 2) if events else None,
            maxLateSeconds=max((event["lateSeconds"] for event in events), default=None),
            endOverdueSeconds=0 if c["paused"] else max(0, st["tick"] - c["nextDeliveryTick"]) * cfg["global"]["tick"],
            finalTerms=dict(reward=c["reward"], intervalSeconds=c["intervalSeconds"], requirements=c["requirements"], largerOrder=c["largerOrder"])))
    result = dict(buildings=count, profile=label, productionLevel=production, customerLevel=sales,
        warmupMinutes=warmup_minutes, measuredMinutes=measured_minutes,
        roster=roster_name, mode=mode, buyerIds=list(roster),
        walkinCash=walkins, regularCash=regulars, operatingCost=costs, netCash=walkins + regulars - costs,
        netPerMinute=round((walkins + regulars - costs) / measured_minutes, 4),
        walkinUnits=sum(walkin_units.values()), regularUnits=sum(regular_units.values()),
        walkinUnitsByGood=walkin_units, regularUnitsByGood=regular_units,
        productionByGood=produced, craftingInputsByGood=consumed, salesByGood=sold,
        startStock=before["inventory"], endStock=after["inventory"],
        startStockRetailValue=sum(goods[gid]["unitPrice"] * qty for gid, qty in before["inventory"].items()),
        endStockRetailValue=sum(goods[gid]["unitPrice"] * qty for gid, qty in after["inventory"].items()),
        shelfCapacity=capacities, fullShelves=sum(after["inventory"].get(gid, 0) >= cap for gid, cap in capacities.items()),
        buyers=buyer_results, deliveries=deliveries, upgraded=upgraded,
        measuredStartTerms=measured_start_terms, conservationPassed=True)
    fingerprint = dict(cash=st["cash"], inventory=st["inventory"], productionWork=st["productionWork"],
        salesWork=st["salesWork"], report=st["report"], activity=st["businessProgression"]["activity"],
        costs=st["businessOperations"]["totalOperatingCosts"])
    result["economyFingerprint"] = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".checks/economy-playtest/regular-buyers.json")
    parser.add_argument("--warmup-minutes", type=int, default=10)
    parser.add_argument("--minutes", type=int, default=60)
    args = parser.parse_args()
    cfg = E.load_config()
    results = []
    for count in (1, 3, 6):
        for profile in PROFILES:
            baseline = run(cfg, count, profile, "none", (), "walkins_only", args.warmup_minutes, args.minutes)
            results.append(baseline)
            for roster_name, roster in ROSTERS[count].items():
                for mode in ("active", "paused", "larger"):
                    case = run(cfg, count, profile, roster_name, roster, mode, args.warmup_minutes, args.minutes)
                    case["netDifferenceFromWalkins"] = case["netCash"] - baseline["netCash"]
                    if mode == "paused":
                        assert case["economyFingerprint"] == baseline["economyFingerprint"], "Paused buyers must match baseline"
                        case["pausedMatchesBaseline"] = True
                    results.append(case)
                    print(count, profile[0], roster_name, mode, "net", case["netCash"], "delta", case["netDifferenceFromWalkins"], flush=True)
        # Every currently eligible buyer alone distinguishes roster selection
        # from simply treating all regular contracts as one income multiplier.
        for buyer in E._customer_catalog(cfg, setup(cfg, count, 1, 1, (), "walkins_only")):
            if not buyer["available"]:
                continue
            case = run(cfg, count, PROFILES[0], "single_" + buyer["id"], (buyer["id"],), "active", args.warmup_minutes, args.minutes)
            baseline = next(r for r in results if r["buildings"] == count and r["profile"] == "balanced" and r["mode"] == "walkins_only")
            case["netDifferenceFromWalkins"] = case["netCash"] - baseline["netCash"]
            results.append(case)
    sensitivity = []
    for count in (1, 3, 6):
        roster_name = "ingredients" if count == 1 else "mixed" if count == 3 else "finished"
        for profile in (PROFILES[0], PROFILES[2]):
            baseline = run(cfg, count, profile, "none", (), "walkins_only", 360, args.minutes)
            case = run(cfg, count, profile, roster_name, ROSTERS[count][roster_name], "active", 360, args.minutes)
            case["netDifferenceFromWalkins"] = case["netCash"] - baseline["netCash"]
            sensitivity.extend((baseline, case))
    sources = ("config/economy.v4.json", "production_economy.py", "business_progression.py",
               "business_operations.py", "workforce.py", "previews/playtest_regular_buyers.py")
    report = dict(sourceSha256={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources},
        setup=dict(seed=71, warmupMinutes=args.warmup_minutes, measuredMinutes=args.minutes,
        startingCash=1000000, startingInventory="empty", buildings="first 1, 3, or 6 tier businesses",
        unlocked="all products of owned businesses via staged grandfathering; no quest speed perks",
        storageLevel=1, staffing="none", focus="balanced", walkins="enabled in every business",
        costs="actual whole-YM per-completed-batch operating expenses", regularPercent=E.CUSTOMER_RETAIL_PERCENT,
        largerOrders="opt in through real upgrade action after three successful shipments; timer resets normally",
        excluded="manual orders, project/quest submissions, purchases, offline absence, and build costs",
        lateness="actual shipment tick minus its saved due tick; subsequent due ticks reset after actual delivery",
        evidence="real player_tick, goods/cash conservation on full run and measured window, paused-baseline exact economy fingerprint"),
        cases=results, matureTownSensitivity=sensitivity)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    print("Saved", len(results), "initial cases and", len(sensitivity), "mature-town sensitivity cases to", args.output)


if __name__ == "__main__":
    main()
