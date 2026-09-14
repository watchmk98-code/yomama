"""Measure free-order refresh choices against fixed, reproducible stock snapshots.

This is a candidate-selection experiment, not a repeated-delivery income bot or
human playtest. It uses the isolated three-card engine and never opens a database.
Run: .venv/bin/python previews/playtest_order_refreshes.py
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import order_engine as O
import production_economy as E
import rules_tables
from previews.order_classes_preview import sample_town


WINDOWS = (1, 3, 10, 50)
RARITIES = tuple(r["id"] for r in E.ORDER_ROLLS)
PROFILES = (("base", 1), ("production_3", 3))


def mean(values):
    return round(statistics.mean(values), 6) if values else None


def town(cfg, count, production, minutes):
    state = sample_town(cfg, count, 71)
    state["cash"] = 1000000  # Removes financing failure from this stock experiment.
    state["inventory"] = {}
    for building in state["b"]:
        building.update(lv=production, sales=1, auto=1, storage=1, reserve=False)
    assert not state["customerContracts"]["active"]
    assert all(E.business_progression.product_unlocked(cfg, state, good["id"])
               for tier in state["tierOf"] for good in cfg["tiers"][tier]["goods"])
    ticks = round(minutes * 60 / cfg["global"]["tick"])
    for tick in range(ticks):
        E.player_tick(cfg, {}, state, tick)
    capacity = {good["id"]: E._good_capacity(cfg, state, slot, good["id"])
                for slot, tier in enumerate(state["tierOf"])
                for good in cfg["tiers"][tier]["goods"]}
    assert all(0 <= state["inventory"].get(gid, 0) <= cap for gid, cap in capacity.items())
    return state, capacity


def candidate(cfg, state, offer, capacity, index):
    goods = E.catalog(cfg)
    protected = E.delivery_reservations(cfg, state, exclude=offer["id"])
    fillable = all(state["inventory"].get(n["goodId"], 0) - protected.get(n["goodId"], 0)
                   >= n["quantity"] for n in offer["requirements"])
    retail = sum(n["quantity"] * goods[n["goodId"]]["unitPrice"]
                 for n in offer["requirements"])
    rarity = next(r for r in E.ORDER_ROLLS if r["id"] == offer["rarity"])
    clipped = 0
    for need in offer["requirements"]:
        good = goods[need["goodId"]]
        raw = max(2, math.ceil(cfg["production"]["orderMinutes"][index] * 60
                               / (good["cycleTicks"] * cfg["global"]["tick"])))
        requested = math.ceil(raw * rarity["quantityPercent"] / 100)
        assert need["quantity"] == min(requested, capacity[need["goodId"]])
        clipped += requested > capacity[need["goodId"]]
    return dict(fillable=fillable, rarity=offer["rarity"], recipe=offer["recipeId"],
                cash=offer["reward"], retailValue=retail, cashPerRetailValue=offer["reward"] / retail,
                materials=offer["materials"], units=sum(n["quantity"] for n in offer["requirements"]),
                products=len(offer["requirements"]), clippedProducts=clipped,
                deliverySeconds=offer.get("deliverySeconds"),
                cashPerDeliverySecond=(offer["reward"] / offer["deliverySeconds"] if index == 0 else None))


def summarize(sequences):
    rows = [row for sequence in sequences for row in sequence]
    by_rarity = {}
    for rarity in RARITIES:
        subset = [row for row in rows if row["rarity"] == rarity]
        by_rarity[rarity] = dict(count=len(subset), share=len(subset) / len(rows),
            fillableShare=mean([int(row["fillable"]) for row in subset]),
            meanCashPerRetailValue=mean([row["cashPerRetailValue"] for row in subset]),
            meanCash=mean([row["cash"] for row in subset]),
            meanMaterials=mean([row["materials"] for row in subset]),
            meanProducts=mean([row["products"] for row in subset]),
            meanUnits=mean([row["units"] for row in subset]),
            shelfClippedOfferShare=mean([int(row["clippedProducts"] > 0) for row in subset]),
            meanDeliverySeconds=mean([row["deliverySeconds"] for row in subset if row["deliverySeconds"] is not None]),
            meanCashPerDeliverySecond=mean([row["cashPerDeliverySecond"] for row in subset if row["cashPerDeliverySecond"] is not None]))
    windows = {}
    for size in WINDOWS:
        selections = []
        first_choices = []
        for sequence in sequences:
            # Every consecutive window is included. Overlapping windows are
            # correlated samples, not independent trials or confidence bounds.
            for start in range(len(sequence) - size + 1):
                candidates = [row for row in sequence[start:start + size] if row["fillable"]]
                selections.append(max(candidates, key=lambda r: r["cashPerRetailValue"]) if candidates else None)
                first_choices.append(sequence[start] if sequence[start]["fillable"] else None)
        winners = [row for row in selections if row is not None]
        matched_pairs = [(winner, first) for winner, first in zip(selections, first_choices)
                         if winner is not None and first is not None]
        windows[str(size)] = dict(candidateOffers=size, overlappingWindows=len(selections),
            matchShare=mean([int(row is not None) for row in selections]),
            meanBestCashPerRetailValue=mean([row["cashPerRetailValue"] for row in winners]),
            meanBestCash=mean([row["cash"] for row in winners]),
            meanBestMaterials=mean([row["materials"] for row in winners]),
            jackpotChosenShareAmongMatches=mean([int(row["rarity"] == "jackpot") for row in winners]),
            meanPremiumGainWhenFirstAlreadyFillable=mean([
                winner["cashPerRetailValue"] - first["cashPerRetailValue"] for winner, first in matched_pairs]),
            meanBestDeliverySeconds=mean([row["deliverySeconds"] for row in winners if row["deliverySeconds"] is not None]))
    return dict(offers=len(rows), fillableShare=mean([int(row["fillable"]) for row in rows]),
                distinctRecipes=len({row["recipe"] for row in rows}), byRarity=by_rarity, windows=windows)


def run(cfg, count, profile, production, args):
    source, capacity = town(cfg, count, production, args.minutes)
    stock_modes = {"after_real_production": copy.deepcopy(source["inventory"]),
                   "artificial_full_shelves": copy.deepcopy(capacity)}
    results = {mode: [] for mode in stock_modes}
    for index in range(3):
        sequences = {mode: [] for mode in stock_modes}
        for seed in range(1, args.seeds + 1):
            starting = copy.deepcopy(source)
            starting.update(rngState=seed, offers=None, orderSerial=0, orderRecipeHistory=[[], [], []])
            board = O.create_board(cfg, starting)
            baseline = copy.deepcopy({key: board[key] for key in ("cash", "materials", "inventory", "tick", "cStats")})
            mode_states = {mode: dict(board, inventory=stock) for mode, stock in stock_modes.items()}
            sequence = {mode: [] for mode in stock_modes}
            for _ in range(args.offers_per_seed):
                receipt = O.apply_action(cfg, board, index, "replace", board["offers"][index]["id"])
                assert receipt["ok"], receipt
                assert all(board[key] == value for key, value in baseline.items()), "A refresh changed stock, time, earnings, or delivery counts"
                offer = board["offers"][index]
                for mode, state in mode_states.items():
                    sequence[mode].append(candidate(cfg, state, offer, capacity, index))
            for mode in stock_modes:
                sequences[mode].append(sequence[mode])
        for mode in stock_modes:
            results[mode].append(dict(card=index + 1, label=O.ORDER_CLASSES[index]["label"], **summarize(sequences[mode])))
    return dict(buildings=count, businessIds=[cfg["tiers"][tier]["id"] for tier in source["tierOf"]],
                profile=profile, levels=dict(production=production, customers=1, warehouse=1),
                snapshotTick=source["tick"], producedValue=source["report"]["produced"],
                walkInCash=source["report"]["retailEarned"],
                stock=source["inventory"], capacities=capacity,
                stockedGoodsAtCapacity=sum(source["inventory"].get(gid, 0) == cap for gid, cap in capacity.items()),
                totalGoods=len(capacity), modes=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--offers-per-seed", type=int, default=200)
    parser.add_argument("--output", type=Path, default=ROOT / ".checks/economy-playtest/order-refreshes.json")
    args = parser.parse_args()
    if args.minutes < 1 or args.seeds < 1 or args.offers_per_seed < max(WINDOWS):
        parser.error("Use positive minutes/seeds and at least 50 offers per seed")
    cfg = E.load_config()
    started = time.monotonic()
    report = dict(experiment="Frozen-stock order candidate selection", minutes=args.minutes,
        seeds=list(range(1, args.seeds + 1)), offersPerSeed=args.offers_per_seed,
        assumptions=["Staged ownership, all owned products unlocked, initial cash 1000000, initial inventory empty.",
                     "Real production/crafting/operating costs/walk-ins run for the snapshot period; no regular buyers.",
                     "All production states use current parameters; only owned buildings and upgrade levels are staged.",
                     "Artificial full shelves are an explicit abundance stress case, not earned stock.",
                     "Each card is sampled independently by actual free replace actions; no deliveries, elapsed time, or stock consumption while sampling.",
                     "The two stock modes inspect exactly the same generated offers.",
                     "Best means highest cash divided by retail value of consumed goods; materials are reported separately.",
                     "Windows contain 1/3/10/50 consecutive candidate offers, not that many extra rerolls after an initial offer.",
                     "Overlapping windows are correlated descriptive samples; this is not human playtesting or a repeated-delivery income forecast."],
        hashes={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in ("config/economy.v4.json", "production_economy.py", "order_engine.py", "delivery_recipes.py")},
        scenarios=[])
    with rules_tables.pinned(cfg):
        for count in (1, 3, 6):
            for profile, production in PROFILES:
                result = run(cfg, count, profile, production, args)
                report["scenarios"].append(result)
                print("{} businesses / {} complete".format(count, profile), flush=True)
    report["elapsedSeconds"] = round(time.monotonic() - started, 2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print("Saved {} in {}s".format(args.output, report["elapsedSeconds"]))


if __name__ == "__main__":
    main()
